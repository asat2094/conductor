from unittest.mock import MagicMock, patch

from harness.models import SubTask, TaskType, AgentType, EvalResult
from harness.orchestrate import EscalateToClaudeError
from harness.parallel_delegate import delegate_parallel


def _mock_result(score=85, agent="gemma4", details="ok"):
    r = MagicMock()
    r.score = score
    r.agent = agent
    r.details = details
    return r


def _make_subtask(sid="p1"):
    return SubTask(
        id=sid, description="add docstring",
        type=TaskType.CODE_EDIT, files=["a.py"], estimated_tokens=500,
    )


def _patch_infra(mock_orchestrate):
    """Return two patch objects for load_providers and load_profiles."""
    return (
        patch("harness.parallel_delegate.load_providers", return_value={"gemma4": MagicMock()}),
        patch("harness.parallel_delegate.load_profiles", return_value={}),
    )


def test_preserves_order(tmp_path):
    tasks = [
        {"task": "task-A", "file": "a.py"},
        {"task": "task-B", "file": "b.py"},
        {"task": "task-C", "file": "c.py"},
    ]

    def fake_orchestrate(subtask, workdir, providers, profiles, diff_mode, _busy, _busy_lock):
        r = MagicMock()
        r.score = 85
        r.agent = "gemma4"
        r.details = f"response for {subtask.description}"
        return r

    with patch("harness.parallel_delegate.orchestrate", side_effect=fake_orchestrate), \
         patch("harness.parallel_delegate.load_providers", return_value={"gemma4": MagicMock()}), \
         patch("harness.parallel_delegate.load_profiles", return_value={}):
        results = delegate_parallel(str(tmp_path), tasks)

    assert len(results) == 3
    assert results[0]["file"] == "a.py"
    assert results[1]["file"] == "b.py"
    assert results[2]["file"] == "c.py"


def test_success_flag(tmp_path):
    with patch("harness.parallel_delegate.orchestrate", return_value=_mock_result(score=85)), \
         patch("harness.parallel_delegate.load_providers", return_value={"gemma4": MagicMock()}), \
         patch("harness.parallel_delegate.load_profiles", return_value={}):
        results = delegate_parallel(str(tmp_path), [{"task": "x", "file": "a.py"}])
    assert results[0]["success"] is True


def test_failure_flag_on_low_score(tmp_path):
    with patch("harness.parallel_delegate.orchestrate", return_value=_mock_result(score=60)), \
         patch("harness.parallel_delegate.load_providers", return_value={"gemma4": MagicMock()}), \
         patch("harness.parallel_delegate.load_profiles", return_value={}):
        results = delegate_parallel(str(tmp_path), [{"task": "x", "file": "a.py"}])
    assert results[0]["success"] is False


def test_exception_captured(tmp_path):
    with patch("harness.parallel_delegate.orchestrate", side_effect=RuntimeError("ollama down")), \
         patch("harness.parallel_delegate.load_providers", return_value={"gemma4": MagicMock()}), \
         patch("harness.parallel_delegate.load_profiles", return_value={}):
        results = delegate_parallel(str(tmp_path), [{"task": "x", "file": "a.py"}])
    assert results[0]["success"] is False
    assert "ollama down" in results[0]["output"]


def test_healer_strategy_none_on_success(tmp_path):
    with patch("harness.parallel_delegate.orchestrate", return_value=_mock_result(score=85)), \
         patch("harness.parallel_delegate.load_providers", return_value={"gemma4": MagicMock()}), \
         patch("harness.parallel_delegate.load_profiles", return_value={}):
        results = delegate_parallel(str(tmp_path), [{"task": "x", "file": "a.py"}])
    assert results[0]["healer_strategy"] is None


def test_heal_succeeds(tmp_path):
    """Orchestrate itself heals — a passing score means heal succeeded."""
    healed_result = _mock_result(score=80, agent="gemma4", details="healed via strategy A (score=80)")

    with patch("harness.parallel_delegate.orchestrate", return_value=healed_result), \
         patch("harness.parallel_delegate.load_providers", return_value={"gemma4": MagicMock()}), \
         patch("harness.parallel_delegate.load_profiles", return_value={}):
        results = delegate_parallel(
            str(tmp_path),
            [{"task": "add docstring", "file": "a.py"}],
            heal=True,
            subtasks=[_make_subtask()],
        )
    assert results[0]["success"] is True


def test_heal_requires_subtasks_to_be_passed(tmp_path):
    """heal=True without subtasks: auto-builds them, orchestrate heals internally."""
    failing_result = _mock_result(score=50, agent="gemma4", details="low score")

    with patch("harness.parallel_delegate.orchestrate", return_value=failing_result), \
         patch("harness.parallel_delegate.load_providers", return_value={"gemma4": MagicMock()}), \
         patch("harness.parallel_delegate.load_profiles", return_value={}):
        results = delegate_parallel(
            str(tmp_path),
            [{"task": "x", "file": "a.py"}],
            heal=True,
            subtasks=None,
        )
    assert results[0]["success"] is False


def test_delegate_parallel_returns_score_and_agent(tmp_path):
    (tmp_path / "a.py").write_text("x=1")

    mock_result = MagicMock()
    mock_result.score = 82
    mock_result.agent = "gemini"
    mock_result.details = "ok"

    with patch("harness.parallel_delegate.orchestrate", return_value=mock_result), \
         patch("harness.parallel_delegate.load_providers", return_value={"gemini": MagicMock()}), \
         patch("harness.parallel_delegate.load_profiles", return_value={}):
        results = delegate_parallel(str(tmp_path), [{"task": "add docstring", "file": "a.py"}])

    assert results[0]["score"] == 82
    assert results[0]["agent"] == "gemini"
    assert results[0]["success"] is True


def test_delegate_parallel_marks_escalated_on_exhaustion(tmp_path):
    (tmp_path / "a.py").write_text("x=1")
    st = SubTask("t1", "task", TaskType.CODE_EDIT, ["a.py"], 100)

    with patch("harness.parallel_delegate.orchestrate", side_effect=EscalateToClaudeError(st)), \
         patch("harness.parallel_delegate.load_providers", return_value={"gemini": MagicMock()}), \
         patch("harness.parallel_delegate.load_profiles", return_value={}):
        results = delegate_parallel(str(tmp_path), [{"task": "task", "file": "a.py"}])

    assert results[0]["escalated"] is True
    assert results[0]["score"] == -1
