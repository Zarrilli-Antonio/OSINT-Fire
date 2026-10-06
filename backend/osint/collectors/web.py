import json
import re
from urllib.parse import unquote, urlparse

import httpx

from ..models import Finding
from . import collector
from .domain import HTTP, MAX_SUBDOMAINS

MAX_HTML = 1_000_000
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")
SOCIAL = re.compile(
    r"""href=["'](https?://(?:www\.)?(?:github\.com|twitter\.com|x\.com|instagram\.com|facebook\.com|youtube\.com|t\.me|"""
    r"""linkedin\.com/(?:company|in)|mastodon\.social)/@?[A-Za-z0-9_.-]+)/?["']""", re.I)
PLACEHOLDER_DOMAINS = {"domain.com", "example.com", "example.org", "email.com", "yourdomain.com", "company.com"}
ASSET_EXT = IMG_EXT + (".ico", ".css", ".js", ".json", ".xml")
NOT_PROFILE = {"share", "intent", "sharer", "login", "home", "tweet", "hashtag", "search"}


def parse_page(domain: str, html: str, headers: dict, url: str) -> list[Finding]:
    me = ("Dominio", domain)
    out = []
    real = lambda e: e.split("@")[-1] not in PLACEHOLDER_DOMAINS  # noqa: E731  (template/placeholder addresses)
    emails = {m.lower().rstrip(".") for m in re.findall(r"mailto:([^\"'?>\s]+)", html, flags=re.I) if "@" in m}
    emails = {e for e in emails if real(e)}
    plain = {m.lower() for m in EMAIL.findall(html) if not m.lower().endswith(IMG_EXT)} - emails
    plain = {e for e in plain if real(e)}
    for e, conf, why in [(e, 0.75, "mailto nella home page") for e in sorted(emails)] + \
                        [(e, 0.55, "indirizzo nel testo della home page") for e in sorted(plain)[:20]]:
        out.append(Finding(me, "email_sul_sito", ("Email", e), conf, why, url=url))
    seen = set()
    for link in SOCIAL.findall(html):
        last = urlparse(link).path.strip("/").split("/")[-1].lower()
        if link.lower() in seen or last in NOT_PROFILE or last.endswith(ASSET_EXT):
            continue
        seen.add(link.lower())
        out.append(Finding(me, "profilo_social", ("Account", link), 0.6, "link a profilo social nella home page", url=url,
                           pivot=False))
    if m := re.search(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)', html, re.I):
        out.append(Finding(me, "tecnologia", ("Tecnologia", m.group(1).strip()), 0.8, "meta generator", url=url, pivot=False))
    if server := headers.get("server"):
        out.append(Finding(me, "tecnologia", ("Tecnologia", server.strip()), 0.8, "header HTTP Server", url=url, pivot=False))
    return out


def _ld_nodes(data):
    """Yield every dict in a JSON-LD document (handles @graph and nesting)."""
    if isinstance(data, list):
        for x in data:
            yield from _ld_nodes(x)
    elif isinstance(data, dict):
        yield data
        for v in data.values():
            if isinstance(v, (dict, list)):
                yield from _ld_nodes(v)


def parse_extras(domain: str, html: str, url: str) -> list[Finding]:
    """tel: links, schema.org JSON-LD (organisation, phone, address, sameAs profiles), twitter:site."""
    me, out = ("Dominio", domain), []
    for t in {unquote(m).strip() for m in re.findall(r"href=[\"']tel:([^\"']+)", html, flags=re.I)}:
        out.append(Finding(me, "telefono_sul_sito", ("Telefono", t), 0.75, "link tel: nella home page", url=url))
    if m := re.search(r'<meta[^>]+name=["\']twitter:site["\'][^>]+content=["\']@?([A-Za-z0-9_]{1,15})', html, re.I):
        out.append(Finding(me, "profilo_social", ("Account", f"https://twitter.com/{m.group(1)}"), 0.7, "meta twitter:site", url=url, pivot=False))
    for blob in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, flags=re.S | re.I):
        try:
            data = json.loads(blob)
        except ValueError:
            continue
        for n in _ld_nodes(data):
            kind = str(n.get("@type", ""))
            if not any(k in kind for k in ("Organization", "LocalBusiness", "Corporation", "Person", "Store", "Restaurant")):
                continue
            if isinstance(n.get("name"), str):
                out.append(Finding(me, "nome_organizzazione", ("Persona" if "Person" in kind else "Azienda", n["name"]), 0.7,
                                   "dati strutturati schema.org", url=url, pivot=False))
            if isinstance(n.get("telephone"), str):
                out.append(Finding(me, "telefono_sul_sito", ("Telefono", n["telephone"]), 0.8, "schema.org telephone", url=url))
            if isinstance(n.get("email"), str) and "@" in n["email"]:
                out.append(Finding(me, "email_sul_sito", ("Email", n["email"].removeprefix("mailto:").lower()), 0.8, "schema.org email", url=url))
            same = n.get("sameAs", [])
            for link in [same] if isinstance(same, str) else same:
                if isinstance(link, str) and link.startswith("http"):
                    out.append(Finding(me, "profilo_social", ("Account", link), 0.8, "schema.org sameAs", url=url, pivot=False))
            addr = n.get("address")
            if isinstance(addr, dict):
                place = ", ".join(str(addr[k]) for k in ("streetAddress", "postalCode", "addressLocality", "addressRegion", "addressCountry")
                                  if isinstance(addr.get(k), (str, int)))
                if place:
                    out.append(Finding(me, "sede", ("Luogo", place), 0.75, "indirizzo schema.org", url=url, pivot=False))
    return out


def parse_humans(domain: str, text: str, url: str) -> list[Finding]:
    out = [Finding(("Dominio", domain), "email_sul_sito", ("Email", e.lower()), 0.6, "humans.txt", url=url)
           for e in sorted(set(EMAIL.findall(text))) if e.split("@")[-1].lower() not in PLACEHOLDER_DOMAINS][:20]
    out += [Finding(("Dominio", domain), "profilo_social", ("Account", f"https://twitter.com/{h}"), 0.5, "handle in humans.txt", url=url, pivot=False)
            for h in sorted(set(re.findall(r"(?:twitter|x)\s*:?\s*@([A-Za-z0-9_]{1,15})", text, flags=re.I)))]
    return out


def parse_security_txt(domain: str, text: str, url: str) -> list[Finding]:
    return [Finding(("Dominio", domain), "contatto_sicurezza", ("Email", m.lower()), 0.85, "security.txt", url=url)
            for m in re.findall(r"^Contact:\s*mailto:([^\s]+)", text, flags=re.I | re.M)]


@collector("web_page", "Dominio", active=True)
async def web_page(domain: str) -> list[Finding]:
    out = []
    async with httpx.AsyncClient(follow_redirects=True, **HTTP) as c:
        try:
            r = await c.get(f"https://{domain}")
            if "text/html" in r.headers.get("content-type", ""):
                out += parse_page(domain, r.text[:MAX_HTML], dict(r.headers), str(r.url))
                out += parse_extras(domain, r.text[:MAX_HTML], str(r.url))
        except httpx.HTTPError:
            pass  # many domains have no website
        try:
            h = await c.get(f"https://{domain}/humans.txt")
            if h.status_code == 200 and "text/plain" in h.headers.get("content-type", ""):
                out += parse_humans(domain, h.text[:50_000], str(h.url))
        except httpx.HTTPError:
            pass
        try:
            s = await c.get(f"https://{domain}/.well-known/security.txt")
            if s.status_code == 200 and "text/plain" in s.headers.get("content-type", ""):
                out += parse_security_txt(domain, s.text[:50_000], str(s.url))
        except httpx.HTTPError:
            pass
    return out


@collector("urlscan", "Dominio")
async def urlscan(domain: str) -> list[Finding]:
    url = f"https://urlscan.io/api/v1/search/?q=domain:{domain}&size=100"
    async with httpx.AsyncClient(**HTTP) as c:
        r = await c.get(url)
    r.raise_for_status()
    out, subs = [], {}
    for res in r.json().get("results", []):
        page = res.get("page", {})
        host = (page.get("domain") or "").lower()
        if host.endswith("." + domain) and len(subs) < MAX_SUBDOMAINS:
            subs.setdefault(host, page.get("ip"))
    for host, ip in sorted(subs.items()):
        out.append(Finding(("Dominio", domain), "sottodominio", ("Dominio", host), 0.7, "scansione pubblica su urlscan.io", url=url))
        if ip:
            out.append(Finding(("Dominio", host), "risolve_a", ("IP", ip), 0.6, "IP rilevato da urlscan.io", url=url, pivot=False))
    return out
