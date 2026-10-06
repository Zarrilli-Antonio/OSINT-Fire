import asyncio
import json
import sys
import tempfile
from pathlib import Path

import httpx

from ..images import phash_url
from ..models import Finding
from ..settings import CFG
from . import collector
from .domain import HTTP


# frozen app: the bundled executable re-runs itself in Maigret mode (see run_backend.py)
MAIGRET_CMD = [sys.executable, "--maigret"] if getattr(sys, "frozen", False) else [sys.executable, "-m", "maigret"]


def parse_maigret(report: dict, username: str) -> list[Finding]:
    out = []
    for site, d in report.items():
        st = d.get("status", {})
        if st.get("status") != "Claimed":
            continue
        url = d["url_user"]
        # same username on a site is a weak signal: may be another person
        out.append(Finding(("Username", username), "account", ("Account", url), 0.5,
                           f"username presente su {site}", url=url, raw={"site": site}, pivot=False))
        for key in ("fullname", "name"):
            if st.get("ids", {}).get(key):
                out.append(Finding(("Account", url), "nome_profilo", ("Persona", st["ids"][key]), 0.4,
                                   f"nome nel profilo {site}", url=url, pivot=False))
    return out


def avatar_urls(report: dict) -> dict[str, str]:
    """account url -> avatar url, for claimed accounts exposing one."""
    return {d["url_user"]: d["status"]["ids"]["image"] for d in report.values()
            if d.get("status", {}).get("status") == "Claimed" and str(d["status"].get("ids", {}).get("image", "")).startswith("http")}


@collector("maigret", "Username")
async def maigret(username: str) -> list[Finding]:
    with tempfile.TemporaryDirectory() as tmp:
        p = await asyncio.create_subprocess_exec(
            *MAIGRET_CMD, username, "--json", "simple", "--folderoutput", tmp, "--no-color", "--no-progressbar",
            "--timeout", str(CFG["maigret_timeout"]), "--top-sites", str(CFG["maigret_top_sites"]),
            *(["--proxy", CFG["proxy"]] if CFG["proxy"] else []),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            await asyncio.wait_for(p.wait(), 300)
        finally:
            if p.returncode is None:  # timeout or the search was stopped: do not leave the scan running
                p.kill()
        files = list(Path(tmp).glob("*.json"))
        if not files:
            return []
        report = json.loads(files[0].read_text())
    out = parse_maigret(report, username)
    avatars = list(avatar_urls(report).items())[:40]
    async with httpx.AsyncClient(follow_redirects=True, **HTTP) as c:
        hashes = await asyncio.gather(*(phash_url(c, u) for _, u in avatars))
    out += [Finding(("Account", acc), "immagine_profilo", ("Immagine", h[0]), 0.9, "avatar del profilo", url=u,
                    raw={"thumb": h[1]}, pivot=False)
            for (acc, u), h in zip(avatars, hashes) if h]
    return out
