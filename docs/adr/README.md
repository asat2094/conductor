# Architecture Decision Records

This directory records architecture decisions for conductor in a Nygard + MADR hybrid format. Each ADR captures Context, Decision, Considered alternatives, Consequences, and Related links.

ADRs are **immutable once Accepted**: an accepted ADR is never edited to change its decision. A later decision that changes course is recorded as a **new ADR** that **supersedes** the earlier one. The earlier ADR's status is updated to Superseded with a pointer forward.

Most ADRs below are **Proposed** — pending user review alongside the [requirements](../specs/conductor/requirements.md) and [design](../specs/conductor/design.md). ADR-0000 is Accepted (the decision to use ADRs); ADR-0015 is Accepted because it records a decision already implemented on `develop`.

The 2026-05-29 multi-provider spec's routing and rate-limit decisions are **Superseded by [ADR-0014](./0014-admission-separate-from-routing.md) and [ADR-0015](./0015-deterministic-routing-supersedes-binary-route.md)**.

## Index

| # | Title | Status |
|---|-------|--------|
| [0000](./0000-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0001](./0001-lean-orchestrator-no-file-bodies.md) | Lean orchestrator, no file bodies | Proposed |
| [0002](./0002-no-trust-maker-self-report.md) | No trust in maker self-report (Law 1) | Proposed |
| [0003](./0003-mechanical-first-model-last.md) | Mechanical-first, model-last (Law 2) | Proposed |
| [0004](./0004-bound-seed-input-ceiling.md) | Bound the seed-input ceiling (Law 3) | Proposed |
| [0005](./0005-accuracy-throughput-over-equi-utilization.md) | Accuracy+throughput over equi-utilization | Proposed |
| [0006](./0006-tiered-maker-pool-bounded-escalation.md) | Tiered maker pool, bounded escalation | Proposed |
| [0007](./0007-author-separation.md) | Author separation (test_author ≠ impl_author) | Proposed |
| [0008](./0008-red-adequacy-mutation-redcause.md) | RED adequacy via mutation + RED-cause | Proposed |
| [0009](./0009-green-full-suite-independent.md) | GREEN full-suite independent | Proposed |
| [0010](./0010-nonfunctional-characterization-gate.md) | Non-functional characterization gate | Proposed |
| [0011](./0011-hardgate-decomposition-briefs.md) | Hard-gate decomposition into briefs | Proposed |
| [0012](./0012-contract-conformance-ast-drop-pact.md) | Contract conformance via AST, drop Pact | Proposed |
| [0013](./0013-worktree-per-maker-isolation.md) | Worktree-per-maker isolation | Proposed |
| [0014](./0014-admission-separate-from-routing.md) | Admission separate from routing | Proposed |
| [0015](./0015-deterministic-routing-supersedes-binary-route.md) | Deterministic routing (supersedes binary route) | Accepted (supersedes 2026-05-29) |
| [0016](./0016-cost-skip-claude-inline.md) | Cost-skip → CLAUDE_INLINE | Proposed |
| [0017](./0017-sensitivity-tag-data-boundary.md) | Sensitivity-tag data boundary | Proposed |
| [0018](./0018-segmented-heartbeat.md) | Segmented heartbeat (v1 stall-only) | Proposed (scoped) |
| [0019](./0019-caveman-compression-paid-boundaries.md) | Caveman compression at paid boundaries | Superseded by 0021 |
| [0020](./0020-mcp-unifying-integration-surface.md) | MCP unifying integration surface | Proposed but Deferred (Phase 2) |
| [0021](./0021-pluggable-context-optimizer.md) | Pluggable context-optimizer facade (baked-in defaults, opt-in backends) | Proposed |
| [0022](./0022-codegraph-decomposition-verifier.md) | Codegraph-backed decomposition verifier (advisory, degrade-clean) | Proposed |
| [0023](./0023-development-tracker-progress-board.md) | Development tracker / progress board (event-sourced, harness-derived, pluggable sinks) | Proposed |
| [0028](./0028-checkpoint-resume-replay.md) | Checkpoint / resume / replay over the event log | Proposed |
| [0029](./0029-wave-failure-mode-taxonomy.md) | Wave failure-mode taxonomy + concurrency cap | Proposed |
| [0030](./0030-git-log-red-gate.md) | git-log RED-before-impl gate (commit-order, zero model trust) | Proposed |
| [0031](./0031-discriminated-brief-schema-guards.md) | Discriminated per-task-type brief/unit schema guards | Proposed |
| [0032](./0032-spec-completeness-probes.md) | Spec-completeness probes (Edge/Prohibition) — advisory, gate-feeding | Proposed |
| [0033](./0033-ccr-reversible-retrieve.md) | CCR reversible-retrieve as an optimizer capability | Proposed |
| [0034](./0034-budget-audit-enforce-rollup.md) | Budget audit｜enforce modes + sub-build spend rollup | Proposed |
| [0035](./0035-pluggable-language-adapters.md) | Pluggable language adapters (language-agnostic base, swappable block) | Proposed (supersedes NFR-SCOPE-1) |
| [0036](./0036-repo-native-style-gate.md) | Repo-native style gate (repo's own lint/format = mechanical oracle) | Proposed |
| [0037](./0037-repo-onboarding-profile.md) | Repo onboarding / profile (detect language, tooling, standards) | Proposed |

> **Borrow provenance (2026-06-30):** ADR-0028/0029/0031/0034 ← microsoft/conductor (patterns, MIT); 0030/0032 ← gsd-core; 0033 ← headroom. All re-implemented in-stack, vendor-neutral. **Explicitly NOT borrowed** (hampers core): LLM-judge `validator`/`dialog` gating (Law-1 violation), static per-agent model choice (router is superior), ensemble/multi-round debate (net-negative, ADR-0004 amendment), continuous autonomous loop, gsd Nyquist coverage-finder (declined — most model-trust-adjacent). **Deferred:** real-time web dashboard, capability-registry plugin contract, CacheAligner.
| [0024](./0024-roles-are-model-assignments-context-isolation-invariant.md) | Roles are model-assignments; bounded-context isolation (not price) is the invariant | Proposed (foundational) |
| [0025](./0025-property-based-metamorphic-gate.md) | Property-based + metamorphic testing as a first-class checker tier | Proposed |
| [0026](./0026-held-out-acceptance-oracle.md) | Held-out acceptance oracle + anti-reward-hacking scope guard + dependency-existence check | Proposed |
| [0027](./0027-bounded-repair-loop.md) | Bounded per-unit repair loop with mechanical stop conditions ("loops", done safely) | Proposed |
