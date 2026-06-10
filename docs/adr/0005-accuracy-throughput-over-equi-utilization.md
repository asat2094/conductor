# ADR-0005: Prioritize accuracy + throughput over maker equi-utilization

- **Status:** Proposed
- **Date:** 2026-06-09
- **Requirements:** REQ-R1, REQ-R2 (routing objective)

## Context

The maker pool could be optimized for several objectives that conflict CAP-style: best-capability-per-task (accuracy), fastest batch drain (throughput), or even load across all makers (equi-utilization). Only two of these can be primary; the user explicitly chose **accuracy + throughput**. Equi-utilization is attractive (keeps the free pool warm) but pulls against routing each unit to its most-capable maker.

## Decision

Optimize for **accuracy + throughput**. Do **not** treat equal maker utilization as a goal — an even-enough spread falls out naturally from one-task-per-maker scheduling (a busy maker is skipped, so work spreads without being forced to). Capability gates eligibility; among eligible makers, dispatch concurrently to drain the batch.

## Considered alternatives

- **Equi-utilization scheduling (round-robin across capable makers)** — Pros: maximal spread, no idle providers, even rate-limit pressure. Cons: concentrates neither accuracy (may pick a weaker eligible maker) nor drain speed; optimizes a metric the user does not care about. Rejected.
- **Pure accuracy-first (always the single best maker)** — Pros: highest per-unit accuracy. Cons: serializes onto one maker, starves throughput under a batch, and rate-limits that maker. Rejected.
- **Pure throughput-first (any available maker)** — Pros: fastest drain. Cons: ignores capability, raises gate-failure/heal churn. Rejected.

## Consequences

- **Positive:** units go to capable makers and fly concurrently; throughput scales with eligible-pool size without sacrificing per-unit accuracy.
- **Negative:** some makers may idle while the best/diverse makers are busy — accepted, since utilization is not a goal.
- **Neutral:** "throughput" is bounded by the concurrency cap (NFR-PERF-2), not by pool size alone.

## Related

ADR-0006 (tiered pool), ADR-0014 (admission spreads load reactively under throttle). REQ routing objective.
