# ADR-0004: Bound the seed-input ceiling; accuracy/correctness outrank cost in the blind-spot regime (Law 3)

- **Status:** Proposed
- **Date:** 2026-06-09
- **Requirements:** REQ-C4, REQ-OBS4, REQ-T6

## Context

Golden / characterization / contract gates verify only the captured inputs and the syntactic surface. If two cheap makers and cheap mutation operators share a blind spot, a logic-shaped under-specified test can pass mechanically below the accept threshold — wrong-but-green. This residual cannot be fully closed by any cheap mechanical check, because every cheap checker may share the failure mode.

## Decision

Bound (not close) the residual with three layers, and in this regime spend cost to protect correctness:

1. **Proactive maker diversity** — the test-author, impl-author, and any verifier roles for one unit draw from *different model families/providers*, so a shared blind spot is unlikely by construction.
2. **Periodic higher-capability random audit** — a thin sample of auto-accepted units is re-checked by a stronger model.
3. **Orchestrator control-takeback (INTERVENE)** — on any blind-spot signal (audit catch, or a high-stakes unit that could not be staffed with diverse makers), the orchestrator takes the unit: tier2 re-derive or implement inline.

Accuracy/correctness outrank cost here; the residual tail is the priced cost of the trade, not a silent wrong-accept.

## Considered alternatives

- **Claim sampling/blind spots eliminated** — Pros: simpler story. Cons: false; correlated blind spots provably survive cheap checks. Rejected.
- **Human-only review of accepted units** — Pros: strongest catch. Cons: does not scale, defeats automation. Rejected (kept as an optional manual audit hook).
- **Single-model verifier** — Pros: cheap. Cons: shares blind spots with the makers it checks. Rejected in favor of cross-family diversity.

## Consequences

- **Positive:** the wrong-but-green tail is bounded and visibly priced; high-stakes units get human-grade attention via takeback.
- **Negative:** diversity constraints can leave capable makers idle; the random audit and takeback cost real Opus/$.
- **Neutral:** "different family" diversity is an independence estimate, not a guarantee — overlapping training corpora reduce its strength.

## Related

ADR-0003 (mechanical-first) — escalation handles the sub-threshold; this handles the *correlated* tail. ADR-0007 (author separation) supplies role diversity. REQ-C4, REQ-OBS4, REQ-T6.
