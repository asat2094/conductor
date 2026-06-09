# Conductor — Distributed Build Design

**Date:** 2026-06-09
**Branch:** `develop`
**Status:** Design — pending user review, then implementation plan

---

## 1. Goal

Make Claude (or a host agent harness) act as a lean **orchestrator + checker** while a heterogeneous **maker pool** does the bulk building. The orchestrator decomposes intent, defines contracts, and checks results via lean signals — it never loads file bodies into its own context. Makers (free local/cloud models + bounded Claude subagents) execute bounded subtasks in isolation.

Four core goals, in tension (a CAP-like trade):

| Goal | Meaning |
|---|---|
| **Efficiency** | keep bulk file content out of the main context window (the real token sink) |
| **Cost** | offload work to free makers; never let overhead exceed inline-Claude cost |
| **Accuracy** | done ⟺ a deterministic gate is green, not a semantic guess |
| **Correctness** | the assembled system works, not just each unit in isolation |

When goals conflict, the chosen priority is **accuracy + throughput**; strict equi-utilization of makers is sacrificed (it falls out naturally from one-task-per-maker scheduling).

### Why this beats a single self-disciplined Claude actor

Superpowers (and similar) ship a TDD *discipline* — advisory markdown one actor is asked to follow. It degrades under context pressure: RED skipped, vacuous tests, self-validation (one actor writes test + impl), self-reported "tests pass." Conductor replaces trust with **mechanical enforcement by an external harness**: gates are code, not advice, and cannot be skipped. The token win is not "free vs paid" alone — it is **bounded maker context vs bloated main-thread history** (main resends full history every turn; a fresh subagent gets only its slice).

---

## 2. Current state (what `develop` already provides vs. what is net-new)

`develop` = `main` + 19 commits (+4499 lines): a full free-multi-provider orchestrator.

**Already present (the distribution plumbing):**
- `provider_call.py` — unified ollama + OpenAI-compat caller; `RateLimitError`, `ProviderError`
- `providers.py` / `providers.json` — 8 free providers (gemma4 local + nim, gemini, openrouter, openrouter_poolside, opencode_deepseek, opencode_mimo)
- `orchestrate.py` — rank → call → eval → heal → fallback loop; per-model rate-limit cooldown; `orchestrate_parallel()`
- `router.py` — `rank_providers()` (cost-normalised accuracy) + legacy binary `route()`
- `parallel_delegate.py`, `parallel_cli.py`, `pipeline.py`, `tokens.py`
- `capability_profiles.json` — 9 providers; `profiles.py` cross-session decay

**Net-new (the correctness spine — this design):**
- **Decomposition** — no `decompose.py` / `dag.py` / `lint_plan.py`, no SubtaskBrief, no `produces`/`consumes`/`logical_deps`. Absent.
- **TDD loop / gates** — test *execution* exists (see evaluator below) but only as a soft, changed-files-only scoring axis. The loop is absent: no RED-first (the test is never run before impl to assert it fails), no test authoring (a `test_<name>` file must pre-exist), no hard GREEN gate (the pytest result is a 0–35 *score*, not a pass/fail gate — a 0 can still total ≥70 via the other axes), no full-suite regression (it runs `pytest <changed_files>` only, so a maker breaking a sibling test elsewhere is not caught), no mutation adequacy.
- **Author separation** — no `test_author ≠ impl_author`, no orchestrator-validates-test step. Absent.
- **Evaluator** — exists but in a weak, self-report-trusting form (see below).

The evaluator that exists today:

```
syntax    = ast.parse                                           (25)
tests     = pytest <changed_files> IF a test_<name> pre-exists  (35)  ← soft score, changed-files only, NOT a gate; S3 refactor free-pass
scope     = basename diff (changed − requested)                 (20)
semantic  = word-overlap of maker's OWN output string vs desc   (20)  ← S11: gameable, trusts self-report
```

Conclusion: develop gives maker pool + parallel dispatch + a weak evaluator. It does **not** give correctness. This design adds it.

---

## 3. Architecture

```
ORCHESTRATOR  (Claude main thread — or a host harness in phase 2)
   intent → decompose → define contracts → CHECK verdicts → merge
   stays LEAN: never loads file bodies; sees briefs + verdicts only
        │ intent + target files
        ▼
DECOMPOSITION  (HARD-GATE phase)                    [decompose.py, dag.py]
   codegraph deps + Claude logical_deps[] → producer→consumer DAG
   emits SubtaskBrief JSON per unit:
     {id, goal, files, context_slices(cut once), contract,
      exit_criteria, verify_cmd, produces[], consumes[], sensitivity}
   lint_plan.py: symbol cross-ref + placeholder scan
   → strategic-compact: file bodies fall out of main context  (TOKEN SAVE)
        │ SubtaskBrief DAG (topo waves, file-overlap aware)
        ▼
ROUTER                                              [router.py]
   1. COST SKIP gate  → tiny task? → AgentType.CLAUDE_INLINE
   2. SENSITIVITY hard-rule → high? local/Claude only, never free cloud
   3. capability×cost rank (pinned profile snapshot + seed)
   4. cold-start: tier-prior + uncertainty (NOT the 1.0 default bug)
        │ ranked maker ladder per unit
        ▼
ADMISSION  (SEPARATE from routing)                  [admission.py]
   per-provider AIMD limiter + token bucket + circuit breaker
   retry allowlist (429/timeout/5xx → retry SAME maker, not escalate)
        ▼
MAKER POOL  (tiered, isolated per unit via git worktree)
   tier0 gemma4 local $0   tier1 free cloud $0   tier2 Claude subagent
   adapters: ollama | openai-compat | (phase2: acpx/ACP)
   author separation:  maker_A writes test  ≠  maker_B writes impl
        │ artifact + structured envelope (status, AST-extracted sigs)
        ▼
GATES  — 100% mechanical, no Claude reading        [evaluator.py]
   RED   : mutation kill-rate + RED-cause string (test adequacy)
   GREEN : harness re-runs test + FULL suite (ignore self-report)
   CONTRACT: AST signature diff vs contracts.json (seam)
   CHARACTERIZATION: golden I/O diff (refactor/rename/perf class)
   confidence 0–1 → ≥0.95 auto-accept, else escalate
        │ pass → MERGE QUEUE: rebase onto integration + full suite (reduce)
        │ ASSEMBLY golden gate (coupled units)      [merge_queue.py]
        │ fail → HEAL  A(reprompt) → B(next maker) → C(tier2) → only-then main
        ▼
LEDGER                                              [session_stats.py]
   run-ledger (routing, fallback, snapshot-hash, seed, verdicts)
   regression ledger · exposure audit · cost-per-successful-task KPI
   + periodic Opus RANDOM AUDIT (backstop for correlated blind spots)
```

### Roles — the token contract

| Stays with the orchestrator (lean) | Delegated to makers (bulk) |
|---|---|
| read intent, decompose into DAG | read file body + transform + write |
| define contract per subtask | draft impl/test to satisfy contract |
| validate the unit test (small read) | run own tests, self-report (re-verified) |
| check verdicts; integration/merge decisions | mechanical edits, codegen, boilerplate |
| author integration + acceptance tests | author unit tests (validated by orchestrator) |

### Maker contract

| Field | Spec |
|---|---|
| **Identity** | one provider per unit-role; tiered: tier0 gemma4 local · tier1 free cloud · tier2 Claude subagent. `test_author ≠ impl_author` for the same unit (harness-enforced). |
| **Input** | exactly one `SubtaskBrief` (goal, `context_slices` cut once, contract, `verify_cmd`, `exit_criteria`). Never the whole repo, never main-thread history. Bounded context is the savings. |
| **Isolation** | own git worktree (path derived from subtask id) + env-injected port/DB/tmpdir. |
| **Output** | structured envelope `{status: DONE|DONE_WITH_CONCERNS|BLOCKED|NEEDS_CONTEXT, changed_files[], exported_signatures[]}` + the written files on disk. |
| **Heartbeat (S13)** | while running, emits periodic checkpoints `{unit_id, segment, action, self_on_track, elapsed}` — a liveness/progress signal the harness corroborates, never trusts (Law 1). Missing heartbeat → stall; corroboration fail → drift → early-kill. |
| **Trust** | none of the envelope or heartbeat is trusted as gate evidence — both are routing/health signals only (Law 1). |
| **Failure** | retryable error (429/timeout/5xx) → admission retries SAME maker; quality miss (gate fail) → heal A→B→C→tier2. |

### Checker contract

The checker is an **external mechanical referee** = the gate engine (`evaluator.py`) + the orchestrator's CHECK step. It is specified as tightly as the maker so "correctness" is not a vibe.

| Field | Spec |
|---|---|
| **Identity** | deterministic gate engine, runs on 100% of units, no model in the hot path (Law 2). |
| **Reads** | the written file (AST-parsed), the unit test, `contracts.json`, golden snapshots, full-suite result. **Never** the maker's self-reported `output`/envelope string (downweighted to ~0, Law 1). |
| **Gate sequence by task class** | **functional:** RED (mutation kill-rate + RED-cause string) → GREEN (re-run unit test + FULL suite) → CONTRACT (AST signature diff vs `contracts.json`). **non-functional** (refactor/rename/perf): CHARACTERIZATION (golden I/O diff) → CONTRACT; rename also uses compile-RED. **assembly:** ASSEMBLY golden over merged coupled units. |
| **Decision** | each gate → pass/fail + sub-confidence; aggregate to a 0–1 score. **≥0.95 → auto-accept, orchestrator reads nothing.** **<0.95 → escalate** (orchestrator failure-read, then Opus). A gate hard-fail (RED survives mutants, GREEN suite red, CONTRACT drift) is an unconditional reject regardless of score. |
| **Orchestrator reads** | failures always; passes never (trust mechanical green) — **except** a thin periodic Opus **random audit** of accepted units (Law 3 backstop for correlated blind spots). |
| **Intervention (control-takeback)** | on a blind-spot signal — ensemble disagreement, audit catch, or a high-stakes unit that could not be staffed with diverse makers — the checker raises an INTERVENE verdict. The orchestrator then takes control of that unit: re-derive via a tier2 Opus subagent, or implement inline. Accuracy/correctness outrank cost in this regime (Law 3). |
| **Output** | lean verdict `{unit_id, gate_results, confidence, accept|escalate|intervene, changed_files}` — never file bodies. This is all the orchestrator's context ever sees. |
| **Invariants** | Laws 1–3 hold on every gate. No gate may derive its evidence from the artifact's own author. |

### Lifecycle

```
1 INTENT     orchestrator receives a dev task
2 DECOMPOSE  codegraph + logical_deps → bounded SubtaskBrief DAG (HARD-GATE)
3 CONTRACT   functional → unit test (maker writes) | non-func → criteria
  3a RED GATE  maker_A writes test → orchestrator validates → harness asserts FAIL
4 DISPATCH   maker_B (≠A) writes impl; accuracy+throughput routing; one-per-maker
  4a GREEN GATE  harness re-runs test + full suite (NOT maker self-report)
5 CHECK      orchestrator reads failures always; trusts mechanical green
6 HEAL       fail → re-prompt with test output (A) → next maker (B/C) → tier2 → main
7 INTEGRATE  merge queue: rebase + full suite; assembly golden; orchestrator confirms green
```

---

## 4. The 3 invariant laws (apply to every gate)

1. **No gate trusts the maker's self-report.** Evidence is harness-derived — AST parse of the actual written file, independent re-run — never the maker's own envelope/output string. Model-based auditors are **advisory only, never gating**.
2. **Mechanical-first, model-last.** Deterministic gates run on 100% of units with no Claude reading; Claude/Opus is invoked only when mechanical confidence is sub-0.95.
3. **Seed-input ceiling is real — and in the blind-spot regime, accuracy/correctness outrank cost.** Golden / characterization / contract gates verify only the captured seed inputs and the syntactic surface, so correlated cheap-maker blind spots can produce wrong-but-green. Three layers bound it: (a) **proactive maker diversity** — the test-author, impl-author, and any verifier roles for one unit draw from *different model families/providers*, so a shared blind spot is unlikely; (b) a thin **periodic Opus random audit** of accepted units; (c) **orchestrator control-takeback** — on any blind-spot signal (ensemble disagreement, audit catch, or unavoidably low maker diversity on a high-stakes unit), the orchestrator *intervenes and takes control of that unit*: it escalates to a more capable independent agent (tier2 Opus subagent) to re-derive, or implements the unit inline. This deliberately spends cost to protect correctness. Do not claim "sampling eliminated."

---

## 5. Shortcomings → bridges

Twelve known shortcomings of the naive distributed-build, each with a bridging fix sourced from superpowers / ECC / ruflo-swarm / external SOTA (FrugalGPT, Mixture-of-Agents, HuggingGPT, ADaPT, Pact CDC, mutation/characterization testing, Netflix adaptive concurrency). Build priority is leverage-ordered and ROI-gated.

| ID | Shortcoming | Bridge (concrete) | Goal |
|---|---|---|---|
| **S5** | small-task overhead > savings | COST SKIP gate in router: project full delegation cost vs inline-Claude; below `min_delegation_tokens` → `AgentType.CLAUDE_INLINE`. ADaPT demand-driven decompose (decompose only on failure). **Meta-gate for all others.** | efficiency, cost |
| **S2** | token-saving ⊥ contract-quality (shallow test validation) | mutation kill-rate RED gate (mutate impl region, test must kill each mutant) + RED-cause string assertion. Deterministic, no body reading. Spec-auditor model = advisory only. | accuracy, correctness |
| **S12** | Claude's own decomposition weak → main-context token blast | HARD-GATE decompose phase → self-contained SubtaskBrief JSON (slices cut once) + `lint_plan.py` symbol/placeholder check + phase-boundary strategic-compact. The actual token-saver; precondition for S1/S4. | efficiency, cost |
| **S9** | capability cold-start / sparsity | kill legacy `route()` 1.0 default (real bug both branches); tier-prior + calibrated uncertainty; seed from `bench.py` baseline. | accuracy, cost |
| **S3** | non-functional tasks ungated (refactor/rename/perf free-pass) | CHARACTERIZATION golden gate (capture observable I/O before, diff after) + contract-surface diff; compile-RED for renames; perf benchmark-delta (advisory band). | correctness, accuracy |
| **S11** | sampled check leaks wrong-but-green | 100%-coverage mechanical gates; downweight maker self-report (`estimate_semantic`) to near-zero; confidence-gated escalation ≥0.95; thin Opus random audit backstop. | accuracy, correctness |
| **S4** | integration seam drift | merge-queue full-suite rebase (model-independent, **keep**). Cross-subtask contract frozen once into both briefs; conformance checked via **AST-extracted** signatures, **not** the maker envelope. Drop Pact ceremony. | correctness |
| **S1** | decomposition semantic blindness (local-green/global-broken) | `produces`/`consumes`/`logical_deps` on SubTask → producer→consumer DAG (shared symbol = coupled even with no structural edge); assembly golden gate over merged coupled units. | correctness, accuracy |
| **S10** | non-reproducible routing | routing = pure function of (features, pinned profile snapshot, seed); live state moved to admission layer; run-ledger replays recorded decisions; id-derived worktree paths. (routing only — makers stay non-deterministic) | correctness (debuggability) |
| **S8** | parallel makers shared-repo contention | git-worktree-per-maker (path derived from subtask id) + env-injected isolated port/DB/tmpdir; file-overlap scheduling (disjoint writes co-dispatch); merge = single reduce stage; **move `session_stats.db` out of the work tree** (cheap immediate win). | correctness, efficiency |
| **S7** | rate-limit cascade → paid escalation balloon | `admission.py`: per-provider AIMD/Gradient limiter + token-bucket + circuit breaker; `_RETRYABLE_ERRORS` allowlist so throttle ≠ incapability; bounded escalation ladder + per-run cost ceiling. | cost, efficiency |
| **S6** | free-cloud data exposure | per-file `sensitivity` tag; router hard-rule high→local/Claude only; minimal-slice briefs; append-only exposure audit. **Real on develop** (cloud providers active). Bounds blast radius; cannot guarantee zero retention. | correctness (data-safety), cost |
| **S13** | no mid-flight visibility — a drifting maker burns full budget before its terminal verdict; stalls invisible | **decomposed checkpoints (segmented heartbeat).** Each maker emits periodic lightweight checkpoint events while running its unit: `{unit_id, segment, action (what it's doing now), self_on_track, elapsed}`. The harness *corroborates* each checkpoint with cheap incremental signals (partial AST-parse, unit RED test still referenced, no scope creep beyond `writes_files`) — the self-assessment is a signal, not trusted (Law 1). Orchestrator sees a segmented liveness+correctness timeline (lean, no bodies), enabling **early-kill on drift**, **stall detection on heartbeat gap**, and a progress timeline in the ledger. | correctness (catch drift early), cost (kill before full burn), efficiency |
| **S14** | prose channels (briefs, prompts, verdicts, memory) carry filler tokens | **caveman compression at paid-token boundaries** (overlay, not a gate; inspiration: [juliusbrussee/caveman](https://github.com/juliusbrussee/caveman)). Three layers: (a) **orchestrator output mode** — caveman-speak replies, ~65–75% output cut, ~free, reasoning untouched; (b) **`caveman-compress`** on repeatedly-read prose artifacts (CLAUDE.md, persistent SubtaskBrief/contract *notes*) — amortized ~46% input/session, with `validate.py` guaranteeing code/URLs/paths/headings byte-preserved; (c) **terse verdicts/briefs** at paid boundaries — tier2 Claude subagent briefs + checker verdict summaries the orchestrator reads. **Prose only — never code, tests, `context_slices`, contract structured fields, or any gate-parsed evidence (Law 1).** Compression is itself a Claude call → apply only where amortized or to the ~free output mode. Makers are mostly free ($0), so compressing maker *input* is a latency/rate-limit win, not a $ win — target $ savings at the paid Claude boundaries. Reuse caveman's sensitivity guard (.env/.ssh/.aws never shipped) → folds into S6. | efficiency, cost |

### Build order (leverage spine, ROI-gated)

```
S5 → S2 → S12 → S9 → S3 → S11 → S4 → S1 → S10 → S13 → S8 → S7 → S6
```
**S14 (caveman compression) is a cross-cutting overlay, not a spine step.** Layer (a) — orchestrator output mode — is ~free and can be on from day one. Layers (b)/(c) attach once the corresponding artifacts (persistent briefs, paid tier2 briefs, verdict summaries) exist.

S5 first is non-negotiable: without the cost gate, the pipeline is net-negative on small tasks and the rest of the program has negative ROI.

### New / extended components

**New files:** `harness/decompose.py`, `harness/dag.py`, `harness/lint_plan.py`, `harness/contracts.json`, `harness/characterize.sh` + `harness/golden/`, `harness/workspace.py`, `harness/merge_queue.py`, `harness/admission.py`, `harness/retrieve.py`, `harness/baseline.json` (from `bench.py`), `harness/prompts/spec_auditor.txt`, `harness/heartbeat.py` (checkpoint emit/corroborate + early-kill/stall detection — S13), `harness/compress.py` (S14 — thin wrapper over the caveman-compress scripts + a prose-channel allowlist that hard-excludes code/tests/`context_slices`/contract fields; reuses caveman's sensitivity guard).

**Extended:** `evaluator.py` (RED/CONTRACT/CHARACTERIZATION/ASSEMBLY modes + 0–1 confidence stop-judger; 100% coverage; downweight self-report), `router.py` (cost SKIP gate → `CLAUDE_INLINE`, sensitivity rule, tier-prior cold-start, pinned snapshot+seed, fallback ladder), `session_stats.py` (run-ledger, regression ledger, exposure audit, cost_usd + budget, cost-per-successful-task KPI), `gemma4_call.py` (structured envelope: status DONE/DONE_WITH_CONCERNS/BLOCKED/NEEDS_CONTEXT + `exported_signatures`; `_RETRYABLE_ERRORS` allowlist), `models.py` (TaskType += REFACTOR/SIGNATURE_CHANGE/PERF; AgentType += CLAUDE_INLINE; SubTask += produces/consumes/logical_deps/sensitivity/writes_files).

---

## 6. Unresolved (no clean fix — bound, do not pretend to close)

- **Correlated blind spots** — if two cheap makers and cheap mutation operators share a gap, a logic-shaped under-specified test passes mechanically below 0.95. Not fully closable, but bounded by three layers (Law 3): proactive cross-family **maker diversity** across the test/impl/verify roles; a periodic Opus/human **random audit**; and **orchestrator control-takeback** (INTERVENE verdict → tier2 Opus re-derive or inline implement) whenever a blind-spot signal fires or a high-stakes unit cannot be staffed with diverse makers. Accuracy/correctness outrank cost in this regime — the residual tail is the cost of that trade, not a silent wrong-accept.
- **Semantic seam correctness** — contracts are syntactic; a type-correct-but-semantically-wrong callee passes without generated/property inputs at the seam.
- **S6 retention** — once bytes reach a free provider, there is no control over its training/retention policy. The bridge bounds and audits blast radius; it cannot guarantee zero exposure.

---

## 7. Testing the harness itself

- `test_decomposer.py` — DAG order from mock codegraph deps; bounded splits; disposability/recurse-or-inline.
- `test_author_separation.py` — A≠B enforced; A excluded from impl routing for its unit.
- `test_red_gate.py` — vacuous/already-green test rejected; mutation survivors reject; genuine RED passes.
- `test_green_gate.py` — self-report ignored; independent re-run; full-suite regression caught.
- `test_router.py` (extend) — cost SKIP → CLAUDE_INLINE; sensitivity hard-rule; cold-start tier-prior (no 1.0 default); tier escalation, only-then-main.
- `test_admission.py` — AIMD cut on throttle; retry allowlist; cost-ceiling stop.
- `test_heartbeat.py` — checkpoint emit + corroborate; stall detection on heartbeat gap; early-kill on drift (scope creep / RED-test no longer referenced); self_on_track never gates (Law 1).
- `test_compress.py` (S14) — code/tests/`context_slices`/contract fields are NEVER sent to compression; `validate.py` preserves code/URLs/paths byte-exact; sensitive paths refused; compression failure falls back to the uncompressed original (no data loss).
- Keep the 97 existing tests green.

---

## 8. Out of scope (parked)

- **Phase 2 — host-harness extension (OpenClaw + Hermes).** Both support MCP (OpenClaw: stdio + HTTP/SSE via `openclaw.json` `mcpServers`; Hermes: MCP-native). The planned surface is a single Python MCP server (`harness/mcp_server.py`) exposing `distribute_task` / `distribute_parallel` → existing `orchestrate()`, serving both harnesses; plus an optional acpx/ACP maker adapter (`acpx <agent> exec`) to add Codex/Claude/OpenClaw ACP agents to the maker pool. **Deferred — not part of this design's build.**
- Streaming responses, multi-turn maker conversations, provider-specific prompt tuning.
