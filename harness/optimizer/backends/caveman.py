"""
Caveman backend — stdlib prose trim (ADR-0021). Deterministic, zero deps. Drops filler words and
collapses whitespace in string message content. Conservative: only edits content, never structure.
Inspiration: github.com/juliusbrussee/caveman (output-style compression).
"""
import re
from typing import Any, Optional

from harness.optimizer.base import OptimizeConfig, OptimizeResult, count_tokens

_FILLER = (
    "basically", "really", "actually", "simply", "just", "very", "quite",
    "in order to", "of course", "as you can see", "it should be noted that",
)
_FILLER_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in _FILLER) + r")\b", re.IGNORECASE)
_WS_RE = re.compile(r"[ \t]{2,}")


def _trim(text: str) -> str:
    text = _FILLER_RE.sub("", text)
    text = _WS_RE.sub(" ", text)
    text = re.sub(r" +([.,;:!?])", r"\1", text)
    return text.strip()


class CavemanCompressor:
    name = "caveman"

    def available(self) -> bool:
        return True

    def optimize(self, messages: list[dict[str, Any]], cfg: OptimizeConfig) -> OptimizeResult:
        before = count_tokens(messages)
        out: list[dict[str, Any]] = []
        for m in messages:
            content = m.get("content")
            if isinstance(content, str):
                out.append({**m, "content": _trim(content)})
            else:
                out.append(m)
        after = count_tokens(out)
        return OptimizeResult(
            messages=out, tokens_before=before, tokens_after=after,
            tokens_saved=max(0, before - after), transforms_applied=["caveman:prose-trim"], backend="caveman",
        )

    def retrieve(self, handle: str) -> Optional[str]:
        return None
