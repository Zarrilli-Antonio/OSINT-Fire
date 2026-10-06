import re
from urllib.parse import urlparse

import httpx

from ..images import phash_url
from ..models import Finding
from ..settings import CFG
from . import collector
from .domain import HTTP

API = "https://api.github.com"


def gh_client() -> httpx.AsyncClient:
    """GitHub API client; uses the optional token from settings (5000 requests/hour instead of 60)."""
    headers = {**HTTP["headers"], **({"Authorization": f"Bearer {CFG['github_token']}"} if CFG["github_token"] else {})}
    return httpx.AsyncClient(**{**HTTP, "headers": headers})
NOREPLY = re.compile(r"^(?:\d+\+)?([^@]+)@users\.noreply\.github\.com$", re.I)
# unauthenticated GitHub API = 60 requests/hour; set github_token in settings for 5000.


def commit_emails(events: list) -> set[str]:
    return {c["author"]["email"].lower() for e in events if e.get("type") == "PushEvent"
            for c in e.get("payload", {}).get("commits", [])
            if c.get("author", {}).get("email") and not c["author"]["email"].lower().endswith("@users.noreply.github.com")}


def parse_user(username: str, u: dict, events: list) -> list[Finding]:
    me, acc, url = ("Username", username), ("Account", u["html_url"]), u["html_url"]
    out = [Finding(me, "account", acc, 0.9, "profilo GitHub", url=url, pivot=False)]
    if u.get("name"):
        out.append(Finding(acc, "nome_profilo", ("Persona", u["name"]), 0.5, "nome nel profilo GitHub", url=url, pivot=False))
    if u.get("company"):
        out.append(Finding(acc, "azienda_dichiarata", ("Azienda", u["company"].lstrip("@").strip()), 0.5, "campo company GitHub",
                           url=url, pivot=False))
    if u.get("location"):
        out.append(Finding(acc, "luogo_dichiarato", ("Luogo", u["location"]), 0.4, "campo location GitHub", url=url, pivot=False))
    if blog := (u.get("blog") or "").strip():
        host = urlparse(blog if "//" in blog else "https://" + blog).hostname
        if host:
            out.append(Finding(acc, "sito_dichiarato", ("Dominio", host.removeprefix("www.")), 0.6, "campo blog GitHub", url=url))
    if u.get("email"):
        out.append(Finding(acc, "email_pubblica", ("Email", u["email"]), 0.85, "email nel profilo GitHub", url=url))
    if u.get("twitter_username"):
        out.append(Finding(acc, "profilo_social", ("Account", f"https://twitter.com/{u['twitter_username']}"), 0.7,
                           "campo twitter GitHub", url=url, pivot=False))
    for e in sorted(commit_emails(events)):
        out.append(Finding(acc, "email_nei_commit", ("Email", e), 0.6, "autore di commit pubblici (può essere un co-autore)", url=url))
    return out


def commit_authors(commits: list) -> list[tuple[str, str]]:
    """(name, email) pairs from a commits API response, noreply addresses excluded."""
    out = []
    for c in commits:
        a = (c.get("commit") or {}).get("author") or {}
        if a.get("email") and not a["email"].lower().endswith("@users.noreply.github.com"):
            out.append((a.get("name", ""), a["email"].lower()))
    return out


@collector("github_user", "Username")
async def github_user(username: str) -> list[Finding]:
    async with gh_client() as c:
        r = await c.get(f"{API}/users/{username}")
        if r.status_code == 404:
            return []
        r.raise_for_status()
        u = r.json()
        ev = await c.get(f"{API}/users/{username}/events/public", params={"per_page": 100})
        events = ev.json() if ev.status_code == 200 else []
        out = parse_user(username, u, events)
        acc, url = ("Account", u["html_url"]), u["html_url"]
        orgs = await c.get(f"{API}/users/{username}/orgs")
        if orgs.status_code == 200:
            out += [Finding(acc, "membro_di", ("Azienda", o["login"]), 0.7, "organizzazione GitHub pubblica", url=f"https://github.com/{o['login']}", pivot=False)
                    for o in orgs.json()]
        # commit author emails of the user's own repos: the classic way to find a developer's address. Costs ~4 API calls,
        # so only when the unauthenticated quota (60/h) has room and the public events showed none.
        if not commit_emails(events) and int(ev.headers.get("x-ratelimit-remaining", 0)) >= 15:
            repos = await c.get(f"{API}/users/{username}/repos", params={"per_page": 5, "sort": "pushed", "type": "owner"})
            seen = set()
            for repo in (repos.json() if repos.status_code == 200 else [])[:3]:
                if repo.get("fork"):
                    continue
                cm = await c.get(f"{API}/repos/{username}/{repo['name']}/commits", params={"author": username, "per_page": 5})
                for name, email in commit_authors(cm.json() if cm.status_code == 200 else []):
                    if email not in seen:
                        seen.add(email)
                        out.append(Finding(acc, "email_nei_commit", ("Email", email), 0.65, f"autore di commit in {repo['name']}", url=url))
                        if name:
                            out.append(Finding(acc, "nome_nei_commit", ("Persona", name), 0.45, "nome dell'autore nei commit", url=url, pivot=False))
        if u.get("avatar_url") and (ph := await phash_url(c, u["avatar_url"])):
            out.append(Finding(("Account", u["html_url"]), "immagine_profilo", ("Immagine", ph[0]), 0.9, "avatar GitHub",
                               url=u["avatar_url"], raw={"thumb": ph[1]}, pivot=False))
    return out


@collector("github_email", "Email")
async def github_email(email: str) -> list[Finding]:
    if m := NOREPLY.match(email):  # noreply addresses embed the username
        return [Finding(("Email", email), "usa_username", ("Username", m.group(1)), 0.95, "indirizzo noreply di GitHub")]
    out = []
    async with gh_client() as c:
        r = await c.get(f"{API}/search/users", params={"q": f"{email} in:email"})
        r.raise_for_status()
        for item in r.json().get("items", [])[:3]:  # search is fuzzy: keep only exact public-email matches
            u = (await c.get(item["url"])).json()
            if (u.get("email") or "").lower() == email:
                out.append(Finding(("Email", email), "usa_username", ("Username", u["login"]), 0.9, "email pubblica nel profilo GitHub",
                                   url=u["html_url"]))
    return out
