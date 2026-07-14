"""
Per-unit processor (ADR-0027 + ADR-0025/0026). Wires a maker through the bounded repair loop against
the composed mechanical unit gate, producing a run_dag-compatible verdict. The maker runs in its own
bounded context (ADR-0024); the loop's feedback is the gate's mechanical evidence only (no soft gate).

maker(subtask, workdir, feedback) -> UnitArtifact   (feedback is None on the first attempt)
gate_spec_for(subtask) -> GateSpec
"""
from dataclasses import dataclass
from typing import Any, Callable

from harness.repair_loop import repair_loop
from harness.unit_gate import evaluate_unit, GateSpec


@dataclass
class UnitVerdict:
    unit_id: str
    accepted: bool
    attempts: int
    outcome: str            # "accepted" | "stuck" | "exhausted"
    evidence: str = ""
    agent_used: str = "maker"
    # run_dag compatibility:
    final_score: int = 0
    routed_to_claude: bool = False


def make_processor(
    maker: Callable[[Any, str, Any], Any],
    gate_spec_for: Callable[[Any], GateSpec],
    *,
    max_attempts: int = 3,
    stuck_window: int = 2,
) -> Callable[[Any, str], UnitVerdict]:
    def process_unit(subtask: Any, workdir: str) -> UnitVerdict:
        spec = gate_spec_for(subtask)

        def make(feedback):
            return maker(subtask, workdir, feedback)

        def gate(artifact):
            outcome = evaluate_unit(artifact, spec)
            return (outcome.passed, outcome.evidence)

        res = repair_loop(make, gate, max_attempts=max_attempts, stuck_window=stuck_window)
        return UnitVerdict(
            unit_id=getattr(subtask, "id", "?"),
            accepted=res.accepted,
            attempts=res.attempts,
            outcome=res.outcome,
            evidence=res.last_evidence,
            final_score=100 if res.accepted else 0,
            routed_to_claude=not res.accepted,
        )

    return process_unit
