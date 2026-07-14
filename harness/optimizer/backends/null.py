"""Null backend — passthrough. Always available, zero deps, cannot alter content (ADR-0021 default)."""
from typing import Any, Optional

from harness.optimizer.base import OptimizeConfig, OptimizeResult, count_tokens


class NullCompressor:
    name = "null"

    def available(self) -> bool:
        return True

    def optimize(self, messages: list[dict[str, Any]], cfg: OptimizeConfig) -> OptimizeResult:
        n = count_tokens(messages)
        return OptimizeResult(messages=messages, tokens_before=n, tokens_after=n, tokens_saved=0, backend="null")

    def retrieve(self, handle: str) -> Optional[str]:
        return None
