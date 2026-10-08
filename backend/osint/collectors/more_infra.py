"""Infrastructure sources: AlienVault OTX, Robtex, RIPEstat, PeeringDB, Tranco, Mozilla Observatory, DNSBL, favicon hash."""
import base64
import json
import re
from urllib.parse import urljoin, urlparse

import dns.asyncresolver
import dns.exception
import dns.reversename
import httpx

from ..models import Finding
from . import collector
from .domain import HTTP

CAP = 50
RIPE = "https://stat.ripe.net/data"
HOST = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")


async def _get(url: str, ok404: bool = True, **kw) -> httpx.Response | None:
    async with httpx.AsyncClient(follow_redirects=True, **HTTP) as c:
        r = await c.get(url, **kw)
    if r.status_code == 404 and ok404:
        return None
    r.raise_for_status()
    return r


# --- AlienVault OTX (indicator "general": the community reports that list the indicator) ---
def parse_otx(kind: str, value: str, j: dict, limit: int = 10) -> list[Finding]:
    out = []
    for p in (j.get("pulse_info") or {}).get("pulses", [])[:limit]:
        name = " ".join(str(p.get("name") or "").split())[:100]
        if p.get("id") and name:
            out.append(Finding((kind, value), "menzionato_in", ("Documento", f"OTX: {name}"), 0.4, "indicatore in un report AlienVault OTX",
                               url=f"https://otx.alienvault.com/pulse/{p['id']}", raw={"tags": p.get("tags")}, pivot=False))
    return out


async def _otx(kind: str, api: str, value: str) -> list[Finding]:
    r = await _get(f"https://otx.alienvault.com/api/v1/indicators/{api}/{value}/general")
    return parse_otx(kind, value, r.json(), ) if r else []


@collector("otx_domain", "Dominio")
async def otx_domain(domain: str) -> list[Finding]:
    return await _otx("Dominio", "domain", domain)


@collector("otx_ip", "IP")
async def otx_ip(ip: str) -> list[Finding]:
    return await _otx("IP", "IPv6" if ":" in ip else "IPv4", ip)


# --- Robtex free API (passive DNS) ---
def parse_robtex_domain(domain: str, text: str) -> list[Finding]:
    seen, out = set(), []
    for line in text.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        t, v = d.get("rrtype"), str(d.get("rrdata") or "").lower().rstrip(".")
        if (t, v) in seen or not v:
            continue
        if t in ("A", "AAAA"):
            out.append(Finding(("Dominio", domain), "risolve_a", ("IP", v), 0.6, "DNS passivo Robtex (può essere storico)", url=f"https://www.robtex.com/dns-lookup/{domain}", pivot=False))
        elif t in ("NS", "MX") and HOST.match(v):
            out.append(Finding(("Dominio", domain), "usa_nameserver" if t == "NS" else "server_posta", ("Dominio", v), 0.6, "DNS passivo Robtex (può essere storico)",
                               url=f"https://www.robtex.com/dns-lookup/{domain}", pivot=False))
        else:
            continue
        seen.add((t, v))
    return out[:CAP]


@collector("robtex_domain", "Dominio")
async def robtex_domain(domain: str) -> list[Finding]:
    r = await _get(f"https://freeapi.robtex.com/pdns/forward/{domain}")
    return parse_robtex_domain(domain, r.text) if r else []


def parse_robtex_ip(ip: str, j: dict) -> list[Finding]:
    names = {str(p.get("o") or "").lower().rstrip(".") for p in j.get("pas") or []}
    return [Finding(("IP", ip), "dominio_ospitato", ("Dominio", n), 0.5, "DNS passivo Robtex (può essere storico o hosting condiviso)", url=f"https://www.robtex.com/ip-lookup/{ip}", pivot=False)
            for n in sorted(names) if HOST.match(n)][:CAP]


@collector("robtex_ip", "IP")
async def robtex_ip(ip: str) -> list[Finding]:
    r = await _get(f"https://freeapi.robtex.com/ipquery/{ip}")
    return parse_robtex_ip(ip, r.json()) if r else []


# --- RIPEstat ---
def parse_ripe_abuse(ip: str, j: dict) -> list[Finding]:
    return [Finding(("IP", ip), "contatto_abuso", ("Email", m.lower()), 0.85, "contatto abuse nel registro RIR (RIPEstat)", url=f"https://stat.ripe.net/{ip}", pivot=False)
            for m in (j.get("data") or {}).get("abuse_contacts", []) if "@" in m]


@collector("ripe_abuse", "IP")
async def ripe_abuse(ip: str) -> list[Finding]:
    r = await _get(f"{RIPE}/abuse-contact-finder/data.json", params={"resource": ip})
    return parse_ripe_abuse(ip, r.json()) if r else []


def parse_ripe_prefix(ip: str, j: dict) -> list[Finding]:
    d, out = j.get("data") or {}, []
    if not d.get("announced"):
        return out
    for a in d.get("asns", []):
        net, url = f"AS{a['asn']} ({d['resource']})", f"https://stat.ripe.net/{ip}"
        out.append(Finding(("IP", ip), "parte_di_rete", ("Rete", net), 0.9, "prefisso annunciato in BGP (RIPEstat)", url=url, pivot=False))
        if a.get("holder"):
            out.append(Finding(("Rete", net), "rete_di", ("Azienda", a["holder"]), 0.8, "titolare dell'ASN (RIPEstat)", url=url, pivot=False))
    return out


@collector("ripe_prefix", "IP")
async def ripe_prefix(ip: str) -> list[Finding]:
    r = await _get(f"{RIPE}/prefix-overview/data.json", params={"resource": ip})
    return parse_ripe_prefix(ip, r.json()) if r else []


def parse_ripe_asn(rete: str, asn: str, overview: dict, prefixes: dict, limit: int = 30) -> list[Finding]:
    out, url = [], f"https://stat.ripe.net/AS{asn}"
    if holder := (overview.get("data") or {}).get("holder"):
        out.append(Finding(("Rete", rete), "rete_di", ("Azienda", holder), 0.8, "titolare dell'ASN (RIPEstat)", url=url, pivot=False))
    for p in (prefixes.get("data") or {}).get("prefixes", [])[:limit]:
        if p.get("prefix"):
            out.append(Finding(("Rete", rete), "annuncia_prefisso", ("Rete", f"AS{asn} ({p['prefix']})"), 0.85, "prefisso annunciato in BGP (RIPEstat)", url=url, pivot=False))
    return out


@collector("ripe_asn", "Rete")
async def ripe_asn(rete: str) -> list[Finding]:
    m = re.match(r"^AS(\d{1,10})\b", rete)
    if not m:
        return []
    ov, pf = await _get(f"{RIPE}/as-overview/data.json", params={"resource": f"AS{m[1]}"}), await _get(f"{RIPE}/announced-prefixes/data.json", params={"resource": f"AS{m[1]}"})
    return parse_ripe_asn(rete, m[1], ov.json() if ov else {}, pf.json() if pf else {})


# --- PeeringDB (network operators: website and NOC contacts they published) ---
def parse_peeringdb(rete: str, j: dict) -> list[Finding]:
    out = []
    for n in (j.get("data") or [])[:1]:
        url = f"https://www.peeringdb.com/asn/{n.get('asn')}"
        if n.get("name"):
            out.append(Finding(("Rete", rete), "rete_di", ("Azienda", n["name"]), 0.85, "scheda PeeringDB", url=url, pivot=False))
        if host := urlparse(n.get("website") or "").hostname:
            out.append(Finding(("Rete", rete), "sito_dichiarato", ("Dominio", host.lower().removeprefix("www.")), 0.8, "sito web nella scheda PeeringDB", url=url))
        for m in sorted(set(re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", n.get("notes") or ""))):
            out.append(Finding(("Rete", rete), "contatto_noc", ("Email", m.lower()), 0.7, "contatto nelle note PeeringDB", url=url, pivot=False))
    return out


@collector("peeringdb", "Rete")
async def peeringdb(rete: str) -> list[Finding]:
    m = re.match(r"^AS(\d{1,10})\b", rete)
    r = m and await _get("https://www.peeringdb.com/api/net", params={"asn": m[1], "fields": "name,asn,website,notes"})
    return parse_peeringdb(rete, r.json()) if r else []


# --- Tranco popularity rank ---
def parse_tranco(domain: str, j: dict) -> list[Finding]:
    ranks = [r for r in j.get("ranks") or [] if r.get("rank")]
    if not ranks:
        return []
    n = ranks[0]["rank"]  # newest first
    bucket = next(f"top {b:,}" for b in (1_000, 10_000, 100_000, 1_000_000) if n <= b)
    return [Finding(("Dominio", domain), "popolarita", ("Servizio", f"Tranco {bucket}"), 0.9, f"posizione {n} nella classifica Tranco",
                    url=f"https://tranco-list.eu/query?q={domain}", raw={"rank": n}, pivot=False)]


@collector("tranco", "Dominio")
async def tranco(domain: str) -> list[Finding]:
    r = await _get(f"https://tranco-list.eu/api/ranks/domain/{domain}")
    return parse_tranco(domain, r.json()) if r and r.text.lstrip().startswith("{") else []


# --- Mozilla Observatory (the scan is run by Mozilla against the target's website) ---
def parse_observatory(domain: str, j: dict) -> list[Finding]:
    if j.get("error") or not j.get("grade"):
        return []
    return [Finding(("Dominio", domain), "valutazione_sicurezza_web", ("Servizio", f"Mozilla Observatory: {j['grade']}"), 0.9, f"intestazioni di sicurezza HTTP, punteggio {j.get('score')}",
                    url=j.get("details_url") or "", raw={"score": j.get("score")}, pivot=False)]


@collector("observatory", "Dominio", active=True)
async def observatory(domain: str) -> list[Finding]:
    async with httpx.AsyncClient(**{**HTTP, "timeout": 60}) as c:
        r = await c.post("https://observatory-api.mdn.mozilla.net/api/v2/scan", params={"host": domain})
    r.raise_for_status()
    return parse_observatory(domain, r.json())


# --- DNS blocklists (zones that answer ordinary queries; 127.255.255.x are the "query refused" codes of Spamhaus) ---
DNSBL = ("zen.spamhaus.org", "bl.spamcop.net", "all.s5h.net")


def parse_dnsbl(ip: str, zone: str, answers: list[str]) -> list[Finding]:
    codes = [a for a in answers if a.startswith("127.") and not a.startswith("127.255.255.")]
    return [Finding(("IP", ip), "in_blocklist", ("Servizio", f"DNSBL {zone}"), 0.8, f"presente in {zone}", raw={"codes": codes}, pivot=False)] if codes else []


@collector("dnsbl", "IP")
async def dnsbl(ip: str) -> list[Finding]:
    if ":" in ip:
        return []
    rev, out = ".".join(reversed(ip.split("."))), []
    for zone in DNSBL:
        try:
            ans = [r.to_text() for r in await dns.asyncresolver.resolve(f"{rev}.{zone}", "A", lifetime=6)]
        except (dns.exception.DNSException, OSError):  # NXDOMAIN = not listed; timeouts are not evidence of anything
            continue
        out += parse_dnsbl(ip, zone, ans)
    return out


# --- favicon hash (Shodan's http.favicon.hash: murmur3 of the base64 with line breaks) ---
def murmur3_32(data: bytes, seed: int = 0) -> int:
    """MurmurHash3 x86 32-bit, returned as a signed int like the mmh3 package."""
    h, n = seed, len(data) // 4 * 4
    for i in range(0, n, 4):
        k = int.from_bytes(data[i:i + 4], "little") * 0xCC9E2D51 & 0xFFFFFFFF
        k = (k << 15 | k >> 17) & 0xFFFFFFFF
        h ^= k * 0x1B873593 & 0xFFFFFFFF
        h = ((h << 13 | h >> 19) & 0xFFFFFFFF) * 5 + 0xE6546B64 & 0xFFFFFFFF
    if tail := data[n:]:
        k = int.from_bytes(tail, "little") * 0xCC9E2D51 & 0xFFFFFFFF
        k = (k << 15 | k >> 17) & 0xFFFFFFFF
        h ^= k * 0x1B873593 & 0xFFFFFFFF
    h ^= len(data)
    h = (h ^ h >> 16) * 0x85EBCA6B & 0xFFFFFFFF
    h = (h ^ h >> 13) * 0xC2B2AE35 & 0xFFFFFFFF
    h ^= h >> 16
    return h - (1 << 32) if h >= 1 << 31 else h


def favicon_hash(content: bytes) -> int:
    return murmur3_32(base64.encodebytes(content))


def find_icon(html: str, base: str) -> str:
    for tag in re.findall(r"<link\b[^>]*>", html, re.I):
        if re.search(r"rel=[\"'][^\"']*\bicon\b", tag, re.I) and (m := re.search(r"href=[\"']([^\"']+)", tag, re.I)):
            return urljoin(base, m[1])
    return urljoin(base, "/favicon.ico")


def parse_favicon(domain: str, content: bytes, url: str) -> list[Finding]:
    if not content:
        return []
    return [Finding(("Dominio", domain), "usa_tracciamento", ("ID tracciamento", f"favicon hash: {favicon_hash(content)}"), 0.9, "hash del favicon (cercabile su Shodan: http.favicon.hash)", url=url, pivot=False)]


@collector("favicon_hash", "Dominio", active=True)
async def favicon_collector(domain: str) -> list[Finding]:
    async with httpx.AsyncClient(follow_redirects=True, **HTTP) as c:
        try:
            page = await c.get(f"https://{domain}/")
            icon = find_icon(page.text[:200_000], str(page.url)) if page.status_code < 400 else f"https://{domain}/favicon.ico"
        except httpx.HTTPError:
            return []
        r = await c.get(icon)
    ok = r.status_code == 200 and 0 < len(r.content) <= 1_000_000 and "html" not in r.headers.get("content-type", "")
    return parse_favicon(domain, r.content, str(r.url)) if ok else []
