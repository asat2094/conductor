# ADR-0017: Per-file sensitivity tag as the data boundary to free-cloud makers

- **Status:** Proposed
- **Date:** 2026-06-09
- **Requirements:** REQ-R4, REQ-E3, NFR-SEC-1

## Context

The maker pool is heterogeneous: local models, bounded Claude subagents, and tier1 free-cloud makers. Free-cloud makers are attractive for their zero marginal cost, but their providers may log, retain, or train on submitted bytes. On the develop line these cloud providers are live, so proprietary or secret-bearing source can physically leave the machine the moment a unit is dispatched. The orchestrator already keeps bulk file bodies out of its own context, but a delegated unit must still ship enough code for the maker to do the work, and that payload is the leak surface.

We need a boundary that lets non-sensitive work keep using the free tier while guaranteeing sensitive material is confined to trusted compute. The boundary must be cheap to evaluate at dispatch time and must be auditable after the fact.

## Decision

Adopt a per-file sensitivity tag that the orchestrator owns and freezes at decompose time. The boundary rules are:

- A file tagged at the highest sensitivity level is NEVER transmitted to any tier1 free-cloud maker. Units touching such files route only to local or Claude makers.
- Briefs carry minimal code slices needed for the unit, not whole files, shrinking the exposure surface even for non-sensitive work.
- An append-only exposure audit records bytes-sent per provider, so any cross-boundary transmission is reconstructable.
- Reuse the sensitive-path refusal behavior from the caveman-compress overlay: paths that are inherently secret-bearing (credential, key, and cloud-config directories) are refused outright as a backstop, independent of the per-file tag.

This binds REQ-R4 (sensitivity-driven routing) and the sensitive-path clause of REQ-E3, with NFR-SEC-1 defining the high-stakes classification that this boundary feeds.

## Considered alternatives

### A. No sensitivity control
- Pros: simplest; every maker is eligible for every unit, maximizing free-tier utilization.
- Cons: proprietary code is shipped to providers that may retain or train on it; no audit trail.
- Why rejected: leaks proprietary code with no recourse — unacceptable on a live-cloud line.

### B. Block all cloud makers unconditionally
- Pros: trivially safe; nothing proprietary ever leaves local/Claude compute.
- Cons: forfeits the free tier for the large majority of work that is not sensitive.
- Why rejected: loses the free-tier value for non-sensitive work, defeating a core economic goal of the pool.

### C. Encrypt-in-transit only
- Pros: protects against on-wire interception; standard transport hardening.
- Cons: the provider still terminates TLS and sees plaintext, and may log or train on it.
- Why rejected: in-transit encryption does nothing about the actual threat — provider-side retention and training of plaintext.

## Consequences

### Positive
- Non-sensitive work retains full access to the free maker tier.
- Sensitive bytes are confined to trusted compute by construction.
- The append-only audit makes any exposure reconstructable per provider.

### Negative
- Tagging is heuristic: a mistagged file can still leak, because the boundary is only as good as the tag.
- Once bytes leave for a provider, the harness has no control over that provider's retention or training.

### Neutral
- Tags are orchestrator-owned and frozen at decompose time, consistent with contract ownership.
- Minimal-slice briefs shrink exposure for all units, not only sensitive ones.

## Related
- ADR-0014 (admission separate from routing)
- ADR-0015 (deterministic routing)
- ADR-0019 (caveman compression at paid boundaries — shares the sensitive-path refusal)
