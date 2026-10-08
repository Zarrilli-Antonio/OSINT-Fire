"""Academic and publication sources for a person's name (arXiv, Crossref, Europe PMC, PubMed, INSPIRE-HEP, Semantic Scholar, Zenodo, OpenAIRE) and Software Heritage for usernames.
Name matches are weak evidence (several people share a name): confidence <= 0.4 and the reason says so. DBLP was skipped: it serves an anti-bot challenge to API clients."""
import asyncio
import re
import unicodedata
import xml.etree.ElementTree as ET

import httpx

from ..models import Finding
from . import collector
from .domain import HTTP

LIMIT, CO_LIMIT = 15, 30  # documents / co-authors per source
WEAK = 0.3


def _tok(s: str) -> list[str]:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    if "," in s:  # "Last, First" -> "First Last"
        a, b = s.split(",", 1)
        s = f"{b} {a}"
    return re.findall(r"[a-z0-9]+", s)


def same_person(a: str, b: str) -> bool:
    """Same last name and same first initial (handles 'Last, First' and middle names)."""
    ta, tb = _tok(a), _tok(b)
    return len(ta) > 1 and len(tb) > 1 and ta[-1] == tb[-1] and ta[0][0] == tb[0][0]


def _valid(name: str) -> bool:
    return len(_tok(name)) >= 2


def papers(name: str, src: str, rows: list[tuple[str, str, str, list[str]]]) -> list[Finding]:
    """rows: (title, doi, url, authors) -> autore_di + collaboratore findings. Only rows where [name] is among the authors."""
    me, out, co = ("Persona", name), [], set()
    for title, doi, url, authors in rows[:LIMIT]:
        if not title or not any(same_person(name, a) for a in authors):
            continue
        doc = ("Documento", f"{title.strip()} ({doi})" if doi else title.strip())
        url = url or (f"https://doi.org/{doi}" if doi else "")
        out.append(Finding(me, "autore_di", doc, WEAK, f"autore su {src}: corrispondenza sul nome (omonimia possibile)", url=url, raw={"doi": doi}, pivot=False))
        for a in authors:
            if not same_person(name, a) and a.strip() and a not in co and len(co) < CO_LIMIT:
                co.add(a)
                out.append(Finding(me, "collaboratore", ("Persona", a.strip()), 0.25, f"coautore su {src}: corrispondenza sul nome (omonimia possibile)", url=url, pivot=False))
    return out


def _orcid(s: str) -> str | None:
    m = re.search(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", s or "")
    return f"https://orcid.org/{m[0]}" if m else None


async def _get(url: str, **kw) -> httpx.Response:
    async with httpx.AsyncClient(follow_redirects=True, **HTTP) as c:
        r = await c.get(url, **kw)
    if r.status_code != 404:
        r.raise_for_status()
    return r


# ---- arXiv (Atom) ----
def parse_arxiv(name: str, xml: str) -> list[Finding]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    rows = [(" ".join((e.findtext("a:title", "", ns) or "").split()), "", e.findtext("a:id", "", ns) or "",
             [a.findtext("a:name", "", ns) or "" for a in e.findall("a:author", ns)]) for e in root.findall("a:entry", ns)]
    return papers(name, "arXiv", rows)


@collector("arxiv", "Persona")
async def arxiv(name: str) -> list[Finding]:
    if not _valid(name):
        return []
    r = await _get("https://export.arxiv.org/api/query", params={"search_query": f'au:"{name}"', "max_results": LIMIT, "sortBy": "submittedDate"})
    return parse_arxiv(name, r.text) if r.status_code == 200 else []


# ---- Crossref ----
def parse_crossref(name: str, j: dict) -> list[Finding]:
    items = (j.get("message") or {}).get("items") or []
    rows = [((i.get("title") or [""])[0], i.get("DOI", ""), i.get("URL", ""), [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in i.get("author") or []]) for i in items]
    out = papers(name, "Crossref", rows)
    seen = set()
    for i in items:  # an ORCID iD attached to the matching author of a record
        for a in i.get("author") or []:
            o = _orcid(a.get("ORCID", ""))
            if o and o not in seen and same_person(name, f"{a.get('given', '')} {a.get('family', '')}"):
                seen.add(o)
                out.append(Finding(("Persona", name), "profilo_accademico", ("Account", o), 0.4, f"ORCID iD indicato su {i.get('DOI', 'Crossref')} (Crossref): corrispondenza sul nome (omonimia possibile)", url=o, pivot=False))
    return out


@collector("crossref", "Persona")
async def crossref(name: str) -> list[Finding]:
    if not _valid(name):
        return []
    r = await _get("https://api.crossref.org/works", params={"query.author": name, "rows": LIMIT, "select": "DOI,title,author,URL"}, timeout=45)
    return parse_crossref(name, r.json()) if r.status_code == 200 else []


# ---- Europe PMC / PubMed (author written "Last F") ----
def _lastf(name: str) -> str:
    t = _tok(name)
    return f"{t[-1]} {t[0][0]}"


def _abbr(s: str) -> list[str]:  # "Bengio Y, Hinton G." -> ["Bengio Y", "Hinton G"]
    return [x.strip(" .") for x in s.split(",") if x.strip(" .")]


def _abbr_papers(name: str, src: str, rows: list[tuple[str, str, str, list[str]]]) -> list[Finding]:
    # abbreviated authors ("LeCun Y") cannot go through same_person (first name is an initial): compare "last initial" directly
    key = _lastf(name).split()
    me, out, co = ("Persona", name), [], set()
    for title, doi, url, authors in rows[:LIMIT]:
        if not title or not any(_tok(a)[:2] == key for a in authors):
            continue
        doc = ("Documento", f"{title.strip()} ({doi})" if doi else title.strip())
        out.append(Finding(me, "autore_di", doc, WEAK, f"autore su {src}: corrispondenza sul nome (omonimia possibile)", url=url, raw={"doi": doi}, pivot=False))
        for a in authors:
            if _tok(a)[:2] != key and a not in co and len(co) < CO_LIMIT:
                co.add(a)
                out.append(Finding(me, "collaboratore", ("Persona", a), 0.25, f"coautore su {src}: corrispondenza sul nome (omonimia possibile)", url=url, pivot=False))
    return out


def parse_europepmc(name: str, j: dict) -> list[Finding]:
    rows = [(r.get("title", ""), r.get("doi", ""), f"https://europepmc.org/article/{r.get('source', 'MED')}/{r.get('id', '')}", _abbr(r.get("authorString", "")))
            for r in (j.get("resultList") or {}).get("result") or []]
    return _abbr_papers(name, "Europe PMC", rows)


@collector("europepmc", "Persona")
async def europepmc(name: str) -> list[Finding]:
    if not _valid(name):
        return []
    r = await _get("https://www.ebi.ac.uk/europepmc/webservices/rest/search", params={"query": f'AUTH:"{_lastf(name).title()}"', "format": "json", "pageSize": LIMIT, "resultType": "lite"})
    return parse_europepmc(name, r.json()) if r.status_code == 200 else []


def parse_pubmed(name: str, j: dict) -> list[Finding]:
    res = j.get("result") or {}
    rows = []
    for uid in res.get("uids") or []:
        d = res[uid]
        doi = next((x["value"] for x in d.get("articleids", []) if x.get("idtype") == "doi"), "")
        rows.append((d.get("title", ""), doi, f"https://pubmed.ncbi.nlm.nih.gov/{uid}/", [a["name"] for a in d.get("authors", []) if a.get("name")]))
    return _abbr_papers(name, "PubMed", rows)


@collector("pubmed", "Persona")
async def pubmed(name: str) -> list[Finding]:
    if not _valid(name):
        return []
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    ids = (await _get(base + "esearch.fcgi", params={"db": "pubmed", "term": f"{_lastf(name)}[Author]", "retmode": "json", "retmax": LIMIT})).json()["esearchresult"].get("idlist") or []
    if not ids:
        return []
    await asyncio.sleep(0.4)  # NCBI allows 3 requests/s without a key
    return parse_pubmed(name, (await _get(base + "esummary.fcgi", params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"})).json())


# ---- INSPIRE-HEP (author records) ----
def parse_inspire(name: str, j: dict) -> list[Finding]:
    me, out = ("Persona", name), []
    for h in ((j.get("hits") or {}).get("hits") or [])[:5]:
        m = h.get("metadata") or {}
        n = m.get("name") or {}
        if not same_person(name, n.get("preferred_name") or n.get("value") or ""):
            continue
        url = f"https://inspirehep.net/authors/{h.get('id')}"
        acc = ("Account", url)
        out.append(Finding(me, "profilo_accademico", acc, WEAK, f"autore su INSPIRE-HEP: corrispondenza sul nome (omonimia possibile)", url=url, pivot=False))
        for i in m.get("ids") or []:
            if i.get("schema") == "ORCID" and (o := _orcid(i.get("value", ""))):
                out.append(Finding(acc, "profilo_collegato", ("Account", o), 0.4, "ORCID indicato nel profilo INSPIRE-HEP", url=url, pivot=False))
        for p in [p for p in m.get("positions") or [] if p.get("current")][:3]:
            if p.get("institution"):
                out.append(Finding(acc, "affiliato_a", ("Azienda", p["institution"]), 0.35, f"affiliazione su INSPIRE-HEP: corrispondenza sul nome (omonimia possibile)", url=url, pivot=False))
    return out


@collector("inspirehep", "Persona")
async def inspirehep(name: str) -> list[Finding]:
    if not _valid(name):
        return []
    r = await _get("https://inspirehep.net/api/authors", params={"q": f'name "{name}"', "size": 5, "fields": "name,ids,positions"})
    return parse_inspire(name, r.json()) if r.status_code == 200 else []


# ---- Semantic Scholar (strict rate limit: one request at a time) ----
_ss_lock = asyncio.Lock()


def parse_semanticscholar(name: str, j: dict) -> list[Finding]:
    me, out = ("Persona", name), []
    for a in (j.get("data") or [])[:8]:
        if not same_person(name, a.get("name", "")):
            continue
        url = a.get("url") or f"https://www.semanticscholar.org/author/{a.get('authorId')}"
        acc = ("Account", url)
        out.append(Finding(me, "profilo_accademico", acc, WEAK, f"autore su Semantic Scholar: corrispondenza sul nome (omonimia possibile)", url=url, raw={"papers": a.get("paperCount")}, pivot=False))
        for d in (a.get("externalIds") or {}).get("DBLP") or []:
            u = "https://dblp.org/search?q=" + d.replace(" ", "+")
            out.append(Finding(acc, "profilo_collegato", ("Account", u), 0.3, "identificativo DBLP indicato da Semantic Scholar", url=u, pivot=False))
        for af in (a.get("affiliations") or [])[:3]:
            out.append(Finding(acc, "affiliato_a", ("Azienda", af), 0.3, f"affiliazione su Semantic Scholar: corrispondenza sul nome (omonimia possibile)", url=url, pivot=False))
        if a.get("homepage"):
            out.append(Finding(acc, "sito_dichiarato", ("Dominio", re.sub(r"^\w+://|[/:?#].*$", "", a["homepage"])), 0.3, "pagina personale indicata su Semantic Scholar", url=a["homepage"], pivot=False))
    return out


@collector("semanticscholar", "Persona")
async def semanticscholar(name: str) -> list[Finding]:
    if not _valid(name):
        return []
    async with _ss_lock:
        r = await _get("https://api.semanticscholar.org/graph/v1/author/search", params={"query": name, "limit": 8, "fields": "name,affiliations,externalIds,paperCount,homepage,url"})
        await asyncio.sleep(1.1)
    return parse_semanticscholar(name, r.json()) if r.status_code == 200 else []


# ---- Zenodo ----
def parse_zenodo(name: str, j: dict) -> list[Finding]:
    rows, out = [], []
    for h in (j.get("hits") or {}).get("hits") or []:
        m = h.get("metadata") or {}
        rows.append((m.get("title", ""), m.get("doi") or h.get("doi") or "", (h.get("links") or {}).get("self_html", ""), [c.get("name", "") for c in m.get("creators") or []]))
        for c in m.get("creators") or []:
            if same_person(name, c.get("name", "")):
                if o := _orcid(c.get("orcid", "")):
                    out.append(Finding(("Persona", name), "profilo_accademico", ("Account", o), 0.4, f"ORCID iD indicato su Zenodo: corrispondenza sul nome (omonimia possibile)", url=o, pivot=False))
                if c.get("affiliation"):
                    out.append(Finding(("Persona", name), "affiliato_a", ("Azienda", c["affiliation"]), 0.3, f"affiliazione su Zenodo: corrispondenza sul nome (omonimia possibile)", url=rows[-1][2], pivot=False))
    return papers(name, "Zenodo", rows) + out


@collector("zenodo", "Persona")
async def zenodo(name: str) -> list[Finding]:
    if not _valid(name):
        return []
    r = await _get("https://zenodo.org/api/records", params={"q": f'creators.name:"{name}"', "size": LIMIT})
    return parse_zenodo(name, r.json()) if r.status_code == 200 else []


# ---- OpenAIRE graph ----
def parse_openaire(name: str, j: dict) -> list[Finding]:
    rows = []
    for r in j.get("results") or []:
        doi = next((p["value"] for p in r.get("pids") or [] if p.get("scheme") == "doi"), "")
        url = next((u for i in r.get("instances") or [] for u in i.get("urls") or []), "")
        rows.append((r.get("mainTitle") or "", doi, url, [a.get("fullName", "") for a in r.get("authors") or []]))
    return papers(name, "OpenAIRE", rows)


@collector("openaire", "Persona")
async def openaire(name: str) -> list[Finding]:
    if not _valid(name):
        return []
    r = await _get("https://api.openaire.eu/graph/v1/researchProducts", params={"authorFullName": name, "pageSize": LIMIT})
    return parse_openaire(name, r.json()) if r.status_code == 200 else []


# ---- Software Heritage: archived source-code origins owned by a username ----
def parse_swh(user: str, origins: list) -> list[Finding]:
    out = []
    for o in origins[:50]:
        m = re.match(r"^https?://(?:www\.)?(github\.com|gitlab\.com|bitbucket\.org|codeberg\.org)/([^/]+)/([^/]+)", o.get("url", "") if isinstance(o, dict) else "")
        if m and m[2].lower() == user.lower() and o.get("has_visits"):
            out.append(Finding(("Username", user), "autore_di", ("Documento", f"{m[1]}/{m[2]}/{m[3]}"), 0.45, "repository di codice sorgente archiviato in Software Heritage (stesso nome utente)", url=o["url"], pivot=False))
    return out


@collector("softwareheritage", "Username")
async def softwareheritage(user: str) -> list[Finding]:
    if not re.fullmatch(r"[\w.-]{2,40}", user):
        return []
    r = await _get(f"https://archive.softwareheritage.org/api/1/origin/search/github.com%2F{user}%2F/", params={"limit": 100, "with_visit": "true"})
    return parse_swh(user, r.json()) if r.status_code == 200 and isinstance(r.json(), list) else []
