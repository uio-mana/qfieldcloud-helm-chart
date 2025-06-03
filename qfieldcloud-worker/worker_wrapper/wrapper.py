import json
import logging
import os
import sys
import tempfile
import traceback
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable

import kubernetes
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import requests
import sentry_sdk
from constance import config
from django.conf import settings
from django.db import transaction
from django.forms.models import model_to_dict
from django.utils import timezone
from qfieldcloud.authentication.models import AuthToken
from qfieldcloud.core.models import (
    ApplyJob,
    ApplyJobDelta,
    Delta,
    Job,
    PackageJob,
    ProcessProjectfileJob,
    Secret,
)
from qfieldcloud.core.utils import get_qgis_project_file
from qfieldcloud.core.utils2 import storage
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

logger = logging.getLogger(__name__)

RETRY_COUNT = 5
TIMEOUT_ERROR_EXIT_CODE = -1
K8S_SIGKILL_EXIT_CODE = 137
TMP_FILE = Path("/tmp")

class QgisException(Exception):
    pass

class JobRun:
    container_timeout_secs = config.WORKER_TIMEOUT_S
    job_class = Job
    command = []

    def __init__(self, job_id: str) -> None:
        try:
            self.job_id = job_id
            self.job = self.job_class.objects.select_related().get(id=job_id)
            self.shared_tempdir = Path(tempfile.mkdtemp(dir=TMP_FILE))
            
            # Load Kubernetes configuration
            try:
                config.load_incluster_config()  # Load in-cluster config when running inside K8s
            except config.ConfigException:
                config.load_kube_config()  # Load kube config when running locally
            
            self.k8s_api = client.BatchV1Api()
            self.k8s_core_api = client.CoreV1Api()
            
        except Exception as err:
            feedback: dict[str, Any] = {}
            (_type, _value, tb) = sys.exc_info()
            feedback["error"] = str(err)
            feedback["error_origin"] = "worker_wrapper"
            feedback["error_stack"] = traceback.format_tb(tb)

            msg = "Uncaught exception when constructing a JobRun:\n"
            msg += json.dumps(msg, indent=2, sort_keys=True)

            if self.job:
                self.job.status = Job.Status.FAILED
                self.job.feedback = feedback
                self.job.save(update_fields=["status", "feedback"])
                logger.exception(msg, exc_info=err)
            else:
                logger.critical(msg, exc_info=err)

    def get_context(self) -> dict[str, Any]:
        context = model_to_dict(self.job)

        for key, value in model_to_dict(self.job.project).items():
            context[f"project__{key}"] = value

        context["project__id"] = self.job.project.id

        return context

    def get_command(self) -> list[str]:
        context = self.get_context()
        return [p % context for p in ["python3", "entrypoint.py", *self.command]]

    def before_k8s_run(self) -> None:
        pass

    def after_k8s_run(self) -> None:
        pass

    def after_k8s_exception(self) -> None:
        pass

    def run(self):
        """The main method to be called on `JobRun`."""
        feedback = {}

        try:
            self.job.status = Job.Status.STARTED
            self.job.started_at = timezone.now()
            self.job.save(update_fields=["status", "started_at"])

            # Concurrency check
            concurrent_jobs_count = (
                self.job.project.jobs.filter(
                    status__in=[Job.Status.QUEUED, Job.Status.STARTED],
                )
                .exclude(pk=self.job.pk)
                .count()
            )

            if concurrent_jobs_count > 0:
                self.job.status = Job.Status.PENDING
                self.job.started_at = None
                self.job.save(update_fields=["status", "started_at"])
                logger.warning(f"Concurrent jobs occurred for job {self.job}.")
                sentry_sdk.capture_message(
                    f"Concurrent jobs occurred for job {self.job}."
                )
                return

            self.before_k8s_run()

            command = self.get_command()
            job_name = f"qfieldcloud-job-{self.job.id}"

            # Create Kubernetes job
            job = self._create_k8s_job(job_name, command)
            
            # Wait for job completion
            exit_code, output = self._wait_for_job_completion(job_name)

            if exit_code == K8S_SIGKILL_EXIT_CODE:
                feedback["error"] = "Kubernetes job killed."
                feedback["error_type"] = "K8S_JOB_KILLED"
                feedback["error_class"] = ""
                feedback["error_origin"] = "container"
                feedback["error_stack"] = ""
            elif exit_code == TIMEOUT_ERROR_EXIT_CODE:
                feedback["error"] = "Worker timeout error."
                feedback["error_type"] = "TIMEOUT"
                feedback["error_class"] = ""
                feedback["error_origin"] = "container"
                feedback["error_stack"] = ""
            else:
                try:
                    with open(self.shared_tempdir.joinpath("feedback.json")) as f:
                        feedback = json.load(f)
                        if feedback.get("error"):
                            feedback["error_origin"] = "container"
                except Exception as err:
                    if not isinstance(feedback, dict):
                        feedback = {"error_feedback": feedback}

                    (_type, _value, tb) = sys.exc_info()
                    feedback["error"] = str(err)
                    feedback["error_origin"] = "worker_wrapper"
                    feedback["error_stack"] = traceback.format_tb(tb)

            feedback["container_exit_code"] = exit_code

            self.job.output = output
            self.job.feedback = feedback
            self.job.save(update_fields=["output", "feedback"])

            if exit_code != 0 or feedback.get("error") is not None:
                self.job.status = Job.Status.FAILED
                self.job.save(update_fields=["status"])

                try:
                    self.after_k8s_exception()
                except Exception as err:
                    logger.error(
                        "Failed to run the `after_k8s_exception` handler.",
                        exc_info=err,
                    )
                return

            self.job.project.refresh_from_db()
            self.after_k8s_run()

            self.job.finished_at = timezone.now()
            self.job.status = Job.Status.FINISHED
            self.job.save(update_fields=["status", "finished_at"])

        except Exception as err:
            (_type, _value, tb) = sys.exc_info()
            feedback["error"] = str(err)
            feedback["error_origin"] = "worker_wrapper"
            feedback["error_stack"] = traceback.format_tb(tb)

            if isinstance(err, requests.exceptions.ReadTimeout):
                feedback["error_timeout"] = True

            logger.error(
                f"Failed job run:\n{json.dumps(feedback, sort_keys=True)}", exc_info=err
            )

            try:
                self.job.status = Job.Status.FAILED
                self.job.feedback = feedback
                self.job.finished_at = timezone.now()

                try:
                    self.after_k8s_exception()
                except Exception as err:
                    logger.error(
                        "Failed to run the `after_k8s_exception` handler.",
                        exc_info=err,
                    )

                self.job.save(update_fields=["status", "feedback", "finished_at"])
            except Exception as err:
                logger.error(
                    "Failed to handle exception and update the job status", exc_info=err
                )

    def _create_k8s_job(self, job_name: str, command: list[str]) -> client.V1Job:
        """Create a Kubernetes job for the QFieldCloud task."""
        token = AuthToken.objects.create(
            user=self.job.created_by,
            client_type=AuthToken.ClientType.WORKER,
            expires_at=timezone.now() + timedelta(seconds=self.container_timeout_secs),
        )

        # Create environment variables
        env_vars = [
            client.V1EnvVar(name="PGSERVICE_FILE_CONTENTS", value=""),
            client.V1EnvVar(name="QFIELDCLOUD_TOKEN", value=token.key),
            client.V1EnvVar(name="QFIELDCLOUD_URL", value=settings.QFIELDCLOUD_WORKER_QFIELDCLOUD_URL),
            client.V1EnvVar(name="JOB_ID", value=self.job_id),
            client.V1EnvVar(name="PROJ_DOWNLOAD_DIR", value="/transformation_grids"),
            client.V1EnvVar(name="QT_QPA_PLATFORM", value="offscreen"),
        ]

        # Add project secrets as environment variables
        for secret in self.job.project.secrets.all():
            if secret.type == Secret.Type.ENVVAR:
                env_vars.append(client.V1EnvVar(name=secret.name, value=secret.value))

        # Create container
        container = client.V1Container(
            name="qfieldcloud-worker",
            image=settings.QFIELDCLOUD_QGIS_IMAGE_NAME,
            command=command,
            env=env_vars,
            resources=client.V1ResourceRequirements(
                limits={
                    "memory": config.WORKER_QGIS_MEMORY_LIMIT,
                    "cpu": str(config.WORKER_QGIS_CPU_SHARES),
                }
            ),
        )

        # Create pod template
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(
                labels={
                    "app": f"{settings.ENVIRONMENT}_worker",
                    "type": self.job.type,
                    "job_id": str(self.job.id),
                    "project_id": str(self.job.project_id),
                }
            ),
            spec=client.V1PodSpec(
                containers=[container],
                restart_policy="Never",
            ),
        )

        # Create job spec
        job_spec = client.V1JobSpec(
            template=template,
            backoff_limit=0,
            ttl_seconds_after_finished=300,  # Clean up job after 5 minutes
        )

        # Create job
        job = client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(name=job_name),
            spec=job_spec,
        )

        try:
            created_job = self.k8s_api.create_namespaced_job(
                namespace=settings.K8S_NAMESPACE,
                body=job,
            )
            return created_job
        except ApiException as e:
            logger.error(f"Exception when creating job: {e}")
            raise

    def _wait_for_job_completion(self, job_name: str) -> tuple[int, str]:
        """Wait for the Kubernetes job to complete and return its exit code and logs."""
        try:
            # Wait for job completion
            while True:
                job = self.k8s_api.read_namespaced_job(
                    name=job_name,
                    namespace=settings.K8S_NAMESPACE,
                )
                
                if job.status.succeeded:
                    exit_code = 0
                    break
                elif job.status.failed:
                    exit_code = 1
                    break
                
                time.sleep(1)

            # Get pod name
            pods = self.k8s_core_api.list_namespaced_pod(
                namespace=settings.K8S_NAMESPACE,
                label_selector=f"job-name={job_name}",
            )
            
            if not pods.items:
                return exit_code, "No pod found for job"

            pod_name = pods.items[0].metadata.name

            # Get pod logs
            logs = self.k8s_core_api.read_namespaced_pod_log(
                name=pod_name,
                namespace=settings.K8S_NAMESPACE,
            )

            return exit_code, logs

        except ApiException as e:
            logger.error(f"Exception when waiting for job completion: {e}")
            return TIMEOUT_ERROR_EXIT_CODE, str(e)

# Inherit from JobRun for specific job types
class PackageJobRun(JobRun):
    job_class = PackageJob
    command = [
        "package",
        "%(project__id)s",
        "%(project__project_filename)s",
        "%(project__packaging_offliner)s",
    ]
    data_last_packaged_at = None

    def before_k8s_run(self) -> None:
        self.data_last_packaged_at = timezone.now()

    def after_k8s_run(self) -> None:
        self.job.project.data_last_packaged_at = self.data_last_packaged_at
        self.job.project.last_package_job = self.job
        self.job.project.save(
            update_fields=(
                "data_last_packaged_at",
                "last_package_job",
            )
        )

        try:
            project_id = str(self.job.project.id)
            package_ids = storage.get_stored_package_ids(project_id)
            job_ids = [
                str(job["id"])
                for job in Job.objects.filter(
                    type=Job.Type.PACKAGE,
                )
                .exclude(id=self.job.id)
                .exclude(
                    status__in=(Job.Status.FAILED, Job.Status.FINISHED),
                )
                .values("id")
            ]

            for package_id in package_ids:
                if package_id == str(self.job.project.last_package_job_id):
                    continue
                if package_id in job_ids:
                    continue
                storage.delete_stored_package(project_id, package_id)
        except Exception as err:
            logger.error(
                "Failed to delete dangling packages, will be deleted via CRON later.",
                exc_info=err,
            )

class DeltaApplyJobRun(JobRun):
    job_class = ApplyJob
    command = ["delta_apply", "%(project__id)s", "%(project__project_filename)s"]

    def __init__(self, job_id: str) -> None:
        super().__init__(job_id)
        if self.job.overwrite_conflicts:
            self.command = [*self.command, "--overwrite-conflicts"]

    def _prepare_deltas(self, deltas: Iterable[Delta]) -> dict[str, Any]:
        delta_contents = []
        delta_client_ids = []

        for delta in deltas:
            delta_contents.append(delta.content)
            if "clientId" in delta.content:
                delta_client_ids.append(delta.content["clientId"])

        local_to_remote_pk_deltas = Delta.objects.filter(
            client_id__in=delta_client_ids,
            last_modified_pk__isnull=False,
        ).values("client_id", "content__localPk", "last_modified_pk")

        client_pks_map = {}
        for delta_with_modified_pk in local_to_remote_pk_deltas:
            key = f"{delta_with_modified_pk['client_id']}__{delta_with_modified_pk['content__localPk']}"
            client_pks_map[key] = delta_with_modified_pk["last_modified_pk"]

        return {
            "deltas": delta_contents,
            "files": [],
            "id": str(uuid.uuid4()),
            "project": str(self.job.project.id),
            "version": "1.0",
            "clientPks": client_pks_map,
        }

    @transaction.atomic()
    def before_k8s_run(self) -> None:
        deltas = self.job.deltas_to_apply.all()
        deltafile_contents = self._prepare_deltas(deltas)

        self.delta_ids = [d.id for d in deltas]

        ApplyJobDelta.objects.filter(
            apply_job_id=self.job_id,
            delta_id__in=self.delta_ids,
        ).update(status=Delta.Status.STARTED)

        self.job.deltas_to_apply.update(last_status=Delta.Status.STARTED)

        with open(self.shared_tempdir.joinpath("deltafile.json"), "w") as f:
            json.dump(deltafile_contents, f)

    def after_k8s_run(self) -> None:
        delta_feedback = self.job.feedback["outputs"]["apply_deltas"]["delta_feedback"]
        is_data_modified = False

        for feedback in delta_feedback:
            delta_id = feedback["delta_id"]
            status = feedback["status"]
            modified_pk = feedback["modified_pk"]

            if status == "status_applied":
                status = Delta.Status.APPLIED
                is_data_modified = True
            elif status == "status_conflict":
                status = Delta.Status.CONFLICT
            elif status == "status_apply_failed":
                status = Delta.Status.NOT_APPLIED
            else:
                status = Delta.Status.ERROR
                is_data_modified = True

            Delta.objects.filter(pk=delta_id).update(
                last_status=status,
                last_feedback=feedback,
                last_modified_pk=modified_pk,
                last_apply_attempt_at=self.job.started_at,
                last_apply_attempt_by=self.job.created_by,
            )

            ApplyJobDelta.objects.filter(
                apply_job_id=self.job_id,
                delta_id=delta_id,
            ).update(
                status=status,
                feedback=feedback,
                modified_pk=modified_pk,
            )

        if is_data_modified:
            self.job.project.data_last_updated_at = timezone.now()
            self.job.project.save(update_fields=("data_last_updated_at",))

    def after_k8s_exception(self) -> None:
        Delta.objects.filter(
            id__in=self.delta_ids,
        ).update(
            last_status=Delta.Status.ERROR,
            last_feedback=None,
            last_modified_pk=None,
            last_apply_attempt_at=self.job.started_at,
            last_apply_attempt_by=self.job.created_by,
        )

        ApplyJobDelta.objects.filter(
            apply_job_id=self.job_id,
            delta_id__in=self.delta_ids,
        ).update(
            status=Delta.Status.ERROR,
            feedback=None,
            modified_pk=None,
        )

class ProcessProjectfileJobRun(JobRun):
    job_class = ProcessProjectfileJob
    command = [
        "process_projectfile",
        "%(project__id)s",
        "%(project__project_filename)s",
    ]

    def get_context(self, *args) -> dict[str, Any]:
        context = super().get_context(*args)

        if not context.get("project__project_filename"):
            context["project__project_filename"] = get_qgis_project_file(
                context["project__id"]
            )

        return context

    def after_k8s_run(self) -> None:
        project = self.job.project
        project.project_details = self.job.feedback["outputs"]["project_details"][
            "project_details"
        ]

        thumbnail_filename = self.shared_tempdir.joinpath("thumbnail.png")
        with open(thumbnail_filename, "rb") as f:
            thumbnail_uri = storage.upload_project_thumbail(
                project, f, "image/png", "thumbnail"
            )
        project.thumbnail_uri = project.thumbnail_uri or thumbnail_uri
        project.save(
            update_fields=(
                "project_details",
                "thumbnail_uri",
            )
        )

    def after_k8s_exception(self) -> None:
        project = self.job.project

        if project.project_details is not None:
            project.project_details = None
            project.save(update_fields=("project_details",))

def cancel_orphaned_workers() -> None:
    """Cancel any orphaned Kubernetes jobs."""
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    k8s_api = client.BatchV1Api()

    try:
        jobs = k8s_api.list_namespaced_job(
            namespace=settings.K8S_NAMESPACE,
            label_selector=f"app={settings.ENVIRONMENT}_worker",
        )
    except ApiException as e:
        logger.error(f"Exception when listing jobs: {e}")
        return

    if not jobs.items:
        return

    job_ids = [job.metadata.name.split("-")[-1] for job in jobs.items]

    worker_with_job_ids = Job.objects.filter(container_id__in=job_ids).values_list(
        "container_id", flat=True
    )

    worker_without_job_ids = set(job_ids) - set(worker_with_job_ids)

    for job_id in worker_without_job_ids:
        try:
            k8s_api.delete_namespaced_job(
                name=f"qfieldcloud-job-{job_id}",
                namespace=settings.K8S_NAMESPACE,
            )
            logger.info(f"Cancel orphaned worker {job_id}")
        except ApiException as e:
            logger.error(f"Exception when deleting job: {e}") 