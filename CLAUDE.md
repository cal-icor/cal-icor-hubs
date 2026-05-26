# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Cal-ICOR JupyterHub infrastructure — Helm charts and deployment configs for running JupyterHub on GKE (Google Kubernetes Engine) for California community colleges and universities. Based on [UC Berkeley DataHub](https://github.com/berkeley-dsep/datahub). Deployments are managed via [hubploy](https://github.com/berkeley-dsep-infra/hubploy).

This is a [Zero to Jupyterhub](https://github.com/jupyterhub/zero-to-jupyterhub-k8s/) deployment of [Jupyterhub](https://github.com/jupyterhub/jupyterhub).  The API references for the two are here:

- [z2jh](https://z2jh.jupyter.org/en/stable/resources/reference.html)
- [jupyterhub](https://jupyterhub.readthedocs.io/en/stable/reference/api/index.html)

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

## GitHub Actions Conventions

- Pin actions using version tags (e.g., @v4), NOT SHA hashes
- Use `vars.IMAGE` for image references, not `github.repository`
- Do NOT bump the labeler action version (known globbing pattern regression in v6) unless you fix the globbing found in cal-icor-hubs/.github/labeler.yml
- Always run actionlint after modifying workflow files

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
- Label `support-deployment` → deploys the support chart when merged to `staging` (there is no separate staging environment for support; this is the only CI-triggered support deploy)

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

## NFS home directory system

Cal-ICOR uses [jupyterhub-home-nfs](https://github.com/2i2c-org/jupyterhub-home-nfs) to provide persistent, quota-enforced home directories for all hubs. This replaces the previous Google Filestore setup and will be applied to every hub deployment.

### Architecture

- A single pre-provisioned GKE persistent disk (XFS-formatted) is mounted by an in-cluster NFS server (NFS Ganesha), running in the `jupyterhub-home-nfs` namespace.
- Each hub gets two subdirectories on that disk: `/export/<hub-name>/staging` and `/export/<hub-name>/prod`.
- JupyterHub mounts user home directories via a PersistentVolume/PersistentVolumeClaim that points at the in-cluster NFS service (`home-nfs.jupyterhub-home-nfs.svc.cluster.local`).
- NFSv4 is required — do not revert to v3 (v3 causes portmapper/UDP connectivity issues on GKE).
- A quota enforcer sidecar uses `xfs_quota` to apply per-user hard quotas on the XFS filesystem.

### The `jupyterhub-home-nfs/` chart

This directory is a wrapper Helm chart around the upstream `2i2c-org/jupyterhub-home-nfs` chart. Key values in `jupyterhub-home-nfs/values.yaml`:

| Key | Purpose |
|-----|---------|
| `gke.volumeId` | Pre-provisioned GKE disk ID backing the NFS server |
| `quotaEnforcer.config.QuotaManager.paths` | List of all hub paths subject to quota enforcement; add `/export/<hub>/staging` and `/export/<hub>/prod` when onboarding a hub |
| `quotaEnforcer.config.QuotaManager.hard_quota` | Per-user hard quota in GiB |
| `nfsServer.enableClientAllowlist` / `allowedClients` | Restrict which IPs can mount. **Important:** NFS mounts originate from the node's primary IP (e.g. `10.7.199.*`), not the pod CIDR — despite upstream docs suggesting pod CIDR `.1` addresses. Always include the node subnet (check with `kubectl get nodes -o wide`) in addition to pod CIDR ranges. |
| `nodeSelector` / `affinity` | Pin the pod to the zone where the GKE disk lives |

Deployed via `.github/workflows/deploy-jupyterhub-home-nfs.yaml`, triggered by the `jupyterhub-home-nfs-deployment` PR label on merge to `staging`.

### Hub-side config

Each hub's `config/common.yaml` points at the in-cluster NFS service:

```yaml
nfsPVC:
  enabled: true
  nfs:
    serverIP: <ClusterIP of home-nfs.jupyterhub-home-nfs.svc.cluster.local>
```

And the per-environment share path in `config/prod.yaml` / `config/staging.yaml`:

```yaml
nfsPVC:
  nfs:
    shareName: <hub-name>/prod   # e.g. jupyter/prod
```

`hub/templates/nfs-pvc.yaml` renders the PV (named `<release>-home-nfs`) and PVC (named `home-nfs`) using NFSv4.

### Onboarding a new hub

1. Copy `_deploy_configs/institution-example.yaml` to `_deploy_configs/<institution_name>.yaml` and fill in the variables.
2. From the repo root (on the `staging` branch), run:
   ```bash
   ./create_deployment.sh --github_user <your-github-username> <institution_name>
   ```
   This handles everything: creating NFS directories on the server, generating the deployment config via cookiecutter, encrypting secrets with SOPS, updating `jupyterhub-home-nfs/values.yaml` with the new quota paths, creating the GitHub label, committing, pushing a feature branch, and opening a PR.

## Creating a new hub deployment

Use the shell wrapper script (run from repo root, must be on `staging` branch):

```bash
# First create _deploy_configs/<institution>.yaml (see _deploy_configs/*.yaml for examples)
./create_deployment.sh --github_user <your-github-username> <institution_name>

# Dry run to preview without side effects
./create_deployment.sh --github_user <user> --dry-run <institution_name>
```

`create_deployment.sh` is a thin wrapper around `scripts/create_deployment.py`. It uses cookiecutter (`deployments/template/`) to generate the deployment directory, encrypts secrets with SOPS, execs into the NFS server pod to create the hub's directories, creates a GitHub label, commits and pushes a feature branch, and opens a PR.

## Manual hubploy deploy (for local testing)

```bash
hubploy --verbose deploy --timeout 30m <deployment-name> hub staging
hubploy --verbose deploy --timeout 30m <deployment-name> hub prod
```

Requires GCP credentials and SOPS key configured locally.

## Ignored hubs in CI

`demo`, `gpu-demo`, `rstudio`, and `sage` are excluded from automatic CI deploys (passed as `--ignore` to `determine-hub-deployments.py`).
