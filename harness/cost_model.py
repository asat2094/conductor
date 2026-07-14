"""
Deterministic projection of the orchestrator's PAID token cost per route (ADR-0016, REQ-R1).

inline      = orchestrator loads file bodies into its own (bloating) context ≈ estimated_tokens.
delegation  = orchestrator sees only a fixed-size brief + lean verdict; makers bear the file tokens.

So delegation pays off only above a crossover (MIN_DELEGATION_TOKENS). Below it, inline is cheaper.

CALIBRATION DEBT (design §7): these constants are conservative v1 anchors. Retune from the
run-ledger once real per-stage token accounting exists.
"""
from harness.models import SubTask

# Orchestrator tokens to author a brief + read a lean verdict for one delegated unit.
_BRIEF_OVERHEAD_TOKENS = 800

# Below this estimated size, delegation overhead is not worth it → inline.
MIN_DELEGATION_TOKENS = _BRIEF_OVERHEAD_TOKENS


def estimate_inline_cost(subtask: SubTask) -> int:
    """Paid orchestrator tokens if it does the unit inline: it loads the bodies."""
    return subtask.estimated_tokens


def estimate_delegation_orchestrator_cost(subtask: SubTask) -> int:
    """Paid orchestrator tokens if delegated: only brief + verdict, independent of file size."""
    return _BRIEF_OVERHEAD_TOKENS


def should_inline(subtask: SubTask, min_delegation_tokens: int = MIN_DELEGATION_TOKENS) -> bool:
    """True when the task is too small for delegation overhead to pay off (REQ-R1)."""
    return subtask.estimated_tokens < min_delegation_tokens
