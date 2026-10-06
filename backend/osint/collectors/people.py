import re
import unicodedata

import httpx

from ..models import Finding
from ..settings import CFG
from . import collector
from .domain import HTTP

# Persona/Azienda lookups in open registries. Names are ambiguous: confidence stays low unless the match is exact.


def parse_gleif(name: str, j: dict) -> list[Finding]:
    out = []
    for r in j.get("data", []):
        e, lei = r["attributes"]["entity"], r["id"]
        legal = e["legalName"]["name"]
        exact = legal.lower() == name.lower()
        src, url = ("Azienda", legal), f"https://search.gleif.org/#/record/{lei}"
        out.append(Finding(("Azienda", name), "entita_legale", src, 0.7 if exact else 0.4, "registro LEI (GLEIF)", url=url, pivot=False))
        out.append(Finding(src, "codice_lei", ("Registrazione", f"LEI {lei}"), 0.95, f"stato {e.get('status')}", url=url, pivot=False))
        if e.get("registeredAs"):
            out.append(Finding(src, "registrazione_locale", ("Registrazione", f"{e.get('jurisdiction')} {e['registeredAs']}"), 0.9,
                               "numero di registro delle imprese", url=url, pivot=False))
        a = e.get("legalAddress", {})
        addr = ", ".join(x for x in (", ".join(a.get("addressLines", [])), a.get("postalCode"), a.get("city"), a.get("country")) if x)
        if addr:
            out.append(Finding(src, "sede_legale", ("Luogo", addr), 0.9, "indirizzo legale nel registro LEI", url=url, pivot=False))
    return out


@collector("gleif", "Azienda")
async def gleif(name: str) -> list[Finding]:
    async with httpx.AsyncClient(**HTTP) as c:
        r = await c.get("https://api.gleif.org/api/v1/lei-records",
                        params={"filter[entity.legalName]": name, "page[size]": 5}, headers={"Accept": "application/vnd.api+json"})
    r.raise_for_status()
    return parse_gleif(name, r.json())


def parse_orcid(name: str, j: dict) -> list[Finding]:
    out = []
    for r in (j.get("expanded-result") or [])[:5]:
        url = f"https://orcid.org/{r['orcid-id']}"
        acc = ("Account", url)
        out.append(Finding(("Persona", name), "profilo_orcid", acc, 0.35, "omonimia possibile (ORCID)", url=url, pivot=False))
        for inst in r.get("institution-name") or []:
            out.append(Finding(acc, "affiliazione", ("Azienda", inst), 0.4, "affiliazione dichiarata su ORCID", url=url, pivot=False))
    return out


@collector("orcid", "Persona")
async def orcid(name: str) -> list[Finding]:
    parts = name.split()
    if len(parts) < 2:
        return []
    async with httpx.AsyncClient(**HTTP) as c:
        r = await c.get("https://pub.orcid.org/v3.0/expanded-search/", headers={"Accept": "application/json"},
                        params={"q": f'given-names:"{parts[0]}" AND family-name:"{parts[-1]}"', "rows": 5})
    r.raise_for_status()
    return parse_orcid(name, r.json())


def parse_openalex(name: str, j: dict) -> list[Finding]:
    out = []
    for a in j.get("results", []):
        if a["display_name"].lower() != name.lower():
            continue
        url = a["id"].replace("https://openalex.org/", "https://openalex.org/authors/")
        acc = ("Account", url)
        out.append(Finding(("Persona", name), "profilo_accademico", acc, 0.4, f"autore su OpenAlex ({a.get('works_count', 0)} opere, omonimia possibile)",
                           url=url, pivot=False))
        if a.get("orcid"):
            out.append(Finding(acc, "profilo_collegato", ("Account", a["orcid"]), 0.8, "ORCID collegato in OpenAlex", url=url, pivot=False))
        for inst in a.get("last_known_institutions") or []:
            out.append(Finding(acc, "affiliazione", ("Azienda", inst["display_name"]), 0.5, "ultima affiliazione nota", url=url, pivot=False))
    return out


@collector("openalex", "Persona")
async def openalex(name: str) -> list[Finding]:
    async with httpx.AsyncClient(**HTTP) as c:
        r = await c.get("https://api.openalex.org/authors", params={"search": name, "per-page": 10})
    r.raise_for_status()
    return parse_openalex(name, r.json())


def username_candidates(name: str) -> list[str]:
    """Typical handle shapes for a person: mariorossi, mario.rossi, mario_rossi, mrossi, rossimario, mariorossi."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    parts = re.findall(r"[a-z0-9]+", ascii_name)
    if len(parts) < 2:
        return []
    f, l = parts[0], parts[-1]
    return list(dict.fromkeys([f + l, f"{f}.{l}", f"{f}_{l}", f[0] + l, l + f, f + l[0]]))


@collector("name_usernames", "Persona")
async def name_usernames(name: str) -> list[Finding]:
    """Handle guesses from a name. Weak evidence by nature (a free handle proves nothing), so they are only followed
    when `auto_username_from_name` is on; otherwise expand the ones you like from the UI."""
    follow = CFG["auto_username_from_name"]
    return [Finding(("Persona", name), "username_ipotetico", ("Username", u), 0.2, "combinazione nome e cognome (ipotesi)", pivot=follow)
            for u in username_candidates(name)]
