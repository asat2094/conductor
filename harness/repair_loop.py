"""
Bounded per-unit repair loop (ADR-0027, REQ-H1/H2/H3). generate -> gate -> repair, with strictly
MECHANICAL stop conditions: gate pass | stuck (gate evidence byte-identical across stuck_window
attempts) | attempt ceiling. NO soft/model gate ever — a fuzzy goal that can't pass a mechanical
gate escalates, it does not get a 'model says good enough' exit. Feedback to make() is the gate's
mechanical evidence only.

make(feedback: Optional[str]) -> artifact   # feedback is None on the first attempt
gate(artifact) -> (passed: bool, evidence: str)
"""
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class RepairResult:
    accepted: bool
    attempts: int
    outcome: str          # "accepted" | "stuck" | "exhausted"
    last_evidence: str = ""


def repair_loop(
    make: Callable[[Optional[str]], Any],
    gate: Callable[[Any], tuple[bool, str]],
    max_attempts: int = 3,
    stuck_window: int = 2,
) -> RepairResult:
    feedback: Optional[str] = None
    recent: list[str] = []
    attempts = 0
    while attempts < max_attempts:
        attempts += 1
        artifact = make(feedback)
        passed, evidence = gate(artifact)
        if passed:
            return RepairResult(accepted=True, attempts=attempts, outcome="accepted", last_evidence=evidence)
        recent.append(evidence)
        # stuck: last `stuck_window` evidences identical -> escalate now, don't burn budget
        if len(recent) >= stuck_window and len(set(recent[-stuck_window:])) == 1:
            return RepairResult(accepted=False, attempts=attempts, outcome="stuck", last_evidence=evidence)
        feedback = evidence
    return RepairResult(accepted=False, attempts=attempts, outcome="exhausted", last_evidence=recent[-1] if recent else "")
