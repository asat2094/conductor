"""
Codegraph-backed decomposition verifier (ADR-0022, REQ-D6/D7/D8). ADVISORY and degrade-clean:
when no codegraph edges are supplied, returns status 'unverified' (declaration-only) and the
build proceeds on the lint-only gate. Never mutates the DAG. Bounded by static-analysis accuracy.

`edges` maps a file path -> list of symbols that file actually references (from codegraph).
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VerifyReport:
    status: str = "unverified"
    errors: list[str] = field(default_factory=list)   # reserved for ERROR-level findings (REQ-D6 high-confidence / dangling-vs-repo) — empty in this advisory slice; wave-incremental gating (REQ-D9) populates it
    warnings: list[str] = field(default_factory=list)
    coverage: float = 0.0
    dense: bool = False


_DENSITY_RATIO = 0.6


def _producer_of(briefs: list[dict]) -> dict[str, str]:
    owner: dict[str, str] = {}
    for b in briefs:
        for sym in b["contract"].get("produces", []):
            owner[sym] = b["id"]
    return owner


def _density(briefs: list[dict]) -> bool:
    n = len(briefs)
    if n < 2:
        return False
    edge_count = 0
    produced = _producer_of(briefs)
    for b in briefs:
        for sym in b["contract"].get("consumes", []):
            if produced.get(sym) not in (None, b["id"]):
                edge_count += 1
    return (edge_count / (n * (n - 1))) >= _DENSITY_RATIO


def verify_decomposition(briefs: list[dict], edges: Optional[dict] = None) -> VerifyReport:
    rep = VerifyReport(dense=_density(briefs))
    if edges is None:
        rep.status = "unverified"
        return rep

    rep.status = "verified"
    produced = _producer_of(briefs)

    declared_total = 0
    corroborated = 0
    for b in briefs:
        uid = b["id"]
        declared = set(b["contract"].get("consumes", []))
        referenced: set[str] = set()
        for f in b.get("files", []):
            referenced.update(edges.get(f, []))

        for sym in referenced:
            owner = produced.get(sym)
            if owner is not None and owner != uid and sym not in declared:
                rep.warnings.append(f"{uid}: references '{sym}' (produced by {owner}) but does not declare consumes it (under-declared edge)")

        for sym in declared:
            declared_total += 1
            if sym in referenced:
                corroborated += 1
            else:
                rep.warnings.append(f"{uid}: over-declared consume '{sym}' (never referenced in its files)")

    rep.coverage = (corroborated / declared_total) if declared_total else 1.0
    return rep
