from harness.merge_queue import MergeQueue, MergeResult


def test_clean_submit_merges_and_passes_suite():
    q = MergeQueue(suite_runner=lambda: (True, "50 passed"), merger=lambda u: (True, ""))
    r = q.submit("u1")
    assert isinstance(r, MergeResult)
    assert r.merged is True and r.suite_passed is True
    assert q.failed is False


def test_suite_regression_fails_submit_and_queue():
    q = MergeQueue(suite_runner=lambda: (False, "1 failed: sibling"), merger=lambda u: (True, ""))
    r = q.submit("u1")
    assert r.merged is False
    assert r.suite_passed is False
    assert q.failed is True


def test_merge_conflict_fails_submit():
    q = MergeQueue(suite_runner=lambda: (True, ""), merger=lambda u: (False, "conflict"))
    r = q.submit("u1")
    assert r.merged is False
    assert q.failed is True


def test_finalize_ff_when_all_clean_and_assembly_ok():
    q = MergeQueue(suite_runner=lambda: (True, ""), merger=lambda u: (True, ""))
    q.submit("u1"); q.submit("u2")
    assert q.finalize(assembly_ok=True) == "ff_to_target"


def test_finalize_discard_when_a_unit_failed():
    q = MergeQueue(suite_runner=lambda: (False, "x"), merger=lambda u: (True, ""))
    q.submit("u1")
    assert q.finalize(assembly_ok=True) == "discard"


def test_finalize_discard_when_assembly_fails_even_if_units_clean():
    q = MergeQueue(suite_runner=lambda: (True, ""), merger=lambda u: (True, ""))
    q.submit("u1")
    assert q.finalize(assembly_ok=False) == "discard"


# --- ADR-0041 per-wave atomic promotion ---

def test_promote_wave_ff_when_clean_and_counts_landed():
    q = MergeQueue(suite_runner=lambda: (True, ""), merger=lambda u: (True, ""))
    q.submit("u1")
    assert q.promote_wave(assembly_ok=True) == "ff_wave"
    assert q.landed_waves == 1
    q.submit("u2")
    assert q.promote_wave(assembly_ok=True) == "ff_wave"
    assert q.landed_waves == 2


def test_promote_wave_holds_on_assembly_fail_and_stays_held():
    q = MergeQueue(suite_runner=lambda: (True, ""), merger=lambda u: (True, ""))
    q.submit("u1")
    assert q.promote_wave(assembly_ok=False) == "hold"   # this wave's assembly red
    assert q.landed_waves == 0
    q.submit("u2")
    assert q.promote_wave(assembly_ok=True) == "hold"     # prefix rule: stays held
    assert q.landed_waves == 0


def test_promote_wave_holds_after_a_submit_failure():
    q = MergeQueue(suite_runner=lambda: (False, "broke"), merger=lambda u: (True, ""))
    q.submit("u1")                                        # sets _failed
    assert q.promote_wave(assembly_ok=True) == "hold"
    assert q.landed_waves == 0
