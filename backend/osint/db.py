import base64
import json
from collections import defaultdict
import sqlite3
import time
from dataclasses import asdict

from .models import Finding, norm
from .settings import CFG


SCHEMA = """
create table if not exists investigation(id integer primary key, name text not null default '', purpose text not null default '', created real);
create table if not exists entity(id integer primary key, inv integer, type text, value text, unique(inv, type, value));
create table if not exists evidence(id integer primary key, inv integer, collector text, url text, raw text, ts real);
create table if not exists relation(id integer primary key, inv integer, src integer, dst integer, rel text,
                                    conf real, reason text, evidence integer, unique(inv, src, dst, rel));
create table if not exists link(id integer primary key, inv integer, a integer, b integer, score real, signals text,
                                decision text, unique(inv, a, b));
create table if not exists setting(key text primary key, value text not null);
create table if not exists image(hash text primary key, data blob);
create table if not exists note(inv integer, entity integer, text text not null default '', starred integer not null default 0,
                                primary key(inv, entity));
create table if not exists run(collector text, type text, value text, ts real, findings text,
                               primary key(collector, type, value));
create table if not exists run_log(id integer primary key, inv integer, ts real, kind text, seeds text, depth integer);
create table if not exists layout(inv integer, entity integer, x real, y real, pinned integer not null default 0, primary key(inv, entity));
create table if not exists hidden(inv integer, entity integer, auto integer not null default 0, primary key(inv, entity));
create table if not exists deleted(inv integer, type text, value text, primary key(inv, type, value));
"""

# columns added after the first release: (table, column, ddl). Applied to fresh and old databases alike.
MIGRATIONS = [
    ("investigation", "seeds", "text not null default '[]'"),
    ("investigation", "max_depth", "integer not null default 2"),
    ("investigation", "max_entities", "integer not null default 300"),
    ("investigation", "updated", "real not null default 0"),
    ("investigation", "view", "text not null default ''"),
    ("entity", "added", "real not null default 0"),
    ("entity", "manual", "integer not null default 0"),  # created by the user, not by a collector
    ("relation", "manual", "integer not null default 0"),
    ("hidden", "auto", "integer not null default 0"),  # 1 = hidden only because the node it hung from was hidden or deleted
]


class DB:
    def __init__(self, path=":memory:"):
        self.c = sqlite3.connect(path, check_same_thread=False)
        self.c.row_factory = sqlite3.Row
        self.c.executescript(SCHEMA)
        if "name" not in {r["name"] for r in self.c.execute("pragma table_info(investigation)")}:  # DB from before names existed
            self.c.execute("alter table investigation add column name text not null default ''")
            self.c.execute("update investigation set name = 'Indagine ' || id where name = ''")
        for table, col, ddl in MIGRATIONS:
            if col not in {r["name"] for r in self.c.execute(f"pragma table_info({table})")}:
                self.c.execute(f"alter table {table} add column {col} {ddl}")
        # entities saved before timestamps existed count as added when their investigation was created
        self.c.execute("update entity set added = coalesce((select created from investigation i where i.id = entity.inv), 0) where added = 0")
        self.c.commit()

    def new_investigation(self, name: str, purpose: str = "", seeds: list | None = None, max_depth: int = 2, max_entities: int = 300) -> int:
        cur = self.c.execute("insert into investigation(name, purpose, created, seeds, max_depth, max_entities) values (?, ?, ?, ?, ?, ?)",
                             (name, purpose, time.time(), json.dumps(seeds or []), max_depth, max_entities))
        self.c.commit()
        return cur.lastrowid

    def entity(self, inv: int, type_: str, value: str) -> tuple[int, bool]:
        """Return (id, created)."""
        value = norm(type_, value)
        row = self.c.execute("select id from entity where inv=? and type=? and value=?", (inv, type_, value)).fetchone()
        if row:
            return row["id"], False
        cur = self.c.execute("insert into entity(inv, type, value, added) values (?, ?, ?, ?)", (inv, type_, value, time.time()))
        self.c.commit()
        return cur.lastrowid, True

    def add_finding(self, inv: int, collector: str, f: Finding) -> bool:
        """Store finding. Return True if dst entity is new. Findings touching an entity the user deleted are dropped."""
        if self.is_deleted(inv, *f.src) or self.is_deleted(inv, *f.dst):
            return False
        src, _ = self.entity(inv, *f.src)
        dst, dst_new = self.entity(inv, *f.dst)
        raw = dict(f.raw)
        if f.dst[0] == "Immagine" and (thumb := raw.pop("thumb", None)):  # keep the blob out of the evidence rows
            self.c.execute("insert or ignore into image(hash, data) values (?, ?)", (f.dst[1], base64.b64decode(thumb)))
        ev = self.c.execute(
            "insert into evidence(inv, collector, url, raw, ts) values (?, ?, ?, ?, ?)",
            (inv, collector, f.url, json.dumps(raw), time.time()),
        ).lastrowid
        self.c.execute(
            "insert or ignore into relation(inv, src, dst, rel, conf, reason, evidence) values (?, ?, ?, ?, ?, ?, ?)",
            (inv, src, dst, f.rel, f.conf, f.reason, ev),
        )
        self.c.commit()
        return dst_new

    def count_entities(self, inv: int) -> int:
        return self.c.execute("select count(*) from entity where inv=?", (inv,)).fetchone()[0]

    def cache_get(self, collector: str, type_: str, value: str) -> list[Finding] | None:
        row = self.c.execute(
            "select ts, findings from run where collector=? and type=? and value=?", (collector, type_, value)
        ).fetchone()
        if not row or time.time() - row["ts"] >= CFG["cache_ttl_hours"] * 3600:
            return None
        return [Finding(src=tuple(d["src"]), dst=tuple(d["dst"]), **{k: v for k, v in d.items() if k not in ("src", "dst")})
                for d in json.loads(row["findings"])]

    def cache_put(self, collector: str, type_: str, value: str, findings: list[Finding]):
        self.c.execute(
            "insert or replace into run(collector, type, value, ts, findings) values (?, ?, ?, ?, ?)",
            (collector, type_, value, time.time(), json.dumps([asdict(f) for f in findings])),
        )
        self.c.commit()

    def graph(self, inv: int) -> dict:
        nodes = [dict(r) for r in self.c.execute("select id, type, value, added, manual from entity where inv=?", (inv,))]
        edges = [dict(r) for r in self.c.execute(
            "select r.id, r.src, r.dst, r.rel, r.conf, r.reason, r.manual, e.collector, e.url "
            "from relation r join evidence e on e.id = r.evidence where r.inv=?", (inv,))]
        hidden = [r[0] for r in self.c.execute("select entity from hidden where inv=?", (inv,))]
        return {"nodes": nodes, "edges": edges, "links": self.links(inv), "notes": self.notes(inv), "hidden": hidden}

    def save_links(self, inv: int, links) -> None:
        """Upsert score/signals; a user decision (confirmed/rejected) survives recomputation."""
        for l in links:
            self.c.execute(
                "insert into link(inv, a, b, score, signals) values (?, ?, ?, ?, ?) "
                "on conflict(inv, a, b) do update set score=excluded.score, signals=excluded.signals",
                (inv, l.a, l.b, l.score, json.dumps(l.signals)))
        self.c.commit()

    def decide(self, inv: int, link_id: int, decision: str | None) -> bool:
        cur = self.c.execute("update link set decision=? where id=? and inv=?", (decision, link_id, inv))
        self.c.commit()
        return cur.rowcount == 1

    def links(self, inv: int) -> list[dict]:
        from .correlate import AUTO
        out = []
        for r in self.c.execute("select * from link where inv=? and coalesce(decision,'') != 'rejected'", (inv,)):
            status = "confirmed" if r["decision"] == "confirmed" else "auto" if r["score"] >= AUTO else "review"
            out.append({"id": r["id"], "a": r["a"], "b": r["b"], "score": 1.0 if status == "confirmed" else r["score"],
                        "signals": json.loads(r["signals"]), "status": status})
        return out

    def list_investigations(self) -> list[dict]:
        return [dict(r) for r in self.c.execute(
            "select i.id, i.name, i.purpose, i.created, i.updated, (select count(*) from entity e where e.inv=i.id) as entities "
            "from investigation i order by i.id desc")]

    def get_investigation(self, inv: int) -> dict | None:
        r = self.c.execute("select id, name, purpose, created, updated from investigation where id=?", (inv,)).fetchone()
        return dict(r) if r else None

    def image(self, hash_: str) -> bytes | None:
        r = self.c.execute("select data from image where hash=?", (hash_,)).fetchone()
        return r["data"] if r else None

    def delete_investigation(self, inv: int) -> bool:
        """Remove an investigation and everything derived from it, including cached collector results and orphan images."""
        if not self.get_investigation(inv):
            return False
        c = self.c
        c.execute("delete from run where (type, value) in (select type, value from entity where inv=?)", (inv,))
        for t in ("relation", "link", "evidence", "note", "layout", "hidden", "deleted", "run_log", "entity"):
            c.execute(f"delete from {t} where inv=?", (inv,))
        c.execute("delete from investigation where id=?", (inv,))
        c.execute("delete from image where hash not in (select value from entity where type='Immagine')")
        c.commit()
        return True

    def set_note(self, inv: int, entity: int, text: str, starred: bool) -> bool:
        """Upsert the user's note/star on an entity. An empty, unstarred note is removed. False if the entity is not in [inv]."""
        if not self.c.execute("select 1 from entity where id=? and inv=?", (entity, inv)).fetchone():
            return False
        text = text.strip()
        if not text and not starred:
            self.c.execute("delete from note where inv=? and entity=?", (inv, entity))
        else:
            self.c.execute(
                "insert into note(inv, entity, text, starred) values (?, ?, ?, ?) "
                "on conflict(inv, entity) do update set text=excluded.text, starred=excluded.starred",
                (inv, entity, text, int(starred)))
        self.c.commit()
        return True

    def notes(self, inv: int) -> list[dict]:
        return [{"entity": r["entity"], "text": r["text"], "starred": bool(r["starred"])}
                for r in self.c.execute("select entity, text, starred from note where inv=?", (inv,))]

    def settings_rows(self) -> list[tuple[str, str]]:
        return [(r["key"], r["value"]) for r in self.c.execute("select key, value from setting")]

    def set_setting(self, key: str, value_json: str) -> None:
        self.c.execute("insert into setting(key, value) values (?, ?) on conflict(key) do update set value=excluded.value", (key, value_json))
        self.c.commit()

    def clear_cache(self) -> int:
        n = self.c.execute("select count(*) from run").fetchone()[0]
        self.c.execute("delete from run")
        self.c.commit()
        return n

    def backup_bytes(self) -> bytes:
        """Consistent copy of the whole database (investigations, notes, settings, cache)."""
        import os
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            dst = sqlite3.connect(path)
            self.c.backup(dst)
            dst.close()
            with open(path, "rb") as f:
                return f.read()
        finally:
            os.unlink(path)

    def wipe(self) -> int:
        n = self.c.execute("select count(*) from investigation").fetchone()[0]
        for t in ("relation", "link", "evidence", "note", "layout", "hidden", "deleted", "run_log", "entity", "investigation", "run", "image"):
            self.c.execute(f"delete from {t}")
        self.c.commit()
        return n


    # ---- search definition, history, layout ----

    def log_run(self, inv: int, kind: str, seeds: list, depth: int) -> None:
        self.c.execute("insert into run_log(inv, ts, kind, seeds, depth) values (?, ?, ?, ?, ?)", (inv, time.time(), kind, json.dumps(seeds), depth))
        self.c.commit()

    def touch(self, inv: int) -> None:
        self.c.execute("update investigation set updated=? where id=?", (time.time(), inv))
        self.c.commit()

    def investigation_detail(self, inv: int) -> dict | None:
        r = self.c.execute("select id, name, purpose, created, updated, seeds, max_depth, max_entities, view from investigation where id=?", (inv,)).fetchone()
        if not r:
            return None
        runs = [{"ts": x["ts"], "kind": x["kind"], "seeds": json.loads(x["seeds"]), "depth": x["depth"]}
                for x in self.c.execute("select ts, kind, seeds, depth from run_log where inv=? order by id", (inv,))]
        seeds = json.loads(r["seeds"])
        if not seeds and not runs:  # saved before the search definition was recorded: rebuild it from the graph
            seeds = self._infer_seeds(inv)
            if seeds:
                self.update_investigation(inv, seeds=seeds)
        return {"id": r["id"], "name": r["name"], "purpose": r["purpose"], "created": r["created"], "updated": r["updated"] or r["created"],
                "seeds": seeds, "max_depth": r["max_depth"], "max_entities": r["max_entities"], "runs": runs}

    def _infer_seeds(self, inv: int) -> list[dict]:
        """Searchable entities that nothing else pointed to: those are what the user typed in."""
        roots = self.c.execute(
            "select type, value from entity e where inv=? and type in ('Dominio','Email','Username','IP','Persona','Azienda','Telefono') "
            "and not exists (select 1 from relation r where r.dst = e.id) and exists (select 1 from relation r where r.src = e.id) order by id", (inv,))
        return [{"type": r["type"], "value": r["value"]} for r in roots]

    def update_investigation(self, inv: int, **fields) -> None:
        cols = {"name", "purpose", "seeds", "max_depth", "max_entities"}
        sets, vals = [], []
        for k, v in fields.items():
            if k in cols and v is not None:
                sets.append(f"{k}=?")
                vals.append(json.dumps(v) if k == "seeds" else v)
        if sets:
            self.c.execute(f"update investigation set {', '.join(sets)} where id=?", (*vals, inv))
            self.c.commit()

    def refresh_plan(self, inv: int) -> tuple[list[tuple[str, str]], dict[tuple[str, str], int], int]:
        """What to re-run to bring the investigation up to date: the base seeds at the base depth, plus every entity the user
        expanded by hand at the depth used then. Returns (seeds, depth per seed, max depth)."""
        d = self.investigation_detail(inv)
        depths: dict[tuple[str, str], int] = {}

        def add(seeds, depth):
            for t, v in seeds:
                k = (t, norm(t, v))
                depths[k] = max(depths.get(k, 0), depth)

        add([(s["type"], s["value"]) for s in d["seeds"]], d["max_depth"])
        for r in d["runs"]:
            if r["kind"] == "expand":
                add([(s["type"], s["value"]) for s in r["seeds"]], r["depth"])
        depths = {k: v for k, v in depths.items() if not self.is_deleted(inv, *k)}  # a seed the user deleted is not searched again
        return list(depths), depths, max(depths.values(), default=0)

    def save_layout(self, inv: int, nodes: list[dict], view: dict) -> None:
        """Remember where the user left the nodes (and the camera) so reopening shows the same picture."""
        valid = {r[0] for r in self.c.execute("select id from entity where inv=?", (inv,))}  # ids of another investigation are junk
        # merge, do not replace: a view that hides some nodes must not forget where those nodes are
        self.c.executemany("insert into layout(inv, entity, x, y, pinned) values (?, ?, ?, ?, ?) "
                           "on conflict(inv, entity) do update set x=excluded.x, y=excluded.y, pinned=excluded.pinned",
                           [(inv, n["id"], n["x"], n["y"], int(bool(n.get("pinned")))) for n in nodes if n["id"] in valid])
        self.c.execute("delete from layout where inv=? and entity not in (select id from entity where inv=?)", (inv, inv))
        self.c.execute("update investigation set view=? where id=?", (json.dumps(view), inv))
        self.c.commit()

    def layout(self, inv: int) -> dict:
        nodes = [{"id": r["entity"], "x": r["x"], "y": r["y"], "pinned": bool(r["pinned"])}
                 for r in self.c.execute("select entity, x, y, pinned from layout where inv=?", (inv,))]
        row = self.c.execute("select view from investigation where id=?", (inv,)).fetchone()
        return {"nodes": nodes, "view": json.loads(row["view"]) if row and row["view"] else {}}


    # ---- nodes and bridges made by the user, and hiding ----

    def add_manual_entity(self, inv: int, type_: str, value: str) -> tuple[int, bool]:
        """(id, created). An entity that already exists (found by a collector or added before) is returned untouched."""
        self.c.execute("delete from deleted where inv=? and type=? and value=?", (inv, type_, norm(type_, value)))  # adding it back is deliberate
        eid, created = self.entity(inv, type_, value)
        if created:
            self.c.execute("update entity set manual=1 where id=?", (eid,))
        self.c.commit()
        return eid, created

    def add_manual_relation(self, inv: int, src: int, dst: int, rel: str, reason: str = "") -> tuple[int, bool] | None:
        """(relation id, created), or None if an endpoint is not in this investigation."""
        ok = {r[0] for r in self.c.execute("select id from entity where inv=? and id in (?, ?)", (inv, src, dst))}
        if src == dst or {src, dst} - ok:
            return None
        row = self.c.execute("select id from relation where inv=? and src=? and dst=? and rel=?", (inv, src, dst, rel)).fetchone()
        if row:
            return row["id"], False
        ev = self.c.execute("insert into evidence(inv, collector, url, raw, ts) values (?, 'manuale', '', '{}', ?)", (inv, time.time())).lastrowid
        rid = self.c.execute("insert into relation(inv, src, dst, rel, conf, reason, evidence, manual) values (?, ?, ?, ?, 1.0, ?, ?, 1)",
                             (inv, src, dst, rel, reason or "aggiunto manualmente", ev)).lastrowid
        self.c.commit()
        return rid, True

    def update_manual_entity(self, inv: int, eid: int, type_: str | None, value: str | None) -> str:
        """'ok' | 'missing' (not found or not user-made) | 'duplicate' (another entity already has that type and value)."""
        r = self.c.execute("select type, value from entity where id=? and inv=? and manual=1", (eid, inv)).fetchone()
        if not r:
            return "missing"
        t, v = type_ or r["type"], norm(type_ or r["type"], value if value is not None else r["value"])
        if self.c.execute("select 1 from entity where inv=? and type=? and value=? and id!=?", (inv, t, v, eid)).fetchone():
            return "duplicate"
        self.c.execute("update entity set type=?, value=? where id=?", (t, v, eid))
        self.c.commit()
        return "ok"

    def is_deleted(self, inv: int, type_: str, value: str) -> bool:
        return self.c.execute("select 1 from deleted where inv=? and type=? and value=?", (inv, type_, norm(type_, value))).fetchone() is not None

    def _adjacency(self, inv: int) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
        out, nbr = defaultdict(set), defaultdict(set)
        for r in self.c.execute("select src, dst from relation where inv=?", (inv,)):
            out[r["src"]].add(r["dst"])
            nbr[r["src"]].add(r["dst"])
            nbr[r["dst"]].add(r["src"])
        return out, nbr

    def orphaned_by(self, inv: int, roots: set[int]) -> list[int]:
        """Nodes that hang from [roots] and would be left with no connection to anything still visible: the data that
        "started from" them. A parent is never swept up by its child, only the other way round."""
        out, nbr = self._adjacency(inv)
        gone = set(roots) | {r[0] for r in self.c.execute("select entity from hidden where inv=?", (inv,))}
        below, stack = set(), list(roots)
        while stack:  # everything reachable downwards (src -> dst) from the roots
            for c in out[stack.pop()]:
                if c not in below and c not in roots:
                    below.add(c)
                    stack.append(c)
        cand = below - gone
        result, seen = [], set()
        for start in sorted(cand):
            if start in seen:
                continue
            comp, stack, linked_outside = [], [start], False
            seen.add(start)
            while stack:  # a group of nodes that only reach each other: orphaned together or not at all
                n = stack.pop()
                comp.append(n)
                for m in nbr[n]:
                    if m in cand:
                        if m not in seen:
                            seen.add(m)
                            stack.append(m)
                    elif m not in gone:
                        linked_outside = True  # still connected to something that stays visible
            if not linked_outside:
                result += comp
        return sorted(result)

    def delete_entities(self, inv: int, ids: list[int], cascade: bool = True) -> tuple[int, list[int]]:
        """Delete nodes (user-made or collected) with their bridges, notes, links and layout. Collected ones are remembered so a
        refresh does not bring them back. With cascade, what hung only from them is hidden (reversible), not deleted.
        Returns (deleted count, ids hidden by the cascade)."""
        rows = self.c.execute(f"select id, type, value, manual from entity where inv=? and id in ({','.join('?' * len(ids))})", (inv, *ids)).fetchall() if ids else []
        gone = {r["id"] for r in rows}
        orphans = self.orphaned_by(inv, gone) if cascade and gone else []
        for r in rows:
            eid = r["id"]
            self.c.execute("delete from evidence where id in (select evidence from relation where inv=? and (src=? or dst=?))", (inv, eid, eid))
            self.c.execute("delete from relation where inv=? and (src=? or dst=?)", (inv, eid, eid))
            self.c.execute("delete from link where inv=? and (a=? or b=?)", (inv, eid, eid))
            for t in ("note", "layout", "hidden"):
                self.c.execute(f"delete from {t} where inv=? and entity=?", (inv, eid))
            self.c.execute("delete from entity where id=?", (eid,))
            if not r["manual"]:
                self.c.execute("insert or ignore into deleted(inv, type, value) values (?, ?, ?)", (inv, r["type"], r["value"]))
        for o in orphans:
            self.c.execute("insert or ignore into hidden(inv, entity, auto) values (?, ?, 1)", (inv, o))
        self.c.commit()
        return len(rows), orphans

    def delete_manual_relation(self, inv: int, rid: int) -> bool:
        r = self.c.execute("select evidence from relation where id=? and inv=? and manual=1", (rid, inv)).fetchone()
        if not r:
            return False
        self.c.execute("delete from relation where id=?", (rid,))
        self.c.execute("delete from evidence where id=?", (r["evidence"],))
        self.c.commit()
        return True

    def set_hidden(self, inv: int, ids: list[int], hide: bool, cascade: bool = True) -> list[int]:
        """Hide/show nodes. Hiding with cascade also hides what hung only from them (marked auto); showing restores those
        again as soon as they have a visible neighbour. Returns every id whose state changed."""
        valid = {r[0] for r in self.c.execute("select id from entity where inv=?", (inv,))} & set(ids)
        before = {r[0] for r in self.c.execute("select entity from hidden where inv=?", (inv,))}
        for eid in valid:
            if hide:  # explicit hide: also turns an auto-hidden node into one the user chose, so it is never auto-restored
                self.c.execute("insert into hidden(inv, entity, auto) values (?, ?, 0) on conflict(inv, entity) do update set auto=0", (inv, eid))
            else:
                self.c.execute("delete from hidden where inv=? and entity=?", (inv, eid))
        if hide and cascade:
            for o in self.orphaned_by(inv, valid):
                self.c.execute("insert or ignore into hidden(inv, entity, auto) values (?, ?, 1)", (inv, o))
        if not hide and cascade:
            _, nbr = self._adjacency(inv)
            changed = True
            while changed:
                changed = False
                hidden = {r[0] for r in self.c.execute("select entity from hidden where inv=?", (inv,))}
                for r in self.c.execute("select entity from hidden where inv=? and auto=1", (inv,)).fetchall():
                    if nbr[r[0]] - hidden:  # a neighbour is visible again
                        self.c.execute("delete from hidden where inv=? and entity=?", (inv, r[0]))
                        changed = True
        self.c.commit()
        after = {r[0] for r in self.c.execute("select entity from hidden where inv=?", (inv,))}
        return sorted(before ^ after)

    def clear_hidden(self, inv: int) -> None:
        self.c.execute("delete from hidden where inv=?", (inv,))
        self.c.commit()


def without_hidden(g: dict) -> dict:
    """The graph as the user sees it with hidden nodes switched off: nodes, their edges, links and notes."""
    hid = set(g.get("hidden", []))
    if not hid:
        return g
    return {"nodes": [n for n in g["nodes"] if n["id"] not in hid],
            "edges": [e for e in g["edges"] if e["src"] not in hid and e["dst"] not in hid],
            "links": [l for l in g["links"] if l["a"] not in hid and l["b"] not in hid],
            "notes": [n for n in g.get("notes", []) if n["entity"] not in hid], "hidden": []}
