# ADR-0028: Checkpoint / resume / replay over the event log

- **Status:** Accepted
- **Date:** 2026-06-30
- **Requirements:** REQ-OBS8, REQ-OBS9
- **Borrowed from:** microsoft/conductor (`checkpoint.py`, `web/replay.py`) — pattern only, MIT, re-implemented in our stack.

## Context

A distributed build is a long, multi-wave, multi-maker run. Today a failure (crash, interrupt, budget stop, a permanently-failing unit) loses all in-flight progress — there is no way to resume from the last good point, and no way to replay a past run for debugging. We already have the right substrate: `tracker_store` is an append-only event log. What is missing is snapshotting and reconstruction.

## Decision

Add checkpoint/resume/replay as pure infrastructure over the existing event log:

- **Checkpoint:** snapshot the run's reconstructable state (waves, per-unit verdicts, accepted set, merge-queue disposition) on failure, interrupt, budget-stop, and at a periodic interval. Snapshots are derived from the event stream — not a separate hand-maintained state — so they cannot diverge.
- **Resume:** restart a partial DAG run from the last checkpoint; already-ACCEPTED units are skipped, only PENDING/FAILED/in-flight units re-dispatch. Resume is a pure replay of the event log up to the checkpoint, then continue.
- **Replay:** reconstruct the full board/timeline of any past run from its JSONL log (for the orchestrator and for operators), with no re-execution.

This stays harness-derived (NFR-TRACK-1): checkpoints record what happened, they never alter a verdict on resume.

## Considered alternatives

- **No resume (status quo)** — Pros: simplest. Cons: long runs lose all progress on any failure; expensive re-work. Rejected.
- **Separately-maintained mutable state file** — Pros: simpler snapshot. Cons: can diverge from the event log (the lying-state risk ADR-0023 rejects). Rejected in favor of event-derived snapshots.

## Consequences

- **Positive:** long/expensive runs survive crashes and interrupts; past runs are debuggable by replay; resume re-uses ACCEPTED work instead of redoing it.
- **Negative:** snapshot cadence is new tuning debt (too frequent = overhead, too sparse = more lost work); resume correctness depends on every state-changing action being event-sourced (a side effect not in the log can't be replayed — discipline required); maker LLM output remains non-deterministic, so resume re-runs (not reproduces) un-accepted units.
- **Neutral:** snapshots live alongside the tracker DB (out of the work tree, ADR-0013).

## Related

[ADR-0023](./0023-development-tracker-progress-board.md) (event log substrate), [ADR-0013](./0013-worktree-per-maker-isolation.md) (db location), [ADR-0010](./0015-deterministic-routing-supersedes-binary-route.md) routing determinism is about routing, this is about run progress. REQ-OBS8/OBS9.
