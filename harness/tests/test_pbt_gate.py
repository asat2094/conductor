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
