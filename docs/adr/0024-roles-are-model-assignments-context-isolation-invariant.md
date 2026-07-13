# ADR-0024: Roles are model-assignments; the invariant is bounded-context isolation, not model price

- **Status:** Accepted (foundational — refines [ADR-0001](./0001-lean-orchestrator-no-file-bodies.md) and generalizes [ADR-0006](./0006-tiered-maker-pool-bounded-escalation.md))
- **Date:** 2026-06-11
- **Requirements:** REQ-RM1, REQ-RM2, REQ-RM3

## Context

Earlier ADRs framed the worker side as "free local/cloud models + a paid-Claude fallback" (ADR-0006) and the savings as keeping bulk out of the orchestrator (ADR-0001). That framing conflated two independent things and quietly hard-coded a wrong assumption: that the win comes from using *unpaid* models.

The real principle: **the unit of optimization is the context, not the model's price.** Main-thread context bloats because history is resent every turn; a role run in its **own bounded context** (a fresh session/subagent given only its slice) avoids that bloat *and* produces higher-quality output because its attention is localized. This holds whether the model is free, open-source, local, or a paid Claude-class model — and whether it's the same model the orchestrator uses or a different one.

Conductor's roles — **decomposer, verifier, maker (test-author / impl-author), checker** — are therefore not "free workers." Each is a **role that gets assigned a model** by capability × cost × availability. The same model may serve several roles; the only hard rule is that each role-instance runs in a **separate, bounded context** — never the orchestrator's main-thread context.

## Decision

1. **Role ≠ model.** Decomposer, verifier, maker, and checker are roles. A **role-model policy** (config) maps each role (and each unit's task-type/stakes) to a model, chosen by **capability × cost × availability** — Claude Opus/Sonnet/Haiku (any class), OSS, or local. Paid models are first-class, not just a fallback.
2. **The hard invariant is context isolation.** Every role-instance runs in its own bounded context, constructed from exactly its `SubtaskBrief` — never inheriting the main thread's history. This is what delivers both the token saving and the localized-quality gain (ADR-0001 deepened). Two roles may use the *same model*; they must not share *context*.
3. **The pool generalizes (ADR-0006 refined).** The "tiered maker pool" becomes a **per-role capability/cost/availability router**: tiers are capability bands spanning local · OSS · free-cloud · paid-Claude-class, and *any* role draws from them. Escalation still flows cheap→capable, but "cheap" and "capable" are points on a cost/capability axis, not "free vs paid."
4. **Cost-skip and routing still apply** (ADR-0016/0015): the router picks the model per role-instance; `cost_skip` still decides when the *whole* unit is too small to delegate at all (inline). The optimizer (ADR-0021) now applies at **any boundary where a *paid* model reads context** — orchestrator-facing output *and* a paid-model role's input brief — conditioned on the assigned model's cost tier (free-model inputs gain latency, not $).
5. **"Free" language is shorthand.** Where the spec says "free models," read "models selected by capability/cost/availability"; the savings rationale everywhere is **bounded isolated context vs bloated main-thread context**, not price.

## Considered alternatives

- **Keep "free workers + paid fallback" (ADR-0006 as-was)** — Pros: simple cost story. Cons: false — it misses that a paid bounded subagent still saves vs inline main-thread, and that decomposer/verifier/checker are also model-assigned roles. Rejected (refined).
- **One model for everything in one context (no isolation)** — Pros: simplest. Cons: main-thread bloat + degraded localized quality — the problem conductor exists to solve. Rejected.
- **Force a different model per role (diversity by mandate)** — Pros: maximizes cross-family blind-spot coverage (ADR-0004). Cons: over-constrains; availability/cost may make same-model-different-context the right call. Rejected as a hard rule; diversity stays a *preference* (ADR-0004), isolation stays the *invariant*.

## Consequences

- **Positive:** removes the free-vs-paid confusion; the design now correctly optimizes context isolation, so a high-stakes unit can be assigned Opus-in-a-bounded-context and *still* save tokens vs inline; the router becomes a clean capability×cost×availability function reusable for every role; the optimizer's paid-boundary rule becomes precise (condition on the assigned model's tier).
- **Negative:** routing is now per-role × per-unit (more decisions, more config — the `role_model_policy` is new tuning/calibration debt); availability-based fallback adds a live-state dependency (which conflicts with S10 determinism unless the chosen model is logged in the run-ledger); paid models in many roles can raise cost if the cost-ceiling (ADR-0014) isn't tuned.
- **Neutral:** "maker pool" terminology stays as a convenience for the worker roles, but its meaning is now "the role-model router's worker tiers."

## Related

[ADR-0001](./0001-lean-orchestrator-no-file-bodies.md) (deepened: isolation is the savings, not price), [ADR-0006](./0006-tiered-maker-pool-bounded-escalation.md) (generalized to a per-role router), [ADR-0004](./0004-bound-seed-input-ceiling.md) (cross-family diversity stays a preference), [ADR-0016](./0016-cost-skip-claude-inline.md)/[0015](./0015-deterministic-routing-supersedes-binary-route.md) (routing/cost-skip), [ADR-0021](./0021-pluggable-context-optimizer.md) (optimize conditioned on the reader's cost tier). REQ-RM1/RM2/RM3.
