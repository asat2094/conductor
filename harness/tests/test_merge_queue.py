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
