# ADR-0016: COST-SKIP meta-gate — route small tasks to inline Claude

- **Status:** Accepted
- **Date:** 2026-06-09
- **Requirements:** REQ-R1

## Context

Conductor's pipeline is not free: a delegated unit pays for DECOMPOSE, a RED test author, two independent dispatches (test author + impl author, who must differ per REQ-T2), GREEN re-runs, a full-suite run, mutation/validation, and merge. For a large task that overhead is dwarfed by the savings of keeping bulk file bodies out of the orchestrator's context. For a *small* task — a one-line edit, a trivial rename — that same overhead exceeds the cost of Claude just doing the edit inline. Without a gate, the pipeline is **net-negative on small tasks**, undermining the ≥50% token-reduction target.

The orchestration philosophy is correctness ≥ accuracy > efficiency > cost; cost is the lowest priority but still a falsifiable target (cost-per-successful-task ≤ inline-Claude cost). We need an ROI check before committing a unit to the full pipeline.

## Decision

Add a **COST-SKIP meta-gate in routing** that, before delegating, **projects the full delegation cost** of running the unit through the pipeline (decompose + RED + 2 dispatches + GREEN + full-suite + validation) and compares it against the **inline-Claude cost** of doing the work directly.

- WHEN estimated tokens fall below `min_delegation_tokens`, OR projected delegation cost ≥ inline-Claude cost, the unit routes to a new `AgentType.CLAUDE_INLINE` and **skips the pipeline** entirely (REQ-R1).
- Decomposition is **demand-driven (ADaPT-style):** a unit is decomposed further only when it *fails*, not preemptively — so small tasks are not split into sub-units that each re-incur pipeline overhead.

This is the ROI meta-gate: without it, the pipeline loses money on exactly the trivial tasks it is most tempting to throw at it.

**Calibration note:** the projected-cost model depends on per-provider cost figures that are currently `0.0` in the registry. The cost model must be calibrated before the comparison arm of the gate is load-bearing; until then the `min_delegation_tokens` arm carries the gate.

## Considered alternatives

### A. Always delegate every unit through the pipeline
- **Pros:** uniform path; no special-casing.
- **Cons:** pipeline overhead exceeds inline cost on small tasks, making delegation net-negative there and eroding the token-reduction target.
- **Why rejected:** loses money on trivial tasks — the exact failure this ADR prevents.

### B. Fixed token threshold only (no cost projection)
- **Pros:** simple, fully deterministic, no cost model needed.
- **Cons:** a flat token cut-off mis-sizes units whose token count and actual pipeline cost diverge (e.g., few tokens but many coupled stages, or many tokens that are cheap to delegate).
- **Why partially kept:** retained as the `min_delegation_tokens` arm, but paired with the full-pipeline cost projection so the decision tracks real ROI rather than token count alone.

### C. Never route inline — keep all work in the maker pool
- **Pros:** maximizes offload from the orchestrator; preserves the lean-checker invariant uniformly.
- **Cons:** forces trivial edits through decompose/RED/GREEN/merge, defeating efficiency on work Claude could finish in one shot.
- **Why rejected:** defeats the efficiency goal precisely where inline is cheapest.

## Consequences

### Positive
- Small/trivial units bypass pipeline overhead, keeping cost-per-successful-task ≤ inline-Claude cost.
- Demand-driven decomposition avoids splitting small units into overhead-heavy sub-units.
- A first-class `CLAUDE_INLINE` route makes the inline path explicit and ledger-visible rather than an implicit fallback.

### Negative
- `CLAUDE_INLINE` work runs in (or close to) the orchestrator's context, so the lean-checker invariant (REQ-O1) is relaxed for these units — acceptable because they are small by construction, but it is a deliberate carve-out.
- The cost-projection arm is only as accurate as the cost model; with provider costs at `0.0` it is not yet trustworthy and needs calibration.

### Neutral
- Adds `AgentType.CLAUDE_INLINE` to the routing surface.
- `min_delegation_tokens`, the cost-model coefficients, and the projection formula are design-level tunables in design.md, not fixed here.

## Related
- REQ-R1 (cost-skip: route to CLAUDE_INLINE below min_delegation_tokens or when delegation ≥ inline)
- REQ-T2 (author separation — the two dispatches the projection accounts for)
- REQ-O1 (lean-checker invariant, relaxed for inline units)
- ADR-0015 (deterministic routing — the meta-gate runs within the pure routing function)
