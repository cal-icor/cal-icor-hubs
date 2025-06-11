#!/usr/bin/env bash

echo "Creating and Enabling alerts for namespace: $1-prod" 
python3 -u ./scripts/hub_alerts/create_alerts.py --create --namespaces $1-prod
python3 -u ./scripts/hub_alerts/create_alerts.py --enable --namespaces $1-prod
rm $1.jupyter.cal-icor.org_alert.json
