# ADR-0013: One git worktree per maker for parallel-dispatch isolation

- **Status:** Accepted
- **Date:** 2026-06-09
- **Requirements:** REQ-I1, REQ-I2, REQ-I4, NFR-PERF-2

## Context

Conductor co-dispatches multiple makers concurrently (NFR-PERF-2 caps the pool and requires co-dispatched units to have disjoint `writes_files`). Each maker edits and creates files, the harness re-runs the unit test plus the full suite, and accepted units are rebased onto a single-writer integration branch (REQ-I1/REQ-I2).

If concurrent makers share one working directory, they interfere: overlapping writes, a single shared test run, contended ports/databases/temp paths, and a dirty tree that makes per-unit rebase and the whole-DAG assembly gate (REQ-I4) impossible to reason about. We need each in-flight unit to have a clean, isolated workspace that still carries real git semantics, so a GREEN unit can be rebased and the integration branch can be fast-forwarded atomically.

The build is atomic at the DAG level (REQ-I2): the integration branch is disposable and only fast-forwards to the target after the assembly golden gate passes. Isolation must support that disposability.

## Decision

Each concurrently-dispatched maker runs in its **own git worktree**:

- The worktree **path is derived from the subtask id, not a timestamp**, so a run is reproducible and a given unit always maps to the same workspace.
- Each worktree gets an **env-injected isolated port / database / tmpdir** so concurrent units never contend on shared runtime resources.
- All **stages of one unit share that unit's worktree** (RED, GREEN, mutation, refactor) — a unit is not scattered across workspaces.
- **Heal attempts reuse the unit's existing worktree** — no new-id worktrees are spun up mid-heal, preserving the subtask-id↔worktree mapping.
- **Merge is a single reduce stage:** accepted units are integrated into one single-writer integration branch, not merged ad hoc per worktree.
- **`session_stats.db` lives OUTSIDE any worktree** so the delegation/run ledger is never duplicated, reset, or clobbered when worktrees are created or torn down.
- Worktrees are **torn down on a terminal verdict** (accept or permanent fail), and a **crash-sweep** reclaims orphaned worktrees left by a killed run.

## Considered alternatives

### A. Shared working directory guarded by locks
- **Pros:** no extra disk; simplest filesystem model.
- **Cons:** locking serializes makers that could run in parallel; even with disjoint `writes_files`, a single test run and shared runtime resources cause contention; a shared dirty tree breaks clean per-unit rebase.
- **Why rejected:** defeats parallel dispatch and contradicts the disjoint-write co-dispatch design.

### B. Plain tmpdir copy per maker (no git)
- **Pros:** cheap isolation; trivial teardown.
- **Cons:** loses git semantics — no clean rebase onto the integration branch, no fast-forward assembly, no merge-queue reduce stage.
- **Why rejected:** the integration/atomicity model depends on real git operations that a flat copy cannot provide.

### C. Container per maker
- **Pros:** strongest isolation (filesystem, network, process).
- **Cons:** heavier startup and resource cost; more operational surface for a v1 local harness.
- **Why deferred:** worktree + env injection gives sufficient isolation for v1; containerization can layer on later if stronger boundaries are needed.

## Consequences

### Positive
- Concurrent makers cannot corrupt each other's files or runtime state; the disjoint-write co-dispatch model becomes safe in practice.
- Subtask-id-derived paths make runs reproducible and let heal reuse the same workspace without churn.
- Real git worktrees enable clean per-unit rebase, the single-writer merge queue, and atomic fast-forward of the integration branch.
- Keeping the stats DB outside the worktree protects the ledger across create/teardown.

### Negative
- Disk and IO cost scale with fan-out — each worktree is a checkout.
- Injected isolated ports draw from a finite range; at high fan-out the port range can be exhausted and must be bounded against `pool_size`.

### Neutral
- Teardown and crash-sweep add lifecycle management the harness must own.
- Exact path templates, port-range allocation, and sweep cadence are design-level details in design.md, not fixed here.

## Related
- REQ-I1 (rebase onto integration branch, single-writer merge queue)
- REQ-I2 (DAG-level atomicity; disposable integration branch)
- REQ-I4 (assembly golden gate over the merged surface)
- NFR-PERF-2 (pool cap; disjoint-write co-dispatch)
- ADR-0012 (seam conformance at the merge/reduce stage)
- ADR-0014 (admission layer governs how many makers are in flight)
