"""
Facade-enforced safety invariants (ADR-0021). These hold regardless of backend:
- protected messages (by role, by tag, or below min_tokens) are restored byte-identical;
- if a backend changes the message count, the whole result is rejected for the original.
This makes a Law-1 violation (compressing gate evidence / code) structurally impossible.
"""
from typing import Any

from harness.optimizer.base import OptimizeConfig, count_tokens


def is_protected(message: dict[str, Any], cfg: OptimizeConfig) -> bool:
    if message.get("role") in cfg.protect_roles:
        return True
    content = message.get("content")
    if isinstance(content, str):
        if any(tag in content for tag in cfg.protect_tags):
            return True
        if count_tokens([message]) < cfg.min_tokens:
            return True
    else:
        return True
    return False


def restore_protected(
    original: list[dict[str, Any]], compressed: list[dict[str, Any]], cfg: OptimizeConfig
) -> list[dict[str, Any]]:
    """Overwrite protected slots with their originals. Reject (return original) on count mismatch."""
    if len(original) != len(compressed):
        return original
    out = list(compressed)
    for i, orig in enumerate(original):
        if is_protected(orig, cfg):
            out[i] = orig
    return out
