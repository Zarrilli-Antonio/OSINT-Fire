"""Entity-resolution: score likely-same-subject links between entities, from signals over the stored graph.

A link is a hypothesis, never a fact. Signals combine with noisy-OR; a name alone never reaches the threshold.
"""
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from itertools import combinations
from urllib.parse import urlparse

from .images import hamming

AUTO = 0.7    # >= : drawn as a real edge
REVIEW = 0.35  # >= : shown in "da verificare"
IDENTITY = {"Username", "Email", "Account", "Persona"}
MAX_IMAGE_OWNERS = 4  # an image on more entities is a default/stock avatar: no signal
MAX_IP_DOMAINS = 3  # IPs hosting more domains are shared hosting/CDN: no signal


@dataclass
class Link:
    a: int
    b: int
    signals: list = field(default_factory=list)  # [(name, weight)]

    @property
    def score(self) -> float:
        p = 1.0
        for _, w in self.signals:
            p *= 1 - w
        return round(1 - p, 3)


def name_key(s: str) -> frozenset:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return frozenset(re.findall(r"[a-z0-9]+", s))


def handles(url: str) -> set[str]:
    u = urlparse(url)
    segs = [x.lstrip("@").lower() for x in u.path.split("/") if x][:2]
    sub = u.hostname.split(".")[:-2] if u.hostname else []
    return set(segs) | {x for x in sub if x != "www"}


def correlate(graph: dict) -> list[Link]:
    nodes = {n["id"]: n for n in graph["nodes"]}
    linked = {frozenset((e["src"], e["dst"])) for e in graph["edges"]}
    links: dict[frozenset, Link] = {}

    def add(a: int, b: int, name: str, w: float):
        k = frozenset((a, b))
        if a == b or k in linked:
            return
        links.setdefault(k, Link(*sorted((a, b)))).signals.append((name, w))

    users = [n for n in nodes.values() if n["type"] == "Username"]
    emails = [n for n in nodes.values() if n["type"] == "Email"]
    accounts = [n for n in nodes.values() if n["type"] == "Account"]

    # email local-part vs username: equal or similar
    for e, u in ((e, u) for e in emails for u in users):
        local = e["value"].split("@")[0]
        if local == u["value"]:
            add(e["id"], u["id"], "parte locale email uguale all'username", 0.6)
        elif SequenceMatcher(None, local, u["value"]).ratio() >= 0.8:
            add(e["id"], u["id"], "username simile alla parte locale email", 0.35)
    for a, b in combinations(users, 2):
        if SequenceMatcher(None, a["value"], b["value"]).ratio() >= 0.8:
            add(a["id"], b["id"], "username simili", 0.35)

    # username equal to the handle in an account URL found by another route
    for u, a in ((u, a) for u in users for a in accounts):
        if u["value"] in handles(a["value"]):
            add(u["id"], a["id"], "username presente nell'URL dell'account", 0.5)

    # same person name on different entities (weak: common names)
    by_name = defaultdict(set)
    for e in graph["edges"]:
        for p, other in ((e["src"], e["dst"]), (e["dst"], e["src"])):
            if nodes[p]["type"] == "Persona" and nodes[other]["type"] in IDENTITY - {"Persona"}:
                key = name_key(nodes[p]["value"])
                if len(key) >= 2:
                    by_name[key].add(other)
    for ids in by_name.values():
        for a, b in combinations(sorted(ids)[:20], 2):
            if not (nodes[a]["type"] == nodes[b]["type"] == "Account"):
                add(a, b, "stesso nome persona", 0.3)

    # same or near-identical profile picture (perceptual hash)
    owners = defaultdict(set)
    for e in graph["edges"]:
        for x, img in ((e["src"], e["dst"]), (e["dst"], e["src"])):
            if nodes[img]["type"] == "Immagine" and nodes[x]["type"] in IDENTITY:
                owners[img].add(x)
    pics = [(x, nodes[i]["value"]) for i, xs in owners.items() if len(xs) <= MAX_IMAGE_OWNERS for x in xs][:80]
    for (xa, ha), (xb, hb) in combinations(pics, 2):
        d = hamming(ha, hb)
        if d == 0:
            add(xa, xb, "stessa immagine profilo", 0.65)
        elif d <= 6:
            add(xa, xb, "immagine profilo molto simile", 0.5)

    # the same SSH/PGP key or phone number on different entities: near-proof of the same owner
    for kind, w, why in (("Chiave SSH", 0.9, "stessa chiave SSH pubblica"), ("Chiave PGP", 0.85, "stessa chiave PGP"),
                         ("Telefono", 0.7, "stesso numero di telefono"),
                         ("ID tracciamento", 0.85, "stesso identificativo di tracciamento/pubblicità"), ("App", 0.85, "stessa app mobile")):
        owners = defaultdict(set)
        for e in graph["edges"]:
            for x, k in ((e["src"], e["dst"]), (e["dst"], e["src"])):
                if nodes[k]["type"] == kind and nodes[x]["type"] in IDENTITY | {"Dominio"}:
                    owners[k].add(x)
        for xs in owners.values():
            if 2 <= len(xs) <= MAX_IMAGE_OWNERS:
                for a, b in combinations(sorted(xs), 2):
                    add(a, b, why, w)

    # domains resolving to the same (non-shared) IP
    by_ip = defaultdict(set)
    for e in graph["edges"]:
        if e["rel"] == "risolve_a":
            by_ip[e["dst"]].add(e["src"])
    for ids in by_ip.values():
        if 2 <= len(ids) <= MAX_IP_DOMAINS:
            for a, b in combinations(sorted(ids), 2):
                add(a, b, "stesso IP", 0.3)

    return [l for l in links.values() if l.score >= REVIEW]
