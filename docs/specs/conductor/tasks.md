# Conductor Distributed Build — Tasks

**Version:** 1.0.0 · **Date:** 2026-06-09
**Derives from:** [requirements.md](./requirements.md) · [design.md](./design.md)

Atomic, independently reviewable/revertible tasks in the corrected build order (design §6). Each task names the requirement(s) it closes and the verifying test. A task is done only when its test is green and its REQ row in [../../traceability.md](../../traceability.md) resolves. **Phase 0 is a prerequisite gate — calibration debts (design §7) block dependent tasks.**

## Phase 0 — Prerequisites (unblock the spine)
- **T0.1** — Un-hardcode `bench.py` foreign paths; add task types `refactor`/`signature_change`/`perf`; emit `baseline.json` (pass@1/pass@3 per provider×task_type). → REQ-R2 (seed), C2 fix · test: `test_bench_baseline`
- **T0.2** — `codegraph_adapter.py`: wrap codegraphcontext MCP; define no-graph degrade (logical_deps-only → single-unit). → REQ-D4 · test: `test_codegraph_adapter` (incl. degrade path)
- **T0.3** — `models.py`: add `TaskType.{refactor,signature_change,perf}`, `AgentType.CLAUDE_INLINE`, `SubTask.{produces,consumes,logical_deps,sensitivity,writes_files}`; migrate dependent tests. → NFR-MIG-1 · test: `test_models`
- **T0.4** — Cost model: replace `0.0` provider costs + flat anchor with per-stage token/$ estimator skeleton fed by the ledger. → design §7 · test: `test_cost_model`

## S5 — Cost-skip meta-gate (ROI; first)
- **T5.1** — `router.py`: project full delegation cost vs inline; below `min_delegation_tokens` or delegation ≥ inline → `CLAUDE_INLINE`, skip pipeline. → REQ-R1, ADR-0016 · test: `test_router::test_cost_skip`
- **T5.2** — Demand-driven (ADaPT): decompose further only on failure. → REQ-R1 · test: `test_router::test_demand_driven`

## S12 — Hard-gate decomposition + briefs (+ orchestrator-output gate)
- **T12.1** — `decompose.py` + `dag.py`: producer→consumer DAG from codegraph + logical_deps; topo waves; file-overlap. → REQ-D1, ADR-0011 · test: `test_decomposer`
- **T12.2** — Emit `SubtaskBrief` JSON (validate against schema); phase-boundary compaction drops bodies. → REQ-D2/D5, REQ-O1 · test: `test_brief_schema`, `test_compaction`
- **T12.3** — `lint_plan.py`: consumed-symbol cross-ref + placeholder scan; reject on dangling. → REQ-D3 · test: `test_lint_plan`
- **T12.4** — `orchestrator_gate.py`: RED-validate orchestrator acceptance tests vs HEAD; 2nd-model DAG/contract review on high-stakes. → REQ-O2/O3 (B3) · test: `test_orchestrator_gate`

## S9 — Cold-start fix
- **T9.1** — `router.py`/`profiles.py`: replace untracked-cell `1.0` default with tier-prior + uncertainty seeded from `baseline.json`; prefer Claude while uncertain. → REQ-R2, ADR-0015 · test: `test_router::test_cold_start_no_1_0`
- **T9.2** — `session_stats.py`: regression ledger; inject stored repro as extra gate next match. → REQ-OBS3 · test: `test_regression_ledger`

## S2 — RED adequacy (true-RED + post-GREEN mutation) — needs S12 + S8
- **T2.1** — `evaluator.py` RED gate: assert test fails NOW for an assertion cause matching brief; reject import/collection/syntax RED; pin id+cause. → REQ-T1/T8, ADR-0008 · test: `test_red_gate`
- **T2.2** — Author separation enforcement (A≠B; exclude A from impl routing). → REQ-T2, ADR-0007 · test: `test_author_separation`
- **T2.3** — `evaluator.py` MUTATION (post-GREEN): behavior-bearing operators over impl region; equivalent-mutant suppression; per-type threshold. → REQ-T4 · test: `test_mutation`

## S3 — Non-functional characterization gate
- **T3.1** — `characterize.sh` + `golden/`: capture observable I/O; **property-based generated inputs under pinned seed**. → REQ-T6, ADR-0010 · test: `test_characterization`
- **T3.2** — `evaluator.py` CONTRACT/CHARACTERIZATION modes + tier→gate-profile table; compile-RED for rename; advisory perf band. → REQ-T6 · test: `test_characterization`, `test_contract`

## S11 — 100% mechanical gates + GREEN + REFACTOR
- **T11.1** — `evaluator.py` GREEN: independent re-run unit test + FULL suite; suite-determinism contract (random order+seed, quarantine, masking, re-run-once). → REQ-T3, ADR-0009 · test: `test_green_gate`
- **T11.2** — REFACTOR beat: restructure-while-green path; record debt delta advisory. → REQ-T5 · test: `test_refactor_beat`
- **T11.3** — Downweight maker `self_output` to ~0; 0–1 confidence stop-judger; behavior-binding flag (REQ-T7). → REQ-C1/C2/C3, REQ-T7 · test: `test_confidence`, `test_behavior_binding`
- **T11.4** — INTERVENE path + random Opus audit hook. → REQ-C4, REQ-OBS4, ADR-0004 · test: `test_intervene`, `test_audit`

## S1 — Logical-coupling DAG + assembly golden
- **T1.1** — Coupling: shared declared symbol ⇒ coupled even without structural edge. → REQ-D1, ADR-0011 · test: `test_decomposer::test_logical_coupling`
- **T1.2** — ASSEMBLY golden over merged coupled units (property-driven). → REQ-I4, ADR-0004 · test: `test_assembly`

## S4 — Contract conformance + merge queue + atomicity
- **T4.1** — `contracts.json` (schema-validated), orchestrator-owned, read-only to makers; AST-extracted signature conformance + Pact-lite examples. → REQ-I1/I3, ADR-0012 · test: `test_contract`
- **T4.2** — `merge_queue.py`: single-writer rebase + full suite; **DAG-atomic** (disposable integration branch, ff-on-whole-DAG-green, discard on permanent fail). → REQ-I1/I2 · test: `test_merge_queue`

## S8 — Worktree isolation
- **T8.1** — `workspace.py`: git-worktree-per-maker, id-derived path, env-injected port/DB/tmpdir; heal reuses unit worktree; teardown + crash-sweep. → ADR-0013, NFR-PERF-2 · test: `test_workspace`
- **T8.2** — Move `session_stats.db` out of the work tree. → ADR-0013 · test: `test_workspace::test_db_outside_tree`

## S10 — Deterministic routing + run-ledger
- **T10.1** — Routing = pure fn(features, pinned snapshot, seed); log snapshot hash + seed. → REQ-R3, ADR-0015 · test: `test_router::test_deterministic`
- **T10.2** — Run-ledger rows (routing/fallback/snapshot/seed/verdicts); replay. → REQ-OBS2 · test: `test_run_ledger`

## S13 — Heartbeat (stall-only v1)
- **T13.1** — `heartbeat.py`: wall-clock stall detection + early-kill (no mid-flight corroboration in v1). → REQ-OBS1, ADR-0018 · test: `test_heartbeat`

## S7 — Admission
- **T7.1** — `admission.py`: per-provider AIMD limiter + token bucket + circuit breaker. → REQ-A1, ADR-0014 · test: `test_admission`
- **T7.2** — `_RETRYABLE_ERRORS` allowlist (retry same maker); per-run cost ceiling block/queue. → REQ-A2/A3 · test: `test_admission::test_retry`, `test_admission::test_ceiling`

## S6 — Sensitivity / data boundary
- **T6.1** — `SubTask.sensitivity` + router hard-rule: high → local/Claude only. → REQ-R4, ADR-0017 · test: `test_router::test_sensitivity`
- **T6.2** — `retrieve.py` minimal-slice briefs; exposure audit; reuse caveman sensitive-path refusal. → REQ-R4, REQ-E3 · test: `test_retrieve`, `test_exposure_audit`

## S14 — Compression overlay (cross-cutting)
- **T14.1** — Orchestrator output mode (a). → REQ-E1, ADR-0019 · test: manual/eval
- **T14.2** — `compress.py`: wrap caveman-compress; **prose-only allowlist** hard-excludes code/tests/context_slices/contract fields; sensitive-path refuse; fail → uncompressed original. → REQ-E2/E3 · test: `test_compress`
