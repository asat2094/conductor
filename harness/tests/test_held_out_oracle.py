from harness.held_out_oracle import strip_oracle_from_context, run_oracle, accept


def test_strip_removes_oracle_paths_from_visible_files():
    visible = strip_oracle_from_context(["m.py", "tests/test_m.py", "tests/oracle_m.py"], oracle_paths=["tests/oracle_m.py"])
    assert "tests/oracle_m.py" not in visible
    assert "m.py" in visible and "tests/test_m.py" in visible


def test_run_oracle_uses_injected_runner():
    rep = run_oracle("pytest tests/oracle_m.py", runner=lambda cmd: True)
    assert rep is True
    rep2 = run_oracle("pytest tests/oracle_m.py", runner=lambda cmd: False)
    assert rep2 is False


def test_accept_requires_both_green_and_oracle():
    assert accept(in_loop_green=True, oracle_passed=True, high_stakes=False) is True
    assert accept(in_loop_green=True, oracle_passed=False, high_stakes=False) is False
    assert accept(in_loop_green=False, oracle_passed=True, high_stakes=False) is False


def test_accept_high_stakes_requires_oracle_present():
    # high-stakes with no oracle result (None) must NOT accept
    assert accept(in_loop_green=True, oracle_passed=None, high_stakes=True) is False


def test_accept_low_stakes_allows_missing_oracle():
    # low-stakes: oracle optional; missing (None) falls back to in-loop green
    assert accept(in_loop_green=True, oracle_passed=None, high_stakes=False) is True


def test_strip_normalizes_paths_before_comparing():
    # oracle declared as 'tests/oracle_m.py' must still be stripped when visible list uses './tests/oracle_m.py'
    visible = strip_oracle_from_context(["m.py", "./tests/oracle_m.py", "tests/./oracle_m.py"], oracle_paths=["tests/oracle_m.py"])
    assert all("oracle_m.py" not in f for f in visible)
    assert "m.py" in visible
