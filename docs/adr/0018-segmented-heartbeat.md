# ADR-0018: Segmented heartbeat — wall-clock stall detection now, mid-flight corroboration deferred

- **Status:** Proposed (scoped)
- **Date:** 2026-06-09
- **Requirements:** REQ-OBS1

## Context

A delegated unit can stall: the maker hangs, the provider silently drops the connection, or generation never terminates. A stalled unit burns wall-clock and budget while producing nothing. We want liveness detection that early-kills stalls.

A richer design corroborates progress mid-flight — observing in-file checkpoints and an action/self-on-track signal, cross-checked against a partial AST of the file as it is written. That design assumes a maker that streams or runs as a multi-turn agent, exposing intermediate state. The current maker pool does not: makers are single-shot blocking REST calls that write the target file exactly once, at the very end. There is no mid-flight state to observe, so corroboration is unbuildable against today's makers.

## Decision

Scope v1 liveness to wall-clock STALL detection plus early-kill only: detect a heartbeat gap against the stage latency budget and kill the unit when the gap exceeds the threshold.

Full mid-flight in-file checkpoint corroboration — action/self-on-track signal cross-checked with partial-AST corroboration — requires an agentic or streaming maker and is DEFERRED to the phase-2 ACP adapter, where such makers exist.

When a self-on-track signal eventually exists, it is never a gate: it is maker self-report, and under Law 1 self-report is never gate evidence. It may at most be an advisory input to stall heuristics.

This realizes REQ-OBS1 as scoped.

## Considered alternatives

### A. Full streaming heartbeat now
- Pros: would catch stalls earlier and corroborate genuine progress vs. idle hangs.
- Cons: current makers do not stream and expose no mid-flight state.
- Why rejected/deferred: unbuildable in v1 against single-shot REST makers; deferred to the phase-2 ACP adapter.

### B. No liveness at all
- Pros: nothing to build.
- Cons: stalls are invisible; wall-clock and budget burn with no result.
- Why rejected: stalls must be detectable and killable.

### C. Poll a provider status API
- Pros: provider-authoritative progress, if available.
- Cons: free tiers do not offer a per-call status API.
- Why rejected: not offered by the free tiers we target.

## Consequences

### Positive
- Stalls are detected and killed in v1 with no dependency on maker internals.
- The deferral keeps the richer design honest — it lands only when streaming makers make it real.

### Negative
- Wall-clock detection is coarse: a maker making slow-but-real progress can be killed, and a maker that hangs just under the threshold is not caught until the budget gap trips.
- No corroboration that elapsed time corresponds to genuine work until the phase-2 adapter.

### Neutral
- Any future self-on-track signal stays advisory, never a gate, preserving Law 1.

## Related
- ADR-0002 (no trust in maker self-report — Law 1)
- ADR-0020 (MCP/ACP integration surface — where the streaming maker arrives)
