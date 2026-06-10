# ADR-0014: An admission layer between routing and dispatch

- **Status:** Proposed
- **Date:** 2026-06-09
- **Requirements:** REQ-A1, REQ-A2, REQ-A3

## Context

The 2026-05-29 multi-provider design folded live operational state into routing: a provider was `FREE`/`BUSY`, rate limits were handled reactively by falling through to the *next* provider on a 429, and there was no cooldown and no run-level cost ceiling. That design has two structural problems:

- **Reactive escalation cascades to paid makers.** Treating any 429/timeout as "skip to next provider" means a transient throttle on a free maker pushes the unit onto a more expensive maker — the opposite of the cost goal. Under load this cascades the whole batch toward paid makers.
- **Mixing live state into routing breaks reproducibility.** Routing must be a pure function of `(features, pinned profile snapshot, seed)` (REQ-R3, ADR-0015). If live availability and rate-limit state feed the routing decision, the recorded decision is no longer replayable from the ledger.

We need a place for live, time-varying operational concerns that is *not* the routing function.

## Decision

Introduce an **admission layer that sits between routing and dispatch**. Routing decides *which maker should do the work* deterministically; admission decides *whether and when that maker may actually be called right now*. The admission layer owns:

- **Per-provider adaptive concurrency limiter (AIMD / gradient style):** on observed throttle, **multiplicatively reduce that provider's in-flight cap** rather than escalating the unit to a different (paid) maker (REQ-A1).
- **Token-bucket rate control** per provider, to pace calls within known limits.
- **Circuit breaker** per provider, to stop hammering a provider that is failing.
- **Retryable-error allowlist:** a retryable error (429 / timeout / 5xx) **retries the SAME maker** with backoff; only a quality-gate miss or exhausted retries escalates (REQ-A2).
- **Per-run cost ceiling:** when the ceiling is reached, admission **blocks or queues** rather than continuing to balloon onto paid makers (REQ-A3).

All of this live state lives in the admission layer, **not** in routing — so the recorded routing decision stays a pure, replayable function (REQ-R3).

## Considered alternatives

### A. Escalate to the next (paid) provider on any 429 — the 2026-05-29 reactive model
- **Pros:** trivial; no per-provider state to track.
- **Cons:** a transient throttle on a free maker silently promotes the unit to a costlier maker; under load the whole batch cascades to paid makers.
- **Why rejected:** this *is* the runaway-cost problem; it inverts the cost priority.

### B. Fixed per-provider concurrency cap
- **Pros:** simple, bounded, predictable.
- **Cons:** a static cap cannot respond to a live throttle — it either sits too low (wasting free capacity) or too high (inviting sustained 429s).
- **Why rejected:** does not adapt to observed throttle, which is the whole point of admission.

### C. No per-run cost ceiling
- **Pros:** never blocks; maximizes throughput.
- **Cons:** with escalation in play, a bad run can keep promoting units to paid makers without bound.
- **Why rejected:** allows runaway paid escalation; a hard ceiling that blocks/queues is required.

## Consequences

### Positive
- Transient throttles are absorbed by shrinking a provider's in-flight cap and retrying the same maker, instead of escalating cost.
- Routing stays deterministic and replayable because all live state is quarantined in admission (REQ-R3).
- The per-run cost ceiling makes paid escalation bounded and predictable.

### Negative
- A new layer adds operational complexity and per-provider state (limiter, bucket, breaker) that must be maintained and observed.
- When the cost ceiling or shrunken concurrency caps bind, units **queue** — admission trades latency for cost control under pressure.

### Neutral
- Admission and routing become distinct responsibilities with a clean handoff; the deterministic routing contract is defined in ADR-0015.
- AIMD constants, bucket sizes, breaker thresholds, and the cost-ceiling value are tunables that live in design.md, not here.

## Related
- REQ-A1 (adaptive concurrency limiter; multiplicative throttle reduction)
- REQ-A2 (retry the same maker on retryable errors)
- REQ-A3 (per-run cost ceiling; block/queue instead of escalate)
- REQ-R3 (routing determinism; live state lives in admission)
- ADR-0015 (deterministic routing; supersedes the 2026-05-29 routing/rate-limit/escalation decisions)
- ADR-0016 (cost-skip meta-gate in routing)
