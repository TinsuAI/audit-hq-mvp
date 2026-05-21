#!/usr/bin/env python3
"""Add audit-hq-demo.tinsu.ai → http://localhost:8000 vào Cloudflare Tunnel.

Tunnel `tinsu-online-server` (UUID 691a9772-…) là remotely-managed — phải
PUT qua Cloudflare API (không sửa /etc/cloudflared/config.yml).

Đọc credentials từ ~/.cloudflared/cert.pem trên Tinsu VPS, idempotent.

Chạy 1 lần lúc setup:
    ssh tinsu 'python3 ~/audit-hq-mvp/deploy/scripts/add-tunnel-ingress.py'
"""

from __future__ import annotations

import base64
import json
import sys
import urllib.error
import urllib.request

CERT_PATH = "/home/tinsu/.cloudflared/cert.pem"
TUNNEL_ID = "691a9772-3168-422e-81eb-7c26e1dec9ef"
HOSTNAME = "audit-hq-demo.tinsu.ai"
SERVICE = "http://localhost:8000"


def load_credentials() -> tuple[str, str]:
    with open(CERT_PATH) as f:
        pem = f.read()
    b64 = "".join(line for line in pem.splitlines() if "TUNNEL" not in line)
    data = json.loads(base64.b64decode(b64))
    return data["apiToken"], data["accountID"]


def main() -> int:
    token, acct = load_credentials()
    url = f"https://api.cloudflare.com/client/v4/accounts/{acct}/cfd_tunnel/{TUNNEL_ID}/configurations"
    headers = {"Authorization": f"Bearer {token}"}

    cur = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=headers)))
    ingress = cur["result"]["config"]["ingress"]
    print(f"Current ingress entries: {len(ingress)}")

    if any(e.get("hostname") == HOSTNAME for e in ingress):
        print(f"{HOSTNAME} already present — nothing to do.")
        return 0

    new_entry = {"hostname": HOSTNAME, "service": SERVICE}
    named = [e for e in ingress if "hostname" in e]
    catchall = [e for e in ingress if "hostname" not in e]
    new_ingress = named + [new_entry] + catchall

    payload: dict = {"config": {"ingress": new_ingress}}
    if "warp-routing" in cur["result"]["config"]:
        payload["config"]["warp-routing"] = cur["result"]["config"]["warp-routing"]

    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body, method="PUT",
        headers={**headers, "Content-Type": "application/json"},
    )
    try:
        resp = json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode()}", file=sys.stderr)
        return 1

    print(f"✓ PUT success: {resp.get('success')}")
    print(
        f"  New version: {resp['result']['version']}, "
        f"entries: {len(resp['result']['config']['ingress'])}"
    )
    print(f"\nDNS: ensure {HOSTNAME} CNAME points to {TUNNEL_ID}.cfargotunnel.com")
    return 0


if __name__ == "__main__":
    sys.exit(main())
