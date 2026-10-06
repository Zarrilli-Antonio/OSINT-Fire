"""Public profile pages without an API: parsed from the HTML the site serves to anyone."""
import html
import json
import re

import httpx

from ..images import phash_url
from ..models import Finding
from . import collector
from .domain import HTTP
from .profiles import Profile, profile_findings, text

BROWSER_UA = {"User-Agent": "Mozilla/5.0 (compatible; OSINT-Fire/0.1)"}


def meta(page: str, prop: str) -> str:
    m = re.search(rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']*)', page, re.I)
    return html.unescape(m.group(1)).strip() if m else ""


def parse_telegram(username: str, page: str) -> Profile | None:
    title = meta(page, "og:title")
    if not title or title.startswith("Telegram: Contact"):  # username not taken, or a private account without public preview
        return None
    return Profile(f"https://t.me/{username}", title, avatar=meta(page, "og:image"), bio=meta(page, "og:description"))


def parse_linktree(username: str, page: str) -> Profile | None:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        return None
    try:
        pp = json.loads(m.group(1))["props"]["pageProps"]
    except (ValueError, KeyError, TypeError):
        return None
    acc = pp.get("account") or {}
    if not acc.get("username"):
        return None
    links = [l["url"] for l in pp.get("links", []) if isinstance(l, dict) and str(l.get("url", "")).startswith("http")]
    links += [s["url"] for s in pp.get("socialLinks", []) if isinstance(s, dict) and str(s.get("url", "")).startswith("http")]
    return Profile(f"https://linktr.ee/{acc['username']}", acc.get("pageTitle") or "", bio=text(acc.get("description")),
                   avatar=acc.get("profilePictureUrl") or "", accounts=links[:30])


def make(name: str, url, parse):
    async def run(username: str) -> list[Finding]:
        async with httpx.AsyncClient(follow_redirects=True, **{**HTTP, "headers": BROWSER_UA}) as c:
            r = await c.get(url(username))
            if r.status_code in (403, 404, 410):  # absent, or the site refuses automated requests (linktr.ee answers 403)
                return []
            r.raise_for_status()
            p = parse(username, r.text)
            if p is None:
                return []
            out = profile_findings(username, name, p)
            if p.avatar.startswith("http") and (ph := await phash_url(c, p.avatar)):
                out.append(Finding(("Account", p.url), "immagine_profilo", ("Immagine", ph[0]), 0.9, f"avatar su {name}", url=p.avatar,
                                   raw={"thumb": ph[1]}, pivot=False))
        return out
    return run


collector("telegram", "Username")(make("telegram", lambda u: f"https://t.me/{u}", parse_telegram))
collector("linktree", "Username")(make("linktree", lambda u: f"https://linktr.ee/{u}", parse_linktree))
