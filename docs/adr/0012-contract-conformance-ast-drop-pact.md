# ADR-0012: Seam contract conformance via harness AST extraction, not full Pact

- **Status:** Accepted
- **Date:** 2026-06-09
- **Requirements:** REQ-I1, REQ-I3

## Context

Conductor decomposes a task into a producer→consumer DAG of units that are implemented by independent, untrusted makers. Where two units meet, they share a **seam** — a function/class signature one unit produces and another consumes. If the producer and consumer drift apart on that seam, the assembled build is broken even though each unit may have passed its own local gates.

Two forces shape how we verify seams:

- **Law 1 (REQ-I1, REQ-C1):** gate evidence must come from harness-side artifacts, never from a maker's self-reported `output`/envelope. A maker that exports its own `exported_signatures` is reporting on itself; trusting that to prove conformance reintroduces exactly the self-attestation Law 1 forbids.
- **Decomposition is upfront, makers are concurrent (REQ-I3):** the orchestrator already freezes the cross-unit interface at DECOMPOSE time. There is no negotiation phase in which a consumer-driven contract could be discovered after the fact; the contract exists before any maker runs.

Full Pact-style consumer-driven contract testing (with broker, `can-i-deploy`, and provider verification handshakes) assumes independently-released services negotiating contracts over time. That ceremony does not match a single atomic build where the orchestrator already owns and freezes the interface.

## Decision

The cross-subtask seam contract is **frozen once at decompose time** and written into both the caller brief and the callee brief, so each maker sees its half of the seam without seeing the other unit's body. The frozen contract set is orchestrator-owned and read-only to makers (REQ-I3); no unit writes it concurrently.

Conformance is checked by the harness:

1. The harness AST-parses each written file and **extracts the actual signatures** from the code on disk.
2. It compares those extracted signatures against the frozen contracts — **never** against any maker-reported envelope or `exported_signatures` field (Law 1).
3. Because signature matching is purely syntactic (a type-correct signature can still be wired wrong), the harness additionally runs **seam-level behavioral example checks** — a "Pact-lite" layer: property-generated examples over the ranges declared in the contract, asserting the producer's output satisfies what the consumer assumes.

We deliberately do **not** adopt the full Pact broker / `can-i-deploy` ceremony.

## Considered alternatives

### A. Full Pact consumer-driven contract testing (broker + can-i-deploy)
- **Pros:** mature ecosystem; explicit provider-verification handshake; versioned contract history.
- **Cons:** broker infrastructure, contract publishing, and deploy-gating ceremony designed for independently-released services; the orchestrator already owns and freezes the interface upfront, so there is no consumer-driven negotiation to model.
- **Why rejected (for v1):** ceremony overhead with no payoff in a single atomic build; the negotiation lifecycle Pact exists to manage does not occur here.

### B. Trust the maker-reported `exported_signatures` envelope
- **Pros:** trivial — no AST parsing; the maker tells us what it produced.
- **Cons:** the maker is attesting to its own output; a maker can report a conforming signature while the file on disk differs.
- **Why rejected:** direct Law 1 (REQ-I1) violation — gate evidence would come from a maker self-report instead of a harness-side artifact.

### C. Signature matching only, no behavioral examples
- **Pros:** cheap, fully deterministic, no generated inputs.
- **Cons:** signatures are syntactic; a unit can match the declared signature yet implement the wrong behavior at the seam (right shape, wrong meaning).
- **Why partially rejected:** kept as the first, fast layer — but type-correct-but-wrong seams would slip through, so it is supplemented by the Pact-lite behavioral example layer rather than relied on alone.

## Consequences

### Positive
- Conformance evidence is harness-derived from the code on disk, satisfying Law 1.
- Freezing the contract into both briefs at decompose time gives every maker a stable, self-contained view of its seam without leaking the counterpart's body.
- The Pact-lite behavioral layer catches type-correct-but-semantically-wrong seams that pure signature matching misses.

### Negative
- AST extraction plus property-generated seam examples cost more than a signature string-compare, and add a generated-input surface that must be seeded for reproducibility.
- Behavioral examples are only as good as the ranges declared in the contract; an under-specified contract narrows what the seam check can catch.

### Neutral
- Contract ownership and freezing semantics live with the orchestrator; makers gain no write path to the contract set.
- Concrete signature-extraction mechanics, example-generation seeds, and contract storage details are design-level and documented in design.md, not here.

## Related
- REQ-I1 (seam conformance via AST signatures vs frozen contracts, never the envelope)
- REQ-I3 (contracts orchestrator-owned, frozen at decompose, read-only to makers)
- REQ-C1 (Law 1 — gate evidence from harness artifacts only)
- ADR-0013 (worktree-per-maker isolation; merge/reduce stage where seams meet)
