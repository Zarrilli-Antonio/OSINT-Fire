import json
import pathlib

from osint.collectors import COLLECTORS, more

FX = pathlib.Path(__file__).parent / "fixtures"


def test_commoncrawl_hosts_only_subdomains_distinct_and_capped():
    lines = [json.loads(l) for l in (FX / "commoncrawl_example.jsonl").read_text().splitlines() if l.startswith("{")]
    lines += [{"url": "https://Blog.example.com:8080/x"}, {"url": "http://evil-example.com/"}, {"url": "https://a.b.example.com/"}, {"url": "garbage"}]
    out = more.parse_commoncrawl("example.com", "CC-MAIN-2026-39", lines)
    assert [f.dst[1] for f in out] == ["a.b.example.com", "blog.example.com", "www.example.com"]
    assert all(f.rel == "sottodominio" and not f.pivot and "CC-MAIN-2026-39" in f.reason for f in out)
    big = [{"url": f"https://h{i}.example.com/"} for i in range(500)]
    assert len(more.parse_commoncrawl("example.com", "x", big)) == more.CC_HOSTS
    assert more.parse_commoncrawl("example.com", "x", []) == []


def test_rdap_asn_real_fixture_and_non_asn():
    d = json.loads((FX / "rdap_autnum_15169.json").read_text())
    out = more.parse_rdap_asn("AS15169 (8.8.8.0/24)", d, "u")
    assert {(f.dst[1], "registrant" in f.reason) for f in out} == {("Google LLC", True), ("Google LLC", False)}
    assert more.parse_rdap_asn("AS1", {}, "u") == []


def test_opencorporates_parse():
    j = {"results": {"companies": [
        {"company": {"name": "FERRARI S.P.A.", "company_number": "00159560366", "jurisdiction_code": "it", "registered_address_in_full": "Via Abetone 4, Maranello",
                     "opencorporates_url": "https://opencorporates.com/companies/it/00159560366", "current_status": "Active", "incorporation_date": "1960-01-01"}},
        {"company": {"name": "Other", "company_number": None}}]}}
    out = more.parse_opencorporates("Ferrari SpA", j)
    assert [(f.rel, f.dst) for f in out] == [("numero_registro", ("Registrazione", "IT 00159560366 — FERRARI S.P.A.")), ("registrato_in", ("Luogo", "Via Abetone 4, Maranello"))]
    assert more.parse_opencorporates("x", {}) == [] and more.parse_opencorporates("x", {"results": {"companies": []}}) == []


def test_registered_and_keyed():
    c = {x.name: x for x in COLLECTORS}
    assert c["opencorporates"].key == ("opencorporates_key",) and c["rdap_asn"].accepts == {"Rete"} and c["commoncrawl"].accepts == {"Dominio"}
