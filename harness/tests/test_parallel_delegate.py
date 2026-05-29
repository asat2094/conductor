import pytest
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
