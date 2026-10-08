from dataclasses import dataclass
from typing import Awaitable, Callable

from ..models import Finding


@dataclass
class Collector:
    name: str
    accepts: set[str]
    fn: Callable[[str], Awaitable[list[Finding]]]
    active: bool = False  # contacts the target's own servers (website, TLS port, DNS guessing), skipped in passive mode
    key: tuple[str, ...] = ()  # settings that hold the credentials this source needs (all must be set)


COLLECTORS: list[Collector] = []


def collector(name: str, *accepts: str, active: bool = False, key: str | tuple[str, ...] | None = None):
    keys = (key,) if isinstance(key, str) else tuple(key or ())

    def deco(fn):
        COLLECTORS.append(Collector(name, set(accepts), fn, active, keys))
        return fn
    return deco


def status(c: Collector) -> str:
    """'ok' or the reason it will not run: disabled | passive | nokey."""
    from ..settings import CFG
    if c.name in CFG["disabled_collectors"]:
        return "disabled"
    if c.active and CFG["passive_only"]:
        return "passive"
    if any(not CFG[k] for k in c.key):
        return "nokey"
    return "ok"


def applicable(type_: str) -> list[Collector]:
    return [c for c in COLLECTORS if type_ in c.accepts and status(c) == "ok"]


# Import for registration side effect.
from . import domain, email, ip, username, wikidata, web, github, subdomains, profiles, people, tls, pgp, phone, keys, social_html, keyed, extra, web_deep, connected, more, more_profiles, more_infra, more_threat, more_records, more_academic, more_crypto  # noqa: E402,F401
