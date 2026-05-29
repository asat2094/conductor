from harness.models import SubTask, TaskType, AgentType, EvalResult
from harness.parallel_delegate import delegate_parallel


def test_preserves_order(tmp_path, monkeypatch):
    calls = []

    def fake_run(workdir, task, files, diff_mode=False):
        calls.append(task)
        return (f"response for {task}", "code block")

    monkeypatch.setattr("harness.parallel_delegate._gemma4_run", fake_run)

    tasks = [
        {"task": "task-A", "file": "a.py"},
        {"task": "task-B", "file": "b.py"},
        {"task": "task-C", "file": "c.py"},
    ]
    results = delegate_parallel(str(tmp_path), tasks)

    assert len(results) == 3
    assert results[0]["file"] == "a.py"
    assert results[1]["file"] == "b.py"
    assert results[2]["file"] == "c.py"


def test_success_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "harness.parallel_delegate._gemma4_run",
        lambda w, t, f, diff_mode=False: ("resp", "code"),
    )
    results = delegate_parallel(str(tmp_path), [{"task": "x", "file": "a.py"}])
    assert results[0]["success"] is True


def test_failure_flag_on_no_code(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "harness.parallel_delegate._gemma4_run",
        lambda w, t, f, diff_mode=False: ("resp", None),
    )
    results = delegate_parallel(str(tmp_path), [{"task": "x", "file": "a.py"}])
    assert results[0]["success"] is False


def test_exception_captured(tmp_path, monkeypatch):
    def boom(w, t, f, diff_mode=False):
        raise RuntimeError("ollama down")

    monkeypatch.setattr("harness.parallel_delegate._gemma4_run", boom)
    results = delegate_parallel(str(tmp_path), [{"task": "x", "file": "a.py"}])
    assert results[0]["success"] is False
    assert "ollama down" in results[0]["output"]


def test_healer_strategy_none_on_success(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "harness.parallel_delegate._gemma4_run",
        lambda w, t, f, diff_mode=False: ("resp", "code"),
    )
    results = delegate_parallel(str(tmp_path), [{"task": "x", "file": "a.py"}])
    assert results[0]["healer_strategy"] is None


def _make_subtask():
    return SubTask(
        id="p1", description="add docstring",
        type=TaskType.CODE_EDIT, files=["a.py"], estimated_tokens=500,
    )


def test_heal_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "harness.parallel_delegate._gemma4_run",
        lambda w, t, f, diff_mode=False: ("resp", None),  # always fails
    )

    def fake_auto_heal(subtask, result, profiles, workdir, **kw):
        healed = EvalResult(
            subtask_id=subtask.id, agent=AgentType.GEMMA4, score=80,
            syntax_score=25, test_score=35, scope_score=20, semantic_score=0,
            details="healed",
        )
        return healed, "A"

    monkeypatch.setattr("harness.parallel_delegate.auto_heal", fake_auto_heal, raising=False)

    # Need to patch _try_heal directly since auto_heal import is inside function
    from harness import parallel_delegate as pd_mod

    def fake_try_heal(task, subtask, base, workdir, diff_mode=False):
        base["success"] = True
        base["healer_strategy"] = "A"
        base["output"] = "healed via strategy A (score=80)"
        return base

    monkeypatch.setattr(pd_mod, "_try_heal", fake_try_heal)

    results = delegate_parallel(
        str(tmp_path),
        [{"task": "add docstring", "file": "a.py"}],
        heal=True,
        subtasks=[_make_subtask()],
    )
    assert results[0]["success"] is True
    assert results[0]["healer_strategy"] == "A"


def test_heal_requires_subtasks_to_be_passed(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "harness.parallel_delegate._gemma4_run",
        lambda w, t, f, diff_mode=False: ("resp", None),
    )
    # heal=True but no subtasks → success stays False, no crash
    results = delegate_parallel(
        str(tmp_path),
        [{"task": "x", "file": "a.py"}],
        heal=True,
        subtasks=None,
    )
    assert results[0]["success"] is False
