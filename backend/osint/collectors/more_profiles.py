"""Username -> structured public profile (display name, bio, location, website, creation date, linked accounts) on sites with a keyless API
or a page meant to be public. Same shape as profiles.py (table-driven); an existing exact name is evidence of existence, not of identity."""
import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable
from urllib.parse import unquote

import httpx

from ..images import phash_url
from ..models import Finding
from . import collector
from .domain import HTTP
from .profiles import URL, Profile, profile_findings, text

CONF = 0.55  # exact-name hit on a public profile


@dataclass
class P(Profile):
    created: str = ""  # YYYY-MM-DD
    conf: float = CONF


def day(v) -> str:
    """ISO string, epoch seconds or 'Month D, YYYY' -> YYYY-MM-DD ('' when unknown)."""
    if isinstance(v, (int, float)) and v > 0:
        return datetime.fromtimestamp(v, timezone.utc).strftime("%Y-%m-%d")
    v = str(v or "")
    if re.match(r"\d{4}-\d{2}-\d{2}", v):
        return v[:10]
    for f in ("%B %d, %Y", "%d %B %Y"):
        try:
            return datetime.strptime(v.strip(), f).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return ""


def tag(xml: str, name: str) -> str:
    m = re.search(rf"<{name}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{name}>", xml, re.S)
    return html.unescape(m.group(1)).strip() if m else ""


def first_url(s: str) -> str:
    return (URL.findall(s or "") or [""])[0].rstrip(".,;")


def findings(username: str, label: str, site: str, p: P) -> list[Finding]:
    out = profile_findings(username, site, p)
    if p.created:
        out.append(Finding(("Account", p.url), "creato_il", ("Data", f"account {label} creato: {p.created}"), 0.9, f"profilo su {site}", url=p.url, pivot=False))
    return out


# ---- parsers: (payload, username) -> P | None ; payload is parsed JSON or raw text depending on the source ----

def _lobsters(j, u):
    acc = [f"https://github.com/{j['github_username']}"] if j.get("github_username") else []
    acc += [f"https://mastodon.social/@{j['mastodon_username']}"] if j.get("mastodon_username") and "@" not in j["mastodon_username"] else []
    return P(f"https://lobste.rs/~{j['username']}", bio=text(j.get("about")), website=first_url(html.unescape(j.get("about") or "")),
             accounts=acc, created=day(j.get("created_at")))


def _packagist(j, u):
    return P(f"https://packagist.org/packages/{u}/", conf=0.4) if j.get("packageNames") else None


def _scratch(j, u):
    pr = j.get("profile") or {}
    return P(f"https://scratch.mit.edu/users/{j['username']}/", location=pr.get("country") or "", bio=text(f"{pr.get('bio', '')} {pr.get('status', '')}"),
             created=day((j.get("history") or {}).get("joined")))


def _mediawiki(base: str):
    def parse(j, u):
        us = (j.get("query") or {}).get("users") or []
        if not us or "missing" in us[0] or "invalid" in us[0]:
            return None
        n = us[0]["name"]
        return P(f"{base}/wiki/User:{n.replace(' ', '_')}", conf=0.4, created=day(us[0].get("registration")),
                 bio=f"{us[0].get('editcount', 0)} edits")
    return parse


def _duolingo(j, u):
    for it in j.get("users") or []:
        if it.get("username", "").lower() == u.lower():
            return P(f"https://www.duolingo.com/profile/{it['username']}", it.get("name") or "", it.get("location") or "", bio=it.get("bio") or "",
                     created=day(it.get("creationDate")))
    return None


def _matrix(j, u):
    return P(f"https://matrix.to/#/@{u.lower()}:matrix.org", j.get("displayname") or "", conf=0.5) if j.get("displayname") else None


def _hex(j, u):
    return P(f"https://hex.pm/users/{j['username']}", emails=[j["email"]] if j.get("email") else [], created=day(j.get("inserted_at")),
             bio=f"{len(j.get('packages') or [])} packages" if j.get("packages") else "", **({"accounts": [f"https://github.com/{j['handles']['github']}"]} if (j.get("handles") or {}).get("github") else {}))


def _lemmy(j, u):
    p = (j.get("person_view") or {}).get("person")
    if not p or p.get("deleted") or p.get("banned"):
        return None
    mx = [f"https://matrix.to/#/{p['matrix_user_id']}"] if p.get("matrix_user_id") else []
    return P(p["actor_id"], p.get("display_name") or "", avatar=p.get("avatar") or "", bio=p.get("bio") or "", accounts=mx, created=day(p.get("published")))


def _openlibrary(j, u):
    d = j.get("description")
    d = d.get("value", "") if isinstance(d, dict) else d or ""
    return P(f"https://openlibrary.org/people/{u}", j.get("displayname") or "", website=(j.get("website") or [""])[0] if isinstance(j.get("website"), list) else j.get("website") or "",
             bio=text(d), created=day((j.get("created") or {}).get("value")))


def _mixcloud(j, u):
    if j.get("error"):
        return None
    return P(j["url"], j.get("name") or "", ", ".join(x for x in (j.get("city"), j.get("country")) if x), avatar=(j.get("pictures") or {}).get("large", ""),
             bio=j.get("biog") or "", created=day(j.get("created_time")))


def _dailymotion(j, u):
    soc = [j[k] for k in ("facebook_url", "twitter_url", "instagram_url", "linkedin_url") if j.get(k)]
    return P(j["url"], j.get("screenname") or "", website=j.get("website_url") or "", bio=j.get("description") or "", accounts=soc, created=day(j.get("created_time")))


def _substack(j, u):
    links = [l["url"] for l in j.get("userLinks") or [] if l.get("url")]
    return P(f"https://substack.com/@{j['handle']}", j.get("name") or "", website=links[0] if links else "", avatar=j.get("photo_url") or "", bio=j.get("bio") or "",
             accounts=links[1:], created=day(j.get("profile_set_up_at")))


def _bitbucket(j, u):
    return P(j["links"]["html"]["href"], j.get("name") or "", avatar=j["links"].get("avatar", {}).get("href", ""), conf=0.4, created=day(j.get("created_on")))


def _forgejo(j, u):
    mail = j.get("email") or ""
    return P(j["html_url"], j.get("full_name") or "", j.get("location") or "", j.get("website") or "", avatar=j.get("avatar_url") or "", bio=j.get("description") or "",
             emails=[mail] if mail and "noreply" not in mail else [], created=day(j.get("created")))


def _gitlab(j, u):
    for it in j if isinstance(j, list) else []:
        if it.get("username", "").lower() == u.lower():
            return P(it["web_url"], it.get("name") or "", avatar=it.get("avatar_url") or "", emails=[it["public_email"]] if it.get("public_email") else [],
                     created=day(it.get("created_at")))
    return None


def _kitsu(j, u):
    for it in j.get("data") or []:
        a = it.get("attributes", {})
        if str(a.get("slug") or a.get("name") or "").lower() == u.lower():
            return P(f"https://kitsu.app/users/{a.get('slug') or a['name']}", a.get("name") or "", a.get("location") or "", a.get("website") or "",
                     avatar=(a.get("avatar") or {}).get("original", ""), bio=a.get("about") or "", created=day(a.get("createdAt")))
    return None


def _modrinth(j, u):
    return P(f"https://modrinth.com/user/{j['username']}", j.get("name") or "", avatar=j.get("avatar_url") or "", bio=j.get("bio") or "", created=day(j.get("created")),
             emails=[j["email"]] if j.get("email") else [])


def _misskey(j, u):
    name = re.sub(r":\w+:", "", j.get("name") or "").strip()
    return P(f"https://misskey.io/@{j['username']}", name, j.get("location") or "", avatar=j.get("avatarUrl") or "", bio=text(j.get("description")), created=day(j.get("createdAt")),
             website=first_url(j.get("description") or ""))


def _sourceforge(j, u):
    lo = j.get("localization") or {}
    return P(f"https://sourceforge.net/u/{j['username']}/", j.get("name") or "", ", ".join(x for x in (lo.get("city"), lo.get("country")) if x),
             (j.get("webpages") or [""])[0] if j.get("webpages") else "", created=day(j.get("joined")))


def _tumblr(js, u):
    m = re.search(r"=\s*(\{.*\})\s*;?\s*$", js, re.S)
    if not m:
        return None
    import json
    t = json.loads(m.group(1)).get("tumblelog") or {}
    return P(f"https://{u}.tumblr.com", bio=text(f"{t.get('title', '')}. {t.get('description', '')}").strip(". "), conf=0.4) if t else None


def _livejournal(x, u):
    if "<foaf:Person>" not in x:
        return None
    loc = ", ".join(unquote(m.group(1)) for k in ("city", "country") if (m := re.search(rf'<ya:{k} dc:title="([^"]*)"', x)))
    hp = re.search(r'<foaf:homepage rdf:resource="([^"]*)"', x)
    return P(f"https://{u.replace('_', '-')}.livejournal.com/profile/", tag(x, "foaf:name"), loc, unquote(hp.group(1)) if hp else "",
             bio=tag(x, "ya:bio"), created=day((re.search(r"lj:dateCreated='([^']*)'", x) or [0, ""])[1]))


def _neocities(j, u):
    i = j.get("info") or {}
    return P(f"https://{i.get('sitename', u)}.neocities.org", website=i.get("domain") or "", conf=0.4, created=day(i.get("created_at") and parsedate_to_datetime(i["created_at"]).isoformat()))


@dataclass
class Source:
    name: str
    label: str  # platform name as shown in the 'account X creato' line
    url: Callable[[str], str]
    parse: Callable
    params: Callable | None = None
    body: Callable | None = None
    raw: bool = False  # parse the response text instead of JSON
    empty: tuple = (400, 404, 410)


def _lem(host):
    return Source(f"lemmy_{host.replace('.', '_')}", f"Lemmy ({host})", lambda u: f"https://{host}/api/v3/user", _lemmy, lambda u: {"username": u})


SOURCES = [
    Source("lobsters", "Lobsters", lambda u: f"https://lobste.rs/~{u}.json", _lobsters),
    Source("packagist", "Packagist", lambda u: "https://packagist.org/packages/list.json", _packagist, lambda u: {"vendor": u}),
    Source("scratch", "Scratch", lambda u: f"https://api.scratch.mit.edu/users/{u}", _scratch),
    *[Source(n, lbl, (lambda b: lambda u: f"{b}/w/api.php")(base), _mediawiki(base),
            lambda u: {"action": "query", "list": "users", "ususers": u, "usprop": "registration|editcount", "format": "json"})
      for n, lbl, base in (("wikipedia_user_en", "Wikipedia", "https://en.wikipedia.org"), ("wikipedia_user_it", "Wikipedia", "https://it.wikipedia.org"),
                           ("wikimedia_commons_user", "Wikimedia Commons", "https://commons.wikimedia.org"), ("wikidata_user", "Wikidata", "https://www.wikidata.org"))],
    Source("duolingo", "Duolingo", lambda u: "https://www.duolingo.com/2017-06-30/users", _duolingo, lambda u: {"username": u}),
    Source("matrix", "Matrix", lambda u: f"https://matrix-client.matrix.org/_matrix/client/v3/profile/@{u.lower()}:matrix.org", _matrix),
    Source("hexpm", "Hex.pm", lambda u: f"https://hex.pm/api/users/{u}", _hex),
    *[_lem(h) for h in ("lemmy.ml", "lemmy.world", "sh.itjust.works", "programming.dev")],
    Source("openlibrary_user", "Open Library", lambda u: f"https://openlibrary.org/people/{u}.json", _openlibrary),
    Source("mixcloud", "Mixcloud", lambda u: f"https://api.mixcloud.com/{u}/", _mixcloud),
    Source("dailymotion", "Dailymotion", lambda u: f"https://api.dailymotion.com/user/{u}", _dailymotion,
           lambda u: {"fields": "id,screenname,description,url,created_time,website_url,facebook_url,twitter_url,instagram_url,linkedin_url"}),
    Source("substack", "Substack", lambda u: f"https://substack.com/api/v1/user/{u}/public_profile", _substack),
    Source("bitbucket", "Bitbucket", lambda u: f"https://api.bitbucket.org/2.0/workspaces/{u}", _bitbucket),
    Source("gitea_com", "Gitea", lambda u: f"https://gitea.com/api/v1/users/{u}", _forgejo),
    Source("framagit", "Framagit", lambda u: "https://framagit.org/api/v4/users", _gitlab, lambda u: {"username": u}),
    Source("kde_invent", "KDE Invent", lambda u: "https://invent.kde.org/api/v4/users", _gitlab, lambda u: {"username": u}),
    Source("kitsu", "Kitsu", lambda u: "https://kitsu.io/api/edge/users", _kitsu, lambda u: {"filter[name]": u}),
    Source("modrinth", "Modrinth", lambda u: f"https://api.modrinth.com/v2/user/{u}", _modrinth),
    Source("misskey_io", "Misskey", lambda u: "https://misskey.io/api/users/show", _misskey, body=lambda u: {"username": u}),
    Source("sourceforge", "SourceForge", lambda u: f"https://sourceforge.net/rest/u/{u}/profile/", _sourceforge),
    Source("tumblr", "Tumblr", lambda u: f"https://{u}.tumblr.com/api/read/json", _tumblr, lambda u: {"num": 0}, raw=True),
    Source("livejournal", "LiveJournal", lambda u: f"https://{u.replace('_', '-')}.livejournal.com/data/foaf.rdf", _livejournal, raw=True),
    Source("neocities", "Neocities", lambda u: "https://neocities.org/api/info", _neocities, lambda u: {"sitename": u}),
]

VALID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")  # usernames end up in URLs/hostnames: refuse anything else


def make(src: Source):
    async def run(username: str) -> list[Finding]:
        if not VALID.match(username):
            return []
        async with httpx.AsyncClient(follow_redirects=True, **HTTP) as c:
            params = src.params(username) if src.params else None
            r = await (c.post(src.url(username), json=src.body(username)) if src.body else c.get(src.url(username), params=params))
            if r.status_code in src.empty:
                return []
            r.raise_for_status()
            try:
                p = src.parse(r.text if src.raw else r.json(), username)
            except (KeyError, IndexError, TypeError, ValueError, AttributeError):
                return []  # unexpected shape = no usable profile
            if p is None:
                return []
            out = findings(username, src.label, src.name, p)
            if p.avatar.startswith("http") and (ph := await phash_url(c, p.avatar)):
                out.append(Finding(("Account", p.url), "immagine_profilo", ("Immagine", ph[0]), 0.9, f"avatar su {src.name}", url=p.avatar, raw={"thumb": ph[1]}, pivot=False))
        return out

    return run


for _s in SOURCES:
    collector(_s.name, "Username")(make(_s))


# ---- sources that need more than one request or accept a person ----

def parse_bsky_search(name: str, j: dict) -> list[Finding]:
    """Name search: only an exact display-name match counts, and it is weak (homonyms)."""
    out = []
    for a in (j.get("actors") or [])[:10]:
        if re.sub(r"[^\w ]", "", a.get("displayName") or "").strip().lower() == name.strip().lower() and a.get("handle"):
            url = f"https://bsky.app/profile/{a['handle']}"
            out.append(Finding(("Persona", name), "account", ("Account", url), 0.25, "ricerca per nome su Bluesky: possibili omonimi", url=url, pivot=False))
    return out[:5]


@collector("bluesky_search", "Persona")
async def bluesky_search(name: str) -> list[Finding]:
    async with httpx.AsyncClient(**HTTP) as c:
        r = await c.get("https://public.api.bsky.app/xrpc/app.bsky.actor.searchActors", params={"q": name, "limit": 25})
    r.raise_for_status()
    return parse_bsky_search(name, r.json())


def parse_osm(username: str, changesets: str, user: dict) -> list[Finding]:
    u = user.get("user") or {}
    if not u.get("display_name"):
        return []
    links = [l.get("url", "") if isinstance(l, dict) else str(l) for l in u.get("social_links") or []]
    return findings(username, "OpenStreetMap", "openstreetmap",
                    P(f"https://www.openstreetmap.org/user/{u['display_name'].replace(' ', '%20')}", bio=u.get("description") or "", website=first_url(" ".join(links) + " " + (u.get("description") or "")),
                      accounts=[l for l in links if l.startswith("http")], created=day(u.get("account_created")), conf=0.5))


@collector("openstreetmap", "Username")
async def openstreetmap(username: str) -> list[Finding]:
    if not VALID.match(username):
        return []
    async with httpx.AsyncClient(**HTTP) as c:
        r = await c.get("https://api.openstreetmap.org/api/0.6/changesets", params={"display_name": username, "limit": 1})
        if r.status_code in (400, 404):
            return []
        r.raise_for_status()
        m = re.search(r'uid="(\d+)" user="([^"]*)"', r.text)  # users without any edit cannot be resolved by name
        if not m or html.unescape(m.group(2)).lower() != username.lower():
            return []
        r2 = await c.get(f"https://api.openstreetmap.org/api/0.6/user/{m.group(1)}.json")
        r2.raise_for_status()
    return parse_osm(username, r.text, r2.json())
