"""Archive: a lossless, versioned JSON copy of one investigation, and the importer that brings it back (also GraphML and the plain json export)."""
import base64
import binascii
import hashlib
import json
import time
import xml.etree.ElementTree as ET

from fastapi import HTTPException, Request

from .models import norm

VERSION = 1
MAX_BODY = 100 * 1024 * 1024
STR = 4000  # cap for any free-text field
SHORT = 200  # cap for names, types, collectors


class Bad(ValueError):
    pass


def build(db, inv: int, meta: dict) -> dict:
    """The whole investigation (hidden nodes included). Never settings, keys or the collector cache."""
    c, d = db.c, db.investigation_detail(inv)
    rows = lambda q: [dict(r) for r in c.execute(q, (inv,))]  # noqa: E731
    ents = rows("select id, type, value, added, manual from entity where inv=?")
    for e in ents:
        e["manual"] = bool(e["manual"])
    rels = [{**r, "manual": bool(r["manual"]), "raw": json.loads(r["raw"] or "{}")} for r in rows(
        "select r.src, r.dst, r.rel, r.conf, r.reason, r.manual, e.collector, e.url, e.ts, e.raw "
        "from relation r join evidence e on e.id = r.evidence where r.inv=?")]
    links = [{**r, "signals": json.loads(r["signals"] or "[]")} for r in rows("select a, b, score, signals, decision from link where inv=?")]
    tags: dict = {}
    for r in c.execute("select entity, name from tag where inv=? order by rowid", (inv,)):
        tags.setdefault(r["entity"], []).append(r["name"])
    images = {}
    for e in ents:
        if e["type"] == "Immagine" and (data := db.image(e["value"])):
            images[e["value"]] = base64.b64encode(data).decode()
    proofs = [{**r, "truncated": bool(r["truncated"]), "body": base64.b64encode(r["body"] or b"").decode()} for r in rows(
        "select entity, url, ts, sha256, size, content_type, status, wayback, truncated, body from proof where inv=? order by id")]
    return {"app": "OSINT-Fire", "format": "archive", "version": VERSION, "exported": time.time(),
            "investigation": {"name": d["name"], "purpose": d["purpose"], "seeds": d["seeds"], "max_depth": d["max_depth"], "max_entities": d["max_entities"],
                              "created": d["created"], "updated": d["updated"], "monitor_days": d["monitor_days"]},
            "entities": ents, "relations": rels, "links": links, "notes": db.notes(inv),
            "tags": [{"entity": e, "tags": t} for e, t in tags.items()],
            "hidden": rows("select entity, auto from hidden where inv=?"),
            "deleted": rows("select type, value from deleted where inv=?"),
            "layout": db.layout(inv), "runs": d["runs"], "images": images, "proofs": proofs}


# ---- reading other formats into the archive shape ----

def from_graph(g: dict) -> dict:
    """The plain 'json' export: {nodes, edges, links, notes, hidden, tags}."""
    now = time.time()
    return {"investigation": {}, "entities": g.get("nodes") or [],
            "relations": [{**e, "ts": now} for e in g.get("edges") or []],
            "links": [{"a": l["a"], "b": l["b"], "score": l.get("score", 0), "signals": l.get("signals", []),
                       "decision": "confirmed" if l.get("status") == "confirmed" else None} for l in g.get("links") or []],
            "notes": g.get("notes") or [], "tags": g.get("tags") or [], "hidden": [{"entity": h, "auto": 0} for h in g.get("hidden") or []]}


def from_graphml(text: str) -> dict:
    """What our GraphML export writes: nodes with type/label, edges with rel/conf/source. 'same subject' edges become links."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise Bad(f"invalid GraphML: {e}")
    tag = lambda el: el.tag.rsplit("}", 1)[-1]  # noqa: E731
    data = lambda el: {d.get("key"): d.text or "" for d in el if tag(d) == "data"}  # noqa: E731
    out: dict = {"investigation": {}, "entities": [], "relations": [], "links": []}
    now = time.time()
    for el in root.iter():
        if tag(el) == "node":
            d = data(el)
            out["entities"].append({"id": el.get("id"), "type": d.get("type", ""), "value": d.get("label", "")})
        elif tag(el) == "edge":
            d = data(el)
            rel, conf, src = d.get("rel", ""), _num(d.get("conf"), 1.0), d.get("source", "")
            if rel.startswith("stesso_soggetto"):
                out["links"].append({"a": el.get("source"), "b": el.get("target"), "score": conf, "signals": [],
                                     "decision": "confirmed" if "(confirmed)" in rel else None})
            else:
                out["relations"].append({"src": el.get("source"), "dst": el.get("target"), "rel": rel, "conf": conf, "reason": "",
                                         "collector": "graphml", "url": src if src.startswith("http") else "", "ts": now})
    return out


# ---- validation helpers ----

def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def _s(v, cap=STR) -> str:
    if v is None:
        return ""
    if not isinstance(v, (str, int, float)):
        raise Bad("expected text")
    return str(v)[:cap]


def _list(doc: dict, key: str) -> list:
    v = doc.get(key)
    if v is None:
        return []
    if not isinstance(v, list) or any(not isinstance(i, dict) for i in v):
        raise Bad(f"'{key}' must be a list of objects")
    return v


def _key(v):
    if isinstance(v, bool) or not isinstance(v, (int, str)):
        raise Bad("an id must be a number or a string")
    return str(v)


def _b64(s) -> bytes:
    try:
        return base64.b64decode(s, validate=True)
    except (binascii.Error, ValueError, TypeError):
        raise Bad("invalid base64")


def parse(raw: bytes) -> dict:
    text = raw.decode("utf-8-sig", "replace").lstrip()
    if text.startswith("<"):
        return from_graphml(text)
    try:
        doc = json.loads(text)
    except ValueError:
        raise Bad("not a JSON, GraphML or OSINT-Fire archive file")
    if not isinstance(doc, dict):
        raise Bad("the file must contain a JSON object")
    if doc.get("format") == "archive":
        v = doc.get("version")
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            raise Bad("invalid archive version")
        if v > VERSION:
            raise Bad(f"archive version {v} is newer than this app supports ({VERSION}); update OSINT-Fire")
        return doc
    if "nodes" in doc and "edges" in doc:
        return from_graph({**doc, "nodes": _list(doc, "nodes"), "edges": _list(doc, "edges"), "links": _list(doc, "links"),
                           "notes": _list(doc, "notes"), "tags": _list(doc, "tags")})
    raise Bad("unrecognised file: expected an OSINT-Fire archive, a json export or GraphML")


def restore(db, doc: dict) -> dict:
    """Write [doc] as a NEW investigation inside one transaction. Nothing is committed unless everything succeeded."""
    c, warns = db.c, []
    try:
        inv_meta = doc.get("investigation") or {}
        if not isinstance(inv_meta, dict):
            raise Bad("'investigation' must be an object")
        name = _s(inv_meta.get("name"), SHORT).strip() or "Imported investigation"
        if c.execute("select 1 from investigation where name=?", (name,)).fetchone():
            name += " (imported)"
        seeds = [{"type": _s(s["type"], SHORT), "value": _s(s["value"])} for s in inv_meta.get("seeds") or [] if isinstance(s, dict) and "type" in s and "value" in s]
        now = time.time()
        created = _num(inv_meta.get("created"), now) or now
        inv = c.execute(
            "insert into investigation(name, purpose, created, seeds, max_depth, max_entities, updated, monitor_days) values (?,?,?,?,?,?,?,?)",
            (name, _s(inv_meta.get("purpose")), created, json.dumps(seeds), max(0, min(int(_num(inv_meta.get("max_depth"), 2)), 10)),
             max(1, min(int(_num(inv_meta.get("max_entities"), 300)), 100000)), _num(inv_meta.get("updated"), created),
             max(0, min(int(_num(inv_meta.get("monitor_days"))), 3650)))).lastrowid
        ids: dict[str, int] = {}
        for e in _list(doc, "entities"):
            t, v = _s(e.get("type"), SHORT).strip(), _s(e.get("value")).strip()
            if not t or not v:
                warns.append("entity with empty type or value skipped")
                continue
            v = norm(t, v)
            c.execute("insert or ignore into entity(inv, type, value, added, manual) values (?,?,?,?,?)",
                      (inv, t, v, _num(e.get("added"), now), int(bool(e.get("manual")))))
            ids[_key(e.get("id"))] = c.execute("select id from entity where inv=? and type=? and value=?", (inv, t, v)).fetchone()[0]
        ref = lambda x: ids.get(_key(x))  # noqa: E731
        nrel = 0
        for r in _list(doc, "relations"):
            s, d, rel = ref(r.get("src")), ref(r.get("dst")), _s(r.get("rel"), SHORT)
            if s is None or d is None or not rel:
                warns.append(f"relation '{rel}' skipped: unknown entity")
                continue
            if c.execute("select 1 from relation where inv=? and src=? and dst=? and rel=?", (inv, s, d, rel)).fetchone():
                continue
            raw = r.get("raw") if isinstance(r.get("raw"), dict) else {}
            ev = c.execute("insert into evidence(inv, collector, url, raw, ts) values (?,?,?,?,?)",
                           (inv, _s(r.get("collector"), SHORT), _s(r.get("url"), 2000), json.dumps(raw), _num(r.get("ts"), now))).lastrowid
            c.execute("insert into relation(inv, src, dst, rel, conf, reason, evidence, manual) values (?,?,?,?,?,?,?,?)",
                      (inv, s, d, rel, _num(r.get("conf"), 1.0), _s(r.get("reason")), ev, int(bool(r.get("manual")))))
            nrel += 1
        for l in _list(doc, "links"):
            a, b = ref(l.get("a")), ref(l.get("b"))
            if a is None or b is None:
                warns.append("link skipped: unknown entity")
                continue
            dec = l.get("decision")
            c.execute("insert or ignore into link(inv, a, b, score, signals, decision) values (?,?,?,?,?,?)",
                      (inv, a, b, _num(l.get("score")), json.dumps(l.get("signals") if isinstance(l.get("signals"), list) else []),
                       dec if dec in ("confirmed", "rejected") else None))
        for n in _list(doc, "notes"):
            if (e := ref(n.get("entity"))) is not None:
                c.execute("insert or replace into note(inv, entity, text, starred) values (?,?,?,?)", (inv, e, _s(n.get("text")), int(bool(n.get("starred")))))
        for t in _list(doc, "tags"):
            if (e := ref(t.get("entity"))) is not None and isinstance(t.get("tags"), list):
                for name_ in t["tags"]:
                    c.execute("insert or ignore into tag(inv, entity, name) values (?,?,?)", (inv, e, _s(name_, SHORT)))
        for h in _list(doc, "hidden"):
            if (e := ref(h.get("entity"))) is not None:
                c.execute("insert or ignore into hidden(inv, entity, auto) values (?,?,?)", (inv, e, int(bool(h.get("auto")))))
        for x in _list(doc, "deleted"):
            t, v = _s(x.get("type"), SHORT), _s(x.get("value"))
            if t and v:
                c.execute("insert or ignore into deleted(inv, type, value) values (?,?,?)", (inv, t, norm(t, v)))
        lay = {} if doc.get("layout") is None else doc["layout"]
        if not isinstance(lay, dict):
            raise Bad("'layout' must be an object")
        for n in _list(lay, "nodes"):
            if (e := ref(n.get("id"))) is not None:
                c.execute("insert or replace into layout(inv, entity, x, y, pinned) values (?,?,?,?,?)", (inv, e, _num(n.get("x")), _num(n.get("y")), int(bool(n.get("pinned")))))
        view = lay.get("view") if isinstance(lay.get("view"), dict) else {}
        c.execute("update investigation set view=? where id=?", (json.dumps(view), inv))
        for r in _list(doc, "runs"):
            seeds_ = r.get("seeds") if isinstance(r.get("seeds"), list) else []
            c.execute("insert into run_log(inv, ts, kind, seeds, depth) values (?,?,?,?,?)",
                      (inv, _num(r.get("ts"), now), _s(r.get("kind"), SHORT), json.dumps(seeds_), int(_num(r.get("depth")))))
        images = {} if doc.get("images") is None else doc["images"]
        if not isinstance(images, dict):
            raise Bad("'images' must be an object")
        wanted = {v for (v,) in c.execute("select value from entity where inv=? and type='Immagine'", (inv,))}
        for h, b in images.items():
            if h in wanted:
                c.execute("insert or ignore into image(hash, data) values (?,?)", (_s(h, SHORT), _b64(b)))
        for p in _list(doc, "proofs"):
            body = _b64(p.get("body") or "")
            digest = hashlib.sha256(body).hexdigest()
            if p.get("sha256") and p["sha256"] != digest:
                warns.append(f"proof {_s(p.get('url'), 100)}: stored hash does not match its content")
            c.execute("insert into proof(inv, entity, url, ts, sha256, size, content_type, status, wayback, truncated, body) values (?,?,?,?,?,?,?,?,?,?,?)",
                      (inv, ref(p["entity"]) if p.get("entity") is not None else None, _s(p.get("url"), 2000), _num(p.get("ts"), now), _s(p.get("sha256"), 100) or digest,
                       len(body), _s(p.get("content_type"), SHORT), int(_num(p.get("status"))), _s(p.get("wayback"), 2000), int(bool(p.get("truncated"))), body))
        c.commit()
    except BaseException:
        c.rollback()
        raise
    return {"id": inv, "name": name, "entities": len(ids), "relations": nrel, "warnings": warns[:200]}


def register(app, get_db):
    @app.post("/investigations/import")
    async def import_archive(request: Request):
        if int(request.headers.get("content-length") or 0) > MAX_BODY:
            raise HTTPException(413, "file too large (limit 100 MB)")
        raw = await request.body()
        if len(raw) > MAX_BODY:
            raise HTTPException(413, "file too large (limit 100 MB)")
        try:
            return restore(get_db(), parse(raw))
        except (Bad, KeyError, TypeError, ValueError, AttributeError, OverflowError) as e:
            raise HTTPException(422, str(e) if isinstance(e, Bad) else "malformed file: unexpected structure")
