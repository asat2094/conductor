# ADR-0042: Generic, pluggable model-evaluation framework (evalkit)

- **Status:** Accepted
- **Date:** 2026-07-14
- **Supersedes:** the gemma4-locked `gemma4-bench/bench.py` calibration script (now a thin client).
- **Requirements:** REQ-EVAL1 (model-agnostic evaluation), REQ-EVAL2 (objective merit scoring), REQ-EVAL3 (extensible dimensions + suites)

## Context

`gemma4-bench/bench.py` was the offline calibration source that seeds `capability_profiles.json`
(which routing ranks on, ADR-0006/0015, and confidence seeds from, ADR-0039). It was needed — but
mis-built with exactly the couplings this project spent its life removing:

1. **gemma4-locked** — hardcoded ollama + `gemma4:latest`; wrote only the gemma4 profile.
2. **Python-locked** — scored via `ast.parse` (violates ADR-0035 language adapters).
3. **Divergent scorer** — a bespoke `ast+keyword` grader, *different* from the mechanical gate
   production actually uses, so calibration measured something other than what routing decides on.

The requirement: a **generic evaluation framework usable anywhere model evaluation is needed**,
producing **meritocratic, detailed, objective** scoring for whatever it evaluates — with pluggable
rating dimensions and both a built-in and bring-your-own suite path, all surfaced in one report.

## Decision

Introduce **`harness/evalkit/`** — a standalone, model-agnostic evaluation framework:

- **Grader protocol** (`graders.py`) — mechanical rating primitives: `SyntaxGrader` (delegates to
  `LanguageAdapter.check_syntax`, language-agnostic), `KeywordGrader`, `OracleGrader` (held-out
  assertion command), `CompositeGrader`. No model judges output — same mechanical basis as the live
  gate (Law 1/2). This is the "generic rating mechanism."
- **Pluggable `Dimension` registry** (`dimensions.py`) — each axis reduces trials to an objective
  value + a normalized 0-100 so unlike units combine. Built-ins: `accuracy`, `reliable_context`,
  `latency`, `cost_per_pass`, `refusal_rate`, `context_degradation`. `register()` adds your own —
  same facade pattern as the optimizer/language adapters (ADR-0021/0035).
- **Suites** (`task.py`) — `default_suite()` (portable synthetic grid, no host-repo dependency) plus
  `load_suite()` for bring-your-own JSON; every task is tagged `builtin|custom` and both origins are
  broken out in the report.
- **Model-agnostic runner** (`runner.py`) — trials run through an injected `caller(spec, prompt)`
  defaulting to `model_call.call_model`, so any backend the harness speaks is evaluable; errors
  become scored-0 refusals, never crashes.
- **`MeritScorecard`** (`report.py`) — per-model × per-dimension × per-task-type, a weighted composite
  **merit**, per-suite-origin breakdown, ranked leaderboard, published as JSON + text. Deterministic
  arithmetic over mechanical measurements — an **objective** basis for decisions, not subjective.
- **Explicit ingest** (`ingest.py`) — a *separate, opt-in* step turns the scorecard into routing
  state (`capability_profiles` + `ConfidenceStore` seed). The report stays the objective source of
  truth; routing consumes it deliberately, never as a side effect.
- **Two entrypoints** — `python3 -m harness.evalkit --model X [--suite f] [--ingest]` and the
  retained `gemma4-bench/bench.py`, now a ~15-line client of evalkit (backward-compat proof that the
  framework is reusable).

## Considered alternatives

- **Keep the gemma4-only script** — Rejected: can't evaluate other models, Python-only, scorer
  divergent from production.
- **Generalize the existing ast+keyword scorer in place** — Rejected: stays Python-locked and keeps
  the calibrate-vs-gate divergence.
- **LLM-judge scoring** — Rejected (Law 1/2): reintroduces the self-report failure mode; ratings must
  be mechanical/objective.
- **Auto-write results straight into routing** — Rejected: couples the objective report to a routing
  side effect. Kept as an explicit `ingest()` call so the report is usable standalone.

## Consequences

- **Positive:** any model/system is evaluable with a detailed objective scorecard; rating dimensions
  and suites are pluggable; calibration now uses the same mechanical syntax oracle as production;
  routing profiles are fed from a defensible objective report; the framework is reusable outside
  conductor.
- **Negative:** more surface (a package vs one script); `cost_per_pass`/`latency` normalization uses
  configurable ceilings/budgets that need calibration to be meaningful (documented, audit-first); the
  CLI's cloud-provider (`openai_compat`) calling path is not yet wired into `model_call` (ollama +
  claude tiers work; the library accepts any caller, so it's a CLI-convenience gap, not a hard limit).
- **Neutral:** `capability_profiles.json` semantics unchanged (rolling-avg merge preserved via the
  ingest step calling `update_accuracy`); `resolve_sources` retained for backward-compat.

## Related

[ADR-0035](./0035-pluggable-language-adapters.md) (syntax oracle reused by SyntaxGrader),
[ADR-0021](./0021-pluggable-context-optimizer.md) (same registry-facade pattern),
[ADR-0006](./0006-tiered-maker-pool-bounded-escalation.md)/[0015](./0015-deterministic-routing-supersedes-binary-route.md)
(capability profiles the ingest feeds), [ADR-0039](./0039-adaptive-confidence-scored-routing.md)
(ConfidenceStore seeded by ingest), [ADR-0026](./0026-held-out-acceptance-oracle.md) (OracleGrader
mirrors the held-out-oracle idea). REQ-EVAL1/2/3.
