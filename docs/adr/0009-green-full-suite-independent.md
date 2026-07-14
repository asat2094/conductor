# ADR-0009: GREEN re-runs the unit test + full suite independently

- **Status:** Accepted
- **Date:** 2026-06-09
- **Requirements:** REQ-T3, REQ-T8

## Context

A maker can claim "tests pass." The legacy evaluator ran `pytest <changed_files>` only — so a maker breaking a *sibling* test elsewhere was never caught, and the result was a soft score, not a gate. GREEN must be an independent, regression-aware pass/fail.

## Decision

At GREEN, the harness **independently re-runs the unit test AND the full suite** (never the maker's self-report); accept only when both are green and the pinned RED test (unmodified) has flipped RED→GREEN for its recorded cause. This requires a **suite-determinism contract**: randomized order under a pinned seed, a flaky-test quarantine excluded from gating, masking of non-deterministic values (time/uuid/network), and a re-run-once policy that records flakes to the regression ledger rather than failing the unit.

## Considered alternatives

- **Trust maker "tests pass"** — Pros: free. Cons: Law 1 violation; unverifiable. Rejected.
- **Changed-files-only pytest (legacy)** — Pros: fast. Cons: misses sibling/regression breakage. Rejected.
- **Unit test only, no full suite** — Pros: cheapest gate. Cons: regressions slip into integration. Rejected.

## Consequences

- **Positive:** regressions and sibling breakage are caught at the unit boundary; GREEN is reproducible.
- **Negative:** full-suite-per-unit is expensive in wall-clock and needs worktree isolation (ADR-0013); flaky suites threaten gating, hence the determinism contract.
- **Neutral:** the determinism contract imposes test-hygiene requirements on the host repo.

## Related

ADR-0008 (RED + immutability), ADR-0013 (worktree isolation makes per-unit full-suite safe), ADR-0002 (no self-report). REQ-T3, REQ-T8.
