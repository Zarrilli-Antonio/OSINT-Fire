import hashlib

import httpx
import pytest

from osint import main, proofs
from osint.db import DB

PUBLIC = ["93.184.216.34"]


@pytest.fixture
def env(monkeypatch):
    db = DB()
    monkeypatch.setattr(main, "db", db)

    async def fake_resolve(host):
        return {"localhost": ["127.0.0.1"], "internal.example": ["10.1.2.3"]}.get(host, PUBLIC)
    monkeypatch.setattr(proofs, "resolve", fake_resolve)

    def serve(handler):
        monkeypatch.setattr(proofs, "_transport", httpx.MockTransport(handler))
    return db, serve


def client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://t")


async def test_proof_hash_and_snapshot(env):
    db, serve = env
    page = b"<html>hello</html>"
    seen = {}

    def h(req):
        seen["ua"] = req.headers["user-agent"]
        return httpx.Response(200, content=page, headers={"content-type": "text/html"})
    serve(h)
    inv = db.new_investigation("t")
    async with client() as c:
        r = (await c.post(f"/investigations/{inv}/proofs", json={"url": "https://example.com/p"})).json()
        assert r["sha256"] == hashlib.sha256(page).hexdigest() and r["size"] == len(page) and r["status"] == 200
        assert r["wayback"] == "" and r["archive_error"] == "" and r["truncated"] is False and seen["ua"].startswith("OSINT-Fire")
        s = await c.get(f"/investigations/{inv}/proofs/{r['id']}/snapshot")
        assert s.content == page and s.headers["content-type"].startswith("text/html") and s.headers["content-disposition"] == "inline"
        assert "sandbox" in s.headers["content-security-policy"]
        assert (await c.get(f"/investigations/{inv}/proofs/999/snapshot")).status_code == 404
        assert "body" not in (await c.get(f"/investigations/{inv}/proofs")).json()[0]
        assert proofs.list_for_report(db, inv)[0]["sha256"] == r["sha256"]


async def test_size_cap(env):
    db, serve = env
    serve(lambda req: httpx.Response(200, content=b"a" * (proofs.MAX_BYTES + 100)))
    inv = db.new_investigation("t")
    async with client() as c:
        r = (await c.post(f"/investigations/{inv}/proofs", json={"url": "https://example.com/big"})).json()
    assert r["truncated"] is True and r["size"] == proofs.MAX_BYTES
    assert r["sha256"] == hashlib.sha256(b"a" * proofs.MAX_BYTES).hexdigest()


@pytest.mark.parametrize("url", ["http://127.0.0.1/x", "http://10.0.0.5/", "http://localhost:8765/", "http://internal.example/", "file:///etc/passwd",
                                 "ftp://example.com/", "http://[::1]/", "http://169.254.169.254/latest", "http://192.168.1.1/", "http://172.16.0.1/"])
async def test_ssrf_refused(env, url):
    db, serve = env
    serve(lambda req: pytest.fail("must not connect"))
    inv = db.new_investigation("t")
    async with client() as c:
        assert (await c.post(f"/investigations/{inv}/proofs", json={"url": url})).status_code == 422
    assert db.c.execute("select count(*) from proof").fetchone()[0] == 0


async def test_redirect_to_private_refused_and_public_redirect_followed(env):
    db, serve = env

    def h(req):
        if req.url.path == "/bad":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})
        if req.url.path == "/ok":
            return httpx.Response(301, headers={"location": "/final"})
        return httpx.Response(200, content=b"end")
    serve(h)
    inv = db.new_investigation("t")
    async with client() as c:
        assert (await c.post(f"/investigations/{inv}/proofs", json={"url": "https://example.com/bad"})).status_code == 422
        r = (await c.post(f"/investigations/{inv}/proofs", json={"url": "https://example.com/ok"})).json()
    assert r["url"] == "https://example.com/final"


async def test_archive_success_and_failure(env):
    db, serve = env
    mode = {"ok": True}

    def h(req):
        if req.url.host == "web.archive.org":
            if mode["ok"]:
                return httpx.Response(200, headers={"content-location": "/web/20240101000000/https://example.com/p"})
            return httpx.Response(429)
        return httpx.Response(200, content=b"x")
    serve(h)
    inv = db.new_investigation("t")
    async with client() as c:
        r = (await c.post(f"/investigations/{inv}/proofs", json={"url": "https://example.com/p", "archive": True})).json()
        assert r["wayback"] == "https://web.archive.org/web/20240101000000/https://example.com/p" and r["archive_error"] == ""
        mode["ok"] = False
        r = (await c.post(f"/investigations/{inv}/proofs", json={"url": "https://example.com/p", "archive": True})).json()
        assert r["wayback"] == "" and "429" in r["archive_error"] and r["sha256"]


def test_parse_archive():
    link = '<https://web.archive.org/web/20240101000000/https://e.com/>; rel="memento"; datetime="x"'
    assert proofs.parse_archive({"link": link}) == "https://web.archive.org/web/20240101000000/https://e.com/"
    assert proofs.parse_archive({}) == ""


async def test_filter_delete_and_investigation_delete(env):
    db, serve = env
    serve(lambda req: httpx.Response(200, content=b"x"))
    inv = db.new_investigation("t")
    e1, _ = db.entity(inv, "Dominio", "a.example")
    async with client() as c:
        p1 = (await c.post(f"/investigations/{inv}/proofs", json={"url": "https://example.com/1", "entity": e1})).json()
        p2 = (await c.post(f"/investigations/{inv}/proofs", json={"url": "https://example.com/2"})).json()
        assert (await c.post(f"/investigations/{inv}/proofs", json={"url": "https://example.com/3", "entity": 999})).status_code == 404
        assert [p["id"] for p in (await c.get(f"/investigations/{inv}/proofs?entity={e1}")).json()] == [p1["id"]]
        assert len((await c.get(f"/investigations/{inv}/proofs")).json()) == 2
        assert (await c.delete(f"/investigations/{inv}/proofs/{p2['id']}")).json() == {"ok": True}
        assert (await c.delete(f"/investigations/{inv}/proofs/{p2['id']}")).status_code == 404
        db.delete_entities(inv, [e1])  # the proof survives, detached
        assert (await c.get(f"/investigations/{inv}/proofs")).json()[0]["entity"] is None
        await c.delete(f"/investigations/{inv}")
    assert db.c.execute("select count(*) from proof").fetchone()[0] == 0
