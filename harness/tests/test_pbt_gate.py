from harness.pbt_gate import run_properties, pbt_available, PBTReport


def test_all_properties_hold_passes():
    props = [lambda x: x + 0 == x, lambda x: x * 1 == x]
    rep = run_properties(props, examples=[0, 1, -5, 99])
    assert rep.passed is True
    assert rep.counterexample is None


def test_failing_property_returns_counterexample():
    # property falsely claims x*2 == x; fails for any nonzero
    rep = run_properties([lambda x: x * 2 == x], examples=[0, 3])
    assert rep.passed is False
    assert rep.counterexample == 3   # first failing example


def test_metamorphic_roundtrip_property():
    # round-trip: decode(encode(x)) == x  (here encode=str, decode=int)
    prop = lambda x: int(str(x)) == x
    rep = run_properties([prop], examples=[0, 42, -7])
    assert rep.passed is True


def test_property_raising_is_treated_as_failure():
    rep = run_properties([lambda x: 1 / x > 0], examples=[1, 0])  # ZeroDivisionError on 0
    assert rep.passed is False
    assert rep.counterexample == 0


def test_pbt_available_reflects_hypothesis_import():
    import importlib.util
    assert pbt_available() == (importlib.util.find_spec("hypothesis") is not None)


def test_empty_props_passes_vacuously():
    rep = run_properties([], examples=[1, 2])
    assert rep.passed is True


def test_multi_property_traversal_is_property_major():
    # p0 passes everything; p1 fails on the FIRST example. property-major order means
    # p0 is fully checked first, then p1 fails on examples[0].
    p0 = lambda x: True
    p1 = lambda x: x > 100            # fails on 5 (first example)
    rep = run_properties([p0, p1], examples=[5, 200])
    assert rep.passed is False
    assert rep.counterexample == 5
    assert rep.failed_property_index == 1


def test_passing_case_sets_failed_index_none():
    rep = run_properties([lambda x: True], examples=[1, 2])
    assert rep.passed is True
    assert rep.failed_property_index is None
