"""
Provider-agnostic context-optimizer contracts (ADR-0021, REQ-E1/E2/E3).
No conductor-specific imports — this package is extractable/reusable by any system.
"""
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable


@dataclass
class OptimizeConfig:
    backend: str = "null"
    min_tokens: int = 250
    protect_roles: tuple[str, ...] = ("system",)
    protect_tags: tuple[str, ...] = ("__gate_evidence__", "__code_edit__")
    target_ratio: Optional[float] = None


@dataclass
class OptimizeResult:
    messages: list[dict[str, Any]]
    tokens_before: int = 0
    tokens_after: int = 0
    tokens_saved: int = 0
    transforms_applied: list[str] = field(default_factory=list)
    backend: str = "null"


def count_tokens(messages: list[dict[str, Any]]) -> int:
    """Cheap char/4 token estimate over message string content. Self-contained (no external tokenizer)."""
    total = 0
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            total += len(content) // 4
    return total


@runtime_checkable
class Compressor(Protocol):
    name: str

    def available(self) -> bool:
        """True if this backend's dependencies are importable and usable."""
        ...

    def optimize(self, messages: list[dict[str, Any]], cfg: OptimizeConfig) -> OptimizeResult:
        """Return compressed messages (same count + order) + metrics."""
        ...

    def retrieve(self, handle: str) -> Optional[str]:
        """Reversible backends return the original for a handle; others return None."""
        ...
