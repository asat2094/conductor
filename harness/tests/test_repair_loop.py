from harness.repair_loop import repair_loop, RepairResult


def test_passes_first_attempt():
    res = repair_loop(make=lambda fb: "art", gate=lambda a: (True, ""), max_attempts=3)
    assert res.accepted is True
    assert res.attempts == 1
    assert res.outcome == "accepted"


def test_repairs_then_passes():
    calls = {"n": 0}
    def gate(a):
        calls["n"] += 1
        return (calls["n"] >= 2, f"fail-{calls['n']}")  # distinct evidence each time
    res = repair_loop(make=lambda fb: "art", gate=gate, max_attempts=3)
    assert res.accepted is True
    assert res.attempts == 2
    assert res.outcome == "accepted"


def test_stuck_detection_byte_identical_evidence():
    # same evidence twice in a row -> stuck, escalate before exhausting budget
    res = repair_loop(make=lambda fb: "art", gate=lambda a: (False, "same-error"), max_attempts=10, stuck_window=2)
    assert res.accepted is False
    assert res.outcome == "stuck"
    assert res.attempts == 2   # aborts at the 2nd identical signal, not 10


def test_exhausts_attempts_with_changing_evidence():
    n = {"i": 0}
    def gate(a):
        n["i"] += 1
        return (False, f"different-{n['i']}")  # never identical -> no stuck -> runs to ceiling
    res = repair_loop(make=lambda fb: "art", gate=gate, max_attempts=3, stuck_window=2)
    assert res.accepted is False
    assert res.outcome == "exhausted"
    assert res.attempts == 3


def test_make_receives_gate_evidence_as_feedback():
    seen = []
    def make(fb):
        seen.append(fb)
        return "art"
    n = {"i": 0}
    def gate(a):
        n["i"] += 1
        return (n["i"] >= 2, f"evidence-{n['i']}")
    repair_loop(make=make, gate=gate, max_attempts=3)
    assert seen[0] is None            # first attempt: no feedback
    assert seen[1] == "evidence-1"    # second attempt fed the mechanical gate evidence


def test_max_attempts_one_failing_is_exhausted():
    res = repair_loop(make=lambda fb: "a", gate=lambda a: (False, "err"), max_attempts=1, stuck_window=2)
    assert res.accepted is False
    assert res.attempts == 1
    assert res.outcome == "exhausted"


def test_max_attempts_one_passing_is_accepted():
    res = repair_loop(make=lambda fb: "a", gate=lambda a: (True, ""), max_attempts=1)
    assert res.accepted is True
    assert res.attempts == 1
    assert res.outcome == "accepted"


def test_stuck_window_one_aborts_on_first_failure():
    # stuck_window=1 => any single failure is 'stuck'
    res = repair_loop(make=lambda fb: "a", gate=lambda a: (False, "e"), max_attempts=5, stuck_window=1)
    assert res.outcome == "stuck"
    assert res.attempts == 1


def test_stuck_window_greater_than_max_attempts_never_sticks():
    n = {"i": 0}
    def gate(a):
        n["i"] += 1
        return (False, f"diff-{n['i']}")   # always different
    res = repair_loop(make=lambda fb: "a", gate=gate, max_attempts=2, stuck_window=5)
    assert res.outcome == "exhausted"
    assert res.attempts == 2
