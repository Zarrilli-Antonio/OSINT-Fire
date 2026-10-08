"""Extra sources: see the matching module in osint/i18n_ext."""
import time
from collections import Counter

import httpx

from ..models import Finding, wallet_kind
from . import collector
from .domain import HTTP

TOP = 10  # counterparties kept per wallet


def _day(ts) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


def _counter(me: str, addrs: list[str], url: str) -> list[Finding]:
    return [Finding(("Portafoglio", me), "controparte", ("Portafoglio", a), 0.8, f"{n} transazioni recenti in comune", url=url, pivot=False)
            for a, n in Counter(a for a in addrs if a and a.lower() != me.lower()).most_common(TOP)]


def parse_btc(me: str, info: dict, txs: list[dict]) -> list[Finding]:
    url = f"https://mempool.space/address/{me}"
    n = info.get("chain_stats", {}).get("tx_count", 0)
    out = [Finding(("Portafoglio", me), "transazioni", ("Servizio", f"Bitcoin: {n} transazioni, ricevuti {info['chain_stats']['funded_txo_sum'] / 1e8:.8f} BTC"),
                   1.0, "dati della blockchain Bitcoin", url=url, pivot=False)]
    times = [t["status"]["block_time"] for t in txs if t.get("status", {}).get("block_time")]
    if times:  # the page is newest first; the oldest one is the first movement only when the history fits in the page
        out.append(Finding(("Portafoglio", me), "creato_il", ("Data", f"ultimo movimento: {_day(max(times))}"), 0.95, "blockchain Bitcoin", url=url, pivot=False))
        if n <= len(txs):
            out.append(Finding(("Portafoglio", me), "creato_il", ("Data", f"portafoglio creato: {_day(min(times))}"), 0.95, "primo movimento sulla blockchain Bitcoin", url=url, pivot=False))
    addrs = [a for t in txs for a in [(v.get("prevout") or {}).get("scriptpubkey_address") for v in t.get("vin", [])] + [v.get("scriptpubkey_address") for v in t.get("vout", [])]]
    return out + _counter(me, addrs, url)


def parse_eth(me: str, d: dict, txs: list[dict]) -> list[Finding]:
    url = f"https://eth.blockscout.com/address/{me}"
    out = []
    if d.get("ens_domain_name"):
        out.append(Finding(("Portafoglio", me), "nome_ens", ("Dominio", d["ens_domain_name"].lower()), 0.95, "nome ENS del portafoglio", url=url, pivot=False))
    for name in dict.fromkeys(t["name"] for t in (d.get("metadata") or {}).get("tags", []) if t.get("name")):
        out.append(Finding(("Portafoglio", me), "etichetta", ("Servizio", name), 0.6, "etichetta pubblica Blockscout (non verificata)", url=url, pivot=False))
    if d.get("creator_address_hash"):
        out.append(Finding(("Portafoglio", me), "creato_da", ("Portafoglio", d["creator_address_hash"].lower()), 0.9, "creatore del contratto", url=url, pivot=False))
    if d.get("is_scam"):
        out.append(Finding(("Portafoglio", me), "segnalato", ("Servizio", "segnalato come truffa su Blockscout"), 0.7, "etichetta di reputazione Blockscout", url=url, pivot=False))
    items = txs
    stamps = sorted(t["timestamp"][:10] for t in items if t.get("timestamp"))
    if stamps:
        out.append(Finding(("Portafoglio", me), "creato_il", ("Data", f"ultimo movimento: {stamps[-1]}"), 0.95, "blockchain Ethereum", url=url, pivot=False))
    addrs = [((t.get(k) or {}).get("hash") or "").lower() for t in items for k in ("from", "to")]
    return out + _counter(me.lower(), addrs, url)


async def _get_json(c: httpx.AsyncClient, url: str):
    r = await c.get(url)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


@collector("btc_wallet", "Portafoglio")
async def btc_wallet(addr: str) -> list[Finding]:
    if wallet_kind(addr) != "btc":
        return []
    async with httpx.AsyncClient(**HTTP) as c:
        info = await _get_json(c, f"https://mempool.space/api/address/{addr}")
        if not info:
            return []
        txs = await _get_json(c, f"https://mempool.space/api/address/{addr}/txs/chain") or []
    return parse_btc(addr, info, txs)


@collector("eth_wallet", "Portafoglio")
async def eth_wallet(addr: str) -> list[Finding]:
    if wallet_kind(addr) != "eth":
        return []
    async with httpx.AsyncClient(**HTTP) as c:
        d = await _get_json(c, f"https://eth.blockscout.com/api/v2/addresses/{addr}")
        if not d:
            return []
        txs = (await _get_json(c, f"https://eth.blockscout.com/api/v2/addresses/{addr}/transactions") or {}).get("items", [])
    return parse_eth(addr, d, txs)


# ---- email intelligence ----

DISPOSABLE = {"mailinator.com", "guerrillamail.com", "guerrillamail.net", "guerrillamail.org", "sharklasers.com", "10minutemail.com", "10minutemail.net",
              "tempmail.com", "temp-mail.org", "temp-mail.io", "yopmail.com", "yopmail.fr", "trashmail.com", "trashmail.net", "throwawaymail.com",
              "getnada.com", "dispostable.com", "maildrop.cc", "fakeinbox.com", "mailnesia.com", "mytemp.email", "tempail.com", "emailondeck.com",
              "mohmal.com", "burnermail.io", "spamgourmet.com", "mintemail.com", "mailcatch.com", "tempinbox.com", "discard.email", "moakt.com",
              "inboxkitten.com", "tmpmail.org", "tmpmail.net", "33mail.com", "anonaddy.me", "simplelogin.com", "dropmail.me", "emailfake.com"}


def parse_disposable(email: str) -> list[Finding]:
    d = email.rsplit("@", 1)[-1].lower()
    if d in DISPOSABLE:
        return [Finding(("Email", email), "tipo_email", ("Servizio", f"email usa e getta o alias: {d}"), 0.9, "dominio nell'elenco dei servizi usa e getta", pivot=False)]
    return []


@collector("email_disposable", "Email")
async def email_disposable(email: str) -> list[Finding]:
    return parse_disposable(email)


def parse_hudsonrock(email: str, d: dict) -> list[Finding]:
    """Only the public summary: that a stealer log exists and when. Never the (masked) credentials the endpoint also returns."""
    st = d.get("stealers") or []
    if not st:
        return []
    dates = sorted((s.get("date_compromised") or "")[:10] for s in st)
    last = next((x for x in reversed(dates) if x), "?")
    return [Finding(("Email", email), "esposta_infostealer", ("Breach", f"Hudson Rock infostealer ({last})"), 0.8,
                    f"{len(st)} computer infettati da infostealer associati all'email (Hudson Rock)", url="https://www.hudsonrock.com/free-tools", pivot=False,
                    raw={"computers": len(st), "last": last})]


@collector("hudsonrock", "Email")
async def hudsonrock(email: str) -> list[Finding]:
    async with httpx.AsyncClient(**HTTP) as c:
        r = await c.get("https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-email", params={"email": email})
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return parse_hudsonrock(email, r.json())


def parse_archive(email: str, d: dict) -> list[Finding]:
    docs = (d.get("response") or {}).get("docs") or []
    return [Finding(("Email", email), "caricato", ("Documento", f"https://archive.org/details/{x['identifier']}"), 0.7,
                    "elemento caricato su Internet Archive con questa email come uploader", url=f"https://archive.org/details/{x['identifier']}", pivot=False,
                    raw={"title": x.get("title")}) for x in docs[:20] if x.get("identifier")]


@collector("archive_uploader", "Email")
async def archive_uploader(email: str) -> list[Finding]:
    async with httpx.AsyncClient(**HTTP) as c:
        r = await c.get("https://archive.org/advancedsearch.php", params={"q": f'uploader:"{email}"', "fl[]": ["identifier", "title"], "rows": 20, "output": "json"})
    r.raise_for_status()
    return parse_archive(email, r.json())
