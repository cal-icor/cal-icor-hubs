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

Hooks enforce: yamllint, ruff (Python linting + formatting), pyupgrade, isort, black, flake8, sops-encryption (blocks unencrypted secrets), codespell, end-of-file-fixer, requirements-txt-fixer, check-case-conflict, check-executables-have-shebangs. The tofu hooks (`tofu_fmt`, `terragrunt_fmt`, `terragrunt_hcl_validate`, `terraform-docs-go`) run locally only — they sit under `ci.skip` in `.pre-commit-config.yaml`, so pre-commit.ci does not run them.

## GitHub Actions Conventions

- Pin actions using version tags (e.g., @v4), NOT SHA hashes
- In the image repos, use `vars.IMAGE` for image references, not `github.repository` (no workflow in this repo builds an image)
- Do NOT bump the labeler action version (known globbing pattern regression in v6) unless you fix the globbing found in cal-icor-hubs/.github/labeler.yml
- Always run actionlint after modifying workflow files

## Secrets: SOPS encryption

All files matching `deployments/*/secrets/*`, `support/secrets.yaml`, and `jupyterhub-home-nfs/secrets/*` **must be encrypted** with SOPS before committing. The pre-commit hook will block unencrypted secrets. Staging/prod secrets encrypt under GCP KMS key `projects/cal-icor-hubs/locations/global/keyRings/jupyterhubs/cryptoKeys/sops`. The dev cluster uses a separate `sops-dev` key for `deployments/dev/secrets/*` and `dev/secrets.yaml`, so dev CI can only decrypt dev secrets (see `.sops.yaml`, which matches the first rule in order). `scripts/secrets/*` (the CILogon admin credentials read by `scripts/cilogon_clients.py`) also encrypts under `sops-dev`.

```bash
# Encrypt a plain secrets file
sops --output deployments/<hub>/secrets/prod.yaml --encrypt deployments/<hub>/secrets/prod.plain.yaml
```

## Deployment architecture

### Branch model
- `staging` branch → deploys to staging hubs (e.g. `staging.jupyter.cal-icor.org`)
- `prod` branch → deploys to production hubs (e.g. `jupyter.cal-icor.org`)
- All development work goes through feature branches → PR to `staging`
- `prevent-prod-merges.yaml` enforces this: only `staging` can merge into `prod`, and `prod` can't merge into `staging`

### How deployments are triggered (GitHub Actions)
Merging to `staging` or `prod` triggers `.github/workflows/deploy-spring-2025.yaml`, the single entry point for the prod cluster. It is a stack of four layers run in order — cluster (tofu) → support → nfs → hub — each a reusable workflow in `.github/workflows/deploy-spring-2025-<layer>.yaml`. A layer runs only if every layer before it succeeded or was skipped.

The `gate` job decides which layers run, via `.github/scripts/decide-layers.py` against a layer spec written inline in the workflow. On push the decision comes from the merged PR's labels plus the branch; on `workflow_dispatch` the inputs pass straight through. Two gate rules to know:
- **`requires`**: support, nfs and hub are forced off unless the cluster already exists (a read-only `gcloud container clusters describe` probe) or is being created in the same run. A layer suppressed this way is reported as a `::notice::` annotation; the change stays committed and deploys on the next stack stand-up.
- **`always_on`**: the hub layer has no gate label of its own — it is on for every push, and the hub leaf resolves *which* hubs from the labels. No hub labels means an empty matrix and a skipped deploy job.

Which layers deploy is controlled by **PR labels**, applied by the labeler on path:
- Label `tofu-spring-2025` → `terragrunt run --all apply` over `tofu/clusters/spring-2025` (network and node pools; the spring-2025 control plane was created by hand and has no tofu unit)
- Label `support-deployment` → deploys the support chart
- Label `jupyterhub-home-nfs-deployment` → deploys the `jupyterhub-home-nfs` chart
- Label `hub-images` or `jupyterhub-deployment` → redeploy **all** hubs
- Label `hub: <name>` (e.g. `hub: jupyter`) → deploy only that hub

The cluster, support and nfs layers are `shared_branch_only`, so they deploy from `staging` only (there is no separate staging environment for either chart); a merge to `prod` runs the hub layer alone. The script `.github/scripts/determine-hub-deployments.py` reads the `GITHUB_PR_LABEL_*` env vars (set in the gate job from the merge commit's PR labels via `irby/get-labels-on-push`) to determine which hubs to deploy.

A tofu destroy is label-only: merge a PR labelled `tofu-destroy-spring-2025` to `staging`. No dispatch menu offers a destroy, and a destroy forces every other layer off in that run. It removes the node pools and network (still a full outage) but never the control plane, so `prod-deploy@`'s RBAC binding survives.

**Labels are applied by path, not by intent** — a comment-only edit under `tofu/clusters/spring-2025/` still gets `tofu-spring-2025` and will run a real apply on merge. Strip deploy-driving labels before merging a docs-only PR.

### Dev cluster

`.github/workflows/deploy-dev.yaml` is the dev cluster's entry point, a stack of five layers: cluster (tofu) → support → nfs → nfs-volume → hub, each in `deploy-dev-<layer>.yaml`. It uses the same gate as prod: label-gated on push to `staging` or `prod`, or `workflow_dispatch`. The cluster, support, nfs and nfs-volume layers run from `staging` only; `hub-dev` deploys from both branches (a `staging` push deploys the dev hub's staging environment, a `prod` push its prod environment). Its labels are `tofu-dev`, `support-dev`, `nfs-dev`, `nfs-volume-dev` and `hub-dev`, applied from `tofu/clusters/dev/**`, `dev/rbac/**` and the files under `dev/` (`support-values.yaml`, `secrets.yaml`, `nfs-values.yaml`, `nfs-volume.yaml`). Dev config lives under `dev/` on purpose: editing `support/**` or `jupyterhub-home-nfs/**` gets the prod labels and deploys the prod charts. The dev hub is `deployments/dev`, labelled `hub-dev`, never `hub: dev`, which prod would pick up.

The `dev` git branch is unrelated to the dev cluster. It is a throwaway snapshot of `staging` and triggers no CI.

### Deploy authentication (keyless WIF)

CI authenticates to GKE with keyless Workload Identity Federation — there are **no service-account keys in the repo**. The GitHub OIDC token is exchanged for short-lived credentials that impersonate `prod-deploy@cal-icor-hubs.iam.gserviceaccount.com` (repo vars `PROD_WIF_PROVIDER` / `PROD_DEPLOY_SA`; cluster coords in `PROD_CLUSTER` / `PROD_ZONE` / `PROD_PROJECT`).

- `deploy-spring-2025-hub.yaml` uses the `.github/actions/gke-auth` composite to write ADC (plus a kubeconfig for the rollout check); hubploy is keyless by default and mints its own GKE kubeconfig from ADC (no gcloud, no key file).
- `deploy-spring-2025-support.yaml` and `deploy-spring-2025-nfs.yaml` use the same `.github/actions/gke-auth` composite (`auth@v3` + `get-gke-credentials@v3`) for raw `helm`; support also does a keyless `oauth2accesstoken` login to the GAR helm registry.
- The `gate` job in `deploy-spring-2025.yaml` authenticates with a bare `auth@v3` (not the composite, whose `get-gke-credentials` is the call that fails on a missing cluster) so its cluster-existence probe works when the cluster is gone. `PROD_DEPLOY_SA` holds `container.clusterViewer` for it.
- Write access is fenced to the `spring-2025` cluster by a `cluster-admin` RBAC ClusterRoleBinding on `prod-deploy@` — project IAM grants only `container.clusterViewer`, since `container.*` roles cannot be IAM-scoped to a single cluster.
- SOPS is still used to decrypt secrets at deploy time; `prod-deploy@` holds `cloudkms.cryptoKeyDecrypter` on the `jupyterhubs/sops` KMS key.
- The tofu cluster deploy (`deploy-spring-2025-cluster.yaml`) authenticates as a separate identity, `prod-infra@cal-icor-hubs.iam.gserviceaccount.com` (repo var `PROD_INFRA_SA`; project roles mirror `dev-infra@`). It also needs `roles/iam.serviceAccountUser` on the default compute SA (`1045396016572-compute@`), which every node pool runs as; without it, node pool creates fail with "does not have access to service account". WIF grants impersonation to the whole repo; access is fenced to `staging` by the `prod-infra` GitHub environment, not by the WIF subject.

#### One-time WIF setup (run once, needs an IAM admin)

The pool, provider, and identity bindings below are created once. The `attribute-condition` locks the pool to the `cal-icor` org and each `principalSet` binding to this one repo, so no other repo can federate in. The provider resource name used in workflows is `projects/1045396016572/locations/global/workloadIdentityPools/github/providers/github`. The `roles/viewer` grant is a repo-wide read-only binding (originally the deleted tofu-ci plan job's identity), separate from the deploy identities.

```bash
gcloud services enable sts.googleapis.com iamcredentials.googleapis.com --project=cal-icor-hubs

gcloud iam workload-identity-pools create github \
  --project=cal-icor-hubs --location=global --display-name="GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc github \
  --project=cal-icor-hubs --location=global --workload-identity-pool=github \
  --display-name="GitHub OIDC" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
  --attribute-condition="assertion.repository_owner == 'cal-icor'"

# Read-only, scoped to this repo's federated identity.
gcloud projects add-iam-policy-binding cal-icor-hubs \
  --role="roles/viewer" \
  --member="principalSet://iam.googleapis.com/projects/1045396016572/locations/global/workloadIdentityPools/github/attribute.repository/cal-icor/cal-icor-hubs"

# Deploy identity for tofu; access is fenced to staging by the prod-infra GitHub environment.
gcloud iam service-accounts add-iam-policy-binding \
  prod-infra@cal-icor-hubs.iam.gserviceaccount.com \
  --project=cal-icor-hubs \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/1045396016572/locations/global/workloadIdentityPools/github/attribute.repository/cal-icor/cal-icor-hubs"

# Node pools run as the default compute SA; creating one needs actAs on it.
gcloud iam service-accounts add-iam-policy-binding \
  1045396016572-compute@developer.gserviceaccount.com \
  --project=cal-icor-hubs \
  --role="roles/iam.serviceAccountUser" \
  --member="serviceAccount:prod-infra@cal-icor-hubs.iam.gserviceaccount.com"
```

### Helm chart structure

```
hub/                        # Wrapper chart (depends on jupyterhub helm chart)
  Chart.yaml                # Wrapper chart metadata (version set by chartpress)
  requirements.yaml         # Declares and pins the jupyterhub chart dependency
  values.yaml               # Global defaults: culling, ingress, singleuser resources,
                            #   CustomAttrSpawner, NFS config, hub image
  templates/
    nfs-pvc.yaml            # NFS PersistentVolumeClaim for user home dirs
    home-dirsize-reporter.yaml
    configmap-hub-templates.yaml  # Hub UI template syncing from git
    configmap-usage-quotas.yaml   # jupyterhub-usage-quotas config
    git-config.yaml         # System-wide gitconfig + GitHub App key Secret (etcGitConfig.enabled)

support/                    # Shared cluster services (one per cluster)
  requirements.yaml         # Pins the subcharts below
  values.yaml               # cert-manager, ingress-nginx, prometheus, grafana, statsd,
                            #   node-placeholder-scaler
  secrets.yaml              # Encrypted Grafana admin password
```

cert-manager runs twice on spring-2025: the support chart's copy (namespace `support`) and an older standalone install in the `cert-manager` namespace. Both are v1.14.5, compete for the same leader leases in `kube-system`, and both register webhooks. Either one can be active after a restart. Don't remove either without first moving its webhooks.

### Per-deployment config layout

```
deployments/<hub-name>/
  hubploy.yaml              # GCP project, cluster, zone
  config/
    common.yaml             # Hub-specific overrides (auth, image, NFS IP, node pools)
    prod.yaml               # Prod-only overrides (hostname, TLS)
    staging.yaml            # Staging-only overrides
  secrets/
    prod.yaml               # Encrypted OAuth client secrets
    staging.yaml            # Encrypted OAuth client secrets
```

Config is merged in order: `hub/values.yaml` → `config/common.yaml` → `config/prod.yaml` (or `staging.yaml`) → `secrets/prod.yaml` (or `staging.yaml`).

### CustomAttrSpawner (hub/values.yaml `02-custom-attr-spawner`)

A custom KubeSpawner subclass that supports per-user and per-group resource overrides via `custom.profiles`, `custom.group_profiles`, `custom.memory`, and `custom.admin` keys in hub config. Admins automatically get a read/write mount of the shared folder at `/home/jovyan/shared_readwrite`.

### Hub image

The hub Docker image lives in `images/hub/Dockerfile`. It extends the z2jh hub image (version must match `hub/requirements.yaml`) and adds pinned `jupyterhub-ltiauthenticator`, `oauthenticator`, `jupyterhub-kubespawner` and `jupyterhub-usage-quotas`. Built and pushed via `chartpress` (config in `chartpress.yaml`); the resulting image tag is stored in `hub/values.yaml` under `jupyterhub.hub.image`.

## NFS home directory system

Cal-ICOR uses [jupyterhub-home-nfs](https://github.com/2i2c-org/jupyterhub-home-nfs) to provide persistent, quota-enforced home directories for all hubs. It replaced the previous Google Filestore setup, and every hub now uses it.

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
| `nfsServer.enableClientAllowlist` / `allowedClients` | Restrict which IPs can mount. **Important:** NFS mounts originate from the node's primary IP, not the pod CIDR — despite upstream docs suggesting pod CIDR `.1` addresses. Allow the node subnet's **whole** primary range, not just the IPs current nodes happen to have (check with `gcloud compute networks subnets list`). spring-2025's is `10.7.196.0/22`, so `10.7.196.*` through `10.7.199.*`. |
| `nodeSelector` / `affinity` | `nodeSelector` pins the pod to the support pool; `affinity` pins it to `us-central1-b`, the zone where the GKE disk lives |

Deployed as the `nfs` layer of `deploy-spring-2025.yaml` (leaf: `.github/workflows/deploy-spring-2025-nfs.yaml`), triggered by the `jupyterhub-home-nfs-deployment` PR label on merge to `staging`.

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

## Creating a new hub deployment

1. Copy `_deploy_configs/institution-example.yaml` to `_deploy_configs/<institution_name>.yaml` and fill in the variables.
2. From the repo root, on the `staging` branch, run:
   ```bash
   ./create_deployment.sh --github_user <your-github-username> <institution_name>

   # Dry run to preview without side effects
   ./create_deployment.sh --github_user <user> --dry-run <institution_name>
   ```
3. After the PR merges, create the hub's alerts: `./create_alerts.sh <hub_name>`. The full checklist is https://docs.cal-icor.org/new-hub/.

`create_deployment.sh` is a thin wrapper around `scripts/create_deployment.py`. It uses cookiecutter (`deployments/template/`) to generate the deployment directory, encrypts secrets with SOPS, execs into the NFS server pod to create the hub's directories, adds the quota paths to `jupyterhub-home-nfs/values.yaml`, adds the `hub: <name>` label to `.github/labeler.yml` and creates it on GitHub, commits and pushes a feature branch, and opens a PR.

## Removing a hub deployment

```bash
./remove_deployment.sh --github_user <your-github-username> <hub_name>
./remove_deployment.sh --github_user <user> --dry-run <hub_name>
```

`remove_deployment.sh` wraps `scripts/remove_deployment.py` and follows https://docs.cal-icor.org/remove-hub/. It deletes the hub's alerts and CILogon client, uninstalls the `<hub>-prod` and `<hub>-staging` helm releases, and opens a PR that removes the label, issue templates and quota paths. Once that PR deploys, it archives and deletes the NFS homedirs, deletes both namespaces, and opens a second PR that removes `deployments/<hub>`. It waits for each PR's checks and asks before merging. `--finish` runs only the second half, `--skip-archive` deletes without archiving. It must run against the `spring-2025` kube context.

## Manual hubploy deploy (for local testing)

```bash
hubploy --verbose deploy --timeout 30m <deployment-name> hub staging
hubploy --verbose deploy --timeout 30m <deployment-name> hub prod
```

Requires local Application Default Credentials (`gcloud auth application-default login`) with access to the cluster and the `jupyterhubs/sops` KMS key. hubploy authenticates via ADC.

## Ignored hubs in CI

`deploy-spring-2025-hub.yaml` passes `--ignore gpu-demo rstudio dev sage` to `determine-hub-deployments.py`, which also ignores `template` by default. So `gpu-demo`, `rstudio`, `dev`, `sage` and `template` are excluded from push-triggered deploys, both all-hubs and per-hub labels (the `hub: sage` label in `.github/labeler.yml` deploys nothing). Every other directory under `deployments/`, including `demo`, deploys on an all-hubs trigger. A `workflow_dispatch` with the `hub` input skips the ignore list. The ignore list in the workflow is the source of truth; check it there, not here.
