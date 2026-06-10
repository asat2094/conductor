"""
Pluggable context-optimizer facade (ADR-0021). One entry point: optimize(messages, cfg).
Default backend is 'null' (passthrough) so the optimizer is inert out of the box. Backends are
registered below; third parties may register more via harness.optimizer.registry.register.
The facade enforces the safety guard (protect-list restore, degrade-to-null) on every call.
"""
from typing import Any, Optional

from harness.optimizer.base import Compressor, OptimizeConfig, OptimizeResult, count_tokens
from harness.optimizer import registry
from harness.optimizer.guard import restore_protected
from harness.optimizer.backends.null import NullCompressor
from harness.optimizer.backends.caveman import CavemanCompressor
from harness.optimizer.backends.headroom import HeadroomCompressor

# Register built-in backends. null + caveman are baked in (zero deps); headroom is opt-in.
registry.register("null", lambda: NullCompressor())
registry.register("caveman", lambda: CavemanCompressor())
registry.register("headroom", lambda: HeadroomCompressor())


def optimize(messages: list[dict[str, Any]], cfg: Optional[OptimizeConfig] = None) -> OptimizeResult:
    """Compress what the LLM reads via the configured backend, enforcing safety invariants.

    Default (no cfg) is passthrough. Any backend failure degrades to null. Protected messages
    (system role, protect-tagged, or below min_tokens) are restored byte-identical.
    """
    cfg = cfg or OptimizeConfig()
    backend = registry.resolve_from_config(cfg)
    try:
        result = backend.optimize(messages, cfg)
    except Exception:
        result = NullCompressor().optimize(messages, cfg)
    result.messages = restore_protected(messages, result.messages, cfg)
    # recompute after-count in case protected restore changed it
    result.tokens_after = count_tokens(result.messages)
    result.tokens_saved = max(0, result.tokens_before - result.tokens_after)
    return result


__all__ = ["optimize", "OptimizeConfig", "OptimizeResult", "Compressor", "registry"]
