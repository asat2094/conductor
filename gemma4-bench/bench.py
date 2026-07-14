#!/usr/bin/env python3
"""
gemma4 capability calibration — now a THIN CONFIG over the generic evalkit framework (ADR-0042).

Historically this file WAS the benchmark (gemma4-locked, Python-only, bespoke scorer). It is now
one configuration of harness.evalkit: evaluate gemma4 over the default suite and ingest the
objective scorecard into capability_profiles.json. Proves the framework is reusable by being a
15-line client of it. Equivalent generic form:

    python3 -m harness.evalkit --model gemma4 --ingest --text

`resolve_sources` is retained for backward-compat (env override CONDUCTOR_BENCH_SOURCES); the
generic default suite now uses portable synthetic payloads, so real sources are optional.
"""
import os
from pathlib import Path

BENCH_DIR = Path(__file__).parent
HARNESS_DIR = BENCH_DIR.parent / "harness"
RESULTS_PATH = BENCH_DIR / "bench_results.json"

_DEFAULT_SOURCE_CANDIDATES = [
    HARNESS_DIR / "orchestrate.py",
    HARNESS_DIR / "evaluator.py",
    HARNESS_DIR / "provider_call.py",
]


def resolve_sources(candidates: list | None = None) -> list[str]:
    """Env override → candidates → synthetic fallback. Retained for backward-compat."""
    env = os.environ.get("CONDUCTOR_BENCH_SOURCES")
    if env:
        paths = [Path(p) for p in env.split(os.pathsep) if p]
    elif candidates is not None:
        paths = list(candidates)
    else:
        paths = list(_DEFAULT_SOURCE_CANDIDATES)
    texts = [p.read_text() for p in paths if isinstance(p, Path) and p.exists()]
    if not texts:
        texts = ["def placeholder(): pass\n" * 50]
    return texts


def main():
    import sys
    sys.path.insert(0, str(BENCH_DIR.parent))
    from harness.evalkit import calibrate, default_suite, ingest

    print("Calibrating gemma4 via evalkit (generic framework)...")
    scorecard = calibrate(
        [{"backend": "ollama", "model": "gemma4:latest", "name": "gemma4"}],
        default_suite(),
        trials=2,
        ctx_by_model={"gemma4": {"price_per_1k": 0.0}},
    )
    print(scorecard.render_text())
    scorecard.publish(str(RESULTS_PATH))
    ingest(scorecard)                       # -> harness/capability_profiles.json (rolling avg)
    print(f"\nRaw scorecard -> {RESULTS_PATH}; profiles updated.")


if __name__ == "__main__":
    main()
