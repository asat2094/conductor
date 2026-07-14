from harness.confidence import ConfidenceStore, MIN_SAMPLES, FLOOR


def test_get_returns_seed_before_min_samples():
    c = ConfidenceStore()
    assert c.get("gemma4", "code_edit", seed=0.8) == 0.8   # no live data -> seed


def test_update_moves_score_toward_outcome_and_counts_samples():
    c = ConfidenceStore()
    for _ in range(MIN_SAMPLES):
        c.update("gemma4", "code_edit", passed=True, seed=0.5)
    assert c.samples("gemma4", "code_edit") == MIN_SAMPLES
    # after several passes the live score rises above the seed and is now used
    assert c.get("gemma4", "code_edit", seed=0.5) > 0.5


def test_failures_drop_score_below_floor_makes_inadmissible():
    c = ConfidenceStore()
    for _ in range(10):
        c.update("gemma4", "code_gen", passed=False, seed=0.9)
    assert c.get("gemma4", "code_gen", seed=0.9) < FLOOR
    assert c.admissible("gemma4", "code_gen", seed=0.9) is False


def test_cold_start_is_admissible():
    c = ConfidenceStore()
    assert c.admissible("newmodel", "code_edit", seed=0.9) is True   # < MIN_SAMPLES


def test_scores_are_scoped_per_task_type():
    c = ConfidenceStore()
    for _ in range(MIN_SAMPLES):
        c.update("gemma4", "code_edit", passed=True, seed=0.5)
        c.update("gemma4", "code_gen", passed=False, seed=0.5)
    assert c.get("gemma4", "code_edit", seed=0.5) > c.get("gemma4", "code_gen", seed=0.5)
