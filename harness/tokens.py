"""
Token estimation from file sizes — avoids requiring user to supply estimated_tokens.
Uses characters/4 as a conservative word-to-token approximation.
"""
from pathlib import Path


def estimate_tokens(files: list[str], workdir: str = ".") -> int:
    total = 0
    root = Path(workdir)
    for f in files:
        path = root / f
        if path.exists():
            total += len(path.read_text()) // 4
    return total
