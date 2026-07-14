"""
Decomposition hard gate (REQ-D5, ADR-0011). Validates briefs, lints the plan, and only on a
clean result returns the topologically-ordered dispatch waves. Any failure raises
DecompositionError carrying all errors — nothing dispatches until decomposition is clean.

logical_deps + produces/consumes drive the DAG (REQ-D1). Codegraph edges, when available, are a
hint the orchestrator folds into logical_deps upstream; this module is deterministic given briefs.
"""
from harness.brief import validate_brief
from harness.lint_plan import lint_briefs
from harness.dag import build_edges, topo_waves, DagCycleError


class DecompositionError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def decompose(briefs: list[dict]) -> list[list[str]]:
    """Return ordered dispatch waves (list of lists of unit ids). Raise DecompositionError on any gate failure."""
    errors: list[str] = []
    for b in briefs:
        for e in validate_brief(b):
            errors.append(f"{b.get('id', '?')}: {e}")
    if errors:
        raise DecompositionError(errors)

    lint_errors = lint_briefs(briefs)
    if lint_errors:
        raise DecompositionError(lint_errors)

    try:
        return topo_waves(build_edges(briefs))
    except DagCycleError as e:
        raise DecompositionError([str(e)])
