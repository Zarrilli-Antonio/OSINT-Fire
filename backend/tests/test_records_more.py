import asyncio
import json
import pathlib

import pytest

from osint.collectors import COLLECTORS, more_records as m

FX = pathlib.Path(__file__).parent / "fixtures"
J = lambda n: json.loads((FX / n).read_text())  # noqa: E731
T = lambda n: (FX / n).read_text()  # noqa: E731


def test_registered():
    got = {(c.name, t) for c in COLLECTORS for t in c.accepts}
    want = {("sec_edgar", "Azienda"), ("usaspending", "Azienda"), ("icij_offshore", "Persona"), ("icij_offshore", "Azienda"), ("sanctions", "Persona"), ("sanctions", "Azienda"),
            ("vies", "Azienda"), ("dbpedia", "Persona"), ("dbpedia", "Azienda"), ("dbpedia", "Luogo"), ("nominatim", "Luogo"), ("openlibrary", "Persona"),
            ("courtlistener", "Persona"), ("courtlistener", "Azienda")}
    assert want <= got
    assert all(not c.key for c in COLLECTORS if c.name in {n for n, _ in want})


def test_name_key():
    assert m.name_key("ROSSI, Mário") == m.name_key("mario rossi") and m.same("Apple Inc.", "APPLE CORP") and not m.same("Ab", "Ab")


def test_sec():
    assert m.parse_sec_entities("Apple Inc", J("sec_entity.json")) == ["0000320193"]
    assert m.parse_sec_entities("Apple", {}) == []
    out = m.parse_sec_submission("Apple Inc", J("sec_submissions.json"))
    d = {(f.rel, f.dst[0]) for f in out}
    assert ("numero_registro", "Registrazione") in d and ("sede", "Luogo") in d and ("deposito_sec", "Documento") in d
    assert any("ONE APPLE PARK WAY" in f.dst[1] for f in out) and not any(f.pivot for f in out if f.dst[0] != "Dominio")
    assert m.parse_sec_submission("x", {}) == []


def test_usaspending():
    out = m.parse_usaspending("Lockheed Martin Corp", J("usaspending.json"))
    assert out and all("UEI" in f.dst[1] for f in out) and not out[0].pivot
    assert m.parse_usaspending("Nobody", J("usaspending.json")) == [] and m.parse_usaspending("x", {}) == []


def test_icij_is_weak():
    out = m.parse_icij("Azienda", "Mossack Fonseca & Co.", J("icij_reconcile.json"))
    assert out and all(f.conf <= 0.3 and "non verificata" in f.reason and not f.pivot for f in out)
    assert m.parse_icij("Azienda", "Zzz Unrelated", J("icij_reconcile.json")) == [] and m.parse_icij("Persona", "x", {}) == []


def test_sanctions_lists_and_matching():
    idx = m.build_index({"OFAC SDN": T("ofac_sdn.csv"), "UE": T("eu_sanctions.csv"), "ONU": T("un_consolidated.xml")})
    out = m.parse_sanctions("Persona", "Sa'ad bin Laden", idx)
    assert [f.dst[1] for f in out] == ["sanzioni OFAC SDN: BIN LADEN, Sa'ad"] and out[0].conf <= 0.3 and not out[0].pivot
    assert m.parse_sanctions("Azienda", "Banco Nacional de Cuba", idx)
    assert m.parse_sanctions("Persona", "Saddam Hussein Al-Tikriti", idx)[0].dst[1].startswith("sanzioni UE")
    assert m.parse_sanctions("Azienda", "Allied Democratic Forces", idx)[0].dst[1].startswith("sanzioni ONU")
    assert m.parse_sanctions("Persona", "Mario Rossi", idx) == [] and m.parse_sanctions("Persona", "x", {}) == []
    assert list(m.parse_un("garbage")) == [] and list(m.parse_ofac("")) == []


def test_sanctions_collector_uses_injected_download(monkeypatch):
    calls = []

    async def fake():
        calls.append(1)
        return {"OFAC SDN": T("ofac_sdn.csv")}
    monkeypatch.setattr(m, "fetch_lists", fake)
    m._sanc.update(ts=0.0, idx={})
    assert asyncio.run(m.sanctions_person("Banco Nacional de Cuba"))
    assert asyncio.run(m.sanctions_company("Casa x")) == [] and len(calls) == 1  # cached the second time


def test_vies():
    assert m.vat_id("it 007.431.10157") == ("IT", "00743110157") and m.vat_id("Ferrari SpA") is None
    j = {**J("vies.json"), "countryCode": "IT"}
    out = m.parse_vies("IT00743110157", j)
    assert {f.rel for f in out} == {"numero_registro", "nome_organizzazione", "indirizzo_registrato"}
    assert "MILANO" in [f for f in out if f.rel == "indirizzo_registrato"][0].dst[1]
    assert len(m.parse_vies("x", {"isValid": True, "name": "---", "address": "---", "vatNumber": "1"})) == 1
    assert m.parse_vies("x", {"isValid": False}) == []


def test_dbpedia():
    out = m.parse_dbpedia("Azienda", "Scuderia Ferrari", J("dbpedia_lookup.json"))
    assert [f.dst[1] for f in out] == ["http://dbpedia.org/resource/Scuderia_Ferrari"]
    assert m.parse_dbpedia("Persona", "Scuderia Ferrari", J("dbpedia_lookup.json")) == [] and m.parse_dbpedia("Luogo", "x", {}) == []


def test_nominatim():
    out = m.parse_nominatim("Via Abetone 4 Maranello", J("nominatim.json"))
    rels = {f.rel: f.dst[1] for f in out}
    assert rels["coordinate"] == "44.532575, 10.864192" and rels["paese"] == "Italia" and "Maranello" in rels["indirizzo_normalizzato"]
    assert m.parse_nominatim("x", []) == [] and m.parse_nominatim("x", {}) == []


def test_openlibrary():
    out = m.parse_openlibrary("Umberto Eco", J("openlibrary_authors.json"))
    assert out and all(f.conf <= 0.3 and f.pivot is False for f in out) and any(f.rel == "opera_nota" for f in out)
    assert m.parse_openlibrary("Mario Rossi", J("openlibrary_authors.json")) == [] and m.parse_openlibrary("x", {}) == []


def test_courtlistener_labelled_weak():
    out = m.parse_courtlistener("Azienda", "Enron", J("courtlistener.json"))
    assert len(out) == 3 and all(f.conf <= 0.3 and "solo corrispondenza sul nome" in f.reason and f.url.startswith("https://www.courtlistener.com/opinion/") for f in out)
    assert m.parse_courtlistener("Persona", "x", {}) == []
