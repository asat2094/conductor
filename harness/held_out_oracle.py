"""
Held-out acceptance oracle (ADR-0026, REQ-T12). A spec/human-derived acceptance test the impl-maker
NEVER sees (stripped from its visible context). Run only at the acceptance boundary via an injected
runner. Mandatory for high-stakes units; optional (falls back to in-loop GREEN) otherwise.
"""
import os
from typing import Callable, Optional


def strip_oracle_from_context(visible_files: list[str], oracle_paths: list[str]) -> list[str]:
    """Remove held-out oracle paths from what the impl-maker sees. Paths are normalized
    (os.path.normpath) on both sides so './tests/x.py' and 'tests/x.py' compare equal — a
    mismatch here would leak the oracle, so normalization is a security requirement."""
    blocked = {os.path.normpath(p) for p in oracle_paths}
    return [f for f in visible_files if os.path.normpath(f) not in blocked]


def run_oracle(oracle_cmd: str, runner: Callable[[str], bool]) -> bool:
    """Run the held-out oracle via an injected runner (returns pass/fail). Runner is injected so the
    harness controls execution and tests need no live subprocess."""
    return bool(runner(oracle_cmd))


def accept(in_loop_green: bool, oracle_passed: Optional[bool], high_stakes: bool) -> bool:
    """Accept only when in-loop GREEN AND the held-out oracle passes. High-stakes units REQUIRE an
    oracle result (None == not run == reject). Low-stakes may fall back to in-loop GREEN."""
    if not in_loop_green:
        return False
    if oracle_passed is None:
        return not high_stakes   # high-stakes needs the oracle; low-stakes falls back to green
    return bool(oracle_passed)
