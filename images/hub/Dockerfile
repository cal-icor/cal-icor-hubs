# Should match the hub image used by version of chart in hub/requirements.yaml
# If that changes, this should be changed too!
FROM jupyterhub/k8s-hub:4.3.3

USER root

RUN apt-get update && apt-get install net-tools
RUN apt-get update && apt-get install -y --only-upgrade ca-certificates && rm -rf /var/lib/apt/lists/*
RUN python3 -m pip install --no-cache jupyterhub-ltiauthenticator==1.6.2
RUN python3 -m pip install --no-cache oauthenticator==17.4.0
RUN python3 -m pip install --no-cache jupyterhub-kubespawner==7.1.0
RUN python3 -m pip install --no-cache jupyterhub-usage-quotas==0.1.5

USER ${NB_USER}
