"""Username -> public profile on developer/community sites with a keyless JSON API.

Table-driven: each source gives a URL and a parser returning a Profile (or None when the account does not exist).
"""
import html
import re
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlparse

import httpx

from ..images import phash_url
from ..models import Finding
from . import collector
from .domain import HTTP

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
URL = re.compile(r"https?://[^\s\"'<>)]+")


def text(s: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).strip()


@dataclass
class Profile:
    url: str
    name: str = ""
    location: str = ""
    website: str = ""
    company: str = ""
    avatar: str = ""
    bio: str = ""
    emails: list = field(default_factory=list)
    accounts: list = field(default_factory=list)  # other profile URLs claimed by the owner
    conf: float = 0.85  # confidence that the account really is this username (lower for fuzzy lookups)


def host(u: str) -> str:
    return (urlparse(u if "//" in u else "https://" + u).hostname or "").removeprefix("www.")


def profile_findings(username: str, site: str, p: Profile) -> list[Finding]:
    me, acc, why = ("Username", username), ("Account", p.url), f"profilo su {site}"
    out = [Finding(me, "account", acc, p.conf, why, url=p.url, pivot=False)]
    if p.name:
        out.append(Finding(acc, "nome_profilo", ("Persona", p.name), 0.5, f"nome nel profilo {site}", url=p.url, pivot=False))
    if p.location:
        out.append(Finding(acc, "luogo_dichiarato", ("Luogo", p.location), 0.4, f"luogo nel profilo {site}", url=p.url, pivot=False))
    if p.company:
        out.append(Finding(acc, "azienda_dichiarata", ("Azienda", p.company.lstrip("@").strip()), 0.5, f"azienda nel profilo {site}",
                           url=p.url, pivot=False))
    if p.website and host(p.website):
        out.append(Finding(acc, "sito_dichiarato", ("Dominio", host(p.website)), 0.6, f"sito nel profilo {site}", url=p.url))
    for e in p.emails:
        out.append(Finding(acc, "email_pubblica", ("Email", e.lower()), 0.75, f"email nel profilo {site}", url=p.url))
    for e in set(EMAIL.findall(p.bio)) - set(p.emails):
        out.append(Finding(acc, "email_nella_bio", ("Email", e.lower()), 0.5, f"indirizzo nella bio su {site}", url=p.url))
    for a in p.accounts:
        out.append(Finding(acc, "profilo_collegato", ("Account", a), 0.7, f"link a un altro profilo su {site}", url=p.url, pivot=False))
    return out


# ---- parsers: (json, username) -> Profile | None ----

def _gitlab(j, u):
    return Profile(j[0]["web_url"], j[0].get("name", ""), avatar=j[0].get("avatar_url", ""),
                   emails=[j[0]["public_email"]] if j[0].get("public_email") else []) if j else None


def _devto(j, u):
    acc = [f"https://github.com/{j['github_username']}"] if j.get("github_username") else []
    acc += [f"https://twitter.com/{j['twitter_username']}"] if j.get("twitter_username") else []
    return Profile(f"https://dev.to/{u}", j.get("name", ""), j.get("location") or "", j.get("website_url") or "",
                   avatar=j.get("profile_image", ""), bio=j.get("summary") or "", accounts=acc)


def _hn(j, u):
    if not j:
        return None
    bio = text(j.get("about"))
    return Profile(f"https://news.ycombinator.com/user?id={u}", bio=bio, website=(URL.findall(html.unescape(j.get("about") or "")) or [""])[0])


def _docker(j, u):
    return Profile(j.get("profile_url") or f"https://hub.docker.com/u/{u}", j.get("full_name", ""), j.get("location", ""),
                   company=j.get("company", ""), avatar=j.get("gravatar_url", ""))


def _chess(j, u):
    return Profile(j["url"], j.get("name", ""), j.get("location", ""), avatar=j.get("avatar", ""))


def _lichess(j, u):
    pr = j.get("profile", {})
    links = URL.findall(pr.get("links", "") or "")
    return Profile(f"https://lichess.org/@/{j['username']}", pr.get("realName", ""), pr.get("location", ""),
                   links[0] if links else "", bio=pr.get("bio", ""), accounts=links[1:])


def _mastodon(j, u):
    verified = [text(f["value"]) for f in j.get("fields", []) if f.get("verified_at")]
    return Profile(j["url"], j.get("display_name", ""), website=verified[0] if verified else "", avatar=j.get("avatar", ""),
                   bio=text(j.get("note")))


def _bsky(j, u):
    return Profile(f"https://bsky.app/profile/{j['handle']}", j.get("displayName", ""), avatar=j.get("avatar", ""),
                   bio=j.get("description") or "")


def _crates(j, u):
    us = j["user"]
    return Profile(f"https://crates.io/users/{us['login']}", us.get("name") or "", avatar=us.get("avatar") or "",
                   accounts=[us["url"]] if us.get("url") else [])


def _gravatar(j, u):
    e = j["entry"][0]
    return Profile(e["profileUrl"], e.get("displayName", ""), avatar=e.get("thumbnailUrl", ""), bio=e.get("aboutMe") or "",
                   accounts=[a["url"] for a in e.get("accounts") or [] if a.get("url")])


def _gitea(j, u):
    mail = j.get("email") or ""
    return Profile(j["html_url"], j.get("full_name", ""), j.get("location", ""), j.get("website", ""), avatar=j.get("avatar_url", ""),
                   bio=j.get("description", ""), emails=[mail] if mail and "noreply" not in mail else [])


def _launchpad(j, u):
    return Profile(j["web_link"], j.get("display_name", ""), j.get("location") or "")


def _speedrun(j, u):
    d = j["data"]
    socials = [v["uri"] for k in ("twitter", "youtube", "twitch", "instagram") if (v := d.get(k)) and v.get("uri")]
    loc = ((d.get("location") or {}).get("country") or {}).get("names", {}).get("international", "")
    return Profile(d["weblink"], d["names"]["international"], loc, accounts=socials)


def _stackexchange(j, u):
    for it in j.get("items", []):  # inname search is fuzzy: keep only the exact display name
        if it.get("display_name", "").lower() == u.lower():
            return Profile(it["link"], it["display_name"], it.get("location") or "", it.get("website_url") or "",
                           avatar=it.get("profile_image", ""), conf=0.4)
    return None


def _hf(j, u):
    orgs = j.get("orgs") or []
    return Profile(f"https://huggingface.co/{u}", j.get("fullname", ""), avatar=j.get("avatarUrl", ""),
                   company=(orgs[0].get("fullname") or orgs[0].get("name") or "") if orgs else "")


def _wpcom(j, u):
    return Profile(j["URL"], bio=f"{j.get('name', '')}. {j.get('description', '')}".strip(". "), avatar=(j.get("icon") or {}).get("img", ""), conf=0.6)


def _codeforces(j, u):
    r = j["result"][0]
    return Profile(f"https://codeforces.com/profile/{r['handle']}", " ".join(x for x in (r.get("firstName"), r.get("lastName")) if x),
                   ", ".join(x for x in (r.get("city"), r.get("country")) if x), company=r.get("organization", ""), avatar=r.get("avatar", ""))


def _hackerrank(j, u):
    m = j["model"]
    accounts = [x for x in (m.get("github_url"), m.get("linkedin_url"), m.get("twitter_url")) if x]
    return Profile(f"https://www.hackerrank.com/profile/{m['username']}", " ".join(x for x in (m.get("personal_first_name"), m.get("personal_last_name")) if x) or m.get("name", ""),
                   m.get("country", ""), m.get("website", ""), company=m.get("company", "") or m.get("school", ""), avatar=m.get("avatar", ""), accounts=accounts, conf=0.8)


def _codewars(j, u):
    return Profile(f"https://www.codewars.com/users/{j['username']}", j.get("name", ""), company=j.get("clan", "") if j.get("clan") != "None" else "")


def _wattpad(j, u):
    return Profile(f"https://www.wattpad.com/user/{j['username']}", j.get("name", ""), j.get("location", ""), avatar=j.get("avatar", ""), bio=text(j.get("description")))


def _discogs(j, u):
    return Profile(f"https://www.discogs.com/user/{j['username']}", j.get("name", ""), j.get("location", ""), j.get("home_page", ""), avatar=j.get("avatar_url", ""), bio=j.get("profile", ""))


def _gitee(j, u):
    return Profile(j["html_url"], j.get("name", ""), website=j.get("blog", ""), avatar=j.get("avatar_url", ""), bio=j.get("bio") or "", emails=[j["email"]] if j.get("email") else [])


def _leetcode(j, u):
    m = (j.get("data") or {}).get("matchedUser")
    if not m:
        return None
    pr = m.get("profile") or {}
    return Profile(f"https://leetcode.com/u/{m['username']}", pr.get("realName", ""), pr.get("countryName") or "", company=pr.get("company") or pr.get("school") or "",
                   avatar=pr.get("userAvatar", ""), bio=text(pr.get("aboutMe")), website=(pr.get("websites") or [""])[0])


def _anilist(j, u):
    m = (j.get("data") or {}).get("User")
    return Profile(m["siteUrl"], avatar=(m.get("avatar") or {}).get("large", ""), bio=text(m.get("about"))) if m else None


def _mojang(j, u):
    return Profile(f"https://namemc.com/profile/{j['name']}", avatar=f"https://crafatar.com/avatars/{j['id']}?size=128&overlay", conf=0.7)


@dataclass
class Source:
    name: str
    url: Callable[[str], str]
    parse: Callable
    params: Callable | None = None  # username -> query params
    body: Callable | None = None  # username -> JSON body (POST)


SOURCES = [
    Source("gitlab", lambda u: "https://gitlab.com/api/v4/users", _gitlab),
    Source("devto", lambda u: "https://dev.to/api/users/by_username", _devto),
    Source("hackernews", lambda u: f"https://hacker-news.firebaseio.com/v0/user/{u}.json", _hn),
    Source("dockerhub", lambda u: f"https://hub.docker.com/v2/users/{u}/", _docker),
    Source("chesscom", lambda u: f"https://api.chess.com/pub/player/{u}", _chess),
    Source("lichess", lambda u: f"https://lichess.org/api/user/{u}", _lichess),
    Source("mastodon_social", lambda u: "https://mastodon.social/api/v1/accounts/lookup", _mastodon),
    Source("bluesky", lambda u: "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile", _bsky),
    Source("crates_io", lambda u: f"https://crates.io/api/v1/users/{u}", _crates),
    Source("gravatar_profile", lambda u: f"https://gravatar.com/{u}.json", _gravatar),
    Source("codeberg", lambda u: f"https://codeberg.org/api/v1/users/{u}", _gitea),
    Source("launchpad", lambda u: f"https://api.launchpad.net/1.0/~{u}", _launchpad),
    Source("speedrun", lambda u: f"https://www.speedrun.com/api/v1/users/{u}", _speedrun),
    Source("stackoverflow", lambda u: "https://api.stackexchange.com/2.3/users", _stackexchange),
    Source("codeforces", lambda u: "https://codeforces.com/api/user.info", _codeforces, lambda u: {"handles": u}),
    Source("hackerrank", lambda u: f"https://www.hackerrank.com/rest/contests/master/hackers/{u}/profile", _hackerrank),
    Source("codewars", lambda u: f"https://www.codewars.com/api/v1/users/{u}", _codewars),
    Source("wattpad", lambda u: f"https://www.wattpad.com/api/v3/users/{u}", _wattpad, lambda u: {"fields": "username,name,description,location,avatar"}),
    Source("discogs", lambda u: f"https://api.discogs.com/users/{u}", _discogs),
    Source("gitee", lambda u: f"https://gitee.com/api/v5/users/{u}", _gitee),
    Source("mojang", lambda u: f"https://api.mojang.com/users/profiles/minecraft/{u}", _mojang),
    Source("leetcode", lambda u: "https://leetcode.com/graphql", _leetcode, body=lambda u: {
        "query": "query u($n:String!){matchedUser(username:$n){username profile{realName countryName company school userAvatar aboutMe websites}}}", "variables": {"n": u}}),
    Source("anilist", lambda u: "https://graphql.anilist.co", _anilist, body=lambda u: {
        "query": "query($n:String){User(name:$n){name about avatar{large} siteUrl}}", "variables": {"n": u}}),
    *[Source(f"mastodon_{h.replace('.', '_')}", (lambda host: lambda u: f"https://{host}/api/v1/accounts/lookup")(h), _mastodon, lambda u: {"acct": u})
      for h in ("hachyderm.io", "fosstodon.org", "infosec.exchange", "mas.to", "mstdn.social", "techhub.social")],
    Source("huggingface", lambda u: f"https://huggingface.co/api/users/{u}/overview", _hf),
    Source("wordpress_com", lambda u: f"https://public-api.wordpress.com/rest/v1.1/sites/{u}.wordpress.com", _wpcom),
]
QUERY = {"gitlab": lambda u: {"username": u}, "devto": lambda u: {"url": u}, "mastodon_social": lambda u: {"acct": u},
         "bluesky": lambda u: {"actor": f"{u}.bsky.social"},
         "stackoverflow": lambda u: {"inname": u, "site": "stackoverflow", "pagesize": 5}}


def make(src: Source):
    async def run(username: str) -> list[Finding]:
        async with httpx.AsyncClient(follow_redirects=True, **HTTP) as c:
            if src.body:
                r = await c.post(src.url(username), json=src.body(username))
            else:
                params = src.params(username) if src.params else QUERY.get(src.name, lambda u: None)(username)
                r = await c.get(src.url(username), params=params)
            if r.status_code in (400, 404, 410):
                return []
            r.raise_for_status()
            j = r.json()
            try:
                p = src.parse(j, username)
            except (KeyError, IndexError, TypeError):
                return []  # unexpected shape = no usable profile
            if p is None:
                return []
            out = profile_findings(username, src.name, p)
            if p.avatar.startswith("http") and (ph := await phash_url(c, p.avatar)):
                out.append(Finding(("Account", p.url), "immagine_profilo", ("Immagine", ph[0]), 0.9, f"avatar su {src.name}",
                                   url=p.avatar, raw={"thumb": ph[1]}, pivot=False))
        return out

    return run


for _s in SOURCES:
    collector(_s.name, "Username")(make(_s))


# ---- sources that need more than one profile ----

def parse_keybase(username: str, j: dict) -> list[Finding]:
    if not j.get("them") or not j["them"][0]:
        return []
    u = j["them"][0]
    url = f"https://keybase.io/{username}"
    acc, out = ("Account", url), [Finding(("Username", username), "account", ("Account", url), 0.85, "profilo Keybase", url=url, pivot=False)]
    pr = u.get("profile") or {}
    if pr.get("full_name"):
        out.append(Finding(acc, "nome_profilo", ("Persona", pr["full_name"]), 0.6, "nome nel profilo Keybase", url=url, pivot=False))
    if pr.get("location"):
        out.append(Finding(acc, "luogo_dichiarato", ("Luogo", pr["location"]), 0.4, "luogo nel profilo Keybase", url=url, pivot=False))
    for pf in (u.get("proofs_summary") or {}).get("all", []):  # cryptographically verified by the owner
        if pf["proof_type"] == "dns":
            out.append(Finding(acc, "dominio_verificato", ("Dominio", pf["nametag"].lower()), 0.95, "prova crittografica Keybase (DNS)", url=url))
        elif pf.get("service_url"):
            out.append(Finding(acc, "profilo_verificato", ("Account", pf["service_url"]), 0.95,
                               f"prova crittografica Keybase ({pf['proof_type']})", url=url, pivot=False))
    return out


@collector("keybase", "Username")
async def keybase(username: str) -> list[Finding]:
    async with httpx.AsyncClient(**HTTP) as c:
        r = await c.get("https://keybase.io/_/api/1.0/user/lookup.json",
                        params={"usernames": username, "fields": "basics,profile,proofs_summary"})
    r.raise_for_status()
    return parse_keybase(username, r.json())


def parse_npm(username: str, j: dict) -> list[Finding]:
    out, seen = [], set()
    for o in j.get("objects", []):
        pkg = o["package"]
        mine = [m for m in pkg.get("maintainers", []) if m.get("username", "").lower() == username.lower()]
        if not mine:
            continue
        out.append(Finding(("Username", username), "pubblica_pacchetto", ("Servizio", f"npm: {pkg['name']}"), 0.9,
                           "pacchetto npm di cui è maintainer", url=pkg.get("links", {}).get("npm", ""), pivot=False))
        if (e := mine[0].get("email")) and e.lower() not in seen:
            seen.add(e.lower())
            out.append(Finding(("Username", username), "email_registry", ("Email", e.lower()), 0.75,
                               "metadato pubblico del registry npm", url=pkg.get("links", {}).get("npm", "")))
    return out


@collector("npm", "Username")
async def npm(username: str) -> list[Finding]:
    async with httpx.AsyncClient(**HTTP) as c:
        r = await c.get("https://registry.npmjs.org/-/v1/search", params={"text": f"maintainer:{username}", "size": 20})
    r.raise_for_status()
    return parse_npm(username, r.json())
