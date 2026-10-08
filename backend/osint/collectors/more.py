"""Further public sources: Common Crawl index, RDAP for autonomous systems, OpenCorporates (needs a token)."""
import json
import re

import httpx

from ..models import Finding
from ..settings import CFG
from . import collector
from .domain import HTTP

CC_LIMIT, CC_HOSTS = 2000, 200


def parse_commoncrawl(domain: str, crawl: str, lines: list[dict]) -> list[Finding]:
    """CDX json lines ({"url": ...}) -> distinct subdomains of [domain], capped."""
    hosts = {h for l in lines if (h := (re.match(r"^\w+://([^/:?#@]+)", l.get("url", "")) or [None, ""])[1].lower().rstrip(".")) and h.endswith("." + domain)}
    return [Finding(("Dominio", domain), "sottodominio", ("Dominio", h), 0.7, f"visto nell'indice Common Crawl {crawl}",
                    url=f"https://index.commoncrawl.org/{crawl}-index?url={h}&output=json", pivot=False) for h in sorted(hosts)[:CC_HOSTS]]


@collector("commoncrawl", "Dominio")
async def commoncrawl(domain: str) -> list[Finding]:
    async with httpx.AsyncClient(**{**HTTP, "timeout": 60}) as c:
        info = await c.get("https://index.commoncrawl.org/collinfo.json")
        info.raise_for_status()
        crawl = info.json()[0]["id"]  # newest first
        r = await c.get(f"https://index.commoncrawl.org/{crawl}-index", params={"url": f"*.{domain}", "output": "json", "fl": "url", "limit": CC_LIMIT})
    if r.status_code == 404:  # nothing indexed for this domain
        return []
    r.raise_for_status()
    return parse_commoncrawl(domain, crawl, [json.loads(l) for l in r.text.splitlines() if l.startswith("{")])


def parse_rdap_asn(rete: str, d: dict, url: str) -> list[Finding]:
    out = []
    for ent in d.get("entities", []):
        for item in ent.get("vcardArray", [None, []])[1]:
            if item[0] == "fn" and item[3]:
                out.append(Finding(("Rete", rete), "rete_di", ("Azienda", item[3]), 0.85, f"RDAP ruolo {','.join(ent.get('roles', []))}", url=url, pivot=False))
    return out


@collector("rdap_asn", "Rete")
async def rdap_asn(rete: str) -> list[Finding]:
    m = re.match(r"^AS(\d{1,10})\b", rete)  # cymru_asn writes "AS15169 (8.8.8.0/24)"; other Rete values are not ASNs
    if not m:
        return []
    async with httpx.AsyncClient(follow_redirects=True, **HTTP) as c:
        r = await c.get(f"https://rdap.org/autnum/{m[1]}")
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return parse_rdap_asn(rete, r.json(), str(r.url))


def parse_opencorporates(name: str, j: dict, limit: int = 5) -> list[Finding]:
    me, out = ("Azienda", name), []
    for item in (j.get("results", {}).get("companies") or [])[:limit]:
        c = item.get("company") or {}
        if not c.get("company_number"):
            continue
        conf = 0.6 if re.sub(r"\W", "", (c.get("name") or "").lower()) == re.sub(r"\W", "", name.lower()) else 0.35
        url = c.get("opencorporates_url") or ""
        out.append(Finding(me, "numero_registro", ("Registrazione", f"{(c.get('jurisdiction_code') or '?').upper()} {c['company_number']} — {c.get('name', '')}"),
                           conf, "registro societario OpenCorporates", url=url, raw={"status": c.get("current_status"), "incorporated": c.get("incorporation_date")}, pivot=False))
        if c.get("registered_address_in_full"):
            out.append(Finding(me, "registrato_in", ("Luogo", c["registered_address_in_full"]), conf - 0.05, "indirizzo nel registro OpenCorporates", url=url, pivot=False))
    return out


@collector("opencorporates", "Azienda", key="opencorporates_key")
async def opencorporates(name: str) -> list[Finding]:
    async with httpx.AsyncClient(**HTTP) as c:
        r = await c.get("https://api.opencorporates.com/v0.4/companies/search", params={"q": name, "api_token": CFG["opencorporates_key"], "per_page": 5})
    r.raise_for_status()
    return parse_opencorporates(name, r.json())
