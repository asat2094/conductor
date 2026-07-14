"""
Codegraph CLI adapter — live query_fn for verify_decomposition (REQ-D4, REQ-D6).

REQ-D4 degrade-clean: any error (missing CLI, rc != 0, parse failure, exception)
degrades to {} or per-file [] without raising. The verifier falls back to
declaration-only 'unverified' status; the build is never blocked by this module.

Wires the `codegraph` CLI as a query_fn suitable for:
    verify_decomposition(briefs, edges=make_codegraph_query()(files, workdir))
"""
from __future__ import annotations

import json
import subprocess
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

Runner = Callable[[list[str], Optional[str]], tuple[int, str]]


# ---------------------------------------------------------------------------
# Default subprocess runner
# ---------------------------------------------------------------------------

def _default_runner(args: list[str], cwd: Optional[str] = None) -> tuple[int, str]:
    """Thin subprocess wrapper. Returns (returncode, stdout+stderr)."""
    try:
        result = subprocess.run(
            ["codegraph"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode, result.stdout + result.stderr
    except Exception as exc:
        return 1, str(exc)


# ---------------------------------------------------------------------------
# parse_symbols
# ---------------------------------------------------------------------------

def parse_symbols(cli_output: str) -> list[str]:
    """Parse symbol names from codegraph CLI output.

    Accepts:
    - JSON list of dicts with a "name" key: [{"name": "foo"}, ...]
    - JSON list of strings: ["foo", "bar"]
    - Plain newline-separated symbol names (fallback)

    Returns a deduplicated list preserving first-seen order. Blank tokens
    and tokens that are clearly non-identifier (no alphanumeric content) are
    dropped. Never raises.
    """
    stripped = cli_output.strip()
    if stripped:
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                names: list[str] = []
                for item in parsed:
                    if isinstance(item, dict) and "name" in item:
                        names.append(str(item["name"]))
                    elif isinstance(item, str):
                        names.append(item)
                return _dedup_clean(names)
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback: plain lines
    lines = cli_output.splitlines()
    return _dedup_clean(lines)


def _dedup_clean(tokens: list[str]) -> list[str]:
    """Deduplicate preserving order; drop blank/non-identifier tokens."""
    seen: set[str] = set()
    result: list[str] = []
    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue
        # Keep tokens that contain at least one alphanumeric char
        if not any(c.isalnum() or c == "_" for c in tok):
            continue
        if tok not in seen:
            seen.add(tok)
            result.append(tok)
    return result


# ---------------------------------------------------------------------------
# make_codegraph_query
# ---------------------------------------------------------------------------

def make_codegraph_query(*, runner: Optional[Runner] = None) -> Callable[[list[str], str], dict[str, list[str]]]:
    """Return a query_fn(files, workdir) -> {file_path: [referenced_symbols]}.

    For each file the adapter calls `codegraph query <file>` via `runner`.
    - rc == 0  → parse stdout for symbols → file maps to [symbols]
    - rc != 0  → file maps to []  (REQ-D4 per-file degrade)
    - exception → file maps to []  (REQ-D4 per-file degrade)
    - total failure (e.g. outer exception) → returns {}

    The returned callable is safe to pass directly as the `edges` argument of
    verify_decomposition after being invoked:
        edges = make_codegraph_query()(files, workdir)
        report = verify_decomposition(briefs, edges=edges)
    """
    _runner: Runner = runner if runner is not None else _default_runner

    def query_fn(files: list[str], workdir: str) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        try:
            for f in files:
                try:
                    rc, out = _runner(["query", f], workdir)
                    if rc == 0:
                        result[f] = parse_symbols(out)
                    else:
                        result[f] = []
                except Exception:
                    result[f] = []
        except Exception:
            return {}
        return result

    return query_fn


# ---------------------------------------------------------------------------
# codegraph_available
# ---------------------------------------------------------------------------

def codegraph_available(*, runner: Optional[Runner] = None) -> bool:
    """Return True iff the codegraph CLI is present and responsive.

    Calls `codegraph --version`; falls back to `codegraph --help` implicitly
    through the single call. Returns False on any exception (REQ-D4 degrade).
    """
    _runner: Runner = runner if runner is not None else _default_runner
    try:
        rc, _ = _runner(["--version"], None)
        return rc == 0
    except Exception:
        return False
