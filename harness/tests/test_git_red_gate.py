from harness.git_red_gate import introducing_commit, is_ancestor, red_before_impl


def _runner(mapping):
    # mapping: tuple(args) -> (rc, out)
    def r(args):
        return mapping[tuple(args)]
    return r


def test_introducing_commit_returns_first_added():
    r = _runner({("log", "--diff-filter=A", "--reverse", "--format=%H", "--", "t.py"): (0, "abc111\n")})
    assert introducing_commit("t.py", runner=r) == "abc111"


def test_introducing_commit_none_when_absent():
    r = _runner({("log", "--diff-filter=A", "--reverse", "--format=%H", "--", "x.py"): (0, "")})
    assert introducing_commit("x.py", runner=r) is None


def test_is_ancestor_true_on_rc0():
    r = _runner({("merge-base", "--is-ancestor", "a", "b"): (0, "")})
    assert is_ancestor("a", "b", runner=r) is True
    r2 = _runner({("merge-base", "--is-ancestor", "a", "b"): (1, "")})
    assert is_ancestor("a", "b", runner=r2) is False


def test_red_before_impl_ok_when_test_commit_is_ancestor():
    m = {
        ("log", "--diff-filter=A", "--reverse", "--format=%H", "--", "test_m.py"): (0, "TESTSHA\n"),
        ("log", "--diff-filter=A", "--reverse", "--format=%H", "--", "m.py"): (0, "IMPLSHA\n"),
        ("merge-base", "--is-ancestor", "TESTSHA", "IMPLSHA"): (0, ""),
    }
    ok, reason = red_before_impl("test_m.py", "m.py", runner=_runner(m))
    assert ok is True


def test_red_before_impl_fails_when_same_commit():
    m = {
        ("log", "--diff-filter=A", "--reverse", "--format=%H", "--", "test_m.py"): (0, "SAME\n"),
        ("log", "--diff-filter=A", "--reverse", "--format=%H", "--", "m.py"): (0, "SAME\n"),
    }
    ok, reason = red_before_impl("test_m.py", "m.py", runner=_runner(m))
    assert ok is False
    assert "same commit" in reason.lower()


def test_red_before_impl_fails_when_test_missing():
    m = {
        ("log", "--diff-filter=A", "--reverse", "--format=%H", "--", "test_m.py"): (0, ""),
        ("log", "--diff-filter=A", "--reverse", "--format=%H", "--", "m.py"): (0, "IMPLSHA\n"),
    }
    ok, reason = red_before_impl("test_m.py", "m.py", runner=_runner(m))
    assert ok is False
