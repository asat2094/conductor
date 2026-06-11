# Conductor Distributed Build — Design

**Version:** 2.0.0
**Status:** Proposed
**Date:** 2026-06-09
**Derives from:** [requirements.md](./requirements.md) · **Decisions:** [../../adr/](../../adr/) · **Schemas:** [./schemas/](./schemas/) · **Tasks:** [tasks.md](./tasks.md) · **Traceability:** [../../traceability.md](../../traceability.md)

This is the **design layer** (the *how* + tunable values). The *why* + rejected alternatives live in ADRs; the *what* (testable requirements) lives in `requirements.md`. This v2 supersedes `docs/superpowers/specs/2026-06-09-conductor-distributed-build-design.md` (kept for history) and the routing/rate-limit decisions of `2026-05-29-multi-provider-harness-design.md` (Superseded by [ADR-0014](../../adr/0014-admission-separate-from-routing.md)/[0015](../../adr/0015-deterministic-routing-supersedes-binary-route.md)).

> **v1 scope: Python repositories only** (NFR-SCOPE-1). The gate engine uses Python `ast` + `pytest`; non-`.py` files do **not** get a silent free pass — they are out of scope and fail closed. Per-language adapters are future work.

---

## 1. Architecture

```
ORCHESTRATOR  (Claude main thread — host harness in phase 2)
   intent → decompose → contracts → CHECK verdicts → merge        ADR-0001
   LEAN: never loads file bodies (REQ-O1); its OWN outputs are gated (REQ-O2/O3)
        │
        ▼
DECOMPOSE  (HARD-GATE)                        decompose.py, dag.py, lint_plan.py
   codegraphcontext MCP deps + orchestrator logical_deps[] → producer→consumer DAG
   IF no codegraph → logical_deps-only → single-unit no-decompose (REQ-D4 degrade)
   emits SubtaskBrief JSON (schemas/subtask_brief) · lint_plan symbol/placeholder check
   ORCHESTRATOR-OUTPUT GATE (REQ-O2/O3): RED-validate orchestrator acceptance tests
     vs HEAD; 2nd-model review of DAG/contracts on high-stakes units
   → strategic-compact: file bodies leave orchestrator context  (TOKEN SAVE)  ADR-0011
        │ SubtaskBrief DAG (topo waves, file-overlap aware)
        ▼
ROUTER                                        router.py
   1. COST-SKIP → tiny/uneconomic? → AgentType.CLAUDE_INLINE      ADR-0016
   2. SENSITIVITY hard-rule → high? local/Claude only             ADR-0017
   3. capability×cost rank (pinned profile snapshot + seed)        ADR-0015
   4. cold-start: tier-prior + calibrated uncertainty (no 1.0)
        ▼
ADMISSION  (separate; live state lives here)  admission.py        ADR-0014
   per-provider AIMD limiter + token bucket + circuit breaker
   _RETRYABLE_ERRORS allowlist (429/timeout/5xx → retry SAME maker)
   per-run cost ceiling → block/queue, not balloon
        ▼
MAKER POOL  (tiered, worktree-isolated)       workspace.py        ADR-0006/0013
   tier0 gemma4 local $0 · tier1 free cloud $0 · tier2 Claude subagent
   author separation: test_author ≠ impl_author (REQ-T2)          ADR-0007
   escalate 0→1→2; never straight to main
        │ envelope (schemas/maker_envelope) — health signal only, NOT gate evidence
        ▼
GATES  — 100% mechanical, no model in hot path  evaluator.py      ADR-0002/0003
   functional:  RED (assertion-cause, true-fail)                  ADR-0008 REQ-T1
              → GREEN (re-run unit test + FULL suite)              ADR-0009 REQ-T3
              → MUTATION adequacy (post-GREEN, equiv-suppressed)   ADR-0008 REQ-T4
              → REFACTOR beat (restructure while green)            REQ-T5
              → CONTRACT (AST sig diff + Pact-lite examples)       ADR-0012 REQ-I1
   non-func:   CHARACTERIZATION (property-driven golden) + CONTRACT ADR-0010 REQ-T6
   confidence 0–1 → ≥ 0.95 auto-accept · < 0.95 escalate · hard-fail = reject
   verdict (schemas/checker_verdict): accept | escalate | intervene
        │ pass → MERGE QUEUE (single-writer): rebase + full suite  merge_queue.py
        │ ASSEMBLY golden over coupled units                       ADR-0004/0010
        │ DAG-ATOMIC: integration branch disposable; ff to target only on whole-DAG green
        │ fail → HEAL A(reprompt)→B(next maker)→C(tier2) → INTERVENE/main
        ▼
LEDGER                                        session_stats.py    ADR-0015
   run-ledger (routing, fallback, snapshot-hash, seed, verdicts)  REQ-OBS2
   regression ledger (REQ-OBS3) · exposure audit (ADR-0017) · cost-per-success KPI
   periodic higher-capability RANDOM AUDIT (REQ-OBS4)             ADR-0004
COMPRESSION OVERLAY (cross-cutting, prose-only)  compress.py      ADR-0019
   (a) orchestrator output mode  (b) caveman-compress prose artifacts  (c) terse paid briefs/verdicts
```

## 2. Maker contract

See [schemas/maker_envelope.schema.json](./schemas/maker_envelope.schema.json). Identity: tiered (ADR-0006), `test_author ≠ impl_author` (ADR-0007). Input: exactly one `SubtaskBrief`, bounded. Isolation: own git worktree, id-derived path, env-injected port/DB/tmpdir (ADR-0013). Output: envelope + files on disk. **Trust: none — envelope/heartbeat are health signals only (ADR-0002).** Failure: retryable → admission retries same maker; quality miss → heal A→B→C.

## 3. Checker contract

External mechanical referee = gate engine + orchestrator CHECK. Reads the **written file (AST-parsed)**, the test, `contracts.json`, golden snapshots, full-suite result — **never** the maker self-report (ADR-0002). Gate sequence by task class is in the architecture block. Decision: per-gate pass/fail + 0–1 confidence; **≥ 0.95 auto-accept** (orchestrator reads nothing), **< 0.95 escalate**, hard-fail = unconditional reject; **INTERVENE** on blind-spot signal (ADR-0004). Output: lean verdict ([schemas/checker_verdict.schema.json](./schemas/checker_verdict.schema.json)) — never file bodies.

## 4. Lifecycle (with the orchestrator-output gate)

```
1 INTENT      orchestrator receives a dev task
2 DECOMPOSE   codegraph + logical_deps → DAG → SubtaskBriefs (HARD-GATE, lint_plan)
  2a ORCH-GATE RED-validate orchestrator acceptance tests vs HEAD; 2nd-model DAG/contract review (REQ-O2/O3)
3 CONTRACT    functional → unit test (maker_A) | non-func → characterization criteria
  3a RED GATE  test fails NOW for an assertion cause matching the brief (REQ-T1); pin test id+cause (REQ-T8)
4 DISPATCH    maker_B (≠A) writes impl; one-per-maker; worktree-isolated
  4a GREEN     re-run unit test + FULL suite (REQ-T3); assert pinned RED test flipped, unmodified
  4b MUTATION  post-GREEN adequacy, equivalent-suppressed (REQ-T4)
  4c REFACTOR  optional restructure while suite stays green; record debt delta (REQ-T5)
5 CHECK       orchestrator reads failures/escalations only; trusts mechanical accept
6 HEAL        fail → reprompt(A) → next maker(B) → tier2(C) → INTERVENE/main
7 INTEGRATE   single-writer merge queue: rebase + full suite; ASSEMBLY golden;
              DAG-atomic: ff to target only on whole-DAG green, else discard integration branch
```

## 5. Tunable values (NOT in ADRs — live here / in config)

| Tunable | v1 default | Owner | Calibrated by |
|---|---|---|---|
| accept confidence threshold | 0.95 | evaluator | bench + audit (REQ-C3) |
| mutation kill-rate threshold | 0.80 non-equivalent | evaluator per task_type | bench |
| `min_delegation_tokens` (cost-skip) | TBD-calibrate | router | cost model (see §7) |
| concurrency `pool_size` | ≤ 8 | dispatcher | NFR-PERF-2 |
| stall = heartbeat gap | > 2× stage budget | heartbeat | NFR-PERF-1 |
| random-audit rate | ≥ 5% | ledger | REQ-OBS4 |
| evaluator axis weights | superseded by gated confidence (not additive) | evaluator | — |

## 6. Build order (re-sequenced — fixes the unbuildable spine; was B1)

```
S5 → S12 → S9 → S2 → S3 → S11 → S1 → S4 → S8 → S10 → S13 → S7 → S6
```
Rationale for the change: S2 (mutation RED adequacy) cannot run before its prerequisites exist — it needs S12 (briefs define the impl region + author roles) and S8 (worktrees to mutate-and-run in isolation). S5 stays first (ROI meta-gate). **S14 (caveman compression) is a cross-cutting overlay** — layer (a) output mode is on from day one; (b)/(c) attach as their artifacts appear. **S13 is descoped in v1 to wall-clock stall detection only** (single-shot REST makers have no mid-flight state); full checkpoint corroboration is gated on the phase-2 ACP adapter (ADR-0018).

### New / extended components
**New:** `decompose.py`, `dag.py`, `lint_plan.py`, `verify.py` (REQ-D6/D7/D8 — codegraph-backed decomposition verifier; advisory, degrade-clean, separate from pure `decompose()` per ADR-0022), `contracts.json` (+ schema), `characterize.sh` + `golden/`, `workspace.py`, `merge_queue.py`, `admission.py`, `retrieve.py`, `baseline.json`, `prompts/spec_auditor.txt`, `heartbeat.py` (stall-only v1), `optimizer/` (pluggable facade, ADR-0021), `orchestrator_gate.py` (REQ-O2/O3), `codegraph_adapter.py` (codegraphcontext MCP + fallback).

> **Decomposition verifier (ADR-0022, resolves L1/L3/L4 of the decomposer's honest limits):** `verify.py` cross-checks declared contracts against codegraph ground truth — under/over-declared edges, dangling-against-real-repo, coverage %, and an advisory density/decomposability signal. It is a **separate advisory layer**: `decompose()` stays pure; the verifier annotates, never mutates; ERROR only on high-confidence; degrades to an explicit `unverified` status when codegraph is absent (preserving REQ-D4/NFR-REPRO-1). It is **bounded by static-analysis accuracy** — dynamic/reflective coupling escapes it (see §7 residuals).
**New (tracker):** `tracker/` — event-sourced development board (ADR-0023, REQ-OBS5/6/7): `state.py` (UnitState lifecycle + declarative transitions + Board projection), `events.py`, `store.py` (append-only over the run-ledger, out-of-worktree), `render/{text,json}.py` baked in + opt-in `rich_tui`/`mcp`/`webhook`/external-PM-bridge sinks. Harness-derived (NFR-TRACK-1), reports-never-gates. Prior art (vibe-kanban / Hermes board / agent-kanban / KaibanJS) was evaluated and rejected as a dependency — patterns borrowed, core built portable.

**Extended:** `evaluator.py` (RED/GREEN/MUTATION/REFACTOR/CONTRACT/CHARACTERIZATION/ASSEMBLY modes, 0–1 confidence, 100% coverage, self-report downweighted); `router.py` (cost-skip → CLAUDE_INLINE, sensitivity rule, tier-prior cold-start, pinned snapshot+seed, fallback ladder); `session_stats.py` (run-ledger, regression ledger, exposure audit, cost_usd + budget, cost-per-success KPI); `gemma4_call.py`/`provider_call.py` (structured envelope + `_RETRYABLE_ERRORS`); `models.py` (TaskType += refactor/signature_change/perf; AgentType += CLAUDE_INLINE; SubTask += produces/consumes/logical_deps/sensitivity/writes_files); `bench.py` (un-hardcode foreign paths; add the 3 new task types so S9 cold-start can seed — was C2).

## 7. Known calibration debts (must close before the dependent step ships)
- **Cost model (C2/M2):** `providers.json` lists all providers at `cost_per_1k = 0.0` and `session_stats` uses a flat display anchor. S5's cost-skip and the cost ceiling need real per-stage token/$ estimates before they can gate. Calibrate from the run-ledger after a warm-up.
- **0.95 threshold:** aggregation across heterogeneous sub-gates + the 0.95 boundary must be validated against the bench/regression ledger, not assumed.
- **bench.py:** currently hardcodes a foreign machine's paths and only 3 task types → its `baseline.json` is non-runnable here and cannot seed the new task types. Fixing bench is a prerequisite of S9.
- **Decomposition verifier residual (ADR-0022):** `verify.py` is bounded by static-analysis accuracy. Dynamic dispatch, reflection, monkeypatching, and string-based imports produce coupling codegraph cannot see → a wrong-grouping can still pass the verifier. Recorded deliberately to keep trust calibrated: the verifier *reduces* L1/L3/L4, it does not *close* them; the assembly golden gate (ADR-0004) remains the empirical backstop. The **wave-incremental** scheme (REQ-D9) removes the block-vs-warn tuning knob (confidence is phase-derived: advisory at decompose, gating at each wave boundary against real gated code) — but it adds **per-wave codegraph re-index cost/latency + state** (mitigate: incremental re-index of changed files only), and **same-wave coupling** is only detectable post-wave (triggers a wave re-split), not pre-dispatch.

## 8. Test plan
Mirrors `requirements.md` §5 traceability. Per-component tests: `test_decomposer`, `test_lint_plan`, `test_orchestrator_gate` (RED-validate + review), `test_author_separation`, `test_red_gate` (assertion-cause; reject import/collection RED), `test_green_gate` (full-suite, immutability), `test_mutation` (equiv-suppression), `test_characterization` (property inputs), `test_contract` (AST diff + Pact-lite), `test_merge_queue` (DAG atomicity/rollback), `test_router` (cost-skip, cold-start no-1.0, sensitivity), `test_admission`, `test_heartbeat` (stall-only), `test_compress` (prose-only guard). **Migration (NFR-MIG-1, was H4):** legacy `route()` 1.0-default tests and additive-evaluator tests are *migrated*, not preserved — "keep green" applies only to unaffected tests.

## 9. Out of scope (v1)
Non-Python languages; phase-2 host-harness MCP extension + ACP maker adapter (ADR-0020); streaming/multi-turn makers; full mid-flight heartbeat corroboration (ADR-0018).
