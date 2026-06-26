from harness.unit_gate import evaluate_unit, UnitArtifact, GateSpec, GateOutcome


def _art(**kw):
    base = dict(changed_files=["m.py"], diff_text="+ def f(): return 1\n", task_type="code_edit",
                in_loop_green=True, oracle_passed=True)
    base.update(kw)
    return UnitArtifact(**base)


def test_all_gates_pass():
    out = evaluate_unit(_art(), GateSpec(properties=[lambda x: x == x], examples=[1, 2]))
    assert out.passed is True
    assert out.evidence == ""
    assert [g for g, ok in out.results] == ["scope_guard", "pbt", "acceptance"]


def test_scope_violation_short_circuits_first():
    out = evaluate_unit(_art(diff_text="+ sys.exit(0)\n"), GateSpec())
    assert out.passed is False
    assert "scope" in out.evidence.lower()
    # pbt/acceptance never reached
    assert [g for g, ok in out.results] == ["scope_guard"]


def test_pbt_counterexample_fails():
    out = evaluate_unit(_art(), GateSpec(properties=[lambda x: x * 2 == x], examples=[0, 5]))
    assert out.passed is False
    assert "counterexample" in out.evidence.lower()
    assert out.results[-1][0] == "pbt"


def test_acceptance_fails_when_in_loop_red():
    out = evaluate_unit(_art(in_loop_green=False), GateSpec())
    assert out.passed is False
    assert "acceptance" in out.evidence.lower()


def test_high_stakes_requires_oracle():
    out = evaluate_unit(_art(oracle_passed=None), GateSpec(high_stakes=True))
    assert out.passed is False   # high-stakes with no oracle result -> reject


def test_low_stakes_no_oracle_passes_on_green():
    out = evaluate_unit(_art(oracle_passed=None), GateSpec(high_stakes=False))
    assert out.passed is True
