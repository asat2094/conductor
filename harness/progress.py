"""
Live development-progress surfacing (ADR-0023, REQ-OBS5/OBS6). The tracking *mechanism* is the
event-sourced board (tracker_store); this module makes it WATCHABLE — for the human (program-manager
live stream + table) and for external PM/kanban tools (JSONL/webhook sinks they consume). All sinks
are pluggable callables `fn(event_dict)` registered via TrackerStore.add_sink. Progress is
harness-derived (NFR-TRACK-1): a sink only reports recorded events, it cannot change a verdict.

External-dependency path: point a kanban/PM tool at the JSONL file (or webhook) — it tails the
harness's ground-truth event stream. No coupling; the harness stays the source of truth.
"""
import json
from typing import Any, Callable, Optional


def _fmt_event(e: dict) -> str:
    """One-line program-manager view of a single event."""
    meta = e.get("meta", {}) or {}
    bits = " ".join(f"{k}={v}" for k, v in meta.items())
    return f"[progress] {e.get('unit_id','?'):<16} {e.get('state','?'):<12} {bits}".rstrip()


def live_sink(write: Callable[[str], None] = print) -> Callable[[dict], None]:
    """A sink that streams each event as it happens (the live view during a run)."""
    def sink(event: dict) -> None:
        write(_fmt_event(event))
    return sink


def jsonl_sink(path: str, *, opener: Callable = open) -> Callable[[dict], None]:
    """A sink that appends each event as a JSON line — the file an external PM/kanban tool tails."""
    def sink(event: dict) -> None:
        with opener(path, "a") as fh:
            fh.write(json.dumps(event, default=str) + "\n")
    return sink


def webhook_sink(post: Callable[[dict], Any]) -> Callable[[dict], None]:
    """A sink that POSTs each event to an external PM service (post injected; failures swallowed —
    observability must never break the build)."""
    def sink(event: dict) -> None:
        try:
            post(event)
        except Exception:
            pass
    return sink


def rollup_of(board: dict) -> dict:
    """Count units per state, from a board() projection."""
    counts: dict[str, int] = {}
    for info in board.values():
        counts[info["state"]] = counts.get(info["state"], 0) + 1
    return counts


def render_board(board: dict, *, rollup: Optional[dict] = None) -> str:
    """Human program-manager table over any board() projection (works for Tracker or TrackerStore)."""
    lines = ["unit                 state         detail"]
    for unit, info in sorted(board.items()):
        detail = " ".join(f"{k}={v}" for k, v in info.items() if k != "state")
        lines.append(f"{unit:<20} {info['state']:<13} {detail}")
    roll = rollup if rollup is not None else rollup_of(board)
    lines.append("rollup: " + " ".join(f"{k}={v}" for k, v in sorted(roll.items())))
    return "\n".join(lines)


__all__ = ["live_sink", "jsonl_sink", "webhook_sink", "render_board", "rollup_of"]
