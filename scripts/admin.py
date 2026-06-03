#!/usr/bin/env python3
"""
VIREN admin CLI. Talks to the gateway's /admin/* endpoints using the
master key.

Examples:
    python scripts/admin.py create acme "Acme Corp" --budget 5000 --min-tier balanced
    python scripts/admin.py list
    python scripts/admin.py usage acme

Env:
    GATEWAY_URL=http://localhost:8000
    GATEWAY_MASTER_KEY=...
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def call(method: str, path: str, body: dict | None = None) -> dict:
    url = os.environ.get("GATEWAY_URL", "http://localhost:8000").rstrip("/") + path
    master = os.environ.get("GATEWAY_MASTER_KEY")
    if not master:
        print("set GATEWAY_MASTER_KEY", file=sys.stderr); sys.exit(2)
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": f"Bearer {master}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}", file=sys.stderr); sys.exit(1)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create", help="Create a tenant")
    c.add_argument("tenant_id")
    c.add_argument("name")
    c.add_argument("--email", default=None)
    c.add_argument("--budget", type=float, default=1000.0)
    c.add_argument("--min-tier", default="cheap", choices=["cheap", "balanced", "frontier"])
    c.add_argument("--notes", default=None)

    sub.add_parser("list", help="List all tenants")

    u = sub.add_parser("usage", help="Show usage for a tenant")
    u.add_argument("tenant_id")

    args = p.parse_args()

    if args.cmd == "create":
        r = call("POST", "/admin/tenants", {
            "id": args.tenant_id, "name": args.name, "contact_email": args.email,
            "monthly_budget_usd": args.budget, "min_tier": args.min_tier,
            "notes": args.notes,
        })
        print(f"Tenant created: {r['id']}")
        print(f"API key (store this NOW — cannot be retrieved later):")
        print(f"  {r['api_key']}")

    elif args.cmd == "list":
        r = call("GET", "/admin/tenants")
        for t in r["tenants"]:
            print(f"  {t['id']:20s}  {t['name']:30s}  "
                  f"min={t['min_tier']:9s}  budget=${t['monthly_budget_usd']:.0f}")

    elif args.cmd == "usage":
        r = call("GET", f"/admin/usage/{args.tenant_id}")
        print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
