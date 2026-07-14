# ADR-0039: Adaptive confidence-scored routing (live per-(model, task-type) feedback)

- **Status:** Accepted
- **Date:** 2026-07-13
- **Extends:** [ADR-0015](./0015-deterministic-routing-supersedes-binary-route.md) (deterministic routing), [ADR-0006](./0006-tiered-maker-pool-bounded-escalation.md) (tiered escalation), [ADR-0016](./0016-cost-skip-claude-inline.md) (cost-skip ROI).
- **Requirements:** REQ-ROUTE-ADAPTIVE (new)

## Context

Routing today (ADR-0015) is deterministic but **coarse and session-static**: `capability_profiles.json` holds thresholds recalibrated offline by the bench, and the only live signal is the blunt "gemma4 accuracy < 70% for task type → claude_agent" rule. It does not learn *within a run*: a model that just failed three `code_edit` units in this session is routed the same as one that aced them.

The user's decision (design-review Q9): routing should be a **dynamic, ROI-based evaluation** where **each completed task raises or lowers a confidence score per model/system**, and routing **prioritizes by that live score** with tiered escalation. This is stronger than a static table and stronger than the coarse 70% rule.

## Decision

Add a **live confidence score** per `(model, task_type)` that the router consults as a first-class input:

- **Score state.** For each `(model, task_type)` keep a confidence in [0,1], seeded from the offline `capability_profiles.json` and persisted in the session store (`session_stats` SQLite). Bench recalibration sets the seed; the live loop moves it.
- **Update rule.** Every gate outcome nudges the score: mechanical ACCEPT ↑, mechanical FAIL / repair-exhaustion / escalation ↓. Use a bounded exponential update (e.g. `s ← s + α(outcome − s)`, small α) so one result never swings routing wildly and recent results weigh more than stale ones. Scoped per task-type — good at `code_gen` ≠ good at `cross_file_refactor`.
- **Routing = deterministic given the scores.** The router still produces a deterministic choice (ADR-0015 preserved): among admissible models for a task-type, rank by `confidence × capability / cost` (the ROI), pick the top; ties broken deterministically. Determinism is *given the current score vector* — same scores + same task ⇒ same route, replayable.
- **Tiered escalation on the same axis.** A FAIL both lowers the maker's score AND escalates the retry to the next band up (local → OSS → free-cloud → paid-Claude-class), consistent with ADR-0006. A model whose score for a task-type drops below a floor is skipped for that type until re-proven (a probe path can re-earn it).
- **Cold start.** No history ⇒ fall back to the offline profile seed (ADR-0016 ROI still applies). The live score only overrides once enough samples exist (min-sample guard) to avoid one bad draw blacklisting a model.

## Considered alternatives

- **Static role→model table** — Rejected (user Q11): can't adapt to a model regressing or a repo where a model underperforms; the whole point of conductor's router is that it's not hard-wired.
- **Keep coarse 70%-per-type rule (ADR-0015 as-is)** — Pros: simplest. Cons: binary, session-static, ignores ROI and recency. The user asked for finer, live adaptation.
- **Full contextual bandit / RL routing** — Pros: theoretically optimal exploration/exploitation. Cons: opaque, hard to make replayable/deterministic, over-engineered for the signal volume here. Rejected — the bounded-update + deterministic-rank is auditable and enough.

## Consequences

- **Positive:** routing self-corrects within a run; a model on a hot/cold streak is used/avoided accordingly; ROI (confidence × capability / cost) is the single ranking currency; still deterministic-and-replayable given the score vector.
- **Negative:** more state to persist + reason about; needs a min-sample guard and bounded α or it thrashes; scores are per-session unless persisted across sessions (a choice — default per-session, seeded from bench). The confidence value is a heuristic input to routing, NOT a gate — it never decides correctness (Law 2 intact).
- **Neutral:** the offline bench (`gemma4-bench`) stays as the seed source; the live loop layers on top.

## Related

[ADR-0015](./0015-deterministic-routing-supersedes-binary-route.md) (extended — routing stays deterministic given scores), [ADR-0006](./0006-tiered-maker-pool-bounded-escalation.md) (escalation bands), [ADR-0016](./0016-cost-skip-claude-inline.md) (ROI cost-skip), [ADR-0005](./0005-accuracy-throughput-over-equi-utilization.md) (accuracy+throughput objective the score serves), `harness/capability_profiles.json`, `harness/session_stats.py`.
