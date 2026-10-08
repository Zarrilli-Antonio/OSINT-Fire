import httpx
import pytest

from osint import features, main
from osint.db import DB, without_hidden
from osint.models import Finding


@pytest.fixture
def db(monkeypatch):
    d = DB()
    monkeypatch.setattr(main, "db", d)
    return d


@pytest.fixture
async def client(db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://t") as c:
        yield c


def _setting_it():
    from osint import settings
    settings.CFG["language"] = "it"


async def test_tags_set_replace_limits_and_graph(client, db):
    inv = db.new_investigation("t")
    a, _ = db.entity(inv, "Dominio", "a.com")
    b, _ = db.entity(inv, "Dominio", "b.com")
    url = f"/investigations/{inv}/entities/{a}/tags"
    r = await client.put(url, json={"tags": [" suspect ", "Verified", "SUSPECT"]})  # trimmed, case-insensitive duplicate dropped
    assert r.json() == {"tags": ["suspect", "Verified"]}
    assert (await client.put(url, json={"tags": ["x"]})).json() == {"tags": ["x"]}  # replaces
    assert (await client.put(url, json={"tags": [""]})).status_code == 422
    assert (await client.put(url, json={"tags": ["a" * 31]})).status_code == 422
    assert (await client.put(url, json={"tags": [f"t{i}" for i in range(13)]})).status_code == 422
    assert (await client.put(url, json={"tags": [f"t{i}" for i in range(12)]})).status_code == 200
    assert (await client.put(f"/investigations/{inv}/entities/999/tags", json={"tags": []})).status_code == 404
    other = db.new_investigation("o")
    assert (await client.put(f"/investigations/{other}/entities/{a}/tags", json={"tags": []})).status_code == 404

    await client.put(f"/investigations/{inv}/entities/{b}/tags", json={"tags": ["k"]})
    g = (await client.get(f"/investigations/{inv}/graph")).json()
    assert {t["entity"]: t["tags"][0] for t in g["tags"]} == {a: "t0", b: "k"}
    db.set_hidden(inv, [b], True, cascade=False)
    assert [t["entity"] for t in without_hidden(db.graph(inv))["tags"]] == [a]

    await client.put(url, json={"tags": []})  # empty list clears
    assert [t["entity"] for t in (await client.get(f"/investigations/{inv}/graph")).json()["tags"]] == [b]


def test_tags_cascade_on_delete(db):
    inv = db.new_investigation("t")
    a, _ = db.entity(inv, "Dominio", "a.com")
    features.set_tags(db, inv, a, ["x"])
    db.delete_entities(inv, [a])
    assert db.c.execute("select count(*) from tag").fetchone()[0] == 0
    b, _ = db.entity(inv, "Dominio", "b.com")
    features.set_tags(db, inv, b, ["x"])
    db.delete_investigation(inv)
    assert db.c.execute("select count(*) from tag").fetchone()[0] == 0


def test_tags_in_markdown_report(db):
    from osint import reports
    inv = db.new_investigation("t")
    a, _ = db.entity(inv, "Dominio", "a.com")
    features.set_tags(db, inv, a, ["suspect"])
    assert "[suspect]" in reports.markdown(db.graph(inv), db.get_investigation(inv))


def test_parse_seeds_autodetect():
    out = features.parse_seeds("Bob@Example.com; 8.8.8.8, 2001:db8::1\n+39 333 123 4567\n3331234567 example.org @bobby\nhttps://www.x.it/path hello")
    assert out["seeds"] == [
        {"type": "Email", "value": "bob@example.com"}, {"type": "IP", "value": "8.8.8.8"}, {"type": "IP", "value": "2001:db8::1"},
        {"type": "Telefono", "value": "+393331234567"}, {"type": "Telefono", "value": "3331234567"}, {"type": "Dominio", "value": "example.org"},
        {"type": "Username", "value": "bobby"}, {"type": "Dominio", "value": "www.x.it"}]
    assert out["skipped"] == ["hello"]


def test_parse_seeds_csv_header_languages_and_duplicates():
    out = features.parse_seeds("Type,Value\nPerson,Mario Rossi\nEmail,A@B.it\nemail,a@b.it\nnonsense,x\nTelefono,333 1234567")
    assert out["seeds"] == [{"type": "Persona", "value": "Mario Rossi"}, {"type": "Email", "value": "a@b.it"}, {"type": "Telefono", "value": "3331234567"}]
    assert out["skipped"] == ["nonsense,x"]
    out = features.parse_seeds("tipo;valore\nAzienda;ACME Srl\nEmpresa;ACME Srl\nBenutzername;bob")
    assert [s["type"] for s in out["seeds"]] == ["Azienda", "Username"]  # same value twice is one seed
    assert features.parse_seeds("") == {"seeds": [], "skipped": []}


async def test_parse_seeds_cap(client):
    text = "\n".join(f"h{i}.example.com" for i in range(600))
    assert len((await client.post("/seeds/parse", json={"text": text})).json()["seeds"]) == 500


async def test_diff(client, db, monkeypatch):
    import time
    inv = db.new_investigation("t")
    assert (await client.get(f"/investigations/{inv}/diff")).json()["first_run"] is True
    t = [1000.0]
    monkeypatch.setattr(time, "time", lambda: t[0])
    db.log_run(inv, "create", [], 1)
    t[0] = 1010
    db.add_finding(inv, "x", Finding(("Dominio", "a.com"), "sottodominio", ("Dominio", "b.a.com"), 1, "t"))
    d = (await client.get(f"/investigations/{inv}/diff")).json()
    assert d["first_run"] is True and d["since"] == 1000 and d["summary"] == {"entities": 2, "relations": 1}

    t[0] = 2000
    db.log_run(inv, "refresh", [], 1)
    t[0] = 2010
    db.add_finding(inv, "x", Finding(("Dominio", "a.com"), "sottodominio", ("Dominio", "c.a.com"), 1, "t"))
    db.add_manual_entity(inv, "Persona", "Bob")
    n_manual, _ = db.entity(inv, "Persona", "Bob")
    c, _ = db.entity(inv, "Dominio", "c.a.com")
    db.add_manual_relation(inv, n_manual, c, "collegato a")
    d = (await client.get(f"/investigations/{inv}/diff")).json()
    assert d["first_run"] is False and d["runs"] == [1000, 2000] and d["since"] == 2000
    assert d["nodes"] == [c] and d["summary"] == {"entities": 1, "relations": 1}  # manual node and bridge are not "new"
    d = (await client.get(f"/investigations/{inv}/diff", params={"since": 0})).json()
    assert d["summary"]["entities"] == 3 and d["summary"]["relations"] == 2
    assert (await client.get("/investigations/99/diff")).status_code == 404


async def test_timeline(client, db, monkeypatch):
    import time
    _setting_it()
    inv = db.new_investigation("t")
    t = [1_700_000_000.0]
    monkeypatch.setattr(time, "time", lambda: t[0])
    db.log_run(inv, "create", [], 1)
    f = lambda v, rel="evento_dominio", reason="r", src=("Dominio", "a.com"): db.add_finding(inv, "rdap", Finding(src, rel, ("Data", v), 1, reason))
    f("registrazione: 2014-05-12")
    f("scadenza: 2030-01-01")
    f("account Reddit creato: 2019-03-04")
    f("registrazione: non-una-data")  # unparseable
    f("boh: 2020-01-01")  # unknown kind
    db.add_finding(inv, "hibp", Finding(("Email", "b@a.com"), "presente_in_breach", ("Breach", "Adobe"), 1, "HIBP, 2013-10-04, dati esposti: x"))
    db.add_finding(inv, "hibp", Finding(("Email", "b@a.com"), "presente_in_breach", ("Breach", "Old"), 1, "HIBP, ?, dati esposti: x"))
    f("ultima modifica: 2021-02-02", src=("Dominio", "hid.com"))
    hid, _ = db.entity(inv, "Dominio", "hid.com")
    db.set_hidden(inv, [hid], True, cascade=False)
    man, _ = db.add_manual_entity(inv, "Persona", "Bob")
    t[0] = 1_700_100_000
    db.log_run(inv, "refresh", [], 1)

    tl = (await client.get(f"/investigations/{inv}/timeline")).json()
    assert tl["undated"] == 3
    assert [(e["kind"], e["date"]) for e in tl["events"]] == [
        ("breach", "2013-10-04"), ("registration", "2014-05-12"), ("first_seen", "2019-03-04"), ("manual", "2023-11-14"), ("run", "2023-11-14"),
        ("run", "2023-11-16"), ("expiry", "2030-01-01")]
    reg = next(e for e in tl["events"] if e["kind"] == "registration")
    assert reg["label"] == "registrazione: 2014-05-12" and reg["collector"] == "rdap" and reg["ts"] == 1399852800 and reg["related"] is not None
    assert next(e for e in tl["events"] if e["kind"] == "breach")["label"] == "Violazione dati: Adobe"
    assert [e["label"] for e in tl["events"] if e["kind"] == "run"] == ["Ricerca avviata", "Aggiornamento"]
    assert next(e for e in tl["events"] if e["kind"] == "manual")["entity"] == man
    from osint import settings
    settings.CFG["language"] = "en"
    assert features.timeline(db, inv)["events"][1]["label"] == "registered: 2014-05-12"
