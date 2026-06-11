# ADR-0023: Development tracker / progress board — event-sourced, harness-derived, pluggable render sinks

- **Status:** Proposed
- **Date:** 2026-06-11
- **Requirements:** REQ-OBS5, REQ-OBS6, REQ-OBS7, NFR-TRACK-1

## Context

The user and the orchestrator need to track the workflow live: the divided tasks (the DAG of work units in topo waves) and per-unit progress across the different maker agents — a program-manager view for the human and a system-leader view for the orchestrator. The data pieces are planned (run-ledger REQ-OBS2, heartbeat REQ-OBS1, regression ledger REQ-OBS3) but there is no unified board projecting them.

### Prior art (researched, all off-main-thread)

Four agent-kanban systems were evaluated as candidate external dependencies: **vibe-kanban** (BloopAI), the **Hermes Kanban** board + **GumbyEnder/hermes-kanban**, **saltbo/agent-kanban**, and **KaibanJS**. The verdict was unanimous: **borrow patterns, do not adopt as a dependency.** Reasons: wrong language (Rust/TypeScript for three of four), each brings its own dispatcher/execution model that would duplicate conductor's router/healer, coarse 4–5-state vocabularies that cannot express RED/GREEN/HEALING/ESCALATED/INTERVENE, mostly no topo-wave scheduling (conductor already has `dag.py`), plus licensing (FSL) and one project sunsetting.

But all four independently converge on the same architecture, which validates and refines this decision:
1. an **append-only event log as the single source of truth; every view is a pure projection** (Hermes `task_events`, KaibanJS `workflowLogs`, vibe DB→JSON-patch, agent-kanban `task_actions`);
2. a **two-layer state split** — coarse human/PM column vs fine machine/per-run state;
3. **harness-derived terminal status, never maker self-report** (process exit / PR merge / dispatcher+PID liveness / framework callbacks);
4. **DAG via parent→child + cycle detection + ready/wave gating**;
5. **per-attempt run rows** (Hermes `task_runs`) rather than overwriting status;
6. a **live event stream as the render-sink hook**, with rendering to external PM tools (e.g. the hermes-kanban→Obsidian bridge) as a legitimate downstream sink.

## Decision

Build a **portable, event-sourced tracker as a built-in core** (no conductor-logic coupling, like the optimizer) with **pluggable render sinks**, adopting the six validated patterns:

- **Event log is the source of truth.** `harness/tracker/` appends typed events (dispatch · red · green · heal · escalate · accept · fail · intervene · heartbeat) to the run-ledger (SQLite, out-of-worktree per S8). The **board is a pure projection** over events — never a separately-maintained, hand-updated status (which could lie).
- **Two-layer state:** a fine per-unit lifecycle `UnitState` (PENDING → READY → DISPATCHED → RED_OK → IMPL_DISPATCHED → GREEN_PENDING → ACCEPTED | HEALING(n) | ESCALATED(tier) | INTERVENE | FAILED) plus a coarse human-facing column mapping (Backlog/Doing/Review/Done/Blocked). Transitions are a **declarative table** (from → to, who may trigger) so legality is checked, not assumed.
- **Per-attempt run records (REQ-OBS7):** heal/escalate attempts are appended as **distinct run rows** (attempt n, maker, outcome, summary), not status overwrites — the attempt history is preserved, like Hermes `task_runs`.
- **Harness-derived (NFR-TRACK-1):** a unit is `ACCEPTED` only because the harness's *gate* passed, not because a maker claims done; heartbeat `self_on_track` is shown as a *liveness hint, marked unverified*. The board cannot be gamed into showing green work that isn't.
- **Dual audience, one truth:** `render("text")` / `render("json")` for the human PM view (baked in, stdlib); `board()` returns the compact current-state dict for the orchestrator to decide what to dispatch / where to INTERVENE — **lean**: it tracks via the board, not by re-reading agent transcripts (a REQ-O1 win).
- **Pluggable render sinks (REQ-OBS6):** `text`/`json` baked in (zero deps); `rich`/`textual` TUI, an **MCP resource**, a **webhook**, and an **external-PM-board bridge** (Obsidian/Trello/Hermes-board) are **opt-in sinks** subscribing to the event stream — this is the "external dependency" path: external tools are downstream *views*, never the engine.
- **Reports, never gates:** the tracker is observability only — it must not influence gating decisions. Gates decide; the tracker records.

## Considered alternatives

- **Adopt an existing agent-kanban as the dependency** (vibe/Hermes/agent-kanban/KaibanJS) — Pros: ready UI. Cons (all four): wrong language or brings its own dispatcher (duplicates conductor), coarse state vocab, mostly no topo-waves, licensing/sunsetting. Rejected — borrow patterns instead.
- **No tracker; rely on logs/the run-ledger directly** — Pros: nothing new. Cons: no live dual-audience view; orchestrator must re-read transcripts (context bloat). Rejected.
- **Maker-self-reported progress board** — Pros: trivial. Cons: gameable, violates the harness-derived invariant. Rejected.

## Consequences

- **Positive:** live PM + orchestrator visibility from one ground-truth log; orchestrator stays lean (tracks via `board()`, not transcripts); external PM tools integrate as opt-in sinks without coupling; harness-derived rule makes the board trustworthy.
- **Negative (honest):**
  - hot-path write overhead — every transition appends an event (mitigate: batch/async append);
  - reinforces the S8 "move `session_stats.db` out of the worktree" fix from optional → load-bearing (shared store contention);
  - the render-sink contract becomes public API to maintain (like the optimizer's);
  - yet another subsystem — bounded by the "reports, never gates" rule so it cannot creep into correctness;
  - per-attempt run rows grow the ledger faster than status-overwrite would.
- **Neutral:** the tracker is a separable layer — extractable or disabled without touching decompose/gates.

## Related

[ADR-0011](./0011-hardgate-decomposition-briefs.md)/`dag.py` (the DAG + waves it projects), [ADR-0013](./0013-worktree-per-maker-isolation.md) (db out of worktree), [ADR-0018](./0018-segmented-heartbeat.md) (heartbeat/stall feeds liveness), [ADR-0021](./0021-pluggable-context-optimizer.md) (same pluggable-sink pattern), [ADR-0002](./0002-no-trust-maker-self-report.md) (harness-derived, not self-report). REQ-OBS5/OBS6/OBS7, NFR-TRACK-1.
