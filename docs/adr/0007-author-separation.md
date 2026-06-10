# ADR-0007: Enforce test-author ≠ impl-author per unit

- **Status:** Proposed
- **Date:** 2026-06-09
- **Requirements:** REQ-T2

## Context

If one maker writes both the unit test and the implementation, it is fox-guarding-henhouse: the maker can write a vacuous or self-satisfying test and an impl that passes it, with no independent check. The same-model-writes-and-reviews failure is a known blind spot.

## Decision

For each functional unit, enforce **`test_author ≠ impl_author`** (harness-tracked), and exclude the test author from impl routing for that unit. The orchestrator independently validates the test between RED and impl dispatch. For high-stakes units, a three-way split (test / impl / review by distinct makers) is the escalation.

## Considered alternatives

- **Same maker writes test + impl** — Pros: one dispatch, cheapest. Cons: self-validation theater — no independent contract. Rejected.
- **Claude writes all unit tests** — Pros: highest-quality contract. Cons: Claude token cost on every unit defeats the savings goal. Rejected (Claude *validates*, does not author, the unit test).
- **Three-way separation always** — Pros: strongest. Cons: three dispatches per unit, overkill for low-stakes. Kept as the high-stakes option only.

## Consequences

- **Positive:** the test is an independent contract the impl maker must satisfy; removes self-validation.
- **Negative:** one extra dispatch per unit; residual bias shifts upstream to the brief author (mitigated by REQ-O3 second-model review of contracts).
- **Neutral:** "different author" is enforced at the provider/role level; combine with ADR-0004 cross-family diversity to also reduce *correlated* blind spots.

## Related

ADR-0004 (diversity/blind spots), ADR-0008 (RED adequacy), ADR-0011 (brief is the upstream artifact). REQ-T2.
