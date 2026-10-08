import dns.asyncresolver
import dns.exception
import dns.reversename
import httpx

from ..models import Finding
from . import collector
from .domain import HTTP


@collector("reverse_dns", "IP")
async def reverse_dns(ip: str) -> list[Finding]:
    try:
        answer = await dns.asyncresolver.resolve(dns.reversename.from_address(ip), "PTR", lifetime=8)
    except (dns.exception.DNSException, OSError):
        return []
    return [Finding(("IP", ip), "reverse_dns", ("Dominio", r.to_text()), 0.9, "record PTR", pivot=False) for r in answer]


@collector("internetdb", "IP")
async def internetdb(ip: str) -> list[Finding]:
    url = f"https://internetdb.shodan.io/{ip}"
    async with httpx.AsyncClient(**HTTP) as c:
        r = await c.get(url)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    j = r.json()
    out = [Finding(("IP", ip), "hostname", ("Dominio", h), 0.8, "hostname noto a Shodan", url=url, pivot=False)
           for h in j.get("hostnames", [])]
    out += [Finding(("IP", ip), "porta_aperta", ("Servizio", f"{ip}:{p}"), 0.9, "porta rilevata da Shodan", url=url,
                    pivot=False) for p in j.get("ports", [])]
    out += [Finding(("IP", ip), "vulnerabilità_nota", ("Vulnerabilità", v), 0.5, "CVE associata da Shodan (non verificata)",
                    url=url) for v in j.get("vulns", [])]
    return out


def parse_rdap_ip(ip: str, d: dict, url: str) -> list[Finding]:
    out = []
    if d.get("name"):
        out.append(Finding(("IP", ip), "parte_di_rete", ("Rete", f"{d['name']} ({d.get('handle', '?')})"), 0.9, "RDAP",
                           url=url, pivot=False))
    for ent in d.get("entities", []):
        for item in ent.get("vcardArray", [None, []])[1]:
            if item[0] == "fn" and item[3]:
                out.append(Finding(("IP", ip), "rete_di", ("Azienda", item[3]), 0.8, f"RDAP ruolo {','.join(ent.get('roles', []))}",
                                   url=url, pivot=False))
    if d.get("country"):
        out.append(Finding(("IP", ip), "registrato_in", ("Luogo", d["country"]), 0.5, "paese nel registro RDAP", url=url, pivot=False))
    return out


@collector("rdap_ip", "IP")
async def rdap_ip(ip: str) -> list[Finding]:
    async with httpx.AsyncClient(follow_redirects=True, **HTTP) as c:
        r = await c.get(f"https://rdap.org/ip/{ip}")
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return parse_rdap_ip(ip, r.json(), str(r.url))


def parse_ipwhois(ip: str, d: dict) -> list[Finding]:
    if not d.get("success"):
        return []
    url, out = f"https://ipwho.is/{ip}", []
    place = ", ".join(x for x in (d.get("city"), d.get("region"), d.get("country")) if x)
    if place:
        out.append(Finding(("IP", ip), "geolocalizzato", ("Luogo", place), 0.4, "geolocalizzazione IP (approssimativa)", url=url, pivot=False))
    c = d.get("connection") or {}
    if c.get("asn"):
        out.append(Finding(("IP", ip), "parte_di_rete", ("Rete", f"AS{c['asn']} {c.get('org', '')}".strip()), 0.8, "ASN (ipwho.is)", url=url, pivot=False))
    if c.get("org"):
        out.append(Finding(("IP", ip), "rete_di", ("Azienda", c["org"]), 0.6, "organizzazione dell'ASN", url=url, pivot=False))
    if c.get("domain"):
        out.append(Finding(("IP", ip), "dominio_provider", ("Dominio", c["domain"]), 0.5, "dominio del provider", url=url, pivot=False))
    return out


@collector("ipwhois", "IP")
async def ipwhois(ip: str) -> list[Finding]:
    async with httpx.AsyncClient(**HTTP) as c:
        r = await c.get(f"https://ipwho.is/{ip}")
    r.raise_for_status()
    return parse_ipwhois(ip, r.json())


def parse_ipinfo(ip: str, d: dict) -> list[Finding]:
    url, out = f"https://ipinfo.io/{ip}", []
    if d.get("org"):
        out.append(Finding(("IP", ip), "parte_di_rete", ("Rete", d["org"]), 0.8, "ASN (ipinfo.io)", url=url, pivot=False))
        out.append(Finding(("IP", ip), "rete_di", ("Azienda", d["org"].split(" ", 1)[-1]), 0.6, "organizzazione dell'ASN", url=url, pivot=False))
    place = ", ".join(x for x in (d.get("city"), d.get("region"), d.get("country")) if x)
    if place:
        out.append(Finding(("IP", ip), "geolocalizzato", ("Luogo", place), 0.4, "geolocalizzazione IP (approssimativa)", url=url, pivot=False))
    if d.get("hostname"):
        out.append(Finding(("IP", ip), "hostname", ("Dominio", d["hostname"]), 0.8, "hostname (ipinfo.io)", url=url, pivot=False))
    return out


@collector("ipinfo", "IP")
async def ipinfo(ip: str) -> list[Finding]:
    async with httpx.AsyncClient(**HTTP) as c:
        r = await c.get(f"https://ipinfo.io/{ip}/json")
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return parse_ipinfo(ip, r.json())


def parse_cymru(ip: str, origin: list[str], asn_name: list[str]) -> list[Finding]:
    out = []
    for rec in origin:  # "15169 | 8.8.8.0/24 | US | arin | 2023-12-28"
        f = [x.strip() for x in rec.strip('"').split("|")]
        if len(f) >= 2:
            out.append(Finding(("IP", ip), "parte_di_rete", ("Rete", f"AS{f[0]} ({f[1]})"), 0.9, "Team Cymru IP-to-ASN", pivot=False))
    for rec in asn_name:  # "15169 | US | arin | 2000-03-30 | GOOGLE, US"
        f = [x.strip() for x in rec.strip('"').split("|")]
        if len(f) >= 5:
            out.append(Finding(("IP", ip), "rete_di", ("Azienda", f[4]), 0.7, "nome ASN (Team Cymru)", pivot=False))
    return out


@collector("cymru_asn", "IP")
async def cymru_asn(ip: str) -> list[Finding]:
    if ":" in ip:  # IPv4 only
        return []
    async def txt(name):
        try:
            return [b"".join(r.strings).decode() for r in await dns.asyncresolver.resolve(name, "TXT", lifetime=8)]
        except (dns.exception.DNSException, OSError):
            return []
    origin = await txt(".".join(reversed(ip.split("."))) + ".origin.asn.cymru.com")
    asn = origin[0].split("|")[0].strip() if origin else None
    return parse_cymru(ip, origin, await txt(f"AS{asn}.asn.cymru.com") if asn else [])


@collector("reverse_ip", "IP")
async def reverse_ip(ip: str) -> list[Finding]:
    from .subdomains import HOSTNAME, hackertarget
    text = await hackertarget("reverseiplookup", ip)
    names = [n.strip().lower() for n in text.splitlines()]
    return [Finding(("IP", ip), "ospita_dominio", ("Dominio", n), 0.6, "reverse IP (HackerTarget), può essere hosting condiviso",
                    pivot=False) for n in names if HOSTNAME.match(n) and not n.endswith(".arpa")][:50]
