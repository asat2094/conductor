from harness.models import SubTask, TaskType
from harness.cost_model import (
    estimate_inline_cost,
    estimate_delegation_orchestrator_cost,
    should_inline,
    MIN_DELEGATION_TOKENS,
)


def _st(tokens: int) -> SubTask:
    return SubTask(id="t", description="d", type=TaskType.CODE_EDIT, files=["a.py"], estimated_tokens=tokens)


def test_inline_cost_is_the_context_load():
    assert estimate_inline_cost(_st(5000)) == 5000


def test_delegation_orchestrator_cost_is_fixed_overhead_not_bodies():
    cheap = estimate_delegation_orchestrator_cost(_st(5000))
    big = estimate_delegation_orchestrator_cost(_st(50000))
    assert cheap == big  # orchestrator never sees the bodies, so cost is independent of file size


def test_small_task_should_inline():
    assert should_inline(_st(MIN_DELEGATION_TOKENS - 1)) is True


def test_large_task_should_not_inline():
    assert should_inline(_st(MIN_DELEGATION_TOKENS + 10_000)) is False
