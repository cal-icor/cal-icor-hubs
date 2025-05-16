import argparse
from pathlib import Path

import secret_file_gen as sfg
import yaml
from cookiecutter.main import cookiecutter

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process school name")
    parser.add_argument("school_name", help="The name of the school")
    args = parser.parse_args()

    par_path = Path(__file__).resolve().parents[1]
    file_path = f"{par_path}/_deploy_configs/{args.school_name}-build-config.yaml"
    with open(file_path) as f:
        config = yaml.safe_load(f)
    if not config:
        print(f"Error: No configuration found for {args.school_name}.")
        exit(1)

    cookiecutter(
        template=f"{par_path}/deployments/template",
        output_dir=f"{par_path}/deployments",
        no_input=True,
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
    print(f"{config["hub_name"]} cookiecutter template configured successfully.")
    # Generate secrets for prod and staging
    for env in ["prod", "staging"]:
        sfg.handle_secrets(config["hub_name"], env)
