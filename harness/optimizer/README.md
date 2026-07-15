# harness/optimizer/

Pluggable **context-optimizer facade** (ADR-0021). Reader-aware prompt/context compression with
baked-in-safe defaults and opt-in backends. Compression is applied only at **paid-model read
boundaries** (a `claude_cli` reader); free/local readers (ollama) skip it for latency.

## Contract (`base.py`)

- `Compressor` Protocol — `optimize(messages, cfg: OptimizeConfig) -> OptimizeResult`.
- `count_tokens(messages)` — rough token estimate.
- Protected roles / evidence are never compressed (safety guard, `guard.py`).

Registry (`registry.py`): `register(name, factory)` · `resolve(name)` · `resolve_from_config(cfg)`.

## Backends

| Backend | Behavior |
|---|---|
| `null` | pass-through (no compression) — the safe default |
| `caveman` | prose-only shorthand compression (drops articles/filler; never touches code/evidence) |
| `headroom` | headroom-style budget-aware compression |

## Usage

Wired via `harness/optimizer_wiring.py`:

```python
from harness.optimizer_wiring import optimize_for_reader
msgs = optimize_for_reader(messages, reader_spec, backend="caveman")  # no-op if reader is free/local
```

`LiveMaker(optimize_context=True, ccr_store=...)` applies it to context slices for paid readers and
(with a CCR store) keeps the original reversibly retrievable (ADR-0033). Add a backend by
implementing `Compressor` and `register()`-ing it — the base engine and callers are untouched.
