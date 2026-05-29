"""
Token estimation from file sizes.
Uses chars/4 as baseline (common GPT-family approximation) with per-extension
multipliers to compensate for high/low information density.
"""
from pathlib import Path

# Multiplier applied to (chars / 4) per extension.
# > 1.0: more tokens per char than avg code (dense syntax, repeated keys)
# < 1.0: fewer tokens per char (prose compresses well, long words)
_EXT_MULTIPLIER: dict[str, float] = {
    ".json": 1.4,    # lots of quotes, brackets, repeated keys
    ".yaml": 1.2,    # indentation + colons inflate token count
    ".yml":  1.2,
    ".toml": 1.1,
    ".md":   0.8,    # prose — long words tokenise efficiently
    ".txt":  0.8,
    ".html": 1.3,    # tag overhead
    ".css":  1.1,
    ".js":   1.0,
    ".ts":   1.0,
    ".py":   1.0,    # baseline
    ".sh":   1.0,
    ".sql":  1.1,
}
_DEFAULT_MULTIPLIER = 1.0


def estimate_tokens(files: list[str], workdir: str = ".") -> int:
    total = 0
    root = Path(workdir)
    for f in files:
        path = root / f
        if path.exists():
            mult = _EXT_MULTIPLIER.get(path.suffix.lower(), _DEFAULT_MULTIPLIER)
            total += int(len(path.read_text()) / 4 * mult)
    return total
