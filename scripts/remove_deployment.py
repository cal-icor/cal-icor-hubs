#!/usr/bin/env python3
import argparse
import difflib
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

from ruamel.yaml import YAML

# the only cluster this script is allowed to touch
EXPECTED_CONTEXT = "gke_cal-icor-hubs_us-central1_spring-2025"
EXPECTED_PROJECT = "cal-icor-hubs"

NFS_NAMESPACE = "jupyterhub-home-nfs"
UPSTREAM_REPO = "cal-icor/cal-icor-hubs"
# the quota enforcer's live config, inside the enforce-xfs-quota container
NFS_QUOTA_CONFIG = "/etc/jupyterhub-home-nfs/mounted-secret/chart-config.yaml"

POLL_INTERVAL = 15
CHECKS_START_TIMEOUT = 120
NFS_ROLLOUT_TIMEOUT = 1800

# feature branches created in phase 1 (gha) and phase 2 (deployment)
GHA_BRANCH = "remove-{}-gha"
DEPLOYMENT_BRANCH = "remove-{}-deployment"

ISSUE_TEMPLATES = (
    "additional_storage_request.yaml",
    "admin_request.yaml",
    "cpu_template.yml",
    "memory_request.yml",
    "package_request.yml",
)


def run(command: list, dry_run: bool = False, **kwargs):
    """
    Run a command that changes something, or print it during a dry run.

    Args:
        command (list): The command and its arguments.
        dry_run (bool): If True, print the command instead of running it.
        **kwargs: Passed through to subprocess.run().

    Returns:
        subprocess.CompletedProcess | None: None during a dry run.
    """
    if dry_run:
        print(f"Dry run enabled. Would run: {shlex.join(command)}")
        return None
    return subprocess.run(command, check=True, **kwargs)


def read_output(command: list, **kwargs) -> str:
    """
    Run a read-only command and return its stripped stdout. Runs during dry
    runs too.
    """
    return subprocess.run(
        command, capture_output=True, text=True, check=True, **kwargs
    ).stdout.strip()


def confirm(prompt: str, expected: str = "y") -> bool:
    """
    Ask the user to type `expected` to continue.
    """
    return input(f"{prompt} ").strip() == expected


def hostname(hub_name: str) -> str:
    """
    The prod hostname for a hub. The jupyter hub lives at the bare domain.
    """
    if hub_name == "jupyter":
        return "jupyter.cal-icor.org"
    return f"{hub_name}.jupyter.cal-icor.org"


def check_branches(root_path: Path, hub_name: str, finish: bool):
    """
    Make sure the feature branches this run will create don't already exist,
    locally or on origin. A stale branch would abort the run partway through,
    after the alerts, CILogon client and helm releases are already gone.

    Args:
        root_path (Path): The path to the root directory of the repository.
        hub_name (str): The name of the hub to remove.
        finish (bool): If True, only check the deployment branch (the gha
            branch is expected to exist from phase 1).

    Raises:
        SystemExit: If any branch exists or git can't be read.
    """
    templates = (DEPLOYMENT_BRANCH,) if finish else (GHA_BRANCH, DEPLOYMENT_BRANCH)
    branches = [template.format(hub_name) for template in templates]

    local, remote = [], []
    for branch in branches:
        try:
            if read_output(["git", "branch", "--list", branch], cwd=str(root_path)):
                local.append(branch)
            if read_output(
                ["git", "ls-remote", "--heads", "origin", branch],
                cwd=str(root_path),
            ):
                remote.append(branch)
        except subprocess.CalledProcessError as e:
            print(f"Unable to check for existing branch {branch}: {e}.")
            sys.exit(1)

    if not (local or remote):
        return

    print(f"Error: branches from a previous removal of {hub_name} already exist:")
    for branch in local:
        print(f"  - local: {branch}")
    for branch in remote:
        print(f"  - origin: {branch}")
    print("Delete them before rerunning:")
    for branch in local:
        print(f"  git branch -D {branch}")
    for branch in remote:
        print(f"  git push origin --delete {branch}")
    sys.exit(1)


def check_environment(root_path: Path, hub_name: str, finish: bool):
    """
    Make sure we're pointed at the right repo state, cluster and project
    before anything with side effects runs.

    Args:
        root_path (Path): The path to the root directory of the repository.
        hub_name (str): The name of the hub to remove.
        finish (bool): If True, skip the gcloud project check.

    Raises:
        SystemExit: If any check fails.
    """
    errors = []

    try:
        branch = read_output(["git", "branch", "--show-current"], cwd=str(root_path))
        dirty = read_output(["git", "status", "--porcelain"], cwd=str(root_path))
    except subprocess.CalledProcessError as e:
        print(f"Unable to read git state from {root_path}: {e}.")
        sys.exit(1)

    if branch != "staging":
        errors.append(f"currently on branch '{branch}', not 'staging'")
    if dirty:
        errors.append("the working tree has uncommitted changes")
    if not (root_path / "deployments" / hub_name).is_dir():
        errors.append(f"deployments/{hub_name} does not exist")
    if hub_name == "template":
        errors.append("refusing to remove the cookiecutter template")

    try:
        context = read_output(["kubectl", "config", "current-context"])
    except subprocess.CalledProcessError:
        context = ""
    if context != EXPECTED_CONTEXT:
        errors.append(f"kubectl context is '{context}', expected '{EXPECTED_CONTEXT}'")

    if not finish:
        try:
            project = read_output(["gcloud", "config", "get-value", "project"])
        except subprocess.CalledProcessError:
            project = ""
        if project != EXPECTED_PROJECT:
            errors.append(
                f"gcloud project is '{project}', expected '{EXPECTED_PROJECT}'"
            )

    if errors:
        print(f"Error: not ready to remove {hub_name}:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)


def get_nfs_mount_path(root_path: Path, hub_name: str) -> str | None:
    """
    Return the hub's top-level NFS directory under /export, read from the
    nfsPVC.nfs.shareName in config/prod.yaml and config/staging.yaml.

    Returns None if either environment points at a directory the hub doesn't
    own (e.g. rstudio shares jupyter/prod), since archiving or deleting it
    would take another hub's homedirs with it.

    Args:
        root_path (Path): The path to the root directory of the repository.
        hub_name (str): The name of the hub.

    Returns:
        str | None: The mount path, or None if the hub shares its NFS dirs.
    """
    yaml = YAML(typ="safe")
    for env in ("prod", "staging"):
        config_path = root_path / "deployments" / hub_name / "config" / f"{env}.yaml"
        config = yaml.load(config_path) if config_path.is_file() else None
        share_name = (
            ((config or {}).get("nfsPVC") or {}).get("nfs", {}).get("shareName")
        )
        if share_name != f"{hub_name}/{env}":
            print(
                f"{config_path.relative_to(root_path)} has shareName "
                f"'{share_name}', not '{hub_name}/{env}'."
            )
            return None
    return hub_name


def show_diff(path: Path, original: str, updated: str, root_path: Path):
    """
    Print a unified diff of a pending file change.
    """
    rel = str(path.relative_to(root_path))
    sys.stdout.writelines(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )
    )


def remove_hub_label(labeler_text: str, hub_name: str) -> str:
    """
    Return labeler_text without the hub's `hub: <hub_name>` entry. Commented
    out entries (e.g. gpu-demo) are left alone.

    Args:
        labeler_text (str): The full contents of .github/labeler.yml.
        hub_name (str): The name of the hub to remove.

    Returns:
        str: The updated labeler.yml contents.
    """
    pattern = re.compile(
        rf"^'hub: {re.escape(hub_name)}':\n(?:[ \t]+- .*\n)+", re.MULTILINE
    )
    return pattern.sub("", labeler_text)


def remove_template_option(template_text: str, hub_name: str) -> str:
    """
    Return an issue template's text without the hub's URL option.
    """
    pattern = re.compile(
        rf"^[ \t]+- {re.escape(hostname(hub_name))}[ \t]*\n", re.MULTILINE
    )
    return pattern.sub("", template_text)


def remove_quota_paths(values_text: str, mount_path: str) -> str:
    """
    Return jupyterhub-home-nfs/values.yaml without the hub's quota paths.

    Mirrors update_nfs_quota_paths() in create_deployment.py: the block is
    rebuilt from its staging/prod pairs so the trailing comma stays right.

    Args:
        values_text (str): The full contents of jupyterhub-home-nfs/values.yaml.
        mount_path (str): The hub's NFS mount path.

    Returns:
        str: The updated values.yaml contents.

    Raises:
        ValueError: If the QuotaManager paths block cannot be found.
    """
    match = re.search(r"(paths: \[)(.*?)(\n\s+\])", values_text, re.DOTALL)
    if not match:
        raise ValueError(
            "Could not find QuotaManager paths block in jupyterhub-home-nfs/values.yaml"
        )

    existing_paths = re.findall(r'"(/export/[^"]+)"', match.group(2))
    pairs = list(zip(existing_paths[::2], existing_paths[1::2]))
    remaining = [pair for pair in pairs if pair[0] != f"/export/{mount_path}/staging"]
    if len(remaining) == len(pairs):
        return values_text

    indent = "          "
    lines = []
    for i, (staging, prod) in enumerate(remaining):
        comma = "," if i < len(remaining) - 1 else ""
        lines.append(f'{indent}"{staging}", "{prod}"{comma}')

    return (
        values_text[: match.start()]
        + match.group(1)
        + "\n"
        + "\n".join(lines)
        + match.group(3)
        + values_text[match.end() :]
    )


def delete_alerts(root_path: Path, hub_name: str, dry_run: bool = False):
    """
    Delete the prod alert policy and uptime check via hub_alerts/create_alerts.py.
    A failure is reported but doesn't stop the removal.
    """
    command = [
        sys.executable,
        str(root_path / "scripts" / "hub_alerts" / "create_alerts.py"),
        "--delete_alerts",
        "--namespaces",
        f"{hub_name}-prod",
    ]
    try:
        run(command, dry_run)
    except subprocess.CalledProcessError as e:
        print(
            f"Error deleting alerts for {hub_name}-prod: {e}\n"
            + "Delete them by hand in the GCP console under Monitoring -> Alerting "
            + "and Monitoring -> Uptime checks."
        )


def delete_cilogon_client(root_path: Path, hub_name: str, dry_run: bool = False):
    """
    Delete the hub's CILogon client via cilogon_clients.py. The user already
    confirmed the removal, so pass -y. Older clients were made by the CILogon
    team and can't be found or deleted with our admin client.
    """
    command = [
        sys.executable,
        str(root_path / "scripts" / "cilogon_clients.py"),
        "remove",
        hub_name,
        "-y",
    ]
    try:
        run(command, dry_run, cwd=str(root_path))
    except subprocess.CalledProcessError as e:
        print(
            f"Unable to delete the CILogon client for {hub_name}: {e}\n"
            + "If the CILogon team created it, email help@cilogon.org with "
            + f"https://{hostname(hub_name)} and ask them to delete it."
        )


def uninstall_helm_releases(hub_name: str, dry_run: bool = False):
    """
    Uninstall the hub's prod and staging helm releases, skipping any that are
    already gone.
    """
    for env in ("prod", "staging"):
        release = f"{hub_name}-{env}"
        result = subprocess.run(
            ["helm", "status", "-n", release, release],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(f"Helm release {release} not found, skipping.")
            continue
        try:
            run(["helm", "uninstall", "-n", release, release], dry_run)
            if not dry_run:
                print(f"Uninstalled helm release {release}.")
        except subprocess.CalledProcessError as e:
            print(f"Error uninstalling {release}: {e}")
            sys.exit(1)


def check_leftover_pods(hub_name: str, dry_run: bool = False):
    """
    Helm doesn't own the user servers that KubeSpawner started, so they can
    outlive the hub and keep the NFS dirs open. Stop if any are still running.
    """
    leftovers = []
    for env in ("prod", "staging"):
        namespace = f"{hub_name}-{env}"
        try:
            pods = read_output(
                [
                    "kubectl",
                    "get",
                    "pods",
                    "-n",
                    namespace,
                    "-l",
                    "component=singleuser-server",
                    "-o",
                    "jsonpath={.items[*].metadata.name}",
                ]
            )
        except subprocess.CalledProcessError:
            continue
        leftovers.extend(f"{namespace}/{pod}" for pod in pods.split())

    if not leftovers:
        return

    print("These user servers are still running and may hold the NFS dirs open:")
    for pod in leftovers:
        print(f"  - {pod}")
    if dry_run:
        print("Dry run enabled. A real run would ask before touching NFS.")
        return
    if not confirm("Continue with the NFS step anyway? [y/N]"):
        print(
            "Exiting. Stop the pods, then archive and delete the NFS dirs "
            + "by hand (https://docs.cal-icor.org/remove-hub/) and rerun with --finish."
        )
        sys.exit(1)


def get_nfs_pod() -> str:
    """
    Return the name of the nfs-server pod.
    """
    try:
        pod_name = read_output(
            [
                "kubectl",
                "get",
                "pod",
                "-n",
                NFS_NAMESPACE,
                "-l",
                "app.kubernetes.io/component=nfs-server",
                "-o",
                "jsonpath={.items[0].metadata.name}",
            ]
        )
    except subprocess.CalledProcessError as e:
        print(f"Error getting NFS server pod: {e}")
        sys.exit(1)
    if not pod_name:
        print(f"Error: No NFS server pod found in {NFS_NAMESPACE} namespace.")
        sys.exit(1)
    return pod_name


def nfs_exec(pod_name: str, shell_command: str, dry_run: bool = False):
    """
    Run a shell command in the nfs-server pod.
    """
    return run(
        [
            "kubectl",
            "exec",
            "-n",
            NFS_NAMESPACE,
            pod_name,
            "-c",
            "nfs-server",
            "--",
            "sh",
            "-c",
            shell_command,
        ],
        dry_run,
    )


def wait_for_nfs_config(mount_path: str, dry_run: bool = False):
    """
    Wait until the running quota enforcer no longer lists /export/<mount_path>.
    The enforcer re-creates every configured path on each loop, so deleting
    the dirs before the quota path PR deploys just brings them back empty.
    """
    if dry_run:
        print(
            f"Dry run enabled. Would wait for the NFS pod to drop /export/{mount_path}"
            + " from its quota paths."
        )
        return

    print(f"Waiting for the NFS pod to drop /export/{mount_path} from its quota paths.")
    deadline = time.monotonic() + NFS_ROLLOUT_TIMEOUT
    while True:
        try:
            pods = read_output(
                [
                    "kubectl",
                    "get",
                    "pod",
                    "-n",
                    NFS_NAMESPACE,
                    "-l",
                    "app.kubernetes.io/component=nfs-server",
                    "-o",
                    "jsonpath={.items[*].metadata.name}",
                ]
            ).split()
        except subprocess.CalledProcessError:
            pods = []

        # more than one pod means a rollout is still in progress
        if len(pods) == 1:
            result = subprocess.run(
                [
                    "kubectl",
                    "exec",
                    "-n",
                    NFS_NAMESPACE,
                    pods[0],
                    "-c",
                    "enforce-xfs-quota",
                    "--",
                    "sh",
                    "-c",
                    f"grep -qF /export/{mount_path}/ {NFS_QUOTA_CONFIG}; echo $?",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            # grep exits 1 on no match
            if result.stdout.strip() == "1":
                print(f"{pods[0]} no longer lists /export/{mount_path}.")
                return

        if time.monotonic() > deadline:
            print(
                f"Error: the NFS pod still lists /export/{mount_path} after "
                + f"{NFS_ROLLOUT_TIMEOUT // 60} minutes. Check that the quota path "
                + "PR got the jupyterhub-home-nfs-deployment label and that its "
                + "deploy succeeded, then rerun with --finish."
            )
            sys.exit(1)
        time.sleep(POLL_INTERVAL)


def remove_nfs_dirs(mount_path: str, skip_archive: bool, dry_run: bool = False):
    """
    Archive /export/<mount_path> to /export/<mount_path>.tar.gz, check that
    the archive reads back, then delete the directory. With skip_archive, ask
    a second time and delete without archiving.

    Args:
        mount_path (str): The hub's NFS mount path.
        skip_archive (bool): If True, delete without archiving.
        dry_run (bool): If True, print what would be done.
    """
    pod_name = get_nfs_pod()
    hub_dir = f"/export/{mount_path}"
    archive = f"/export/{mount_path}.tar.gz"

    try:
        nfs_exec(pod_name, f"test -d {hub_dir}", dry_run=False)
    except subprocess.CalledProcessError:
        print(f"{hub_dir} does not exist on {pod_name}, skipping the NFS step.")
        return

    if skip_archive:
        if dry_run:
            print(f"Dry run enabled. Would ask, then delete {hub_dir} unarchived.")
        elif not confirm(
            f"--skip-archive is set. Type '{mount_path}' to delete {hub_dir} "
            + "without archiving it:",
            expected=mount_path,
        ):
            print("Exiting without deleting the NFS dirs.")
            sys.exit(1)
    else:
        try:
            nfs_exec(pod_name, f"test ! -e {archive}", dry_run=False)
        except subprocess.CalledProcessError:
            print(f"Error: {archive} already exists. Move it aside and rerun.")
            sys.exit(1)

        print(f"Archiving {hub_dir} to {archive} on {pod_name}.")
        try:
            nfs_exec(
                pod_name,
                f"tar -zcf {archive} -C /export {mount_path} "
                + f"&& tar -tzf {archive} > /dev/null && ls -l {archive}",
                dry_run,
            )
        except subprocess.CalledProcessError as e:
            print(f"Error archiving {hub_dir}, not deleting it: {e}")
            sys.exit(1)

    print(f"Deleting {hub_dir} on {pod_name}.")
    try:
        nfs_exec(pod_name, f"rm -rf {hub_dir}", dry_run)
    except subprocess.CalledProcessError as e:
        print(f"Error deleting {hub_dir}: {e}")
        sys.exit(1)


def create_branch(branch_name: str, root_path: Path, dry_run: bool = False):
    """
    Create a feature branch off the current (staging) branch.
    """
    try:
        run(["git", "switch", "-c", branch_name], dry_run, cwd=str(root_path))
    except subprocess.CalledProcessError as e:
        print(f"Error creating branch {branch_name}: {e}")
        sys.exit(1)


def update_repo_files(
    root_path: Path, hub_name: str, mount_path: str | None, dry_run: bool = False
) -> list:
    """
    Remove the hub from labeler.yml, the issue templates and the NFS quota
    paths. Prints a diff of each change.

    Returns:
        list: The paths (relative to root_path) that changed.
    """
    edits = [
        (root_path / ".github" / "labeler.yml", remove_hub_label, hub_name),
    ]
    edits.extend(
        (
            root_path / ".github" / "ISSUE_TEMPLATE" / name,
            remove_template_option,
            hub_name,
        )
        for name in ISSUE_TEMPLATES
    )
    if mount_path:
        edits.append(
            (
                root_path / "jupyterhub-home-nfs" / "values.yaml",
                remove_quota_paths,
                mount_path,
            )
        )

    changed = []
    for path, edit, name in edits:
        original = path.read_text()
        updated = edit(original, name)
        if updated == original:
            print(f"No {hub_name} entry in {path.relative_to(root_path)}, skipping.")
            continue
        show_diff(path, original, updated, root_path)
        if not dry_run:
            path.write_text(updated)
        changed.append(path.relative_to(root_path))
    return changed


def delete_github_label(hub_name: str, dry_run: bool = False):
    """
    Delete the hub's GitHub label. A missing label isn't an error.
    """
    try:
        run(
            [
                "gh",
                "label",
                f"-R{UPSTREAM_REPO}",
                "delete",
                f"hub: {hub_name}",
                "--yes",
            ],
            dry_run,
        )
    except subprocess.CalledProcessError as e:
        print(f"Unable to delete GitHub label 'hub: {hub_name}': {e}")


def commit_and_push(
    root_path: Path,
    branch_name: str,
    commit_message: str,
    files: list,
    remove: bool = False,
    dry_run: bool = False,
):
    """
    Stage the given files (git rm -r them if remove is set), commit, and push
    the branch to origin.
    """
    stage = ["git", "rm", "-r", "-q"] if remove else ["git", "add"]
    try:
        run(stage + [str(f) for f in files], dry_run, cwd=str(root_path))
        run(["git", "commit", "-m", commit_message], dry_run, cwd=str(root_path))
        run(["git", "push", "origin", branch_name], dry_run, cwd=str(root_path))
    except subprocess.CalledProcessError as e:
        print(f"Error committing and pushing {branch_name}: {e}")
        sys.exit(1)


def create_pr(
    github_user: str, branch_name: str, title: str, body: str, dry_run: bool = False
) -> str | None:
    """
    Open a PR against staging and return its URL.
    """
    command = [
        "gh",
        "pr",
        "new",
        "-R",
        UPSTREAM_REPO,
        "-H",
        f"{github_user}:{branch_name}",
        "-B",
        "staging",
        "-t",
        title,
        "-b",
        body,
    ]
    try:
        result = run(command, dry_run, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"Unable to create pull request for {branch_name}: {e.stderr}")
        sys.exit(1)
    if dry_run:
        return None
    return result.stdout.strip().splitlines()[-1]


def wait_for_checks(pr_url: str) -> bool:
    """
    Wait for the PR's checks to finish. The labeler is one of them, and the
    deploy reads the labels it adds, so merging early can skip a deploy.
    Returns True if every check passed.
    """
    print(f"\nWaiting for checks on {pr_url}.")
    deadline = time.monotonic() + CHECKS_START_TIMEOUT
    while True:
        result = subprocess.run(
            ["gh", "pr", "checks", pr_url],
            capture_output=True,
            text=True,
            check=False,
        )
        output = result.stdout + result.stderr
        # gh exits 0 when all checks pass, 8 while any are pending
        if result.returncode == 0:
            return True
        if result.returncode == 8:
            subprocess.run(
                ["gh", "pr", "checks", pr_url, "--watch", "--interval", "10"],
                check=False,
            )
            # some checks (eg: pre-commit.ci) register late, so look again
            deadline = time.monotonic() + CHECKS_START_TIMEOUT
        elif "no checks reported" not in output:
            print(output)
            return False
        if time.monotonic() > deadline:
            print(f"No checks started on {pr_url} after {CHECKS_START_TIMEOUT}s.")
            return False
        time.sleep(POLL_INTERVAL)


def merge_pr(pr_url: str, resume_hint: str) -> bool:
    """
    Wait for the PR's checks, show its labels, then ask whether to merge it.
    'y' merges, anything else exits with resume_hint.
    """
    checks_passed = wait_for_checks(pr_url)
    try:
        labels = read_output(
            [
                "gh",
                "pr",
                "view",
                pr_url,
                "--json",
                "labels",
                "--jq",
                '[.labels[].name] | join(", ")',
            ]
        )
    except subprocess.CalledProcessError:
        labels = "(unable to read labels)"

    print(f"\nPull request: {pr_url}")
    print(f"Labels: {labels or '(none)'}")
    if not checks_passed:
        print("Warning: not every check passed. Look at the PR before merging.")
    if not confirm("Does it look good and is it ready to merge? [y/n]"):
        print(f"Not merging. {resume_hint}")
        sys.exit(0)
    try:
        subprocess.run(["gh", "pr", "merge", pr_url, "--merge"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error merging {pr_url}: {e}\n{resume_hint}")
        sys.exit(1)
    return True


def sync_staging(root_path: Path):
    """
    Bring the local staging branch (and the origin fork) up to date with
    upstream after a merge.
    """
    for command in (
        ["git", "checkout", "staging"],
        ["git", "fetch", "--all", "--prune"],
        ["git", "rebase", "--stat", "upstream/staging"],
        ["git", "push", "origin", "staging"],
    ):
        try:
            subprocess.run(command, check=True, cwd=str(root_path))
        except subprocess.CalledProcessError as e:
            print(f"Error syncing staging ({' '.join(command)}): {e}")
            sys.exit(1)


def delete_branch(branch_name: str, root_path: Path):
    """
    Delete a merged feature branch locally and on origin, so a later removal
    of the same hub doesn't trip check_branches. Failures only warn: the PR
    is already merged.
    """
    try:
        run(["git", "branch", "-d", branch_name], cwd=str(root_path))
    except subprocess.CalledProcessError as e:
        print(f"Warning: unable to delete local branch {branch_name}: {e}")

    try:
        on_origin = read_output(
            ["git", "ls-remote", "--heads", "origin", branch_name],
            cwd=str(root_path),
        )
        if on_origin:
            run(["git", "push", "origin", "--delete", branch_name], cwd=str(root_path))
    except subprocess.CalledProcessError as e:
        print(f"Warning: unable to delete origin branch {branch_name}: {e}")


def remove_infrastructure(
    root_path: Path,
    github_user: str,
    hub_name: str,
    skip_archive: bool = False,
    dry_run: bool = False,
    no_pr: bool = False,
):
    """
    Steps 1-3 of https://docs.cal-icor.org/remove-hub/: alerts, CILogon
    client and helm releases, then the labeler/issue template/quota path PR.
    This PR has to merge before the deployment folder goes, or the labeler
    re-creates the hub's label on the next PR. It also has to deploy before
    the NFS dirs go (see wait_for_nfs_config).
    """
    mount_path = get_nfs_mount_path(root_path, hub_name)
    if mount_path is None:
        print(
            f"{hub_name} shares its NFS dirs with another hub. Skipping the NFS "
            + "archive/delete and the quota path change."
        )

    print(f"Deleting alerts for {hub_name}-prod.")
    delete_alerts(root_path, hub_name, dry_run)

    print(f"Deleting the CILogon client for {hub_name}.")
    delete_cilogon_client(root_path, hub_name, dry_run)

    print(f"Uninstalling helm releases for {hub_name}.")
    uninstall_helm_releases(hub_name, dry_run)

    branch_name = GHA_BRANCH.format(hub_name)
    print(f"Creating feature branch {branch_name}.")
    create_branch(branch_name, root_path, dry_run)

    changed = update_repo_files(root_path, hub_name, mount_path, dry_run)

    print(f"Deleting GitHub label 'hub: {hub_name}'.")
    delete_github_label(hub_name, dry_run)

    if not changed:
        print("No repo files reference the hub, so there's no first PR.")
        if not dry_run:
            run(["git", "switch", "staging"], cwd=str(root_path))
            run(["git", "branch", "-d", branch_name], cwd=str(root_path))
        return

    commit_and_push(
        root_path,
        branch_name,
        f"Remove {hub_name} labels, issue template URLs and NFS quota paths.",
        changed,
        dry_run=dry_run,
    )

    resume_hint = (
        "Merge it to staging, sync your staging branch, then run:\n"
        + f"  ./remove_deployment.sh -g {github_user} --finish {hub_name}"
    )
    if no_pr:
        print(f"Skipping pull request creation as per --no-pr flag. {resume_hint}")
        sys.exit(0)

    pr_url = create_pr(
        github_user,
        branch_name,
        f"Remove `{hub_name}` labels, issue template URLs and NFS quota paths.",
        f"First of two PRs removing `{hub_name}`, brought to you by "
        + "`remove_deployment.py`. This one has to merge before the "
        + "deployment folder is removed.",
        dry_run,
    )
    if dry_run:
        print(
            "Dry run enabled. Would ask to merge the PR, sync staging, "
            + f"then delete {branch_name}."
        )
        return

    merge_pr(pr_url, resume_hint)
    sync_staging(root_path)
    print(f"Deleting merged branch {branch_name}.")
    delete_branch(branch_name, root_path)


def remove_deployment_dir(
    root_path: Path,
    github_user: str,
    hub_name: str,
    skip_archive: bool = False,
    dry_run: bool = False,
    no_pr: bool = False,
):
    """
    Steps 4-5 of https://docs.cal-icor.org/remove-hub/: archive and delete
    the NFS dirs once the quota path change has deployed, then remove
    deployments/<hub> in a second PR, once the labeler entry is gone from
    staging.
    """
    labeler = (root_path / ".github" / "labeler.yml").read_text()
    if not dry_run and remove_hub_label(labeler, hub_name) != labeler:
        print(
            f"Error: .github/labeler.yml on staging still has 'hub: {hub_name}'. "
            + "Merge the first PR and sync staging before running --finish."
        )
        sys.exit(1)

    mount_path = get_nfs_mount_path(root_path, hub_name)
    if mount_path:
        check_leftover_pods(hub_name, dry_run)
        wait_for_nfs_config(mount_path, dry_run)
        remove_nfs_dirs(mount_path, skip_archive, dry_run)

    branch_name = DEPLOYMENT_BRANCH.format(hub_name)
    print(f"Creating feature branch {branch_name}.")
    create_branch(branch_name, root_path, dry_run)

    commit_and_push(
        root_path,
        branch_name,
        f"Remove {hub_name} deployment.",
        [Path("deployments") / hub_name],
        remove=True,
        dry_run=dry_run,
    )

    resume_hint = "Merge it to staging when you're ready."
    if no_pr:
        print(f"Skipping pull request creation as per --no-pr flag. {resume_hint}")
        return

    pr_url = create_pr(
        github_user,
        branch_name,
        f"Remove `{hub_name}` deployment.",
        f"Remove `{hub_name}` deployment, brought to you by `remove_deployment.py`.",
        dry_run,
    )
    if dry_run:
        print(
            "Dry run enabled. Would ask to merge the PR, sync staging, "
            + f"then delete {branch_name}."
        )
        return

    merge_pr(pr_url, resume_hint)
    sync_staging(root_path)
    print(f"Deleting merged branch {branch_name}.")
    delete_branch(branch_name, root_path)


def main(args):
    """
    Remove a hub deployment. This script should be run from the root
    cal-icor-hubs directory.
    """
    root_path = Path(__file__).resolve().parents[1]
    if Path.cwd() != root_path:
        print("Error: This script must be run from the root cal-icor-hubs directory.")
        sys.exit(1)

    hub_name = args.hub_name
    check_branches(root_path, hub_name, args.finish)
    check_environment(root_path, hub_name, args.finish)

    if args.dry_run:
        print(
            "Performing a dry-run: no remote, NFS, helm or git changes will be made.\n"
        )

    nfs_action = "deletes" if args.skip_archive else "archives then deletes"
    if args.finish:
        warning = (
            f"This {nfs_action} the NFS homedirs and removes deployments/{hub_name}."
        )
    else:
        warning = (
            f"This uninstalls {hub_name}-prod and {hub_name}-staging, deletes "
            + f"their alerts and CILogon client, and {nfs_action} the NFS homedirs."
        )
    if args.dry_run:
        print(f"Dry run enabled. Would ask you to type '{hub_name}' to continue.")
    elif not confirm(f"{warning} Type '{hub_name}' to continue:", expected=hub_name):
        print("Exiting.")
        sys.exit(1)

    if not args.finish:
        remove_infrastructure(
            root_path,
            args.github_user,
            hub_name,
            args.skip_archive,
            args.dry_run,
            args.no_pr,
        )

    remove_deployment_dir(
        root_path,
        args.github_user,
        hub_name,
        args.skip_archive,
        args.dry_run,
        args.no_pr,
    )

    done = "branches pushed" if args.no_pr else "removed from staging"
    print(
        f"\n{hub_name} {done}."
        + "\nMerge staging to prod soon: until then, a prod deploy that redeploys "
        + f"all hubs will reinstall {hub_name}-prod."
        + "\n\nYou also need to remove the hub's openssl token from the "
        + "cloudbank-pilot-hub-users service in the enc-pilots.json file. "
        + "The instructions for that are found here: \n"
        + "https://github.com/cal-icor/cal-icor-hubs#keeping-it-in-sync-with-cloudbank-pilot-hub-users"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Remove a hub deployment.  This should be run from the root "
        + "cal-icor-hubs directory, on the staging branch."
        + "\n\n"
        + "Follows https://docs.cal-icor.org/remove-hub/: deletes the alerts and "
        + "CILogon client, uninstalls the helm releases, opens a PR for the "
        + "labels/issue templates/quota paths, archives and deletes the NFS "
        + "homedirs once that PR deploys, then opens a PR for the deployment "
        + "folder. It waits for each PR's checks, then asks before merging.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "hub_name",
        type=str,
        help="The name of the hub. This should match the folder name in "
        + "cal-icor-hubs/deployments/<hub_name>",
    )
    parser.add_argument(
        "--github_user",
        "-g",
        type=str,
        help="The GitHub username of the user creating the pull requests (required).",
        required=True,
    )
    parser.add_argument(
        "--skip-archive",
        "-s",
        action="store_true",
        help="If set, delete the hub's NFS directories without archiving them first.",
    )
    parser.add_argument(
        "--finish",
        "-f",
        action="store_true",
        help="If set, only archive and delete the NFS dirs and remove the "
        + "deployment folder (second PR). Use this after merging the first PR "
        + "by hand.",
    )
    parser.add_argument(
        "--no-pr",
        "-n",
        action="store_true",
        help="If set, push the branch but don't create or merge a pull request.",
    )
    parser.add_argument(
        "--dry-run",
        "-D",
        action="store_true",
        help="If set, the script will go through all the steps but not actually "
        + "make any changes (eg: not deleting alerts, helm releases or NFS "
        + "dirs, not editing files, creating branches or pushing to GitHub).",
    )
    args = parser.parse_args()

    main(args)
