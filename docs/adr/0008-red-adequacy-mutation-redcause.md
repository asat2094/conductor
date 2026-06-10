# ADR-0008: RED adequacy via assertion-cause RED + post-GREEN mutation, not test presence

- **Status:** Proposed
- **Date:** 2026-06-09
- **Requirements:** REQ-T1, REQ-T4, REQ-T8

## Context

The legacy evaluator scored "a test exists and passes" — a soft signal that rewards vacuous, already-green, or implementation-coupled tests. Canonical TDD requires a test that fails *now*, *for the right reason*. And test *adequacy* (does the test actually exercise behavior?) is a separate question from RED validity. Mutation testing answers adequacy, but the implementation does not exist at true RED, so mutation cannot be the RED gate itself.

## Decision

- **True RED:** the unit test must fail against current code, and the failure must be an **assertion** failure whose captured cause matches the brief's declared expected behavior. Import/collection/syntax errors are rejected as invalid RED.
- **Adequacy (separate, post-GREEN):** after GREEN, run mutation over the impl region using **behavior-bearing** operators (boundary, return-value, condition-removal — not only arithmetic flips), **suppress equivalent mutants** from the denominator, and reject the unit if the non-equivalent kill-rate is below the per-task-type threshold (value lives in design/config).
- **Immutability:** pin the RED test identity + cause hash; reject at GREEN if that exact test was modified between RED and GREEN.

## Considered alternatives

- **Test-presence = adequacy (legacy)** — Pros: trivial. Cons: rewards vacuous tests; the develop weakness. Rejected.
- **Mutation as the RED gate** — Pros: one adequacy number. Cons: no impl exists at true RED; conflates RED validity with adequacy. Rejected — mutation runs post-GREEN.
- **Cheap arithmetic-only mutation operators** — Pros: fast. Cons: gameable by impl-coupled tests; equivalent-mutant noise. Rejected in favor of behavior-bearing operators + equivalent suppression.

## Consequences

- **Positive:** vacuous, wrong-reason, and impl-coupled tests are rejected mechanically; adequacy is measured on real impl.
- **Negative:** mutation adds runtime to every accepted unit; equivalent-mutant suppression is heuristic and imperfect.
- **Neutral:** RED-cause matching needs a structured expected-behavior field in the brief.

## Related

ADR-0007 (author separation), ADR-0009 (GREEN), ADR-0010 (non-functional gate). REQ-T1, REQ-T4, REQ-T8.
