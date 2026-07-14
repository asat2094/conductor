"""
Gate the orchestrator's OWN (non-deterministic LLM) outputs (REQ-O2/O3, ADR-0011). The orchestrator
authors the DAG and the acceptance tests; if those are wrong, every downstream mechanical-green is
wrong-but-green. Two checks, both fail-closed:
  - REQ-O2: orchestrator-authored acceptance tests are RED-validated against HEAD (must FAIL pre-build,
    proving they actually test the not-yet-built behavior).
  - REQ-O3: the DAG/contracts get an independent second-model review for high-stakes builds.
All IO is injected (runner for tests, reviewer for the 2nd model) so the logic is unit-testable.
"""
from typing import Callable, Optional


def red_validate_acceptance(test_cmds: list, *, runner: Callable) -> tuple:
    """Each acceptance test must FAIL (rc != 0) against HEAD. A passing one is an offender (it does
    not test new behavior). Returns (all_red, offenders)."""
    offenders = []
    for cmd in test_cmds:
        rc, _ = runner(cmd)
        if rc == 0:
            offenders.append(cmd)
    return (len(offenders) == 0, offenders)


def review_dag(dag_summary, *, reviewer: Optional[Callable], high_stakes: bool = False) -> tuple:
    """Independent 2nd-model review of the DAG/contracts for high-stakes builds. Low-stakes -> skipped.
    Reviewer exceptions fail closed."""
    if not high_stakes:
        return (True, "skipped (low-stakes)")
    if reviewer is None:
        return (False, "high-stakes build requires a reviewer")
    try:
        approved, notes = reviewer(dag_summary)
    except Exception as e:  # fail closed
        return (False, f"review error: {e}")
    return (bool(approved), notes)


def orchestrator_gate(test_cmds: list, dag_summary, *, runner: Callable,
                      reviewer: Optional[Callable] = None, high_stakes: bool = False) -> tuple:
    """ok iff all acceptance tests are RED (REQ-O2) AND the DAG review approves (REQ-O3, high-stakes)."""
    all_red, offenders = red_validate_acceptance(test_cmds, runner=runner)
    if not all_red:
        return (False, f"acceptance tests not RED (offenders pass pre-build): {offenders}")
    approved, notes = review_dag(dag_summary, reviewer=reviewer, high_stakes=high_stakes)
    if not approved:
        return (False, f"DAG review rejected: {notes}")
    return (True, "orchestrator outputs gated OK")
