from harness.orchestrator_gate import red_validate_acceptance, review_dag, orchestrator_gate


def test_all_acceptance_tests_red_passes():
    r = lambda cmd: (1, "AssertionError")
    all_red, offenders = red_validate_acceptance(["pytest a", "pytest b"], runner=r)
    assert all_red is True and offenders == []


def test_a_passing_acceptance_test_is_an_offender():
    def r(cmd):
        return (0, "passed") if cmd == "pytest b" else (1, "fail")
    all_red, offenders = red_validate_acceptance(["pytest a", "pytest b"], runner=r)
    assert all_red is False
    assert "pytest b" in offenders


def test_review_skipped_when_low_stakes():
    ok, notes = review_dag("dag", reviewer=lambda d: (False, "should not run"), high_stakes=False)
    assert ok is True


def test_review_runs_when_high_stakes():
    ok, notes = review_dag("dag", reviewer=lambda d: (True, "looks good"), high_stakes=True)
    assert ok is True and "good" in notes


def test_review_error_fails_closed():
    def boom(d):
        raise RuntimeError("x")
    ok, notes = review_dag("dag", reviewer=boom, high_stakes=True)
    assert ok is False


def test_orchestrator_gate_combines_both():
    r = lambda cmd: (1, "fail")
    ok, detail = orchestrator_gate(["pytest a"], "dag", runner=r, reviewer=lambda d: (True, "ok"), high_stakes=True)
    assert ok is True
    ok2, _ = orchestrator_gate(["pytest a"], "dag", runner=lambda c: (0, "passed"), high_stakes=False)
    assert ok2 is False
