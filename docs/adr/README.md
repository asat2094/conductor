# Architecture Decision Records

This directory records architecture decisions for conductor in a Nygard + MADR hybrid format. Each ADR captures Context, Decision, Considered alternatives, Consequences, and Related links.

ADRs are **immutable once Accepted**: an accepted ADR is never edited to change its decision. A later decision that changes course is recorded as a **new ADR** that **supersedes** the earlier one. The earlier ADR's status is updated to Superseded with a pointer forward.

The 2026-05-29 multi-provider spec's routing and rate-limit decisions are **Superseded by [ADR-0014](./0014-admission-separate-from-routing.md) and [ADR-0015](./0015-deterministic-routing.md)**.

## Index

| # | Title | Status |
|---|-------|--------|
| [0000](./0000-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0001](./0001-lean-orchestrator-no-file-bodies.md) | Lean orchestrator, no file bodies | Accepted |
| [0002](./0002-no-trust-in-maker-self-report.md) | No trust in maker self-report | Accepted |
| [0003](./0003-mechanical-first-model-last.md) | Mechanical-first, model-last | Accepted |
| [0004](./0004-bound-the-seed-input-ceiling.md) | Bound the seed-input ceiling | Accepted |
| [0005](./0005-accuracy-throughput-over-equi-utilization.md) | Accuracy+throughput over equi-utilization | Accepted |
| [0006](./0006-tiered-maker-pool-bounded-escalation.md) | Tiered maker pool, bounded escalation | Accepted |
| [0007](./0007-author-separation.md) | Author separation | Accepted |
| [0008](./0008-red-adequacy-mutation-red-cause.md) | RED adequacy via mutation + RED-cause | Accepted |
| [0009](./0009-green-full-suite-independent.md) | GREEN full-suite independent | Accepted |
| [0010](./0010-non-functional-characterization-gate.md) | Non-functional characterization gate | Accepted |
| [0011](./0011-hard-gate-decomposition-into-briefs.md) | Hard-gate decomposition into briefs | Accepted |
| [0012](./0012-contract-conformance-via-ast-drop-pact.md) | Contract conformance via AST, drop Pact | Accepted |
| [0013](./0013-worktree-per-maker-isolation.md) | Worktree-per-maker isolation | Accepted |
| [0014](./0014-admission-separate-from-routing.md) | Admission separate from routing | Accepted |
| [0015](./0015-deterministic-routing.md) | Deterministic routing (supersedes binary route) | Accepted |
| [0016](./0016-cost-skip-claude-inline.md) | Cost-skip CLAUDE_INLINE | Accepted |
| [0017](./0017-sensitivity-tag-data-boundary.md) | Sensitivity-tag data boundary | Proposed |
| [0018](./0018-segmented-heartbeat.md) | Segmented heartbeat | Proposed (scoped) |
| [0019](./0019-caveman-compression-paid-boundaries.md) | Caveman compression at paid boundaries | Proposed |
| [0020](./0020-mcp-unifying-integration-surface.md) | MCP unifying integration surface | Proposed but Deferred (Phase 2) |
