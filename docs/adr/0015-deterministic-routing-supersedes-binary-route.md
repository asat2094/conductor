# ADR-0015: Deterministic routing — supersedes the 2026-05-29 binary route()

- **Status:** Accepted (Supersedes the 2026-05-29 multi-provider spec's routing, rate-limit, and escalation decisions) — **extended by [ADR-0039](./0039-adaptive-confidence-scored-routing.md)**: routing stays deterministic but now consumes a live per-(model, task-type) confidence score (ROI = confidence × capability / cost).
- **Date:** 2026-06-09
- **Requirements:** REQ-R2, REQ-R3

## Context

The 2026-05-29 multi-provider harness design (`docs/superpowers/specs/2026-05-29-multi-provider-harness-design.md`, status Approved) defined routing as `rank_providers()` over live state. It carried three decisions that we now reverse:

- **Untracked-cell accuracy default of 1.0 (and 0.7 in the ranker).** The legacy `route()` defaulted an untracked `(provider, task_type)` cell optimistically. An optimistic default means a never-tested maker looks maximally trustworthy and gets work it has not earned — a cold-start trust bug.
- **Live state inside routing.** Provider `FREE`/`BUSY` state and reactive rate-limit fallthrough were part of the routing decision, so the recorded decision depended on wall-clock availability and could not be replayed.
- **Reactive rate-limit with no cooldown, and `EscalateToClaudeError` raised to the main thread.** A 429 fell straight to the next provider, and exhaustion threw an escalation error up to the orchestrator's main thread.

REQ-R2 and REQ-R3 require the opposite: no optimistic cold-start default, and a routing decision that is a pure, replayable function. This ADR records the superseding decision; the live operational concerns it removes from routing are relocated to the admission layer (ADR-0014).

## Decision

Routing is a **pure function of `(features, pinned profile snapshot, seed)`** — given the same inputs it always yields the same decision, and that decision is replayable from the run-ledger (REQ-R3).

- The **untracked-cell accuracy default of 1.0 is killed.** An untracked `(provider, task_type)` cell uses a **tier-prior with calibrated uncertainty** seeded from the bench baseline; while uncertainty is wide, routing prefers Claude/verification rather than trusting an unproven maker (REQ-R2).
- **Live availability and rate-limit state move OUT of routing** into the admission layer (ADR-0014). Routing no longer reads `FREE`/`BUSY` and no longer reacts to 429s; the recorded routing decision is unaffected by live state.

This **supersedes** the 2026-05-29 spec's: binary `route()`; the 0.7/1.0 untracked-cell default; the reactive, no-cooldown rate-limit handling; and the `EscalateToClaudeError`-to-main-thread escalation. The 2026-05-29 spec should be marked **"Superseded by ADR-0014 / ADR-0015"**.

## Considered alternatives

### A. Keep the binary `route()` with the optimistic untracked-cell default
- **Pros:** no change; already implemented.
- **Cons:** an untracked cell defaulting high lets an unproven maker draw work it has not earned; the cold-start trust bug persists.
- **Why rejected:** it is the bug REQ-R2 exists to fix.

### B. Availability-aware routing (route on live FREE/BUSY + rate-limit state)
- **Pros:** routing reflects what is actually callable right now; avoids dispatching to a throttled provider.
- **Cons:** the decision depends on wall-clock state and is not reproducible from the ledger, violating REQ-R3.
- **Why rejected:** non-reproducible; the availability concern is moved to the admission layer (ADR-0014) where live state belongs.

## Consequences

### Positive
- Routing decisions are deterministic and replayable from `(features, pinned profile snapshot, seed)` (REQ-R3, NFR-REPRO-1).
- Cold-start no longer over-trusts unproven makers; a tier-prior with wide uncertainty steers early units to Claude/verification (REQ-R2).
- Clean separation: routing decides *who*, admission decides *whether/when* (ADR-0014).

### Negative
- Early in a profile's life, the calibrated-uncertainty prior routes more to Claude/verification, raising early-run cost until profiles tighten.
- Pinning a profile snapshot per decision adds a snapshot/seed bookkeeping obligation on the routing path and the ledger.

### Neutral
- Supersedes prior decisions rather than extending them; the 2026-05-29 spec must be re-labeled as superseded.
- The prior's distribution shape, the uncertainty-width policy, and tier-prior values are design-level tunables in design.md, not fixed here.

## Related
- REQ-R2 (no 1.0 untracked-cell default; tier-prior with calibrated uncertainty)
- REQ-R3 (routing determinism; live state lives in admission)
- NFR-REPRO-1 (decisions replayable from the run-ledger)
- NFR-MIG-1 (legacy `route()` 1.0-default tests migrated, not preserved)
- ADR-0014 (admission layer that now owns the relocated live state)
- 2026-05-29 multi-provider harness design (superseded by this ADR and ADR-0014)
