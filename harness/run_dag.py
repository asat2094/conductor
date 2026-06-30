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
    assembly: Optional[str] = None   # merge-queue disposition: "ff_to_target" | "discard" | None


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
    merge_queue: Optional[Any] = None,
    reverify: Optional[Callable] = None,
    failure_mode: str = "continue_on_error",
    resume_from: Optional[dict] = None,
) -> DagRunResult:
    """Decompose -> verify -> per-wave [cost_skip -> dispatch -> track]. Optional integration:
    `merge_queue` (ADR-0004/0012): each ACCEPTED unit submitted; finalize() decides ff/discard.
    `reverify(by_id_briefs, accepted_so_far) -> VerifyReport` (REQ-D9): re-run at each wave boundary.
    `failure_mode` (ADR-0029, REQ-I5): 'continue_on_error' (default) | 'fail_fast' (abort remaining
    waves on first failure) | 'all_or_nothing' (any failure -> discard the build at finalize).
    `resume_from` (ADR-0028): a checkpoint dict; units already ACCEPTED are skipped (not re-dispatched).
    All default to current behavior (backward-compat)."""
    process_unit = process_unit or _default_process_unit
    tracker = tracker or Tracker()
    resumed = set((resume_from or {}).get("accepted", []))

    waves = decompose(briefs)
    report = verify_decomposition(briefs, edges=edges)
    by_id = {b["id"]: b for b in briefs}

    accepted = failed = inline = 0
    accepted_ids: list[str] = []
    verdicts: dict[str, Any] = {}
    aborted = False
    for wave in waves:
        if aborted:
            break
        for uid in wave:
            if uid in resumed:  # ADR-0028 resume: skip already-accepted work
                tracker.record(uid, UnitState.ACCEPTED, resumed=True)
                accepted += 1
                accepted_ids.append(uid)
                continue
            brief = by_id[uid]
            st = brief_to_subtask(brief, workdir)
            if cost_skip(st) == AgentType.CLAUDE_INLINE:
                tracker.record(uid, UnitState.INLINE)
                inline += 1
                continue
            tracker.record(uid, UnitState.DISPATCHED)
            verdict = process_unit(st, workdir)
            verdicts[uid] = verdict
            unit_failed = False
            if getattr(verdict, "routed_to_claude", False):
                tracker.record(uid, UnitState.INLINE, escalated=True)
                inline += 1
            elif getattr(verdict, "final_score", 0) >= accept_threshold:
                if merge_queue is not None:
                    mr = merge_queue.submit(uid)
                    if not getattr(mr, "merged", True):
                        tracker.record(uid, UnitState.FAILED, score=getattr(verdict, "final_score", 0), merge="rejected")
                        failed += 1
                        unit_failed = True
                if not unit_failed:
                    tracker.record(uid, UnitState.ACCEPTED, score=verdict.final_score, maker=getattr(verdict, "agent_used", "?"))
                    accepted += 1
                    accepted_ids.append(uid)
            else:
                tracker.record(uid, UnitState.FAILED, score=getattr(verdict, "final_score", 0))
                failed += 1
                unit_failed = True
            if unit_failed and failure_mode == "fail_fast":  # ADR-0029: stop on first failure
                aborted = True
                break
        # wave boundary: re-verify the next wave against accrued GREEN code (REQ-D9)
        if reverify is not None:
            report = reverify(by_id, list(accepted_ids))

    # DAG-atomic finalize (ADR-0004/0012, REQ-I2): ff to target only if whole DAG clean.
    # all_or_nothing / fail_fast (ADR-0029): any failure -> the whole build is discarded.
    clean = (failed == 0) and not aborted
    assembly = None
    if merge_queue is not None:
        assembly = merge_queue.finalize(assembly_ok=clean)
    elif failure_mode in ("all_or_nothing", "fail_fast"):
        assembly = "ff_to_target" if clean else "discard"

    return DagRunResult(
        waves=waves, board=tracker.board(), verify=report,
        accepted=accepted, failed=failed, inline=inline, verdicts=verdicts,
        assembly=assembly,
    )
