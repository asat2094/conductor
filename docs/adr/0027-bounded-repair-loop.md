# ADR-0027: Bounded per-unit repair loop with mechanical stop conditions ("loops", done safely)

- **Status:** Accepted
- **Date:** 2026-06-16
- **Requirements:** REQ-H1, REQ-H2, REQ-H3

## Context

"Loop engineering" (the June-2026 term: design the system that prompts the agent, not the prompt) is credible only because of one principle: **give the loop something that can say no** — a mechanical verifier, not the model's self-assessment. "A loop with nothing to push back is the agent agreeing with itself." Conductor already has the hard part (mechanical gates, no maker self-report). What it lacks is an *explicit, bounded* repair loop formalizing how a gate-failed unit gets fixed.

The evidence sets tight bounds: verifier-in-the-loop (generate→test→repair) lifts reliability (Reflexion 91% vs 80% HumanEval), but resampling against an imperfect verifier is **capped regardless of compute (optimal N often ≤5, sometimes 0)**; self-correction captures ~75% of its gain in rounds 1–2; and the dominant failure modes are **runaway cost**, **spinning** (looping on the same broken thing), and **erosion of the mechanical gate** (adding a soft "model says good enough" gate to break a stall).

## Decision

Formalize healing as a **bounded per-unit repair loop** with strictly mechanical stop conditions:

```
attempt = 0
while attempt < MAX_REPAIR (default 3, hard ceiling < 10):
    result = maker.generate(brief, failure_feedback)   # feedback = the MECHANICAL gate output
    verdict = gate(result)                              # deterministic: RED-cause/GREEN/mutation/PBT/scope
    if verdict.passed: return ACCEPTED
    if stuck(verdict): break                            # stuck-detection (see below)
    failure_feedback = verdict.mechanical_evidence      # failing test, counterexample, mutation survivor
    attempt += 1
escalate()   # next tier maker (ADR-0006) or human — NEVER loosen the gate
```

- **Failure feedback is the mechanical gate output only** (failing test, PBT counterexample, mutation survivor, scope-violation reason) — never a model's opinion.
- **Stuck-detection (REQ-H2):** abort the loop if the gate's failure signal is byte-identical (or the diff is empty) across the last N attempts (default 2) — a known Ralph-loop control. Stuck → escalate immediately, don't burn the remaining budget.
- **Hard caps (REQ-H3):** per-unit attempt ceiling (<10) AND a per-unit token/cost ceiling tied into the cost model (ADR-0016)/admission ceiling (ADR-0014). Reaching either → escalate.
- **No soft gate, ever (REQ-H1):** the stop condition stays mechanical. If a fuzzy goal cannot be expressed as a passing gate, the loop escalates to a human/frontier model — it does **not** add a "model judges good-enough" exit. This is the explicit guard against loop-engineering's central failure mode.
- **Scope:** this is the **per-unit** loop (lowest risk, blast radius = one isolated unit). A **whole-DAG loop-until-green** (re-run aggregate/assembly gate, spawn repair units, re-converge with a wave-level iteration cap + no-progress kill) is permitted but deferred. A **continuous autonomous loop** (cron, unattended) is explicitly **out of scope** for now — that is where loopmaxxing/runaway/slop live.

## Considered alternatives

- **Unbounded loop-until-green (naive Ralph)** — Pros: simple, sometimes works. Cons: runaway cost, infinite spinning; needs the caps anyway. Rejected (bounded form adopted).
- **No explicit loop (single heal attempt → escalate, status quo healer A/B/C)** — Pros: cheapest, no spinning. Cons: under-uses cheap-maker self-repair against ground truth; one shot is below the ~75%-in-rounds-1–2 sweet spot. Rejected (the bounded loop is the tuned middle).
- **Add a soft model-judge exit to break stalls** — Pros: fewer escalations. Cons: "the agent agreeing with itself" — erodes the entire mechanical-gate guarantee. **Explicitly rejected.**
- **Whole-DAG loop / continuous autonomous loop now** — Pros: more autonomy. Cons: can mask bad decomposition by brute force; runaway cost/slop. Deferred.

## Consequences

- **Positive:** units self-heal against mechanical ground truth instead of bouncing straight to expensive escalation or a human; captures the legitimate core of "loops" while *strengthening* (not diluting) the gate discipline; cost is hard-bounded.
- **Negative (honest):**
  - every retry is repeated (possibly paid) model calls — bounded by the caps but still a cost multiplier on hard units; tie to the cost ceiling.
  - stuck-detection on byte-identical output can miss "different-but-still-wrong" spinning (cosmetic churn that never fixes the defect) — the attempt ceiling is the backstop.
  - MAX_REPAIR is new tuning debt (default 3 from the rounds-1–2 evidence; per-task-type calibration later).
  - a unit that legitimately needs >3 attempts escalates "early" — accepted: escalation is cheaper than a spinning loop.
- **Neutral:** integrates with the tracker (HEALING(attempt n) states, REQ-OBS7 per-attempt run rows) — the loop is fully observable.

## Related

[ADR-0006](./0006-tiered-maker-pool-bounded-escalation.md) (escalation target when the loop exhausts), [ADR-0014](./0014-admission-separate-from-routing.md) (cost ceiling), [ADR-0016](./0016-cost-skip-claude-inline.md) (per-unit cost model), [ADR-0023](./0023-development-tracker-progress-board.md) (HEALING states + per-attempt rows), [ADR-0008](./0008-red-adequacy-mutation-redcause.md)/[0025](./0025-property-based-metamorphic-gate.md) (the gates whose output is the loop's feedback). REQ-H1/H2/H3.
