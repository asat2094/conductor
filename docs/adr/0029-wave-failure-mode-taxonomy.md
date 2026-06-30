# ADR-0029: Wave failure-mode taxonomy + concurrency cap

- **Status:** Proposed
- **Date:** 2026-06-30
- **Requirements:** REQ-I5, NFR-PERF-3
- **Borrowed from:** microsoft/conductor (`fail_fast | continue_on_error | all_or_nothing`, `max_concurrent`).

## Context

`run_dag` dispatches a wave of independent units, then submits accepted ones to the merge queue. But the *failure semantics of a wave* are implicit: what happens to the rest of a wave when one unit fails? Today it just continues and tallies. Different builds want different policies, and there is no crisp vocabulary or concurrency bound for the parallel dispatch.

## Decision

Adopt an explicit, named failure-mode taxonomy on the wave executor, plus a concurrency cap:

- **`fail_fast`** — first unit failure aborts the wave (and, with DAG atomicity, discards the build). For builds where any failure means stop.
- **`continue_on_error`** — failed units are recorded FAILED; the rest of the wave proceeds; finalize decides ff/discard (current behavior — becomes the explicit default).
- **`all_or_nothing`** — the whole wave is accepted only if every unit passes; any failure discards the wave's work.
- **`max_concurrent`** — cap simultaneous in-flight makers per wave (composes with admission's per-provider AIMD cap, ADR-0014, and worktree isolation, ADR-0013).

This is pure scheduling policy — it changes *which units run / how failure propagates*, never *how correctness is judged* (the mechanical gates are untouched).

## Considered alternatives

- **Single implicit policy (status quo)** — Pros: simplest. Cons: no control over failure propagation; unclear semantics. Rejected (continue_on_error becomes the named default).
- **Per-unit failure policy** — Pros: maximal flexibility. Cons: over-engineered; failure propagation is naturally a wave/build concern. Rejected.

## Consequences

- **Positive:** crisp, configurable failure semantics; `max_concurrent` bounds resource use and composes with existing caps; named modes make build intent explicit.
- **Negative:** three modes + a cap = more config surface and test matrix; `all_or_nothing` can waste a wave's good units on one failure (the cost of its guarantee).
- **Neutral:** orthogonal to merge-queue atomicity (ADR-0012) — failure-mode governs the wave, atomicity governs the whole-DAG ff/discard.

## Related

[ADR-0012](./0012-contract-conformance-ast-drop-pact.md)/merge-queue (DAG atomicity), [ADR-0013](./0013-worktree-per-maker-isolation.md) (isolation enables safe concurrency), [ADR-0014](./0014-admission-separate-from-routing.md) (per-provider concurrency). REQ-I5, NFR-PERF-3.
