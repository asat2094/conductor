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
