# ADR-0040: Ensemble as best-of-N maker strategy (gate-selected, not vote-on-correctness)

- **Status:** Accepted
- **Date:** 2026-07-13
- **Amends:** the ensemble-rejection note on [ADR-0004](./0004-bound-seed-input-ceiling.md) and the borrow-provenance note in the [ADR index](./README.md). Ensemble moves from "rejected" to "adaptable — one bounded form only."
- **Requirements:** REQ-ENSEMBLE-BESTOFN (new)

## Context

Ensemble / multi-model debate was previously **rejected** (borrow-provenance note, ADR-0004 amendment): running N models and having them *vote or debate on whether output is correct* is expensive and — decisively — **consensus ≠ correct**. A majority of models can agree on wrong code. That form reintroduces model-trust and is still rejected.

The user's decision (design-review Q11): ensemble is **adaptable** — but only in the one form that does not violate the core. The distinction that makes it safe: **who decides correctness.**

## Decision

Adopt ensemble ONLY as an **opt-in best-of-N maker strategy**, where the **mechanical gate selects the winner** — never a vote:

- **Fan-out.** For a designated (usually high-stakes or historically-hard) unit, spawn N maker candidates in parallel (different models, or the same model at different temperature/seed), each in its own bounded worktree (ADR-0013).
- **Gate selects, models do not vote.** Every candidate runs the full mechanical gate stack (RED/GREEN/mutation/lint/style). The **first candidate that passes all gates wins**; if several pass, the deterministic tiebreak applies (ADR-0038 inconclusive-only judge, or a mechanical preference like smallest diff). Candidates that fail are discarded. There is **no vote, no debate, no consensus** on correctness — the gate is still the sole arbiter (Law 2 intact).
- **Opt-in and cost-bounded.** Off by default (N=1). Enabled per-unit by the router when a unit's confidence score (ADR-0039) is low or its stakes are high, and bounded by the cost ceiling (ADR-0034) — best-of-N multiplies maker cost N×, so it's a targeted tool, not the default.
- **What stays rejected:** ensemble *voting/debate on correctness*, LLM-judge consensus as an accept gate, majority-rules acceptance. Those remain out (Law 1/2).

## Considered alternatives

- **Keep ensemble fully rejected (prior state)** — Pros: simplest, one maker per unit. Cons: forgoes a cheap-ish reliability lever for hard units where the gate can pick the good candidate for free. User chose to allow the bounded form.
- **Ensemble vote/debate on correctness** — Rejected (unchanged): consensus ≠ correct; reintroduces model-trust.
- **Always best-of-N** — Rejected: N× maker cost on every unit; wasteful where one maker passes. Opt-in, router-gated instead.

## Consequences

- **Positive:** higher first-pass success on hard/high-stakes units without trusting any model's opinion — the gate still decides, it just gets more candidates to choose from; composes cleanly with the confidence router (0039) and cost ceiling (0034).
- **Negative:** N× maker cost when enabled; more worktrees/concurrency to manage; needs a clear trigger policy so it doesn't creep to always-on. Mitigated by opt-in default + router/cost gating.
- **Neutral:** with N=1 (default) behavior is identical to today.

## Related

[ADR-0004](./0004-bound-seed-input-ceiling.md) (ensemble-rejection amended), [ADR-0013](./0013-worktree-per-maker-isolation.md) (each candidate isolated), [ADR-0038](./0038-inconclusive-only-judge-tiebreak.md) (tiebreak when multiple candidates pass), [ADR-0039](./0039-adaptive-confidence-scored-routing.md) (low-confidence units trigger best-of-N), [ADR-0034](./0034-budget-audit-enforce-rollup.md) (cost ceiling bounds N).
