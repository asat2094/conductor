from harness.characterization_gate import capture_golden, diff_golden, characterization_ok


def test_capture_runs_each_symbol_over_inputs():
    cap = lambda sym, inp: inp * 2
    g = capture_golden(["double"], [1, 2, 3], capture=cap)
    assert g == {"double": [2, 4, 6]}


def test_capture_records_exceptions_as_strings():
    def cap(sym, inp):
        if inp == 0:
            raise ValueError("boom")
        return 10 // inp
    g = capture_golden(["inv"], [2, 0], capture=cap)
    assert g["inv"][0] == 5
    assert g["inv"][1].startswith("ERROR:")


def test_diff_detects_behavior_drift():
    before = {"f": [1, 2, 3]}
    after = {"f": [1, 2, 99]}        # behavior changed
    assert diff_golden(before, after) == ["f"]


def test_no_drift_when_identical():
    g = {"f": [1, 2, 3]}
    assert diff_golden(g, dict(g)) == []


def test_characterization_ok_passes_when_preserved():
    g = {"f": [1, 2]}
    passed, ev = characterization_ok(g, dict(g))
    assert passed is True


def test_characterization_ok_fails_on_drift():
    passed, ev = characterization_ok({"f": [1]}, {"f": [2]})
    assert passed is False
    assert "f" in ev
