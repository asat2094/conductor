"""
run_dag — the integration orchestrator (ADR-0011/0022/0023/0024). Wires the built spine:
decompose (hard gate) -> verify (advisory) -> per-wave [cost_skip -> dispatch -> harness-derived tracking].

process_unit(subtask, workdir) -> verdict  is INJECTED. Default wraps the existing run_pipeline
(full provider engine). Tests inject a fake. codegraph `edges` default None -> verify is
declaration-only (degrade-clean). Roles are model-assignments in isolated context (ADR-0024):
each unit is processed from its own brief, never the main-thread history.

SEAMS (not built here): per-unit TDD gate sequence (RED/GREEN/mutation — lives inside process_unit),
role_model_policy resolver, per-wave codegraph re-index re-verify (REQ-D9), full pluggable tracker sinks.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from harness.decompose import decompose
from harness.verify import verify_decomposition, VerifyReport
from harness.router import cost_skip
from harness.run_brief import brief_to_subtask
from harness.tracker import Tracker, UnitState
from harness.models import AgentType

ProcessUnit = Callable[[Any, str], Any]


@dataclass
class DagRunResult:
    waves: list[list[str]]
    board: dict[str, dict[str, Any]]
    verify: VerifyReport
    accepted: int = 0
    failed: int = 0
    inline: int = 0
    verdicts: dict[str, Any] = field(default_factory=dict)


def _default_process_unit(subtask: Any, workdir: str) -> Any:
    from harness.pipeline import run_pipeline
    return run_pipeline(subtask, workdir=workdir)


def run_dag(
    briefs: list[dict],
    workdir: str = ".",
    *,
    process_unit: Optional[ProcessUnit] = None,
    tracker: Optional[Tracker] = None,
    edges: Optional[dict] = None,
    accept_threshold: int = 70,
) -> DagRunResult:
    process_unit = process_unit or _default_process_unit
    tracker = tracker or Tracker()

    waves = decompose(briefs)
    report = verify_decomposition(briefs, edges=edges)
    by_id = {b["id"]: b for b in briefs}

    accepted = failed = inline = 0
    verdicts: dict[str, Any] = {}
    for wave in waves:
        for uid in wave:
            brief = by_id[uid]
            st = brief_to_subtask(brief, workdir)
            if cost_skip(st) == AgentType.CLAUDE_INLINE:
                tracker.record(uid, UnitState.INLINE)
                inline += 1
                continue
            tracker.record(uid, UnitState.DISPATCHED)
            verdict = process_unit(st, workdir)
            verdicts[uid] = verdict
            if getattr(verdict, "routed_to_claude", False):
                tracker.record(uid, UnitState.INLINE, escalated=True)
                inline += 1
            elif getattr(verdict, "final_score", 0) >= accept_threshold:
                tracker.record(uid, UnitState.ACCEPTED, score=verdict.final_score, maker=getattr(verdict, "agent_used", "?"))
                accepted += 1
            else:
                tracker.record(uid, UnitState.FAILED, score=getattr(verdict, "final_score", 0))
                failed += 1

    return DagRunResult(
        waves=waves, board=tracker.board(), verify=report,
        accepted=accepted, failed=failed, inline=inline, verdicts=verdicts,
    )
