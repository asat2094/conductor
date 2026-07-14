"""
Deterministic pre-dispatch lint over a set of SubtaskBriefs (REQ-D3, ADR-0011).
Catches dangling consumed symbols (no upstream producer) and placeholder text. This is a
syntactic guard — it catches missing references, NOT wrong groupings (that residual is
bounded by the assembly golden gate, ADR-0004).

TODO (Plan 3): add an external/pre-existing-symbol allowlist so units that consume existing repo symbols are not false-flagged.
"""

_PLACEHOLDERS = ("TODO", "TBD", "FIXME", "XXX", "<placeholder>")
_SCANNED_FIELDS = ("goal", "exit_criteria")


def lint_briefs(briefs: list[dict]) -> list[str]:
    """Return human-readable lint errors. Empty list == clean (decomposition may proceed)."""
    errors: list[str] = []

    # duplicate producer detection
    producer_count: dict[str, list[str]] = {}
    for b in briefs:
        for sym in b["contract"].get("produces", []):
            producer_count.setdefault(sym, []).append(b["id"])
    for sym, owners in producer_count.items():
        if len(owners) > 1:
            errors.append(f"symbol '{sym}' is produced by multiple units: {sorted(owners)}")

    produced: set[str] = set()
    for b in briefs:
        produced.update(b["contract"].get("produces", []))

    for b in briefs:
        uid = b["id"]
        for sym in b["contract"].get("consumes", []):
            if sym not in produced:
                errors.append(f"{uid}: consumes '{sym}' but no unit produces it")
        for fieldname in _SCANNED_FIELDS:
            text = b.get(fieldname, "") or ""
            for ph in _PLACEHOLDERS:
                if ph in text:
                    errors.append(f"{uid}: placeholder '{ph}' found in {fieldname}")
    return errors
