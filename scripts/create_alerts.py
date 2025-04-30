#!/usr/bin/env python3
import argparse
import json
import re
import subprocess

import yaml


def find_target_channels(namespace, project_id):
    target_channels = []
    if "staging" in namespace:
        target_channels.append(project_id + "-staging-alert-channel")
    if "prod" in namespace:
        target_channels.append(project_id + "-prod-alert-channel")
        target_channels.append("Berkeley Datahub - PagerDuty")
        target_channels.append("ds-infrastructure-email")
    return target_channels


def extract_channel_names(target_channels):
    try:
        result = subprocess.run(
            ["gcloud", "alpha", "monitoring", "channels", "list"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"Error running gcloud command: {e}")
        return None

    yaml_content = result.stdout
    documents = yaml.safe_load_all(yaml_content)

    channel_names = []
    for document in documents:
        if document.get("displayName") in target_channels:
            channel_names.append(document.get("name"))

    return channel_names


def get_notification_channels(namespace, project_id):
    target_channels = find_target_channels(namespace, project_id)
    notification_channels = extract_channel_names(target_channels)
    return notification_channels


def find_host(namespace, domain):
    host = ""
    if "staging" in namespace:
        host = (
            namespace + "." + domain
            if namespace != "jupyter-staging"
            else "staging." + domain
        )
    elif "prod" in namespace:
        host = (
            namespace.split("-")[0] + "." + domain
            if namespace != "jupyter-prod"
            else domain
        )
    return host


def extract_policy_id(namespace):
    try:
        result = subprocess.run(
            ["gcloud", "alpha", "monitoring", "policies", "list"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"Error running gcloud command: {e}")
        return None

    yaml_content = result.stdout
    documents = yaml.safe_load_all(yaml_content)

    for document in documents:
        if namespace + " uptime failure" == document.get("displayName"):
            return document.get("name")
    return None


def disable_alert_for_policy(namespace):
    policy_name = extract_policy_id(namespace)
    if not policy_name:
        print(f"Could not find an alert policy for {namespace}. ")
        return
    try:
        subprocess.run(
            [
                "gcloud",
                "alpha",
                "monitoring",
                "policies",
                "update",
                policy_name,
                "--no-enabled",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        print(f"Successfully disabled alerts for {namespace}. ")
    except subprocess.CalledProcessError as e:
        print(f"Error running gcloud command: {e}")


def enable_alert_for_policy(namespace):
    policy_name = extract_policy_id(namespace)
    if not policy_name:
        print(f"Could not find an alert policy for {namespace}. ")
        return
    try:
        subprocess.run(
            [
                "gcloud",
                "alpha",
                "monitoring",
                "policies",
                "update",
                policy_name,
                "--enabled",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        print(f"Successfully enabled alerts for {namespace}. ")
    except subprocess.CalledProcessError as e:
        print(f"Error running gcloud command: {e}")


def create_uptime_check(host, project_id):
    """
    Function to create the uptime check and capture the uptime_check_id
    """
    # Run the uptime check creation command
    command = [
        "gcloud",
        "monitoring",
        "uptime",
        "create",
        f"{host}",
        "--resource-labels",
        f"host={host},project_id={project_id}",
        "--resource-type",
        "uptime-url",
        "--request-method",
        "get",
        "--validate-ssl",
        "true",
        "--protocol",
        "https",
        "--port",
        "443",
        "--status-classes",
        "2xx",
        "--period",
        "1",
        "--timeout",
        "10",
    ]

    # Run the command and capture the output
    result = subprocess.run(command, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        print(f"Error creating uptime check for {host}. ")
        return None

    # The expected output format is: "Created uptime [projects/<project_id>/uptimeCheckConfigs/<uptime_check_id>]."
    uptime_check_id_match = re.search(
        r"Created uptime \[projects/[^/]+/uptimeCheckConfigs/([^/]+)\]", result.stderr
    )
    if uptime_check_id_match:
        return uptime_check_id_match.group(1)
    print(f"Could not extract uptime_check_id for {host}. ")
    return None


def create_alerts(namespaces, domain, project_id):
    """
    Iterate through each namespace and domain to create and run the `gcloud` command
    """
    for namespace in namespaces:
        host = find_host(namespace, domain)
        if not host:
            print(f"Could not find a notification channel for {host}. ")
            continue

        notification_channels = get_notification_channels(namespace, project_id)
        if not len(notification_channels):
            print(f"Could not find a notification channel for {host}. ")
            continue

        if not host:
            print(f"Could not find a notification channel for {host}. ")
            continue

        # Create uptime check and capture uptime_check_id
        print(f"Creating uptime check for {host}...")
        uptime_check_id = create_uptime_check(host, project_id)

        if uptime_check_id is None:
            print(
                f"Skipping alert policy creation for {host} due to uptime check creation failure."
            )
            continue

        duration = "600s"
        if "staging" in namespace:
            duration = "1800s"

        # Create JSON structure for alert policy
        alert_policy = {
            "displayName": f"{namespace} uptime failure",
            "conditions": [
                {
                    "displayName": f"{namespace} uptime failure greater than 1",
                    "conditionThreshold": {
                        "aggregations": [
                            {
                                "alignmentPeriod": "600s",
                                "crossSeriesReducer": "REDUCE_COUNT_FALSE",
                                "groupByFields": [
                                    "resource.label.project_id",
                                    "resource.label.host",
                                ],
                                "perSeriesAligner": "ALIGN_NEXT_OLDER",
                            }
                        ],
                        "comparison": "COMPARISON_GT",
                        "duration": duration,
                        "filter": f'resource.type = "uptime_url" AND metric.type = "monitoring.googleapis.com/uptime_check/check_passed" AND metric.labels.check_id = "{uptime_check_id}"',
                        "thresholdValue": 1,
                        "trigger": {"count": 1},
                    },
                }
            ],
            "alertStrategy": {},
            "combiner": "OR",
            "enabled": True,
            "notificationChannels": notification_channels,
            "severity": "CRITICAL",
        }

        # Write the alert policy to a JSON file
        json_filename = f"{host}_alert.json"
        with open(json_filename, "w") as f:
            json.dump(alert_policy, f, indent=2)

        # Run the gcloud command to create the alert policy
        try:
            print(f"Creating alert policy for {host}...")
            command = [
                "gcloud",
                "alpha",
                "monitoring",
                "policies",
                "create",
                f"--policy-from-file={json_filename}",
            ]
            subprocess.run(command, check=True)
            print(f"Alert policy for {host} created successfully!")
        except subprocess.CalledProcessError as e:
            print(f"Error creating alert policy for {host}: {e}")


def main():
    """
    Usage:
    1. Create a new uptime checker and associate an alert policy with it for a namespace.
        python3 create_alerts.py --create --namespaces dev-staging dev-prod
    2. Enable an alert policy for a namespace.
        python3 create_alerts.py --enable_alerts --namespaces dev-staging
    3. Disable an alert policy for a namespace.
        python3 create_alerts.py --disable_alerts --namespaces dev-staging
    """
    parser = argparse.ArgumentParser(
        description="Create alerts with specified parameters."
    )

    parser.add_argument(
        "--namespaces", help="Comma-separated list of namespaces.", nargs="*"
    )
    parser.add_argument(
        "--domain", help="The domain to use for alerts.", default="jupyter.cal-icor.org"
    )
    parser.add_argument(
        "--project_id", help="The Google Cloud project ID.", default="cal-icor-hubs"
    )
    parser.add_argument(
        "--enable_alerts", action="store_true", help="Enable alert policy."
    )
    parser.add_argument(
        "--disable_alerts", action="store_true", help="Disable alert policy."
    )
    parser.add_argument(
        "--create", action="store_true", help="Create an alert policy.", default=False
    )

    args = parser.parse_args()
    namespaces = args.namespaces
    if args.enable_alerts:
        for namespace in namespaces:
            enable_alert_for_policy(namespace)

    if args.disable_alerts:
        for namespace in namespaces:
            disable_alert_for_policy(namespace)
    if args.create:
        create_alerts(namespaces, args.domain, args.project_id)


if __name__ == "__main__":
    main()
