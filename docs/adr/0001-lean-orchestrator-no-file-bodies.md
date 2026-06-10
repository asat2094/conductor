# ADR-0001: Lean orchestrator never loads maker-produced file bodies

- **Status:** Proposed
- **Date:** 2026-06-09
- **Requirements:** REQ-O1

## Context

The orchestrator is the Claude main thread (phase 1) — the most expensive context in the system and the one whose history grows monotonically across a whole build. Input/context tokens dominate cost: every byte that enters the orchestrator's context is re-billed on every subsequent turn for the rest of the run. If the orchestrator reads maker-produced file bodies — the full text of generated implementations, tests, and edits — its context bloats with bulk content that it does not need in order to orchestrate, and the per-task token saving from delegating to a cheap maker is erased by the orchestrator re-reading the maker's output.

The savings mechanism of the whole system is the contrast between **bounded maker context** (a maker sees only its self-contained brief and produces a file) and a **lean orchestrator history** (which sees only the small artifacts needed to decide). That contrast collapses the moment file bodies flow back up.

## Decision

The orchestrator's context never receives a maker-produced file body. The orchestrator reads only:

- **briefs** — the self-contained `SubtaskBrief` it authored for each unit,
- **contracts** — the orchestrator-owned `produces`/`consumes` seam declarations, and
- **lean verdicts** — the mechanical checker's pass/fail/confidence result per unit.

File bodies are written to disk and gated by the harness; their bytes are AST-parsed and re-run harness-side and never surface in the orchestrator's context. Acceptance of a unit is communicated to the orchestrator as a verdict, not as content.

## Considered alternatives

- **Orchestrator reads unified diffs instead of full files** — Pros: smaller than full files, still human-legible, shows exactly what changed. Cons: still bulk content that scales with the size of the change and accumulates across every unit in the build; reintroduces the re-billing problem at a reduced but unbounded rate. Rejected: any per-unit body content in the orchestrator breaks the bounded-vs-bloated contrast.
- **Orchestrator reads LLM-generated semantic summaries of each file** — Pros: very compact, captures intent rather than syntax. Cons: costs a model call per unit to produce, and a summary can silently drift from what the file actually contains, undermining the harness-derived-evidence principle (ADR-0002). Partial: kept as a *possible future extension* for high-stakes units where a compact human-readable rationale is worth the cost, but not as the default path and never as gate evidence.

## Consequences

- **Positive:** orchestrator context stays small and roughly flat per unit, so delegation savings are preserved across the whole build; the orchestrator cannot accidentally "review" maker output and be misled by it, which reinforces the no-trust principle.
- **Negative:** the orchestrator is genuinely blind to file contents, so when it must intervene (REQ-C4) it has to re-derive context from disk on demand rather than already holding it; debugging a bad unit from the orchestrator's perspective is harder because the body was never in its history.
- **Neutral:** the value of the system now hinges on the brief being truly self-contained and the verdict being trustworthy — pressure that lands on the decomposition and checker layers, not here.

## Related

ADR-0002 (no-trust maker self-report) — verdicts the orchestrator reads must be harness-derived, not maker-reported. REQ-O1; supports the token-reduction success criterion in the requirements doc.
