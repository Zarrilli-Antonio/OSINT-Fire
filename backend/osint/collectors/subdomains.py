import re
import time

import httpx

from ..models import Finding
from . import collector
from .domain import HTTP, MAX_SUBDOMAINS

HOSTNAME = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")
_ht_blocked_until = 0.0  # hackertarget free tier: ~50 requests/day per IP. After a refusal, skip it for an hour.


async def hackertarget(path: str, q: str) -> str:
    global _ht_blocked_until
    if time.time() < _ht_blocked_until:
        return ""
    async with httpx.AsyncClient(**HTTP) as c:
        r = await c.get(f"https://api.hackertarget.com/{path}/", params={"q": q})
    r.raise_for_status()
    text = r.text.strip()
    if text.lower().startswith(("api count exceeded", "error check your search")):
        _ht_blocked_until = time.time() + 3600
        raise RuntimeError(f"hackertarget: {text[:80]}")
    return "" if text.lower().startswith("error") or text.lower().startswith("no records") else text


def parse_hostsearch(domain: str, text: str) -> list[Finding]:
    out, seen = [], set()
    for line in text.splitlines()[:MAX_SUBDOMAINS]:
        host, _, ip = line.partition(",")
        host = host.strip().lower()
        if not host.endswith("." + domain) or host in seen:
            continue
        seen.add(host)
        out.append(Finding(("Dominio", domain), "sottodominio", ("Dominio", host), 0.8, "hostsearch pubblico (HackerTarget)"))
        if ip.strip():
            out.append(Finding(("Dominio", host), "risolve_a", ("IP", ip.strip()), 0.7, "IP noto a HackerTarget", pivot=False))
    return out


@collector("hackertarget_hosts", "Dominio")
async def hackertarget_hosts(domain: str) -> list[Finding]:
    return parse_hostsearch(domain, await hackertarget("hostsearch", domain))


def parse_certspotter(domain: str, issuances: list) -> list[Finding]:
    names = {n.lstrip("*.").lower() for i in issuances for n in i.get("dns_names", [])}
    return [Finding(("Dominio", domain), "sottodominio", ("Dominio", n), 0.9, "certificato TLS (Cert Spotter)")
            for n in sorted(names) if n.endswith("." + domain)][:MAX_SUBDOMAINS]


@collector("certspotter", "Dominio")
async def certspotter(domain: str) -> list[Finding]:
    async with httpx.AsyncClient(**{**HTTP, "timeout": 40}) as c:
        r = await c.get("https://api.certspotter.com/v1/issuances",
                        params={"domain": domain, "include_subdomains": "true", "expand": "dns_names"})
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return parse_certspotter(domain, r.json())
