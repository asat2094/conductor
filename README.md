# conductor — a distributed AI coding harness

Claude orchestrates; decomposes a dev task into a DAG of bounded work-units; assigns roles (maker/checker/validator) to models by capability×cost (Claude families / OSS / local gemma4), each in isolated bounded context. Accepts work only through mechanical gates (tests/AST/mutation/lint) — never a maker's self-report.

```
Claude (orchestrator)
  ├─ route → gemma4 (local, free)   code edits · code gen · test writing
  ├─ route → OpenCode (free tier)   when local budget exhausted
  └─ route → Claude agent           research · cross-file refactors · complex tasks
```

## Core principles

- **Mechanical-first correctness** (Law 1): no model judges its own work. Every output passes syntax check (AST parse), test run (if tests exist), scope validation (changed files match request), and semantic overlap check (description vs output).
- **Bounded-context isolation is the savings** — not model price. The orchestrator sees only brief summaries + lean verdicts; makers see isolated file bodies and test results, not the full codebase. This keeps context lean regardless of repo size.
- **TDD as contract**: a true RED→GREEN→mutation cycle replaces self-assertion. Test author ≠ impl author (ADR-0012); test runs green before the impl author sees them.
- **Author separation** (REQ-T2): test writer and implementation writer are different agents, verified independently against shared ground-truth tests. Prevents collusion.
- **Pluggable language adapters** (Python, JavaScript, generic text). Each speaks its native test runner and linter.
- **Repo-native style gate**: adapts to the target repo's own lint/format tools (Ruff, Prettier, ESLint, etc.). No harness-imposed style.
- **Cost-skip ROI gate** (ADR-0016): if estimated tokens < 800 or projected delegation cost ≥ inline-Claude cost, the unit skips the pipeline and routes to `CLAUDE_INLINE`.
- **Bounded repair loop** (ADR-0013): on evaluator score < 70, the healer auto-tries strategy A (shrink scope) then B (re-prompt with failure detail). Only surfaces strategy C (escalate) if both fail. Limits waste from trivial mis-parses.

## Quickstart

```python
from harness.live_pipeline import build_live, build_report

brief = {
    "id": "add",
    "goal": "Create calc.py with add(a, b) returning a + b.",
    "task_type": "code_gen",
    "files": ["calc.py", "test_calc.py"],
    "writes_files": ["calc.py"],
    "context_slices": [],
    "contract": {"produces": ["add"], "consumes": []},
    "verify_cmd": "python3 -m pytest test_calc.py -q",
    "exit_criteria": "tests pass",
    "sensitivity": "low",
    "estimated_tokens": 5000,
}

result, tracker = build_live([brief], workdir="/path/to/git/repo")
print(build_report(result, tracker))
```

The harness:
1. **Routes** the brief through cost-skip, router, and capability gates.
2. **Decomposes** into RED (test author) and GREEN (impl author) waves if the router assigns it to a maker pool.
3. **Dispatches** each wave in parallel via the assigned maker(s) (local gemma4, cloud cheap OSS, or Claude API).
4. **Evaluates** output against the composed unit gate (syntax + tests + scope + semantic).
5. **Heals** on score < 70 (auto-retry strategies A→B before surfacing C).
6. **Tracks** every unit in SQLite with timestamps, model, tokens, cost, and outcome.

## Requirements

| Tool | Purpose |
|---|---|
| Python 3.11+ | Harness runtime |
| git | Version control (already present) |
| ollama | Optional: runs gemma4 locally (or use free cloud tiers) |
| pytest | Test suite runner (optional; harness auto-detects test files) |

**Network optional.** The harness works entirely local (gemma4 via ollama) or routes to free cloud tiers (DeepSeek, NIM, Gemini, OpenRouter, OpenCode Zen). Bring your own API keys for paid providers.

**gemma4 on ollama** requires ~10 GB disk and ≥16 GB RAM for comfortable use (slower on less RAM).

## Architecture

```
brief (JSON)
  ↓
[cost-skip gate] — if < 800 tokens or projected cost ≥ inline, route to CLAUDE_INLINE
  ↓
[router] — decompose → RED wave (test author) + GREEN wave (impl author)
  ↓
[parallel maker dispatch] — each wave runs independently in isolated bounded context
  ↓
[composed unit gate] — syntax + tests + scope + semantic checks (mechanical, no model judgment)
  ↓
[healer] — if score < 70, auto-retry A (shrink scope) → B (re-prompt) → surface C (escalate)
  ↓
[tracker] — record unit outcome in SQLite (model, tokens, cost, verdict)
  ↓
result + stats
```

Decomposition (ADR-0011), verification (ADR-0012), per-wave cost-skip (ADR-0016), dispatch (ADR-0024), healing (ADR-0013), tracking (ADR-0021), and progress reporting (ADR-0023) each have their own ADR. See `docs/adr/` for the full design (39 ADRs, covering deterministic routing, author separation, cost awareness, and bounded repair).

## Tests

```bash
python3 -m pytest -q
```

434 tests passing. Covers router, evaluator, healer, cost model, capability profiles, parallel dispatch, and the full live pipeline end-to-end.

## Status

**Research-validated + live-proven prototype.** The cost model uses placeholder prices (all providers at `0.0`); the cost-skip gate and budget ceiling (ADR-0014/0034) need real per-1k-token prices to gate meaningfully. Running in `audit` mode (ADR-0034) is safe — it tracks spend and warns but never blocks.

**References:**
- `docs/adr/` — 39 architecture decision records covering the full design philosophy.
- `docs/traceability.md` — traceability matrix linking requirements to ADRs and code.
- `harness/live_pipeline.py` — the entrypoint (composition of router → makers → evaluator → healer → tracker).

## Setup

```bash
git clone https://github.com/asat2094/conductor
cd conductor-develop
bash setup.sh
```

`setup.sh` is idempotent. It checks system specs, verifies ollama + gemma4, installs dependencies, and runs the full test suite.

## Configuration

### Cost calibration (placeholder → real)

All providers in `harness/providers.json` are priced at `cost_per_1k_tokens: 0.0`. To enable the cost-skip gate (ADR-0016) and budget ceiling (ADR-0014/0034):

1. **Add real prices** to `providers.json` (e.g., `"cost_per_1k_tokens": 0.002` for Claude Haiku).
2. **Recalibrate** `harness/cost_model.MIN_DELEGATION_TOKENS` from a real run ledger. See `docs/cost-calibration.md`.
3. **Audit first** (ADR-0034): run in budget `audit` mode to track real spend before switching to `enforce`.

### Local vs. cloud makers

Pass `policy={"default_maker": "gemma4"}` to `build_live()` to prefer local gemma4. The harness respects model availability: if gemma4 is down, it auto-falls back to the next cheaper option (DeepSeek, NIM, OpenRouter, then Claude API). Set via environment:

```bash
export CONDUCTOR_DEFAULT_MAKER="gemma4"   # prefer local
export CONDUCTOR_DEFAULT_MAKER="deepseek" # prefer free DeepSeek Zen
```

### Capability profiles (live-updated)

`harness/capability_profiles.json` tracks per-model accuracy by task type (code_edit, code_gen, test_write). Profiles are updated in-session as units are evaluated and decay toward neutral between sessions. Calibrate from scratch via **evalkit** — the generic, model-agnostic evaluation framework (ADR-0042) that produces an objective, ranked merit scorecard across pluggable dimensions (accuracy, latency, cost-per-pass, refusal rate, context degradation, reliable context):

```bash
python3 -m harness.evalkit --model gemma4 --ingest --text   # calibrate + feed routing profiles
python3 -m harness.evalkit --model gemma4 --model sonnet --report card.json   # rank several models
python3 -m harness.evalkit --model gemma4 --suite my_suite.json               # bring your own tasks
python3 gemma4-bench/bench.py  # backward-compat: a thin evalkit client for gemma4
```

evalkit is reusable anywhere model evaluation is needed — mechanical graders (no model judges output, Law 1/2), pluggable `Dimension` axes, built-in + bring-your-own suites, published objective report; feeding routing is an explicit opt-in `ingest()` step.

---

**Questions?** See the ADRs (`docs/adr/`) for deep dives on routing, author separation, cost awareness, and bounded repair. The design is fully traced and decision-rationale is explicit.
