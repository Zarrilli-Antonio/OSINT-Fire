"""Companies, organisations and public records: SEC EDGAR, USAspending, ICIJ Offshore Leaks, sanctions lists, VIES, DBpedia, Nominatim, Open Library, CourtListener.

Name-only matches (people, ICIJ, sanctions, courts, books) are weak evidence of a homonym: confidence stays <= 0.3 and the reason says so."""
import asyncio
import csv
import io
import json
import re
import time
import unicodedata
import xml.etree.ElementTree as ET

import httpx

from ..models import Finding
from . import collector
from .domain import HTTP

NAME_ONLY = "corrispondenza sul nome, non verificata"
SUFFIX = {"inc", "corp", "corporation", "ltd", "llc", "spa", "srl", "sa", "plc", "co", "company", "limited", "gmbh", "ag", "bv", "nv", "the", "sas", "snc"}


def name_key(s: str) -> str:
    """Accent/case/punctuation/order-insensitive key ('ROSSI, Mario' == 'Mario Rossi'; corporate suffixes dropped)."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    toks = [t for t in re.findall(r"[a-z0-9]+", s) if t not in SUFFIX]
    return " ".join(sorted(toks))


def same(a: str, b: str) -> bool:
    k = name_key(a)
    return len(k) >= 5 and k == name_key(b)


def ua() -> dict:  # SEC and OSM want a descriptive User-Agent: the one from the settings plus the tool name
    return {"User-Agent": f"{HTTP['headers']['User-Agent']} OSINT-Fire"}


def client(**kw) -> httpx.AsyncClient:
    return httpx.AsyncClient(**{**HTTP, "headers": {**HTTP["headers"], **ua()}, "follow_redirects": True, **kw})


# ---- SEC EDGAR ----------------------------------------------------------------------------------------------------------------------------------------

def parse_sec_entities(name: str, j: dict) -> list[str]:
    """CIKs (10 digits) of hits whose name (without the '(TICKER)' tail) equals the searched one."""
    out = []
    for h in (j.get("hits") or {}).get("hits") or []:
        ent = re.sub(r"\s*\([^)]*\)\s*$", "", (h.get("_source") or {}).get("entity") or "")
        if same(ent, name) and str(h.get("_id", "")).isdigit():
            out.append(str(h["_id"]).zfill(10))
    return out[:3]


def parse_sec_submission(name: str, d: dict) -> list[Finding]:
    me, cik = ("Azienda", name), d.get("cik", "")
    if not cik:
        return []
    url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}"
    out = [Finding(me, "numero_registro", ("Registrazione", f"SEC CIK {cik} — {d.get('name', '')}"), 0.7, "iscrizione alla SEC (EDGAR)", url=url, pivot=False)]
    if d.get("ein"):
        out.append(Finding(me, "numero_registro", ("Registrazione", f"EIN {d['ein']}"), 0.7, "iscrizione alla SEC (EDGAR)", url=url, pivot=False))
    b = (d.get("addresses") or {}).get("business") or {}
    addr = ", ".join(str(b[k]) for k in ("street1", "street2", "city", "stateOrCountry", "zipCode") if b.get(k))
    if addr:
        out.append(Finding(me, "sede", ("Luogo", addr), 0.7, "indirizzo commerciale in EDGAR", url=url, pivot=False))
    for t in d.get("tickers") or []:
        out.append(Finding(me, "ticker", ("Servizio", f"ticker {t}"), 0.7, "iscrizione alla SEC (EDGAR)", url=url, pivot=False))
    if d.get("website"):
        out.append(Finding(me, "sito_dichiarato", ("Dominio", re.sub(r"^https?://|/.*$", "", d["website"]).removeprefix("www.")), 0.7, "sito indicato in EDGAR", url=url))
    r = (d.get("filings") or {}).get("recent") or {}
    for form, acc, doc in list(zip(r.get("form", []), r.get("accessionNumber", []), r.get("primaryDocument", [])))[:3]:
        out.append(Finding(me, "deposito_sec", ("Documento", f"{form} {acc}"), 0.7, "documento depositato presso la SEC",
                           url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{doc}", pivot=False))
    return out


@collector("sec_edgar", "Azienda")
async def sec_edgar(name: str) -> list[Finding]:
    out: list[Finding] = []
    async with client() as c:
        r = await c.get("https://efts.sec.gov/LATEST/search-index", params={"keysTyped": name})
        r.raise_for_status()
        for cik in parse_sec_entities(name, r.json())[:1]:  # the best exact match only
            s = await c.get(f"https://data.sec.gov/submissions/CIK{cik}.json")
            if s.status_code == 404:
                continue
            s.raise_for_status()
            out += parse_sec_submission(name, s.json())
    return out


# ---- USAspending ----------------------------------------------------------------------------------------------------------------------------------------

def parse_usaspending(name: str, j: dict) -> list[Finding]:
    out = []
    for x in (j.get("results") or [])[:50]:
        if same(x.get("name") or "", name) and x.get("uei"):
            out.append(Finding(("Azienda", name), "numero_registro", ("Registrazione", f"UEI {x['uei']} — {x['name']}"), 0.6, "beneficiario di fondi federali USA (USAspending)",
                               url=f"https://www.usaspending.gov/recipient/{x['id']}/latest", raw={"amount": x.get("amount")}, pivot=False))
    return out[:5]


@collector("usaspending", "Azienda")
async def usaspending(name: str) -> list[Finding]:
    async with client() as c:
        r = await c.post("https://api.usaspending.gov/api/v2/recipient/", json={"keyword": name, "limit": 10, "page": 1, "sort": "amount", "order": "desc"})
    if r.status_code in (400, 404):
        return []
    r.raise_for_status()
    return parse_usaspending(name, r.json())


# ---- ICIJ Offshore Leaks --------------------------------------------------------------------------------------------------------------------------------

def parse_icij(kind: str, name: str, j: dict) -> list[Finding]:
    out = []
    for x in ((j.get("q0") or {}).get("result") or [])[:10]:
        if same(x.get("name") or "", name):
            out.append(Finding((kind, name), "citato_in_inchiesta", ("Evento", f"ICIJ Offshore Leaks: {x['name']}"), 0.3, NAME_ONLY,
                               url=f"https://offshoreleaks.icij.org/nodes/{x['id']}", raw={"description": x.get("description"), "score": x.get("score")}, pivot=False))
    return out[:5]


async def _icij(kind: str, name: str) -> list[Finding]:
    async with client() as c:
        r = await c.post("https://offshoreleaks.icij.org/api/v1/reconcile", data={"queries": json.dumps({"q0": {"query": name, "limit": 10}})})
    if r.status_code in (400, 404):
        return []
    r.raise_for_status()
    return parse_icij(kind, name, r.json())


@collector("icij_offshore", "Persona")
async def icij_person(name: str) -> list[Finding]:
    return await _icij("Persona", name)


@collector("icij_offshore", "Azienda")
async def icij_company(name: str) -> list[Finding]:
    return await _icij("Azienda", name)


# ---- sanctions lists (OFAC SDN, EU consolidated, UN Security Council), matched locally ------------------------------------------------------------------

LISTS = {
    "OFAC SDN": "https://www.treasury.gov/ofac/downloads/sdn.csv",
    "UE": "https://webgate.ec.europa.eu/fsd/fsf/public/files/csvFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw",
    "ONU": "https://scsanctions.un.org/resources/xml/en/consolidated.xml",
}
PAGES = {"OFAC SDN": "https://sanctionssearch.ofac.treas.gov/", "UE": "https://www.sanctionsmap.eu/", "ONU": "https://main.un.org/securitycouncil/en/content/un-sc-consolidated-list"}
TTL = 24 * 3600
_sanc = {"ts": 0.0, "idx": {}}


def parse_ofac(text: str):
    for r in csv.reader(io.StringIO(text)):
        if len(r) > 3 and r[1].strip():
            yield r[0].strip(), r[1].strip(), r[3].strip().strip("-0 ")


def parse_eu(text: str):
    for r in csv.DictReader(io.StringIO(text.lstrip("﻿")), delimiter=";"):
        if (r.get("NameAlias_WholeName") or "").strip():
            yield r.get("Entity_LogicalId", ""), r["NameAlias_WholeName"].strip(), r.get("Entity_Regulation_Programme", "")


def parse_un(text: str):
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return
    for e in list(root.iter("INDIVIDUAL")) + list(root.iter("ENTITY")):
        g = lambda t: (e.findtext(t) or "").strip()  # noqa: E731
        ref, prog = g("REFERENCE_NUMBER") or g("DATAID"), g("UN_LIST_TYPE")
        main = " ".join(g(t) for t in ("FIRST_NAME", "SECOND_NAME", "THIRD_NAME", "FOURTH_NAME") if g(t))
        for n in [main] + [(a.text or "").strip() for a in e.iter("ALIAS_NAME")]:
            if n:
                yield ref, n, prog


PARSERS = {"OFAC SDN": parse_ofac, "UE": parse_eu, "ONU": parse_un}


def build_index(texts: dict[str, str]) -> dict[str, list]:
    idx: dict[str, list] = {}
    for lst, text in texts.items():
        for ref, name, prog in PARSERS[lst](text):
            k = name_key(name)
            if len(k) >= 5:
                idx.setdefault(k, []).append((lst, ref, name, prog))
    return idx


async def fetch_lists() -> dict[str, str]:  # replaced in tests
    texts, err = {}, None
    async with client(timeout=120) as c:
        for lst, url in LISTS.items():
            try:
                r = await c.get(url)
                r.raise_for_status()
                texts[lst] = r.text
            except httpx.HTTPError as e:  # one list down must not hide the others
                err = e
    if not texts and err:
        raise err
    return texts


async def sanctions_index() -> dict[str, list]:
    if time.time() - _sanc["ts"] > TTL or not _sanc["idx"]:
        _sanc.update(idx=await asyncio.to_thread(build_index, await fetch_lists()), ts=time.time())
    return _sanc["idx"]


def parse_sanctions(kind: str, name: str, idx: dict) -> list[Finding]:
    out, seen = [], set()
    for lst, ref, listed, prog in idx.get(name_key(name), [])[:20]:
        if (lst, ref) in seen:
            continue
        seen.add((lst, ref))
        out.append(Finding((kind, name), "in_lista_sanzioni", ("Evento", f"sanzioni {lst}: {listed}"), 0.3, NAME_ONLY, url=PAGES[lst], raw={"ref": ref, "programme": prog}, pivot=False))
    return out[:5]


@collector("sanctions", "Persona")
async def sanctions_person(name: str) -> list[Finding]:
    return parse_sanctions("Persona", name, await sanctions_index())


@collector("sanctions", "Azienda")
async def sanctions_company(name: str) -> list[Finding]:
    return parse_sanctions("Azienda", name, await sanctions_index())


# ---- VIES VAT validation ----------------------------------------------------------------------------------------------------------------------------------

VAT = re.compile(r"^(AT|BE|BG|CY|CZ|DE|DK|EE|EL|ES|FI|FR|HR|HU|IE|IT|LT|LU|LV|MT|NL|PL|PT|RO|SE|SI|SK|XI)([0-9A-Z+*]{8,12})$")


def vat_id(value: str) -> tuple[str, str] | None:
    m = VAT.match(re.sub(r"[\s.\-]", "", value).upper())
    return (m.group(1), m.group(2)) if m else None


def parse_vies(value: str, j: dict) -> list[Finding]:
    if not j.get("isValid"):
        return []
    me, vat = ("Azienda", value), f"{j.get('countryCode') or ''}{j.get('vatNumber', '')}"
    url = "https://ec.europa.eu/taxation_customs/vies/"
    out = [Finding(me, "numero_registro", ("Registrazione", f"VIES {vat}"), 0.9, "partita IVA valida nel sistema VIES", url=url, pivot=False)]
    nm, ad = (j.get("name") or "").strip(), re.sub(r"\s*\n\s*", ", ", (j.get("address") or "").strip())
    if nm and nm != "---":
        out.append(Finding(me, "nome_organizzazione", ("Azienda", nm), 0.9, "ragione sociale in VIES", url=url))
    if ad and ad != "---":
        out.append(Finding(me, "indirizzo_registrato", ("Luogo", ad), 0.9, "indirizzo in VIES", url=url, pivot=False))
    return out


async def _vies(value: str) -> list[Finding]:
    cc = vat_id(value)
    if not cc:
        return []
    async with client() as c:
        r = await c.get(f"https://ec.europa.eu/taxation_customs/vies/rest-api/ms/{cc[0]}/vat/{cc[1]}")
    if r.status_code in (400, 404):
        return []
    r.raise_for_status()
    j = r.json()
    if "UNAVAILABLE" in str(j.get("userError", "")) or "BUSY" in str(j.get("userError", "")):
        raise RuntimeError(f"VIES: {j['userError']}")
    j["countryCode"] = cc[0]
    return parse_vies(value, j)


@collector("vies", "Azienda")
async def vies(value: str) -> list[Finding]:
    return await _vies(value)


# ---- DBpedia lookup -------------------------------------------------------------------------------------------------------------------------------------

DBP_TYPES = {"Persona": {"Person"}, "Azienda": {"Organisation", "Company"}, "Luogo": {"Place", "Settlement", "Country"}}
B = re.compile(r"</?B>")


def parse_dbpedia(kind: str, name: str, j: dict) -> list[Finding]:
    out = []
    for d in (j.get("docs") or [])[:20]:
        label, res = B.sub("", (d.get("label") or [""])[0]), (d.get("resource") or [""])[0]
        if res and same(label, name) and DBP_TYPES[kind] & set(d.get("typeName") or []):
            out.append(Finding((kind, name), "voce_dbpedia", ("Documento", res), 0.3 if kind == "Persona" else 0.5,
                               NAME_ONLY if kind == "Persona" else "voce DBpedia con lo stesso nome", url=res, raw={"comment": B.sub("", (d.get("comment") or [""])[0])}, pivot=False))
    return out[:3]


async def _dbpedia(kind: str, name: str) -> list[Finding]:
    async with client() as c:
        r = await c.get("https://lookup.dbpedia.org/api/search", params={"query": name, "maxResults": 10, "format": "json"}, headers={"Accept": "application/json"})
    r.raise_for_status()
    return parse_dbpedia(kind, name, r.json())


@collector("dbpedia", "Persona")
async def dbpedia_person(name: str) -> list[Finding]:
    return await _dbpedia("Persona", name)


@collector("dbpedia", "Azienda")
async def dbpedia_company(name: str) -> list[Finding]:
    return await _dbpedia("Azienda", name)


@collector("dbpedia", "Luogo")
async def dbpedia_place(name: str) -> list[Finding]:
    return await _dbpedia("Luogo", name)


# ---- OpenStreetMap Nominatim ----------------------------------------------------------------------------------------------------------------------------

_nom = {"t": 0.0}
_nom_lock = asyncio.Lock()


def parse_nominatim(place: str, j: list) -> list[Finding]:
    out, me = [], ("Luogo", place)
    for i, x in enumerate(j[:3] if isinstance(j, list) else []):
        conf, url = (0.7 if i == 0 else 0.4), f"https://www.openstreetmap.org/{x.get('osm_type')}/{x.get('osm_id')}"
        addr = x.get("display_name") or ""
        if addr and addr != place:
            out.append(Finding(me, "indirizzo_normalizzato", ("Luogo", addr), conf, "indirizzo normalizzato da OpenStreetMap", url=url, pivot=False))
        if x.get("lat") and x.get("lon"):
            out.append(Finding(me, "coordinate", ("Luogo", f"{float(x['lat']):.6f}, {float(x['lon']):.6f}"), conf, "coordinate da OpenStreetMap", url=url, pivot=False))
        if i == 0 and (cn := (x.get("address") or {}).get("country")):
            out.append(Finding(me, "paese", ("Luogo", cn), conf, "paese da OpenStreetMap", url=url, pivot=False))
    return out


@collector("nominatim", "Luogo")
async def nominatim(place: str) -> list[Finding]:
    async with _nom_lock:  # usage policy: at most 1 request per second
        await asyncio.sleep(max(0.0, 1.1 - (time.time() - _nom["t"])))
        try:
            async with client() as c:
                r = await c.get("https://nominatim.openstreetmap.org/search", params={"q": place, "format": "jsonv2", "addressdetails": 1, "limit": 3})
        finally:
            _nom["t"] = time.time()
    r.raise_for_status()
    return parse_nominatim(place, r.json())


# ---- Open Library authors ---------------------------------------------------------------------------------------------------------------------------------

def parse_openlibrary(name: str, j: dict) -> list[Finding]:
    out, me = [], ("Persona", name)
    for d in (j.get("docs") or [])[:10]:
        if not any(same(n, name) for n in [d.get("name") or ""] + list(d.get("alternate_names") or [])[:30]):
            continue
        url = f"https://openlibrary.org/authors/{d['key']}"
        out.append(Finding(me, "pagina_autore", ("Documento", f"Open Library: {d.get('name')}"), 0.3, NAME_ONLY, url=url, raw={"work_count": d.get("work_count"), "birth": d.get("birth_date")}, pivot=False))
        if d.get("top_work"):
            out.append(Finding(me, "opera_nota", ("Documento", d["top_work"]), 0.3, NAME_ONLY, url=url, pivot=False))
        if len(out) >= 6:
            break
    return out


@collector("openlibrary", "Persona")
async def openlibrary(name: str) -> list[Finding]:
    async with client() as c:
        r = await c.get("https://openlibrary.org/search/authors.json", params={"q": name, "limit": 5})
    r.raise_for_status()
    return parse_openlibrary(name, r.json())


# ---- CourtListener (public opinion search, no token) ----------------------------------------------------------------------------------------------------

def parse_courtlistener(kind: str, name: str, j: dict) -> list[Finding]:
    out = []
    for x in (j.get("results") or [])[:5]:
        if x.get("caseName") and x.get("absolute_url"):
            out.append(Finding((kind, name), "menzionato_in", ("Documento", f"{x['caseName']} ({x.get('court', '')}, {x.get('dateFiled', '')})"), 0.2,
                                "il nome compare in una sentenza USA, solo corrispondenza sul nome", url="https://www.courtlistener.com" + x["absolute_url"], pivot=False))
    return out


async def _courts(kind: str, name: str) -> list[Finding]:
    async with client() as c:
        r = await c.get("https://www.courtlistener.com/api/rest/v4/search/", params={"q": f'"{name}"', "type": "o", "page_size": 5})
    if r.status_code in (401, 403):  # a token became mandatory: nothing we may do keyless
        return []
    r.raise_for_status()
    return parse_courtlistener(kind, name, r.json())


@collector("courtlistener", "Persona")
async def courts_person(name: str) -> list[Finding]:
    return await _courts("Persona", name)


@collector("courtlistener", "Azienda")
async def courts_company(name: str) -> list[Finding]:
    return await _courts("Azienda", name)
