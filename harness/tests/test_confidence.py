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


# --- persistence (ADR-0039) ---

def test_save_load_roundtrip(tmp_path):
    from harness.confidence import load_store, save_store
    db = str(tmp_path / "conf.db")
    c = ConfidenceStore()
    for _ in range(MIN_SAMPLES + 1):
        c.update("gemma4", "code_edit", passed=True, seed=0.5)
    save_store(c, db)
    c2 = load_store(db)
    assert c2.samples("gemma4", "code_edit") == c.samples("gemma4", "code_edit")
    assert c2.get("gemma4", "code_edit", seed=0.5) == c.get("gemma4", "code_edit", seed=0.5)


def test_load_missing_db_gives_cold_store(tmp_path):
    from harness.confidence import load_store
    c = load_store(str(tmp_path / "nope.db"))
    assert c.samples("x", "y") == 0                      # empty, seeds apply


# --- ADR-0040 best_of_n_policy ---

def test_policy_fans_out_on_low_confidence():
    from harness.confidence import best_of_n_policy
    c = ConfidenceStore()
    for _ in range(10):
        c.update("gemma4", "code_gen", passed=False, seed=0.9)   # cold streak -> low
    pol = best_of_n_policy(c, "gemma4", n=3, threshold=0.5)
    assert pol({"task_type": "code_gen"}) == 3


def test_policy_single_maker_when_confident():
    from harness.confidence import best_of_n_policy
    c = ConfidenceStore()
    pol = best_of_n_policy(c, "gemma4", n=3, threshold=0.5)      # cold start -> seed 0.7 >= 0.5
    assert pol({"task_type": "code_edit"}) == 1


def test_policy_fans_out_on_high_sensitivity():
    from harness.confidence import best_of_n_policy
    pol = best_of_n_policy(ConfidenceStore(), "gemma4", n=4)
    assert pol({"task_type": "code_edit", "sensitivity": "high"}) == 4
