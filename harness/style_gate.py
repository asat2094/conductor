"""
Repo-native style/standards gate — ADR-0036.

The gate runs the repo's own lint + format-check commands (resolved via the
language adapter, ADR-0035) against the unit's changed files. A lint/format
failure is a mechanical gate failure → feeds the repair loop (the maker is
re-prompted with the lint output as feedback, like any other gate evidence).

Degrade-clean: a repo with no detected lint/format tooling → the style gate is
skipped (status `no-style-tooling`), not failed — conductor doesn't invent
standards a repo doesn't have.

Law-2 (mechanical-first): style compliance is a mechanical gate.
Law-1 (no-trust-maker-self-report): evidence is tool output, not a maker claim.
"""

import subprocess
from typing import Callable, Optional


def _default_runner(cmd: str, workdir: str) -> tuple:
    r = subprocess.run(cmd, shell=True, cwd=workdir, capture_output=True, text=True, timeout=120)
    return (r.returncode, (r.stdout or "") + (r.stderr or ""))


def _tool_absent(rc: int, output: str) -> bool:
    """A tool that isn't installed (rc 127 / 'command not found' / 'No such file') is treated as
    absent tooling for that check — skip it, don't fail (ADR-0036: don't fail on standards a machine
    can't run)."""
    low = output.lower()
    return rc == 127 or "command not found" in low or "no such file" in low or "not found" in low


def style_gate(
    adapter,
    files: list,
    workdir: str,
    *,
    runner: Callable[[str, str], tuple] = None,
) -> tuple[bool, str, str]:
    """
    Run repo-native lint + format-check gates on the given files.

    Args:
        adapter: LanguageAdapter providing lint_cmd() and format_check_cmd().
        files: List of file paths to check.
        workdir: Working directory for running commands.
        runner: Callable(cmd, workdir) -> (returncode, output). Injectable for tests.

    Returns:
        (passed: bool, evidence: str, status: str)
        - passed=True, evidence="", status="no-style-tooling" if no tooling detected.
        - passed=True, evidence="", status="checked" if all checks pass.
        - passed=False, evidence="<failure output>", status="checked" if any check fails.
    """
    runner = runner or _default_runner

    # Resolve lint and format-check commands from the adapter.
    lint_cmd = adapter.lint_cmd(files)
    fmt_cmd = adapter.format_check_cmd(files)

    # Degrade-clean: no tooling configured -> skip (not fail).
    if lint_cmd is None and fmt_cmd is None:
        return (True, "", "no-style-tooling")

    ran_any = False
    for cmd in [lint_cmd, fmt_cmd]:
        if cmd is None:
            continue
        rc, output = runner(cmd, workdir)
        if _tool_absent(rc, output):
            continue  # tool not installed -> that check is absent tooling, skip (don't fail)
        ran_any = True
        if rc != 0:
            return (False, output, "checked")  # a present tool reported a real style violation

    if not ran_any:
        return (True, "", "no-style-tooling")  # every configured tool was absent
    return (True, "", "checked")
