from harness.process_unit import make_processor, UnitVerdict
from harness.unit_gate import UnitArtifact, GateSpec


class _Sub:
    def __init__(self, uid): self.id = uid; self.type = type("T", (), {"value": "code_edit"})()


def _good_artifact(green=True):
    return UnitArtifact(changed_files=["m.py"], diff_text="+ def f(): return 1\n",
                        task_type="code_edit", in_loop_green=green, oracle_passed=True)


def test_accepted_unit_maps_to_passing_verdict():
    maker = lambda sub, wd, fb: _good_artifact()
    proc = make_processor(maker, gate_spec_for=lambda sub: GateSpec())
    v = proc(_Sub("u1"), ".")
    assert isinstance(v, UnitVerdict)
    assert v.accepted is True
    assert v.final_score == 100
    assert v.routed_to_claude is False
    assert v.attempts == 1
    assert v.outcome == "accepted"


def test_failing_unit_escalates():
    # maker always returns a red artifact -> gate fails every attempt -> exhausted -> escalate
    maker = lambda sub, wd, fb: _good_artifact(green=False)
    proc = make_processor(maker, gate_spec_for=lambda sub: GateSpec(), max_attempts=2)
    v = proc(_Sub("u2"), ".")
    assert v.accepted is False
    assert v.final_score == 0
    assert v.routed_to_claude is True
    assert v.outcome in ("exhausted", "stuck")


def test_repairs_then_accepts():
    calls = {"n": 0}
    def maker(sub, wd, fb):
        calls["n"] += 1
        return _good_artifact(green=(calls["n"] >= 2))   # red first, green second
    proc = make_processor(maker, gate_spec_for=lambda sub: GateSpec(), max_attempts=3)
    v = proc(_Sub("u3"), ".")
    assert v.accepted is True
    assert v.attempts == 2


def test_maker_receives_feedback_after_first_fail():
    seen = []
    def maker(sub, wd, fb):
        seen.append(fb)
        return _good_artifact(green=(len(seen) >= 2))
    proc = make_processor(maker, gate_spec_for=lambda sub: GateSpec(), max_attempts=3)
    proc(_Sub("u4"), ".")
    assert seen[0] is None             # first attempt: no feedback
    assert seen[1] is not None         # second: fed the gate evidence
    assert "acceptance" in seen[1].lower()
