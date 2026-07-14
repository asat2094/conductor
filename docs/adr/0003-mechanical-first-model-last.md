# ADR-0003: Mechanical-first, model-last (Law 2)

- **Status:** Accepted — **amended by [ADR-0038](./0038-inconclusive-only-judge-tiebreak.md)**: one bounded exception — an LLM-judge may break a tie only when mechanical gates are *inconclusive*, never overriding a FAIL, logged + per-DAG quota'd.
- **Date:** 2026-06-09
- **Requirements:** REQ-C2, REQ-C3

## Context

A model in the verification hot path is expensive (tokens) and non-deterministic (the same artifact can be judged differently across runs). But pure-mechanical gates cannot catch every semantic problem. The system needs the cheapness and reproducibility of deterministic checks for the common case, and the judgment of a model only where deterministic evidence is genuinely insufficient.

## Decision

Deterministic gates (RED-cause assertion, mutation kill-rate, GREEN re-run + full suite, AST contract diff, characterization golden) run on **100% of units with no model in the hot path**. Each unit aggregates to a 0–1 mechanical confidence. A model-based check fires **only** when that confidence is below the accept threshold. The threshold value is a tunable that lives in `design.md` / config — not in this ADR.

## Considered alternatives

- **Model-graded on every unit** — Pros: maximal semantic coverage. Cons: model cost on every unit (defeats the cost goal), non-deterministic verdicts (defeats reproducibility), and a model reading maker output risks collusion. Rejected.
- **Pure mechanical, never escalate to a model** — Pros: fully deterministic and cheap. Cons: leaves a semantic residue (the sub-threshold tail) silently accepted. Rejected — the residue is exactly where wrong-but-green hides.

## Consequences

- **Positive:** the common case is cheap, fast, reproducible, and model-free; model cost is spent only on the genuinely-uncertain minority.
- **Negative:** the accept threshold becomes a critical tunable — mis-calibration silently shifts the cost/accuracy balance, so it must be validated against the bench/regression ledger.
- **Neutral:** introduces a confidence aggregation function whose composition across heterogeneous sub-gates must be defined in design.

## Related

ADR-0002 (no trust in self-report) — defines the model check as advisory, never gate evidence. ADR-0004 (seed-input ceiling) — the random audit complements sub-threshold escalation. REQ-C2, REQ-C3.
