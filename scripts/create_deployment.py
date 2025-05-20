#!/usr/bin/env python3
import argparse
from pathlib import Path

import secret_file_gen as sfg
import yaml
from cookiecutter.main import cookiecutter


def create_deployment(config, root_path, manual_config=False):
    """
    Create a new deployment for an institution using the provided configuration.
    Args:
        config (dict): The configuration dictionary containing deployment details.
        root_path (str): The parent path where the deployment will be created.
    """

    cookiecutter(
        template=f"{root_path}/deployments/template",
        output_dir=f"{root_path}/deployments",
        no_input=manual_config,
        extra_context={
            "hub_name": config["hub_name"],
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
            "admin_emails": ", ".join(email for email in config["admin_emails"]),
        },
    )
    print(f"{config['hub_name']} cookiecutter template configured successfully.")
    # Generate secrets for prod and staging
    for env in ["prod", "staging"]:
        sfg.handle_secrets(config["hub_name"], env)


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

    create_deployment(config, root_path, args.manual_config)


if __name__ == "__main__":
    main()
