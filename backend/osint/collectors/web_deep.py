"""Deeper look at a website: tracking IDs, rel=me links, feeds, ads.txt, mobile app files, WordPress authors.
All of it is public files the site serves to anyone. Contacts the target's server, so it is an "active" collector."""
import json
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

import httpx

from ..models import Finding
from . import collector
from .domain import HTTP
from .profiles import EMAIL, text
from .web import PLACEHOLDER_DOMAINS

MAX_BODY = 500_000

# (label, regex): identifiers the site owner put in the page. The same ID on two domains means the same owner/account.
TRACKERS = [
    ("Google Analytics", r"\b(UA-\d{4,10}-\d{1,3})\b"), ("Google Analytics 4", r"\b(G-[A-Z0-9]{8,12})\b"),
    ("Google Tag Manager", r"\b(GTM-[A-Z0-9]{4,8})\b"), ("Google AdSense", r"\b(ca-pub-\d{10,20})\b"),
    ("Google Ads", r"\b(AW-\d{8,12})\b"), ("Meta Pixel", r"fbq\(\s*['\"]init['\"]\s*,\s*['\"](\d{10,20})['\"]"),
    ("Hotjar", r"hjid\s*[:=]\s*(\d{5,9})"), ("Microsoft Clarity", r"clarity\.ms/tag/([a-z0-9]{8,12})"),
    ("LinkedIn Insight", r"_linkedin_partner_id\s*=\s*['\"](\d{5,9})['\"]"),
]


def parse_trackers(domain: str, html: str, url: str) -> list[Finding]:
    out, seen = [], set()
    for label, rx in TRACKERS:
        for m in re.findall(rx, html):
            if (label, m) not in seen:
                seen.add((label, m))
                out.append(Finding(("Dominio", domain), "usa_tracciamento", ("ID tracciamento", f"{label} {m}"), 0.9, "identificativo nel codice della pagina", url=url, pivot=False))
    return out[:20]


def parse_rel_me(domain: str, html: str, url: str) -> list[Finding]:
    """rel="me" links are how people verify their own profiles (IndieWeb/Mastodon): strong identity evidence."""
    out = []
    for tag in re.findall(r"<(?:a|link)\b[^>]*>", html, flags=re.I):
        if re.search(r'rel=["\'][^"\']*\bme\b', tag, re.I) and (m := re.search(r'href=["\']([^"\']+)', tag, re.I)):
            href = urljoin(url, m.group(1))
            if href.startswith("http") and domain not in href:
                out.append(Finding(("Dominio", domain), "profilo_verificato", ("Account", href), 0.9, 'link rel="me" nella pagina', url=url, pivot=False))
    return out[:15]


def feed_links(html: str, base: str) -> list[str]:
    return [urljoin(base, m) for m in re.findall(r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*href=["\']([^"\']+)', html, re.I)][:2]


def parse_feed(domain: str, xml_text: str, url: str) -> list[Finding]:
    me, out = ("Dominio", domain), []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    names, emails = set(), set()
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        val = (el.text or "").strip()
        if tag in ("creator", "managingEditor", "webMaster", "author") and val:
            for e in EMAIL.findall(val):
                emails.add(e.lower())
            name = re.sub(r"\(?\b" + EMAIL.pattern + r"\b\)?", "", val).strip(" ()<>")
            if name and len(name) < 80:
                names.add(name)
        if tag == "email" and "@" in val:
            emails.add(val.lower())
        if tag == "name" and val and len(val) < 80:
            names.add(val)
    for n in sorted(names)[:10]:
        out.append(Finding(me, "autore_nel_feed", ("Persona", n), 0.6, "autore nel feed RSS/Atom", url=url, pivot=False))
    for e in sorted(emails)[:10]:
        if e.split("@")[-1] not in PLACEHOLDER_DOMAINS:
            out.append(Finding(me, "email_nel_feed", ("Email", e), 0.7, "indirizzo nel feed RSS/Atom", url=url))
    return out


def parse_ads_txt(domain: str, txt: str, url: str) -> list[Finding]:
    out, seen = [], set()
    for line in txt.splitlines()[:300]:
        parts = [x.strip() for x in line.split("#")[0].split(",")]
        if len(parts) >= 3 and parts[2].upper() == "DIRECT" and parts[1]:  # DIRECT = the publisher's own seller account
            key = (parts[0].lower(), parts[1])
            if key not in seen:
                seen.add(key)
                out.append(Finding(("Dominio", domain), "account_pubblicitario", ("ID tracciamento", f"ads.txt {key[0]} {key[1]}"), 0.85, "ads.txt, venditore DIRECT", url=url, pivot=False))
    return out[:20]


def parse_assetlinks(domain: str, data, url: str) -> list[Finding]:
    out = []
    for item in data if isinstance(data, list) else []:
        t = (item or {}).get("target", {})
        if t.get("namespace") == "android_app" and t.get("package_name"):
            out.append(Finding(("Dominio", domain), "app_android", ("App", f"Android: {t['package_name']}"), 0.9, "assetlinks.json", url=url, pivot=False))
    return out


def parse_aasa(domain: str, data, url: str) -> list[Finding]:
    ids = set()
    d = data if isinstance(data, dict) else {}
    for det in (d.get("applinks") or {}).get("details", []) or []:
        ids.update([det.get("appID")] if det.get("appID") else det.get("appIDs", []))
    ids.update((d.get("webcredentials") or {}).get("apps", []))
    return [Finding(("Dominio", domain), "app_ios", ("App", f"iOS: {i}"), 0.9, "apple-app-site-association", url=url, pivot=False) for i in sorted(ids)[:10] if isinstance(i, str)]


def parse_wp_users(domain: str, users, url: str) -> list[Finding]:
    out = []
    for u in users if isinstance(users, list) else []:
        if not isinstance(u, dict):
            continue
        if u.get("name"):
            out.append(Finding(("Dominio", domain), "autore_wordpress", ("Persona", u["name"]), 0.7, "utente pubblico dell'API REST di WordPress", url=url, pivot=False))
        if u.get("slug"):
            out.append(Finding(("Dominio", domain), "username_wordpress", ("Username", u["slug"]), 0.5, "slug dell'autore su WordPress (spesso lo username)", url=url, pivot=False))
        if u.get("link"):
            out.append(Finding(("Dominio", domain), "pagina_autore", ("Account", u["link"]), 0.6, "pagina autore WordPress", url=url, pivot=False))
    return out[:20]


async def _get(c: httpx.AsyncClient, url: str):
    try:
        r = await c.get(url)
    except httpx.HTTPError:
        return None
    return r if r.status_code == 200 else None


@collector("web_deep", "Dominio", active=True)
async def web_deep(domain: str) -> list[Finding]:
    out = []
    async with httpx.AsyncClient(follow_redirects=True, **HTTP) as c:
        home = await _get(c, f"https://{domain}/")
        if home is not None and "html" in home.headers.get("content-type", ""):
            html = home.text[:MAX_BODY]
            out += parse_trackers(domain, html, str(home.url)) + parse_rel_me(domain, html, str(home.url))
            for link in feed_links(html, str(home.url)):
                if (f := await _get(c, link)) is not None:
                    out += parse_feed(domain, f.text[:MAX_BODY], link)
        for path, parser, as_json in (("/ads.txt", parse_ads_txt, False), ("/.well-known/assetlinks.json", parse_assetlinks, True),
                                      ("/.well-known/apple-app-site-association", parse_aasa, True), ("/wp-json/wp/v2/users?per_page=20", parse_wp_users, True)):
            r = await _get(c, f"https://{domain}{path}")
            if r is None:
                continue
            try:
                out += parser(domain, r.json() if as_json else r.text[:MAX_BODY], str(r.url))
            except ValueError:
                pass
    return out
