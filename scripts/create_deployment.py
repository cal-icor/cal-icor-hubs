#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml
from cookiecutter.main import cookiecutter
from hubploy import helm


def delete_file(filepath):
    """
    Deletes a file from the filesystem.

    Args:
        filepath (str): The path to the file to be deleted.

    Raises:
        FileNotFoundError: If the file does not exist.
        PermissionError: If the file cannot be deleted due to insufficient permissions.
        Exception: For any other errors during file deletion.
    """
    try:
        os.remove(filepath)
        print(f"Deleted file: {filepath}")
    except FileNotFoundError:
        print(f"File not found: {filepath}")
    except PermissionError:
        print(f"No permission to delete: {filepath}")
    except Exception as e:
        print(f"Error deleting file: {e}")


def encrypt_file(input_file, output_file):
    """
    Encrypts a file using the `sops` command-line tool.

    Args:
        input_file (str): The path to the input file to be encrypted.
        output_file (str): The path where the encrypted file will be saved.

    Raises:
        SystemExit: If the input file does not exist or encryption fails.
    """
    if not os.path.isfile(input_file):
        print(f"Error: Input file '{input_file}' does not exist.")
        sys.exit(1)

    try:
        subprocess.run(
            ["sops", "--output", output_file, "--encrypt", input_file], check=True
        )
        print(f"Encrypted file saved as: {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"Encryption failed: {e}")
        sys.exit(1)


def handle_secrets(school_arg, env_arg):
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
        os.path.join("deployments", school_arg, "secrets", f"{env_arg}.plain.yaml"),
        os.path.join("deployments", school_arg, "secrets", f"{env_arg}.yaml"),
    )
    delete_file(
        os.path.join("deployments", school_arg, "secrets", f"{env_arg}.plain.yaml")
    )


def create_label(hub_name, root_path):
    """
    Create labels for the new hub in the GitHub repository.

    Args:
        hub_name (str): The name of the hub.
        root_path (str): The path to the root directory of the repository.
    Returns:
        str: The GitHub label created for the new hub.
    """
    labeler_path = os.path.join(root_path, ".github", "labeler.yml")
    hub_label = f"""
'hub: {hub_name}':
  - 'deployments/{hub_name}/**'
""".strip()
    with open(labeler_path, "a") as f:
        print(hub_label, file=f)
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


def stage_and_push(hub_name, root_path, branch_name):
    """
    Stage the new deployment files for the hub.

    Args:
        hub_name (str): The name of the hub.
        root_path (str): The path to the root directory of the repository.
        branch_name (str): The name of the branch to push the changes to.
    """
    files_to_add = [
        f"deployments/{hub_name}/",
        ".github/labeler.yml",
    ]
    for file in files_to_add:
        print(f"Adding {file} to staging.")
        try:
            subprocess.check_call(["git", "add", file], cwd=root_path)
        except subprocess.CalledProcessError as e:
            print(f"Error adding {file} to commit: {e}")
            exit(1)

    commit_message = f"Add {hub_name} deployment."
    print(f"Committing changes for {hub_name} with message {commit_message}.")
    try:
        subprocess.check_call(
            ["git", "commit", "-m", f"{commit_message}"], cwd=root_path
        )
    except subprocess.CalledProcessError as e:
        print(f"Error committing {hub_name}: {e}")
        exit(1)

    remote = "origin"
    print(f"Pushing {branch_name} to {remote}")
    try:
        subprocess.check_call(["git", "push", remote, branch_name], cwd=root_path)
    except subprocess.CalledProcessError as e:
        print(f"Error pushing {branch_name} to {remote}: {e}")
        exit(1)


def create_pr(github_user, hub_name, branch_name, github_label):
    """
    Add, commit and create a pull request for the new hub deployment.
    Args:
        github_user (str): The GitHub username of the user creating the pull request.
        hub_name (str): The name of the hub.
        root_path (str): The path to the root directory of the repository.
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


def create_branch(branch_name, root_path):
    """
    Create a new branch in the Git repository.

    Args:
        branch_name (str): The name of the new branch to be created.
    """
    try:
        branch = (
            subprocess.run(
                ["git", "branch", "--show-current"], cwd=root_path, capture_output=True
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
        subprocess.check_call(["git", "switch", "-c", branch_name], cwd=root_path)
        print(f"Created new branch: {branch_name}")
    except subprocess.CalledProcessError as e:
        print(f"Error creating branch {branch_name}: {e}")
        exit(1)


def populate_deployment_config(config, root_path, manual_config):
    """
    Populate the deployment configuration file with the provided configuration.

    Args:
        config (dict): The configuration dictionary containing deployment details.
        root_path (str): The path to the root directory of the repository.
        manual_config (bool): If True, the script will ask for confirmation for each step.
    """
    # Run the cookiecutter to generate the deployment files
    print(f"Generating {config['hub_name']} cookiecutter template.")
    cookiecutter(
        template=f"{root_path}/deployments/template",
        output_dir=f"{root_path}/deployments",
        no_input=manual_config,
        extra_context={
            "hub_name": config["hub_name"],
            "hub_filestore_instance": config["hub_filestore_instance"],
            "hub_filestore_ip": config["hub_filestore_ip"],
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
            "allow_all": config["allow_all"],
            "admin_emails": ", ".join(email for email in config["admin_emails"]),
        },
    )

    # Generate secrets for prod and staging
    print(f"Generating and encrypting secrets for {config['hub_name']}.")
    for env in ["prod", "staging"]:
        handle_secrets(config["hub_name"], env)


def create_deployment(config, github_user, root_path, manual_config=False):
    """
    Create a new deployment for an institution using the provided configuration.
    Args:
        config (dict): The configuration dictionary containing deployment details.
        root_path (str): The parent path where the deployment will be created.
        manual_config (bool): If True, the script will ask for confirmation for each step.
    """
    # create the prod and staging directories on filestore for the new hub
    print(f"Creating directories for {config['hub_name']} on filestore.")
    try:
        subprocess.check_call(
            [
                "gcloud",
                "compute",
                "ssh",
                "nfsserver",
                "--tunnel-through-iap",
                "--zone=us-central1-b",
                "--command",
                "sudo -u ubuntu install -d -o 1000 -g 1000 "
                + f"/export/{config['hub_filestore_instance']}/{config['hub_name']}/prod "
                + f"/export/{config['hub_filestore_instance']}/{config['hub_name']}/staging",
            ]
        )
    except subprocess.CalledProcessError as e:
        print(f"Error creating directories for {config['hub_name']}: {e}")
        exit(1)

    # Create a feature branch
    branch_name = f"add-{config['hub_name']}-deployment"
    create_branch(branch_name, root_path)

    # Populate the deployment configuration
    print(f"Populating deployment config for {config['hub_name']}.")
    populate_deployment_config(config, root_path, manual_config)

    # Create labels for the new hub
    print(f"Creating repo and github labels for {config['hub_name']}.")
    github_label = create_label(config["hub_name"], root_path)

    # Stage the new deployment files
    print(f"Staging new deployment files for {config['hub_name']}.")
    stage_and_push(config["hub_name"], root_path, branch_name)

    # Create a pull request for the new hub
    print(f"Creating pull request for {config['hub_name']}.")
    create_pr(github_user, config["hub_name"], branch_name, github_label)


def main():
    """
    Main function to parse arguments and create a new deployment for an institution.
    This script should be run from the root cal-icor-hubs directory.
    """

    parser = argparse.ArgumentParser(
        description="Create a new deployment for an institution.  This should "
        + "be run from the root cal-icor-hubs directory."
        + "\n\n"
        + "You will also need to fill out the cookiecutter template config "
        + "in the _deploy_configs/<hubname>.yaml dir in the root of the repo.",
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
        help="The GitHub username of the user creating the pull request.",
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
        + "filestore IP, node pool deployment, etc).",
    )
    args = parser.parse_args()

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
    file_path = f"{root_path}/_deploy_configs/{args.institution_name}.yaml"
    with open(file_path) as f:
        config = yaml.safe_load(f)
    if not config:
        print(f"Error loading config for {args.institution_name}.")
        exit(1)

    create_deployment(config, args.github_user, root_path, args.manual_config)

    if args.deploy:
        print(f"Deploying the hub to {config['hub_name']}-staging.")
        helm.deploy(hub=config["hub_name"], chart="hub", environment="staging")
        print(f"Deployment to {config['hub_name']}-staging complete.")


if __name__ == "__main__":
    main()
