# harness/evalkit/

A **generic, model-agnostic evaluation framework** with objective merit scoring (ADR-0042). Usable
anywhere model evaluation is needed — not conductor-specific. Everything is mechanical/deterministic:
no model ever judges output (Law 1/2), so results are a defensible, objective basis for decisions.

## Pipeline

```
specs ─→ evaluate() ─→ TrialResults ─→ build_scorecard() ─→ MeritScorecard ─→ ingest() [opt-in]
         (per model)   (mechanical    (objective, ranked)   (published)       └→ capability_profiles
                        graders)                                                  + ConfidenceStore
```

## CLI

```bash
python3 -m harness.evalkit --model gemma4 --text                     # objective merit scorecard
python3 -m harness.evalkit --model gemma4 --model sonnet --report card.json   # rank several models
python3 -m harness.evalkit --model gemma4 --suite my_suite.json      # bring your own tasks
python3 -m harness.evalkit --model gemma4 --sources a.py,b.py        # realistic context payloads
python3 -m harness.evalkit --model gemma4 --ingest                   # feed routing profiles (opt-in)
```

A cloud model with a missing API key **fails loud** (exit 2) — it never silently scores 0 and poisons
routing profiles.

## Library

```python
from harness.evalkit import calibrate, default_suite, load_suite, ingest, register_dimension

card = calibrate([{"backend": "ollama", "model": "gemma4:latest", "name": "gemma4"}],
                 default_suite(), trials=2, ctx_by_model={"gemma4": {"price_per_1k": 0.0}})
print(card.render_text())          # ranked leaderboard, per-dimension, per-task-type
ingest(card)                       # -> capability_profiles.json (rolling avg), opt-in
```

## Pieces

| File | Role |
|---|---|
| `graders.py` | mechanical `Grader`: `Syntax` (→LanguageAdapter, any lang) · `Keyword` · `Oracle` (held-out assertion) · `Composite` · `Gated` (syntax gates keyword) |
| `dimensions.py` | pluggable `Dimension` registry: `accuracy` · `reliable_context` · `latency` · `cost_per_pass` · `refusal_rate` · `context_degradation` |
| `task.py` | `EvalTask` / `EvalSuite`, `default_suite()`, `load_suite()` (BYO), `resolve_sources()` |
| `runner.py` | model-agnostic trials via `model_call` (ollama / claude / openai_compat); errors→refusals, config errors propagate |
| `report.py` | `MeritScorecard` — weighted composite merit, ranked, per-origin breakdown, JSON+text, `publish()` |
| `ingest.py` | opt-in: scorecard → `capability_profiles` + `ConfidenceStore` seed |

## Extend it

- **New rating axis:** `register_dimension("my_axis", MyDimension)` — `compute(trials, ctx) -> DimensionScore(value, unit, normalized, detail)`.
- **New grader:** any object with `grade(output, task) -> int` in [0,100]; wire it into a suite task.
- **Your own suite:** `load_suite(path_or_list)` — JSON tasks `{id, task_type, language, prompt, context_tokens, grader:{...}}`; grader kinds: `syntax` · `keyword` · `oracle` · `composite`.

> **Security:** an `oracle` grader's `cmd` runs via shell — suite JSON is a trusted-operator input,
> never load a suite from untrusted / PR-submitted content.
