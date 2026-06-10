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
