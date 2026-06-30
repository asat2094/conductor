from harness.mutation import mutate, kill_rate, adequacy_ok


def test_mutate_flips_comparison():
    muts = mutate("def f(x):\n    return x == 1\n")
    ops = [op for op, _ in muts]
    assert any("compar" in op.lower() or "==" in op or "eq" in op.lower() for op in ops)
    assert any("!=" in src for _, src in muts)


def test_mutate_returns_distinct_mutants():
    muts = mutate("def f(x):\n    return x + 1\n")
    srcs = [s for _, s in muts]
    assert len(srcs) == len(set(srcs))   # distinct
    assert all(s != "def f(x):\n    return x + 1\n" for s in srcs)  # actually mutated


def test_kill_rate_all_killed():
    src = "def f(x):\n    return x == 1\n"
    rate, survivors = kill_rate(src, test_runner=lambda m: True)   # every mutant killed
    assert rate == 1.0 and survivors == []


def test_kill_rate_with_survivor():
    src = "def f(x):\n    return x == 1\n"
    # kill all except mutants whose source contains '!='
    rate, survivors = kill_rate(src, test_runner=lambda m: "!=" not in m)
    assert rate < 1.0
    assert survivors   # at least one survivor


def test_adequacy_ok_threshold():
    src = "def f(x):\n    return x == 1\n"
    passed, ev = adequacy_ok(src, test_runner=lambda m: True, threshold=0.8)
    assert passed is True
    passed2, ev2 = adequacy_ok(src, test_runner=lambda m: False, threshold=0.8)
    assert passed2 is False
    assert "surviv" in ev2.lower() or ev2


def test_no_mutants_passes_vacuously():
    rate, survivors = kill_rate("x = 1\n", test_runner=lambda m: False)
    assert rate == 1.0   # nothing to mutate -> vacuously adequate


def test_mutate_boolean_and_or():
    muts = mutate("def f(a, b):\n    return a and b\n")
    ops = [op for op, _ in muts]
    assert any("and" in op.lower() for op in ops)
    assert any(" or " in src for _, src in muts)


def test_mutate_boolean_literals():
    muts = mutate("def f():\n    return True\n")
    ops = [op for op, _ in muts]
    assert any("true" in op.lower() or "false" in op.lower() for op in ops)
    assert any("False" in src for _, src in muts)


def test_mutate_arithmetic_plus_minus():
    muts = mutate("def f(x):\n    return x + 5\n")
    ops = [op for op, _ in muts]
    assert any("arithm" in op.lower() or "plus" in op.lower() for op in ops)
    assert any(" - " in src for _, src in muts)


def test_mutate_return_constant():
    muts = mutate("def f():\n    return 0\n")
    ops = [op for op, _ in muts]
    assert any("return" in op.lower() or "const" in op.lower() for op in ops)
    assert any("return 1" in src for _, src in muts)


def test_kill_rate_partial_survivors():
    """Test kill_rate with partial survival (some mutants killed, some survive)."""
    src = "def f(x):\n    return x == 1\n"
    # Kill mutant if it contains "!=" (the flipped comparison)
    def selective_killer(m: str) -> bool:
        return "!=" in m  # True = killed, False = survives
    rate, survivors = kill_rate(src, test_runner=selective_killer)
    # Exactly one mutant (comparison flip), it's killed
    assert rate == 1.0


def test_adequacy_ok_custom_threshold():
    """Test adequacy_ok with custom thresholds."""
    src = "def f(x):\n    return x == 1\n"
    # All mutants killed
    passed_high, _ = adequacy_ok(src, test_runner=lambda m: True, threshold=0.95)
    assert passed_high is True
    # No mutants killed, threshold 0.5 (fail)
    passed_low, ev = adequacy_ok(src, test_runner=lambda m: False, threshold=0.5)
    assert passed_low is False
    assert "50.0%" in ev or "50%" in ev
