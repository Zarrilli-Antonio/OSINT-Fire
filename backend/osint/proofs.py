"""Proofs: a dated, hashed copy of a web page (plus an optional Internet Archive copy) to attach to an investigation."""
import asyncio
import hashlib
import ipaddress
import re
import socket
import time
from urllib.parse import urljoin, urlsplit

import httpx
from fastapi import HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import settings

MAX_BYTES = 5 * 1024 * 1024
MAX_HOPS = 5
TIMEOUT = 20
ARCHIVE_TIMEOUT = 60
_transport: httpx.AsyncBaseTransport | None = None  # tests inject a mock transport here


class Refused(ValueError):
    pass


async def resolve(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({i[4][0] for i in infos})


async def check_url(url: str) -> None:
    """SSRF guard: http(s) only, and the host must resolve only to public addresses. Raises Refused."""
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise Refused("only http and https URLs are allowed")
    try:
        addrs = [str(ipaddress.ip_address(p.hostname))]  # a literal address needs no lookup
    except ValueError:
        try:
            addrs = await resolve(p.hostname)
        except OSError:
            raise Refused("host does not resolve")
    for a in addrs:
        ip = ipaddress.ip_address(a.split("%")[0])
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise Refused("addresses on private or local networks are not allowed")
    # ponytail: lookup and connect resolve separately (DNS rebinding window). Pin the resolved IP if this ever faces untrusted users.


def _client(**kw) -> httpx.AsyncClient:
    proxy = settings.CFG["proxy"] or None
    return httpx.AsyncClient(headers={"User-Agent": settings.CFG["user_agent"]}, transport=_transport, **({} if _transport else {"proxy": proxy}), **kw)


async def fetch(url: str) -> dict:
    """GET [url], following redirects by hand so every hop is checked. Body is capped at MAX_BYTES."""
    async with _client(timeout=TIMEOUT, follow_redirects=False) as c:
        for _ in range(MAX_HOPS + 1):
            await check_url(url)
            async with c.stream("GET", url) as r:
                if r.is_redirect and (loc := r.headers.get("location")):
                    url = urljoin(url, loc)
                    continue
                body, truncated = b"", False
                async for chunk in r.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        body, truncated = body[:MAX_BYTES], True
                        break
                return {"url": url, "status": r.status_code, "content_type": r.headers.get("content-type", ""), "body": body, "truncated": truncated}
    raise Refused("too many redirects")


_MEMENTO = re.compile(r"<(https?://web\.archive\.org/web/\d+[^>]*)>\s*;\s*rel=\"[^\"]*memento[^\"]*\"")


def parse_archive(headers: dict, final_url: str = "") -> str:
    """The snapshot address from a Save Page Now response ('' if none)."""
    if cl := headers.get("content-location"):
        return urljoin("https://web.archive.org/", cl)
    if m := _MEMENTO.search(headers.get("link", "")):
        return m.group(1)
    return final_url if re.match(r"https?://web\.archive\.org/web/\d+", final_url) else ""


async def archive(url: str) -> tuple[str, str]:
    """(wayback url, error). Never raises: archiving is a bonus."""
    try:
        async with _client(timeout=ARCHIVE_TIMEOUT, follow_redirects=True) as c:
            r = await c.get("https://web.archive.org/save/" + url)
        if r.status_code >= 400:
            return "", f"archive.org answered HTTP {r.status_code}"
        if w := parse_archive(r.headers, str(r.url)):
            return w, ""
        return "", "archive.org did not return a snapshot address"
    except Exception as e:
        return "", f"archive.org request failed: {type(e).__name__}"


def list_for_report(db, inv: int) -> list[dict]:
    return [{"url": r["url"], "ts": r["ts"], "sha256": r["sha256"], "size": r["size"], "wayback": r["wayback"], "entity": r["entity"]}
            for r in db.c.execute("select url, ts, sha256, size, wayback, entity from proof where inv=? order by ts, id", (inv,))]


class NewProof(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    entity: int | None = None
    archive: bool = False


def register(app, get_db):
    @app.post("/investigations/{inv}/proofs")
    async def create_proof(inv: int, body: NewProof):
        db = get_db()
        if not db.get_investigation(inv):
            raise HTTPException(404)
        if body.entity is not None and not db.c.execute("select 1 from entity where id=? and inv=?", (body.entity, inv)).fetchone():
            raise HTTPException(404, "entity not found")
        url = body.url.strip()
        try:
            await check_url(url)
            f = await fetch(url)
        except Refused as e:
            raise HTTPException(422, str(e))
        except httpx.HTTPError as e:
            raise HTTPException(502, f"could not fetch the page: {type(e).__name__}")
        wayback, err = await archive(url) if body.archive else ("", "")
        ts, digest = time.time(), hashlib.sha256(f["body"]).hexdigest()
        pid = db.c.execute("insert into proof(inv, entity, url, ts, sha256, size, content_type, status, wayback, truncated, body) values (?,?,?,?,?,?,?,?,?,?,?)",
                           (inv, body.entity, f["url"], ts, digest, len(f["body"]), f["content_type"], f["status"], wayback, int(f["truncated"]), f["body"])).lastrowid
        db.c.commit()
        return {"id": pid, "url": f["url"], "ts": ts, "sha256": digest, "size": len(f["body"]), "status": f["status"], "content_type": f["content_type"],
                "wayback": wayback, "truncated": f["truncated"], "archive_error": err}

    @app.get("/investigations/{inv}/proofs")
    def list_proofs(inv: int, entity: int | None = None):
        db = get_db()
        if not db.get_investigation(inv):
            raise HTTPException(404)
        q, args = "select id, entity, url, ts, sha256, size, content_type, status, wayback, truncated from proof where inv=?", [inv]
        if entity is not None:
            q, args = q + " and entity=?", args + [entity]
        return [{**dict(r), "truncated": bool(r["truncated"])} for r in db.c.execute(q + " order by ts desc, id desc", args)]

    @app.get("/investigations/{inv}/proofs/{pid}/snapshot")
    def snapshot(inv: int, pid: int):
        r = get_db().c.execute("select body, content_type from proof where id=? and inv=?", (pid, inv)).fetchone()
        if not r:
            raise HTTPException(404)
        # the page is foreign content served from our own origin: sandbox it so scripts in it cannot call the API
        return Response(r["body"], media_type=r["content_type"] or "application/octet-stream",
                        headers={"Content-Disposition": "inline", "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:",
                                 "X-Content-Type-Options": "nosniff"})

    @app.delete("/investigations/{inv}/proofs/{pid}")
    def delete_proof(inv: int, pid: int):
        db = get_db()
        if not db.c.execute("delete from proof where id=? and inv=?", (pid, inv)).rowcount:
            raise HTTPException(404)
        db.c.commit()
        return {"ok": True}
