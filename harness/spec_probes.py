"""
Spec-completeness probes — surface omitted edge-cases + prohibitions as CANDIDATE criteria.

ADVISORY ONLY (ADR-0032, REQ-D11):
- Probes PROPOSE criteria; a mechanical gate (PBT/characterization) DISPOSES.
- Probe output is never gate evidence (Law 1).
- The 8-category taxonomy is heuristic, reduces not eliminates missing-edge risk.

Probes may accept an optional external prober for enrichment, but deterministic
default is always used if no prober is provided.
"""

import copy
from typing import Callable, Optional


EDGE_CATEGORIES = ("boundary", "adjacency", "empty", "encoding", "ordering", "precision", "idempotency", "concurrency")


def edge_probe(brief: dict, *, prober: Optional[Callable] = None) -> list[str]:
    """
    Return candidate edge-case criteria for a brief.

    Args:
        brief: Brief dict containing at least "goal" key.
        prober: Optional external function(brief, EDGE_CATEGORIES) -> list[str].
                If provided, its output is returned instead of deterministic default.

    Returns:
        List of candidate criteria, one per EDGE_CATEGORIES entry.
        Each criterion is templated against brief["goal"].

    Design:
        - If prober is provided, call it and return result (advisory enrichment).
        - Otherwise return deterministic default criteria.
        - Does NOT mutate input.
    """
    default = _default_edges(brief)
    if prober is not None:
        # ADVISORY guarantee (ADR-0032): a misbehaving prober must NEVER block the caller —
        # degrade to the deterministic default on any exception.
        try:
            return prober(brief, EDGE_CATEGORIES)
        except Exception:
            return default
    return default


def _default_edges(brief: dict) -> list[str]:
    goal = brief.get("goal", "operation")
    return [
        f"boundary: verify {goal} handles boundary inputs",
        f"adjacency: verify {goal} handles inputs near valid ranges",
        f"empty: verify {goal} handles empty or null inputs",
        f"encoding: verify {goal} handles encoding variations",
        f"ordering: verify {goal} handles different input orderings",
        f"precision: verify {goal} handles precision/rounding edge cases",
        f"idempotency: verify {goal} is idempotent when applicable",
        f"concurrency: verify {goal} is safe under concurrent access",
    ]


def prohibition_probe(brief: dict, *, prober: Optional[Callable] = None) -> list[str]:
    """
    Return must-NOT candidate criteria for a brief.

    Args:
        brief: Brief dict containing at least "goal" key.
        prober: Optional external function(brief, EDGE_CATEGORIES) -> list[str].
                If provided, its output is returned instead of deterministic default.

    Returns:
        List of must-NOT candidate criteria.

    Design:
        - If prober is provided, call it and return result (advisory enrichment).
        - Otherwise return deterministic default prohibitions.
        - Does NOT mutate input.
    """
    default = [
        "must not crash on empty input",
        "must not mutate input parameters",
        "must not silently ignore errors",
        "must not leak secrets in error messages",
        "must not block indefinitely on concurrent access",
    ]
    if prober is not None:
        try:  # advisory must never block (ADR-0032)
            return prober(brief, EDGE_CATEGORIES)
        except Exception:
            return default
    return default


def annotate_brief(brief: dict, *, prober: Optional[Callable] = None) -> dict:
    """
    Return a COPY of brief with candidate_criteria injected as ADVISORY annotations.

    Args:
        brief: Original brief dict.
        prober: Optional external function for enrichment.

    Returns:
        New dict with all original fields plus "candidate_criteria" key.
        The "candidate_criteria" dict has:
          - "edges": output of edge_probe()
          - "prohibitions": output of prohibition_probe()
          - "dismissed": empty list (for future use)

    Design:
        - Does NOT mutate input.
        - Returned dict is a shallow copy with new "candidate_criteria" key.
        - candidate_criteria is ADVISORY only — never used as gate evidence.
    """
    out = copy.deepcopy(brief)   # deep copy so nested fields can't bleed back into the input
    out["candidate_criteria"] = {
        "edges": edge_probe(brief, prober=prober),
        "prohibitions": prohibition_probe(brief, prober=prober),
        "dismissed": [],
    }
    return out
