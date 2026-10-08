import asyncio
import time

import httpx
import pytest
from fastapi import HTTPException

from osint import monitor, settings
from osint.db import DB

DAY = 86400


@pytest.fixture(autouse=True)
def _monitoring_on():
    old = settings.CFG["monitoring"]
    settings.CFG["monitoring"] = True
    yield
    settings.CFG["monitoring"] = old


def make(db, days, created=1000.0, checked=0.0, name="t"):
    inv = db.new_investigation(name)
    db.c.execute("update investigation set created=?, monitor_days=?, monitor_checked=? where id=?", (created, days, checked, inv))
    db.c.commit()
    return inv


def stub(db, add):
    """A refresh that adds entities now and returns an already finished task."""
    calls = []

    def start(inv):
        calls.append(inv)
        for t, v in add:
            db.entity(inv, t, v)
        f = asyncio.get_running_loop().create_future()
        f.set_result(None)
        return f
    start.calls = calls
    return start


def test_due_logic():
    db = DB()
    a = make(db, 0)
    b = make(db, 1, created=1000)
    c = make(db, 3, created=1000, checked=1000 + 2 * DAY)
    d = make(db, 1, created=1000)
    db.c.execute("update investigation set updated=? where id=?", (1000 + DAY, d))  # recently touched: counts as checked
    assert monitor.due(db, 1000 + DAY) == [b]
    assert monitor.due(db, 1000 + 2 * DAY - 1) == [b]  # a off, c and d not yet
    assert monitor.due(db, 1000 + 2 * DAY) == [b, d]
    assert a not in monitor.due(db, 10**9)
    assert c in monitor.due(db, 1000 + 5 * DAY)


async def test_alert_only_when_new():
    db = DB()
    now = time.time()  # entities are stamped with the real clock, so the fake one must be near it
    inv = make(db, 1, created=now - 10 * DAY)
    start = stub(db, [("Dominio", "new.example")])
    assert await monitor.tick(db, start, clock=lambda: now) == [inv]
    alerts = db.c.execute("select * from alert").fetchall()
    assert len(alerts) == 1 and alerts[0]["entities"] == 1 and alerts[0]["inv"] == inv
    assert db.c.execute("select monitor_checked from investigation").fetchone()[0] == now
    # nothing due now; later, a run that finds nothing new makes no alert but still marks it checked
    assert await monitor.tick(db, start, clock=lambda: now + 10) == []
    later = now + 2 * DAY
    assert await monitor.tick(db, stub(db, [("Dominio", "new.example")]), clock=lambda: later) == [inv]
    assert db.c.execute("select count(*) from alert").fetchone()[0] == 1
    assert db.c.execute("select monitor_checked from investigation").fetchone()[0] == later


async def test_manual_entities_do_not_alert():
    db = DB()
    now = time.time()
    inv = make(db, 1, created=now - 10 * DAY)

    def start(i):
        db.add_manual_entity(i, "Dominio", "mine.example")
        f = asyncio.get_running_loop().create_future()
        f.set_result(None)
        return f
    await monitor.tick(db, start, clock=lambda: now)
    assert db.c.execute("select count(*) from alert").fetchone()[0] == 0


async def test_off_when_setting_false_or_days_zero():
    db = DB()
    make(db, 0)
    start = stub(db, [("Dominio", "x.example")])
    assert await monitor.tick(db, start, clock=lambda: 10**9) == []
    make(db, 1)
    settings.CFG["monitoring"] = False
    assert await monitor.tick(db, start, clock=lambda: 10**9) == []
    assert start.calls == []


async def test_running_investigation_skipped_and_failure_marks_checked():
    db = DB()
    inv = make(db, 1)

    def busy(i):
        raise HTTPException(409)
    assert await monitor.check(db, inv, busy, clock=lambda: 5000.0) is None
    assert db.c.execute("select monitor_checked from investigation").fetchone()[0] == 0

    async def boom():
        raise RuntimeError("x")

    assert await monitor.check(db, inv, lambda i: asyncio.ensure_future(boom()), clock=lambda: 5000.0) is None
    assert db.c.execute("select monitor_checked from investigation").fetchone()[0] == 5000.0


async def test_loop_runs_and_cancels():
    db = DB()
    inv = make(db, 1, created=1.0)
    start = stub(db, [("Dominio", "z.example")])
    t = asyncio.create_task(monitor.loop(lambda: db, start, interval=0.01))
    await asyncio.sleep(0.1)
    t.cancel()
    with pytest.raises(asyncio.CancelledError):
        await t
    assert start.calls == [inv]  # checked once, not due again


def test_summary_capped_at_10():
    db = DB()
    inv = db.new_investigation("t")
    for i in range(15):
        db.entity(inv, "Dominio", f"d{i}.example")
    r = monitor.new_since(db, inv, 0)
    assert r["entities"] == 15 and len(r["summary"]) == 10


async def test_routes(monkeypatch):
    from osint import main
    db = DB()
    monkeypatch.setattr(main, "db", db)
    inv = db.new_investigation("Case")
    db.entity(inv, "Dominio", "a.example")
    db.c.execute("insert into alert(inv, ts, entities, relations, summary) values (?, 5, 1, 0, '[{\"type\":\"Dominio\",\"value\":\"a.example\"}]')", (inv,))
    db.c.execute("insert into alert(inv, ts, entities, relations, seen) values (?, 6, 2, 1, 1)", (inv,))
    db.c.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://t") as c:
        assert (await c.put(f"/investigations/{inv}/monitor", json={"days": 7})).json() == {"days": 7}
        assert (await c.put(f"/investigations/{inv}/monitor", json={"days": 5})).status_code == 422
        assert (await c.put("/investigations/999/monitor", json={"days": 1})).status_code == 404
        d = (await c.get(f"/investigations/{inv}")).json()
        assert d["monitor_days"] == 7 and d["monitor_checked"] == 0
        al = (await c.get("/alerts")).json()
        assert [a["ts"] for a in al] == [6, 5] and al[1]["name"] == "Case" and al[1]["summary"][0]["type_label"]
        un = (await c.get("/alerts?unseen=true")).json()
        assert len(un) == 1 and un[0]["seen"] is False
        assert (await c.post(f"/alerts/{un[0]['id']}/seen")).json() == {"ok": True}
        assert (await c.post("/alerts/999/seen")).status_code == 404
        assert (await c.get("/alerts?unseen=true")).json() == []
        db.c.execute("insert into alert(inv, ts) values (?, 7)", (inv,))
        assert (await c.post("/alerts/seen-all")).json() == {"ok": True, "count": 1}
        await c.delete(f"/investigations/{inv}")
        assert (await c.get("/alerts")).json() == []
