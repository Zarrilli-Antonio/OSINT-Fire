import base64
import hashlib

import httpx

from ..models import Finding
from . import collector
from .domain import HTTP

HOSTS = ("github.com", "gitlab.com", "codeberg.org")


def ssh_fingerprint(line: str) -> str | None:
    parts = line.split()
    if len(parts) < 2 or not parts[0].startswith(("ssh-", "ecdsa-", "sk-")):
        return None
    try:
        blob = base64.b64decode(parts[1], validate=True)
    except ValueError:
        return None
    return "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")


def parse_keys(username: str, host: str, text: str) -> list[Finding]:
    acc, out = ("Account", f"https://{host}/{username}"), []
    for fp in sorted({f for line in text.splitlines()[:20] if (f := ssh_fingerprint(line))}):
        out.append(Finding(acc, "chiave_ssh", ("Chiave SSH", fp), 0.95, f"chiave SSH pubblica su {host}", url=f"https://{host}/{username}.keys", pivot=False))
    if out:
        out.insert(0, Finding(("Username", username), "possibile_profilo", acc, 0.7, f"{host} pubblica chiavi per questo username", pivot=False))
    return out


@collector("ssh_keys", "Username")
async def ssh_keys(username: str) -> list[Finding]:
    """Public SSH keys listed by forges. The same key on two sites is strong proof of the same owner."""
    out = []
    async with httpx.AsyncClient(follow_redirects=True, **HTTP) as c:
        for host in HOSTS:
            try:
                r = await c.get(f"https://{host}/{username}.keys")
            except httpx.HTTPError:
                continue
            if r.status_code == 200 and "text/plain" in r.headers.get("content-type", "text/plain"):
                out += parse_keys(username, host, r.text)
    return out
