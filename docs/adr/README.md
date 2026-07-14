# Architecture Decision Records

This directory records architecture decisions for conductor in a Nygard + MADR hybrid format. Each ADR captures Context, Decision, Considered alternatives, Consequences, and Related links.

ADRs are **immutable once Accepted**: an accepted ADR is never edited to change its decision. A later decision that changes course is recorded as a **new ADR** that **supersedes** the earlier one. The earlier ADR's status is updated to Superseded with a pointer forward.

Status (design review, 2026-07-13/14): all ADRs **Accepted** except — ADR-0019 Superseded by 0021; ADR-0020 Deferred (Phase 2). Four new ADRs came out of the review: **0038** (inconclusive-only judge tiebreak, amends 0003), **0039** (adaptive confidence-scored routing, extends 0015/0006/0016), **0040** (ensemble best-of-N maker, amends 0004), **0041** (per-wave atomic merge — closed-subgraph landing, amends 0012, resolves the parked 0029 merge-granularity question).

The 2026-05-29 multi-provider spec's routing and rate-limit decisions are **Superseded by [ADR-0014](./0014-admission-separate-from-routing.md) and [ADR-0015](./0015-deterministic-routing-supersedes-binary-route.md)**.

## Index

| # | Title | Status |
|---|-------|--------|
| [0000](./0000-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0001](./0001-lean-orchestrator-no-file-bodies.md) | Lean orchestrator, no file bodies | Accepted |
| [0002](./0002-no-trust-maker-self-report.md) | No trust in maker self-report (Law 1) | Accepted |
| [0003](./0003-mechanical-first-model-last.md) | Mechanical-first, model-last (Law 2) | Accepted |
| [0004](./0004-bound-seed-input-ceiling.md) | Bound the seed-input ceiling (Law 3) | Accepted |
| [0005](./0005-accuracy-throughput-over-equi-utilization.md) | Accuracy+throughput over equi-utilization | Accepted |
| [0006](./0006-tiered-maker-pool-bounded-escalation.md) | Tiered maker pool, bounded escalation | Accepted |
| [0007](./0007-author-separation.md) | Author separation (test_author ≠ impl_author) | Accepted |
| [0008](./0008-red-adequacy-mutation-redcause.md) | RED adequacy via mutation + RED-cause | Accepted |
| [0009](./0009-green-full-suite-independent.md) | GREEN full-suite independent | Accepted |
| [0010](./0010-nonfunctional-characterization-gate.md) | Non-functional characterization gate | Accepted |
| [0011](./0011-hardgate-decomposition-briefs.md) | Hard-gate decomposition into briefs | Accepted |
| [0012](./0012-contract-conformance-ast-drop-pact.md) | Contract conformance via AST, drop Pact | Accepted |
| [0013](./0013-worktree-per-maker-isolation.md) | Worktree-per-maker isolation | Accepted |
| [0014](./0014-admission-separate-from-routing.md) | Admission separate from routing | Accepted |
| [0015](./0015-deterministic-routing-supersedes-binary-route.md) | Deterministic routing (supersedes binary route) | Accepted (supersedes 2026-05-29) |
| [0016](./0016-cost-skip-claude-inline.md) | Cost-skip → CLAUDE_INLINE | Accepted |
| [0017](./0017-sensitivity-tag-data-boundary.md) | Sensitivity-tag data boundary | Accepted |
| [0018](./0018-segmented-heartbeat.md) | Segmented heartbeat (v1 stall-only) | Accepted (scoped) |
| [0019](./0019-caveman-compression-paid-boundaries.md) | Caveman compression at paid boundaries | Superseded by 0021 |
| [0020](./0020-mcp-unifying-integration-surface.md) | MCP unifying integration surface | Proposed but Deferred (Phase 2) |
| [0021](./0021-pluggable-context-optimizer.md) | Pluggable context-optimizer facade (baked-in defaults, opt-in backends) | Accepted |
| [0022](./0022-codegraph-decomposition-verifier.md) | Codegraph-backed decomposition verifier (advisory, degrade-clean) | Accepted |
| [0023](./0023-development-tracker-progress-board.md) | Development tracker / progress board (event-sourced, harness-derived, pluggable sinks) | Accepted |
| [0028](./0028-checkpoint-resume-replay.md) | Checkpoint / resume / replay over the event log | Accepted |
| [0029](./0029-wave-failure-mode-taxonomy.md) | Wave failure-mode taxonomy + concurrency cap | Accepted (atomicity settled in 0041) |
| [0030](./0030-git-log-red-gate.md) | git-log RED-before-impl gate (commit-order, zero model trust) | Accepted |
| [0031](./0031-discriminated-brief-schema-guards.md) | Discriminated per-task-type brief/unit schema guards | Accepted |
| [0032](./0032-spec-completeness-probes.md) | Spec-completeness probes (Edge/Prohibition) — advisory, gate-feeding | Accepted |
| [0033](./0033-ccr-reversible-retrieve.md) | CCR reversible-retrieve as an optimizer capability | Accepted |
| [0034](./0034-budget-audit-enforce-rollup.md) | Budget audit｜enforce modes + sub-build spend rollup | Accepted |
| [0035](./0035-pluggable-language-adapters.md) | Pluggable language adapters (language-agnostic base, swappable block) | Accepted (supersedes NFR-SCOPE-1) |
| [0036](./0036-repo-native-style-gate.md) | Repo-native style gate (repo's own lint/format = mechanical oracle) | Accepted |
| [0037](./0037-repo-onboarding-profile.md) | Repo onboarding / profile (detect language, tooling, standards) | Accepted |

> **Implementation-status note (2026-07-14, post gap-review):** every designed gate is now
> production-reachable from `python3 -m harness` / `build_live`: git-RED (0030) via `--tdd-gates`,
> mutation (0008) + characterization (0010) via `GateSpec.extra_gates` / `gate_stages.py`,
> codegraph reverify (0022) via `--codegraph`, spec probes (0032) via `--probes`, cost ceiling
> (0014/0034) via `--budget`, checkpoints (0028) via `--checkpoint`, judge (0038) / confidence
> (0039, SQLite-persisted) / best-of-N (0040) / per-wave merge (0041) via `build_live` knobs;
> sensitivity boundary (0017) enforced in `rank_providers`. `strict_gates.py` remains the primitive
> library; its author-separation lives in `role_policy` (+ judge author-check), its GREEN discipline
> in the in-loop test + merge-queue full suite. The legacy one-off path (`harness.pipeline`) now
> shares the adapter-based test scorer (0035).

> **Borrow provenance (2026-06-30):** ADR-0028/0029/0031/0034 ← microsoft/conductor (patterns, MIT); 0030/0032 ← gsd-core; 0033 ← headroom. All re-implemented in-stack, vendor-neutral. **Explicitly NOT borrowed** (hampers core): LLM-judge `validator`/`dialog` gating as a *primary* accept mechanism (Law-1 violation — but see ADR-0038 for the narrow inconclusive-only tiebreak carve-out), static per-agent model choice (superseded by ADR-0039 dynamic confidence routing), ensemble/multi-round debate *voting on correctness* (consensus ≠ correct — but see ADR-0040: ensemble adopted in the bounded best-of-N form where the mechanical gate selects, never a vote), continuous autonomous loop, gsd Nyquist coverage-finder (declined — most model-trust-adjacent). **Deferred:** real-time web dashboard, capability-registry plugin contract, CacheAligner.
| [0024](./0024-roles-are-model-assignments-context-isolation-invariant.md) | Roles are model-assignments; bounded-context isolation (not price) is the invariant | Accepted (foundational) |
| [0025](./0025-property-based-metamorphic-gate.md) | Property-based + metamorphic testing as a first-class checker tier | Accepted |
| [0026](./0026-held-out-acceptance-oracle.md) | Held-out acceptance oracle + anti-reward-hacking scope guard + dependency-existence check | Accepted |
| [0027](./0027-bounded-repair-loop.md) | Bounded per-unit repair loop with mechanical stop conditions ("loops", done safely) | Accepted |
| [0038](./0038-inconclusive-only-judge-tiebreak.md) | Inconclusive-only LLM-judge tiebreak (bounded exception to Law 2) | Accepted (amends 0003) |
| [0039](./0039-adaptive-confidence-scored-routing.md) | Adaptive confidence-scored routing (live per-(model, task-type) feedback) | Accepted (extends 0015/0006/0016) |
| [0040](./0040-ensemble-best-of-n-maker.md) | Ensemble as best-of-N maker (gate-selected, not vote-on-correctness) | Accepted (amends 0004) |
| [0041](./0041-per-wave-atomic-merge.md) | Per-wave atomic merge (closed-subgraph landing) | Accepted (amends 0012, un-parks 0029) |
