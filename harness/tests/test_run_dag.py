from harness.run_dag import run_dag, DagRunResult
from harness.tracker import UnitState

A = {"id": "a", "goal": "produce parser", "task_type": "code_gen", "files": ["p.py"],
     "writes_files": ["p.py"], "context_slices": [], "contract": {"produces": ["parse"], "consumes": []},
     "verify_cmd": "pytest", "exit_criteria": "ok", "sensitivity": "low", "estimated_tokens": 5000}
B = {"id": "b", "goal": "use parser", "task_type": "code_edit", "files": ["m.py"],
     "writes_files": ["m.py"], "context_slices": [], "contract": {"produces": [], "consumes": ["parse"]},
     "verify_cmd": "pytest", "exit_criteria": "ok", "sensitivity": "low", "estimated_tokens": 5000}


class _FakeVerdict:
    def __init__(self, score, agent="gemma4"):
        self.final_score = score
        self.agent_used = agent
        self.routed_to_claude = False


def test_run_dag_processes_units_in_wave_order_and_tracks():
    seen = []
    def fake_process(subtask, workdir):
        seen.append(subtask.id)
        return _FakeVerdict(85)
    res = run_dag([B, A], workdir=".", process_unit=fake_process)
    assert seen == ["a", "b"]
    assert res.board["a"]["state"] == UnitState.ACCEPTED
    assert res.board["b"]["state"] == UnitState.ACCEPTED
    assert res.accepted == 2


def test_run_dag_marks_failed_below_threshold():
    def fake_process(subtask, workdir):
        return _FakeVerdict(40)
    res = run_dag([A], workdir=".", process_unit=fake_process)
    assert res.board["a"]["state"] == UnitState.FAILED
    assert res.failed == 1


def test_run_dag_cost_skips_tiny_unit_to_inline():
    tiny = {**A, "id": "t", "estimated_tokens": 100}
    called = []
    def fake_process(subtask, workdir):
        called.append(subtask.id)
        return _FakeVerdict(90)
    res = run_dag([tiny], workdir=".", process_unit=fake_process)
    assert res.board["t"]["state"] == UnitState.INLINE
    assert "t" not in called


def test_run_dag_raises_clean_on_bad_decomposition():
    import pytest
    from harness.decompose import DecompositionError
    ghost = {**B, "contract": {"produces": [], "consumes": ["nonexistent"]}}
    with pytest.raises(DecompositionError):
        run_dag([ghost], workdir=".", process_unit=lambda s, w: _FakeVerdict(90))


def test_run_dag_attaches_verify_report():
    res = run_dag([A, B], workdir=".", process_unit=lambda s, w: _FakeVerdict(90))
    assert res.verify.status == "unverified"
