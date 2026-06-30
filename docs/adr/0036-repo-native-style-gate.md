# ADR-0036: Repo-native style/standards gate — the repo's own tooling is a mechanical oracle

- **Status:** Proposed
- **Date:** 2026-06-30
- **Requirements:** REQ-STYLE1, REQ-STYLE2

## Context

To contribute to an existing codebase, output must match that repo's coding standards, or a maintainer rejects it on style/idiom. The naive approach — "ask the model to write in the house style" — is unreliable and, worse, would tempt an LLM-judge "is this stylish enough?" gate (Law-1 violation). But a codebase that has standards almost always encodes them in **executable tooling**: a linter (`ruff`/`eslint`/`golangci-lint`), a formatter (`black`/`prettier`/`gofmt`), an `.editorconfig`. Running those is **mechanical** — a deterministic pass/fail, not a model opinion. So "adapt to the codebase's standards" reduces to "**pass the codebase's own lint + format-check gates**", which is exactly conductor's mechanical-first model.

## Decision

Add a **repo-native style gate** as another mechanical gate in the unit-gate stack:

- The gate runs the **repo's own** lint + format-check commands (resolved via the language adapter, ADR-0035, and detected at onboarding, ADR-0037 — e.g. `ruff check` + `black --check`, or `eslint` + `prettier --check`, or `gofmt -l` + `go vet`) against the unit's changed files.
- A lint/format failure is a **mechanical gate failure** → feeds the repair loop (the maker is re-prompted with the lint output as feedback, like any other gate evidence). No model judges style.
- **Auto-format escape hatch:** where the repo ships a deterministic formatter (`black`/`prettier`/`gofmt`), optionally run it to *fix* formatting before the check, since formatting is mechanically reversible and not a behavior change (still gated by tests).
- **Degrade-clean:** a repo with no detected lint/format tooling → the style gate is skipped (status `no-style-tooling`), not failed — conductor doesn't invent standards a repo doesn't have.
- Style is **adapted-to, never invented**: the gate reflects *the repo's* config; conductor imposes no house style of its own.

This keeps the core intact: style compliance is a *mechanical* gate (Law-2), its evidence is *tool output* not a maker claim (Law-1), and it feeds the *bounded repair loop* (ADR-0027) like every other gate.

## Considered alternatives

- **LLM-judge "is this in the house style?"** — Pros: works without repo tooling. Cons: Law-1 violation, unreliable (style judging is even noisier than correctness judging). Rejected.
- **Prompt the maker with the style guide and hope** — Pros: cheap. Cons: not gated → no guarantee; maintainer still bounces it. Kept as a *soft* prompt enrichment (feed lint config + sample code, ADR-0035/context_slices), but the *gate* is the mechanical lint/format run.
- **Impose conductor's own house style** — Pros: uniform. Cons: defeats "adapt to the target repo." Rejected.

## Consequences

- **Positive:** "matches the repo's standards" becomes a deterministic, maintainer-trustworthy gate; reuses the repo's existing tooling (zero style config to maintain in conductor); pairs with auto-format to fix trivial style mechanically.
- **Negative:** only as good as the repo's tooling — a repo with weak/no linting gets weak/no style enforcement (honest: conductor can't enforce standards a repo doesn't encode); running lint/format per unit adds wall-clock; some linters need project setup (deps installed) to run, adding an onboarding dependency.
- **Neutral:** style gate is opt-in per repo via the profile; greenfield repos (built by conductor) can adopt a chosen toolchain and gate on it identically.

## Related

[ADR-0035](./0035-pluggable-language-adapters.md) (adapter supplies lint/format cmds), [ADR-0037](./0037-repo-onboarding-profile.md) (detects the tooling), [ADR-0027](./0027-bounded-repair-loop.md) (style failure feeds the loop), [ADR-0002](./0002-no-trust-maker-self-report.md)/[0003](./0003-mechanical-first-model-last.md) (mechanical, tool-derived). REQ-STYLE1/2.
