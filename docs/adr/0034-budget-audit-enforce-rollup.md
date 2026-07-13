# ADR-0034: Budget audit|enforce modes + sub-build spend rollup

- **Status:** Accepted
- **Date:** 2026-06-30
- **Requirements:** REQ-A5
- **Borrowed from:** microsoft/conductor (`budget_usd` + `budget_mode: audit|enforce`, parent rollup).

## Context

The admission layer (ADR-0014) has a per-run cost ceiling that blocks when reached. But turning a hard ceiling on cold is risky — it can stall a real build mid-DAG before the threshold is calibrated. microsoft/conductor separates `audit` (track + warn, never block) from `enforce` (block at limit), and rolls sub-workflow spend up to the parent. This gives a safe rollout path (audit first, learn the real cost, then enforce) and correct accounting when units spawn sub-units.

## Decision

Extend the admission cost-ceiling with two modes + rollup:

- **`audit`** — track cumulative spend, emit a warning as it approaches/exceeds the budget, but **never block**. The safe default for a new build until cost is calibrated (closes the design §7 calibration debt: providers currently priced at 0.0).
- **`enforce`** — the existing hard behavior: block/queue at the limit rather than ballooning to paid escalation.
- **Sub-build spend rollup** — when a unit recurses into a sub-build, its spend rolls up into the parent's cumulative total, so the ceiling accounts for the whole tree, not just the top level.
- **One-time unpriced-model warning** — if a model has no price entry, warn once and continue in audit (don't silently count it as free).

## Considered alternatives

- **Hard ceiling only (status quo, ADR-0014)** — Pros: simplest, strongest guarantee. Cons: stalls real builds before the threshold is calibrated; no safe rollout. Rejected (enforce remains, audit added in front).
- **No budget tracking** — defeats cost-awareness, a core goal. Rejected.

## Consequences

- **Positive:** safe audit-before-enforce rollout; correct whole-tree accounting; the unpriced-model warning prevents silent free-counting; directly addresses the cost-model calibration debt.
- **Negative:** `audit` mode by definition does not stop overspend (it only warns) — a misconfigured run left in audit can run up cost; rollup needs every sub-build to report spend to its parent (plumbing).
- **Neutral:** mode is per-run config; enforce is unchanged from ADR-0014.

## Related

[ADR-0014](./0014-admission-separate-from-routing.md) (cost ceiling this extends), [ADR-0016](./0016-cost-skip-claude-inline.md) (cost model / calibration debt this helps close). REQ-A5.
