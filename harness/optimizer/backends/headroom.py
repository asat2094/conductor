"""
Headroom backend (ADR-0021, opt-in). Lazy-imports the heavy `headroom-ai` dependency; if it is not
installed, available() is False and the registry degrades to null. Real compression via
headroom.compress when present. CCR retrieve() wiring is deferred to the pipeline plan.
"""
import importlib.util
from typing import Any, Optional

from harness.optimizer.base import OptimizeConfig, OptimizeResult, count_tokens


class HeadroomCompressor:
    name = "headroom"

    def available(self) -> bool:
        return importlib.util.find_spec("headroom") is not None

    def optimize(self, messages: list[dict[str, Any]], cfg: OptimizeConfig) -> OptimizeResult:
        from headroom import compress  # lazy — only when available

        kwargs: dict[str, Any] = {}
        if cfg.target_ratio is not None:
            kwargs["target_ratio"] = cfg.target_ratio
        result = compress(messages, **kwargs)
        before = getattr(result, "tokens_before", count_tokens(messages))
        after = getattr(result, "tokens_after", count_tokens(result.messages))
        return OptimizeResult(
            messages=result.messages, tokens_before=before, tokens_after=after,
            tokens_saved=max(0, before - after),
            transforms_applied=list(getattr(result, "transforms_applied", ["headroom"])),
            backend="headroom",
        )

    def retrieve(self, handle: str) -> Optional[str]:
        return None  # CCR retrieve wiring deferred to the pipeline plan
