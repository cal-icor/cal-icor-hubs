# Uptime Checker and Alert Policy Management

## Create a new uptime checker and associate an alert policy with it for a namespace.

``` bash
create_alerts.py --create --namespaces dev-staging dev-prod
```

## Enable an alert policy for a namespace.

``` bash
create_alerts.py --enable_alerts --namespaces dev-staging
```

## Disable an alert policy for a namespace.

``` bash
create_alerts.py --disable_alerts --namespaces dev-staging
```

## Delete the alert policy and uptime check for a namespace.

``` bash
create_alerts.py --delete_alerts --namespaces dev-prod
```
