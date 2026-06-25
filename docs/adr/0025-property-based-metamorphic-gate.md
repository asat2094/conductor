# ADR-0025: Property-based + metamorphic testing as a first-class checker tier

- **Status:** Proposed
- **Date:** 2026-06-16
- **Requirements:** REQ-T10, REQ-T11

## Context

The deterministic gate (compile/type/lint/run held-out tests) is high-precision but low-recall for *logic* errors — type-checking empirically catches ~15% of defects, and **7.8–47.9% of test-passing "solved" SWE-bench patches are actually wrong** ([2503.15223], SWE-Bench+, UTBoost). This is the "wrong-but-green" gap conductor's Law-1 gates do not, by themselves, close: an example-based test suite is necessary but not sufficient.

The strongest single piece of evidence in the 2025–2026 reliability literature is that **property-based testing (PBT) + metamorphic testing** attack exactly this gap: each PBT finds **~50× as many mutants** as the average unit test (OOPSLA 2025), metamorphic prompt testing catches **75% of erroneous GPT-4 programs at 8.6% false-positive** ([2406.06864]), and Anthropic's own red-team bet for catching model-written bugs is autonomous PBT — not LLM-judge, not SMT ([red.anthropic.com 2026]). It is also cheap: ~76% of mutations die within the first ~20 generated inputs.

Conductor today uses property-based inputs only in the *characterization* gate for non-functional units (ADR-0010). The evidence says it should be a **core checker tier for functional units too**.

## Decision

Add **property-based + metamorphic testing as a first-class checker tier**, run on 100% of functional units after GREEN, before acceptance:

- For each changed function the checker drives **property-based inputs (Hypothesis)** under a pinned seed against declared invariants (from the brief's `contract.expected_behavior` / `produces`), plus **metamorphic relations** where applicable (e.g. round-trip `decode(encode(x))==x`, ordering/idempotency/scale relations).
- It is **mechanical** (Law 2): the properties run as real code; no model judges the result. A surviving counterexample is a **hard gate failure** → repair loop (ADR-0027), with the counterexample fed back as the failure signal.
- Generated inputs and any minimized counterexample are recorded in the run-ledger for reproducibility (pinned seed → replayable).
- Properties come from the contract/brief (orchestrator-authored, gated per ADR-0011/O2-O3) — **not** from the impl-maker (else it's self-testing; see ADR-0026).
- Bounded: a per-unit input cap (default ~50, tunable) keeps it cheap; counterexample minimization is capped.

## Considered alternatives

- **Example-based tests only (status quo)** — Pros: simplest. Cons: the documented wrong-but-green gap; necessary-not-sufficient. Rejected as the sole functional gate.
- **LLM-judge for semantic correctness** — Pros: catches intent. Cons: κ≈0.1–0.2, ~50% of wrong code passed — unreliable as a gate (kept advisory only, ADR-0003). Rejected as a gate.
- **Formal methods / SMT (Dafny/TLA+)** — Pros: strongest guarantee. Cons: over-engineering for typical software; "vacuous verification" trap (models pass via tautological specs, [2509.22908]); belongs only on security/money/protocol cores. Rejected for the general path.

## Consequences

- **Positive:** closes most of the wrong-but-green gap with mechanical (not model) evidence — the highest-ROI reliability upgrade available; cheap (counterexamples surface in the first ~20 inputs); reproducible via pinned seed.
- **Negative (honest):**
  - **property quality is the new bottleneck** — a weak/incomplete property set gives false confidence (it reduces, not closes, the gap; the assembly golden gate and human validator remain backstops). Properties are orchestrator-authored, so they inherit decomposition-judgment risk.
  - **flaky-property risk** — non-deterministic code (time/uuid/network) breaks PBT determinism; requires the same masking the suite-determinism contract (ADR-0009) mandates.
  - new dependency (Hypothesis) on the checker path — acceptable (test-only, not the harness core; behind the existing Python-only scope).
  - per-unit input cap is new tuning debt.
- **Neutral:** metamorphic relations only apply where a relation exists (round-trip, ordering, scale); units without one fall back to PBT-over-invariants + the example tests.

## Related

[ADR-0009](./0009-green-full-suite-independent.md) (GREEN precedes this; determinism contract shared), [ADR-0010](./0010-nonfunctional-characterization-gate.md) (PBT already used there — this generalizes it), [ADR-0003](./0003-mechanical-first-model-last.md) (mechanical, not LLM-judge), [ADR-0026](./0026-held-out-acceptance-oracle.md) (properties are not maker-authored), [ADR-0027](./0027-bounded-repair-loop.md) (counterexample feeds the repair loop). REQ-T10/T11.
