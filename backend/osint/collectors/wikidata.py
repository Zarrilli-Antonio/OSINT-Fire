from urllib.parse import urlparse

import httpx

from ..models import Finding
from . import collector
from .domain import HTTP

API = "https://www.wikidata.org/w/api.php"
# property -> (relation, entity type). Official website, GitHub, Twitter/X, Instagram usernames.
PROPS = {"P856": ("sito_ufficiale", "Dominio"), "P2037": ("account_github", "Username"),
         "P2002": ("account_twitter", "Username"), "P2003": ("account_instagram", "Username")}


async def _lookup(kind: str, name: str) -> list[Finding]:
    async with httpx.AsyncClient(**HTTP) as c:
        r = await c.get(API, params={"action": "wbsearchentities", "search": name, "language": "it", "uselang": "it",
                                     "type": "item", "limit": 3, "format": "json"})
        r.raise_for_status()
        hits = r.json().get("search", [])
        out, exact = [], []
        for h in hits:
            is_exact = h.get("label", "").lower() == name.lower()
            if is_exact:
                exact.append(h)
            out.append(Finding((kind, name), "voce_wikidata", ("Wikidata", f"{h['id']} · {h.get('label', '')} — {h.get('description', '')}"),
                               0.6 if is_exact else 0.3, "corrispondenza per nome su Wikidata (omonimi possibili)", url=h["concepturi"],
                               pivot=False))
        conf = 0.55 if len(exact) == 1 else 0.4  # several exact labels = homonyms, trust less
        for best in exact:  # only follow claims of exact-label matches
            e = (await c.get(f"https://www.wikidata.org/wiki/Special:EntityData/{best['id']}.json")).json()
            claims = e["entities"][best["id"]]["claims"]
            for prop, (rel, dst_type) in PROPS.items():
                for cl in claims.get(prop, []):
                    v = cl["mainsnak"].get("datavalue", {}).get("value")
                    if not isinstance(v, str):
                        continue
                    if dst_type == "Dominio":
                        v = (urlparse(v).hostname or "").removeprefix("www.")
                    if v:
                        out.append(Finding((kind, name), rel, (dst_type, v), conf,
                                           f"dato Wikidata {best['id']} ({prop})", url=best["concepturi"]))
        return out


@collector("wikidata", "Persona")
async def wikidata_person(name: str) -> list[Finding]:
    return await _lookup("Persona", name)


@collector("wikidata", "Azienda")
async def wikidata_company(name: str) -> list[Finding]:
    return await _lookup("Azienda", name)
