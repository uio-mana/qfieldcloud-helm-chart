FROM opengisch/qfieldcloud-app:latest

# Install Kubernetes Python client as root
USER root
RUN pip3 install kubernetes

# Create transformation grids directory and download grids
RUN mkdir -p /transformation_grids
ARG TRANSFORMATION_GRIDS_URL
RUN wget --mirror ${TRANSFORMATION_GRIDS_URL} -P /transformation_grids --no-host-directories \
    && chmod a+r /transformation_grids/*

# Copy the Kubernetes wrapper implementation
COPY ./worker_wrapper /usr/src/app/worker_wrapper/

# Set environment variables
ENV PYTHONPATH=/usr/src/app
ENV LOGGER_SOURCE=worker_wrapper

USER app
# Set the entrypoint
ENTRYPOINT ["python", "-m", "worker_wrapper.wrapper"]
