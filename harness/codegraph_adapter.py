"""
Codegraph dependency lookup with an explicit degrade path (REQ-D4, ADR-0011).

The real source is the codegraphcontext MCP, available only in a live session. It is injected
as `query_fn(files, workdir) -> dict[str, list[str]]` so this module stays unit-testable and the
MCP-absent / MCP-error path is explicit: return {} → caller falls back to logical_deps-only.
Wiring query_fn to the live MCP happens in the pipeline plan.
"""
from typing import Callable, Optional

QueryFn = Callable[[list, str], dict]


def dependency_edges(files: list[str], workdir: str, query_fn: Optional[QueryFn] = None) -> dict[str, list[str]]:
    """symbol -> list of symbols it depends on. {} means 'no graph available' (degrade)."""
    if query_fn is None:
        return {}
    try:
        result = query_fn(files, workdir)
    except Exception:
        return {}
    return result if isinstance(result, dict) else {}
