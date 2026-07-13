# ADR-0038: Inconclusive-only LLM-judge tiebreak (bounded exception to Law 2)

- **Status:** Accepted
- **Date:** 2026-07-13
- **Amends:** [ADR-0003](./0003-mechanical-first-model-last.md) (Law 2, mechanical-first). Core holds; this carves one bounded exception.
- **Requirements:** REQ-GATE-TIEBREAK (new)

## Context

Law 2 (ADR-0003) says correctness is decided ONLY by deterministic gates; a model may advise but never gates. In practice some slices have **no mechanical gate available**: a brief with no test authored yet, a config/doc unit with no assertable behavior, or two candidate diffs that both pass every gate equally (a genuine tie). Today these fall through to "escalate to orchestrator/human," which is correct but stalls throughput on the exact cases where mechanical evidence is silent, not negative.

The user's decision (design-review Q1): allow an **LLM-judge tiebreak** — but without reopening the self-report failure mode that the whole thesis closes (LLM-judge as a primary accept gate shows κ≈0.1–0.2 and passed ~50% of wrong code in the research that motivated conductor).

## Decision

An LLM-judge may act as a tiebreak **only** under all of these conditions:

1. **Inconclusive-only.** The judge fires only when the mechanical gates return *inconclusive* — no applicable deterministic gate ran (no test/AST/lint check exists for the slice), or ≥2 candidates are mechanically indistinguishable (all pass identically). It NEVER fires when a mechanical gate has run.
2. **Never overrides a FAIL.** A mechanical FAIL is terminal. The judge cannot resurrect a unit that failed any gate. It only breaks a tie among *not-failed* outcomes or decides a *no-gate-ran* slice.
3. **Not self-report.** The judging model MUST be a different model than the impl-author (author-separation, ADR-0007 extended to judges) and is given the artifact + brief, not the maker's own claims.
4. **Logged + quota'd.** Every judge-accept is recorded in the tracker with a `judge_tiebreak` event (which model, which slice, verdict) and counts against a **per-DAG quota** (default: small, e.g. ≤10% of units). Exceeding the quota escalates to the orchestrator instead of judging — a DAG that leans on the judge is a decomposition smell, surfaced not hidden.
5. **Prefer building a gate.** When a slice repeatedly hits the inconclusive path, that is a signal to author a test (feed the next wave), not to keep judging.

## Considered alternatives

- **Pure mechanical-only (built, ADR-0003 unamended)** — Pros: strongest guarantee, zero model-trust. Cons: stalls on no-gate slices; forces human on ties that don't need one. The user chose to relax exactly here.
- **LLM-judge as a primary accept gate (gsd/ms-conductor style)** — Rejected. Reopens the self-report failure mode; this is the pattern conductor exists to avoid.
- **Hybrid where judge can override a mechanical result on "high confidence"** — Rejected. "High confidence" is the wrong-but-green vector; #2 (never overrides FAIL) is non-negotiable.

## Consequences

- **Positive:** no-gate and true-tie slices stop stalling; throughput improves on the cases where mechanical evidence is genuinely silent; the quota + logging keep the exception visible and small.
- **Negative:** a narrow, audited crack in Law 2 — a judge-accept on a no-gate slice can be wrong. Mitigated by author-separation, never-override-FAIL, the quota, and the tracker log (every judge-accept is reviewable). Honest: this is weaker than mechanical-only; the user accepted the tradeoff knowingly.
- **Neutral:** when a suite exists, behavior is identical to before (judge never fires).

## Related

[ADR-0003](./0003-mechanical-first-model-last.md) (amended), [ADR-0002](./0002-no-trust-maker-self-report.md) (Law 1 — judge is not the author), [ADR-0007](./0007-author-separation.md) (author-separation extended to judges), [ADR-0023](./0023-development-tracker-progress-board.md) (judge_tiebreak events), [ADR-0027](./0027-bounded-repair-loop.md) (escalation path when quota exceeded).
