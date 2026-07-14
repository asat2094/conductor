# ADR-0041: Per-wave atomic merge (closed-subgraph landing)

- **Status:** Accepted
- **Date:** 2026-07-14
- **Amends:** [ADR-0012](./0012-contract-conformance-ast-drop-pact.md) (was whole-DAG ff-or-discard at finalize). Resolves the merge-granularity item PARKED on [ADR-0029](./0029-wave-failure-mode-taxonomy.md).
- **Requirements:** REQ-I4 (refined), REQ-I6 (new — per-wave promotion)

## Context

`merge_queue.finalize()` was **DAG-atomic all-or-nothing**: fast-forward the whole DAG to target only if every unit passed, else discard the entire integration branch. One failed leaf discarded all sibling GREEN work (resume recomputes onto a fresh branch). The design-review parked the granularity question.

Key facts that framed the decision:
- The merge queue already merges accepted units one-at-a-time and **re-runs the full suite after each merge**, so **nothing red ever lands regardless of granularity** — the target branch is never made red by this policy.
- The real trade is therefore **wasted work** (DAG-atomic discards good units) **vs semantic incompleteness** (landing a feature whose missing piece had no failing test — green but non-functional).
- Topo **waves are already dependency-closed by construction**: a wave runs only after every dependency in prior waves was accepted, and units *within* a wave are independent (no intra-wave edges). So "the largest dependency-closed GREEN prefix" == "all fully-GREEN waves up to the first wave containing a failure."

## Decision

Finalize is **per-wave atomic** with **closed-subgraph (prefix) landing** — user decision, design review 2026-07-14:

- **Land per wave.** When a wave completes with **every unit GREEN** and the cumulative integration state passes the full-suite/assembly check, **fast-forward that wave's segment to the target branch**. Target advances wave-by-wave.
- **Prefix hold on first failure.** The **first wave containing any failure**, and **all successor waves**, are **HELD** (not landed). Landed set = waves `0..k-1` where wave `k` is the first failing wave.
- **Invariant: target stays green + no dangling references.** Guaranteed by topo order — a landed unit only references its dependency-closure, which lies in already-landed prior waves; intra-wave units are independent, so a landed unit never references an un-landed one.
- **Remainder is resumable (ADR-0028).** Held waves are recorded as pending; on resume, landed waves are skipped and a fresh integration branch continues the remainder, fast-forwarding onto the already-advanced target.
- **DAG-atomic remains an opt-in strict mode** (`atomicity="dag"`) for releases that must land whole-or-nothing; default is `atomicity="wave"`.
- **Orthogonal to `failure_mode` (ADR-0029).** `failure_mode` governs the *wave dispatch loop* (fail_fast vs continue_on_error); `atomicity` governs *what lands at finalize*. Independent knobs — e.g. `continue_on_error` still processes later waves for tracking/verdicts, but only the GREEN prefix lands.

## Considered alternatives

- **Keep whole-DAG atomic (built)** — Pros: strongest "feature whole-or-absent"; simplest rollback. Cons: one failure wastes all sibling GREEN work. Retained as opt-in `atomicity="dag"`, not the default.
- **Partial per-unit merge (land any accepted unit)** — Rejected: an arbitrary unit can leave a feature half-present; enforcing closure to make it safe collapses it into the per-wave rule anyway.
- **Maximal closed-subgraph (land every independent GREEN subgraph, even past the first failing wave under continue_on_error)** — Deferred: maximizes preservation but needs per-unit reachability bookkeeping for marginal gain over the prefix rule. Revisit if wasted-work on independent late subgraphs proves material.
- **Land GREEN units within the first failing wave** — Deferred: dangling-safe (intra-wave units are independent) but complicates rollback reasoning; hold-whole-wave is cleaner for a small cost.

## Consequences

- **Positive:** completed waves are preserved (kills the wasted-work problem); target is always green + semantically consistent (no half-features from the prefix rule); resume continues cleanly onto the advanced target; whole-or-nothing still available as a mode.
- **Negative:** target now advances mid-build (a consumer watching target sees partial features land wave-by-wave — acceptable, each landed wave is green + closed); a wave with one failed unit still wastes that wave's other GREEN units (the residual cost of hold-whole-wave); finalize/merge-queue gains a per-wave promotion step + an `atomicity` mode flag (more test surface).
- **Neutral:** `atomicity="dag"` reproduces the old behavior exactly — the 434 tests' expectations hold under the opt-in mode.

## Related

[ADR-0012](./0012-contract-conformance-ast-drop-pact.md) (amended — finalize granularity), [ADR-0029](./0029-wave-failure-mode-taxonomy.md) (orthogonal failure_mode; un-parked by this ADR), [ADR-0028](./0028-checkpoint-resume-replay.md) (held waves resume), [ADR-0013](./0013-worktree-per-maker-isolation.md) (isolation enables per-wave integration branches), `harness/merge_queue.py`, `harness/run_dag.py`. REQ-I4/I6.
