# Should match the hub image used by version of chart in hub/requirements.yaml
# If that changes, this should be changed too!
FROM jupyterhub/k8s-hub:4.4.0

USER root

RUN apt-get update && apt-get install net-tools
RUN python3 -m pip install --no-cache jupyterhub-ltiauthenticator==1.6.2
RUN python3 -m pip install --no-cache oauthenticator==17.4.0
RUN python3 -m pip install --no-cache jupyterhub-kubespawner==7.1.0

USER ${NB_USER}
