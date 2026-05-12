# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Cal-ICOR JupyterHub infrastructure — Helm charts and deployment configs for running JupyterHub on GKE (Google Kubernetes Engine) for California community colleges and universities. Based on [UC Berkeley DataHub](https://github.com/berkeley-dsep/datahub). Deployments are managed via [hubploy](https://github.com/berkeley-dsep-infra/hubploy).

## Setup

```bash
pip install -r dev-requirements.txt
pre-commit install
pre-commit run --all-files
```

`dev-requirements.txt` is for local development. `requirements.txt` is used only by GitHub Actions CI.

## Linting and pre-commit hooks

```bash
# Run all hooks against all files
pre-commit run --all-files

# Run a specific hook
pre-commit run ruff --all-files
pre-commit run yamllint --all-files
```

Hooks enforce: yamllint, ruff (Python linting + formatting), pyupgrade, isort, black, flake8, sops-encryption (blocks unencrypted secrets), codespell, end-of-file-fixer.

## Secrets: SOPS encryption

All files matching `deployments/*/secrets/*` and `support/secrets.yaml` **must be encrypted** with SOPS before committing. The pre-commit hook will block unencrypted secrets. Encryption uses GCP KMS key `projects/cal-icor-hubs/locations/global/keyRings/jupyterhubs/cryptoKeys/sops`.

```bash
# Encrypt a plain secrets file
sops --output deployments/<hub>/secrets/prod.yaml --encrypt deployments/<hub>/secrets/prod.plain.yaml
```

## Deployment architecture

### Branch model
- `staging` branch → deploys to staging hubs (e.g. `staging.jupyter.cal-icor.org`)
- `prod` branch → deploys to production hubs (e.g. `jupyter.cal-icor.org`)
- All development work goes through feature branches → PR to `staging`

### How deployments are triggered (GitHub Actions)
Merging to `staging` or `prod` triggers `.github/workflows/deploy-hubs.yaml`. Which hubs deploy is controlled by **PR labels**:
- Label `hub-images` or `jupyterhub-deployment` → redeploy **all** hubs
- Label `hub: <name>` (e.g. `hub: jupyter`) → deploy only that hub
- Label `support-deployment` → deploys the support chart (only on `staging`)

The script `.github/scripts/determine-hub-deployments.py` reads `GITHUB_PR_LABEL_HUB_*` env vars set by the labeler to determine which hubs to deploy.

### Helm chart structure

```
hub/                        # Wrapper chart (depends on jupyterhub helm chart)
  Chart.yaml                # Pins jupyterhub chart version
  requirements.yaml         # Declares jupyterhub dependency
  values.yaml               # Global defaults: culling, ingress, singleuser resources,
                            #   CustomAttrSpawner, NFS config, hub image
  templates/
    nfs-pvc.yaml            # NFS PersistentVolumeClaim for user home dirs
    home-dirsize-reporter.yaml
    configmap-hub-templates.yaml  # Hub UI template syncing from git

support/                    # Shared cluster services (one per cluster)
  values.yaml               # cert-manager, ingress-nginx, prometheus, grafana, statsd
  secrets.yaml              # Encrypted Grafana/alertmanager credentials
```

### Per-deployment config layout

```
deployments/<hub-name>/
  hubploy.yaml              # GCP project, cluster, zone, service key path
  config/
    common.yaml             # Hub-specific overrides (auth, image, NFS IP, node pools)
    prod.yaml               # Prod-only overrides (hostname, TLS)
    staging.yaml            # Staging-only overrides
    filestore/              # NFS filestore config
  secrets/
    gke-key.json            # Encrypted GKE service account key
    prod.yaml               # Encrypted OAuth client secrets
    staging.yaml            # Encrypted OAuth client secrets
```

Config is merged in order: `hub/values.yaml` → `config/common.yaml` → `config/prod.yaml` (or `staging.yaml`) → `secrets/*.yaml`.

### CustomAttrSpawner (hub/values.yaml `02-custom-attr-spawner`)

A custom KubeSpawner subclass that supports per-user and per-group resource overrides via `custom.profiles`, `custom.group_profiles`, `custom.memory`, and `custom.admin` keys in hub config. Admins automatically get a read/write mount of the shared folder at `/home/jovyan/shared_readwrite`.

### Hub image

The hub Docker image lives in `images/hub/Dockerfile`. It extends the z2jh hub image (version must match `hub/requirements.yaml`) and adds `jupyterhub-ltiauthenticator` and `oauthenticator`. Built and pushed via `chartpress` (config in `chartpress.yaml`); the resulting image tag is stored in `hub/values.yaml` under `jupyterhub.hub.image`.

## Creating a new hub deployment

Use the automated script (run from repo root, must be on `staging` branch):

```bash
# First create _deploy_configs/<institution>.yaml (see _deploy_configs/*.yaml for examples)
python scripts/create_deployment.py --github_user <your-github-username> <institution_name>

# Dry run to preview without side effects
python scripts/create_deployment.py --github_user <user> --dry-run <institution_name>
```

This uses cookiecutter (`deployments/template/`) to generate the deployment directory, encrypts secrets with SOPS, creates a GitHub label, commits and pushes a feature branch, and opens a PR.

## Manual hubploy deploy (for local testing)

```bash
hubploy --verbose deploy --timeout 30m <deployment-name> hub staging
hubploy --verbose deploy --timeout 30m <deployment-name> hub prod
```

Requires GCP credentials and SOPS key configured locally.

## Ignored hubs in CI

`demo`, `gpu-demo`, `rstudio`, and `sage` are excluded from automatic CI deploys (passed as `--ignore` to `determine-hub-deployments.py`).
