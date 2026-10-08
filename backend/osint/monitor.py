"""Monitoring: re-run an investigation every N days while the app is open, and keep an alert when something new turned up."""
import asyncio
import json
import time
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel

from . import i18n, settings

INTERVAL = 600  # seconds between scheduler wake-ups (tests pass their own)
DAY = 86400


def new_since(db, inv: int, since: float) -> dict:
    """What arrived after [since]: counts plus the first 10 new entities. Hand-made entities and bridges never count."""
    c = db.c
    rows = c.execute("select type, value from entity where inv=? and added >= ? and manual=0 order by id", (inv, since)).fetchall()
    rels = c.execute("select count(*) from relation r join evidence e on e.id = r.evidence where r.inv=? and r.manual=0 and e.ts >= ?", (inv, since)).fetchone()[0]
    return {"entities": len(rows), "relations": rels, "summary": [{"type": r["type"], "value": r["value"]} for r in rows[:10]]}


def due(db, now: float) -> list[int]:
    out = []
    for r in db.c.execute("select id, monitor_days, monitor_checked, updated, created from investigation where monitor_days > 0 order by id"):
        if now - max(r["monitor_checked"], r["updated"], r["created"] or 0) >= r["monitor_days"] * DAY:
            out.append(r["id"])
    return out


async def check(db, inv: int, start_refresh, clock=time.time) -> int | None:
    """Refresh one investigation, wait for it and store an alert if it brought something new. Returns the alert id (or None)."""
    started = clock()
    try:
        task = start_refresh(inv)
    except HTTPException:  # already running, or gone: try again next time
        return None
    try:
        await task
    except asyncio.CancelledError:
        if asyncio.current_task().cancelling():  # we are being shut down, not the refresh stopped by the user
            raise
    except Exception:
        pass  # a failed run still counts as checked: no retry storm
    diff = new_since(db, inv, started)
    alert = None
    if diff["entities"] or diff["relations"]:
        alert = db.c.execute("insert into alert(inv, ts, entities, relations, summary) values (?, ?, ?, ?, ?)",
                             (inv, clock(), diff["entities"], diff["relations"], json.dumps(diff["summary"]))).lastrowid
    db.c.execute("update investigation set monitor_checked=? where id=?", (clock(), inv))
    db.c.commit()
    return alert


async def tick(db, start_refresh, clock=time.time) -> list[int]:
    """One scheduler pass: every due investigation, one at a time. Off when the setting is off."""
    if not settings.CFG["monitoring"]:
        return []
    done = []
    for inv in due(db, clock()):
        await check(db, inv, start_refresh, clock)
        done.append(inv)
    return done


async def loop(get_db, start_refresh, interval: float | None = None, clock=time.time):
    while True:
        try:
            await tick(get_db(), start_refresh, clock)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass  # the scheduler must outlive any single failure
        await asyncio.sleep(INTERVAL if interval is None else interval)


class MonitorBody(BaseModel):
    days: Literal[0, 1, 3, 7, 14, 30]


def register(app, get_db, start_refresh):
    @app.put("/investigations/{inv}/monitor")
    def set_monitor(inv: int, body: MonitorBody):
        db = get_db()
        if not db.get_investigation(inv):
            raise HTTPException(404)
        db.c.execute("update investigation set monitor_days=? where id=?", (body.days, inv))
        db.c.commit()
        return {"days": body.days}

    @app.get("/alerts")
    def list_alerts(unseen: bool = False):
        lang = settings.lang()
        rows = get_db().c.execute(
            "select a.*, i.name from alert a join investigation i on i.id = a.inv " + ("where a.seen=0 " if unseen else "") + "order by a.ts desc, a.id desc limit 100")
        return [{"id": r["id"], "inv": r["inv"], "name": r["name"], "ts": r["ts"], "entities": r["entities"], "relations": r["relations"], "seen": bool(r["seen"]),
                 "summary": [{**s, "type_label": i18n.label("type", s["type"], lang),
                              "label": i18n.label_value(s["value"], lang) if s["type"] in ("Servizio", "Data") else s["value"]} for s in json.loads(r["summary"])]}
                for r in rows]

    @app.post("/alerts/seen-all")
    def seen_all():
        db = get_db()
        n = db.c.execute("update alert set seen=1 where seen=0").rowcount
        db.c.commit()
        return {"ok": True, "count": n}

    @app.post("/alerts/{alert_id}/seen")
    def seen(alert_id: int):
        db = get_db()
        if not db.c.execute("update alert set seen=1 where id=?", (alert_id,)).rowcount:
            raise HTTPException(404)
        db.c.commit()
        return {"ok": True}
