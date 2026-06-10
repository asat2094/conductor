# ADR-0000: Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-06-09
- **Requirements:** (process ADR — governs how all REQ-* decisions are recorded)

## Context

Conductor is a correctness-spine system where a small number of durable choices (don't trust maker self-report, never load file bodies into the orchestrator, bound — not close — the seed-input blind spot) shape every downstream component. When those choices live only in prose — scattered across the requirements doc, code comments, and chat history — they decay: the *why* is lost, alternatives are silently re-litigated, and a future contributor reverses a load-bearing decision without realizing it was deliberate. This is the exact gap this record fixes.

We need a place where architecturally significant decisions are captured at the moment they are made, with the forces and rejected alternatives that justify them, and where they remain stable enough to cite from requirements and design.

## Decision

Adopt Architecture Decision Records (Nygard format, extended with MADR-style "Considered alternatives" and "Consequences") for every architecturally significant decision.

- ADRs live in-repo under `docs/adr/`, one file per decision, versioned with the code they govern.
- An accepted ADR is **immutable**: its content does not change after acceptance. A decision is revised only by writing a **new** ADR that supersedes the old one; the superseded ADR's status is updated to point at its successor, but its body stays intact as the historical record.
- ADRs are indexed in `docs/adr/README.md` so the decision set is discoverable.
- Each ADR must state its forces (Context), the durable choice (Decision), at least two serious alternatives, and at least one honest negative consequence.

Tunable constants, filenames, and build order do **not** belong in ADRs; they live in `design.md`. ADRs capture the durable *why*, not the adjustable *how*.

## Considered alternatives

- **No ADRs — decisions captured in prose (requirements doc, comments, chat)** — Pros: zero process overhead, nothing new to learn. Cons: the *why* and rejected alternatives evaporate; decisions get silently reversed; no immutable history. Rejected: this is precisely the failure mode the record exists to prevent.
- **Wiki / Confluence decision log** — Pros: rich editing, easy linking, familiar to many teams. Cons: not in-repo, not versioned with the code, not reviewable in the same PR that implements the decision, and drifts out of sync. Rejected: decisions must travel with the code and be reviewable alongside it.

## Consequences

- **Positive:** durable decisions are discoverable, immutable, and citable from REQ-* and design.md; rejected alternatives are preserved so they aren't re-litigated; review of a decision happens in the same PR as its first implementation.
- **Negative:** writing an ADR is friction at decision time, and contributors must learn to distinguish "architecturally significant" (write an ADR) from routine (don't). Some judgment calls will be inconsistent.
- **Neutral:** the index in `docs/adr/README.md` must be maintained by hand or by a small tool; superseded ADRs accumulate as historical records rather than being deleted.

## Related

All subsequent ADRs (ADR-0001 … ADR-0005) follow this format and convention. Requirements doc references the ADR set at `docs/adr/`.
