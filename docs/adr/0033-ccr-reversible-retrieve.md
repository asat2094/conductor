# ADR-0033: CCR reversible-retrieve as an optimizer capability

- **Status:** Accepted
- **Date:** 2026-06-30
- **Requirements:** REQ-E4
- **Borrowed from:** headroom (CCR — compress, keep original locally, retrieve on demand).

## Context

The pluggable optimizer (ADR-0021) compresses prose at paid-reader boundaries, but compression is lossy: once the orchestrator's verdict/tool-output is compressed, detail is gone. headroom's CCR (Compress-Cache-Retrieve) keeps the original locally and lets the reader call a `retrieve(handle)` tool to pull the full text on demand. This directly strengthens the lean-orchestrator principle (REQ-O1): the orchestrator can hold compressed verdicts/tool-output and retrieve the original *only* when a verdict genuinely needs scrutiny — bulk stays out of context, full fidelity stays one call away.

## Decision

Add **reversible-retrieve as an optional optimizer-backend capability** (the `retrieve()` method already stubbed on the `Compressor` protocol, ADR-0021):

- A reversible backend, when it compresses, stores the original keyed by a handle (local store, TTL); the compressed output carries the handle.
- The reader (orchestrator, or a paid tier-2 maker) can `optimizer.retrieve(handle)` to get the original on demand.
- **Strict guardrail:** retrieve operates only on the *read/optimize* path — orchestrator-facing verdicts, tool-output, briefs. It is **never** applied to gate evidence (Law 1): the mechanical gates always read the real on-disk file, never a compressed-then-retrieved proxy.
- Reversibility is per-backend (the `null`/`caveman` backends return `None`; a headroom/CCR backend implements it). Degrade-clean: if the store is gone (TTL expired) retrieve returns `None` and the reader falls back to the compressed text.

## Considered alternatives

- **Lossy compression only (status quo)** — Pros: simplest. Cons: compressed detail is unrecoverable; orchestrator can't drill into a borderline verdict. Rejected (this is additive, opt-in).
- **Never compress orchestrator-read content** — Pros: full fidelity always. Cons: forgoes the token saving CCR makes safe. Rejected.

## Consequences

- **Positive:** lean orchestrator gets lossless-on-demand — compress aggressively, retrieve rarely; full fidelity available without holding bulk in context.
- **Negative:** adds a local original-store with TTL/cleanup (state lifecycle, overlaps tracker/worktree state); a retrieve after TTL expiry loses the original (degrade to compressed); reversibility is only as good as the store's retention.
- **Neutral:** opt-in per backend — the baked-in null/caveman path stays non-reversible and dependency-free.

## Related

[ADR-0021](./0021-pluggable-context-optimizer.md) (the facade + `retrieve()` protocol method), [ADR-0001](./0001-lean-orchestrator-no-file-bodies.md) (lean orchestrator — CCR's direct beneficiary), [ADR-0002](./0002-no-trust-maker-self-report.md) (never on gate evidence). REQ-E4.
