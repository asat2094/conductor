from harness.strict_gates import red_gate, green_gate, author_separation_ok


def _runner_map(mapping):
    # mapping: cmd -> (rc, output)
    def r(cmd):
        return mapping[cmd]
    return r


def test_valid_red_assertion_failure_naming_symbol():
    r = _runner_map({"pytest t": (1, "E       AssertionError: parse_order not annotated")})
    ok, reason = red_gate("pytest t", "parse_order", runner=r)
    assert ok is True


def test_invalid_red_when_test_passes():
    r = _runner_map({"pytest t": (0, "1 passed")})
    ok, reason = red_gate("pytest t", "parse_order", runner=r)
    assert ok is False
    assert "did not fail" in reason.lower()


def test_invalid_red_on_import_error():
    r = _runner_map({"pytest t": (1, "E   ImportError: cannot import name 'parse_order'")})
    ok, reason = red_gate("pytest t", "parse_order", runner=r)
    assert ok is False
    assert "wrong reason" in reason.lower()


def test_invalid_red_assertion_not_naming_symbol():
    r = _runner_map({"pytest t": (1, "E   AssertionError: something unrelated")})
    ok, reason = red_gate("pytest t", "parse_order", runner=r)
    assert ok is False


def test_green_requires_both_unit_and_suite():
    r = _runner_map({"pytest u": (0, "1 passed"), "pytest all": (0, "50 passed")})
    passed, ev = green_gate("pytest u", "pytest all", runner=r)
    assert passed is True


def test_green_fails_when_suite_regresses():
    r = _runner_map({"pytest u": (0, "1 passed"), "pytest all": (1, "1 failed sibling_test")})
    passed, ev = green_gate("pytest u", "pytest all", runner=r)
    assert passed is False
    assert "suite" in ev.lower()


def test_green_fails_when_unit_fails():
    r = _runner_map({"pytest u": (1, "fail"), "pytest all": (0, "ok")})
    passed, ev = green_gate("pytest u", "pytest all", runner=r)
    assert passed is False


def test_author_separation():
    assert author_separation_ok("makerA", "makerB") is True
    assert author_separation_ok("makerA", "makerA") is False
    assert author_separation_ok("", "makerB") is False
    assert author_separation_ok("makerA", "") is False
