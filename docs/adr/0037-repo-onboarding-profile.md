# ADR-0037: Repo onboarding / profile — detect language, tooling, and standards once

- **Status:** Accepted
- **Date:** 2026-06-30
- **Requirements:** REQ-ONB1, REQ-ONB2

## Context

For conductor to work on an arbitrary repo (greenfield or existing OSS), it must know: what language(s), how to run tests, how to lint/format, where the codegraph index is, and any declared contribution standards (`CONTRIBUTING.md`, `.editorconfig`). Today these are assumed (Python/pytest) or passed ad hoc. Both the language adapter (ADR-0035) and the style gate (ADR-0036) need this resolved *once*, up front, deterministically.

## Decision

Add a **`RepoProfile`** produced by a one-time **onboarding** step over a target repo:

- **Detect language(s)** from manifests/extensions (`pyproject.toml`/`setup.py`→python, `package.json`→javascript/typescript, `go.mod`→go, `Cargo.toml`→rust, …) → selects the `LanguageAdapter` (ADR-0035); unknown → `generic`.
- **Detect test command** (`pytest`, `npm test`/`jest`, `go test ./...`, `cargo test`) and test-file convention.
- **Detect lint/format tooling** (`ruff`/`eslint`/`golangci-lint`/`clippy`; `black`/`prettier`/`gofmt`/`rustfmt`) for the style gate (ADR-0036).
- **Locate/trigger the codegraph index** (ADR-0022/codegraph_live) for the decomposition verifier.
- **Read declared standards** (`CONTRIBUTING.md`, `.editorconfig`, lint config) — surfaced as *advisory* brief enrichment (the maker is told the conventions; the *gate* is still the mechanical lint run, ADR-0036).
- Detection is **best-effort + overridable**: every field can be set explicitly in config; detection only fills gaps. Missing pieces degrade cleanly (no test cmd → weak GREEN + a logged warning; no lint → style gate skipped).

The profile is pure data the rest of the system consumes — it adds **no** language branching to the base (the adapter does that), and it changes **no** guardrail.

## Considered alternatives

- **Assume Python/pytest (status quo)** — Pros: zero onboarding. Cons: only works on one stack; can't target arbitrary repos. Rejected.
- **Require the user to hand-configure everything** — Pros: explicit. Cons: high friction per repo. Rejected in favor of detect-then-override.
- **LLM "figure out the repo"** — Pros: flexible. Cons: non-deterministic onboarding; the facts (lang, test cmd, lint) are mechanically detectable from manifests. Rejected — detection is deterministic; an LLM may *assist* reading CONTRIBUTING but the profile fields come from manifests.

## Consequences

- **Positive:** one deterministic step turns "an arbitrary repo" into a fully-configured run (adapter + test + lint + codegraph + standards); greenfield and existing repos use the same path; overridable so detection failures are recoverable.
- **Negative:** detection heuristics will mis-detect some repos (monorepos, polyglot, unusual layouts) → mitigated by explicit override; reading CONTRIBUTING is advisory only (can't mechanically enforce prose rules — only the encoded lint/test can be gated).
- **Neutral:** the profile is config-like state, versionable per repo; polyglot repos resolve a per-unit adapter by the unit's file language (future extension).

## Related

[ADR-0035](./0035-pluggable-language-adapters.md) (profile selects the adapter), [ADR-0036](./0036-repo-native-style-gate.md) (profile detects lint/format), [ADR-0022](./0022-codegraph-decomposition-verifier.md)/codegraph_live (profile locates the index). REQ-ONB1/2.
