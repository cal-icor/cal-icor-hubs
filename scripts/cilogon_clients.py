#!/usr/bin/env python3
"""
Manage Cal-ICOR's CILogon OIDC clients via the admin client.

Mirrors the CloudBank deployer's `cilogon-client-app` commands

Production clients only -- staging hubs use DummyAuthenticator.

  ./scripts/cilogon_clients.py list
  ./scripts/cilogon_clients.py get    csustan
  ./scripts/cilogon_clients.py add    csustan
  ./scripts/cilogon_clients.py update csustan
  ./scripts/cilogon_clients.py remove csustan

Credentials come from scripts/secrets/enc-cilogon.yaml (sops-encrypted):

    cilogon_admin:
      client_id: cilogon:/adminClient/<hash>/<ts>
      client_secret: <secret>

or from $CILOGON_ADMIN_ID / $CILOGON_ADMIN_SECRET

API reference:
https://cilogon.github.io/oa4mp/server/manuals/dynamic-client-registration.html
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import requests
import yaml

API = "https://cilogon.org/oauth2/oidc-cm"
REPO = Path(__file__).resolve().parent.parent
ADMIN_SECRET_FILE = REPO / "scripts" / "secrets" / "enc-cilogon.yaml"

# Cal-ICOR conventions. Production only -- staging hubs authenticate with
# DummyAuthenticator (authenticator_class: dummy), so they need no CILogon client.
SCOPE = "openid email org.cilogon.userinfo profile"


def hostname(hub):
    return f"{hub}.jupyter.cal-icor.org"


def client_name(hub):
    return f"cal-icor-{hub}"


# --------------------------------------------------------------------------- creds


def load_admin_credentials():
    env_id, env_secret = (
        os.environ.get("CILOGON_ADMIN_ID"),
        os.environ.get("CILOGON_ADMIN_SECRET"),
    )
    if env_id and env_secret:
        return env_id, env_secret

    if not ADMIN_SECRET_FILE.is_file() or ADMIN_SECRET_FILE.stat().st_size == 0:
        sys.exit(
            f"No admin credentials.\n"
            f"  {ADMIN_SECRET_FILE} is missing or empty, and "
            f"CILOGON_ADMIN_ID / CILOGON_ADMIN_SECRET are unset."
        )

    try:
        plain = subprocess.run(
            ["sops", "-d", str(ADMIN_SECRET_FILE)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError as e:
        sys.exit(f"Could not decrypt {ADMIN_SECRET_FILE}:\n{e.stderr}")

    admin = (yaml.safe_load(plain) or {}).get("cilogon_admin") or {}
    cid, secret = admin.get("client_id"), admin.get("client_secret")
    if not cid or not secret:
        sys.exit(
            f"{ADMIN_SECRET_FILE} needs cilogon_admin.client_id and "
            f"cilogon_admin.client_secret (client_id is currently "
            f"{'set' if cid else 'EMPTY'})."
        )
    return cid, secret


def headers(admin_id, admin_secret):
    # NB: CILogon wants base64(id:secret) presented as a *Bearer* token
    token = base64.urlsafe_b64encode(f"{admin_id}:{admin_secret}".encode()).decode(
        "ascii"
    )
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
    }


def url(client_id=None):
    return API if client_id is None else f"{API}?client_id={client_id}"


def body(hub, callback=None):
    """Client payload. `callback` overrides the derived Cal-ICOR URL, which is
    what you want when a hub moves domain -- the main reason to `update`."""
    return {
        "client_name": client_name(hub),
        "app_type": "web",
        "redirect_uris": [callback or f"https://{hostname(hub)}/hub/oauth_callback"],
        "scope": SCOPE,
    }


def check(resp):
    if not resp.ok:
        print(f"CILogon returned {resp.status_code}", file=sys.stderr)
        print(resp.text, file=sys.stderr)
        sys.exit(1)
    return resp


# ------------------------------------------------------------------------- lookups


def all_clients(auth):
    resp = check(requests.get(url(), headers=headers(*auth), timeout=10))
    return resp.json().get("clients", [])


def find_by_hub(auth, hub):
    """Resolve a hub to its client dict via the CILogon-side name."""
    want = client_name(hub)
    matches = [c for c in all_clients(auth) if c.get("name") == want]
    if len(matches) > 1:
        ids = ", ".join(c["client_id"] for c in matches)
        print(
            f"WARNING: {len(matches)} clients named {want!r}: {ids}",
            file=sys.stderr,
        )
    return matches[0] if matches else None


def secrets_path(hub):
    return REPO / "deployments" / hub / "secrets" / "prod.yaml"


def write_to_hub_secrets(hub, client_id, client_secret):
    """Patch the CILogonOAuthenticator credentials into the hub's sops file."""
    path = secrets_path(hub)
    if not path.is_file():
        print(f"  ! {path} does not exist — not written", file=sys.stderr)
        return

    plain = subprocess.run(
        ["sops", "-d", str(path)], capture_output=True, text=True, check=True
    ).stdout
    data = yaml.safe_load(plain) or {}
    cfg = (
        data.setdefault("jupyterhub", {})
        .setdefault("hub", {})
        .setdefault("config", {})
        .setdefault("CILogonOAuthenticator", {})
    )
    cfg["client_id"] = client_id
    cfg["client_secret"] = client_secret

    with tempfile.NamedTemporaryFile(
        "w", suffix=".yaml", delete=False, dir=path.parent
    ) as tmp:
        yaml.safe_dump(data, tmp, default_flow_style=False, sort_keys=False)
        tmp_path = Path(tmp.name)
    try:
        subprocess.run(["sops", "-e", "-i", str(tmp_path)], check=True)
        tmp_path.replace(path)
        print(f"  wrote encrypted credentials to {path.relative_to(REPO)}")
    except subprocess.CalledProcessError as e:
        tmp_path.unlink(missing_ok=True)
        sys.exit(f"sops encrypt failed, {path} left untouched: {e}")


# ------------------------------------------------------------------------ commands


def cmd_list(args, auth):
    clients = all_clients(auth)
    if args.json:
        print(json.dumps(clients, indent=2, sort_keys=True))
        return
    if not clients:
        print("No clients.")
        return
    width = max(len(c.get("name") or "") for c in clients)
    print(f"{len(clients)} client(s)\n")
    # The list endpoint returns names and ids only; use `get` for callbacks.
    for c in sorted(clients, key=lambda x: (x.get("name") or "").lower()):
        name = c.get("name") or "-"
        print(f"  {name:<{width}}  {c.get('client_id', '')}")


def cmd_get(args, auth):
    client = find_by_hub(auth, args.hub)
    if not client:
        sys.exit(f"No CILogon client named {client_name(args.hub)}")
    detail = check(
        requests.get(url(client["client_id"]), headers=headers(*auth), timeout=10)
    ).json()
    print(json.dumps(detail, indent=2, sort_keys=True))


def cmd_add(args, auth):
    payload = body(args.hub, args.callback)
    if args.dry_run:
        print(f"POST {url()}")
        print(json.dumps(payload, indent=2))
        return
    if find_by_hub(auth, args.hub):
        sys.exit(
            f"A client named {client_name(args.hub)} already exists. "
            f"Use `update` instead, or `remove` it first."
        )
    client = check(
        requests.post(url(), json=payload, headers=headers(*auth), timeout=10)
    ).json()
    print(f"Created {client['client_id']}")
    # CILogon does not retain the secret — capture it now or re-create the client.
    if args.write:
        write_to_hub_secrets(args.hub, client["client_id"], client["client_secret"])
    else:
        print(json.dumps(client, indent=2, sort_keys=True))
        print("\n! Secret shown once and never stored by CILogon. Save it now.")


def cmd_update(args, auth):
    client = find_by_hub(auth, args.hub)
    if not client:
        sys.exit(f"No CILogon client named {client_name(args.hub)}")
    payload = body(args.hub, args.callback)
    if args.dry_run:
        print(f"PUT {client['client_id']}")
        print(json.dumps(payload, indent=2))
        return
    # Omitted attributes are DELETED from the stored client, so always PUT the
    # full body rather than a partial patch.
    check(
        requests.put(
            url(client["client_id"]),
            json=payload,
            headers=headers(*auth),
            timeout=10,
        )
    )
    print(f"Updated {client['client_id']}")


def cmd_remove(args, auth):
    client = find_by_hub(auth, args.hub)
    if not client:
        sys.exit(f"No CILogon client named {client_name(args.hub)}")
    cid = client["client_id"]
    if not args.yes:
        confirm = input(f"Delete {client['name']} ({cid})? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return
    check(requests.delete(url(cid), headers=headers(*auth), timeout=10))
    print(f"Deleted {cid}")
    stale = secrets_path(args.hub)
    if stale.is_file():
        print(f"! {stale.relative_to(REPO)} still holds the dead credentials.")


# ---------------------------------------------------------------------------- main


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("list", help="list every Cal-ICOR CILogon client")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("get", help="show one client's full details")
    s.add_argument("hub")
    s.set_defaults(func=cmd_get)

    s = sub.add_parser("add", help="create a client for a hub")
    s.add_argument("hub")
    s.add_argument(
        "--write",
        action="store_true",
        help="patch credentials into deployments/<hub>/secrets/prod.yaml",
    )
    s.add_argument("--callback", help="override the derived callback URL")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_add)

    s = sub.add_parser("update", help="re-PUT a client's name/callback/scope")
    s.add_argument("hub")
    s.add_argument("--callback", help="override the derived callback URL")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_update)

    s = sub.add_parser("remove", help="delete a client")
    s.add_argument("hub")
    s.add_argument("-y", "--yes", action="store_true")
    s.set_defaults(func=cmd_remove)

    args = p.parse_args()
    args.func(args, load_admin_credentials())


if __name__ == "__main__":
    main()
