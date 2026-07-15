# docs/

Design documentation for conductor. The harness is spec-driven (SDD) and every decision is recorded
as an ADR — the code and these docs are traceably linked.

## Where to look

| Path | What's there |
|---|---|
| [`adr/`](adr/README.md) | **42 Architecture Decision Records** — the authoritative design. Start at [`adr/README.md`](adr/README.md) for the indexed list + status. |
| `specs/conductor/` | Spec-driven-development source of truth: [`requirements.md`](specs/conductor/requirements.md) (EARS), [`design.md`](specs/conductor/design.md), [`tasks.md`](specs/conductor/tasks.md), `schemas/` (SubtaskBrief + unit JSON schemas). |
| [`traceability.md`](traceability.md) | Requirement → ADR → code matrix. |
| `cost-calibration.md` | How to move provider prices from seeded ballparks to real, and run budget `audit` before `enforce`. |
| `ci-workflow.yml.example` | CI workflow template (copy to `.github/workflows/` with a workflow-scoped token). |
| `superpowers/` | Historical planning docs + implementation plans (dated snapshots; not live guidance). |

## Reading order for a newcomer

1. Root [`README.md`](../README.md) — what conductor is + quickstart.
2. [`adr/0001`](adr/0001-lean-orchestrator-no-file-bodies.md)–`0004` — the three laws (lean orchestrator,
   no self-report, mechanical-first, bounded-context).
3. [`adr/0011`](adr/0011-hardgate-decomposition-briefs.md) / `0024` / `0025`–`0027` — decomposition,
   role assignment, the TDD-as-contract gate stack, bounded repair.
4. [`adr/0035`](adr/0035-pluggable-language-adapters.md)–`0042` — pluggability, style, onboarding, the
   design-review additions (judge tiebreak, confidence routing, best-of-N, per-wave merge, evalkit).

ADRs are immutable once Accepted — a course change is a new ADR that supersedes the earlier one.
