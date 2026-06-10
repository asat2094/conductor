# ADR-0020: A single MCP server as the unifying work-distribution surface

- **Status:** Proposed but Deferred (Phase 2)
- **Date:** 2026-06-09
- **Requirements:** —

## Context

In phase 2 conductor is extended to run under a host harness rather than only the Claude main thread. Two candidate hosts are in view: OpenClaw, which consumes external tools via an mcpServers configuration over stdio plus HTTP/SSE, and Hermes, which is MCP-native. We also want to grow the maker pool with agentic backends (Codex, Claude, and OpenClaw ACP agents). The risk is fragmentation: a bespoke adapter per host and per maker family yields an N-by-M integration matrix that is expensive to build and maintain.

We need one surface that both hosts can consume and that can absorb additional maker backends without per-host glue.

## Decision

When the host-harness extension is built, conductor exposes a single MCP server over stdio as the work-distribution surface. Both hosts consume that one surface: OpenClaw via its mcpServers configuration (stdio plus HTTP/SSE) and Hermes natively. An optional ACP subprocess adapter (acpx-style) attaches Codex, Claude, and OpenClaw ACP agents to the maker pool.

MCP is chosen as the common surface because it is the intersection both hosts already support, whereas ACP is supported by only one path. ACP is therefore an additive maker-onboarding mechanism, not the integration surface.

This decision is Proposed but Deferred to Phase 2; it is recorded now to fix the integration direction before host-harness work begins.

## Considered alternatives

### A. Per-harness custom adapters
- Pros: each host gets a tailored integration.
- Cons: an N-integration matrix that grows with every host and maker family.
- Why rejected: unmaintainable integration count.

### B. ACP-only surface
- Pros: directly onboards agentic ACP makers.
- Cons: Hermes is MCP-native and OpenClaw consumes MCP, so ACP is not the common surface; only MCP is.
- Why rejected: MCP is the common denominator across both hosts, so MCP is preferred over ACP-only. ACP remains the optional maker-onboarding adapter.

### C. Raw subprocess / PTY scraping of agent CLIs
- Pros: works against any CLI without a protocol.
- Cons: brittle terminal scraping; exactly the problem dedicated adapters were built to avoid.
- Why rejected: acpx exists precisely to avoid PTY scraping.

## Consequences

### Positive
- One surface serves both hosts; no per-host integration matrix.
- ACP adds agentic makers without becoming the integration contract.

### Negative
- Adds an MCP server process and an optional ACP adapter to build and operate; full value lands only in phase 2.

### Neutral
- The decision is recorded ahead of implementation to anchor phase-2 design direction.

## Related
- ADR-0006 (tiered maker pool, bounded escalation)
- ADR-0013 (worktree-per-maker isolation)
- ADR-0018 (segmented heartbeat — the streaming/agentic maker arrives via this adapter)
