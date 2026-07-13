# ADR-0006: Tiered maker pool with bounded escalation 0→1→2, never straight to main

- **Status:** Accepted — **generalized by [ADR-0024](./0024-roles-are-model-assignments-context-isolation-invariant.md)**: the "tiers" are capability/cost/availability bands (local · OSS · free-cloud · paid-Claude-class) that *every* role draws from, and the invariant is bounded-context isolation, not model price. "Free vs paid" here is shorthand. **Extended by [ADR-0039](./0039-adaptive-confidence-scored-routing.md)**: band selection is driven by a live per-(model, task-type) confidence score; escalation both lowers the failing model's score and moves up a band.
- **Date:** 2026-06-09
- **Requirements:** REQ-O1, REQ-C4 (escalation target)

## Context

The token win is not "free vs paid" alone — it is **bounded maker context vs bloated main-thread history**. The main orchestrator resends full history every turn; a fresh subagent gets only its slice. So even a paid Claude subagent, given a bounded brief, saves tokens versus the orchestrator doing the unit inline with its accumulated context. The legacy harness offered only a gemma4-or-Claude binary, with `EscalateToClaudeError` bubbling failures straight back to the main thread.

## Decision

The maker pool is **tiered**: tier0 gemma4 local ($0) · tier1 free cloud ($0) · tier2 bounded Claude subagent (low $). Escalation flows **0→1→2** within the pool; failures do **not** bubble straight back to the main orchestrator. Only a fully-exhausted ladder (or an explicit INTERVENE per ADR-0004) reaches main.

## Considered alternatives

- **gemma4-or-Claude binary (legacy `route()`)** — Pros: simple. Cons: no cost gradient, no free-cloud tier, escalates to main on failure. Rejected (superseded by ADR-0015).
- **Flat pool, no tiers** — Pros: simplest routing. Cons: loses the cost gradient that makes cheap-first sensible. Rejected.
- **Escalate to main on any failure** — Pros: fast human-grade fix. Cons: re-loads bulk into main context, defeating the token-saving rationale. Rejected.

## Consequences

- **Positive:** cheap-first with graceful, bounded fallback; main context is protected; tier2 still saves vs inline.
- **Negative:** more routing machinery and per-tier capability tracking; tier2 spends real $.
- **Neutral:** "bounded Claude subagent" presumes a subagent spawn mechanism the orchestrator controls.

## Related

ADR-0005 (routing objective), ADR-0015 (supersedes binary route), ADR-0016 (CLAUDE_INLINE is a routing target, distinct from tier2 escalation). REQ-O1.
