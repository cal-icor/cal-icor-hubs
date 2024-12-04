# Cal-ICOR JupyterHubs 

Contains a fully reproducible configuration for JupyterHub for the Cal ICOR deployments.

[Cal ICOR](https://cal-icor.org)

In partnership with [UC Berkeley CDSS](https://cdss.berkeley.edu)

## Single-user server images
All user images are located in their own repositories located in the
[Cal ICOR repo](https://github.com/cal-icor).  You can
find them either by [searching there](https://github.com/orgs/cal-icor/repositories?language=&q=image&sort=&type=all)
or from links in the deployment's `image/README.md`.

## Branches

The `staging` branch always reflects the state of the [staging JupyterHub](https://hub-staging.jupyterhubs.cal-icor.org),
and the `prod` branch reflects the state of the [production JupyterHub](https://hub.jupyterhubs.cal-icor.org).

## Installing the required python packages for working with datahub

In the root directory of this repo, install `dev-requirements.txt` with the
following command:  `pip install -r dev-requirements.txt`.  This will install
the base python packages that are required to perform the tasks associated with
editing, testing, building and deploying hubs.

The other python package definition file, `requirements.txt` is used solely by
our Github Actions CI/CD pipeline.

## Pre-Commit hooks: Installing

The previous step, `pip install -r dev-requirements.txt`, installs the package
[`pre-commit`](https://pre-commit.com/). This is used to run a series of
commands defined in the file [`.pre-commit-config.yaml`](https://github.com/cal-icor/cal-icor-hubs/blob/staging/.pre-commit-config.yaml)
to help ensure no mistakes are committed to the repo.

After you've installed `dev-requirements.txt`, execute the following two
commands:

```
pre-commit install
pre-commit run --all-files
```

## Setting up your fork and clones

First, go to your [github profile settings](https://github.com/settings/keys)
and make sure you have an SSH key uploaded.

Next, go to the [Cal ICOR hubs github repo](https://github.com/cal-icor/cal-icor-hubs/)
and create a fork.  To do this, click on the `fork` button and then `Create fork`.

Now clone this repo on your local device.  You can get the URL to do
this by clicking on the green `Code` button in the primary Datahub repo (*not* your fork)
and clicking on `ssh`:
```
git clone git@github.com:cal-icor/cal-icor-hubs.git
```

Now `cd` in to `cal-icor-hubs` and set up your local repo to point both at the primary
Jupyterhub repo (`upstream`) and your fork (`origin`).  After the initial clone,
`origin` will be pointing to the main repo and we'll need to change that.
```
$ cd datahub
$ git remote -v
origin	git@github.com:cal-icor/cal-icor-hubs.git (fetch)
origin	git@github.com:cal-icor/cal-icor-hubs.git (push)
$ git remote rename origin upstream
$ git remote add origin git@github.com:<your github username>/cal-icor-hubs.git
$ git remote -v
origin	git@github.com:<your github username>/cal-icor-hubs.git (fetch)
origin	git@github.com:<your github username>/cal-icor-hubs.git (push)
upstream	git@github.com:cal-icor/cal-icor-hubs.git (fetch)
upstream	git@github.com:cal-icor/cal-icor-hubs.git (push)
```

Now you can sync your local repo from `upstream`, and push those changes to your
fork (`origin`):
```
git checkout staging && \
git fetch --prune --all && \
git rebase upstream/staging && \
git push origin staging
```

## Procedure

When developing for this deployment, always work in a fork of this repo.
You should also make sure that your repo is up-to-date with this one prior
to making changes. This is because other contributors may have pushed changes
after you last synced with this repo but before you upstreamed your changes.

### Syncing your repo

The following commands will sync the local clone of your fork with `upstream`:
```
git checkout staging && \
git fetch --prune --all && \
git rebase upstream/staging && \
git push origin staging
```

### Creating a feature branch

To create a new feature branch and switch to it, run the following command:
```
git checkout -b <branch name>
```

### Checking the status and diffs of your local work

After you make your changes, you can use the following commands to see
what's been modified and check out the diffs:  `git status` and `git diff`.

### Adding, committing and pushing changes

When you're ready to push these changes, first you'll need to stage them for a
commit:
```
git add <file1> <file2> <etc>
```

Commit these changes locally:
```
git commit -m "some pithy commit description"
```

Now push to your fork:
```
git push origin <branch name>
```

### Creating a pull request

Once you've pushed to your fork, you can go to the
[Datahub repo](https://github.com/cal-icor/cal-icor-hubs) and there
should be a big green button on the top that says `Compare and pull request`.
Click on that, check out the commits and file diffs, edit the title and
description if needed and then click `Create pull request`.

If you're having issues, you can refer to the [github documentation for pull
requests](https://help.github.com/articles/about-pull-requests/).
The choice for `base` in the GitHub PR user interface should be the staging
branch of this repo while the choice for `head` is your fork.

Once this is complete and if there are no problems, you can request that
someone review the PR before merging, or you can merge yourself if you are
confident. This merge will trigger a Github Actions workflow which upgrades the
helm deployment on the staging site. When this is complete, test your
changes there. For example if you updated a library, make sure that a new
user server instance has the new version. If you spot any problems you can
revert your change. You should test the changes soon after the merge since
we do not want unverified changes to linger in staging.

If staging fails, *never* update production. Revert your change or
call in help if necessary. If your change is successful, you will need
to merge the change from staging branch to production. Create another PR,
this time with the `base` set to prod and the `head` set to staging. This
PR will trigger a similar Travis process. Test your change on production
for good measure.

## SSL: LetsEncrypt Strategy
The Berkeley-based SPA email address, cal-icor-support@berkeley.edu, is the
contact email used to create the SSL certificate for the datahub at
[LetsEncrypt](https://letsencrypt.org/). The address is only used by LetsEncrypt
when there is a problem renewing the certificate.
