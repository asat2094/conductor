# ADR-0035: Pluggable language adapters — language-agnostic base, swappable per-language block

- **Status:** Accepted
- **Date:** 2026-06-30
- **Requirements:** REQ-LANG1, REQ-LANG2, REQ-LANG3
- **Supersedes:** NFR-SCOPE-1 (Python-only v1) — replaced by per-language adapters.

## Context

The harness hardcodes Python in its *verification blocks*: `evaluator.check_syntax` uses `ast.parse`; `_run_tests` shells `pytest`; `mutation` operators are Python syntax; contract/signature extraction assumes Python AST; `live_maker`/`strict_gates` assume a pytest command; `deps_check` queries PyPI. This was a v1-scope shortcut (NFR-SCOPE-1), **not a real constraint** — the LLM maker already writes any language; only the *mechanical gates* are Python-bound.

The user's requirement: a **block-by-block** system where the base structure is language-agnostic and **only the language-specific block changes** when the language changes — no structural modification. The **core mantra (mechanical-first, Law-1 no-self-report, bounded-context) and all guardrails must remain** regardless of language.

## Decision

Introduce a **`LanguageAdapter`** abstraction — the single seam where every language-specific operation lives — with a registry + resolver, mirroring the proven optimizer-facade pattern (ADR-0021):

- **One Protocol** (`harness/lang/base.py`) covering every language-specific touchpoint the gates need:
  `check_syntax(path) -> bool`, `run_tests(cmd_or_files, workdir) -> (rc, out)`, `discover_test_cmd(files) -> str|None`, `is_test_file(path) -> bool`, `extract_signatures(path) -> list[str]`, `mutate(source) -> list[(op, mutated)]`, `lint_cmd() / format_check_cmd()`, `verify_dependency(name) -> status`.
- **Registry + resolver** (`register(name, factory)`, `resolve(language)`); resolution is by the repo profile's detected language (ADR-0037), with a **generic fallback adapter** so an unknown language degrades cleanly (syntax/lint best-effort, tests via discovered cmd) rather than crashing.
- **The base system never branches on language.** `evaluator`, `strict_gates`, `mutation`, `characterization`, contract-conformance, `live_maker` call the *resolved adapter*; they contain zero `ast`/`pytest`/`.py` literals. Swapping `python` → `javascript` swaps one registered block; the DAG/waves/repair-loop/merge-queue/tracker/decompose are untouched.
- **Guardrails are adapter-independent and enforced by the base:** Law-1 (gates read adapter-extracted facts, never maker self-report), Law-2 (adapter ops are mechanical — AST parse, test run, lint run — never an LLM judge), bounded-context, author-separation, mechanical RED/GREEN. The adapter only changes *how* a mechanical fact is computed, never *whether* the gate is mechanical.

Ship `python` and at least one second adapter (`javascript`: `node --check`/`eslint`/`jest`/npm) to prove block-swap, plus the `generic` fallback.

## Considered alternatives

- **Keep Python-only (NFR-SCOPE-1)** — Pros: simplest. Cons: artificially limits a language-agnostic maker; can't contribute to non-Python OSS. Rejected.
- **`if language == ...` branches inside each gate** — Pros: no new abstraction. Cons: structural language-coupling smeared across every gate; violates "only the language block changes." Rejected — single adapter seam instead.
- **A heavy multi-language framework dependency (tree-sitter for everything)** — Pros: uniform parsing. Cons: heavy dep, and most ops (test/lint/format) are CLI invocations anyway. Rejected for the base; an adapter *may* use tree-sitter internally.

## Consequences

- **Positive:** any language an LLM can code + that has CLI test/lint/format tooling is supported by writing one adapter; the base stays clean and language-blind; the mantra/guardrails hold uniformly because the adapter only swaps the *mechanism* of a mechanical check; greenfield and existing repos both work (the adapter is resolved from the repo, not assumed).
- **Negative:** the `LanguageAdapter` Protocol is a broad public contract — adding a touchpoint means updating every adapter; per-language adapters are real work (correct mutation operators, signature extraction differ per language); the generic fallback is weaker (best-effort syntax, no mutation) — honest degradation, not full coverage.
- **Neutral:** existing Python behavior is preserved by making `python` the default adapter — the 378 tests keep passing unchanged.

## Related

[ADR-0021](./0021-pluggable-context-optimizer.md) (same pluggable-facade+registry pattern), [ADR-0008](./0008-red-adequacy-mutation-redcause.md)/[0009](./0009-green-full-suite-independent.md)/[0025](./0025-property-based-metamorphic-gate.md) (gates that now delegate to the adapter), [ADR-0036](./0036-repo-native-style-gate.md) (style via adapter's lint/format), [ADR-0037](./0037-repo-onboarding-profile.md) (detects which adapter to resolve). REQ-LANG1/2/3.
