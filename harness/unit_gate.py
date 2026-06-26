"""
Composed per-unit mechanical gate (ADR-0025/0026, Law 2). Runs the built deterministic gates in
order, short-circuits on first failure, and returns mechanical evidence that feeds the repair loop
(ADR-0027). No model in the loop. Order: scope-guard (reward-hacking) -> property-based -> acceptance.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from harness.scope_guard import scan_reward_hacking
from harness.pbt_gate import run_properties
from harness.held_out_oracle import accept as _oracle_accept


@dataclass
class UnitArtifact:
    changed_files: list[str]
    diff_text: str = ""
    task_type: str = "code_edit"
    in_loop_green: bool = True
    oracle_passed: Optional[bool] = None


@dataclass
class GateSpec:
    properties: list[Callable[[Any], bool]] = field(default_factory=list)
    examples: list[Any] = field(default_factory=list)
    high_stakes: bool = False


@dataclass
class GateOutcome:
    passed: bool
    evidence: str
    results: list = field(default_factory=list)   # [(gate_name, passed)]


def evaluate_unit(artifact: UnitArtifact, spec: GateSpec) -> GateOutcome:
    results: list = []

    violations = scan_reward_hacking(artifact.changed_files, artifact.diff_text, artifact.task_type)
    results.append(("scope_guard", not violations))
    if violations:
        return GateOutcome(False, "scope: " + "; ".join(violations), results)

    pbt = run_properties(spec.properties, spec.examples)
    results.append(("pbt", pbt.passed))
    if not pbt.passed:
        return GateOutcome(False, f"pbt counterexample: {pbt.counterexample!r}", results)

    accepted = _oracle_accept(artifact.in_loop_green, artifact.oracle_passed, spec.high_stakes)
    results.append(("acceptance", accepted))
    if not accepted:
        return GateOutcome(False, "acceptance failed (in-loop green and/or held-out oracle)", results)

    return GateOutcome(True, "", results)
