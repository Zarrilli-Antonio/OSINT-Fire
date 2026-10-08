import asyncio
import json
import pathlib

import httpx
import pytest

from osint.collectors import COLLECTORS as _C, more_threat as T
from osint.models import PIVOT, norm

COLLECTORS = {c.name: c for c in _C}
FX = pathlib.Path(__file__).parent / "fixtures"
rd = lambda n: (FX / n).read_text()  # noqa: E731


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    T.CACHE.clear()
    monkeypatch.setattr(T, "NVD_GAP", 0)


def test_registration():
    for n, (_, _, _, types) in T.FEEDS.items():
        assert COLLECTORS[n].accepts == set(types)
    for n in ("nvd", "cisa_kev", "epss"):
        assert "Vulnerabilità" in COLLECTORS[n].accepts and not COLLECTORS[n].key
    assert "Vulnerabilità" in PIVOT and norm("Vulnerabilità", " cve-2021-44228 ") == "CVE-2021-44228"


def test_feodo_and_lists():
    idx = T.parse_feodo(rd("feodo_ipblocklist.json"))
    ip = next(iter(idx.ips))
    f = T.feed_findings("IP", ip, "Feodo", idx)
    assert len(f) == 1 and f[0].rel == "listato_in" and f[0].dst == ("Servizio", "feed: Feodo") and not f[0].pivot
    assert T.feed_findings("IP", "192.0.2.1", "Feodo", idx) == [] and T.parse_feodo("garbage").ips == set()
    bl = T.parse_iplist(rd("blocklist_de_all.txt"))
    assert bl.hit("1.0.164.165") and not bl.hit("1.0.164.166") and T.parse_iplist("").ips == set()


def test_spamhaus_cidr_ipv6_safe():
    idx = T.parse_drop(rd("spamhaus_drop.txt"))
    assert idx.hit("1.10.17.9") == "1.10.16.0/20" and idx.hit("1.11.0.1") is None and idx.hit("2001:db8::1") is None
    assert idx.info["1.10.16.0/20"] == "SBL256894"


def test_urlhaus_and_openphish_hosts():
    u = T.parse_urlhaus_hosts(rd("urlhaus_hostfile.txt"))
    assert u.hit("123.YWXWW.net") and not u.hit("ywxww.net")
    o = T.parse_openphish(rd("openphish_feed.txt"))
    assert o.hit("getfollowersinstant.blogspot.com") and o.hit("worker-throbbing-cake-edea.roseober17.workers.dev")


def test_nvd_real_fixture():
    out = T.parse_nvd("CVE-2021-44228", json.loads(rd("nvd_cve_2021_44228.json")))
    by = {f.rel: f for f in out}
    assert by["punteggio_cvss"].dst == ("Servizio", "CVSS 10.0: critica") and by["punteggio_cvss"].conf == 0.95
    assert by["pubblicata_il"].dst == ("Data", "2021-12-10")
    assert 0 < sum(f.rel == "riferimento" for f in out) <= T.MAX_REFS and all(not f.pivot for f in out)
    assert T.parse_nvd("CVE-2021-44228", {}) == [] and T.parse_nvd("CVE-1999-0001", json.loads(rd("nvd_cve_2021_44228.json"))) == []


def test_kev_and_epss_real_fixtures():
    cat = T.parse_kev_catalog(rd("cisa_kev.json"))
    out = T.parse_kev("CVE-2021-44228", cat)
    assert ("Servizio", "sfruttata attivamente (CISA KEV)") in [f.dst for f in out] and max(f.conf for f in out) == 0.95
    assert T.parse_kev("CVE-2000-0001", cat) == [] and T.parse_kev_catalog("garbage") == {}
    e = T.parse_epss("CVE-2021-44228", json.loads(rd("epss_cve_2021_44228.json")))
    assert e[0].dst == ("Servizio", "EPSS 100.00% (percentile 100.0)") or e[0].dst[1].startswith("EPSS 99.")
    assert T.parse_epss("CVE-2021-44228", {"data": []}) == []


async def test_bulk_one_fetch_shared_and_ttl(monkeypatch):
    calls = []

    def handler(req):
        calls.append(str(req.url))
        return httpx.Response(200, text="192.0.2.7\n")

    real = httpx.AsyncClient
    monkeypatch.setattr(T.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **{k: v for k, v in kw.items() if k != "transport"}))
    res = await asyncio.gather(*[COLLECTORS["blocklist_de"].fn("192.0.2.7") for _ in range(5)])
    assert len(calls) == 1 and all(len(r) == 1 for r in res)
    assert await COLLECTORS["blocklist_de"].fn("192.0.2.8") == [] and len(calls) == 1
    T.CACHE["blocklist_de"] = (T.CACHE["blocklist_de"][0] - T.TTL - 1, T.CACHE["blocklist_de"][1])
    await COLLECTORS["blocklist_de"].fn("192.0.2.7")
    assert len(calls) == 2


async def test_vuln_collectors_http(monkeypatch):
    def handler(req):
        u = str(req.url)
        if "nvd" in u:
            return httpx.Response(200, text=rd("nvd_cve_2021_44228.json"))
        if "first.org" in u:
            return httpx.Response(200, text=rd("epss_cve_2021_44228.json"))
        return httpx.Response(200, text=rd("cisa_kev.json"))

    real = httpx.AsyncClient
    monkeypatch.setattr(T.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    for n in ("nvd", "cisa_kev", "epss"):
        assert await COLLECTORS[n].fn("cve-2021-44228")
        assert await COLLECTORS[n].fn("not-a-cve") == []


async def test_errors(monkeypatch):
    real = httpx.AsyncClient
    for status, ok in ((404, True), (429, False)):
        monkeypatch.setattr(T.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(lambda r: httpx.Response(status)), **kw))
        if ok:
            assert await COLLECTORS["nvd"].fn("CVE-2021-44228") == []
        else:
            with pytest.raises(httpx.HTTPStatusError):
                await COLLECTORS["epss"].fn("CVE-2021-44228")
