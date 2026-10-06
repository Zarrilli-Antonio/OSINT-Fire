"""Sources that use the user's own accounts on a platform through its OFFICIAL API (app credentials or a personal token).
This is the supported way to query those services: no scraping, no session cookies, nothing that breaks the platform's terms."""
import time
from collections import Counter

import httpx

from ..models import Finding
from ..settings import CFG
from . import collector
from .domain import HTTP
from .keyed import client
from .profiles import Profile, profile_findings, text
from ..images import phash_url

_tokens: dict[str, tuple[str, float]] = {}  # provider -> (token, expiry)


async def _token(name: str, fetch) -> str:
    tok, exp = _tokens.get(name, ("", 0.0))
    if tok and time.time() < exp - 60:
        return tok
    tok, ttl = await fetch()
    _tokens[name] = (tok, time.time() + ttl)
    return tok


async def _with_avatar(out: list[Finding], p: Profile) -> list[Finding]:
    if p.avatar.startswith("http"):
        async with httpx.AsyncClient(follow_redirects=True, **HTTP) as c:
            if ph := await phash_url(c, p.avatar):
                out.append(Finding(("Account", p.url), "immagine_profilo", ("Immagine", ph[0]), 0.9, "avatar del profilo", url=p.avatar, raw={"thumb": ph[1]}, pivot=False))
    return out


# ---------------- Reddit (app-only OAuth) ----------------

async def reddit_token() -> str:
    async def fetch():
        async with client({}) as c:
            r = await c.post("https://www.reddit.com/api/v1/access_token", auth=(CFG["reddit_client_id"], CFG["reddit_client_secret"]), data={"grant_type": "client_credentials"})
        r.raise_for_status()
        j = r.json()
        if "access_token" not in j:
            raise RuntimeError(f"Reddit: {j.get('error', 'autenticazione rifiutata')}")
        return j["access_token"], j.get("expires_in", 3600)
    return await _token("reddit", fetch)


def parse_reddit(username: str, about: dict, overview: dict) -> list[Finding]:
    d = about.get("data") or {}
    if not d.get("name"):
        return []
    url = f"https://www.reddit.com/user/{d['name']}"
    p = Profile(url, bio=text((d.get("subreddit") or {}).get("public_description")), avatar=(d.get("icon_img") or "").split("?")[0], conf=0.9)
    out = profile_findings(username, "reddit", p)
    acc = ("Account", url)
    if d.get("created_utc"):
        out.append(Finding(acc, "creato_il", ("Data", f"account Reddit creato: {time.strftime('%Y-%m-%d', time.gmtime(d['created_utc']))}"), 0.95, "profilo Reddit", url=url, pivot=False))
    out.append(Finding(acc, "attivita", ("Servizio", f"Reddit: karma {d.get('link_karma', 0)} post, {d.get('comment_karma', 0)} commenti"), 0.9, "profilo Reddit", url=url, pivot=False))
    subs = Counter(c["data"]["subreddit"] for c in (overview.get("data") or {}).get("children", []) if (c.get("data") or {}).get("subreddit"))
    for sub, n in subs.most_common(8):
        out.append(Finding(acc, "attivo_in", ("Interesse", f"r/{sub}"), 0.7, f"{n} contributi recenti", url=f"https://www.reddit.com/r/{sub}", pivot=False))
    return out


@collector("reddit", "Username", key=("reddit_client_id", "reddit_client_secret"))
async def reddit(username: str) -> list[Finding]:
    tok = await reddit_token()
    async with client({"Authorization": f"Bearer {tok}"}) as c:
        about = await c.get(f"https://oauth.reddit.com/user/{username}/about")
        if about.status_code in (403, 404):
            return []
        about.raise_for_status()
        ov = await c.get(f"https://oauth.reddit.com/user/{username}/overview", params={"limit": 50})
    out = parse_reddit(username, about.json(), ov.json() if ov.status_code == 200 else {})
    prof = (about.json().get("data") or {})
    return await _with_avatar(out, Profile(f"https://www.reddit.com/user/{prof.get('name', username)}", avatar=(prof.get("icon_img") or "").split("?")[0]))


# ---------------- Twitch ----------------

async def twitch_token() -> str:
    async def fetch():
        async with client({}) as c:
            r = await c.post("https://id.twitch.tv/oauth2/token", params={"client_id": CFG["twitch_client_id"], "client_secret": CFG["twitch_client_secret"], "grant_type": "client_credentials"})
        r.raise_for_status()
        j = r.json()
        return j["access_token"], j.get("expires_in", 3600)
    return await _token("twitch", fetch)


def parse_twitch(username: str, j: dict) -> list[Finding]:
    d = (j.get("data") or [None])[0]
    if not d:
        return []
    url = f"https://www.twitch.tv/{d['login']}"
    out = profile_findings(username, "twitch", Profile(url, bio=text(d.get("description")), avatar=d.get("profile_image_url", ""), conf=0.9))
    if d.get("created_at"):
        out.append(Finding(("Account", url), "creato_il", ("Data", f"account Twitch creato: {d['created_at'][:10]}"), 0.95, "profilo Twitch", url=url, pivot=False))
    if d.get("broadcaster_type"):
        out.append(Finding(("Account", url), "tipo_account", ("Servizio", f"Twitch: {d['broadcaster_type']}"), 0.9, "profilo Twitch", url=url, pivot=False))
    return out


@collector("twitch", "Username", key=("twitch_client_id", "twitch_client_secret"))
async def twitch(username: str) -> list[Finding]:
    tok = await twitch_token()
    async with client({"Client-Id": CFG["twitch_client_id"], "Authorization": f"Bearer {tok}"}) as c:
        r = await c.get("https://api.twitch.tv/helix/users", params={"login": username})
    r.raise_for_status()
    j = r.json()
    out = parse_twitch(username, j)
    return await _with_avatar(out, Profile(f"https://www.twitch.tv/{username}", avatar=((j.get("data") or [{}])[0]).get("profile_image_url", ""))) if out else out


# ---------------- YouTube ----------------

def parse_youtube(username: str, j: dict) -> list[Finding]:
    items = j.get("items") or []
    if not items:
        return []
    sn = items[0].get("snippet", {})
    handle = sn.get("customUrl") or f"@{username}"
    url = f"https://www.youtube.com/{handle}"
    out = profile_findings(username, "youtube", Profile(url, location=sn.get("country", ""), bio=text(sn.get("description")), avatar=(sn.get("thumbnails", {}).get("high") or sn.get("thumbnails", {}).get("default") or {}).get("url", ""), conf=0.9))
    if sn.get("title"):
        out.append(Finding(("Account", url), "nome_canale", ("Persona", sn["title"]), 0.3, "titolo del canale (può essere un marchio o un soprannome)", url=url, pivot=False))
    if sn.get("publishedAt"):
        out.append(Finding(("Account", url), "creato_il", ("Data", f"canale YouTube creato: {sn['publishedAt'][:10]}"), 0.95, "canale YouTube", url=url, pivot=False))
    return out


@collector("youtube", "Username", key="youtube_key")
async def youtube(username: str) -> list[Finding]:
    async with client({}) as c:
        r = await c.get("https://www.googleapis.com/youtube/v3/channels", params={"part": "snippet", "forHandle": f"@{username}", "key": CFG["youtube_key"]})
    r.raise_for_status()
    j = r.json()
    out = parse_youtube(username, j)
    thumb = (((j.get("items") or [{}])[0].get("snippet") or {}).get("thumbnails") or {}).get("default", {}).get("url", "")
    return await _with_avatar(out, Profile(f"https://www.youtube.com/@{username}", avatar=thumb)) if out else out


# ---------------- Spotify ----------------

async def spotify_token() -> str:
    async def fetch():
        async with client({}) as c:
            r = await c.post("https://accounts.spotify.com/api/token", auth=(CFG["spotify_client_id"], CFG["spotify_client_secret"]), data={"grant_type": "client_credentials"})
        r.raise_for_status()
        j = r.json()
        return j["access_token"], j.get("expires_in", 3600)
    return await _token("spotify", fetch)


def parse_spotify(username: str, j: dict) -> list[Finding]:
    if not j.get("id"):
        return []
    url = (j.get("external_urls") or {}).get("spotify") or f"https://open.spotify.com/user/{j['id']}"
    return profile_findings(username, "spotify", Profile(url, j.get("display_name") or "", avatar=((j.get("images") or [{}])[0]).get("url", ""), conf=0.7))


@collector("spotify", "Username", key=("spotify_client_id", "spotify_client_secret"))
async def spotify(username: str) -> list[Finding]:
    tok = await spotify_token()
    async with client({"Authorization": f"Bearer {tok}"}) as c:
        r = await c.get(f"https://api.spotify.com/v1/users/{username}")
    if r.status_code in (400, 404):
        return []
    r.raise_for_status()
    j = r.json()
    return await _with_avatar(parse_spotify(username, j), Profile((j.get("external_urls") or {}).get("spotify", ""), avatar=((j.get("images") or [{}])[0]).get("url", "")))


# ---------------- X (Twitter) API v2, bearer token ----------------

def parse_x(username: str, j: dict) -> list[Finding]:
    d = j.get("data")
    if not d:
        return []
    url = f"https://x.com/{d['username']}"
    site = ""
    for u in ((d.get("entities") or {}).get("url") or {}).get("urls", []):
        site = u.get("expanded_url") or site
    out = profile_findings(username, "x", Profile(url, d.get("name", ""), d.get("location", ""), site, avatar=(d.get("profile_image_url") or "").replace("_normal", "_400x400"),
                                                  bio=text(d.get("description")), conf=0.95))
    if d.get("created_at"):
        out.append(Finding(("Account", url), "creato_il", ("Data", f"account X creato: {d['created_at'][:10]}"), 0.95, "profilo X", url=url, pivot=False))
    m = d.get("public_metrics") or {}
    if m:
        out.append(Finding(("Account", url), "attivita", ("Servizio", f"X: {m.get('followers_count', 0)} follower, {m.get('tweet_count', 0)} post"), 0.9, "profilo X", url=url, pivot=False))
    return out


@collector("x_profile", "Username", key="x_bearer")
async def x_profile(username: str) -> list[Finding]:
    async with client({"Authorization": f"Bearer {CFG['x_bearer']}"}) as c:
        r = await c.get(f"https://api.x.com/2/users/by/username/{username}",
                        params={"user.fields": "created_at,description,location,profile_image_url,public_metrics,url,entities,verified"})
    if r.status_code == 404:
        return []
    r.raise_for_status()
    j = r.json()
    return await _with_avatar(parse_x(username, j), Profile(f"https://x.com/{username}", avatar=((j.get("data") or {}).get("profile_image_url") or "").replace("_normal", "_400x400")))


# ---------------- Companies House (UK registry) ----------------

def parse_companies(name: str, j: dict) -> list[Finding]:
    out = []
    for it in j.get("items", []):
        title, num = it.get("title", ""), it.get("company_number")
        url = f"https://find-and-update.company-information.service.gov.uk/company/{num}"
        exact = title.lower().rstrip(". ") == name.lower().rstrip(". ")
        src = ("Azienda", title)
        out.append(Finding(("Azienda", name), "societa_registrata", src, 0.75 if exact else 0.4, f"Companies House, stato {it.get('company_status', '?')}", url=url, pivot=False))
        out.append(Finding(src, "numero_registro", ("Registrazione", f"UK {num}"), 0.95, "Companies House", url=url, pivot=False))
        if it.get("address_snippet"):
            out.append(Finding(src, "sede_legale", ("Luogo", it["address_snippet"]), 0.9, "indirizzo registrato", url=url, pivot=False))
        if it.get("date_of_creation"):
            out.append(Finding(src, "costituita", ("Data", f"costituzione: {it['date_of_creation']}"), 0.95, "Companies House", url=url, pivot=False))
    return out


def parse_officers(name: str, j: dict) -> list[Finding]:
    out = []
    for it in j.get("items", []):
        url = "https://find-and-update.company-information.service.gov.uk" + (it.get("links") or {}).get("self", "")
        acc = ("Account", url)
        out.append(Finding(("Persona", name), "amministratore_registrato", acc, 0.35, f"omonimia possibile, {it.get('appointment_count', 0)} incarichi (Companies House)", url=url, pivot=False))
        if it.get("address_snippet"):
            out.append(Finding(acc, "indirizzo_registrato", ("Luogo", it["address_snippet"]), 0.5, "indirizzo nel registro pubblico", url=url, pivot=False))
        if it.get("description"):
            out.append(Finding(acc, "dettaglio", ("Servizio", it["description"]), 0.5, "registro pubblico", url=url, pivot=False))
    return out


async def _ch(path: str, name: str) -> dict:
    async with client({}) as c:
        r = await c.get(f"https://api.company-information.service.gov.uk{path}", params={"q": name, "items_per_page": 5}, auth=(CFG["companieshouse_key"], ""))
    r.raise_for_status()
    return r.json()


@collector("companies_house", "Azienda", key="companieshouse_key")
async def companies_house(name: str) -> list[Finding]:
    return parse_companies(name, await _ch("/search/companies", name))


@collector("companies_house_officers", "Persona", key="companieshouse_key")
async def companies_house_officers(name: str) -> list[Finding]:
    return parse_officers(name, await _ch("/search/officers", name)) if len(name.split()) >= 2 else []


# ---------------- GreyNoise (community) ----------------

def parse_greynoise(ip: str, j: dict) -> list[Finding]:
    url, me, out = f"https://viz.greynoise.io/ip/{ip}", ("IP", ip), []
    if j.get("noise") or j.get("riot"):
        out.append(Finding(me, "classificazione", ("Servizio", f"GreyNoise: {j.get('classification', '?')}{', ' + j['name'] if j.get('name') else ''}"), 0.8,
                           "scansioni di massa osservate" if j.get("noise") else "servizio noto e benigno (RIOT)", url=url, pivot=False))
    return out


@collector("greynoise", "IP", key="greynoise_key")
async def greynoise(ip: str) -> list[Finding]:
    async with client({"key": CFG["greynoise_key"]}) as c:
        r = await c.get(f"https://api.greynoise.io/v3/community/{ip}")
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return parse_greynoise(ip, r.json())


# ---------------- AlienVault OTX ----------------

def parse_otx(kind: str, value: str, j: dict) -> list[Finding]:
    me, url, out, seen = (kind, value), f"https://otx.alienvault.com/indicator/{'domain' if kind == 'Dominio' else 'ip'}/{value}", [], set()
    for r in (j.get("passive_dns") or [])[:150]:
        host, addr = (r.get("hostname") or "").lower(), r.get("address") or ""
        if kind == "Dominio":
            if host.endswith("." + value) and host not in seen:
                seen.add(host)
                out.append(Finding(me, "sottodominio", ("Dominio", host), 0.7, "passive DNS (OTX)", url=url))
            if addr.count(".") == 3 and addr not in seen:
                seen.add(addr)
                out.append(Finding(me, "risolve_a", ("IP", addr), 0.6, "risoluzione storica (OTX)", url=url, pivot=False))
        elif host and host not in seen:
            seen.add(host)
            out.append(Finding(me, "dominio_ospitato", ("Dominio", host), 0.6, "passive DNS (OTX)", url=url, pivot=False))
    return out


def _otx(kind: str, path: str):
    async def run(value: str) -> list[Finding]:
        async with client({"X-OTX-API-KEY": CFG["otx_key"]}) as c:
            r = await c.get(f"https://otx.alienvault.com/api/v1/indicators/{path}/{value}/passive_dns")
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return parse_otx(kind, value, r.json())
    return run


collector("otx_domain", "Dominio", key="otx_key")(_otx("Dominio", "domain"))
collector("otx_ip", "IP", key="otx_key")(_otx("IP", "IPv4"))


# ---------------- URLhaus (abuse.ch) ----------------

def parse_urlhaus(kind: str, value: str, j: dict) -> list[Finding]:
    if j.get("query_status") != "ok":
        return []
    me, url = (kind, value), f"https://urlhaus.abuse.ch/host/{value}/"
    urls = j.get("urls") or []
    online = sum(1 for u in urls if u.get("url_status") == "online")
    out = [Finding(me, "reputazione", ("Servizio", f"URLhaus: {j.get('urls_count', len(urls))} URL malevoli segnalati ({online} online)"), 0.85, "abuse.ch URLhaus", url=url, pivot=False)]
    for u in urls[:5]:
        out.append(Finding(me, "url_malevolo", ("Servizio", f"URL malevolo: {u.get('url', '')[:120]} ({u.get('threat', '?')})"), 0.85, "abuse.ch URLhaus", url=u.get("urlhaus_link", url), pivot=False))
    return out


def _urlhaus(kind: str):
    async def run(value: str) -> list[Finding]:
        async with client({"Auth-Key": CFG["abusech_key"]}) as c:
            r = await c.post("https://urlhaus-api.abuse.ch/v1/host/", data={"host": value})
        r.raise_for_status()
        return parse_urlhaus(kind, value, r.json())
    return run


collector("urlhaus_domain", "Dominio", key="abusech_key")(_urlhaus("Dominio"))
collector("urlhaus_ip", "IP", key="abusech_key")(_urlhaus("IP"))
