"""More keyless sources: package registries, blogs, game profiles, GitHub organisations, Tor exit list, Wikipedia."""
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote, urlparse

import httpx

from ..models import Finding
from . import collector
from .domain import HTTP
from .github import API, gh_client
from .profiles import Profile, host, profile_findings, text
from .social_html import make

FORGES = {"github.com", "gitlab.com", "bitbucket.org", "rubygems.org", "codeberg.org", "sourceforge.net"}


def parse_steam(username: str, page: str) -> Profile | None:
    try:
        root = ET.fromstring(page)
    except ET.ParseError:
        return None
    if root.tag != "profile":  # <response><error> for unknown vanity names
        return None
    g = lambda tag: (root.findtext(tag) or "").strip()  # noqa: E731
    return Profile(f"https://steamcommunity.com/id/{username}", g("realname"), g("location"), avatar=g("avatarFull"), bio=text(g("summary")), conf=0.8)


def parse_medium(username: str, page: str) -> Profile | None:
    try:
        ch = ET.fromstring(page).find("channel")
    except ET.ParseError:
        return None
    if ch is None:
        return None
    m = re.match(r"Stories by (.+) on Medium", ch.findtext("title") or "")
    return Profile(f"https://medium.com/@{username}", m.group(1) if m else "", avatar=ch.findtext("image/url") or "", bio=text(ch.findtext("description")))


collector("steam", "Username")(make("steam", lambda u: f"https://steamcommunity.com/id/{u}?xml=1", parse_steam))
collector("medium", "Username")(make("medium", lambda u: f"https://medium.com/feed/@{u}", parse_medium))


def parse_rubygems(username: str, gems: list) -> list[Finding]:
    me, out = ("Username", username), []
    for g in gems[:30]:
        url = f"https://rubygems.org/gems/{g['name']}"
        out.append(Finding(me, "pubblica_pacchetto", ("Servizio", f"gem: {g['name']}"), 0.85, "gem Ruby di cui è owner", url=url, pivot=False))
        for key in ("homepage_uri", "source_code_uri"):
            h = host(g.get(key) or "")
            if h and h not in FORGES:
                out.append(Finding(me, "sito_nel_pacchetto", ("Dominio", h), 0.6, f"{key} di un suo pacchetto", url=url))
        for a in str(g.get("authors") or "").split(","):
            if len(a.strip()) > 3:
                out.append(Finding(me, "autore_nel_pacchetto", ("Persona", a.strip()), 0.4, "campo authors di un suo pacchetto", url=url, pivot=False))
    return out


@collector("rubygems", "Username")
async def rubygems(username: str) -> list[Finding]:
    async with httpx.AsyncClient(**HTTP) as c:
        r = await c.get(f"https://rubygems.org/api/v1/owners/{username}/gems.json")
    if r.status_code in (403, 404):
        return []
    r.raise_for_status()
    return parse_rubygems(username, r.json())


def slugs(name: str) -> list[str]:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return list(dict.fromkeys([base, base.replace("-", "")])) if base else []


def norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def parse_org(name: str, org: dict, members: list) -> list[Finding]:
    """Only accept an org whose login or display name equals the searched name (a slug guess alone is not enough)."""
    if norm_name(org.get("login", "")) != norm_name(name) and norm_name(org.get("name") or "") != norm_name(name):
        return []
    me, acc, url = ("Azienda", name), ("Account", org["html_url"]), org["html_url"]
    out = [Finding(me, "organizzazione_github", acc, 0.6, "organizzazione GitHub con lo stesso nome", url=url, pivot=False)]
    if h := host(org.get("blog") or ""):
        out.append(Finding(acc, "sito_dichiarato", ("Dominio", h), 0.7, "campo blog dell'organizzazione", url=url))
    if org.get("location"):
        out.append(Finding(acc, "luogo_dichiarato", ("Luogo", org["location"]), 0.5, "campo location dell'organizzazione", url=url, pivot=False))
    if org.get("email"):
        out.append(Finding(acc, "email_pubblica", ("Email", org["email"].lower()), 0.7, "email dell'organizzazione", url=url))
    if org.get("twitter_username"):
        out.append(Finding(acc, "profilo_social", ("Account", f"https://twitter.com/{org['twitter_username']}"), 0.7, "campo twitter dell'organizzazione", url=url, pivot=False))
    for m in members[:30]:
        out.append(Finding(acc, "membro_pubblico", ("Username", m["login"]), 0.5, "membro pubblico dell'organizzazione", url=url, pivot=False))
    return out


@collector("github_org", "Azienda")
async def github_org(name: str) -> list[Finding]:
    async with gh_client() as c:
        for slug in slugs(name):
            r = await c.get(f"{API}/orgs/{slug}")
            if r.status_code == 404:
                continue
            r.raise_for_status()
            org = r.json()
            mem = await c.get(f"{API}/orgs/{org['login']}/members", params={"per_page": 30})
            if out := parse_org(name, org, mem.json() if mem.status_code == 200 else []):
                return out
    return []


_tor = {"ts": 0.0, "ips": set()}


@collector("tor_exit", "IP")
async def tor_exit(ip: str) -> list[Finding]:
    if time.time() - _tor["ts"] > 3600:
        async with httpx.AsyncClient(**HTTP) as c:
            r = await c.get("https://check.torproject.org/torbulkexitlist")
        r.raise_for_status()
        _tor.update(ts=time.time(), ips=set(r.text.split()))
    return [Finding(("IP", ip), "anonimizzatore", ("Servizio", "nodo di uscita Tor"), 0.95, "elenco ufficiale dei nodi di uscita Tor",
                    url="https://check.torproject.org/torbulkexitlist", pivot=False)] if ip in _tor["ips"] else []


def parse_wikipedia(kind: str, name: str, lang: str, j: dict) -> list[Finding]:
    if j.get("type") != "standard":  # disambiguation pages and the like say nothing about this entity
        return []
    url = (j.get("content_urls") or {}).get("desktop", {}).get("page", "")
    exact = j.get("title", "").lower() == name.lower()
    desc = j.get("description") or text(j.get("extract"))[:120]
    return [Finding((kind, name), "voce_wikipedia", ("Wikipedia", f"{j['title']} ({lang}.wikipedia) — {desc}"), 0.6 if exact else 0.4,
                    "voce enciclopedica con questo titolo (omonimi possibili)", url=url, raw={"extract": text(j.get("extract"))[:400]}, pivot=False)]


async def _wikipedia(kind: str, name: str) -> list[Finding]:
    out = []
    async with httpx.AsyncClient(follow_redirects=True, **HTTP) as c:
        for lang in ("it", "en"):
            r = await c.get(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(name.replace(' ', '_'))}")
            if r.status_code == 200:
                out += parse_wikipedia(kind, name, lang, r.json())
    return out


@collector("wikipedia", "Persona")
async def wikipedia_person(name: str) -> list[Finding]:
    return await _wikipedia("Persona", name)


@collector("wikipedia", "Azienda")
async def wikipedia_company(name: str) -> list[Finding]:
    return await _wikipedia("Azienda", name)


def parse_roblox(username: str, lookup: dict, user: dict) -> list[Finding]:
    d = (lookup.get("data") or [None])[0]
    if not d:
        return []
    url = f"https://www.roblox.com/users/{d['id']}/profile"
    out = profile_findings(username, "roblox", Profile(url, bio=text(user.get("description")), conf=0.8))
    if user.get("created"):
        out.append(Finding(("Account", url), "creato_il", ("Data", f"account Roblox creato: {user['created'][:10]}"), 0.95, "profilo Roblox", url=url, pivot=False))
    return out


@collector("roblox", "Username")
async def roblox(username: str) -> list[Finding]:
    async with httpx.AsyncClient(**HTTP) as c:
        r = await c.post("https://users.roblox.com/v1/usernames/users", json={"usernames": [username], "excludeBannedUsers": False})
        r.raise_for_status()
        look = r.json()
        if not look.get("data"):
            return []
        u = await c.get(f"https://users.roblox.com/v1/users/{look['data'][0]['id']}")
    return parse_roblox(username, look, u.json() if u.status_code == 200 else {})
