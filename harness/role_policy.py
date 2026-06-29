"""
Role -> model assignment (ADR-0024). Roles are model-assignments chosen by capability x cost;
the invariant (bounded-context isolation) lives in the maker, not here. High-stakes bumps cheap
roles up a tier. Pure; no IO. A custom policy dict overrides the defaults per role.
"""
from typing import Optional

# capability/cost tiers (cheap -> capable)
TIERS = [
    {"backend": "ollama", "model": "gemma4:latest"},
    {"backend": "claude_cli", "model": "haiku"},
    {"backend": "claude_cli", "model": "sonnet"},
    {"backend": "claude_cli", "model": "opus"},
]

ROLE_DEFAULTS = {
    "decomposer":  {"backend": "claude_cli", "model": "opus"},
    "test_author": {"backend": "claude_cli", "model": "sonnet"},
    "impl_author": {"backend": "ollama", "model": "gemma4:latest"},
    "verifier":    {"backend": "claude_cli", "model": "haiku"},
    "checker":     {"backend": "claude_cli", "model": "haiku"},
}


def _bump(spec: dict) -> dict:
    """Return the next capability tier above `spec` (or the top tier)."""
    for i, t in enumerate(TIERS):
        if t == spec:
            return TIERS[min(i + 1, len(TIERS) - 1)]
    # spec not a known tier -> escalate to sonnet as a safe high tier
    return {"backend": "claude_cli", "model": "sonnet"}


def resolve_model(role: str, *, high_stakes: bool = False, policy: Optional[dict] = None) -> dict:
    table = {**ROLE_DEFAULTS, **(policy or {})}
    spec = table.get(role, table["checker"])
    if high_stakes:
        spec = _bump(spec)
    return dict(spec)
