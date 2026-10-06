import re
from urllib.parse import unquote

import httpx

from ..models import Finding
from . import collector
from .domain import HTTP

SERVERS = ("https://keys.openpgp.org", "https://keyserver.ubuntu.com")
ADDR = re.compile(r"^(.*?)\s*<([^<>@\s]+@[^<>\s]+)>\s*$")
REVERSED = re.compile(r"^([^<>\s]+@[^<>\s]+)\s*<([^<>]+)>\s*$")  # "<addr> <Name>" stored the other way round


def parse_pgp(email: str, text: str, url: str) -> list[Finding]:
    """Machine-readable HKP index: `pub:<fingerprint>:...` followed by `uid:<Name <addr>>:...` lines."""
    out, key = [], None
    for line in text.splitlines():
        f = line.split(":")
        if f[0] == "pub" and len(f) > 1 and f[1]:
            key = ("Chiave PGP", f[1].upper())
            out.append(Finding(("Email", email), "chiave_pgp", key, 0.8, "chiave pubblica su keyserver", url=url, pivot=False))
        elif f[0] == "uid" and key and len(f) > 1:
            uid = unquote(f[1])
            if m := ADDR.match(uid):
                name, addr = m.group(1).strip(), m.group(2).lower()
            elif m := REVERSED.match(uid):
                addr, name = m.group(1).lower(), m.group(2).strip()
            else:
                continue
            if name and "@" not in name:
                out.append(Finding(key, "identita_nella_chiave", ("Persona", name), 0.6, "nome nello UID della chiave PGP", url=url, pivot=False))
            if addr != email and "@" in addr:
                out.append(Finding(key, "email_nella_chiave", ("Email", addr), 0.7, "altro indirizzo nello UID della chiave PGP", url=url))
    return out


@collector("pgp_keyserver", "Email")
async def pgp_keyserver(email: str) -> list[Finding]:
    out = []
    async with httpx.AsyncClient(**HTTP) as c:
        for base in SERVERS:
            try:
                r = await c.get(f"{base}/pks/lookup", params={"op": "index", "options": "mr", "search": email})
            except httpx.HTTPError:
                continue  # one keyserver down must not hide the other
            if r.status_code == 200:
                out += parse_pgp(email, r.text, str(r.url))
    return out
