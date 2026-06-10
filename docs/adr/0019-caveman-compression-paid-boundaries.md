# ADR-0019: Caveman compression as a cross-cutting overlay at paid-token boundaries

- **Status:** Superseded by [ADR-0021](./0021-pluggable-context-optimizer.md) — caveman is now one backend behind the pluggable optimizer facade, not the fixed engine. Its prose-only / never-gate-evidence guidance survives as the facade's protect-list invariant.
- **Date:** 2026-06-09
- **Requirements:** REQ-E1, REQ-E2, REQ-E3

## Context

Tokens cost money only at paid boundaries — namely the orchestrator's own output and the bounded tier2 Claude calls. Free-cloud and local makers carry no marginal token cost, so compressing their input saves latency and eases rate limits but saves no money. We want an efficiency mechanism that targets dollars without endangering correctness, and that does not become a correctness gate.

Compression is dangerous if applied to material that must stay byte-exact: code, tests, context slices, structured contract fields, and any gate-parsed evidence. Mangling any of those would corrupt the very artifacts the gates depend on.

## Decision

Treat caveman compression as a cross-cutting overlay, never a gate, applied only at paid-token boundaries:

- The orchestrator emits in a terse output mode (near-free reduction of its own output tokens; reasoning untouched).
- A caveman-compress pass runs on repeatedly-read prose artifacts, where the compression cost amortizes over re-reads, and validation keeps code, URLs, and paths byte-exact.
- Verdicts and briefs sent to tier2 Claude are kept terse.

Compression applies to PROSE ONLY. It is never applied to code, tests, context slices, contract structured fields, or gate evidence. Sensitive paths are refused (shared with ADR-0017).

Free-maker input compression is treated as a latency and rate-limit win, not a dollar win, and is out of scope for this cost decision.

Inspiration and the validation approach are drawn from the external caveman project (github.com/juliusbrussee/caveman).

This realizes REQ-E1 (orchestrator output mode), REQ-E2 (compress repeatedly-read prose with byte-exact validation), and REQ-E3 (the compression guard and sensitive-path refusal).

## Considered alternatives

### A. Compress everything, including maker input
- Pros: maximal token reduction across the whole pipeline.
- Cons: free makers carry no token cost, so there is no dollar saving; compressing code risks corrupting it.
- Why rejected: no money saved on free-maker input, and real risk to code correctness.

### B. No compression
- Pros: zero added machinery; nothing can be mangled.
- Cons: leaves paid output tokens unreduced.
- Why rejected: leaves output tokens on the table at the exact boundaries where they cost money.

### C. Custom in-house summarizer
- Pros: full control over the algorithm.
- Cons: reinvents an existing, validated tool.
- Why rejected: reinvents caveman with no added value.

## Consequences

### Positive
- Targets dollars precisely — only paid boundaries are compressed.
- Byte-exact validation protects code, URLs, and paths; the overlay never becomes a gate.

### Negative
- Compression itself costs a Claude call; it only pays off on repeatedly-read artifacts where the cost amortizes.
- Depends on an external repository's validation logic, which must be vendored and pinned to avoid drift and supply-chain risk.

### Neutral
- Free-maker input compression remains available purely as a latency/rate-limit lever.

## Related
- ADR-0017 (sensitivity boundary — shares the sensitive-path refusal)
- ADR-0001 (lean orchestrator, no file bodies)
- ADR-0016 (cost-skip inline)
