import asyncio

from .collectors import applicable
from .correlate import correlate
from .db import DB
from .models import PIVOT, norm
from .settings import is_ignored_domain

# ponytail: one global semaphore, no per-host rate limit. Add per-host limiter if a source starts throttling.
SEM = asyncio.Semaphore(8)


def set_concurrency(n: int) -> None:
    global SEM
    SEM = asyncio.Semaphore(n)  # takes effect for the next collector call; running ones keep the old limiter


async def _run_one(db: DB, c, type_: str, value: str, fresh: bool = False):
    cached = None if fresh else db.cache_get(c.name, type_, value)
    if cached is not None:
        return cached
    async with SEM:
        findings = await c.fn(value)
    db.cache_put(c.name, type_, value, findings)
    return findings


def _follow(f, depth: int, max_depth: int, db: DB, inv: int, max_entities: int) -> bool:
    if not f.pivot or f.dst[0] not in PIVOT or depth >= max_depth or db.count_entities(inv) >= max_entities:
        return False
    return not (f.dst[0] == "Dominio" and is_ignored_domain(norm(*f.dst)))  # gmail.com & co are not traced from a finding


async def investigate(db: DB, inv: int, seeds: list[tuple[str, str]], max_depth: int, max_entities: int, emit, *,
                      fresh: bool = False, seed_depths: dict | None = None):
    """Level-by-level BFS. Each new pivotable entity is queried at the next depth. Results are stored as each collector
    finishes, so cancelling the task (Stop) keeps everything found so far.
    fresh=True ignores cached collector results (refresh). seed_depths gives a seed its own depth (a seed with depth d
    starts d levels below max_depth, so every seed stops at its own limit)."""
    seen: set[tuple[str, str]] = set()
    own = seed_depths or {}
    level = [(t, norm(t, v), max_depth - own.get((t, norm(t, v)), max_depth)) for t, v in seeds]
    stopped = False
    before = db.count_entities(inv)
    try:
        while level:
            jobs = {}
            for t, v, depth in level:
                if (t, v) in seen or db.is_deleted(inv, t, v):  # deleted by the user: neither queried nor brought back
                    continue
                seen.add((t, v))
                db.entity(inv, t, v)
                for c in applicable(t):
                    jobs[asyncio.create_task(_run_one(db, c, t, v, fresh))] = (c, v, depth)
            level, pending = [], set(jobs)
            try:
                while pending:
                    done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        c, v, depth = jobs[task]
                        if task.exception():
                            emit({"type": "error", "collector": c.name, "target": v, "error": repr(task.exception())})
                            continue
                        res = task.result()
                        emit({"type": "run", "collector": c.name, "target": v, "found": len(res)})
                        for f in res:
                            if db.add_finding(inv, c.name, f):
                                emit({"type": "entity", "entity": {"type": f.dst[0], "value": norm(*f.dst)}, "via": c.name})
                            if _follow(f, depth, max_depth, db, inv, max_entities):
                                level.append((f.dst[0], norm(*f.dst), depth + 1))
            except asyncio.CancelledError:
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)  # let collectors clean up (e.g. kill a Maigret scan)
                stopped = True
                break
    finally:
        db.save_links(inv, correlate(db.graph(inv)))
        db.touch(inv)
        emit({"type": "done", "stopped": stopped, "new": db.count_entities(inv) - before})
