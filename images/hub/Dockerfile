# Should match the hub image used by version of chart in hub/requirements.yaml
# If that changes, this should be changed too!
FROM jupyterhub/k8s-hub:4.3.3

USER root

RUN apt-get update && apt-get install net-tools
RUN apt-get install -y --no-install-recommends libbrotli1
RUN apt-get update && apt-get install -y --only-upgrade ca-certificates && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN python3 -m pip install -r /tmp/requirements.txt
RUN rm -f /tmp/requirements.txt

USER ${NB_USER}
