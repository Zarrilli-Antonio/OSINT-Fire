"""Discord: there is no public user search, so the only open door is the invite link. An invite (discord.gg/<code>) shows, without any
login, the server's name, description, size and, when the invite has one, who created it. Invite links found on pages become Account
nodes; this reads them. Server and user ids are snowflakes: the creation time is encoded in them."""
import re
from datetime import datetime, timezone

import httpx

from ..models import Finding
from . import collector
from .domain import HTTP

INVITE = re.compile(r"^https?://(?:www\.)?(?:discord\.gg|discord(?:app)?\.com/invite)/([\w-]{2,32})/?$", re.I)
EPOCH_MS = 1420070400000  # 2015-01-01, the origin of Discord snowflakes


def invite_code(url: str) -> str | None:
    m = INVITE.match(url.strip())
    return m.group(1) if m else None


def snowflake_date(sid: str) -> str:
    return datetime.fromtimestamp(((int(sid) >> 22) + EPOCH_MS) / 1000, timezone.utc).strftime("%Y-%m-%d")


def parse_invite(url: str, d: dict) -> list[Finding]:
    g = d.get("guild") or {}
    gid = str(d.get("guild_id") or g.get("id") or "")
    if not gid.isdigit() or not g.get("name"):
        return []
    src = ("Account", url)
    members = d.get("approximate_member_count")
    reason = "invito pubblico Discord" + (f" ({members} membri)" if members else "")
    server = ("Servizio", f"Discord: {g['name']} ({gid})")
    out = [Finding(src, "server_discord", server, 0.9, reason, url=url, raw={"members": members, "online": d.get("approximate_presence_count"), "description": g.get("description")}, pivot=False),
           Finding(server, "evento_server", ("Data", f"server Discord creato: {snowflake_date(gid)}"), 0.95, "data codificata nell'ID del server", url=url, pivot=False)]
    inv = d.get("inviter") or {}
    if inv.get("username"):
        who = ("Username", str(inv["username"]))
        out.append(Finding(src, "invito_creato_da", who, 0.6, "creatore dell'invito Discord", url=url, raw={"id": inv.get("id")}, pivot=False))
        if inv.get("global_name"):
            out.append(Finding(who, "nome_profilo", ("Persona", str(inv["global_name"])), 0.4, "nome visualizzato su Discord", url=url, pivot=False))
        if str(inv.get("id", "")).isdigit():
            out.append(Finding(who, "evento_account", ("Data", f"account Discord creato: {snowflake_date(str(inv['id']))}"), 0.95, "data codificata nell'ID dell'utente", url=url, pivot=False))
    return out


@collector("discord_invite", "Account")
async def discord_invite(url: str) -> list[Finding]:
    code = invite_code(url)
    if not code:
        return []
    async with httpx.AsyncClient(**HTTP) as c:
        r = await c.get(f"https://discord.com/api/v10/invites/{code}", params={"with_counts": "true"})
    if r.status_code in (404, 410):  # unknown or expired invite
        return []
    r.raise_for_status()
    return parse_invite(url, r.json())
