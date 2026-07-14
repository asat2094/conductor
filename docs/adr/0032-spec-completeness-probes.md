# ADR-0032: Spec-completeness probes (Edge-Probe + Prohibition-Probe) — advisory, gate-feeding

- **Status:** Accepted
- **Date:** 2026-06-30
- **Requirements:** REQ-D11
- **Borrowed from:** gsd-core (Edge-Probe 8-category taxonomy + Prohibition-Probe must-NOT pass).

## Context

A goal-backward verifier is confidently wrong about edges the spec never stated — gsd-core measured ~0.93 confidence catching 0/12 omitted edges. The fix is to surface omitted edge-cases and prohibitions into explicit, checkable criteria *before code exists*. Edge-Probe is a closed 8-category QA taxonomy (boundary, adjacency, empty, encoding, ordering, precision, idempotency, concurrency); Prohibition-Probe is an adversarial recall→precision pass for "must-NOT" (safety/fairness) constraints. Our briefs today carry `exit_criteria` + a contract but no systematic edge/prohibition surfacing — so a brief can be silently under-specified, and every downstream mechanical gate then verifies the *wrong* (incomplete) spec.

## Decision

Add spec-completeness probes at decompose time — **advisory, never a gate, never model-trusting as evidence**:

- Run Edge-Probe (the 8-category checklist) and Prohibition-Probe against each functional brief; surface omitted edges/prohibitions as **candidate criteria appended to the brief**, each with a mandatory dismissal reason if the orchestrator declines it.
- The probe output is **advisory annotation** — it does not block dispatch. Its value is that surfaced criteria become **properties/tests a mechanical gate later checks** (PBT/ADR-0025, characterization/ADR-0010): the probe *proposes*, the deterministic gate *disposes*.
- Probes may be LLM-assisted (they're a brainstorming aid), but their output is **never gate evidence** — it only enriches the brief; correctness is still decided mechanically (Law 1/2 intact).

## Considered alternatives

- **Edge/Prohibition probes as a hard pre-dispatch gate** — Pros: forces completeness. Cons: probe output is model-generated → gating on it violates Law 1, and false "missing edge" flags block valid briefs. Rejected — advisory only.
- **No completeness surfacing (status quo)** — Pros: simplest. Cons: silently under-specified briefs → wrong-but-green downstream. Rejected.

## Consequences

- **Positive:** raises brief quality before dispatch; converts "the spec forgot the empty/boundary/concurrency case" into explicit criteria the mechanical gates then enforce; cheap, language-agnostic.
- **Negative:** advisory output can be ignored (its criteria only bite if turned into a gate property); LLM-assisted probing costs tokens; the 8-category taxonomy is a heuristic, not exhaustive — it reduces, doesn't eliminate, missing-edge risk.
- **Neutral:** sits beside the orchestrator-output gate (REQ-O2/O3) as another pre-dispatch quality lift, not a correctness gate.

## Related

[ADR-0011](./0011-hardgate-decomposition-briefs.md) (decompose), [ADR-0025](./0025-property-based-metamorphic-gate.md) / [ADR-0010](./0010-nonfunctional-characterization-gate.md) (the mechanical gates that enforce surfaced criteria), [ADR-0003](./0003-mechanical-first-model-last.md) (probes advise, mechanics decide). REQ-D11.
