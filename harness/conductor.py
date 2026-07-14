"""
Conductor top-level entrypoint (ADR-0011/0022/0023/0024). Ties the pipeline together: decompose ->
verify -> per-wave [cost_skip -> dispatch via the composed process_unit -> harness-derived tracking],
then renders a program-manager report. The orchestrator stays lean — it reads the board + result,
never the unit file bodies (ADR-0001).
"""
from typing import Any, Callable, Optional

from harness.run_dag import run_dag, DagRunResult
from harness.tracker import Tracker
from harness.unit_gate import GateSpec


def default_gate_spec_for(subtask: Any) -> GateSpec:
    """Default gate spec for a unit. Properties / held-out oracle are wired per-unit by the caller;
    the default is an empty spec (scope-guard + acceptance still run inside the gate)."""
    return GateSpec()


def build(
    briefs: list[dict],
    workdir: str = ".",
    *,
    process_unit: Optional[Callable[[Any, str], Any]] = None,
    edges: Optional[dict] = None,
) -> tuple[DagRunResult, Tracker]:
    """Run the full distributed build over `briefs`. Returns (result, tracker). Raises
    DecompositionError if the decomposition hard gate fails (nothing dispatches)."""
    tracker = Tracker()
    result = run_dag(briefs, workdir=workdir, process_unit=process_unit, tracker=tracker, edges=edges)
    return result, tracker


def build_report(result: DagRunResult, tracker: Tracker) -> str:
    """Human program-manager view: waves, rollup, verify status, and the live board."""
    lines = [
        f"waves: {result.waves}",
        f"accepted={result.accepted} failed={result.failed} inline={result.inline}",
        f"verify: {result.verify.status} dense={result.verify.dense}",
        tracker.render_text(),
    ]
    return "\n".join(lines)
