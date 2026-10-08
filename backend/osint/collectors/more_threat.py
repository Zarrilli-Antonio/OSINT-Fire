"""Public threat-intelligence feeds (matched locally from a cached bulk download) and vulnerability data (NVD, CISA KEV, EPSS).

Feed terms (public, free, keyless; we only answer 'is this value listed', never republish the list):
- abuse.ch Feodo Tracker / URLhaus: CC0, no attribution required.
- Spamhaus DROP: free to use; credit "The Spamhaus Project"; do not redistribute.
- blocklist.de: free; credit blocklist.de. CINS Army: free; credit cinsscore.com (Sentinel IPS).
- Emerging Threats compromised IPs: free (Proofpoint ET open rules). OpenPhish community feed: non-commercial use only.
- NVD: public domain, rate limited without key (5 req/30 s). CISA KEV: public domain. EPSS (FIRST): free, credit FIRST.org.
"""
import asyncio
import ipaddress
import json
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

from ..models import Finding
from . import collector
from .domain import HTTP

TTL = 6 * 3600
CACHE: dict[str, tuple[float, object]] = {}  # key -> (monotonic time, parsed data); tests may pre-fill or clear it
_LOCKS: dict = {}
NVD_GAP = 1.0  # seconds between NVD requests (keyless limit: 5 per 30 s per IP; serialised below)
MAX_REFS = 15


async def bulk(key: str, url: str, parse):
    """Download+parse [url] once per TTL; concurrent callers share one fetch."""
    async with _LOCKS.setdefault((key, asyncio.get_running_loop()), asyncio.Lock()):
        hit = CACHE.get(key)
        if hit and time.monotonic() - hit[0] < TTL:
            return hit[1]
        async with httpx.AsyncClient(follow_redirects=True, **{**HTTP, "timeout": 60}) as c:
            r = await c.get(url)
        r.raise_for_status()
        data = parse(r.text)
        CACHE[key] = (time.monotonic(), data)
        return data


# --- blocklists --------------------------------------------------------------------------------------------------

@dataclass
class Index:
    ips: set = field(default_factory=set)
    nets: list = field(default_factory=list)
    hosts: set = field(default_factory=set)
    info: dict = field(default_factory=dict)  # value -> extra detail (malware family, SBL id)

    def hit(self, value: str) -> str | None:
        """The listed entry matching [value] (an IP, or a CIDR containing it, or a host), else None."""
        v = value.strip().lower()
        try:
            ip = ipaddress.ip_address(v)
        except ValueError:
            return v if v in self.hosts else None
        if str(ip) in self.ips:
            return str(ip)
        return next((str(n) for n in self.nets if ip.version == n.version and ip in n), None)


def _lines(text: str):
    for l in text.splitlines():
        l = l.split("#")[0].split(";")[0].strip()
        if l:
            yield l


def _ip(s: str):
    try:
        return str(ipaddress.ip_address(s.strip()))
    except ValueError:
        return None


def parse_iplist(text: str) -> Index:
    return Index(ips={ip for l in _lines(text) if (ip := _ip(l.split()[0]))})


def parse_feodo(text: str) -> Index:
    try:
        rows = json.loads(text)
    except ValueError:
        return Index()
    rows = [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    return Index(ips={ip for r in rows if (ip := _ip(str(r.get("ip_address") or "")))},
                 info={r["ip_address"]: r.get("malware") or "" for r in rows if r.get("ip_address")})


def parse_urlhaus_hosts(text: str) -> Index:
    out = Index()
    for l in _lines(text):
        h = l.split()[-1].lower()
        (out.ips if _ip(h) else out.hosts).add(h)
    return out


def parse_drop(text: str) -> Index:
    out = Index()
    for l in text.splitlines():
        cidr, _, sbl = l.partition(";")
        try:
            n = ipaddress.ip_network(cidr.strip(), strict=False)
        except ValueError:
            continue
        out.nets.append(n)
        out.info[str(n)] = sbl.strip()
    return out


def parse_openphish(text: str) -> Index:
    out = Index()
    for l in text.splitlines():
        h = (urlparse(l.strip()).hostname or "").lower()
        if h:
            (out.ips if _ip(h) else out.hosts).add(h)
    return out


# name -> (title, url, parser, accepted entity types)
FEEDS = {
    "feodo_tracker": ("Feodo Tracker (abuse.ch)", "https://feodotracker.abuse.ch/downloads/ipblocklist.json", parse_feodo, ("IP",)),
    "urlhaus_hosts": ("URLhaus (abuse.ch)", "https://urlhaus.abuse.ch/downloads/hostfile/", parse_urlhaus_hosts, ("IP", "Dominio")),
    "spamhaus_drop": ("Spamhaus DROP", "https://www.spamhaus.org/drop/drop.txt", parse_drop, ("IP",)),  # includes the former EDROP
    "blocklist_de": ("blocklist.de", "https://lists.blocklist.de/lists/all.txt", parse_iplist, ("IP",)),
    "et_compromised": ("Emerging Threats compromised IPs", "https://rules.emergingthreats.net/blockrules/compromised-ips.txt", parse_iplist, ("IP",)),
    "cins_army": ("CINS Army", "https://cinsscore.com/list/ci-badguys.txt", parse_iplist, ("IP",)),
    "openphish": ("OpenPhish", "https://openphish.com/feed.txt", parse_openphish, ("IP", "Dominio")),
}


def feed_findings(type_: str, value: str, title: str, idx: Index, url: str = "") -> list[Finding]:
    listed = idx.hit(value)
    if not listed:
        return []
    return [Finding((type_, value), "listato_in", ("Servizio", f"feed: {title}"), 0.8, f"presente nella lista pubblica {title}",
                    url=url, raw={"entry": listed, "detail": idx.info.get(listed, "")}, pivot=False)]


def _register(name: str, title: str, url: str, parse, types: tuple):
    async def run(value: str) -> list[Finding]:
        t = "IP" if _ip(value) else "Dominio"
        return feed_findings(t, value, title, await bulk(name, url, parse), url)
    run.__name__ = name
    collector(name, *types)(run)


for _n, (_t, _u, _p, _ty) in FEEDS.items():
    _register(_n, _t, _u, _p, _ty)


# --- vulnerabilities ---------------------------------------------------------------------------------------------

CVE_RX = re.compile(r"^CVE-\d{4}-\d{4,}$")
SEV = {"CRITICAL": "critica", "HIGH": "alta", "MEDIUM": "media", "LOW": "bassa", "NONE": "nessuna"}
NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0?cveId="
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
EPSS_URL = "https://api.first.org/data/v1/epss?cve="
_nvd_lock: dict = {}


def cve_id(value: str) -> str | None:
    v = value.strip().upper()
    return v if CVE_RX.match(v) else None


def _cvss(metrics: dict) -> tuple[float, str, str] | None:
    for k in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        ms = metrics.get(k) or []
        if ms:
            m = next((x for x in ms if x.get("type") == "Primary"), ms[0])
            d = m.get("cvssData") or {}
            if "baseScore" in d:
                return float(d["baseScore"]), str(d.get("baseSeverity") or m.get("baseSeverity") or "").upper(), str(d.get("version") or "")
    return None


def parse_nvd(cve: str, data: dict) -> list[Finding]:
    vs = (data or {}).get("vulnerabilities") or []
    c = next((v.get("cve") or {} for v in vs if (v.get("cve") or {}).get("id") == cve), None)
    if not c:
        return []
    url, me, out = f"https://nvd.nist.gov/vuln/detail/{cve}", ("Vulnerabilità", cve), []
    desc = next((d["value"] for d in c.get("descriptions") or [] if d.get("lang") == "en"), "")
    if s := _cvss(c.get("metrics") or {}):
        out.append(Finding(me, "punteggio_cvss", ("Servizio", f"CVSS {s[0]}: {SEV.get(s[1], 'nessuna')}"), 0.95,
                           "punteggio CVSS pubblicato da NVD", url=url, raw={"score": s[0], "severity": s[1], "cvss": s[2], "description": desc}, pivot=False))
    if c.get("published"):
        out.append(Finding(me, "pubblicata_il", ("Data", c["published"][:10]), 0.95, "data di pubblicazione in NVD", url=url, pivot=False))
    cwes = list(dict.fromkeys(d["value"] for w in c.get("weaknesses") or [] for d in w.get("description") or [] if str(d.get("value", "")).startswith("CWE-")))
    out += [Finding(me, "debolezza", ("Servizio", w), 0.9, "debolezza (CWE) indicata in NVD", url=url, pivot=False) for w in cwes[:5]]
    refs = sorted(c.get("references") or [], key=lambda r: not ({"Vendor Advisory", "Patch"} & set(r.get("tags") or [])))
    out += [Finding(me, "riferimento", ("Documento", r["url"]), 0.9, "riferimento nella scheda NVD", url=url, raw={"tags": r.get("tags") or []}, pivot=False)
            for r in refs[:MAX_REFS] if r.get("url")]
    return out


def parse_kev(cve: str, catalog: dict) -> list[Finding]:
    e = catalog.get(cve) if isinstance(catalog, dict) else None
    if not e:
        return []
    me, url = ("Vulnerabilità", cve), "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"
    why = "presente nel catalogo CISA Known Exploited Vulnerabilities"
    out = [Finding(me, "stato_sfruttamento", ("Servizio", "sfruttata attivamente (CISA KEV)"), 0.95, why, url=url,
                   raw={"name": e.get("vulnerabilityName"), "required_action": e.get("requiredAction"), "due": e.get("dueDate")}, pivot=False)]
    if prod := " ".join(x for x in (e.get("vendorProject"), e.get("product")) if x):
        out.append(Finding(me, "colpisce_prodotto", ("Servizio", prod), 0.95, "prodotto indicato nel catalogo CISA KEV", url=url, pivot=False))
    if e.get("dateAdded"):
        out.append(Finding(me, "aggiunta_al_catalogo_il", ("Data", e["dateAdded"]), 0.95, why, url=url, pivot=False))
    if e.get("knownRansomwareCampaignUse") == "Known":
        out.append(Finding(me, "stato_sfruttamento", ("Servizio", "usata in campagne ransomware (CISA KEV)"), 0.9, why, url=url, pivot=False))
    out += [Finding(me, "riferimento", ("Documento", u), 0.85, "riferimento nel catalogo CISA KEV", url=url, pivot=False)
            for u in re.findall(r"https?://[^\s;]+", e.get("notes") or "")[:5]]
    return out


def parse_kev_catalog(text: str) -> dict:
    try:
        return {v["cveID"]: v for v in json.loads(text).get("vulnerabilities", []) if v.get("cveID")}
    except (ValueError, AttributeError, TypeError, KeyError):
        return {}


def parse_epss(cve: str, data: dict) -> list[Finding]:
    row = next((r for r in (data or {}).get("data") or [] if str(r.get("cve", "")).upper() == cve), None)
    try:
        p, pc = float(row["epss"]) * 100, float(row["percentile"]) * 100
    except (TypeError, KeyError, ValueError):
        return []
    return [Finding(("Vulnerabilità", cve), "probabilità_sfruttamento", ("Servizio", f"EPSS {p:.2f}% (percentile {pc:.1f})"), 0.9,
                    "probabilità di sfruttamento stimata da EPSS (FIRST)", url=f"https://api.first.org/data/v1/epss?cve={cve}",
                    raw={"epss": row["epss"], "percentile": row["percentile"], "date": row.get("date")}, pivot=False)]


@collector("nvd", "Vulnerabilità")
async def nvd(value: str) -> list[Finding]:
    if not (cve := cve_id(value)):
        return []
    async with _nvd_lock.setdefault(asyncio.get_running_loop(), asyncio.Lock()):  # serialised: keyless rate limit
        try:
            async with httpx.AsyncClient(**HTTP) as c:
                r = await c.get(NVD_URL + cve)
        finally:
            await asyncio.sleep(NVD_GAP)
    if r.status_code == 404:
        return []
    r.raise_for_status()  # 403/429 = rate limited: reported by the runner
    return parse_nvd(cve, r.json())


@collector("cisa_kev", "Vulnerabilità")
async def cisa_kev(value: str) -> list[Finding]:
    return parse_kev(cve, await bulk("cisa_kev", KEV_URL, parse_kev_catalog)) if (cve := cve_id(value)) else []


@collector("epss", "Vulnerabilità")
async def epss(value: str) -> list[Finding]:
    if not (cve := cve_id(value)):
        return []
    async with httpx.AsyncClient(**HTTP) as c:
        r = await c.get(EPSS_URL + cve)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return parse_epss(cve, r.json())
