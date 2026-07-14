"""
Git-worktree-per-maker isolation (ADR-0013). Each concurrently-dispatched maker gets its own git
worktree at a path derived from the unit id (NOT a timestamp — reproducibility, S10), plus an
env-injected unit-scoped TMPDIR. Live finding (gemma4 run): without an isolated worktree the maker's
diff is empty, so scope_guard can't see test-file rewrites, and parallel makers collide on the git
index — this module is what makes both work. All git calls go through an injected runner so the
logic is unit-testable without a real repo.
"""
import os
import re
import subprocess
from typing import Callable, Optional

Runner = Callable[[list], tuple]

_WORKTREE_SUBDIR = ".conductor-worktrees"
_SAFE = re.compile(r"[^A-Za-z0-9_-]")


def _default_runner(args: list) -> tuple:
    r = subprocess.run(["git"] + args, capture_output=True, text=True, timeout=120)
    return (r.returncode, (r.stdout or "") + (r.stderr or ""))


def sanitize_unit_id(uid: str) -> str:
    return _SAFE.sub("_", uid)


def worktree_path(base: str, unit_id: str) -> str:
    """Deterministic worktree path for a unit (id-derived, reproducible)."""
    return os.path.join(base, _WORKTREE_SUBDIR, sanitize_unit_id(unit_id))


def alloc_worktree(repo: str, unit_id: str, *, runner: Optional[Runner] = None) -> str:
    """git worktree add (detached) at the id-derived path. Returns the path. Tolerant if it exists."""
    runner = runner or _default_runner
    path = worktree_path(repo, unit_id)
    if not os.path.isdir(path):
        runner(["-C", repo, "worktree", "add", "--detach", path])
    return path


def teardown_worktree(repo: str, path: str, *, runner: Optional[Runner] = None) -> bool:
    """git worktree remove --force. Returns True on success."""
    runner = runner or _default_runner
    rc, _ = runner(["-C", repo, "worktree", "remove", "--force", path])
    return rc == 0


def inject_env(unit_id: str, base_env: Optional[dict] = None) -> dict:
    """Return a copy of base_env with a unit-scoped TMPDIR + CONDUCTOR_UNIT. Does not mutate input."""
    env = dict(base_env or {})
    env["CONDUCTOR_UNIT"] = unit_id
    env["TMPDIR"] = os.path.join("/tmp", "conductor", sanitize_unit_id(unit_id))
    return env
