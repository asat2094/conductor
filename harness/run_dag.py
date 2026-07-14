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
    assembly: Optional[str] = None   # disposition: "ff_to_target" | "partial" | "discard" | None
    landed_waves: int = 0            # ADR-0041: waves fast-forwarded to target (per-wave mode)
    held_waves: int = 0              # ADR-0041: waves held (first failure + successors)


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
    atomicity: str = "wave",
    best_of_n: Optional[Callable[[dict], int]] = None,
    confidence: Optional[Any] = None,
) -> DagRunResult:
    """Decompose -> verify -> per-wave [cost_skip -> dispatch -> track]. Optional integration:
    `merge_queue` (ADR-0004/0012): each ACCEPTED unit submitted; finalize() decides ff/discard.
    `reverify(by_id_briefs, accepted_so_far) -> VerifyReport` (REQ-D9): re-run at each wave boundary.
    `failure_mode` (ADR-0029, REQ-I5): 'continue_on_error' (default) | 'fail_fast' (abort remaining
    waves on first failure) | 'all_or_nothing' (any failure -> discard the build at finalize).
    `resume_from` (ADR-0028): a checkpoint dict; units already ACCEPTED are skipped (not re-dispatched).
    `atomicity` (ADR-0041): 'wave' (default) — each fully-GREEN wave fast-forwards to target as it
    completes; the first failing wave + successors are HELD (dependency-closed GREEN prefix). 'dag' —
    whole-DAG ff-or-discard at finalize (strict opt-in). Only affects the merge_queue path; without a
    merge_queue nothing physically lands and disposition follows failure_mode as before.
    Backward-compat: with a merge_queue, a fully-clean build yields 'ff_to_target' under either mode.
    `best_of_n` (ADR-0040): `best_of_n(brief) -> int` — spawn up to N maker candidates for a unit; the
    MECHANICAL gate selects the FIRST candidate clearing accept_threshold (no vote/debate). None -> N=1
    (current behavior). Caller sizes N from confidence (ADR-0039) / stakes / cost ceiling (ADR-0034).
    `confidence` (ADR-0039): a ConfidenceStore; each unit's gate outcome updates the maker's live
    per-task-type score, feeding future routing. None -> no live feedback (offline profiles only)."""
    process_unit = process_unit or _default_process_unit
    tracker = tracker or Tracker()
    resumed = set((resume_from or {}).get("accepted", []))

    waves = decompose(briefs)
    report = verify_decomposition(briefs, edges=edges)
    by_id = {b["id"]: b for b in briefs}

    accepted = failed = inline = 0
    landed_waves = held_waves = 0
    accepted_ids: list[str] = []
    verdicts: dict[str, Any] = {}
    aborted = False
    for wave in waves:
        if aborted:
            break
        wave_failed = False
        wave_submits = 0          # ADR-0041: units actually merged this wave (resumed/inline don't count)
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
            n = max(1, int(best_of_n(brief))) if best_of_n is not None else 1
            tracker.record(uid, UnitState.DISPATCHED, candidates=n)
            task_type = brief.get("task_type", "code_edit")
            # best-of-N (ADR-0040): the gate selects the first candidate that clears the threshold;
            # candidates never vote. N=1 is the ordinary single-maker path.
            verdict = None
            tried = 0
            for _ in range(n):
                tried += 1
                verdict = process_unit(st, workdir)
                escalated = getattr(verdict, "routed_to_claude", False)
                cand_pass = (not escalated) and getattr(verdict, "final_score", 0) >= accept_threshold
                # ADR-0039: record EACH candidate's gate outcome against its own maker — best-of-N may
                # span providers, so a per-candidate update keeps every model's live score honest.
                if confidence is not None and not escalated:
                    confidence.update(getattr(verdict, "agent_used", "?"), task_type, cand_pass)
                if cand_pass:
                    break
            verdicts[uid] = verdict
            unit_failed = False
            if getattr(verdict, "routed_to_claude", False):
                tracker.record(uid, UnitState.INLINE, escalated=True)
                inline += 1
            elif getattr(verdict, "final_score", 0) >= accept_threshold:
                if merge_queue is not None:
                    wave_submits += 1
                    mr = merge_queue.submit(uid)
                    if not getattr(mr, "merged", True):
                        tracker.record(uid, UnitState.FAILED, score=getattr(verdict, "final_score", 0), merge="rejected")
                        failed += 1
                        unit_failed = True
                if not unit_failed:
                    tracker.record(uid, UnitState.ACCEPTED, score=verdict.final_score, maker=getattr(verdict, "agent_used", "?"), candidates=tried)
                    accepted += 1
                    accepted_ids.append(uid)
            else:
                tracker.record(uid, UnitState.FAILED, score=getattr(verdict, "final_score", 0))
                failed += 1
                unit_failed = True
            wave_failed = wave_failed or unit_failed
            if unit_failed and failure_mode == "fail_fast":  # ADR-0029: stop on first failure
                aborted = True
                break
        # wave boundary: re-verify the next wave against accrued GREEN code (REQ-D9)
        if reverify is not None:
            report = reverify(by_id, list(accepted_ids))
        # ADR-0041 per-wave atomic promotion: land the wave only if fully GREEN. Only waves that had a
        # real failure OR a real merge submission are promoted/held — a resumed-only or inline-only
        # wave merged nothing, so it neither lands nor holds (fixes overstated disposition). The queue's
        # prefix rule holds this + all successor waves once any wave fails.
        if merge_queue is not None and atomicity == "wave" and (wave_failed or wave_submits > 0):
            if merge_queue.promote_wave(assembly_ok=not wave_failed) == "ff_wave":
                landed_waves += 1
            else:
                held_waves += 1

    # DAG-atomic finalize (ADR-0004/0012, REQ-I2): ff to target only if whole DAG clean.
    # all_or_nothing / fail_fast (ADR-0029): any failure -> the whole build is discarded.
    clean = (failed == 0) and not aborted
    assembly = None
    if merge_queue is not None:
        if atomicity == "wave":
            # No wave held -> clean build -> ff. A held prefix with some landed -> partial; none -> discard.
            # Keyed on held_waves (not len(waves)) so no-merge waves don't skew the disposition.
            if held_waves == 0:
                assembly = "ff_to_target"
            elif landed_waves > 0:
                assembly = "partial"
            else:
                assembly = "discard"
        else:  # atomicity == "dag": strict whole-or-nothing (ADR-0012)
            assembly = merge_queue.finalize(assembly_ok=clean)
    elif failure_mode in ("all_or_nothing", "fail_fast"):
        assembly = "ff_to_target" if clean else "discard"

    return DagRunResult(
        waves=waves, board=tracker.board(), verify=report,
        accepted=accepted, failed=failed, inline=inline, verdicts=verdicts,
        assembly=assembly, landed_waves=landed_waves, held_waves=held_waves,
    )
