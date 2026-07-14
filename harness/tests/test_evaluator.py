from pathlib import Path
from harness.models import SubTask, TaskType, AgentType
from harness.evaluator import (
    check_syntax,
    check_scope,
    estimate_semantic,
    evaluate,
)


def test_syntax_valid_python(tmp_path):
    f = tmp_path / "ok.py"
    f.write_text("def foo():\n    return 1\n")
    assert check_syntax([str(f)]) == 25


def test_syntax_invalid_python(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text("def foo(\n")
    assert check_syntax([str(f)]) == 0


def test_syntax_skips_non_python(tmp_path):
    f = tmp_path / "data.json"
    f.write_text('{"key": 1}')
    assert check_syntax([str(f)]) == 25


def test_scope_exact_match():
    assert check_scope(["a.py", "b.py"], ["a.py", "b.py"]) == 20


def test_scope_minor_overshoot():
    assert check_scope(["a.py", "b.py", "c.py"], ["a.py", "b.py"]) == 10


def test_scope_major_overshoot():
    assert check_scope(["a.py", "b.py", "c.py", "d.py"], ["a.py"]) == 0


def test_semantic_high_overlap():
    score = estimate_semantic("fix RSI calculation indicator", "fix RSI calculation")
    assert score >= 15


def test_semantic_low_overlap():
    score = estimate_semantic("unrelated output about weather", "fix RSI calculation")
    assert score <= 8


def test_evaluate_perfect_score(tmp_path):
    f = tmp_path / "ok.py"
    f.write_text("def foo():\n    return 1\n")
    subtask = SubTask(
        id="t1", description="fix foo function",
        type=TaskType.CODE_EDIT, files=[str(f)], estimated_tokens=100,
    )
    result = evaluate(subtask, AgentType.GEMMA4, [str(f)], "fix foo function done")
    # syntax=25, scope=20, semantic>=15, test=20 (no tests ran)
    assert result.score >= 70


def test_run_tests_delegates_to_adapter_for_unknown_language():
    # ADR-0035: a test-looking file with no adapter runner gets partial credit, not a pytest shell-out
    from harness.evaluator import _run_tests
    assert _run_tests(["test_thing.zig"]) == 20  # generic adapter -> no cmd -> 20, no crash
