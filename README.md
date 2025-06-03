# QField Cloud Helm Chart

This Helm chart deploys QField Cloud to Kubernetes.

## Adding the Helm Repository

```bash
helm repo add qfieldcloud https://opengisch.github.io/qfieldcloud-helm-chart
helm repo update
```

## Prerequisites

- Kubernetes 1.19+
- Helm 3.2.0+
- PostgreSQL database (external)
- PostGIS-enabled PostgreSQL database (external)

## Installing the Chart

To install the chart with the release name `qfieldcloud`:

```bash
helm install qfieldcloud qfieldcloud/qfieldcloud
```

The command deploys QField Cloud on the Kubernetes cluster in the default configuration. The [Parameters](#parameters) section lists the parameters that can be configured during installation.

## Uninstalling the Chart

To uninstall/delete the `qfieldcloud` deployment:

```bash
helm uninstall qfieldcloud
```

## Architecture

This Helm chart follows Kubernetes best practices and includes the following components:

1. **Django Application**: The main web application serving the QField Cloud API
2. **Worker Processes**: Background workers for processing tasks
3. **Cron Jobs**: For running periodic tasks
4. **Memcached**: For caching
5. **Transformation Grids**: Downloaded as an init container and stored in a persistent volume

The chart is designed to work with external databases (PostgreSQL and PostGIS) rather than deploying them as part of the chart, following the separation of concerns principle.

## Parameters

### Common parameters

| Name                | Description                                        | Value           |
|---------------------|----------------------------------------------------|-----------------|
| `nameOverride`      | String to partially override qfieldcloud.fullname  | `""`            |
| `fullnameOverride`  | String to fully override qfieldcloud.fullname      | `""`            |
| `serviceAccount.create` | Specifies whether a ServiceAccount should be created | `true`        |
| `serviceAccount.name` | The name of the ServiceAccount to use             | `""`            |

### Django application parameters

| Name                           | Description                                                                               | Value           |
|--------------------------------|-------------------------------------------------------------------------------------------|-----------------|
| `django.gunicorn.timeout`      | Gunicorn timeout in seconds                                                               | `120`           |
| `django.gunicorn.maxRequests`  | Maximum number of requests a worker will process before restarting                        | `1000`          |
| `django.gunicorn.workers`      | Number of Gunicorn workers                                                                | `4`             |
| `django.gunicorn.threads`      | Number of threads per worker                                                              | `2`             |
| `django.settings.debug`        | Enable debug mode                                                                         | `false`         |
| `django.settings.environment`  | Environment (production, staging, development)                                            | `production`    |
| `django.settings.secretKey`    | Django secret key (should be provided via secret)                                         | `""`            |
| `django.settings.allowedHosts` | Comma-separated list of allowed hosts                                                     | `"*"`           |
| `django.settings.settingsModule` | Django settings module                                                                    | `qfieldcloud.settings` |
| `django.settings.accountEmailVerification` | Email verification setting                                                             | `mandatory`     |
| `django.settings.useI18n`      | Enable internationalization                                                              | `true`          |
| `django.settings.defaultLanguage` | Default language                                                                        | `en`            |
| `django.settings.defaultTimeZone` | Default time zone                                                                      | `UTC`           |
| `django.settings.authTokenExpirationHours` | Authentication token expiration in hours                                           | `24`            |
| `django.settings.passwordLoginDisabled` | Disable password login                                                              | `false`         |
| `django.settings.subscriptionModel` | Subscription model                                                                   | `free`          |

### Sentry parameters

| Name                           | Description                                                                               | Value           |
|--------------------------------|-------------------------------------------------------------------------------------------|-----------------|
| `django.sentry.dsn`            | Sentry DSN                                                                                | `""`            |
| `django.sentry.release`        | Sentry release                                                                            | `""`            |
| `django.sentry.sampleRate`     | Sentry sample rate                                                                        | `0.1`           |

### Email parameters

| Name                           | Description                                                                               | Value           |
|--------------------------------|-------------------------------------------------------------------------------------------|-----------------|
| `django.email.host`            | SMTP host                                                                                 | `""`            |
| `django.email.useTls`          | Use TLS for SMTP                                                                          | `true`          |
| `django.email.useSsl`          | Use SSL for SMTP                                                                          | `false`         |
| `django.email.port`            | SMTP port                                                                                 | `587`           |
| `django.email.hostUser`        | SMTP username                                                                             | `""`            |
| `django.email.hostPassword`    | SMTP password (should be provided via secret)                                             | `""`            |
| `django.email.defaultFromEmail` | Default from email address                                                              | `noreply@example.com` |

### Storage parameters

| Name                           | Description                                                                               | Value           |
|--------------------------------|-------------------------------------------------------------------------------------------|-----------------|
| `django.storage.type`          | Storage type (local, s3, etc.)                                                            | `local`         |
| `django.storage.accessKeyId`   | Storage access key ID                                                                     | `""`            |
| `django.storage.secretAccessKey` | Storage secret access key (should be provided via secret)                              | `""`            |
| `django.storage.bucketName`    | Storage bucket name                                                                       | `""`            |
| `django.storage.regionName`    | Storage region name                                                                       | `""`            |
| `django.storage.endpointUrl`   | Storage endpoint URL                                                                      | `""`            |
| `django.storage.projectDefaultStorage` | Default storage for projects                                                      | `local`         |

### Database parameters

| Name                           | Description                                                                               | Value           |
|--------------------------------|-------------------------------------------------------------------------------------------|-----------------|
| `database.external`            | Use external database                                                                     | `true`          |
| `database.host`                | Database host                                                                             | `""`            |
| `database.port`                | Database port                                                                             | `5432`          |
| `database.name`                | Database name                                                                             | `qfieldcloud`   |
| `database.user`                | Database user                                                                             | `qfieldcloud`   |
| `database.password`            | Database password (should be provided via secret)                                         | `""`            |
| `database.sslMode`             | Database SSL mode                                                                         | `prefer`        |

### Geodatabase parameters

| Name                           | Description                                                                               | Value           |
|--------------------------------|-------------------------------------------------------------------------------------------|-----------------|
| `geodatabase.external`         | Use external geodatabase                                                                  | `true`          |
| `geodatabase.host`             | Geodatabase host                                                                          | `""`            |
| `geodatabase.port`             | Geodatabase port                                                                          | `5432`          |
| `geodatabase.name`             | Geodatabase name                                                                          | `qfieldcloud_geodb` |
| `geodatabase.user`             | Geodatabase user                                                                          | `qfieldcloud`   |
| `geodatabase.password`         | Geodatabase password (should be provided via secret)                                      | `""`            |

### QGIS parameters

| Name                           | Description                                                                               | Value           |
|--------------------------------|-------------------------------------------------------------------------------------------|-----------------|
| `qgis.image.repository`        | QGIS image repository                                                                     | `opengisch/qfieldcloud-qgis` |
| `qgis.image.tag`               | QGIS image tag                                                                            | `latest`        |
| `qgis.image.pullPolicy`        | QGIS image pull policy                                                                    | `IfNotPresent`  |
| `qgis.transformationGrids.downloadOnStartup` | Download transformation grids on startup                                           | `true`          |
| `qgis.transformationGrids.sourceUrl` | URL to download transformation grids from                                          | `https://cdn.proj.org/` |

### Worker parameters

| Name                           | Description                                                                               | Value           |
|--------------------------------|-------------------------------------------------------------------------------------------|-----------------|
| `worker.enabled`               | Enable worker deployment                                                                  | `true`          |
| `worker.replicaCount`          | Number of worker replicas                                                                 | `1`             |
| `worker.image.repository`      | Worker image repository                                                                   | `opengisch/qfieldcloud` |
| `worker.image.tag`             | Worker image tag                                                                          | `latest`        |
| `worker.image.pullPolicy`      | Worker image pull policy                                                                  | `IfNotPresent`  |
| `worker.resources.limits`      | Worker resource limits                                                                    | `{}`            |
| `worker.resources.requests`    | Worker resource requests                                                                  | `{}`            |

### Memcached parameters

| Name                           | Description                                                                               | Value           |
|--------------------------------|-------------------------------------------------------------------------------------------|-----------------|
| `memcached.enabled`            | Enable Memcached deployment                                                               | `true`          |
| `memcached.image.repository`   | Memcached image repository                                                                | `memcached`     |
| `memcached.image.tag`          | Memcached image tag                                                                       | `1`             |
| `memcached.image.pullPolicy`   | Memcached image pull policy                                                               | `IfNotPresent`  |
| `memcached.resources.limits`   | Memcached resource limits                                                                 | `{}`            |
| `memcached.resources.requests` | Memcached resource requests                                                               | `{}`            |

### Cron jobs parameters

| Name                           | Description                                                                               | Value           |
|--------------------------------|-------------------------------------------------------------------------------------------|-----------------|
| `cronJobs.enabled`             | Enable cron jobs                                                                          | `true`          |
| `cronJobs.image.repository`    | Cron jobs image repository                                                                | `opengisch/qfieldcloud` |
| `cronJobs.image.tag`           | Cron jobs image tag                                                                       | `latest`        |
| `cronJobs.image.pullPolicy`    | Cron jobs image pull policy                                                               | `IfNotPresent`  |
| `cronJobs.schedule`            | Cron schedule                                                                             | `@every 1m`     |
| `cronJobs.resources.limits`    | Cron jobs resource limits                                                                 | `{}`            |
| `cronJobs.resources.requests`  | Cron jobs resource requests                                                               | `{}`            |

### Exposure parameters

| Name                               | Description                                                                               | Value           |
|-----------------------------------|-------------------------------------------------------------------------------------------|-----------------|
| `service.type`                    | Kubernetes Service type                                                                   | `ClusterIP`     |
| `service.port`                    | Kubernetes Service port                                                                   | `80`            |
| `ingress.enabled`                 | Enable ingress record generation for QField Cloud                                         | `false`         |
| `ingress.className`               | IngressClass resource name                                                                | `""`            |
| `ingress.annotations`             | Additional custom annotations for QField Cloud ingress                                    | `{}`            |
| `ingress.hosts`                   | The list of hosts to be covered with this ingress record                                 | `[]`            |
| `ingress.tls`                     | TLS configuration for ingress                                                            | `[]`            |

### Resource parameters

| Name                           | Description                                                                               | Value           |
|--------------------------------|-------------------------------------------------------------------------------------------|-----------------|
| `resources.limits`             | The resources limits for the QField Cloud container                                       | `{}`            |
| `resources.requests`           | The requested resources for the QField Cloud container                                    | `{}`            |

### Pod parameters

| Name                           | Description                                                                               | Value           |
|--------------------------------|-------------------------------------------------------------------------------------------|-----------------|
| `nodeSelector`                 | Node labels for pod assignment                                                            | `{}`            |
| `tolerations`                  | Tolerations for pod assignment                                                            | `[]`            |
| `affinity`                     | Affinity for pod assignment                                                               | `{}`            |

### Persistence parameters

| Name                           | Description                                                                               | Value           |
|--------------------------------|-------------------------------------------------------------------------------------------|-----------------|
| `persistence.static.enabled`   | Enable persistence for static files                                                       | `true`          |
| `persistence.static.size`      | Size of persistent volume for static files                                                | `1Gi`           |
| `persistence.media.enabled`    | Enable persistence for media files                                                        | `true`          |
| `persistence.media.size`       | Size of persistent volume for media files                                                 | `10Gi`          |
| `persistence.transformationGrids.enabled` | Enable persistence for transformation grids                                        | `true`          |
| `persistence.transformationGrids.size` | Size of persistent volume for transformation grids                                   | `1Gi`           |

## Configuration and installation

### Basic installation

```bash
helm install qfieldcloud qfieldcloud/qfieldcloud
```

### Installation with custom values

```bash
helm install qfieldcloud qfieldcloud/qfieldcloud --set django.settings.environment=production
```

### Installation with external databases

```bash
helm install qfieldcloud qfieldcloud/qfieldcloud \
  --set database.external=true \
  --set database.host=my-postgres-host \
  --set database.name=qfieldcloud \
  --set database.user=qfieldcloud \
  --set database.password=my-secret-password \
  --set geodatabase.external=true \
  --set geodatabase.host=my-postgis-host \
  --set geodatabase.name=qfieldcloud_geodb \
  --set geodatabase.user=qfieldcloud \
  --set geodatabase.password=my-secret-password
```

### Installation with ingress

```bash
helm install qfieldcloud qfieldcloud/qfieldcloud \
  --set ingress.enabled=true \
  --set ingress.className=nginx \
  --set ingress.hosts[0].host=qfieldcloud.example.com \
  --set ingress.hosts[0].paths[0].path=/ \
  --set ingress.hosts[0].paths[0].pathType=Prefix \
  --set ingress.tls[0].secretName=qfieldcloud-tls \
  --set ingress.tls[0].hosts[0]=qfieldcloud.example.com
```

## Development

### Packaging the Chart

To package the chart and update the repository index:

```bash
./package.sh
```

This will:
1. Package the chart into a .tgz file
2. Update the repository index
3. Create/update the index.yaml file

## License

Copyright (c) 2024 QField Cloud Team

Licensed under the MIT License - see the [LICENSE](LICENSE) file for details. 