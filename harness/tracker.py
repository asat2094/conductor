"""
Minimal event-sourced development board (ADR-0023 slice; REQ-OBS5/OBS7). Board is a pure
projection over an append-only event log. Progress is HARNESS-DERIVED (NFR-TRACK-1): the caller
records a state only from a harness fact (dispatch happened, gate passed) — never a maker claim.
Full pluggable render sinks (rich/MCP/webhook/external-PM) are deferred to the tracker plan.
"""
from dataclasses import dataclass, field
from typing import Any


class UnitState:
    PENDING = "PENDING"
    READY = "READY"
    DISPATCHED = "DISPATCHED"
    HEALING = "HEALING"
    ESCALATED = "ESCALATED"
    INTERVENE = "INTERVENE"
    INLINE = "INLINE"
    ACCEPTED = "ACCEPTED"
    FAILED = "FAILED"


@dataclass
class Event:
    unit_id: str
    state: str
    meta: dict[str, Any] = field(default_factory=dict)


class Tracker:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def record(self, unit_id: str, state: str, **meta: Any) -> None:
        self.events.append(Event(unit_id=unit_id, state=state, meta=meta))

    def board(self) -> dict[str, dict[str, Any]]:
        """Latest-state projection per unit (for the orchestrator/system-leader view)."""
        out: dict[str, dict[str, Any]] = {}
        for e in self.events:
            out[e.unit_id] = {"state": e.state, **e.meta}
        return out

    def rollup(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for unit, info in self.board().items():
            counts[info["state"]] = counts.get(info["state"], 0) + 1
        return counts

    def render_text(self) -> str:
        """Human program-manager view (stdlib, baked-in sink)."""
        lines = ["unit                 state         detail"]
        for unit, info in sorted(self.board().items()):
            detail = " ".join(f"{k}={v}" for k, v in info.items() if k != "state")
            lines.append(f"{unit:<20} {info['state']:<13} {detail}")
        roll = self.rollup()
        lines.append("rollup: " + " ".join(f"{k}={v}" for k, v in sorted(roll.items())))
        return "\n".join(lines)
