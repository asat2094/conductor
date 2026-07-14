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
    # optional repo-native style gate (ADR-0036): a language adapter + workdir; when set, the unit's
    # changed files are run through the repo's own lint/format as a mechanical gate. None -> skipped.
    style_adapter: Any = None
    workdir: str = "."
    style_runner: Optional[Callable] = None
    # inconclusive-only judge tiebreak (ADR-0038): consulted ONLY when NO deterministic correctness
    # gate exists (no properties, no examples, no oracle, not high-stakes). judge(artifact) -> bool.
    # Fenced by harness.judge invariants (never overrides a fail; author-separation; per-DAG quota).
    judge: Optional[Callable[[Any], bool]] = None
    judge_quota: Any = None            # shared harness.judge.JudgeQuota across the DAG
    impl_author: str = "?"
    judge_model: str = "?"
    # ADR-0038 audit trail: called with (decision, reason) on EVERY judge decision so the caller
    # can emit a tracker JUDGE_TIEBREAK event. None -> no logging (unit-test convenience only).
    judge_logger: Optional[Callable[[str, str], None]] = None
    # Opt-in mechanical stages (ADR-0008 mutation / ADR-0010 characterization / ADR-0030 git-RED):
    # [(name, fn(artifact) -> (ok, evidence))], run after acceptance, before style. Each stage must
    # be deterministic — the seam exists so designed gates are production-reachable, never an LLM.
    extra_gates: list = field(default_factory=list)


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

    # correctness gate. When NO deterministic acceptance signal exists AND a judge is configured,
    # the inconclusive-only judge decides (ADR-0038); otherwise the mechanical oracle decides.
    no_correctness_signal = (
        not spec.properties and not spec.examples
        and artifact.oracle_passed is None and not spec.high_stakes
        and artifact.in_loop_green is None      # no in-loop test ran -> genuinely no gate to decide
    )
    if spec.judge is not None and no_correctness_signal:
        from harness.judge import tiebreak, JudgeQuota
        quota = spec.judge_quota if spec.judge_quota is not None else JudgeQuota(limit=1)
        r = tiebreak(
            candidates=["unit"], inconclusive=True, mechanical_fail=False, quota=quota,
            judge_call=lambda cs: "unit" if spec.judge(artifact) else None,
            impl_author=spec.impl_author, judge_model=spec.judge_model,
        )
        if spec.judge_logger is not None:   # ADR-0038: every judge decision is logged
            spec.judge_logger(r.decision, r.reason)
        accepted = (r.decision == "select")
        results.append(("judge", accepted))
        if not accepted:
            return GateOutcome(False, f"judge: {r.decision} ({r.reason})", results)
    else:
        accepted = _oracle_accept(artifact.in_loop_green, artifact.oracle_passed, spec.high_stakes)
        results.append(("acceptance", accepted))
        if not accepted:
            return GateOutcome(False, "acceptance failed (in-loop green and/or held-out oracle)", results)

    # opt-in mechanical stages (mutation / characterization / git-RED) — short-circuit like the rest
    for gate_name, gate_fn in spec.extra_gates:
        ok, evidence = gate_fn(artifact)
        results.append((gate_name, ok))
        if not ok:
            return GateOutcome(False, f"{gate_name}: {evidence}", results)

    # repo-native style gate (ADR-0036): mechanical — runs the repo's own lint/format. Degrade-clean
    # when no adapter configured or no tooling detected (status 'no-style-tooling' -> pass).
    if spec.style_adapter is not None:
        from harness.style_gate import style_gate, _default_runner
        # auto-format escape hatch (ADR-0036): formatting is mechanically reversible + not a behavior
        # change (tests still gate), so fix formatting before checking — avoids escalating a
        # functionally-correct unit purely on whitespace.
        fix = getattr(spec.style_adapter, "format_fix_cmd", lambda f: None)(artifact.changed_files)
        if fix:
            (spec.style_runner or _default_runner)(fix, spec.workdir)
        passed, evidence, status = style_gate(
            spec.style_adapter, artifact.changed_files, spec.workdir, runner=spec.style_runner
        )
        results.append(("style", passed))
        if not passed:
            return GateOutcome(False, f"style: {evidence}", results)

    return GateOutcome(True, "", results)
