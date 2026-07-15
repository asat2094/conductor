# harness/lang/

Pluggable **per-language adapters** (ADR-0035). This is the *single seam* where language-specific
behavior lives — the base harness never branches on language. Swap `python` → `javascript` and the
DAG / waves / gates / merge are untouched; only the adapter block changes.

## The contract (`base.py` — `LanguageAdapter` Protocol)

| Method | Returns |
|---|---|
| `check_syntax(path)` | `bool` — does the file parse? (mechanical syntax oracle) |
| `is_test_file(path)` | `bool` — test-file naming convention |
| `discover_test_cmd(files, workdir)` | `str \| None` — how to run the relevant tests |
| `run_tests(cmd, workdir, *, runner=None)` | `(rc, output)` |
| `extract_signatures(path)` | `list` — public API signatures (contract conformance) |
| `mutate(source)` | `list[(op, mutated)]` — mutation operators (ADR-0008) |
| `lint_cmd(files)` / `format_check_cmd(files)` | `str \| None` — repo-native style gate (ADR-0036) |
| `verify_dependency(name)` | `"ok" \| "unresolvable" \| "unverified" \| "invalid"` — slopsquatting guard (ADR-0026) |

Registry: `register(name, factory)` · `resolve(language)` · `adapter_for_path(path)`.
A `GenericAdapter` fallback degrades cleanly (best-effort syntax/lint, no mutation) for unknown
languages — the harness never crashes on an unrecognized file.

## Shipped adapters

- `python_adapter.py` — `ast` / pytest / ruff / black / PyPI.
- `javascript_adapter.py` — `node --check` / jest / eslint / prettier / npm registry.
- `GenericAdapter` (in `base.py`) — the degrade-clean fallback.

## Add a language

1. Implement the Protocol (a class with the methods above) in `harness/lang/<lang>_adapter.py`.
2. `from harness.lang.base import register; register("<lang>", MyAdapter)` at import time.
3. Import it once (e.g. in `lang/__init__.py`) so the registration runs.

Guardrails are adapter-independent: an adapter only changes *how* a mechanical fact is computed
(parse, test-run, lint), never *whether* a gate is mechanical (Law 2 holds for every language).
