import pytest
from harness.conductor import build, build_report, default_gate_spec_for
from harness.unit_gate import GateSpec

A = {"id": "a", "goal": "produce parser", "task_type": "code_gen", "files": ["p.py"],
     "writes_files": ["p.py"], "context_slices": [], "contract": {"produces": ["parse"], "consumes": []},
     "verify_cmd": "pytest", "exit_criteria": "ok", "sensitivity": "low", "estimated_tokens": 5000}
B = {"id": "b", "goal": "use parser", "task_type": "code_edit", "files": ["m.py"],
     "writes_files": ["m.py"], "context_slices": [], "contract": {"produces": [], "consumes": ["parse"]},
     "verify_cmd": "pytest", "exit_criteria": "ok", "sensitivity": "low", "estimated_tokens": 5000}


class _V:
    def __init__(self, score): self.final_score = score; self.agent_used = "maker"; self.routed_to_claude = False


def test_build_runs_dag_and_returns_result_and_tracker():
    result, tracker = build([B, A], process_unit=lambda st, wd: _V(90))
    assert result.waves == [["a"], ["b"]]
    assert result.accepted == 2
    assert tracker is not None


def test_build_report_is_human_readable_string():
    result, tracker = build([A], process_unit=lambda st, wd: _V(88))
    rep = build_report(result, tracker)
    assert isinstance(rep, str)
    assert "accepted" in rep.lower()
    assert "a" in rep


def test_build_propagates_decomposition_error():
    from harness.decompose import DecompositionError
    ghost = {**B, "contract": {"produces": [], "consumes": ["nonexistent"]}}
    with pytest.raises(DecompositionError):
        build([ghost], process_unit=lambda st, wd: _V(90))


def test_default_gate_spec_for_returns_gatespec():
    spec = default_gate_spec_for(object())
    assert isinstance(spec, GateSpec)
