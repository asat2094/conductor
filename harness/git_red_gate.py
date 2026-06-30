"""
git_red_gate: Mechanically prove failing-test commit precedes implementation commit.

References:
  - ADR-0030: RED-before-impl gate for TDD enforcement
  - REQ-T14: Test commit must be ancestor of (or precede) impl commit

Design:
  Pure git inspection, zero model trust. A `runner(args:list)->(rc:int,out:str)`
  is INJECTED so tests need no real git repo.

Functions:
  - introducing_commit(path, *, runner) -> str|None
  - is_ancestor(a, b, *, runner) -> bool
  - red_before_impl(test_file, impl_file, *, runner) -> (ok:bool, reason:str)
"""

import subprocess
from typing import Callable, Optional, Tuple


def introducing_commit(
    path: str,
    *,
    runner: Callable[[list], Tuple[int, str]] = None,
) -> Optional[str]:
    """
    Find the commit that first ADDED the file at `path`.

    Uses `git log --diff-filter=A --reverse --format=%H -- <path>`.
    Returns the FIRST commit hash (the one that added the file), or None if
    the file has no introducing commit.

    Args:
        path: File path to check.
        runner: Callable that executes git commands. Defaults to subprocess.run.
                Expected signature: (args: list) -> (rc: int, output: str)

    Returns:
        The commit hash (string), or None if not found or git error.
    """
    if runner is None:
        runner = _default_runner

    rc, out = runner(["log", "--diff-filter=A", "--reverse", "--format=%H", "--", path])
    if rc != 0:
        return None

    lines = out.strip().split("\n") if out.strip() else []
    if not lines:
        return None

    return lines[0] if lines[0] else None


def is_ancestor(
    a: str,
    b: str,
    *,
    runner: Callable[[list], Tuple[int, str]] = None,
) -> bool:
    """
    Check if commit `a` is an ancestor of (or equal to) commit `b`.

    Uses `git merge-base --is-ancestor a b`. Returns True if rc==0, False otherwise.

    Args:
        a: The potential ancestor commit hash.
        b: The commit to check against.
        runner: Callable that executes git commands. Defaults to subprocess.run.

    Returns:
        True if `a` is an ancestor of `b`, False otherwise.
    """
    if runner is None:
        runner = _default_runner

    rc, _ = runner(["merge-base", "--is-ancestor", a, b])
    return rc == 0


def red_before_impl(
    test_file: str,
    impl_file: str,
    *,
    runner: Callable[[list], Tuple[int, str]] = None,
) -> Tuple[bool, str]:
    """
    Mechanically prove the failing-test commit precedes the implementation commit.

    Implements the RED-before-impl gate: checks that both files have introducing
    commits, that they are different commits, and that the test commit is an
    ancestor of the implementation commit.

    This enforces TDD: tests must be added in a separate commit BEFORE the
    implementation. If both files appear in the same commit (e.g., due to squashing),
    this gate will fail.

    Args:
        test_file: Path to the test file (e.g., "test_m.py").
        impl_file: Path to the implementation file (e.g., "m.py").
        runner: Callable that executes git commands. Defaults to subprocess.run.

    Returns:
        (ok: bool, reason: str)
        - (True, "RED commit precedes impl") if test commit is ancestor of impl.
        - (False, reason_str) otherwise, explaining the failure.

    Raises:
        None (all errors are reported via the tuple return).

    References:
        - ADR-0030: RED-before-impl gate for TDD enforcement
        - REQ-T14: Requires per-unit commit cadence (test then impl as separate commits)
    """
    if runner is None:
        runner = _default_runner

    test_sha = introducing_commit(test_file, runner=runner)
    impl_sha = introducing_commit(impl_file, runner=runner)

    if test_sha is None:
        return (False, f"Missing introducing commit for {test_file}")

    if impl_sha is None:
        return (False, f"Missing introducing commit for {impl_file}")

    if test_sha == impl_sha:
        return (False, "test and impl added in same commit")

    if is_ancestor(test_sha, impl_sha, runner=runner):
        return (True, "RED commit precedes impl")

    return (False, "impl commit not after test commit")


def _default_runner(args: list) -> Tuple[int, str]:
    """Default runner using subprocess.run with git."""
    result = subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
    )
    return (result.returncode, result.stdout)
