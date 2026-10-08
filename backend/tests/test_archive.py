import base64
import json

import httpx
import pytest

from osint import archive, main
from osint.db import DB
from osint.models import Finding


@pytest.fixture
def db(monkeypatch):
    d = DB()
    monkeypatch.setattr(main, "db", d)
    return d


def client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://t")


def build(db):
    inv = db.new_investigation("Case", "purpose", [{"type": "Dominio", "value": "a.com"}])
    db.log_run(inv, "create", [{"type": "Dominio", "value": "a.com"}], 2)
    thumb = base64.b64encode(b"\xff\xd8jpegbytes").decode()
    db.add_finding(inv, "dns", Finding(("Dominio", "a.com"), "ha_ip", ("IP", "1.2.3.4"), 0.9, "r", "http://x", {"k": 1}))
    db.add_finding(inv, "web", Finding(("Dominio", "a.com"), "avatar", ("Immagine", "abc123"), 0.5, "r2", "", {"thumb": thumb}))
    a, _ = db.entity(inv, "Dominio", "a.com")
    ip, _ = db.entity(inv, "IP", "1.2.3.4")
    b, _ = db.add_manual_entity(inv, "Persona", "Mario")
    db.add_manual_relation(inv, b, a, "possiede", "why")
    db.set_note(inv, a, "hello", True)
    c = db.c
    c.execute("insert into tag(inv, entity, name) values (?,?,?)", (inv, a, "vip"))
    c.execute("insert into link(inv, a, b, score, signals, decision) values (?,?,?,?,?,?)", (inv, a, b, 0.8, '["x"]', "confirmed"))
    c.execute("insert into deleted(inv, type, value) values (?,?,?)", (inv, "Email", "gone@x.com"))
    c.execute("insert into proof(inv, entity, url, ts, sha256, size, content_type, status, wayback, truncated, body) values (?,?,?,?,?,?,?,?,?,?,?)",
              (inv, a, "http://a.com", 5.0, __import__("hashlib").sha256(b"<p>").hexdigest(), 3, "text/html", 200, "", 0, b"<p>"))
    c.commit()
    db.set_hidden(inv, [ip], True, cascade=False)
    db.save_layout(inv, [{"id": a, "x": 1.5, "y": 2.5, "pinned": True}], {"zoom": 2})
    return inv


def canon(db, inv):
    """Graph payload with ids replaced by type:value so two investigations can be compared."""
    g = db.graph(inv)
    name = {n["id"]: f'{n["type"]}:{n["value"]}' for n in g["nodes"]}
    lay = db.layout(inv)
    return {
        "nodes": sorted((name[n["id"]], n["manual"], n["added"]) for n in g["nodes"]),
        "edges": sorted((name[e["src"]], name[e["dst"]], e["rel"], e["conf"], e["reason"], e["manual"], e["collector"], e["url"]) for e in g["edges"]),
        "raw": sorted(r[0] for r in db.c.execute("select raw from evidence where inv=?", (inv,))),
        "links": sorted((name[l["a"]], name[l["b"]], l["score"], tuple(l["signals"]), l["status"]) for l in g["links"]),
        "notes": sorted((name[n["entity"]], n["text"], n["starred"]) for n in g["notes"]),
        "tags": sorted((name[t["entity"]], tuple(t["tags"])) for t in g["tags"]),
        "hidden": sorted(name[h] for h in g["hidden"]),
        "deleted": sorted(tuple(r) for r in db.c.execute("select type, value from deleted where inv=?", (inv,))),
        "layout": sorted((name[n["id"]], n["x"], n["y"], n["pinned"]) for n in lay["nodes"]), "view": lay["view"],
        "runs": db.investigation_detail(inv)["runs"][0]["seeds"],
        "proofs": sorted((r["url"], r["sha256"], r["body"], name.get(r["entity"])) for r in db.c.execute("select * from proof where inv=?", (inv,))),
    }


async def post(content, **kw):
    async with client() as c:
        return await c.post("/investigations/import", content=content, **kw)


async def test_round_trip(db):
    inv = build(db)
    async with client() as c:
        r = await c.get(f"/investigations/{inv}/export?format=archive")
    doc = r.json()
    assert doc["format"] == "archive" and doc["version"] == 1 and doc["app"] == "OSINT-Fire"
    assert len(doc["hidden"]) == 1 and len(doc["images"]) == 1 and "settings" not in doc
    r = await post(r.content)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["id"] != inv and out["entities"] == 4 and out["relations"] == 3 and out["warnings"] == []
    assert db.get_investigation(out["id"])["name"] == "Case (imported)"
    assert canon(db, out["id"]) == canon(db, inv)
    assert db.image("abc123") == b"\xff\xd8jpegbytes"
    d1, d2 = db.investigation_detail(inv), db.investigation_detail(out["id"])
    assert {k: d1[k] for k in ("purpose", "seeds", "max_depth", "created")} == {k: d2[k] for k in ("purpose", "seeds", "max_depth", "created")}


async def test_graphml_round_trip(db):
    inv = build(db)
    async with client() as c:
        x = (await c.get(f"/investigations/{inv}/export?format=graphml&include_hidden=true")).text
    r = await post(x.encode())
    assert r.status_code == 200, r.text
    g = db.graph(r.json()["id"])
    assert {(n["type"], n["value"]) for n in g["nodes"]} >= {("Dominio", "a.com"), ("IP", "1.2.3.4")}
    assert any(e["rel"] == "ha_ip" and e["conf"] == 0.9 for e in g["edges"])
    assert len(g["links"]) == 1


async def test_plain_json_import(db):
    inv = build(db)
    async with client() as c:
        g = (await c.get(f"/investigations/{inv}/export?format=json&include_hidden=true")).json()
    r = await post(json.dumps(g).encode())
    assert r.status_code == 200, r.text
    new = r.json()["id"]
    assert len(db.graph(new)["nodes"]) == len(g["nodes"]) and len(db.graph(new)["hidden"]) == 1
    assert db.notes(new)[0]["text"] == "hello"


async def test_name_clash_and_unique_name(db):
    inv = build(db)
    doc = archive.build(db, inv, db.get_investigation(inv))
    doc["investigation"]["name"] = "Fresh"
    assert db.get_investigation((await post(json.dumps(doc).encode())).json()["id"])["name"] == "Fresh"


@pytest.mark.parametrize("body", [b"nope", b"[1]", b'{"x":1}', b"<graphml", b'{"format":"archive","version":1,"entities":5}',
                                  b'{"format":"archive","version":1,"entities":[{"type":[1],"value":"x"}]}',
                                  b'{"format":"archive","version":"1"}', b'{"format":"archive","version":1,"images":[]}'])
async def test_malformed_is_422(db, body):
    r = await post(body)
    assert r.status_code == 422
    assert db.c.execute("select count(*) from investigation").fetchone()[0] == 0


async def test_future_version(db):
    r = await post(b'{"format":"archive","version":2}')
    assert r.status_code == 422 and "newer" in r.json()["detail"]


async def test_oversize(db, monkeypatch):
    monkeypatch.setattr(archive, "MAX_BODY", 10)
    assert (await post(b"x" * 11)).status_code == 413


async def test_bad_relations_skipped_and_normalised(db):
    doc = {"format": "archive", "version": 1, "investigation": {"name": "n"},
           "entities": [{"id": 1, "type": "Dominio", "value": " A.COM. "}, {"id": 2, "type": "Dominio", "value": "a.com"}],
           "relations": [{"src": 1, "dst": 9, "rel": "x"}, {"src": 1, "dst": 2, "rel": "same"}]}
    r = (await post(json.dumps(doc).encode())).json()
    assert r["entities"] == 2 and r["relations"] == 1 and len(r["warnings"]) == 1
    assert db.c.execute("select count(*) from entity where inv=?", (r["id"],)).fetchone()[0] == 1


async def test_atomic_rollback(db, monkeypatch):
    inv = build(db)
    body = json.dumps(archive.build(db, inv, db.get_investigation(inv))).encode()
    n = {t: db.c.execute(f"select count(*) from {t}").fetchone()[0] for t in ("investigation", "entity", "evidence", "relation", "proof", "image")}

    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(archive, "_b64", boom)
    with pytest.raises(RuntimeError):
        await post(body)
    assert n == {t: db.c.execute(f"select count(*) from {t}").fetchone()[0] for t in n}
