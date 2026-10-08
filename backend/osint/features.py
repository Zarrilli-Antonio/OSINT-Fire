"""Tags, seed parsing, diff and timeline. Logic is in plain functions taking the DB; register() only wires the routes."""
import csv
import io
import ipaddress
import re
from datetime import date, datetime, timezone
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import i18n, settings
from .models import norm

MAX_TAGS, MAX_TAG_LEN, MAX_SEEDS = 12, 30, 500


# ---- tags ----

def set_tags(db, inv: int, eid: int, tags: list[str]) -> list[str] | None:
    """Replace the tags of an entity. None if the entity is not in [inv]; ValueError on invalid input."""
    if not db.c.execute("select 1 from entity where id=? and inv=?", (eid, inv)).fetchone():
        return None
    clean, seen = [], set()
    for t in tags:
        t = " ".join(t.split())
        if not 1 <= len(t) <= MAX_TAG_LEN:
            raise ValueError(f"a tag must be 1 to {MAX_TAG_LEN} characters")
        if t.casefold() not in seen:  # "Suspect" and "suspect" are the same tag
            seen.add(t.casefold())
            clean.append(t)
    if len(clean) > MAX_TAGS:
        raise ValueError(f"at most {MAX_TAGS} tags per entity")
    db.c.execute("delete from tag where inv=? and entity=?", (inv, eid))
    db.c.executemany("insert into tag(inv, entity, name) values (?, ?, ?)", [(inv, eid, t) for t in clean])
    db.c.commit()
    return clean


# ---- seeds from pasted text / CSV ----

_EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")
_DOMAIN = re.compile(r"^(?!-)[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$", re.I)
_PHONE = re.compile(r"^\+?\d{7,}$")
_PHONE_LINE = re.compile(r"^\+[\d ().-]+$")  # spaces allowed only when it starts with +, else "1 2" would be glued
_SPLIT = re.compile(r"[\s,;]+")
_TYPE_WORDS = {"type", "tipo", "typ"}
_VALUE_WORDS = {"value", "valore", "valor", "wert"}


def _type_names() -> dict[str, str]:
    from .main import SEED_TYPES  # late: main imports this module
    return {w.casefold(): it for it, tr in i18n.TYPES.items() if it in SEED_TYPES for w in (it, *tr)}


def _detect(tok: str) -> tuple[str, str] | None:
    if re.match(r"^https?://", tok, re.I):
        tok = urlparse(tok).hostname or ""
    if _EMAIL.match(tok):
        return "Email", tok
    if tok.startswith("@") and re.match(r"^@[\w.]+$", tok):
        return "Username", tok[1:]
    try:
        return "IP", str(ipaddress.ip_address(tok))
    except ValueError:
        pass
    if _PHONE.match(tok):
        return "Telefono", tok
    if _DOMAIN.match(tok):
        return "Dominio", tok
    return None


def parse_seeds(text: str) -> dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    names = _type_names()
    header = False
    if lines:
        first = [c.strip().casefold() for c in re.split(r"[,;\t]", lines[0])]
        if len(first) >= 2 and first[0] in _TYPE_WORDS and first[1] in _VALUE_WORDS:
            header, lines = True, lines[1:]
    seeds, skipped, seen = [], [], set()

    def add(t: str, v: str):
        v = norm(t, v)
        if v and (t, v) not in seen:
            seen.add((t, v))
            seeds.append({"type": t, "value": v})

    for line in lines:
        if header:  # explicit type column: the only way to give a Person or a Company
            row = next(csv.reader([line], delimiter="\t" if "\t" in line else ";" if ";" in line and "," not in line else ","), [])
            t = names.get(row[0].strip().casefold()) if len(row) >= 2 else None
            if t and row[1].strip():
                add(t, row[1])
            else:
                skipped.append(line)
        elif _PHONE_LINE.match(line) and sum(c.isdigit() for c in line) >= 7:
            add("Telefono", line)
        else:
            for tok in _SPLIT.split(line):
                if tok and (d := _detect(tok)):
                    add(*d)
                elif tok:
                    skipped.append(tok)
    return {"seeds": seeds[:MAX_SEEDS], "skipped": skipped[:MAX_SEEDS]}


# ---- diff ----

def diff(db, inv: int, since: float | None = None) -> dict:
    """What is new since [since] (default: the start of the last run). Manual entities and bridges never count."""
    runs = [r["ts"] for r in db.c.execute("select ts from run_log where inv=? order by ts", (inv,))]
    if since is None:
        since = runs[-1] if runs else 0.0
    nodes = [r[0] for r in db.c.execute("select id from entity where inv=? and manual=0 and added > ? order by id", (inv, since))]
    edges = [r[0] for r in db.c.execute(
        "select r.id from relation r join evidence e on e.id = r.evidence where r.inv=? and r.manual=0 and e.ts > ? order by r.id", (inv, since))]
    return {"since": since, "first_run": len(runs) <= 1, "runs": runs, "nodes": nodes, "edges": edges,
            "summary": {"entities": len(nodes), "relations": len(edges)}}


# ---- timeline ----

# Italian prefix of a Data value -> event kind
_DATA_KINDS = {"registrazione": "registration", "costituzione": "registration", "scadenza": "expiry",
               "ultima modifica": "change", "trasferimento": "change"}
_HIBP = re.compile(r"^HIBP, (\d{4}(?:-\d{2}-\d{2})?),")
_DATE = re.compile(r"^(\d{4})(?:-(\d{2})-(\d{2}))?")


def _day(s: str) -> float | None:
    """Epoch of 00:00 UTC for 'YYYY-MM-DD' (a bare year counts as 1 January)."""
    m = _DATE.match(s.strip())
    if not m:
        return None
    try:
        d = date(int(m[1]), int(m[2] or 1), int(m[3] or 1))
    except ValueError:
        return None
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


def timeline(db, inv: int, lang: str | None = None) -> dict:
    lang = lang or settings.lang()
    hidden = {r[0] for r in db.c.execute("select entity from hidden where inv=?", (inv,))}
    events, undated = [], 0

    def add(ts, kind, entity, related, label, collector=""):
        events.append({"ts": ts, "date": _iso(ts), "kind": kind, "entity": entity, "related": related, "label": label, "collector": collector})

    # dated facts hang from the entity that has them (a domain -> its Data node, an email -> its Breach)
    for r in db.c.execute(
            "select r.src, r.dst, r.reason, d.type, d.value, e.collector from relation r join entity d on d.id = r.dst "
            "join evidence e on e.id = r.evidence where r.inv=? and d.manual=0 and d.type in ('Data', 'Breach') order by r.id", (inv,)):
        if r["src"] in hidden or r["dst"] in hidden:
            continue
        if r["type"] == "Data":
            what, _, when = r["value"].rpartition(": ")
            kind = _DATA_KINDS.get(what) or ("first_seen" if what.endswith(" creato") else None)
            ts = _day(when) if kind else None
            if ts is None:
                undated += 1
                continue
            add(ts, kind, r["src"], r["dst"], i18n.label_value(r["value"], lang), r["collector"])
        elif (m := _HIBP.match(r["reason"])) or r["reason"].startswith("HIBP, ?"):
            ts = _day(m[1]) if m else None
            if ts is None:
                undated += 1
                continue
            add(ts, "breach", r["src"], r["dst"], i18n.ui("tl_breach", lang).replace("{}", r["value"]), r["collector"])
    for r in db.c.execute("select id, type, value, added from entity where inv=? and manual=1 and added > 0", (inv,)):
        if r["id"] not in hidden:
            add(r["added"], "manual", r["id"], None, i18n.ui("tl_manual", lang).replace("{}", i18n.label_value(r["value"], lang)))
    for r in db.c.execute("select ts, kind from run_log where inv=? order by id", (inv,)):
        key = f"tl_run_{r['kind']}"
        add(r["ts"], "run", None, None, i18n.ui(key, lang) if key in i18n.UI else r["kind"])
    events.sort(key=lambda e: e["ts"])
    return {"events": events, "undated": undated}


# ---- routes ----

class TagsBody(BaseModel):
    tags: list[str] = Field(max_length=100)


class SeedsText(BaseModel):
    text: str = Field(max_length=2_000_000)


def register(app: FastAPI, get_db) -> None:
    """get_db is late-bound so tests that replace main.db keep working."""

    @app.put("/investigations/{inv}/entities/{eid}/tags")
    def put_tags(inv: int, eid: int, body: TagsBody):
        try:
            tags = set_tags(get_db(), inv, eid, body.tags)
        except ValueError as e:
            raise HTTPException(422, str(e))
        if tags is None:
            raise HTTPException(404, "entity not found")
        return {"tags": tags}

    @app.post("/seeds/parse")
    def seeds_parse(body: SeedsText):
        return parse_seeds(body.text)

    @app.get("/investigations/{inv}/diff")
    def get_diff(inv: int, since: float | None = None):
        if not get_db().get_investigation(inv):
            raise HTTPException(404, "investigation not found")
        return diff(get_db(), inv, since)

    @app.get("/investigations/{inv}/timeline")
    def get_timeline(inv: int):
        if not get_db().get_investigation(inv):
            raise HTTPException(404, "investigation not found")
        return timeline(get_db(), inv)
