import base64
import re

import httpx
import pytest

from osint import main, reports
from osint.db import DB
from osint.models import Finding

PNG = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==")
FAKE = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\0" * 20).decode()  # right magic, not an image
EVIL = "<script>alert(1)</script>"
ALL = list(reports.SECTIONS)
EXTRAS = {"proofs": [{"url": "https://p.example/x", "ts": 1.7e9, "sha256": "ab" * 32, "size": 3, "wayback": "", "entity": None}],
          "timeline": [{"date": "2014-05-12", "label": "registered"}]}


@pytest.fixture
def setup(monkeypatch):
    db = DB()
    monkeypatch.setattr(main, "db", db)
    inv = db.new_investigation("Rep")
    db.add_finding(inv, "c", Finding(("Username", EVIL), "usa", ("Email", "bob@x.com"), 0.9, "t"))
    g = db.graph(inv)
    g["tags"] = [{"entity": g["nodes"][0]["id"], "tags": ["suspect"]}]
    g["notes"] = [{"entity": g["nodes"][1]["id"], "text": "mynote", "starred": True}]
    return db, inv, g, db.get_investigation(inv)


@pytest.mark.parametrize("fmt", ["md", "html", "pdf"])
def test_all_formats(setup, fmt):
    _, _, g, meta = setup
    out = reports.render(g, meta, fmt, sections=ALL, title="T", header="H", footer="F", logo=PNG if fmt != "md" else None, extras=EXTRAS, lang="en")
    assert out[:4] == b"%PDF" if fmt == "pdf" else all(x in out for x in (b"suspect", b"mynote", b"2014-05-12"))


def test_section_filtering(setup):
    _, _, g, meta = setup
    full = reports.render(g, meta, "md", extras=EXTRAS, lang="en").decode()
    assert "suspect" in full and "mynote" in full and "p.example" in full
    only = reports.render(g, meta, "md", sections=["tags"], extras=EXTRAS, lang="en").decode()
    assert "suspect" in only and "mynote" not in only and "p.example" not in only and "2014" not in only
    h = reports.render(g, meta, "html", sections=["summary"], lang="en").decode()
    assert "<details" not in h and "<table" not in h


def test_html_escaping_and_standalone(setup):
    _, _, g, meta = setup
    h = reports.render(g, meta, "html", title=EVIL, header=EVIL, footer='"><img src=x>', logo=PNG, extras={"proofs": [{"url": EVIL, "ts": 0, "sha256": "x"}]}).decode()
    assert EVIL not in h and "&lt;script&gt;alert(1)&lt;/script&gt;" in h and "<img src=x>" not in h
    assert h.count("<script>") == 1  # only our filter script
    assert "data:image/png;base64," in h
    assert not re.search(r'(src|href)\s*=\s*["\']?https?://', h) and "url(http" not in h and "@import" not in h
    assert "prefers-color-scheme:dark" in h and "@media print" in h


def test_logo_validation(setup):
    _, _, g, meta = setup
    for bad in ["!!notb64", base64.b64encode(b"GIF89a....").decode(), base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 1_000_001).decode()]:
        with pytest.raises(ValueError):
            reports.render(g, meta, "html", logo=bad)
    with pytest.raises(ValueError):
        reports.render(g, meta, "pdf", logo=FAKE)
    assert reports.decode_logo(base64.b64encode(b"\xff\xd8\xff\xe0x").decode())[1] == "image/jpeg"


def test_language(setup):
    _, _, g, meta = setup
    assert "Riepilogo" in reports.render(g, meta, "md", lang="it").decode()
    assert "Zusammenfassung" in reports.render(g, meta, "md", lang="de").decode()


async def test_endpoint(setup):
    db, inv, _, _ = setup
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://t") as c:
        r = await c.post(f"/investigations/{inv}/report", json={"format": "html", "sections": ["summary", "entities"], "logo": PNG, "lang": "en"})
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
        assert 'filename="report-%d.html"' % inv in r.headers["content-disposition"] and "&lt;script&gt;" in r.text
        r = await c.post(f"/investigations/{inv}/report", json={"format": "pdf"})
        assert r.status_code == 200 and r.content[:4] == b"%PDF" and r.headers["content-type"] == "application/pdf"
        r = await c.post(f"/investigations/{inv}/report", json={"format": "md"})
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
        for body in ({"format": "docx"}, {"sections": ["nope"]}, {"logo": "!!"}, {"lang": "xx"}):
            assert (await c.post(f"/investigations/{inv}/report", json=body)).status_code == 422
        assert (await c.post("/investigations/999/report", json={})).status_code == 404
        db.set_hidden(inv, [n["id"] for n in db.graph(inv)["nodes"] if n["value"] == EVIL], True, cascade=False)
        body = {"format": "md", "sections": ["entities"], "lang": "en"}
        assert "bob@x.com" in (await c.post(f"/investigations/{inv}/report", json=body)).text  # visible one stays
        assert EVIL not in (await c.post(f"/investigations/{inv}/report", json=body)).text
        assert EVIL in (await c.post(f"/investigations/{inv}/report", json={**body, "include_hidden": True})).text
