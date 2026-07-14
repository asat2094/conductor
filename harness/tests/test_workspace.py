from harness.workspace import worktree_path, alloc_worktree, teardown_worktree, inject_env, sanitize_unit_id


def test_path_is_deterministic_from_id():
    a = worktree_path("/repo", "unit-1")
    b = worktree_path("/repo", "unit-1")
    assert a == b
    assert "unit-1" in a and a.startswith("/repo")


def test_sanitize_unit_id():
    assert sanitize_unit_id("a/b c:d") == "a_b_c_d"


def test_alloc_runs_git_worktree_add():
    calls = []
    def runner(args):
        calls.append(args)
        return (0, "")
    p = alloc_worktree("/repo", "u1", runner=runner)
    assert "worktree" in calls[0] and "add" in calls[0]
    assert p == worktree_path("/repo", "u1")


def test_teardown_runs_git_worktree_remove():
    seen = {}
    def runner(args):
        seen["args"] = args
        return (0, "")
    ok = teardown_worktree("/repo", "/repo/.conductor-worktrees/u1", runner=runner)
    assert ok is True
    assert "remove" in seen["args"]


def test_inject_env_is_pure_and_scopes_tmpdir():
    base = {"PATH": "/usr/bin"}
    env = inject_env("u1", base)
    assert env["PATH"] == "/usr/bin"
    assert env["CONDUCTOR_UNIT"] == "u1"
    assert "u1" in env["TMPDIR"]
    assert "TMPDIR" not in base
