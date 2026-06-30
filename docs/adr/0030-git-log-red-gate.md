# ADR-0030: git-log RED-before-impl gate

- **Status:** Proposed
- **Date:** 2026-06-30
- **Requirements:** REQ-T14
- **Borrowed from:** gsd-core (MVP+TDD capability — commit-order inspection).

## Context

`strict_gates.red_gate` validates true-RED by *running* the test and asserting an assertion-cause failure. That proves the test fails now. But it does not prove the **temporal discipline** of TDD: that the failing test existed *before* the implementation. A maker (or a sloppy loop) could write impl-and-test together, or write the test after the impl, and still show a green suite. gsd-core's MVP+TDD gate inspects the git log to mechanically prove a RED commit precedes any behavior-adding (`feat`) commit — pure commit inspection, zero model trust.

## Decision

Add a **git-log RED-before-impl gate**: for a functional unit, inspect the unit's commit history (in its worktree, ADR-0013) and require that a commit containing the failing test precedes the commit that adds the implementation. Mechanically: the test file's introducing commit is an ancestor of the impl file's introducing commit, and the test was RED at the test-commit (cross-checked with the recorded RED-cause hash from `strict_gates`/ADR-0008). No model is consulted — it is `git log`/`git diff` parsing.

This complements (does not replace) the run-based true-RED gate: run-RED proves *the test fails for the right reason*; git-log RED proves *it failed first*.

## Considered alternatives

- **Run-based true-RED only (status quo)** — Pros: simpler. Cons: doesn't catch test-written-after-impl / co-authored test+impl. Rejected (this is additive).
- **Trust the maker's claim of TDD order** — Law 1 violation. Rejected.

## Consequences

- **Positive:** mechanically enforces the *temporal* half of TDD with zero model trust; pairs with author-separation to make the test a genuine prior contract.
- **Negative:** requires per-unit git history granularity (the maker must commit test then impl separately — a workflow constraint on the maker harness); squashed/amended history defeats it (mitigate: enforce the commit cadence in the maker, or run the gate pre-squash); adds git-archaeology cost per unit.
- **Neutral:** only meaningful inside worktree isolation (ADR-0013), where each unit has its own commit lineage.

## Related

[ADR-0008](./0008-red-adequacy-mutation-redcause.md) (run-based true-RED + cause hash), [ADR-0007](./0007-author-separation.md) (test is an independent prior artifact), [ADR-0013](./0013-worktree-per-maker-isolation.md) (per-unit lineage). REQ-T14.
