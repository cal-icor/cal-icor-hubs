#!/usr/bin/env python3
import argparse
import re
import subprocess
import sys
from io import StringIO
from pathlib import Path

from cookiecutter.main import cookiecutter
from hubploy import helm
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.scalarstring import SingleQuotedScalarString

# these are the keys populate_deployment_config() reads out of the config
REQUIRED_KEYS = (
    "admin_emails",
    "allow_all",
    "allowed_organizations",
    "authenticator_class",
    "authenticator_class_instance",
    "hub_name",
    "hub_nfs_server_ip",
    "idp_allowed_domains",
    "idp_url",
    "institution",
    "institution_logo_url",
    "institution_url",
    "landing_page_branch",
    "prod",
)

# these keys are required. The rest can be empty or missing depending on the
# authenticator: idp_url and idp_allowed_domains are cilogon
# allowed_organizations is github only
# allow_all is shibboleth/incommon only
REQUIRED_NON_EMPTY = (
    "admin_emails",
    "authenticator_class",
    "authenticator_class_instance",
    "hub_name",
    "hub_nfs_server_ip",
    "institution",
    "institution_logo_url",
    "institution_url",
    "landing_page_branch",
)

# joined into comma-separated strings for the cookiecutter context
JOINED_KEYS = ("admin_emails", "allowed_organizations", "idp_allowed_domains")

VALID_HUB_TYPES = ("python-base", "rstudio-base")


def validate_config(config: dict, config_path: Path):
    """
    Check the deployment config before anything with side effects runs.

    create_deployment() cuts the feature branch and creates the hub's directories
    on the NFS server before it renders the cookiecutter template, so an unfilled
    config used to fail partway through with a bare KeyError or TypeError and
    leave both behind. Report everything wrong with the config up front instead.

    Args:
        config (dict): The parsed deployment configuration.
        config_path (Path): Path to the config file, used in the error output.

    Raises:
        SystemExit: If the config is missing keys or has unfilled values.
    """
    errors = []

    # we now call "hub_type" instead of "deployment_type"
    if "deployment_type" in config:
        errors.append("'deployment_type' has been renamed to 'hub_type'")

    hub_type = config.get("hub_type") or VALID_HUB_TYPES[0]
    if hub_type not in VALID_HUB_TYPES:
        errors.append(f"'hub_type' must be one of {', '.join(VALID_HUB_TYPES)}")

    for key in REQUIRED_KEYS:
        if key not in config:
            errors.append(f"'{key}' is missing")
        elif key in REQUIRED_NON_EMPTY and not config[key]:
            errors.append(f"'{key}' is empty")

    # A bare '-' under a list key parses to [None], which fails the join in
    # populate_deployment_config() with an unhelpful TypeError.
    for key in JOINED_KEYS:
        value = config.get(key)
        if isinstance(value, list) and not all(value):
            errors.append(f"'{key}' has a blank list entry")

    prod = config.get("prod")
    if prod is not None and not isinstance(prod, dict):
        errors.append("'prod' must hold 'client' and 'secret'")
    elif isinstance(prod, dict):
        for key in ("client", "secret"):
            if not prod.get(key):
                errors.append(f"'prod.{key}' is empty")

    if errors:
        print(f"Error: {config_path} is not ready to deploy:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)


def delete_file(filepath: Path):
    """
    Deletes a file from the filesystem.

    Args:
        filepath (Path): The path to the file to be deleted.

    Raises:
        FileNotFoundError: If the file does not exist.
        PermissionError: If the file cannot be deleted due to insufficient permissions.
        Exception: For any other errors during file deletion.
    """
    try:
        filepath.unlink()
        print(f"Deleted file: {filepath}")
    except FileNotFoundError:
        print(f"File not found: {filepath}")
    except PermissionError:
        print(f"No permission to delete: {filepath}")
    except OSError as e:
        print(f"Error deleting file: {e}")


def encrypt_file(input_file: Path, output_file: Path):
    """
    Encrypts a file using the `sops` command-line tool.

    Args:
        input_file (Path): The path to the input file to be encrypted.
        output_file (Path): The path where the encrypted file will be saved.

    Raises:
        SystemExit: If the input file does not exist or encryption fails.
    """
    if not input_file.is_file():
        print(f"Error: Input file '{input_file}' does not exist.")
        sys.exit(1)

    try:
        subprocess.run(
            ["sops", "--output", str(output_file), "--encrypt", str(input_file)],
            check=True,
        )
        print(f"Encrypted file saved as: {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"Encryption failed: {e}")
        sys.exit(1)


def handle_secrets(school_arg: str, env_arg: str):
    """
    Handles the encryption and cleanup of secret files.

    Args:
        school_arg (str): The name of the school.
        env_arg (str): The environment (e.g., 'staging', 'prod').

    This function:
    2. Encrypts the plain YAML file.
    3. Deletes the plain YAML file after encryption.
    """
    print("Secret file generation and encryption beginning.")
    encrypt_file(
        Path(f"deployments/{school_arg}/secrets/{env_arg}.plain.yaml"),
        Path(f"deployments/{school_arg}/secrets/{env_arg}.yaml"),
    )
    delete_file(Path(f"deployments/{school_arg}/secrets/{env_arg}.plain.yaml"))


def insert_hub_label(labeler_text: str, hub_name: str) -> str:
    """
    Return labeler_text with a `hub: <hub_name>` label inserted into the
    hub-specific label block in alphabetical order.

    The whole active hub block is rewritten sorted. Commented-out entries
    (e.g. gpu-demo) and any other trailing comment lines are preserved
    untouched at the bottom of the block. If the hub already has an active
    entry, the text is unchanged.

    Args:
        labeler_text (str): The full contents of .github/labeler.yml.
        hub_name (str): The name of the hub to add.

    Returns:
        str: The updated labeler.yml contents.

    Raises:
        ValueError: If the hub-label block marker cannot be found.
    """
    marker = "# add hub-specific labels for deployment changes"
    if marker not in labeler_text:
        raise ValueError(f"Could not find hub-label marker '{marker}' in labeler.yml")

    head, _, tail = labeler_text.partition(marker)

    # Split the block into active `hub: <name>` entries and trailing comment
    # lines (e.g. the commented-out gpu-demo entry), which we preserve verbatim
    # at the bottom rather than round-tripping through the parser.
    entry_lines, trailing_lines = [], []
    for line in tail.splitlines():
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            trailing_lines.append(line)
        else:
            entry_lines.append(line)

    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)

    existing = yaml.load("\n".join(entry_lines)) or {}
    names = {key.split("hub: ", 1)[1] for key in existing}
    if hub_name in names:
        return labeler_text
    names.add(hub_name)

    # Rebuild the whole active block sorted, so it self-heals to alphabetical
    # order on every run. Single-quote the key (the `: ` needs it) and the glob
    # value to match the existing style.
    block = CommentedMap()
    for name in sorted(names):
        block[SingleQuotedScalarString(f"hub: {name}")] = [
            SingleQuotedScalarString(f"deployments/{name}/**")
        ]
    buf = StringIO()
    yaml.dump(block, buf)

    parts = [head + marker, buf.getvalue().rstrip("\n")]
    if trailing_lines:
        parts.append("\n".join(trailing_lines))
    return "\n".join(parts) + "\n"


def create_label(hub_name: str, root_path: str) -> str:
    """
    Create labels for the new hub in the GitHub repository.

    Args:
        hub_name (str): The name of the hub.
        root_path (str): The path to the root directory of the repository.
    Returns:
        str: The GitHub label created for the new hub.
    """
    labeler_path = Path(root_path) / ".github" / "labeler.yml"
    original = labeler_path.read_text()
    updated = insert_hub_label(original, hub_name)
    if updated == original:
        print(f"Label for {hub_name} already present in labeler.yml, skipping.")
    else:
        labeler_path.write_text(updated)
        print(f"Added {hub_name} to the labeler.yml file in alphabetical order.")

    # create the github label for the new hub
    github_label = f"hub: {hub_name}"
    try:
        subprocess.run(
            [
                "gh",
                "label",
                "-Rcal-icor/cal-icor-hubs",
                "create",
                github_label,
                "--description",
                f"Label for {hub_name} deployment.",
                "--force",
            ],
            check=True,
        )
        print(f"Created GitHub label for {hub_name}.")
    except subprocess.CalledProcessError as e:
        print(f"Unable to get branch from {root_path}: {e}.")
        sys.exit(1)

    return github_label


def stage_and_push(
    hub_name: str, root_path: Path, branch_name: str, extra_files: list | None = None
):
    """
    Stage the new deployment files for the hub.

    Args:
        hub_name (str): The name of the hub.
        root_path (Path): The path to the root directory of the repository.
        branch_name (str): The name of the branch to push the changes to.
        extra_files (list): Additional files to stage alongside the deployment files.
    """
    files_to_add = [
        Path(f"deployments/{hub_name}/"),
        Path(".github/labeler.yml"),
    ]
    if extra_files:
        files_to_add.extend(extra_files)
    for file in files_to_add:
        print(f"Adding {file!s} to staging.")
        try:
            subprocess.check_call(["git", "add", str(file)], cwd=str(root_path))
        except subprocess.CalledProcessError as e:
            print(f"Error adding {file!s} to commit: {e}")
            sys.exit(1)

    commit_message = f"Add {hub_name} deployment."
    print(f"Committing changes for {hub_name} with message {commit_message}.")
    try:
        subprocess.check_call(
            ["git", "commit", "-m", f"{commit_message}"], cwd=str(root_path)
        )
    except subprocess.CalledProcessError as e:
        print(f"Error committing {hub_name}: {e}")
        sys.exit(1)

    remote = "origin"
    print(f"Pushing {branch_name} to {remote}")
    try:
        subprocess.check_call(["git", "push", remote, branch_name], cwd=str(root_path))
    except subprocess.CalledProcessError as e:
        print(f"Error pushing {branch_name} to {remote}: {e}")
        sys.exit(1)


def create_pr(github_user: str, hub_name: str, branch_name: str, github_label: str):
    """
    Add, commit and create a pull request for the new hub deployment.
    Args:
        github_user (str): The GitHub username of the user creating the pull request.
        hub_name (str): The name of the hub.
        branch_name (str): The name of the branch to push the changes to.
        github_label (str): The GitHub label to be added to the pull request.
    """
    body = f"Add `{hub_name}` deployment, brought to you by `create_deployment.py`."
    title = f"Add `{hub_name}` deployment."
    upstream_repo = "git@github.com:cal-icor/cal-icor-hubs.git"

    print(f"Creating a pull request for {hub_name} on branch {branch_name}")
    owner_and_repo = re.search(".+:(.+?).git$", upstream_repo).group(1)
    try:
        command = [
            "gh",
            "pr",
            "new",
            f"-t {title}",
            f"-R{owner_and_repo}",
            f"-H{github_user}:{branch_name}",
            "-Bstaging",
            f"-l{github_label}",
        ]
        if body is not None:
            command.append(f"-b {body}")
        print(command)
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Unable to create pull request for {hub_name}: {e}")
        sys.exit(1)


def create_branch(branch_name: str, root_path: Path):
    """
    Create a new branch in the Git repository.

    Args:
        branch_name (str): The name of the new branch to be created.
        root_path (Path): The path to the root directory of the repository.
    """
    try:
        branch = (
            subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=str(root_path),
                capture_output=True,
                check=True,
            )
            .stdout.decode("utf-8")
            .strip()
        )
    except subprocess.CalledProcessError as e:
        print(f"Unable to get branch from {root_path}: {e}.")
        sys.exit(1)

    if branch != "staging":
        print(
            f"Currently not on branch 'staging' in {root_path}. Not "
            + "creating a feature branch and exiting."
        )
        sys.exit(1)
    try:
        subprocess.check_call(["git", "switch", "-c", branch_name], cwd=str(root_path))
    except subprocess.CalledProcessError as e:
        print(f"Error creating branch {branch_name}: {e}")
        sys.exit(1)


def populate_deployment_config(
    config: dict, root_path: Path, manual_config: bool = False
):
    """
    Populate the deployment configuration file with the provided configuration.

    Args:
        config (dict): The configuration dictionary containing deployment details.
        root_path (Path): The path to the root directory of the repository.
        manual_config (bool): If True, the script will ask for confirmation for each step.
    """
    # Run the cookiecutter to generate the deployment files
    print(f"Generating {config['hub_name']} cookiecutter template.")

    print(f"Generating openssl key for {config['hub_name']}.")
    api_token = subprocess.run(
        ["openssl", "rand", "-hex", "32"], capture_output=True, text=True, check=True
    ).stdout.strip()

    # Check for overridden image_name and image_tag in the config, if not found, don't set them.
    cookiecutter(
        template=f"{root_path}/deployments/template",
        output_dir=f"{root_path}/deployments",
        no_input=manual_config,
        extra_context={
            "image_name": (config["image_name"] if config.get("image_name") else None),
            "image_tag": (config["image_tag"] if config.get("image_tag") else None),
            "hub_type": (
                config["hub_type"] if config.get("hub_type") else "python-base"
            ),
            "hub_name": config["hub_name"],
            "hub_nfs_mount_path": config["hub_nfs_mount_path"],
            "hub_nfs_server_ip": config["hub_nfs_server_ip"],
            "institution": config["institution"],
            "institution_url": config["institution_url"],
            "institution_logo_url": config["institution_logo_url"],
            "landing_page_branch": config["landing_page_branch"],
            "authenticator_class": config["authenticator_class"],
            "authenticator_class_instance": config["authenticator_class_instance"],
            "client_id_prod": config["prod"]["client"],
            "client_secret_prod": config["prod"]["secret"],
            "cloudbank_api_token_prod": api_token,
            "idp_url": config["idp_url"],
            "idp_allowed_domains": ", ".join(
                domain for domain in config["idp_allowed_domains"]
            ),
            "allowed_organizations": ", ".join(
                org for org in config["allowed_organizations"]
            ),
            "allow_all": config["allow_all"],
            "admin_emails": ", ".join(email for email in config["admin_emails"]),
        },
    )

    # Encrypt the prod secret. The staging secret is a shared dummy-auth
    # password shipped verbatim by the template, so it needs no processing.
    print(f"Encrypting prod secret for {config['hub_name']}.")
    handle_secrets(config["hub_name"], "prod")


def update_nfs_quota_paths(
    hub_name: str, mount_path: str, root_path: Path, dry_run: bool = False
):
    """
    Add the new hub's NFS export paths to jupyterhub-home-nfs/values.yaml in alphabetical order.

    Skips if mount_path != hub_name, which means the hub shares another hub's NFS directory
    (e.g. rstudio shares the jupyter path) and should not get its own quota entries.

    Args:
        hub_name (str): The name of the hub.
        mount_path (str): The NFS mount path for the hub (usually the same as hub_name).
        root_path (Path): The path to the root directory of the repository.
        dry_run (bool): If True, print what would be done without making changes.

    Returns:
        None

    Raises:
        FileNotFoundError: If jupyterhub-home-nfs/values.yaml does not exist.
        ValueError: If the QuotaManager paths block cannot be found in values.yaml.
    """
    if mount_path != hub_name:
        print(
            f"Hub '{hub_name}' uses shared NFS path '{mount_path}', skipping quota path update."
        )
        return

    values_path = root_path / "jupyterhub-home-nfs" / "values.yaml"
    if not values_path.is_file():
        raise FileNotFoundError(
            f"Could not find jupyterhub-home-nfs/values.yaml at {values_path}"
        )
    content = values_path.read_text()

    match = re.search(r"(paths: \[)(.*?)(\n\s+\])", content, re.DOTALL)
    if not match:
        raise ValueError(
            "Could not find QuotaManager paths block in jupyterhub-home-nfs/values.yaml"
        )

    existing_paths = re.findall(r'"(/export/[^"]+)"', match.group(2))
    pairs = list(zip(existing_paths[::2], existing_paths[1::2]))

    new_staging = f"/export/{mount_path}/staging"
    new_prod = f"/export/{mount_path}/prod"

    if new_staging in existing_paths:
        print(f"Paths for '{hub_name}' already exist in quota paths, skipping.")
        return

    pairs.append((new_staging, new_prod))
    pairs.sort(key=lambda p: p[0])

    indent = "          "
    lines = []
    for i, (staging, prod) in enumerate(pairs):
        comma = "," if i < len(pairs) - 1 else ""
        lines.append(f'{indent}"{staging}", "{prod}"{comma}')

    new_inner = "\n" + "\n".join(lines)
    new_content = (
        content[: match.start()]
        + match.group(1)
        + new_inner
        + match.group(3)
        + content[match.end() :]
    )

    if dry_run:
        print(
            f"Dry run: Would add '{new_staging}' and '{new_prod}' to quota paths in alphabetical order."
        )
        return

    values_path.write_text(new_content)
    print(f"Added NFS quota paths for '{hub_name}' in alphabetical order.")


def create_remote_dirs(config: dict):
    """
    Create the prod and staging directories on the in-cluster NFS server for the new hub.

    Execs into the nfs-server pod in the jupyterhub-home-nfs namespace to create
    /export/<hub>/staging, /export/<hub>/staging/_shared, /export/<hub>/prod,
    and /export/<hub>/prod/_shared, owned by uid/gid 1000.

    Args:
        config (dict): The configuration dictionary containing deployment details.
    """
    hub_name = config["hub_name"]
    mount_path = config["hub_nfs_mount_path"]
    dirs = [
        f"/export/{mount_path}/staging",
        f"/export/{mount_path}/staging/_shared",
        f"/export/{mount_path}/prod",
        f"/export/{mount_path}/prod/_shared",
    ]

    try:
        pod_name = (
            subprocess.run(
                [
                    "kubectl",
                    "get",
                    "pod",
                    "-n",
                    "jupyterhub-home-nfs",
                    "-l",
                    "app.kubernetes.io/component=nfs-server",
                    "-o",
                    "jsonpath={.items[0].metadata.name}",
                ],
                capture_output=True,
                check=True,
            )
            .stdout.decode("utf-8")
            .strip()
        )
    except subprocess.CalledProcessError as e:
        print(f"Error getting NFS server pod: {e}")
        sys.exit(1)

    if not pod_name:
        print("Error: No NFS server pod found in jupyterhub-home-nfs namespace.")
        sys.exit(1)

    print(f"Creating directories on NFS server pod {pod_name}.")
    mkdir_cmd = "mkdir -p " + " ".join(dirs)
    chown_cmd = f"chown -R 1000:1000 /export/{mount_path}"
    try:
        subprocess.check_call(
            [
                "kubectl",
                "exec",
                "-n",
                "jupyterhub-home-nfs",
                pod_name,
                "--",
                "sh",
                "-c",
                f"{mkdir_cmd} && {chown_cmd}",
            ]
        )
    except subprocess.CalledProcessError as e:
        print(f"Error creating directories for {hub_name}: {e}")
        sys.exit(1)


def create_deployment(
    config: dict,
    github_user: str,
    root_path: Path,
    deploy: bool = False,
    manual_config: bool = False,
    dry_run: bool = False,
    no_pr: bool = False,
):
    """
    Create a new deployment for an institution using the provided configuration.
    Args:
        config (dict): The configuration dictionary containing deployment details.
        github_user (str): The GitHub username of the user creating the pull request.
        root_path (str): The parent path where the deployment will be created.
        deploy (bool): If True, the script will deploy the hub to staging after creating the pull request.
        manual_config (bool): If True, the script will ask for confirmation for each step.
        dry_run (bool): If True, the script will go through all the steps but not actually make any changes.
        no_pr (bool): If True, the script will not open a pull request.
    """
    # Resolve hub_nfs_mount_path: defaults to hub_name when not set, allowing two or
    # more hubs to share the same NFS staging/prod directories by pointing at the same path.
    if "hub_nfs_mount_path" not in config or not config["hub_nfs_mount_path"]:
        print(f"Using hub_name '{config['hub_name']}' as hub_nfs_mount_path.")
        config["hub_nfs_mount_path"] = config["hub_name"]
    else:
        print(
            f"Using hub_nfs_mount_path '{config['hub_nfs_mount_path']}' "
            f"for {config['hub_name']}."
        )

    # The following steps will not be run if the dry_run flag is set, but we
    # will print out what would have been done.

    # Create a feature branch
    branch_name = f"add-{config['hub_name']}-deployment"
    if dry_run:
        print(f"Dry run enabled. Would create feature branch {branch_name}.")
    else:
        print(f"Creating feature branch {branch_name}.")
        create_branch(branch_name, root_path)

    # create the prod and staging directories on the NFS server for the new hub
    if dry_run:
        print(
            f"Dry run enabled. Would create directories for {config['hub_name']} on the NFS server."
        )
    else:
        print(f"Creating directories for {config['hub_name']} on the NFS server.")
        create_remote_dirs(config)

    # Populate the deployment configuration
    print(f"Populating deployment config for {config['hub_name']}.")
    populate_deployment_config(config, root_path, manual_config)

    # Update NFS quota paths in jupyterhub-home-nfs/values.yaml
    if dry_run:
        print(
            f"Dry run enabled. Would update NFS quota paths for {config['hub_name']}."
        )
        update_nfs_quota_paths(
            config["hub_name"], config["hub_nfs_mount_path"], root_path, dry_run=True
        )
    else:
        print(f"Updating NFS quota paths for {config['hub_name']}.")
        update_nfs_quota_paths(
            config["hub_name"], config["hub_nfs_mount_path"], root_path
        )

    # Create labels for the new hub
    if dry_run:
        print(f"Dry run enabled. Would create GitHub label for {config['hub_name']}.")
    else:
        print(f"Creating repo and github labels for {config['hub_name']}.")
        github_label = create_label(config["hub_name"], root_path)

    # Stage and push the new deployment files
    if dry_run:
        print(
            f"Dry run enabled. Would stage and push the new deployment files for {config['hub_name']} to branch {branch_name}."
        )
    else:
        print(f"Staging and pushing the new deployment files for {config['hub_name']}.")
        stage_and_push(
            config["hub_name"],
            root_path,
            branch_name,
            extra_files=[Path("jupyterhub-home-nfs/values.yaml")],
        )

    # Create a pull request for the new hub
    if dry_run:
        print(f"Dry run enabled. Not creating pull request for {config['hub_name']}.")
    elif no_pr:
        print(
            f"Skipping pull request creation for {config['hub_name']} as per --no-pr flag."
        )
    else:
        print(f"Creating pull request for {config['hub_name']}.")
        create_pr(github_user, config["hub_name"], branch_name, github_label)

    if deploy:
        if dry_run:
            print(
                f"Dry run enabled. Would deploy the hub to {config['hub_name']}-staging."
            )
        else:
            print(f"Deploying the hub to {config['hub_name']}-staging.")
            helm.deploy(hub=config["hub_name"], chart="hub", environment="staging")
            print(f"Deployment to {config['hub_name']}-staging complete.")


def main(args):
    """
    Main function to parse arguments and create a new deployment for an institution.
    This script should be run from the root cal-icor-hubs directory.
    """
    # Check if the script is run from the correct directory
    if Path.cwd() != Path(__file__).resolve().parents[1]:
        print("Error: This script must be run from the root cal-icor-hubs directory.")
        sys.exit(1)

    # Check if the _deploy_configs directory exists
    if not Path(__file__).resolve().parents[1].joinpath("_deploy_configs").exists():
        print("Error: The _deploy_configs directory does not exist. Please create it.")
        sys.exit(1)

    # Check if the config file exists
    if (
        not Path(__file__)
        .resolve()
        .parents[1]
        .joinpath(f"_deploy_configs/{args.institution_name}.yaml")
        .exists()
    ):
        print(f"Error: The config file {args.institution_name}.yaml does not exist.")
        sys.exit(1)

    root_path = Path(__file__).resolve().parents[1]
    deployment_config = (
        Path(root_path) / "_deploy_configs" / f"{args.institution_name}.yaml"
    )
    config = YAML(typ="safe").load(deployment_config)
    if not config:
        print(f"Error loading config for {args.institution_name}.")
        sys.exit(1)

    validate_config(config, deployment_config)

    if args.dry_run:
        print(
            "Performing a dry-run, only the config changes in your repo will be performed, but no remote actions taken.\n"
        )

    create_deployment(
        config,
        args.github_user,
        root_path,
        args.deploy,
        args.manual_config,
        args.dry_run,
        args.no_pr,
    )

    print(
        f"\nDeployment for {config['hub_name']} created."
        + "\nDo not forget to create the alerts for the new hub after merging "
        + "the PR to prod. The instructions for that are found here: \n"
        + "https://docs.cal-icor.org/new-hub/#create-the-alerts-for-the-new-hub"
        + "\n\n"
        + "You also need to update the openssl token in the "
        + "cloudbank-pilot-hub-users service in the enc-pilots.json file for "
        + "the new hub. The instructions for that are found here: \n"
        + "https://github.com/cal-icor/cal-icor-hubs#keeping-it-in-sync-with-cloudbank-pilot-hub-users"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create a new deployment for an institution.  This should "
        + "be run from the root cal-icor-hubs directory."
        + "\n\n"
        + "You will also need to fill out the cookiecutter template config "
        + "in the _deploy_configs/<institution_name>.yaml dir in the root of the repo.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--deploy",
        "-d",
        action="store_true",
        help="If set, the script will deploy the hub after creating the PR.",
    )
    parser.add_argument(
        "--github_user",
        "-g",
        type=str,
        help="The GitHub username of the user creating the pull request (required).",
        required=True,
    )
    parser.add_argument(
        "institution_name",
        type=str,
        help="The name of the institution. This should be the same as the "
        + "config file name in cal-icor-hubs/_deploy_configs/"
        + "<institution_name>.yaml",
    )
    parser.add_argument(
        "--manual-config",
        "-m",
        action="store_false",
        help="If set, the script will ask for confirmation for each step, "
        + "allowing you to manually configure the deployment (eg: custom "
        + "node pool deployment, etc).",
    )
    parser.add_argument(
        "--no-pr",
        "-n",
        action="store_true",
        help="If set, the script will not create a pull request after creating the deployment.",
    )
    parser.add_argument(
        "--dry-run",
        "-D",
        action="store_true",
        help="If set, the script will go through all the steps but not actually "
        + "make any changes (eg: not actually creating branches, pushing to "
        + "GitHub, creating remoter directories or deploying to staging).",
    )
    args = parser.parse_args()

    main(args)
