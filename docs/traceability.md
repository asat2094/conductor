# Conductor Distributed Build — Traceability Matrix

**Version:** 1.0.0 · **Date:** 2026-06-09
Binds every requirement to a design component, the ADR that justifies it, the task that builds it, and the test that verifies it. A REQ with no test = **coverage gap**; a component with no REQ = **gold-plating**. Both are flagged at the bottom.

Sources: [requirements.md](./specs/conductor/requirements.md) · [design.md](./specs/conductor/design.md) · [tasks.md](./specs/conductor/tasks.md) · [adr/](./adr/)

| REQ | Requirement (short) | Design component | ADR | Task | Verifying test |
|---|---|---|---|---|---|
| REQ-O1 | orchestrator never loads file bodies | DECOMPOSE compaction | 0001 | T12.2 | test_compaction |
| REQ-O2 | RED-validate orchestrator acceptance tests vs HEAD | orchestrator_gate.py | 0011 | T12.4 | test_orchestrator_gate |
| REQ-O3 | 2nd-model review of DAG/contracts (high-stakes) | orchestrator_gate.py | 0011 | T12.4 | test_orchestrator_gate |
| REQ-D1 | producer→consumer DAG (codegraph + logical_deps) | decompose.py, dag.py | 0011 | T12.1, T1.1 | test_decomposer |
| REQ-D2 | self-contained SubtaskBrief | decompose.py + schema | 0011 | T12.2 | test_brief_schema |
| REQ-D3 | lint_plan symbol/placeholder check | lint_plan.py | 0011 | T12.3 | test_lint_plan |
| REQ-D4 | codegraph source + degrade path | codegraph_adapter.py | 0011 | T0.2 | test_codegraph_adapter |
| REQ-D5 | DECOMPOSE is a hard gate | decompose.py | 0011 | T12.2 | test_compaction |
| REQ-D6 | verifier: under-declared edge + dangling-vs-repo | verify.py | 0022 | (Plan 4) | test_verify::under_declared |
| REQ-D7 | verifier: over-declared warning + coverage | verify.py | 0022 | (Plan 4) | test_verify::coverage |
| REQ-D8 | advisory decomposability/density signal | verify.py | 0022 | (Plan 4) | test_verify::density |
| REQ-D9 | wave-incremental verify (advisory→gating per wave) | verify.py + pipeline | 0022 | (Pipeline plan) | test_verify::wave_incremental |
| NFR-VERIFY-1 | verifier advisory, degrade-clean, decompose() pure | verify.py | 0022 | (Plan 4) | test_verify::degrade_clean |
| REQ-T1 | true RED (assertion cause, not import error) | evaluator RED | 0008 | T2.1 | test_red_gate |
| REQ-T2 | author separation A≠B | dispatcher | 0007 | T2.2 | test_author_separation |
| REQ-T3 | GREEN re-run unit + full suite | evaluator GREEN | 0009 | T11.1 | test_green_gate |
| REQ-T4 | post-GREEN mutation, equiv-suppressed | evaluator MUTATION | 0008 | T2.3 | test_mutation |
| REQ-T5 | REFACTOR beat | evaluator REFACTOR | 0008/0009 | T11.2 | test_refactor_beat |
| REQ-T6 | property-driven characterization | characterize.sh, evaluator | 0010 | T3.1, T3.2 | test_characterization |
| REQ-T7 | behavior-binding (assert on contract surface) | evaluator | 0008 | T11.3 | test_behavior_binding |
| REQ-T8 | RED test immutable across RED→GREEN | evaluator | 0008/0009 | T2.1, T11.1 | test_green_gate |
| REQ-C1 | no maker self-report as evidence | evaluator | 0002 | T11.3 | test_confidence |
| REQ-C2 | mechanical gates 100%, model-last | evaluator | 0003 | T11.3 | test_confidence |
| REQ-C3 | confidence ≥0.95 accept / hard-fail reject | evaluator stop-judger | 0003 | T11.3 | test_confidence |
| REQ-C4 | INTERVENE on blind-spot signal | checker + orchestrator | 0004 | T11.4 | test_intervene |
| REQ-R1 | cost-skip → CLAUDE_INLINE | router.py | 0016 | T5.1, T5.2 | test_router::test_cost_skip |
| REQ-R2 | cold-start no 1.0 default | router.py, profiles.py | 0015 | T9.1 | test_router::test_cold_start_no_1_0 |
| REQ-R3 | deterministic routing (pinned snapshot+seed) | router.py | 0015 | T10.1 | test_router::test_deterministic |
| REQ-R4 | sensitivity hard-rule | router.py | 0017 | T6.1 | test_router::test_sensitivity |
| REQ-A1 | AIMD concurrency limiter | admission.py | 0014 | T7.1 | test_admission |
| REQ-A2 | retryable-error allowlist (retry same maker) | admission.py | 0014 | T7.2 | test_admission::test_retry |
| REQ-A3 | per-run cost ceiling | admission.py | 0014 | T7.2 | test_admission::test_ceiling |
| REQ-I1 | merge-queue full suite + AST contract conformance | merge_queue.py, contracts | 0012 | T4.1, T4.2 | test_contract, test_merge_queue |
| REQ-I2 | DAG-level atomicity / rollback | merge_queue.py | 0012 | T4.2 | test_merge_queue |
| REQ-I3 | contracts.json orchestrator-owned, read-only | contracts.json + schema | 0012 | T4.1 | test_contract |
| REQ-I4 | assembly golden over coupled units | evaluator ASSEMBLY | 0004/0010 | T1.2 | test_assembly |
| REQ-OBS1 | wall-clock stall detection (v1) | heartbeat.py | 0018 | T13.1 | test_heartbeat |
| REQ-OBS2 | run-ledger replay | session_stats.py | 0015 | T10.2 | test_run_ledger |
| REQ-OBS3 | regression ledger + repro injection | session_stats.py | 0008 | T9.2 | test_regression_ledger |
| REQ-OBS4 | random higher-capability audit | ledger + audit hook | 0004 | T11.4 | test_audit |
| REQ-OBS5 | dual-audience live board (projection) | tracker/state.py | 0023 | (Plan T) | test_tracker::board |
| REQ-OBS6 | pluggable render sinks | tracker/render/* | 0023 | (Plan T) | test_tracker::sinks |
| REQ-OBS7 | per-attempt run records | tracker/store.py | 0023 | (Plan T) | test_tracker::run_records |
| NFR-TRACK-1 | harness-derived, reports-not-gates | tracker/* | 0023 | (Plan T) | test_tracker::harness_derived |
| REQ-E1 | caveman output mode | orchestrator | 0019 | T14.1 | eval |
| REQ-E2 | caveman-compress prose artifacts | compress.py | 0019 | T14.2 | test_compress |
| REQ-E3 | prose-only compression guard | compress.py | 0019 | T14.2 | test_compress |
| NFR-SCOPE-1 | Python-only v1, no silent free pass | evaluator | 0010 | T3.2 | test_characterization |
| NFR-PERF-2 | concurrency cap + file-overlap co-dispatch | dispatcher, workspace.py | 0013 | T8.1 | test_workspace |
| NFR-MIG-1 | migrate superseded tests, don't preserve | evaluator, router | 0015 | T0.3 | test_models |

## Flags

**Coverage gaps (REQ → no concrete automated test yet):**
- REQ-E1 (caveman output mode) — verified by eval/manual, not a unit test. Acceptable (output-style, not logic).
- NFR-PERF-1 (latency budgets) — observed via ledger, no dedicated test; add a budget-assertion test when budgets are set.
- NFR-REPRO-1 — covered indirectly by test_run_ledger + test_router::test_deterministic; no standalone replay test yet.
- NFR-SEC-1 (high-stakes definition) — drives REQ-O3/REQ-C4 logic; the definition itself needs a `test_stakes_classifier`.

**Gold-plating watch (component → ensure a REQ justifies it):**
- `retrieve.py` minimal-slice — justified by REQ-R4/REQ-E3; keep scoped to sensitivity + brief-size, not general retrieval.
- ASSEMBLY golden — justified by REQ-I4; do not expand into a general E2E suite.

**Phase-2 / deferred (no v1 REQ):**
- ADR-0020 (MCP integration surface) — deferred; intentionally has no v1 requirement.
- ADR-0018 full mid-flight heartbeat corroboration — deferred to phase-2 ACP; v1 only REQ-OBS1 stall.
