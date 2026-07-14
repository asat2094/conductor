"""
Mechanical TDD gates: true-RED / GREEN / author-separation.

ADR references:
  ADR-0007 — Author-separation gate: test and implementation must have different authors.
  ADR-0008 — GREEN gate: unit test AND full suite must both pass before a task is accepted.
  ADR-0009 — RED gate: a valid RED requires an AssertionError referencing the target
              symbol, NOT an import/collection/syntax error.

No model is invoked here; all decisions are purely mechanical (string matching + return
codes).  A test-runner is injected via the `runner` keyword argument so callers remain
in full control of execution and tests need no live pytest process.
"""

from __future__ import annotations

# Markers whose presence in a failing test output means the RED is for the wrong reason.
# Checked case-insensitively.
_WRONG_RED: tuple[str, ...] = (
    "ImportError",
    "ModuleNotFoundError",
    "SyntaxError",
    "CollectionError",
    "fixture",
    "no tests ran",
)


def red_gate(
    test_cmd: str,
    target_symbol: str,
    *,
    runner,
) -> tuple[bool, str]:
    """Return (is_valid_red, reason).

    A VALID red requires:
    - The test command exits with a non-zero return code (test failed).
    - The output contains "AssertionError" and mentions *target_symbol*.
    - None of the _WRONG_RED markers appear in the output.

    ADR-0009.
    """
    rc, output = runner(test_cmd)

    if rc == 0:
        return False, "test did not fail"

    # rc != 0 — check why it failed
    output_lower = output.lower()
    for marker in _WRONG_RED:
        if marker.lower() in output_lower:
            return False, f"RED for wrong reason: {marker}"

    if "AssertionError" in output and target_symbol in output:
        return True, "valid RED"

    return False, "assertion does not reference target / not an assertion failure"


def green_gate(
    unit_test_cmd: str,
    full_suite_cmd: str,
    *,
    runner,
) -> tuple[bool, str]:
    """Return (passed, evidence).

    Passes ONLY when BOTH the unit test command AND the full suite command exit 0.
    On any failure the evidence names which command failed and includes up to 120 chars
    of its output.

    ADR-0008.
    """
    unit_rc, unit_out = runner(unit_test_cmd)
    if unit_rc != 0:
        return False, f"unit test failed: {unit_out[:120]}"

    suite_rc, suite_out = runner(full_suite_cmd)
    if suite_rc != 0:
        return False, f"full suite regressed: {suite_out[:120]}"

    return True, "green"


def author_separation_ok(test_author: str, impl_author: str) -> bool:
    """Return True iff both authors are non-empty and distinct.

    ADR-0007.
    """
    return bool(test_author) and bool(impl_author) and test_author != impl_author
