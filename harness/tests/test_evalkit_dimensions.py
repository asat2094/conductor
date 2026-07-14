from types import SimpleNamespace
import pytest
from harness.evalkit import dimensions as D


def _t(score=100, passed=True, latency_s=1.0, tokens_used=1000, context_tokens=1000,
       task_type="code_gen", output="x"):
    return SimpleNamespace(score=score, passed=passed, latency_s=latency_s,
                           tokens_used=tokens_used, context_tokens=context_tokens,
                           task_type=task_type, output=output)


def test_accuracy_mean():
    s = D.resolve("accuracy").compute([_t(score=80), _t(score=100)], {})
    assert s.value == 90.0 and s.normalized == 90.0


def test_reliable_context_picks_largest_passing():
    trials = [_t(score=90, context_tokens=1000), _t(score=90, context_tokens=8000),
              _t(score=40, context_tokens=32000)]
    s = D.resolve("reliable_context").compute(trials, {"pass_threshold": 70})
    assert s.value == 8000.0
    assert s.detail["max_context"] == 32000


def test_latency_normalized_against_ceiling():
    s = D.resolve("latency").compute([_t(latency_s=30.0)], {"latency_ceiling_s": 60.0})
    assert s.value == 30.0 and s.normalized == 50.0


def test_cost_per_pass_local_is_free_full_score():
    s = D.resolve("cost_per_pass").compute([_t(passed=True)], {"price_per_1k": 0.0})
    assert s.value == 0.0 and s.normalized == 100.0


def test_cost_per_pass_no_passes_is_infinite_zero_score():
    s = D.resolve("cost_per_pass").compute([_t(passed=False)], {"price_per_1k": 0.01})
    assert s.value == float("inf") and s.normalized == 0.0


def test_cost_per_pass_paid_scales_with_budget():
    # 2 trials * 1000 tok * $0.01/1k = $0.02 total, 2 passes -> $0.01/pass; budget 0.02 -> 50
    s = D.resolve("cost_per_pass").compute([_t(passed=True), _t(passed=True)],
                                           {"price_per_1k": 0.01, "cost_budget_per_pass": 0.02})
    assert s.value == 0.01 and s.normalized == 50.0


def test_refusal_rate():
    s = D.resolve("refusal_rate").compute([_t(output="x"), _t(output="  "), _t(output="")], {})
    assert s.value == pytest.approx(0.667, abs=0.01)
    assert s.normalized == pytest.approx(33.3, abs=0.5)


def test_context_degradation_flat_is_full():
    trials = [_t(score=90, context_tokens=1000), _t(score=90, context_tokens=32000)]
    s = D.resolve("context_degradation").compute(trials, {})
    assert s.value == 0.0 and s.normalized == 100.0


def test_context_degradation_measures_drop():
    trials = [_t(score=90, context_tokens=1000), _t(score=40, context_tokens=32000)]
    s = D.resolve("context_degradation").compute(trials, {})
    assert s.value == 50.0 and s.normalized == 50.0


def test_registry_unknown_raises():
    with pytest.raises(KeyError):
        D.resolve("nonexistent")


def test_register_custom_dimension():
    class Custom(D.Dimension):
        name = "custom"
        def compute(self, trials, ctx):
            return D.DimensionScore("custom", 1.0, "u", 42.0)
    D.register("custom", Custom)
    assert D.resolve("custom").compute([], {}).normalized == 42.0


def test_default_dimensions_set():
    names = [d.name for d in D.default_dimensions()]
    assert "accuracy" in names and "cost_per_pass" in names and len(names) == 6


# --- regression: review fixes ---

def test_reliable_context_per_type_not_contaminated():
    # strong code_gen (passes to 32000) + weak test_write (fails everywhere) -> ceiling = 32000,
    # NOT 0 (a pooled cross-type mean used to collapse it).
    trials = ([_t(score=90, context_tokens=c, task_type="code_gen") for c in (1000, 8000, 32000)]
              + [_t(score=10, context_tokens=c, task_type="test_write") for c in (1000, 8000, 32000)])
    s = D.resolve("reliable_context").compute(trials, {"pass_threshold": 70})
    assert s.value == 32000.0
    assert s.detail["per_task_type"] == {"code_gen": 32000, "test_write": 0}


def test_context_degradation_single_context_is_neutral_not_perfect():
    s = D.resolve("context_degradation").compute([_t(score=100, context_tokens=1000)], {})
    assert s.normalized == 50.0                      # neutral, not 100
    assert s.detail["n_contexts"] == 1


def test_cost_per_pass_free_model_zero_passes_still_full():
    # free/local model, NO passes -> still 100 (free is free), not 0
    s = D.resolve("cost_per_pass").compute([_t(passed=False)], {"price_per_1k": 0.0})
    assert s.value == 0.0 and s.normalized == 100.0
