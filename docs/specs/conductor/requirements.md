# Conductor Distributed Build — Requirements

**Version:** 1.0.0
**Status:** Proposed — single source of truth for the distributed-build feature
**Date:** 2026-06-09
**Design:** [design.md](./design.md) · **Tasks:** [tasks.md](./tasks.md) · **Traceability:** [../../traceability.md](../../traceability.md) · **ADRs:** [../../adr/](../../adr/)

This document is the **source of truth**. Design, tasks, and code derive from it; a change to any `REQ-*` must ripple to its design section, tasks, and verifying tests before merge. Requirements use **EARS** notation (Easy Approach to Requirements Syntax): `WHEN <trigger> THE SYSTEM SHALL <response>`, `WHILE <state> …`, `IF <condition> THEN …`, or ubiquitous `THE SYSTEM SHALL …`.

---

## 1. Scope & vision

Conductor lets a lean **orchestrator** (Claude main thread, or a host harness in phase 2) decompose a dev task, delegate bounded units to a heterogeneous **maker pool** (free local/cloud models + bounded Claude subagents), and accept work only through **mechanical gates** — keeping bulk file content out of the orchestrator's context. Goals, in priority order under conflict: **correctness ≥ accuracy > efficiency > cost**, with **accuracy + throughput** chosen over maker equi-utilization (see [ADR-0005](../../adr/0005-accuracy-throughput-over-equi-utilization.md)).

### 1.1 In scope (v1)
- Python repositories only (see NFR-SCOPE-1).
- The correctness spine: decomposition, TDD gates, author separation, mechanical checking, routing, admission, merge/atomicity, observability, compression overlay.

### 1.2 Out of scope (v1)
- Non-Python languages (gate adapters deferred).
- Phase-2 host-harness extension (OpenClaw/Hermes MCP surface, ACP maker adapter).
- Streaming / multi-turn maker conversations, provider-specific prompt tuning.

---

## 2. Functional requirements (EARS)

### Orchestrator (lean checker)
- **REQ-O1** — THE SYSTEM SHALL ensure the orchestrator's context never receives a maker-produced file body; the orchestrator reads only briefs, contracts, and lean verdicts.
- **REQ-O2** *(B3)* — WHEN the orchestrator authors acceptance/assembly tests, THE SYSTEM SHALL RED-validate them against current HEAD (assert they fail before any unit runs) before they are trusted.
- **REQ-O3** *(B3)* — WHEN the orchestrator emits a decomposition DAG or a unit contract, THE SYSTEM SHALL obtain an independent second-model review of that DAG/contract before dispatch on high-stakes units (stakes defined in NFR-SEC-1 / measurable targets).

### Decomposition
- **REQ-D1** — WHEN a task enters DECOMPOSE, THE SYSTEM SHALL build a producer→consumer DAG from codegraph structural deps plus orchestrator-declared `logical_deps[]`; two units sharing a declared symbol SHALL be treated as coupled even without a structural edge.
- **REQ-D2** — THE SYSTEM SHALL emit one self-contained `SubtaskBrief` per unit (schema: [schemas/subtask_brief.schema.json](./schemas/subtask_brief.schema.json)); a unit whose brief cannot be made self-contained within the size bound SHALL be recursed (if large) or routed inline (if small).
- **REQ-D3** — WHEN briefs are produced, THE SYSTEM SHALL run `lint_plan` to cross-reference every consumed symbol against an upstream producer/contract declaration and SHALL reject on dangling symbols or placeholders before dispatch.
- **REQ-D4** *(B2)* — THE SYSTEM SHALL source codegraph from the codegraphcontext MCP; IF codegraph is unavailable or returns no edges THEN THE SYSTEM SHALL fall back to `logical_deps[]`-only coupling, and IF neither is available THEN to a single-unit no-decompose pass, logging the degrade.
- **REQ-D5** — DECOMPOSE SHALL be a HARD-GATE phase: no unit dispatches until briefs are produced, `lint_plan`-clean, and the phase-boundary compaction has dropped read file bodies from orchestrator context.
- **REQ-D6** *(verifier, L1/L3)* — WHEN codegraph edges are available, THE SYSTEM SHALL cross-check declared contracts against them and SHALL flag an **under-declared dependency** (a unit referencing a symbol owned by another unit with no declared `consumes`/edge) as an ERROR only when high-confidence, otherwise a warning; and SHALL flag a `consumes` of an existing symbol codegraph reports absent as an ERROR.
- **REQ-D7** *(verifier coverage, L4)* — THE SYSTEM SHALL report an **over-declared** `consumes` (declared but never referenced) as a warning and SHALL emit a coverage metric (`% of declared edges corroborated by codegraph`) plus the list of unverifiable units.
- **REQ-D8** *(decomposability signal, L2)* — THE SYSTEM SHALL emit an **advisory** decomposability signal when the dependency graph is near-complete / collapses to one densely-coupled blob ("prefer inline/interactive"); this signal SHALL NOT auto-route — it informs, the orchestrator decides.
- **REQ-D9** *(wave-incremental verification)* — verifier confidence rises as waves complete: at decompose time, checks on not-yet-written in-DAG `produces` SHALL be **advisory**; AFTER each wave passes GREEN, THE SYSTEM SHALL re-index codegraph (incrementally) and re-verify the next wave's `consumes` against the **actually-produced, gated** symbols — at this boundary the check is high-confidence and SHALL **gate** (block/re-derive the affected unit; re-split the wave on a discovered same-wave coupling). Existing-repo-symbol dangling MAY gate even at decompose time. This is the resolution of "ERROR only when high-confidence" — confidence is phase-derived, not a tunable.

### TDD gates
- **REQ-T1** *(true RED)* — WHEN a unit test is authored, THE SYSTEM SHALL run it against current code and accept RED only IF the failure is an **assertion** failure whose captured cause matches the brief's declared expected behavior; import/collection/syntax errors SHALL be rejected as invalid RED.
- **REQ-T2** *(author separation)* — THE SYSTEM SHALL enforce `test_author ≠ impl_author` for the same unit and SHALL exclude the test author from impl routing for that unit.
- **REQ-T3** *(GREEN)* — WHEN impl is submitted, THE SYSTEM SHALL independently re-run the unit test AND the full suite (never the maker's self-report) and SHALL accept only on both green.
- **REQ-T4** *(mutation adequacy, post-GREEN)* — AFTER GREEN, THE SYSTEM SHALL run mutation adequacy over the impl region using behavior-bearing operators, SHALL suppress equivalent mutants from the denominator, and SHALL reject the unit IF kill-rate < the per-task-type threshold.
- **REQ-T5** *(REFACTOR)* — AFTER GREEN, THE SYSTEM SHALL permit a refactor beat in which structure may change WHILE the unit test + full suite stay green, and SHALL record that the refactor preserved green in the ledger; a design-debt delta (complexity/duplication) SHALL be recorded as an advisory signal.
- **REQ-T6** *(generative goldens)* — WHEN a non-functional unit (refactor/rename/perf) is gated, THE SYSTEM SHALL drive characterization with property-based generated inputs under a pinned seed and SHALL diff before/after over that input space, not over fixed seed inputs alone.
- **REQ-T7** *(behavior binding)* — THE SYSTEM SHALL flag a unit test whose assertions reference symbols outside the unit's contract `produces`/`consumes` surface as implementation-coupled (advisory by default; gating for high-sensitivity units).
- **REQ-T8** *(test immutability across RED→GREEN)* — THE SYSTEM SHALL pin the RED test's identity and cause hash and SHALL reject at GREEN IF that exact test was modified between RED and GREEN.

### Checker (mechanical referee)
- **REQ-C1** *(Law 1)* — THE SYSTEM SHALL derive all gate evidence from harness-side artifacts (AST parse of the written file, independent re-run); it SHALL NOT use any maker self-reported `output`/envelope/heartbeat field as gate evidence.
- **REQ-C2** *(Law 2)* — THE SYSTEM SHALL run deterministic gates on 100% of units and SHALL invoke a model-based check only WHEN aggregate mechanical confidence is below the accept threshold.
- **REQ-C3** — THE SYSTEM SHALL compute a 0–1 confidence per unit; WHEN confidence ≥ the accept threshold AND no gate hard-failed THEN auto-accept (orchestrator reads nothing); ELSE escalate. A gate hard-fail SHALL reject unconditionally regardless of confidence.
- **REQ-C4** *(Law 3 / INTERVENE)* — WHEN a blind-spot signal fires (audit catch, or a high-stakes unit that could not be staffed with cross-family-diverse makers), THE SYSTEM SHALL raise INTERVENE and the orchestrator SHALL take control of the unit (tier2 re-derive or inline). Accuracy/correctness outrank cost in this regime.

### Routing
- **REQ-R1** *(S5 cost-skip)* — WHEN projected delegation cost ≥ inline-Claude cost OR estimated tokens < `min_delegation_tokens`, THE SYSTEM SHALL route the unit to `CLAUDE_INLINE` and skip the pipeline.
- **REQ-R2** *(S9 cold-start)* — THE SYSTEM SHALL NOT default an untracked `(provider, task_type)` cell to accuracy 1.0; it SHALL use a tier-prior with calibrated uncertainty seeded from the bench baseline, preferring Claude/verification while uncertainty is wide.
- **REQ-R3** *(S10 determinism)* — THE SYSTEM SHALL make a routing decision a pure function of `(features, pinned profile snapshot, seed)`; live availability/rate-limit state SHALL live in the admission layer and SHALL NOT alter the recorded routing decision.
- **REQ-R4** *(S6 sensitivity)* — WHEN a file is tagged `sensitivity=high`, THE SYSTEM SHALL NOT transmit its bytes to any tier1 free-cloud maker; it SHALL route only to local or Claude makers.

### Admission (separate from routing)
- **REQ-A1** *(S7)* — THE SYSTEM SHALL wrap each provider in an adaptive concurrency limiter that multiplicatively reduces in-flight cap on observed throttle, instead of escalating the batch.
- **REQ-A2** — WHEN a maker call fails with a retryable error (429/timeout/5xx), THE SYSTEM SHALL retry the SAME maker with backoff; only a quality-gate miss or exhausted retries SHALL escalate.
- **REQ-A3** — THE SYSTEM SHALL enforce a per-run cost ceiling; WHEN reached THE SYSTEM SHALL block/queue rather than continue escalating to paid makers.

### Integration & atomicity
- **REQ-I1** *(S4)* — WHEN a unit reaches GREEN, THE SYSTEM SHALL rebase it onto an integration branch in a single-writer merge queue and re-run the full suite; seam conformance SHALL be checked via AST-extracted signatures vs `contracts.json`, never the maker envelope.
- **REQ-I2** *(B-atomicity)* — THE SYSTEM SHALL treat the build as atomic at the DAG level: the integration branch is disposable and SHALL be fast-forwarded to the target branch only after the whole-DAG assembly golden gate passes; a permanent unit failure SHALL abort the build and discard the integration branch.
- **REQ-I3** *(contracts ownership)* — `contracts.json` SHALL be orchestrator-owned, frozen at decompose time, and read-only to makers; no unit SHALL write it concurrently.
- **REQ-I4** *(assembly)* — WHEN coupled units merge, THE SYSTEM SHALL run an assembly golden gate (property-driven where applicable) over the merged surface.

### Observability
- **REQ-OBS1** *(S13, scoped)* — THE SYSTEM SHALL detect a stalled unit via wall-clock heartbeat gap and SHALL early-kill it. *Mid-flight in-file corroboration requires an agentic/streaming maker and is deferred to the phase-2 ACP adapter (see [ADR-0018](../../adr/0018-segmented-heartbeat.md)).*
- **REQ-OBS2** *(S10)* — THE SYSTEM SHALL record a run-ledger row per unit: routing decision, chosen+fallback maker, profile-snapshot hash, seed, RED/GREEN/mutation verdicts.
- **REQ-OBS3** *(S9)* — WHEN a heal fails, THE SYSTEM SHALL write a regression-ledger entry `(provider, task_type, failure_category, repro)` and SHALL inject the stored repro as an extra gate on the next matching unit.
- **REQ-OBS4** *(Law 3)* — THE SYSTEM SHALL audit a random sample (≥ the target rate, NFR/targets) of auto-accepted units with a higher-capability model as the correlated-blind-spot backstop.
- **REQ-OBS5** *(tracker, dual audience)* — THE SYSTEM SHALL maintain a development board as a pure projection over an append-only event log: a human program-manager view via `render("text"|"json")` and an orchestrator system-leader view via `board()` returning the compact current state (waves done/in-flight/blocked/failed, per-unit `UnitState`, owning maker, attempts). The orchestrator SHALL track via the board, not by re-reading agent transcripts.
- **REQ-OBS6** *(pluggable render sinks)* — THE SYSTEM SHALL render the board through pluggable sinks: `text` + `json` baked in (zero deps); `rich`/`textual` TUI, an MCP resource, a webhook, and an external-PM-board bridge (e.g. Obsidian/Trello/Hermes-board) SHALL be opt-in sinks subscribing to the event stream — external tools are downstream views, never the engine.
- **REQ-OBS7** *(per-attempt run records)* — WHEN a unit is healed or escalated, THE SYSTEM SHALL append a distinct run record (attempt n, maker, outcome, summary) rather than overwriting status, preserving attempt history.

### Efficiency / compression (overlay)
- **REQ-E1** *(S14a)* — THE SYSTEM SHALL support a caveman output mode for orchestrator replies (output-token reduction; reasoning untouched).
- **REQ-E2** *(S14b)* — THE SYSTEM SHALL support `caveman-compress` on repeatedly-read prose artifacts, with deterministic validation that code, URLs, paths, and headings are byte-preserved.
- **REQ-E3** *(S14, guard)* — THE SYSTEM SHALL NOT submit code, tests, `context_slices`, contract structured fields, or any gate-parsed evidence to compression; and SHALL refuse sensitive paths (.env/.ssh/.aws…).

---

## 3. Non-functional requirements

- **NFR-SCOPE-1** — THE SYSTEM SHALL operate on Python repositories only in v1; non-`.py` files SHALL NOT pass the syntax/contract gates by default (no silent free pass). Per-language adapters are a future requirement.
- **NFR-PERF-1** *(latency)* — Each gate stage SHALL declare a latency budget; WHEN a unit exceeds its budget without a heartbeat THE SYSTEM SHALL mark it stalled (REQ-OBS1).
- **NFR-PERF-2** *(throughput)* — THE SYSTEM SHALL cap concurrent makers at a configured `pool_size` (default ≤ 8) and SHALL co-dispatch only units with disjoint `writes_files`.
- **NFR-SEC-1** *(data boundary)* — A unit is "high-stakes" IF it touches `sensitivity=high` files OR ≥ N coupled units OR a seam contract; high-stakes units trigger REQ-O3 review and REQ-C4 eligibility.
- **NFR-REPRO-1** — Routing decisions and gate verdicts SHALL be replayable from the run-ledger; maker LLM sampling is acknowledged non-deterministic and out of replay scope.
- **NFR-MIG-1** *(H4)* — Existing tests that assert superseded behavior (legacy `route()` 1.0 default; additive 25/35/20/20 evaluator axes) SHALL be explicitly migrated, not preserved; "keep green" applies only to unaffected tests.
- **NFR-TRACK-1** *(tracker harness-derived, reports-not-gates)* — Board progress SHALL be derived from harness-observed events (dispatch happened, gate passed), NOT from maker self-report; `self_on_track` heartbeat SHALL be shown only as an unverified liveness hint. The tracker SHALL be observability-only — it SHALL NOT influence any gating/routing decision. It SHALL be a separable layer that does not alter `decompose()` or the gate engine.
- **NFR-VERIFY-1** *(verifier stays advisory)* — The decomposition verifier (REQ-D6/D7/D8) SHALL be a separate layer that never mutates the DAG and never becomes a hard requirement: `decompose()` SHALL remain pure/deterministic given briefs; WHEN codegraph is absent or errors THE SYSTEM SHALL emit an explicit `unverified` status and proceed on the lint-only gate (preserving REQ-D4 and NFR-REPRO-1). The verifier is bounded by static-analysis accuracy — dynamic/reflective coupling it cannot see remains a recorded residual, not a closed gap.

---

## 4. Measurable success criteria (falsifiable targets)

Targets are validated on the bench suite + run-ledger. Numbers are v1 baselines, tuned post-pilot.

| KPI | Target | Measured by |
|---|---|---|
| **Token reduction** vs inline-Claude baseline | ≥ 50% input tokens on bench tasks above `min_delegation_tokens` | run-ledger token accounting |
| **False-accept rate** (wrong-but-green caught by Opus audit) | ≤ 2% of auto-accepted units | REQ-OBS4 audit sample |
| **Per-task-type maker accuracy** before a maker is trusted (not Claude-verified) | ≥ 70% | capability profiles + bench |
| **Cost-per-successful-task** | ≤ inline-Claude cost for the same task class | session_stats KPI |
| **Mutation kill-rate** threshold (per task type) | ≥ 0.80 non-equivalent mutants killed | REQ-T4 |
| **Accept confidence threshold** | 0.95 (calibrated; see [ADR-0003](../../adr/0003-mechanical-first-model-last.md)) | REQ-C3 |
| **Audit coverage** | ≥ 5% of auto-accepted units sampled | REQ-OBS4 |
| **Stall detection** | heartbeat gap > 2× stage latency budget | REQ-OBS1 |

---

## 5. Traceability

Every `REQ-*` maps forward to ≥1 verifying test and back from ≥1 design component in [../../traceability.md](../../traceability.md). A requirement with no test is a coverage gap; a component with no requirement is gold-plating — both are flagged there.
