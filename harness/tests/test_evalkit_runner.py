from harness.evalkit.runner import evaluate, model_name, TrialResult
from harness.evalkit.task import default_suite, load_suite


def _spec(name=None):
    return {"backend": "ollama", "model": "gemma4:latest", **({"name": name} if name else {})}


def test_model_name_default_and_override():
    assert model_name({"backend": "ollama", "model": "gemma4:latest"}) == "ollama:gemma4:latest"
    assert model_name({"backend": "x", "model": "y", "name": "custom"}) == "custom"


def test_evaluate_runs_all_tasks_and_trials():
    suite = default_suite(context_sizes=[1000], task_types=["code_gen"])
    good = lambda spec, prompt: "def validate_input(d):\n    return 'symbol' in d\n"
    res = evaluate(_spec(), suite, caller=good, trials=3)
    assert len(res) == 3
    assert all(isinstance(r, TrialResult) for r in res)
    assert all(r.score == 100 and r.passed for r in res)


def test_evaluate_scores_bad_output_zero():
    suite = default_suite(context_sizes=[1000], task_types=["code_gen"])
    res = evaluate(_spec(), suite, caller=lambda s, p: "garbage(", trials=1)
    assert res[0].score == 0 and res[0].passed is False


def test_evaluate_generic_error_propagates_fail_loud():
    # a non-transient error is a probable bug -> propagate (not silently masked as a 0 refusal)
    import pytest
    suite = default_suite(context_sizes=[1000], task_types=["code_gen"])
    def boom(spec, prompt):
        raise RuntimeError("unexpected bug")
    with pytest.raises(RuntimeError):
        evaluate(_spec(), suite, caller=boom, trials=1)


def test_evaluate_records_latency_via_injected_clock():
    suite = default_suite(context_sizes=[1000], task_types=["code_gen"])
    ticks = iter([10.0, 12.5])
    res = evaluate(_spec(), suite, caller=lambda s, p: "def validate_input(d): return 'symbol' in d",
                   trials=1, clock=lambda: next(ticks))
    assert res[0].latency_s == 2.5


def test_evaluate_preserves_task_origin():
    suite = load_suite([{"id": "c1", "task_type": "code_gen", "prompt": "p",
                         "context_tokens": 500, "grader": {"type": "keyword", "keywords": ["foo"]}}])
    res = evaluate(_spec(), suite, caller=lambda s, p: "foo", trials=1)
    assert res[0].origin == "custom"


def test_evaluate_config_error_propagates_not_swallowed():
    # unknown-backend / programming errors must NOT be masked as refusals (would poison profiles)
    import pytest
    suite = default_suite(context_sizes=[1000], task_types=["code_gen"])
    def bad_backend(spec, prompt):
        raise ValueError("Unknown backend: 'openai_compat'")
    with pytest.raises(ValueError):
        evaluate(_spec(), suite, caller=bad_backend, trials=1)


def test_evaluate_transient_error_is_refusal():
    suite = default_suite(context_sizes=[1000], task_types=["code_gen"])
    def flaky(spec, prompt):
        raise ConnectionError("connection refused")
    res = evaluate(_spec(), suite, caller=flaky, trials=1)
    assert res[0].output == "" and res[0].score == 0    # transient -> refusal, no crash
