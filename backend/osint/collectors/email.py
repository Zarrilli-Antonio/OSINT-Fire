import hashlib

import httpx

from ..models import Finding
from ..settings import CFG, is_ignored_domain
from ..images import phash_url
from . import collector
from .domain import HTTP


@collector("email_domain", "Email")
async def email_domain(email: str) -> list[Finding]:
    domain = email.split("@", 1)[1]
    if is_ignored_domain(domain):  # gmail.com & co: record the provider, do not create a domain to trace
        return [Finding(("Email", email), "provider_email", ("Servizio", f"provider email pubblico: {domain}"), 1.0, "dominio nell'elenco dei provider pubblici", pivot=False)]
    return [Finding(("Email", email), "dominio_email", ("Dominio", domain), 1.0, "parte dopo @")]


@collector("gravatar", "Email")
async def gravatar(email: str) -> list[Finding]:
    h = hashlib.sha256(email.encode()).hexdigest()
    url = f"https://gravatar.com/{h}.json"
    out = []
    async with httpx.AsyncClient(follow_redirects=True, **HTTP) as c:
        avatar = f"https://gravatar.com/avatar/{h}?d=404&s=256"
        if ph := await phash_url(c, avatar):
            out.append(Finding(("Email", email), "immagine_profilo", ("Immagine", ph[0]), 0.9, "avatar Gravatar", url=avatar,
                               raw={"thumb": ph[1]}, pivot=False))
        r = await c.get(url)
    if r.status_code == 404:
        return out
    r.raise_for_status()
    e = r.json()["entry"][0]
    if e.get("preferredUsername"):
        out.append(Finding(("Email", email), "usa_username", ("Username", e["preferredUsername"]), 0.85,
                           "profilo Gravatar", url=url))
    if e.get("displayName"):
        out.append(Finding(("Email", email), "intestata_a", ("Persona", e["displayName"]), 0.6,
                           "nome nel profilo Gravatar", url=url))
    for a in e.get("accounts", []):
        out.append(Finding(("Email", email), "account", ("Account", a["url"]), 0.85,
                           f"collegato in Gravatar ({a.get('shortname', '')})", url=url))
    return out


@collector("xposedornot", "Email")
async def xposedornot(email: str) -> list[Finding]:
    url = f"https://api.xposedornot.com/v1/check-email/{email}"
    async with httpx.AsyncClient(**HTTP) as c:
        r = await c.get(url)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    # indicators only: breach names, never the leaked data
    names = [b for group in r.json().get("breaches", []) for b in group]
    return [Finding(("Email", email), "presente_in_breach", ("Breach", b), 0.7, "indicata in database di breach pubblico",
                    url=url, pivot=False) for b in names]


@collector("leakcheck", "Email")
async def leakcheck(email: str) -> list[Finding]:
    url = "https://leakcheck.io/api/public"
    async with httpx.AsyncClient(**HTTP) as c:
        r = await c.get(url, params={"check": email})
    r.raise_for_status()
    j = r.json()
    if not j.get("success"):
        return []
    # public endpoint: only source names and dates, never the leaked data
    return [Finding(("Email", email), "presente_in_breach", ("Breach", s["name"]), 0.65, "LeakCheck, database pubblico di breach",
                    url=url, raw={"date": s.get("date")}, pivot=False) for s in j.get("sources", [])]


ROLE_LOCALS = {"info", "admin", "administrator", "contact", "contatti", "support", "sales", "noreply", "no-reply", "donotreply", "hello",
               "mail", "office", "webmaster", "postmaster", "hostmaster", "security", "abuse", "root", "dmarc", "privacy", "legal",
               "billing", "team", "press", "jobs", "hr", "help", "marketing", "ufficio", "segreteria", "amministrazione", "dns", "noc"}


def local_part_username(email: str) -> str | None:
    local = email.split("@")[0].split("+")[0].lower()
    return local if len(local) >= 3 and local not in ROLE_LOCALS and not local.isdigit() else None


def distinctive(handle: str) -> bool:
    """Personal-looking handle (mario.rossi, m_rossi84): short common words like 'john' match thousands of strangers."""
    return len(handle) >= 6 or any(c in handle for c in "._-") or (any(c.isdigit() for c in handle) and len(handle) >= 4)


@collector("email_username", "Email")
async def email_username(email: str) -> list[Finding]:
    """The part before @ as a candidate username. Followed (social scan) only if the setting is on and the handle is distinctive;
    otherwise it stays a node you can expand by hand."""
    u = local_part_username(email)
    if not u:
        return []
    follow = CFG["auto_username_from_email"] and distinctive(u)
    return [Finding(("Email", email), "possibile_username", ("Username", u), 0.4, "parte locale dell'indirizzo", pivot=follow)]


@collector("libravatar", "Email")
async def libravatar(email: str) -> list[Finding]:
    url = f"https://seccdn.libravatar.org/avatar/{hashlib.sha256(email.encode()).hexdigest()}?d=404&s=256"
    async with httpx.AsyncClient(follow_redirects=True, **HTTP) as c:
        ph = await phash_url(c, url)
    return [Finding(("Email", email), "immagine_profilo", ("Immagine", ph[0]), 0.85, "avatar Libravatar", url=url, raw={"thumb": ph[1]},
                    pivot=False)] if ph else []


_disposable = {"ts": 0.0, "domains": set()}
DISPOSABLE_URL = "https://raw.githubusercontent.com/disposable-email-domains/disposable-email-domains/main/disposable_email_blocklist.conf"


def validity_findings(email: str, has_mx: bool, disposable: bool) -> list[Finding]:
    me, out = ("Email", email), []
    if disposable:
        out.append(Finding(me, "tipo_indirizzo", ("Servizio", "dominio di posta usa-e-getta"), 0.9, "elenco pubblico di domini temporanei", pivot=False))
    if not has_mx:
        out.append(Finding(me, "validita", ("Servizio", "il dominio non riceve posta (nessun MX)"), 0.85, "nessun record MX/A", pivot=False))
    return out


@collector("email_validity", "Email")
async def email_validity(email: str) -> list[Finding]:
    import time

    import dns.asyncresolver
    import dns.exception
    domain = email.split("@", 1)[1]
    if time.time() - _disposable["ts"] > 24 * 3600:
        async with httpx.AsyncClient(**HTTP) as c:
            r = await c.get(DISPOSABLE_URL)
        if r.status_code == 200:
            _disposable.update(ts=time.time(), domains={x.strip().lower() for x in r.text.splitlines() if x.strip() and not x.startswith("#")})
    has_mx = False
    for rtype in ("MX", "A"):
        try:
            await dns.asyncresolver.resolve(domain, rtype, lifetime=8)
            has_mx = True
            break
        except (dns.exception.DNSException, OSError):
            continue
    return validity_findings(email, has_mx, domain in _disposable["domains"])
