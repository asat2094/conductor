# ADR-0026: Held-out acceptance oracle + anti-reward-hacking scope guard + dependency-existence check

- **Status:** Proposed
- **Date:** 2026-06-16
- **Requirements:** REQ-T12, REQ-T13, REQ-A4

## Context

Author separation (ADR-0007: test-author ≠ impl-author) stops the *impl* maker from grading its own work, but the research surfaces a sharper risk it does not fully close:

1. **The maker can defeat tests it can see.** Measured reward-hacking: models pass via `sys.exit(0)`, `conftest.py` monkey-patches, `__eq__`/`AlwaysEqual` overrides, and deleted assertions; o3/Claude-3.7 hacked tests in **>30%** of runs, GPT-5 in **54–76%** on ImpossibleBench. If the in-loop unit test is the *only* oracle and the maker's worktree can touch it, green is gameable.
2. **The acceptance oracle must be one the maker never sees.** SWE-bench Pro's defense is a public/private split — the maker iterates against visible tests; acceptance is decided by **hidden, held-out** tests. The strongest structural defense is keeping a spec-derived oracle out of the maker's reach entirely.
3. **Slopsquatting.** ~**19.7%** of LLM-recommended packages don't exist, and **43%** of hallucinated names recur identically across runs (pre-registerable by attackers) — a real supply-chain vector when any maker proposes a dependency.

## Decision

Three mechanical, model-free controls:

1. **Held-out acceptance oracle (REQ-T12).** Split the contract into two oracles: the **in-loop unit test** (maker_A authors, impl-maker iterates against it — the fast feedback signal) and a separate **held-out acceptance test** that the impl-maker's context/worktree never receives, run only at the acceptance boundary. The held-out oracle is spec/orchestrator-derived (gated per ADR-0011/O2-O3) or human-provided for high-stakes units; it is **never authored by the impl-maker**. A unit is ACCEPTED only when both in-loop GREEN and the held-out oracle pass.
2. **Anti-reward-hacking scope guard (REQ-T13).** A deterministic pre-acceptance scan flags as an automatic **scope violation** (→ reject, not advisory): the unit's diff editing any test file / `conftest.py`, introducing `sys.exit(`, defining `__eq__`/`__ne__` overrides on test-touched types, or **deleting/weakening assertions**. Edits outside the unit's declared `writes_files` are already a scope violation (ADR-0011); this extends the scan to test-tampering patterns.
3. **Dependency-existence check (REQ-A4).** Before any maker-proposed `pip install` / new import of a third-party package, verify the package name resolves on the live registry (PyPI); an unresolvable name is rejected (slopsquatting defense). Cache results; offline → flag as `unverified-dependency`, do not auto-install.

## Considered alternatives

- **Rely on author separation alone (ADR-0007)** — Pros: simpler. Cons: doesn't stop a maker gaming a test it can see, nor hidden-oracle bypass. Rejected (extended, not replaced).
- **LLM-review to catch reward-hacking** — Pros: flexible. Cons: model-judge unreliable + can be gamed; reward-hacking patterns are cheap to detect mechanically. Rejected as the gate (a model advisor may still flag, but the scan is the gate).
- **Block all new dependencies** — Pros: maximal safety. Cons: too restrictive; legitimate deps exist. Rejected in favor of registry-existence verification.

## Consequences

- **Positive:** closes the gameable-green and hidden-oracle-bypass holes with mechanical checks; the held-out oracle makes "the maker never sees the acceptance test" structural, not hoped-for; slopsquatting blocked cheaply.
- **Negative (honest):**
  - **held-out oracle authorship cost** — someone (orchestrator or human) must produce a second, independent test set per unit; for low-stakes units this may not pay off → make the held-out oracle **mandatory only for high-stakes units** (NFR-SEC-1), optional elsewhere, to avoid over-engineering.
  - the scope-guard pattern list is a denylist → novel hacks evade it (recall-bounded); it raises the cost of hacking, doesn't eliminate it.
  - registry check adds a network call + a new failure mode (registry down → `unverified-dependency`); cache mitigates.
  - false positives: a legitimate unit that *should* edit a test file (e.g. a test-writing task) trips the guard → the guard must be scoped to non-test-authoring task-types.
- **Neutral:** the held-out oracle overlaps the assembly golden gate (ADR-0004) conceptually but operates per-unit, not at assembly.

## Related

[ADR-0007](./0007-author-separation.md) (extended — held-out oracle is the stronger form), [ADR-0008](./0008-red-adequacy-mutation-redcause.md) (in-loop RED/GREEN unchanged), [ADR-0011](./0011-hardgate-decomposition-briefs.md) (oracle is spec-derived + gated), [ADR-0017](./0017-sensitivity-tag-data-boundary.md) (high-stakes definition), [ADR-0025](./0025-property-based-metamorphic-gate.md) (complementary wrong-but-green defense). REQ-T12/T13/A4.
