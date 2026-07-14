"""
Producer→consumer dependency DAG over SubtaskBriefs (REQ-D1, ADR-0011).
A consumer depends on whichever unit produces a symbol it consumes; logical_deps add
explicit edges even without a shared symbol. topo_waves layers the DAG into dispatch waves;
units in the same wave are mutually independent and may be co-dispatched.
"""


class DagCycleError(Exception):
    """Raised when the dependency graph contains a cycle (cannot be ordered)."""


def build_edges(briefs: list[dict]) -> dict[str, set[str]]:
    """unit_id -> set of unit_ids it depends on."""
    produced_by: dict[str, str] = {}
    for b in briefs:
        for sym in b["contract"].get("produces", []):
            produced_by[sym] = b["id"]

    deps: dict[str, set[str]] = {b["id"]: set() for b in briefs}
    for b in briefs:
        uid = b["id"]
        for sym in b["contract"].get("consumes", []):
            producer = produced_by.get(sym)
            if producer is not None and producer != uid:
                deps[uid].add(producer)
        for ld in b.get("logical_deps", []):
            if ld in deps and ld != uid:
                deps[uid].add(ld)
    return deps


def topo_waves(deps: dict[str, set[str]]) -> list[list[str]]:
    """Kahn layered topological sort. Each wave is a sorted list of mutually-independent unit ids."""
    remaining = {uid: set(d) for uid, d in deps.items()}
    waves: list[list[str]] = []
    while remaining:
        ready = sorted(uid for uid, d in remaining.items() if not d)
        if not ready:
            raise DagCycleError(f"cycle among: {sorted(remaining)}")
        waves.append(ready)
        for uid in ready:
            del remaining[uid]
        for d in remaining.values():
            d.difference_update(ready)
    return waves


def writes_overlap(a: dict, b: dict) -> bool:
    """True if two units write any common file (cannot safely co-dispatch). REQ NFR-PERF-2."""
    return bool(set(a.get("writes_files", [])) & set(b.get("writes_files", [])))
