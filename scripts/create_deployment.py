#!/usr/bin/env python3
import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml
from cookiecutter.main import cookiecutter
from hubploy import helm


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
    except Exception as e:
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
    hub_label = f"""
'hub: {hub_name}':
  - 'deployments/{hub_name}/**'
""".strip()
    with labeler_path.open("a") as labeler_file:
        labeler_file.write(f"\n{hub_label}\n")
    print(f"Added {hub_name} to the labeler.yml file.")

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
        exit(1)

    return github_label


def stage_and_push(
    hub_name: str, root_path: Path, branch_name: str, extra_files: list = None
):
    """
    Stage the new deployment files for the hub.

    Args:
        hub_name (str): The name of the hub.
        root_path (str): The path to the root directory of the repository.
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
        print(f"Adding {str(file)} to staging.")
        try:
            subprocess.check_call(["git", "add", str(file)], cwd=str(root_path))
        except subprocess.CalledProcessError as e:
            print(f"Error adding {str(file)} to commit: {e}")
            exit(1)

    commit_message = f"Add {hub_name} deployment."
    print(f"Committing changes for {hub_name} with message {commit_message}.")
    try:
        subprocess.check_call(
            ["git", "commit", "-m", f"{commit_message}"], cwd=str(root_path)
        )
    except subprocess.CalledProcessError as e:
        print(f"Error committing {hub_name}: {e}")
        exit(1)

    remote = "origin"
    print(f"Pushing {branch_name} to {remote}")
    try:
        subprocess.check_call(["git", "push", remote, branch_name], cwd=str(root_path))
    except subprocess.CalledProcessError as e:
        print(f"Error pushing {branch_name} to {remote}: {e}")
        exit(1)


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
        subprocess.run(command)
    except subprocess.CalledProcessError as e:
        print(f"Unable to create pull request for {hub_name}: {e}")
        exit(1)


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
            )
            .stdout.decode("utf-8")
            .strip()
        )
    except subprocess.CalledProcessError as e:
        print(f"Unable to get branch from {root_path}: {e}.")
        exit(1)

    if branch != "staging":
        print(
            f"Currently not on branch 'staging' in {root_path}. Not "
            + "creating a feature branch and exiting."
        )
        exit(1)
    try:
        subprocess.check_call(["git", "switch", "-c", branch_name], cwd=str(root_path))
    except subprocess.CalledProcessError as e:
        print(f"Error creating branch {branch_name}: {e}")
        exit(1)


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

    # Check for overridden image_name and image_tag in the config, if not found, don't set them.
    cookiecutter(
        template=f"{root_path}/deployments/template",
        output_dir=f"{root_path}/deployments",
        no_input=manual_config,
        extra_context={
            "image_name": (
                config["image_name"]
                if "image_name" in config and config["image_name"]
                else None
            ),
            "image_tag": (
                config["image_tag"]
                if "image_tag" in config and config["image_tag"]
                else None
            ),
            "hub_type": (
                config["hub_type"]
                if "hub_type" in config and config["hub_type"]
                else "python-base"
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
            "client_id_staging": config["staging"]["client"],
            "client_secret_prod": config["prod"]["secret"],
            "client_secret_staging": config["staging"]["secret"],
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

    # Generate secrets for prod and staging
    print(f"Generating and encrypting secrets for {config['hub_name']}.")
    for env in ["prod", "staging"]:
        handle_secrets(config["hub_name"], env)


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
        exit(1)

    if not pod_name:
        print("Error: No NFS server pod found in jupyterhub-home-nfs namespace.")
        exit(1)

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
        exit(1)


def create_deployment(
    config: dict,
    github_user: str,
    root_path: Path,
    deploy: bool = False,
    manual_config: bool = False,
    dry_run: bool = False,
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
    elif args.no_pr:
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
        exit(1)

    # Check if the _deploy_configs directory exists
    if not Path(__file__).resolve().parents[1].joinpath("_deploy_configs").exists():
        print("Error: The _deploy_configs directory does not exist. Please create it.")
        exit(1)

    # Check if the config file exists
    if (
        not Path(__file__)
        .resolve()
        .parents[1]
        .joinpath(f"_deploy_configs/{args.institution_name}.yaml")
        .exists()
    ):
        print(f"Error: The config file {args.institution_name}.yaml does not exist.")
        exit(1)

    root_path = Path(__file__).resolve().parents[1]
    deployment_config = (
        Path(root_path) / "_deploy_configs" / f"{args.institution_name}.yaml"
    )
    config = yaml.safe_load(deployment_config.read_text())
    if not config:
        print(f"Error loading config for {args.institution_name}.")
        exit(1)

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
    )

    print(
        f"\nDeployment for {config['hub_name']} created."
        + "\nDo not forget to create the alerts for the new hub after merging "
        + "the PR to prod. The instructions for that are found here: \n"
        + "https://docs.cal-icor.org/new-hub/#create-the-alerts-for-the-new-hub"
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
