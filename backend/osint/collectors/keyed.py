"""Sources that need a (usually free-tier) API key. Inactive until the key is set in Settings."""
import httpx

from ..models import Finding
from ..settings import CFG
from . import collector
from .domain import HTTP

MAX = 100


def client(extra: dict) -> httpx.AsyncClient:
    return httpx.AsyncClient(**{**HTTP, "headers": {**HTTP["headers"], **extra}})


# ---------------- VirusTotal ----------------

def parse_vt_domain(domain: str, info: dict, subs: dict, res: dict) -> list[Finding]:
    me, url, out = ("Dominio", domain), f"https://www.virustotal.com/gui/domain/{domain}", []
    a = (info.get("data") or {}).get("attributes", {})
    if (mal := (a.get("last_analysis_stats") or {}).get("malicious")) is not None:
        out.append(Finding(me, "reputazione", ("Servizio", f"VirusTotal: {mal} motori lo segnalano come malevolo"), 0.8, "analisi VirusTotal", url=url, pivot=False))
    if a.get("registrar"):
        out.append(Finding(me, "registrar", ("Azienda", a["registrar"]), 0.8, "registrar secondo VirusTotal", url=url, pivot=False))
    for cat in sorted(set((a.get("categories") or {}).values()))[:5]:
        out.append(Finding(me, "categoria", ("Servizio", f"categoria: {cat}"), 0.6, "classificazione VirusTotal", url=url, pivot=False))
    for s in subs.get("data", [])[:MAX]:
        out.append(Finding(me, "sottodominio", ("Dominio", s["id"].lower()), 0.8, "sottodominio noto a VirusTotal", url=url))
    for r in res.get("data", [])[:30]:
        if ip := r.get("attributes", {}).get("ip_address"):
            out.append(Finding(me, "risolve_a", ("IP", ip), 0.7, "risoluzione storica (VirusTotal)", url=url, pivot=False))
    return out


@collector("virustotal_domain", "Dominio", key="virustotal_key")
async def virustotal_domain(domain: str) -> list[Finding]:
    base = f"https://www.virustotal.com/api/v3/domains/{domain}"
    async with client({"x-apikey": CFG["virustotal_key"]}) as c:
        info = await c.get(base)
        if info.status_code == 404:
            return []
        info.raise_for_status()
        subs = await c.get(base + "/subdomains", params={"limit": 40})
        res = await c.get(base + "/resolutions", params={"limit": 20})
    return parse_vt_domain(domain, info.json(), subs.json() if subs.status_code == 200 else {}, res.json() if res.status_code == 200 else {})


def parse_vt_ip(ip: str, info: dict, res: dict) -> list[Finding]:
    me, url, out = ("IP", ip), f"https://www.virustotal.com/gui/ip-address/{ip}", []
    a = (info.get("data") or {}).get("attributes", {})
    if (mal := (a.get("last_analysis_stats") or {}).get("malicious")) is not None:
        out.append(Finding(me, "reputazione", ("Servizio", f"VirusTotal: {mal} motori lo segnalano come malevolo"), 0.8, "analisi VirusTotal", url=url, pivot=False))
    if a.get("as_owner"):
        out.append(Finding(me, "rete_di", ("Azienda", a["as_owner"]), 0.7, "proprietario ASN (VirusTotal)", url=url, pivot=False))
    if a.get("country"):
        out.append(Finding(me, "paese", ("Luogo", a["country"]), 0.6, "paese secondo VirusTotal", url=url, pivot=False))
    for r in res.get("data", [])[:MAX]:
        if h := r.get("attributes", {}).get("host_name"):
            out.append(Finding(me, "dominio_ospitato", ("Dominio", h.lower()), 0.6, "risoluzione storica (VirusTotal)", url=url, pivot=False))
    return out


@collector("virustotal_ip", "IP", key="virustotal_key")
async def virustotal_ip(ip: str) -> list[Finding]:
    base = f"https://www.virustotal.com/api/v3/ip_addresses/{ip}"
    async with client({"x-apikey": CFG["virustotal_key"]}) as c:
        info = await c.get(base)
        if info.status_code == 404:
            return []
        info.raise_for_status()
        res = await c.get(base + "/resolutions", params={"limit": 40})
    return parse_vt_ip(ip, info.json(), res.json() if res.status_code == 200 else {})


# ---------------- Shodan ----------------

def parse_shodan(ip: str, d: dict) -> list[Finding]:
    me, url, out = ("IP", ip), f"https://www.shodan.io/host/{ip}", []
    if d.get("org"):
        out.append(Finding(me, "rete_di", ("Azienda", d["org"]), 0.75, "organizzazione secondo Shodan", url=url, pivot=False))
    if d.get("city") or d.get("country_name"):
        out.append(Finding(me, "geolocalizzato", ("Luogo", ", ".join(x for x in (d.get("city"), d.get("country_name")) if x)), 0.4,
                           "geolocalizzazione Shodan (approssimativa)", url=url, pivot=False))
    for h in d.get("hostnames", []):
        out.append(Finding(me, "hostname", ("Dominio", h.lower()), 0.8, "hostname noto a Shodan", url=url, pivot=False))
    for dom in d.get("domains", []):
        out.append(Finding(me, "dominio_associato", ("Dominio", dom.lower()), 0.6, "dominio noto a Shodan", url=url, pivot=False))
    for banner in d.get("data", [])[:30]:
        prod = " ".join(x for x in (banner.get("product"), banner.get("version")) if x)
        label = f"{banner.get('port')}/{banner.get('transport', 'tcp')}" + (f" {prod}" if prod else "")
        out.append(Finding(me, "servizio_esposto", ("Servizio", label), 0.9, "banner raccolto da Shodan", url=url, pivot=False))
    for v in list(d.get("vulns", []))[:30]:
        out.append(Finding(me, "vulnerabilità_nota", ("Vulnerabilità", v), 0.5, "CVE associata da Shodan (non verificata)", url=url))
    return out


@collector("shodan_host", "IP", key="shodan_key")
async def shodan_host(ip: str) -> list[Finding]:
    async with client({}) as c:
        r = await c.get(f"https://api.shodan.io/shodan/host/{ip}", params={"key": CFG["shodan_key"]})
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return parse_shodan(ip, r.json())


# ---------------- Hunter ----------------

def parse_hunter(domain: str, j: dict) -> list[Finding]:
    d, me, url, out = j.get("data") or {}, ("Dominio", domain), f"https://hunter.io/search/{domain}", []
    if d.get("organization"):
        out.append(Finding(me, "organizzazione", ("Azienda", d["organization"]), 0.7, "Hunter.io", url=url, pivot=False))
    if d.get("pattern"):
        out.append(Finding(me, "formato_email", ("Servizio", f"formato email: {d['pattern']}@{domain}"), 0.8, "pattern rilevato da Hunter.io", url=url, pivot=False))
    for e in d.get("emails", [])[:MAX]:
        conf = min(0.9, 0.5 + (e.get("confidence", 0) or 0) / 250)
        out.append(Finding(me, "email_trovata", ("Email", e["value"].lower()), conf, f"Hunter.io{', ' + e['position'] if e.get('position') else ''}", url=url))
        name = " ".join(x for x in (e.get("first_name"), e.get("last_name")) if x)
        if name:
            out.append(Finding(("Email", e["value"].lower()), "intestata_a", ("Persona", name), 0.6, "nome associato da Hunter.io", url=url, pivot=False))
    return out


@collector("hunter_domain", "Dominio", key="hunter_key")
async def hunter_domain(domain: str) -> list[Finding]:
    async with client({}) as c:
        r = await c.get("https://api.hunter.io/v2/domain-search", params={"domain": domain, "api_key": CFG["hunter_key"], "limit": 50})
    if r.status_code in (400, 404):
        return []
    r.raise_for_status()
    return parse_hunter(domain, r.json())


# ---------------- Have I Been Pwned ----------------

def parse_hibp(email: str, breaches: list) -> list[Finding]:
    return [Finding(("Email", email), "presente_in_breach", ("Breach", b["Name"]), 0.9,
                    f"HIBP, {b.get('BreachDate', '?')}, dati esposti: {', '.join(b.get('DataClasses', [])[:6])}",
                    url=f"https://haveibeenpwned.com/PwnedWebsites#{b['Name']}", pivot=False) for b in breaches]


@collector("hibp", "Email", key="hibp_key")
async def hibp(email: str) -> list[Finding]:
    async with client({"hibp-api-key": CFG["hibp_key"]}) as c:
        r = await c.get(f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}", params={"truncateResponse": "false"})
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return parse_hibp(email, r.json())


# ---------------- SecurityTrails ----------------

def parse_securitytrails(domain: str, j: dict) -> list[Finding]:
    return [Finding(("Dominio", domain), "sottodominio", ("Dominio", f"{s}.{domain}".lower()), 0.85, "SecurityTrails",
                    url=f"https://securitytrails.com/domain/{domain}/dns") for s in j.get("subdomains", [])[:MAX * 3]]


@collector("securitytrails", "Dominio", key="securitytrails_key")
async def securitytrails(domain: str) -> list[Finding]:
    async with client({"APIKEY": CFG["securitytrails_key"]}) as c:
        r = await c.get(f"https://api.securitytrails.com/v1/domain/{domain}/subdomains", params={"children_only": "false"})
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return parse_securitytrails(domain, r.json())


# ---------------- AbuseIPDB ----------------

def parse_abuseipdb(ip: str, j: dict) -> list[Finding]:
    d, me, url, out = j.get("data") or {}, ("IP", ip), f"https://www.abuseipdb.com/check/{ip}", []
    out.append(Finding(me, "reputazione", ("Servizio", f"AbuseIPDB: punteggio {d.get('abuseConfidenceScore', 0)}%, {d.get('totalReports', 0)} segnalazioni"),
                       0.8, "AbuseIPDB (ultimi 90 giorni)", url=url, pivot=False))
    if d.get("isp"):
        out.append(Finding(me, "rete_di", ("Azienda", d["isp"]), 0.7, "ISP secondo AbuseIPDB", url=url, pivot=False))
    if d.get("domain"):
        out.append(Finding(me, "dominio_provider", ("Dominio", d["domain"].lower()), 0.5, "dominio dell'ISP", url=url, pivot=False))
    if d.get("countryCode"):
        out.append(Finding(me, "paese", ("Luogo", d["countryCode"]), 0.6, "paese secondo AbuseIPDB", url=url, pivot=False))
    if d.get("usageType"):
        out.append(Finding(me, "tipo_uso", ("Servizio", f"uso: {d['usageType']}"), 0.7, "AbuseIPDB", url=url, pivot=False))
    if d.get("isTor"):
        out.append(Finding(me, "anonimizzatore", ("Servizio", "nodo Tor"), 0.9, "AbuseIPDB", url=url, pivot=False))
    return out


@collector("abuseipdb", "IP", key="abuseipdb_key")
async def abuseipdb(ip: str) -> list[Finding]:
    async with client({"Key": CFG["abuseipdb_key"], "Accept": "application/json"}) as c:
        r = await c.get("https://api.abuseipdb.com/api/v2/check", params={"ipAddress": ip, "maxAgeInDays": 90})
    r.raise_for_status()
    return parse_abuseipdb(ip, r.json())
