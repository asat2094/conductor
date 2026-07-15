"""
Generic model-evaluation CLI (evalkit, ADR-0042).

    python3 -m harness.evalkit --model gemma4 [--model sonnet ...] \
        [--suite my_suite.json] [--trials N] [--sizes 1000,8000,32000] \
        [--report out.json] [--text] [--ingest] [--profiles-path P] [--confidence-db DB]

Evaluates each --model over the default grid (or a bring-your-own --suite), prints a ranked
objective MeritScorecard, and — only with --ingest — writes results into routing profiles.
"""
import argparse
import json
import sys
from pathlib import Path

_CLAUDE_TIERS = {"haiku", "sonnet", "opus"}
_PROVIDERS = Path(__file__).resolve().parents[1] / "providers.json"


def resolve_spec(name: str) -> tuple[dict, float]:
    """Map a model name to a (call_model spec, price_per_1k). Claude tiers -> claude_cli;
    providers.json entries -> their backend/model/price; anything else -> best-effort ollama."""
    if name in _CLAUDE_TIERS:
        return {"backend": "claude_cli", "model": name, "name": name}, _claude_price(name)
    try:
        providers = json.loads(_PROVIDERS.read_text())
    except Exception:
        providers = {}
    cfg = providers.get(name)
    if cfg:
        price = float(cfg.get("cost_per_1k_tokens", 0.0))
        if cfg.get("type") == "ollama":
            return {"backend": "ollama", "model": cfg.get("model", name), "name": name}, price
        # openai_compat: carry base_url + api_key_env so call_model can reach it (and fail loud
        # with a clear message if the key env is unset — never silently score 0).
        return ({"backend": "openai_compat", "model": cfg.get("model", name), "name": name,
                 "base_url": cfg["base_url"], "api_key_env": cfg.get("api_key_env")}, price)
    return {"backend": "ollama", "model": name, "name": name}, 0.0


def _claude_price(tier: str) -> float:
    return {"haiku": 0.001, "sonnet": 0.003, "opus": 0.015}.get(tier, 0.0)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m harness.evalkit", description=__doc__)
    ap.add_argument("--model", action="append", required=True, help="model name (repeatable)")
    ap.add_argument("--suite", default=None, help="bring-your-own suite JSON (default: built-in grid)")
    ap.add_argument("--trials", type=int, default=2)
    ap.add_argument("--sizes", default=None, help="comma-separated context sizes for the default suite")
    ap.add_argument("--sources", default=None,
                    help="comma-separated source files to build realistic payloads (else synthetic)")
    ap.add_argument("--language", default="python")
    ap.add_argument("--report", default=None, help="write the scorecard JSON here")
    ap.add_argument("--text", action="store_true", help="print the human leaderboard")
    ap.add_argument("--ingest", action="store_true", help="write results into routing profiles (opt-in)")
    ap.add_argument("--profiles-path", default=None)
    ap.add_argument("--confidence-db", default=None)
    args = ap.parse_args(argv)

    from harness.evalkit import calibrate, default_suite, load_suite, ingest

    if args.suite:
        suite = load_suite(args.suite)
    else:
        from harness.evalkit import resolve_sources
        sizes = [int(x) for x in args.sizes.split(",")] if args.sizes else None
        srcs = resolve_sources(args.sources.split(",")) if args.sources else resolve_sources()
        suite = default_suite(language=args.language, context_sizes=sizes, sources=srcs or None)

    specs, ctx_by_model = [], {}
    for name in args.model:
        spec, price = resolve_spec(name)
        specs.append(spec)
        ctx_by_model[name] = {"price_per_1k": price}

    try:
        scorecard = calibrate(specs, suite, trials=args.trials, ctx_by_model=ctx_by_model)
    except (ValueError, KeyError) as e:
        # config error (unknown/uncallable backend, missing API key) — fail loud, never ingest garbage
        print(f"evalkit: cannot evaluate ({e})", file=sys.stderr)
        return 2

    if args.text or not args.report:
        print(scorecard.render_text())
    if args.report:
        scorecard.publish(args.report)
        print(f"scorecard -> {args.report}")
    if args.ingest:
        ingest(scorecard,
               profiles_path=Path(args.profiles_path) if args.profiles_path else None,
               confidence_db=args.confidence_db)
        print("ingested into routing profiles")

    leader = scorecard.leader()
    print(f"leader: {leader.model} (merit={leader.merit:.1f})" if leader else "no models")
    return 0


if __name__ == "__main__":
    sys.exit(main())
