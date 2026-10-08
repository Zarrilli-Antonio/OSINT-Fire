import json
from pathlib import Path

from osint import collectors
from osint.features import parse_seeds
from osint.collectors import more_crypto as m
from osint.models import norm, wallet_kind

F = Path(__file__).parent / "fixtures"
BTC, ETH = "1BoatSLRHtKNngkdXEeobR76b53LETtpyT", "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"


def test_wallet_detect_and_norm():
    assert wallet_kind(BTC) == "btc" and wallet_kind(ETH) == "eth" and wallet_kind("bc1pws6pvj75rcsc2eglpp9k570prnjh40nfpyahlyumk8y8smjayvasyhns5c") == "btc"
    assert wallet_kind("example.com") is None and wallet_kind("0x123") is None
    assert norm("Portafoglio", ETH) == ETH.lower() and norm("Portafoglio", BTC) == BTC
    s = parse_seeds(f"{BTC}\n{ETH}\nexample.com")["seeds"]
    assert {"type": "Portafoglio", "value": BTC} in s and {"type": "Portafoglio", "value": ETH.lower()} in s and {"type": "Dominio", "value": "example.com"} in s


def test_parse_btc():
    j = json.loads((F / "btc_mempool.json").read_text())
    out = m.parse_btc(BTC, j["info"], j["txs"])
    assert any(f.rel == "controparte" and not f.pivot and f.dst[1] != BTC for f in out)
    assert any(f.dst[0] == "Data" and f.dst[1].startswith("ultimo movimento: ") for f in out)
    assert all(f.dst[1] != BTC for f in out)


def test_parse_eth():
    j = json.loads((F / "eth_blockscout.json").read_text())
    out = m.parse_eth(ETH.lower(), j["address"], j["txs"]["items"])
    assert any(f.rel == "nome_ens" and f.dst == ("Dominio", "vitalik.eth") for f in out)
    assert any(f.rel == "controparte" for f in out)


def test_email_parsers():
    assert m.parse_disposable("a@mailinator.com") and not m.parse_disposable("a@example.org")
    assert m.parse_hudsonrock("a@b.c", {"stealers": []}) == [] and m.parse_hudsonrock("a@b.c", {})  == []
    f = m.parse_hudsonrock("a@b.c", {"stealers": [{"date_compromised": "2026-10-06T14:24:00.000Z", "top_passwords": ["1*3"]}]})
    assert f[0].dst == ("Breach", "Hudson Rock infostealer (2026-10-06)") and "1*3" not in str(f)
    assert m.parse_archive("a@b.c", {}) == []
    assert m.parse_archive("a@b.c", {"response": {"docs": [{"identifier": "x", "title": "t"}]}})[0].dst[0] == "Documento"


def test_registered():
    reg = {c.name: c for c in collectors.COLLECTORS}
    for n, t in [("btc_wallet", "Portafoglio"), ("eth_wallet", "Portafoglio"), ("email_disposable", "Email"), ("hudsonrock", "Email"), ("archive_uploader", "Email")]:
        assert t in reg[n].accepts and not reg[n].key
