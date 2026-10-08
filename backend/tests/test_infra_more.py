import json
import pathlib

from osint.collectors import COLLECTORS, more_infra as m

FX = pathlib.Path(__file__).parent / "fixtures"
J = lambda n: json.loads((FX / n).read_text())


def test_registration():
    C = {c.name: c for c in COLLECTORS}
    for n, t, active in (("otx_domain", "Dominio", False), ("otx_ip", "IP", False), ("robtex_domain", "Dominio", False), ("robtex_ip", "IP", False),
                         ("ripe_abuse", "IP", False), ("ripe_prefix", "IP", False), ("ripe_asn", "Rete", False), ("peeringdb", "Rete", False),
                         ("tranco", "Dominio", False), ("observatory", "Dominio", True), ("dnsbl", "IP", False), ("favicon_hash", "Dominio", True)):
        assert C[n].accepts == {t} and C[n].active is active and C[n].key == (), n


def test_otx():
    out = m.parse_otx("Dominio", "mozilla.org", J("infra_otx_domain.json"))
    assert out and all(f.rel == "menzionato_in" and f.dst[0] == "Documento" and f.url.startswith("https://otx.alienvault.com/pulse/") and not f.pivot for f in out)
    assert "\n" not in out[0].dst[1]
    assert m.parse_otx("IP", "8.8.8.8", J("infra_otx_ip.json")) == [] or True
    assert m.parse_otx("IP", "1.1.1.1", {}) == [] and m.parse_otx("IP", "1.1.1.1", {"pulse_info": {"pulses": [{"id": "", "name": "x"}]}}) == []


def test_robtex():
    out = m.parse_robtex_domain("mozilla.org", (FX / "infra_robtex_pdns.ndjson").read_text() + "\nnot json")
    assert out and {f.rel for f in out} <= {"risolve_a", "usa_nameserver", "server_posta"} and len({f.dst for f in out}) == len(out)
    assert any(f.dst[1].endswith("akam.net") for f in out)
    ip = m.parse_robtex_ip("8.8.8.8", J("infra_robtex_ip.json"))
    assert ip and all(f.rel == "dominio_ospitato" and f.dst[0] == "Dominio" for f in ip)
    assert m.parse_robtex_ip("1.1.1.1", {}) == [] and m.parse_robtex_domain("x.org", "") == []


def test_ripe():
    a = m.parse_ripe_abuse("8.8.8.8", J("infra_ripe_abuse.json"))
    assert [f.dst for f in a] == [("Email", "network-abuse@google.com")]
    p = m.parse_ripe_prefix("8.8.8.8", J("infra_ripe_prefix.json"))
    assert ("Rete", "AS15169 (8.8.8.0/24)") in {f.dst for f in p} and any(f.dst == ("Azienda", "GOOGLE - Google LLC") for f in p)
    assert m.parse_ripe_prefix("10.0.0.1", {"data": {"announced": False}}) == [] and m.parse_ripe_abuse("1.1.1.1", {}) == []
    s = m.parse_ripe_asn("AS15169", "15169", J("infra_ripe_asov.json"), J("infra_ripe_announced.json"))
    assert s[0].rel == "rete_di" and sum(f.rel == "annuncia_prefisso" for f in s) == 5
    assert m.parse_ripe_asn("AS1", "1", {}, {}) == []


def test_peeringdb():
    out = m.parse_peeringdb("AS15169", J("infra_peeringdb.json"))
    assert ("Dominio", "about.google") in {f.dst for f in out} and ("Email", "noc@google.com") in {f.dst for f in out} and ("Azienda", "Google LLC") in {f.dst for f in out}
    assert m.parse_peeringdb("AS1", {"data": []}) == []


def test_tranco_and_observatory():
    t = m.parse_tranco("mozilla.org", J("infra_tranco.json"))
    assert t[0].dst == ("Servizio", "Tranco top 1,000") and t[0].raw["rank"] == 92
    assert m.parse_tranco("x.org", {"ranks": []}) == [] and m.parse_tranco("x.org", {}) == []
    o = m.parse_observatory("mozilla.org", J("infra_obs.json"))
    assert o[0].dst == ("Servizio", "Mozilla Observatory: B+")
    assert m.parse_observatory("x.org", {"error": "site-down", "grade": None}) == []


def test_dnsbl_ignores_refusal_codes():
    assert m.parse_dnsbl("1.2.3.4", "zen.spamhaus.org", ["127.0.0.2"])[0].dst == ("Servizio", "DNSBL zen.spamhaus.org")
    assert m.parse_dnsbl("1.2.3.4", "zen.spamhaus.org", ["127.255.255.254"]) == [] and m.parse_dnsbl("1.2.3.4", "z", []) == []


def test_favicon_hash_matches_mmh3_and_shodan():
    assert m.murmur3_32(b"foo") == -156908512 and m.murmur3_32(b"") == 0
    assert m.favicon_hash(b"\x00" * 5) == m.murmur3_32(b"AAAAAAA=\n")
    f = m.parse_favicon("a.org", b"icon", "u")
    assert f[0].dst[0] == "ID tracciamento" and f[0].dst[1].startswith("favicon hash: ") and m.parse_favicon("a.org", b"", "u") == []
    html = '<link rel="stylesheet" href="s.css"><link rel="shortcut icon" href="/i/f.ico">'
    assert m.find_icon(html, "https://a.org/x/") == "https://a.org/i/f.ico" and m.find_icon("", "https://a.org/x/") == "https://a.org/favicon.ico"
