import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from . import collectors
from .db import DB
from . import ai, connections, features, i18n, monitor, proofs, reports, settings
from .db import without_hidden
from .export import to_graphml
from .paths import db_path
from .runner import investigate

@asynccontextmanager
async def lifespan(_app):
    # the monitoring scheduler only lives while the server runs (test clients that skip lifespan never start it)
    sched = asyncio.create_task(monitor.loop(lambda: db, start_refresh))
    yield
    sched.cancel()


app = FastAPI(title="OSINT-Fire", lifespan=lifespan)
db = DB(db_path())
settings.load(db)
tasks: dict[int, asyncio.Task] = {}
events: dict[int, list[dict]] = {}  # in-memory, replayed to late SSE subscribers
SEED_TYPES = {"Dominio", "Email", "Username", "IP", "Persona", "Azienda", "Telefono"}


class Seed(BaseModel):
    type: str
    value: str


class NewInvestigation(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    purpose: str = ""  # optional
    seeds: list[Seed] = []  # empty = a blank map to build by hand
    max_depth: int = Field(2, ge=0, le=4)
    max_entities: int = Field(300, ge=1, le=2000)


@app.get("/collectors")
def list_collectors():
    """One row per collector name (a few serve several seed types), with whether and why it would not run."""
    rows: dict[str, dict] = {}
    for c in collectors.COLLECTORS:
        r = rows.setdefault(c.name, {"name": c.name, "accepts": set(), "active": c.active, "key": c.key[0] if c.key else None, "keys": list(c.key), "status": collectors.status(c)})
        r["accepts"] |= c.accepts
    return [{**r, "accepts": sorted(r["accepts"])} for r in rows.values()]


@app.get("/settings")
def get_settings():
    return settings.public()


class SettingsPatch(BaseModel):
    values: dict


@app.put("/settings")
def put_settings(body: SettingsPatch):
    try:
        settings.update(db, body.values)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return settings.public()


@app.post("/connections/{provider}/test")
async def test_connection(provider: str):
    """One cheap authenticated call with the saved credentials, so you know a key works before relying on it."""
    try:
        ok, message = await connections.test(provider)
    except KeyError:
        raise HTTPException(404, "unknown provider")
    return {"ok": ok, "message": message}


@app.get("/maintenance/stats")
def maintenance_stats():
    q = lambda sql: db.c.execute(sql).fetchone()[0]  # noqa: E731
    path = db.c.execute("pragma database_list").fetchone()["file"]
    import os
    return {"path": path, "size": os.path.getsize(path) if path and os.path.exists(path) else 0, "investigations": q("select count(*) from investigation"),
            "entities": q("select count(*) from entity"), "evidence": q("select count(*) from evidence"), "cache_entries": q("select count(*) from run"),
            "images": q("select count(*) from image"), "notes": q("select count(*) from note")}


@app.post("/maintenance/clear-cache")
def maintenance_clear_cache():
    n = db.clear_cache()
    return {"cleared": n}


@app.post("/maintenance/vacuum")
def maintenance_vacuum():
    db.c.execute("vacuum")
    return {"ok": True}


@app.get("/maintenance/backup")
def maintenance_backup():
    return Response(db.backup_bytes(), media_type="application/x-sqlite3")


class Wipe(BaseModel):
    confirm: str


@app.post("/maintenance/wipe")
def maintenance_wipe(body: Wipe):
    """Delete every investigation and all derived data. Settings are kept. Needs the literal confirmation word."""
    if body.confirm not in ("ELIMINA", "DELETE", "ELIMINAR", "LÖSCHEN"):  # the word the UI asks for, in each language
        raise HTTPException(422, "confirmation missing")
    for t in list(tasks.values()):
        t.cancel()
    tasks.clear()
    events.clear()
    return {"deleted": db.wipe()}


@app.get("/ai/status")
def ai_status():
    ok, why = ai.configured()
    return {"configured": ok, "reason": why, "provider": settings.CFG["ai_provider"], "model": settings.CFG["ai_model"]}


class AIRequest(BaseModel):
    task: str
    question: str = ""


@app.post("/investigations/{inv}/ai")
async def ai_task(inv: int, body: AIRequest):
    meta = db.get_investigation(inv)
    if not meta:
        raise HTTPException(404)
    import httpx
    try:
        async with httpx.AsyncClient(timeout=120) as c:
            return await ai.run(c, db.graph(inv), meta, body.task, body.question)
    except ai.AIError as e:
        raise HTTPException(502, str(e))


@app.get("/investigations/{inv}/status")
def inv_status(inv: int):
    if not db.get_investigation(inv):
        raise HTTPException(404)
    t = tasks.get(inv)
    g = db.graph(inv)
    return {"running": bool(t and not t.done()), "entities": len(g["nodes"]), "relations": len(g["edges"]), "links": len(g["links"]),
            "last_event": (events.get(inv) or [None])[-1]}


@app.post("/investigations")
async def create(body: NewInvestigation):
    bad = [s.type for s in body.seeds if s.type not in SEED_TYPES]
    if bad:
        raise HTTPException(422, f"unsupported seed type: {bad}")
    seeds = [{"type": s.type, "value": s.value} for s in body.seeds]
    inv = db.new_investigation(body.name.strip(), body.purpose.strip(), seeds, body.max_depth, body.max_entities)
    db.log_run(inv, "create", seeds, body.max_depth)
    events[inv] = []
    if not seeds:  # blank map: nothing to collect, the user adds nodes and bridges
        events[inv].append({"type": "done", "stopped": False, "new": 0})
        return {"id": inv}
    tasks[inv] = asyncio.create_task(investigate(db, inv, [(s.type, s.value) for s in body.seeds],
                                                 body.max_depth, body.max_entities, events[inv].append))
    return {"id": inv}


@app.get("/images/{hash_}")
def image(hash_: str):
    data = db.image(hash_)
    if data is None:
        raise HTTPException(404)
    return Response(data, media_type="image/jpeg")


@app.get("/investigations")
def list_investigations():
    return db.list_investigations()


@app.delete("/investigations/{inv}")
def delete(inv: int):
    if t := tasks.pop(inv, None):
        t.cancel()  # still running: stop before its rows disappear
    events.pop(inv, None)
    if not db.delete_investigation(inv):
        raise HTTPException(404)
    return {"ok": True}


@app.get("/investigations/{inv}/export")
def export(inv: int, format: str = "json", include_hidden: bool = False):
    meta = db.get_investigation(inv)
    if not meta:
        raise HTTPException(404)
    g = db.graph(inv)
    if not include_hidden:
        g = without_hidden(g)
    match format:
        case "graphml":
            return Response(to_graphml(g), media_type="application/xml")
        case "md":
            return Response(reports.markdown(g, meta), media_type="text/markdown; charset=utf-8")
        case "pdf":
            return Response(reports.pdf(g, meta), media_type="application/pdf")
        case "obsidian":  # {"files": {relative path: content}}, written to disk by the client
            return {"files": reports.obsidian(g, meta)}
        case "json":
            return g
    raise HTTPException(422, "format: json|graphml|md|pdf|obsidian")


class ReportBody(BaseModel):
    format: str = "html"
    sections: list[str] = ["summary", "entities", "relations", "links", "notes", "tags", "proofs", "timeline"]
    title: str = Field("", max_length=200)
    header: str = Field("", max_length=2000)
    footer: str = Field("", max_length=2000)
    logo: str | None = None
    include_hidden: bool = False
    lang: str | None = None


@app.post("/investigations/{inv}/report")
def custom_report(inv: int, body: ReportBody):
    meta = db.get_investigation(inv)
    if not meta:
        raise HTTPException(404)
    if body.lang and body.lang not in i18n.LANGS:
        raise HTTPException(422, "lang: it|en|es|de")
    g = db.graph(inv)
    if not body.include_hidden:
        g = without_hidden(g)
    extras = {}
    try:  # optional modules written separately: report still works without them
        from . import features, proofs
        if "proofs" in body.sections:
            extras["proofs"] = proofs.list_for_report(db, inv)
        if "timeline" in body.sections:
            extras["timeline"] = features.timeline(db, inv, body.lang or settings.lang())["events"]
    except (ImportError, AttributeError, TypeError, KeyError):
        pass
    try:
        data = reports.render(g, meta, body.format, sections=body.sections, title=body.title, header=body.header,
                              footer=body.footer, logo=body.logo, lang=body.lang, extras=extras)
    except ValueError as e:
        raise HTTPException(422, str(e))
    mt = {"html": "text/html; charset=utf-8", "md": "text/markdown; charset=utf-8", "pdf": "application/pdf"}[body.format]
    return Response(data, media_type=mt, headers={"Content-Disposition": f'attachment; filename="report-{inv}.{body.format}"'})


class Expand(BaseModel):
    seeds: list[Seed] = Field(min_length=1)
    max_depth: int = Field(1, ge=0, le=4)
    max_entities: int = Field(300, ge=1, le=2000)  # extra entities allowed on top of those already in the investigation


@app.post("/investigations/{inv}/expand")
async def expand(inv: int, body: Expand):
    """Run collectors on entities already in the graph (or new ones), adding results to the same investigation."""
    if not db.get_investigation(inv):
        raise HTTPException(404)
    if (t := tasks.get(inv)) and not t.done():
        raise HTTPException(409, "a search is already running on this investigation")
    bad = [s.type for s in body.seeds if s.type not in SEED_TYPES]
    if bad:
        raise HTTPException(422, f"unsupported seed type: {bad}")
    db.log_run(inv, "expand", [{"type": s.type, "value": s.value} for s in body.seeds], body.max_depth)
    events[inv] = []  # fresh stream: the previous one already ended with "done"
    tasks[inv] = asyncio.create_task(investigate(db, inv, [(s.type, s.value) for s in body.seeds], body.max_depth,
                                                 db.count_entities(inv) + body.max_entities, events[inv].append))
    return {"id": inv}


class NoteBody(BaseModel):
    text: str = Field("", max_length=5000)
    starred: bool = False


@app.put("/investigations/{inv}/entities/{entity}/note")
def set_note(inv: int, entity: int, body: NoteBody):
    if not db.set_note(inv, entity, body.text, body.starred):
        raise HTTPException(404)
    return {"ok": True}


@app.post("/investigations/{inv}/stop")
async def stop(inv: int):
    """Stop a running search. Everything found so far is kept, the graph is correlated and the event stream ends with done/stopped."""
    if not db.get_investigation(inv):
        raise HTTPException(404)
    t = tasks.get(inv)
    if not t or t.done():
        return {"stopped": False}
    t.cancel()
    await asyncio.wait({t}, timeout=15)  # collectors get a moment to clean up
    return {"stopped": True}


@app.get("/investigations/{inv}")
def investigation(inv: int):
    d = db.investigation_detail(inv)
    if not d:
        raise HTTPException(404)
    return d


class Refresh(BaseModel):
    """Optional edits to the search definition, applied before re-running it."""
    name: str | None = Field(None, min_length=1, max_length=120)
    purpose: str | None = None
    seeds: list[Seed] | None = Field(None, min_length=1)
    max_depth: int | None = Field(None, ge=0, le=4)
    max_entities: int | None = Field(None, ge=1, le=2000)


def start_refresh(inv: int, body: Refresh | None = None) -> asyncio.Task:
    """Re-run the search as it was last defined (base seeds + the entities you expanded by hand), ignoring cached results,
    and add whatever is new. Body can change name, purpose, seeds, depth first. Returns the running task; HTTPException if it cannot start."""
    if not db.get_investigation(inv):
        raise HTTPException(404)
    if (t := tasks.get(inv)) and not t.done():
        raise HTTPException(409, "a search is already running on this investigation")
    body = body or Refresh()
    if body.seeds is not None:
        bad = [s.type for s in body.seeds if s.type not in SEED_TYPES]
        if bad:
            raise HTTPException(422, f"unsupported seed type: {bad}")
    db.update_investigation(inv, name=body.name and body.name.strip(), purpose=body.purpose and body.purpose.strip() if body.purpose is not None else None,
                            seeds=[{"type": s.type, "value": s.value} for s in body.seeds] if body.seeds else None,
                            max_depth=body.max_depth, max_entities=body.max_entities)
    seeds, depths, max_depth = db.refresh_plan(inv)
    d = db.investigation_detail(inv)
    db.log_run(inv, "refresh", [{"type": t, "value": v} for t, v in seeds], max_depth)
    events[inv] = []
    tasks[inv] = asyncio.create_task(investigate(db, inv, seeds, max_depth, db.count_entities(inv) + d["max_entities"], events[inv].append,
                                                 fresh=True, seed_depths=depths))
    return tasks[inv]


@app.post("/investigations/{inv}/refresh")
async def refresh(inv: int, body: Refresh | None = None):
    started = time.time()
    start_refresh(inv, body)
    return {"id": inv, "started": started}


monitor.register(app, lambda: db, start_refresh)  # late-bound: tests replace main.db
proofs.register(app, lambda: db)


class NewEntity(BaseModel):
    type: str = Field(min_length=1, max_length=40)
    value: str = Field(min_length=1, max_length=500)


def _clean(s: str) -> str:
    return " ".join(s.split())  # no control characters or runs of blanks


@app.post("/investigations/{inv}/entities")
def create_entity(inv: int, body: NewEntity):
    """A node made by hand. If it already exists (found by a collector, or added before) the existing id comes back with created=false."""
    if not db.get_investigation(inv):
        raise HTTPException(404)
    eid, created = db.add_manual_entity(inv, _clean(body.type), _clean(body.value))
    return {"id": eid, "created": created}


class EntityEdit(BaseModel):
    type: str | None = Field(None, min_length=1, max_length=40)
    value: str | None = Field(None, min_length=1, max_length=500)


@app.patch("/investigations/{inv}/entities/{eid}")
def edit_entity(inv: int, eid: int, body: EntityEdit):
    res = db.update_manual_entity(inv, eid, _clean(body.type) if body.type else None, _clean(body.value) if body.value else None)
    if res == "missing":
        raise HTTPException(404, "node not found or not created by hand")
    if res == "duplicate":
        raise HTTPException(409, "a node with this type and value already exists")
    return {"ok": True}


class DeleteEntities(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=5000)
    cascade: bool = True  # hide what hung only from the deleted nodes


@app.post("/investigations/{inv}/entities/delete")
def delete_entities(inv: int, body: DeleteEntities):
    """Delete nodes, collected or user-made. Collected ones stay deleted across refreshes. With cascade, data that started only
    from them is hidden (not deleted), so it can be shown again."""
    if not db.get_investigation(inv):
        raise HTTPException(404)
    n, hidden = db.delete_entities(inv, body.ids, body.cascade)
    if n == 0:
        raise HTTPException(404, "no node found")
    return {"deleted": n, "hidden": hidden}


@app.delete("/investigations/{inv}/entities/{eid}")
def delete_entity(inv: int, eid: int, cascade: bool = True):
    n, hidden = db.delete_entities(inv, [eid], cascade)
    if n == 0:
        raise HTTPException(404, "node not found")
    return {"ok": True, "hidden": hidden}


class NewRelation(BaseModel):
    src: int
    dst: int
    rel: str = Field("collegato a", min_length=1, max_length=80)
    reason: str = Field("", max_length=500)


@app.post("/investigations/{inv}/relations")
def create_relation(inv: int, body: NewRelation):
    """A bridge between two nodes of the investigation, with a label you choose."""
    r = db.add_manual_relation(inv, body.src, body.dst, _clean(body.rel), body.reason.strip())
    if r is None:
        raise HTTPException(422, "the two nodes must be different and belong to this investigation")
    return {"id": r[0], "created": r[1]}


@app.delete("/investigations/{inv}/relations/{rid}")
def delete_relation(inv: int, rid: int):
    if not db.delete_manual_relation(inv, rid):
        raise HTTPException(404, "bridge not found or not created by hand")
    return {"ok": True}


class HiddenBody(BaseModel):
    ids: list[int] = Field(max_length=5000)
    hidden: bool = True
    cascade: bool = True  # also hide what hangs only from these nodes / show it again with them


@app.put("/investigations/{inv}/hidden")
def set_hidden(inv: int, body: HiddenBody):
    if not db.get_investigation(inv):
        raise HTTPException(404)
    ids = db.set_hidden(inv, body.ids, body.hidden, body.cascade)
    return {"changed": len(ids), "ids": ids}


@app.delete("/investigations/{inv}/hidden")
def clear_hidden(inv: int):
    if not db.get_investigation(inv):
        raise HTTPException(404)
    db.clear_hidden(inv)
    return {"ok": True}


class LayoutBody(BaseModel):
    nodes: list[dict]
    view: dict = {}


@app.put("/investigations/{inv}/layout")
def put_layout(inv: int, body: LayoutBody):
    if not db.get_investigation(inv):
        raise HTTPException(404)
    nodes = [n for n in body.nodes if isinstance(n.get("id"), int) and n["id"] > 0 and isinstance(n.get("x"), (int, float)) and isinstance(n.get("y"), (int, float))]
    db.save_layout(inv, nodes[:5000], body.view)
    return {"saved": db.c.execute("select count(*) from layout where inv=?", (inv,)).fetchone()[0]}


@app.get("/investigations/{inv}/layout")
def get_layout(inv: int):
    if not db.get_investigation(inv):
        raise HTTPException(404)
    return db.layout(inv)


@app.get("/investigations/{inv}/graph")
def graph(inv: int):
    """Canonical data (identities and logic) plus display labels in the interface language."""
    return i18n.localize_graph(db.graph(inv), settings.lang())


class Decision(BaseModel):
    decision: str | None = Field(pattern="^(confirmed|rejected)$")  # null clears... use DELETE semantics later


@app.post("/investigations/{inv}/links/{link_id}")
def decide(inv: int, link_id: int, body: Decision):
    if not db.decide(inv, link_id, body.decision):
        raise HTTPException(404)
    return {"ok": True}


@app.get("/investigations/{inv}/events")
async def stream(inv: int):
    if inv not in events:
        raise HTTPException(404)

    async def gen():
        import json
        i = 0
        while True:
            while i < len(events[inv]):
                ev = events[inv][i]
                i += 1
                yield f"data: {json.dumps(ev)}\n\n"
                if ev["type"] == "done":
                    return
            await asyncio.sleep(0.3)

    return StreamingResponse(gen(), media_type="text/event-stream")


features.register(app, lambda: db)  # tags, seed parsing, diff, timeline
