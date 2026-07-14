"""
Inconclusive-only LLM-judge tiebreak (ADR-0038 — bounded exception to Law 2).

A judge may act ONLY when the mechanical gates are *inconclusive* — no applicable
deterministic gate ran, or several candidates are mechanically indistinguishable.
It is fenced by hard invariants so it never becomes a primary accept gate:

  1. NEVER overrides a mechanical FAIL (a FAIL is terminal — calling here is a bug).
  2. Fires only when `inconclusive=True` (the caller proved no gate could decide).
  3. Author-separation: the judge model MUST differ from the impl-author, else we
     cannot judge -> escalate.
  4. Per-DAG quota: once exhausted -> escalate instead of judging (a DAG leaning on
     the judge is a decomposition smell, surfaced not hidden).

Every judge decision is meant to be logged by the caller (tracker JUDGE_TIEBREAK).
"""
from dataclasses import dataclass
from typing import Callable, Optional


class JudgeError(Exception):
    """Raised on a misuse that violates an invariant (never-override-FAIL / not-inconclusive)."""


@dataclass
class JudgeQuota:
    """Per-DAG cap on judge tiebreaks. Default small — the judge is an exception, not a path."""
    limit: int
    used: int = 0

    def exhausted(self) -> bool:
        return self.used >= self.limit

    def consume(self) -> None:
        self.used += 1


@dataclass
class TiebreakResult:
    decision: str                 # "select" | "reject" | "escalate"
    winner: Optional[str] = None  # candidate id when decision == "select"
    reason: str = ""


def tiebreak(
    *,
    candidates: list[str],
    inconclusive: bool,
    mechanical_fail: bool,
    quota: JudgeQuota,
    judge_call: Callable[[list[str]], Optional[str]],
    impl_author: str,
    judge_model: str,
) -> TiebreakResult:
    """Decide an inconclusive slice via a judge, under the ADR-0038 invariants.

    `judge_call(candidates) -> winner_id | None` is the model call: it returns the
    id it accepts, or None to reject. It is invoked ONLY after every invariant passes.
    """
    # Invariant 1: a mechanical FAIL is terminal — the judge cannot resurrect it.
    if mechanical_fail:
        raise JudgeError("judge may not override a mechanical FAIL")
    # Invariant 2: only inconclusive slices reach the judge.
    if not inconclusive:
        raise JudgeError("judge fires only when mechanical gates are inconclusive")
    if not candidates:
        raise JudgeError("no candidates to judge")

    # Invariant 3: author-separation — a model may not judge its own output.
    if judge_model == impl_author:
        return TiebreakResult("escalate", reason="author-separation: judge == impl-author")
    # Invariant 4: quota — do not lean on the judge.
    if quota.exhausted():
        return TiebreakResult("escalate", reason="judge quota exhausted")

    quota.consume()
    winner = judge_call(candidates)
    if winner is None:
        return TiebreakResult("reject", reason="judge rejected")
    if winner not in candidates:
        raise JudgeError(f"judge returned unknown candidate {winner!r}")
    return TiebreakResult("select", winner=winner, reason="judge tiebreak")
