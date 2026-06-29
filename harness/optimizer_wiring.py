"""Context-optimizer wiring for reader-aware compression (REQ-RM3, ADR-0021).

Only compress when the READER is a paid model (claude_cli backend).
Free/local readers (ollama) → latency-only, skip compression by default.

This module gates optimization to paid-model read boundaries: if the reader
consuming the messages is local/free (ollama), skip the expensive compress step.
If the reader is a paid Claude API model, apply optimization.
"""
from typing import Any, Optional

from harness.optimizer import optimize
from harness.optimizer.base import OptimizeConfig


def is_paid_reader(spec: dict[str, Any]) -> bool:
    """Check if the reader spec indicates a paid Claude API consumer.

    Args:
        spec: Reader specification dict with 'backend' and optional 'model' keys.

    Returns:
        True iff spec["backend"] == "claude_cli" (paid Claude API).
        False for local backends (ollama, mock, etc.).
    """
    return spec.get("backend") == "claude_cli"


def optimize_for_reader(
    messages: list[dict[str, Any]],
    reader_spec: dict[str, Any],
    *,
    backend: str = "caveman",
    min_tokens: int = 250,
) -> list[dict[str, Any]]:
    """Compress messages only if the reader is a paid model.

    Implements REQ-RM3/ADR-0021: apply context optimization at paid-model read
    boundaries. Free/local readers (ollama) skip compression for latency.
    System messages and protected roles are never compressed (safety guard).

    Args:
        messages: Message list to optimize.
        reader_spec: Reader specification (e.g., {"backend": "claude_cli", "model": "haiku"}).
        backend: Compression backend to use if reader is paid (default: "caveman").
        min_tokens: Minimum message size before compression (default: 250).

    Returns:
        If reader is paid: optimized messages (possibly compressed).
        If reader is free: messages unchanged (latency not cost-sensitive).
    """
    if not is_paid_reader(reader_spec):
        # Free reader → no compression, avoid latency penalty
        return messages

    # Paid reader → apply optimization
    cfg = OptimizeConfig(backend=backend, min_tokens=min_tokens)
    result = optimize(messages, cfg)
    return result.messages
