# Conductor Pluggable Optimizer Facade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A provider-agnostic context-optimizer facade with a pluggable backend registry: `null` (passthrough, default) and `caveman` (stdlib prose trim) baked in with zero deps, `headroom` as an opt-in lazy-imported backend, and a protect-list/min-tokens/degrade safety layer enforced by the facade regardless of backend.

**Architecture:** Self-contained package `harness/optimizer/` with NO conductor-specific imports (so it is extractable/reusable by any system). One entry point `optimize(messages, cfg)`; default backend `null` makes it inert out of the box. Backends implement a `Compressor` Protocol and self-register. The facade enforces safety invariants (protect-list restored byte-identical, min-token skip, degrade-to-null on any backend failure) so a misbehaving backend can never violate them.

**Tech Stack:** Python 3.11+, pytest via `python3 -m pytest` (the `/opt/homebrew/bin/pytest` shim is broken in this env), stdlib only for the baked-in path.

**Requirements covered:** REQ-E1, REQ-E2, REQ-E3. ADR-0021 (supersedes ADR-0019 engine). On branch `feat/conductor-distributed-build`. Baseline: 132 pass / 3 pre-existing `openai`-missing failures — add no new failures. No Co-Authored-By lines on commits.

**Scope note:** v1 wires the seam + the two baked-in backends + a headroom backend whose `optimize()` lazy-imports `headroom` (real call if installed; `available()` returns False when absent so the facade degrades to null in this env). Wiring the optimizer into the orchestrate pipeline + CCR `retrieve()` integration are deferred to the pipeline plan.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `harness/optimizer/__init__.py` | public `optimize()` + re-exports; registers built-in backends | Create |
| `harness/optimizer/base.py` | `Compressor` Protocol, `OptimizeConfig`, `OptimizeResult`, `count_tokens` | Create |
| `harness/optimizer/guard.py` | protect-list / min-tokens / restore-protected invariants | Create |
| `harness/optimizer/registry.py` | `register` / `resolve` (+ env override, degrade-to-null) | Create |
| `harness/optimizer/backends/__init__.py` | package marker | Create |
| `harness/optimizer/backends/null.py` | passthrough backend (always available) | Create |
| `harness/optimizer/backends/caveman.py` | stdlib prose-trim backend | Create |
| `harness/optimizer/backends/headroom.py` | opt-in lazy-import headroom backend | Create |
| `harness/tests/test_optimizer_*.py` | per-module tests | Create |

---

## Task 1: Base contracts (`base.py`)

**Files:**
- Create: `harness/optimizer/base.py`, `harness/optimizer/__init__.py` (empty for now), `harness/optimizer/backends/__init__.py` (empty)
- Test: `harness/tests/test_optimizer_base.py`

- [ ] **Step 1: Write the failing test**

Create `harness/tests/test_optimizer_base.py`:

```python
from harness.optimizer.base import OptimizeConfig, OptimizeResult, count_tokens


def test_config_defaults_to_null_backend():
    cfg = OptimizeConfig()
    assert cfg.backend == "null"
    assert cfg.min_tokens == 250
    assert "system" in cfg.protect_roles


def test_count_tokens_sums_message_content_char_quarter():
    msgs = [{"role": "user", "content": "a" * 40}]  # 40 chars -> ~10 tokens
    assert count_tokens(msgs) == 10


def test_count_tokens_ignores_non_string_content():
    msgs = [{"role": "user", "content": None}, {"role": "user"}]
    assert count_tokens(msgs) == 0


def test_optimize_result_holds_metrics():
    r = OptimizeResult(messages=[], tokens_before=100, tokens_after=40, tokens_saved=60, backend="x")
    assert r.tokens_saved == 60 and r.backend == "x"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest harness/tests/test_optimizer_base.py -v`
Expected: FAIL — `ModuleNotFoundError: harness.optimizer.base`.

- [ ] **Step 3: Write minimal implementation**

Create `harness/optimizer/__init__.py` as an empty file (populated in Task 7). Create `harness/optimizer/backends/__init__.py` as an empty file. Create `harness/optimizer/base.py`:

```python
"""
Provider-agnostic context-optimizer contracts (ADR-0021, REQ-E1/E2/E3).
No conductor-specific imports — this package is extractable/reusable by any system.
"""
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable


@dataclass
class OptimizeConfig:
    backend: str = "null"                       # null | caveman | headroom | <registered>
    min_tokens: int = 250                       # skip messages below this token estimate
    protect_roles: tuple[str, ...] = ("system",)  # roles never compressed
    protect_tags: tuple[str, ...] = ("__gate_evidence__", "__code_edit__")  # markers in message content
    target_ratio: Optional[float] = None        # backend-specific keep ratio


@dataclass
class OptimizeResult:
    messages: list[dict[str, Any]]
    tokens_before: int = 0
    tokens_after: int = 0
    tokens_saved: int = 0
    transforms_applied: list[str] = field(default_factory=list)
    backend: str = "null"


def count_tokens(messages: list[dict[str, Any]]) -> int:
    """Cheap char/4 token estimate over message string content. Self-contained (no external tokenizer)."""
    total = 0
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            total += len(content) // 4
    return total


@runtime_checkable
class Compressor(Protocol):
    name: str

    def available(self) -> bool:
        """True if this backend's dependencies are importable and usable."""
        ...

    def optimize(self, messages: list[dict[str, Any]], cfg: OptimizeConfig) -> OptimizeResult:
        """Return compressed messages (same count + order) + metrics."""
        ...

    def retrieve(self, handle: str) -> Optional[str]:
        """Reversible backends return the original for a handle; others return None."""
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest harness/tests/test_optimizer_base.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add harness/optimizer/__init__.py harness/optimizer/base.py harness/optimizer/backends/__init__.py harness/tests/test_optimizer_base.py
git commit -m "feat(optimizer): add base contracts — Compressor Protocol, config, result, token count (ADR-0021)"
```

---

## Task 2: Null backend (passthrough)

**Files:**
- Create: `harness/optimizer/backends/null.py`
- Test: `harness/tests/test_optimizer_null.py`

- [ ] **Step 1: Write the failing test**

Create `harness/tests/test_optimizer_null.py`:

```python
from harness.optimizer.base import OptimizeConfig
from harness.optimizer.backends.null import NullCompressor


def test_null_is_always_available():
    assert NullCompressor().available() is True


def test_null_returns_messages_unchanged_with_equal_token_counts():
    msgs = [{"role": "user", "content": "x" * 40}]
    r = NullCompressor().optimize(msgs, OptimizeConfig())
    assert r.messages is msgs
    assert r.tokens_before == r.tokens_after == 10
    assert r.tokens_saved == 0
    assert r.backend == "null"


def test_null_retrieve_returns_none():
    assert NullCompressor().retrieve("any") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest harness/tests/test_optimizer_null.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Create `harness/optimizer/backends/null.py`:

```python
"""Null backend — passthrough. Always available, zero deps, cannot alter content (ADR-0021 default)."""
from typing import Any, Optional

from harness.optimizer.base import OptimizeConfig, OptimizeResult, count_tokens


class NullCompressor:
    name = "null"

    def available(self) -> bool:
        return True

    def optimize(self, messages: list[dict[str, Any]], cfg: OptimizeConfig) -> OptimizeResult:
        n = count_tokens(messages)
        return OptimizeResult(messages=messages, tokens_before=n, tokens_after=n, tokens_saved=0, backend="null")

    def retrieve(self, handle: str) -> Optional[str]:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest harness/tests/test_optimizer_null.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add harness/optimizer/backends/null.py harness/tests/test_optimizer_null.py
git commit -m "feat(optimizer): add null passthrough backend (ADR-0021 default)"
```

---

## Task 3: Safety guard (`guard.py`)

**Files:**
- Create: `harness/optimizer/guard.py`
- Test: `harness/tests/test_optimizer_guard.py`

- [ ] **Step 1: Write the failing test**

Create `harness/tests/test_optimizer_guard.py`:

```python
from harness.optimizer.base import OptimizeConfig
from harness.optimizer.guard import is_protected, restore_protected


def test_protected_by_role():
    cfg = OptimizeConfig()
    assert is_protected({"role": "system", "content": "x"}, cfg) is True
    assert is_protected({"role": "user", "content": "x"}, cfg) is False


def test_protected_by_tag():
    cfg = OptimizeConfig()
    assert is_protected({"role": "user", "content": "code __gate_evidence__ here"}, cfg) is True


def test_protected_when_below_min_tokens():
    cfg = OptimizeConfig(min_tokens=100)
    assert is_protected({"role": "user", "content": "short"}, cfg) is True  # tiny -> not worth compressing


def test_restore_protected_overwrites_backend_changes_on_protected_slots():
    cfg = OptimizeConfig()
    original = [
        {"role": "system", "content": "S" * 400},
        {"role": "user", "content": "U" * 400},
    ]
    backend_out = [
        {"role": "system", "content": "MANGLED"},   # backend wrongly touched protected system msg
        {"role": "user", "content": "compressed-u"},
    ]
    fixed = restore_protected(original, backend_out, cfg)
    assert fixed[0]["content"] == "S" * 400          # protected restored byte-identical
    assert fixed[1]["content"] == "compressed-u"     # non-protected backend output kept


def test_restore_protected_falls_back_to_original_on_length_mismatch():
    cfg = OptimizeConfig()
    original = [{"role": "user", "content": "U" * 400}]
    backend_out = []  # backend dropped a message — unsafe
    assert restore_protected(original, backend_out, cfg) is original
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest harness/tests/test_optimizer_guard.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Create `harness/optimizer/guard.py`:

```python
"""
Facade-enforced safety invariants (ADR-0021). These hold regardless of backend:
- protected messages (by role, by tag, or below min_tokens) are restored byte-identical;
- if a backend changes the message count, the whole result is rejected for the original.
This makes a Law-1 violation (compressing gate evidence / code) structurally impossible.
"""
from typing import Any

from harness.optimizer.base import OptimizeConfig, count_tokens


def is_protected(message: dict[str, Any], cfg: OptimizeConfig) -> bool:
    if message.get("role") in cfg.protect_roles:
        return True
    content = message.get("content")
    if isinstance(content, str):
        if any(tag in content for tag in cfg.protect_tags):
            return True
        if count_tokens([message]) < cfg.min_tokens:
            return True
    else:
        return True  # non-string content (tool blocks, images) — never compress
    return False


def restore_protected(
    original: list[dict[str, Any]], compressed: list[dict[str, Any]], cfg: OptimizeConfig
) -> list[dict[str, Any]]:
    """Overwrite protected slots with their originals. Reject (return original) on count mismatch."""
    if len(original) != len(compressed):
        return original
    out = list(compressed)
    for i, orig in enumerate(original):
        if is_protected(orig, cfg):
            out[i] = orig
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest harness/tests/test_optimizer_guard.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add harness/optimizer/guard.py harness/tests/test_optimizer_guard.py
git commit -m "feat(optimizer): add safety guard — protect-list + min-tokens + restore invariant (REQ-E3)"
```

---

## Task 4: Backend registry (`registry.py`)

**Files:**
- Create: `harness/optimizer/registry.py`
- Test: `harness/tests/test_optimizer_registry.py`

- [ ] **Step 1: Write the failing test**

Create `harness/tests/test_optimizer_registry.py`:

```python
import pytest
from harness.optimizer import registry
from harness.optimizer.base import OptimizeConfig


class _FakeUnavailable:
    name = "fake"
    def available(self): return False
    def optimize(self, messages, cfg): raise AssertionError("must not be called")
    def retrieve(self, handle): return None


@pytest.fixture(autouse=True)
def _clean_registry():
    saved = dict(registry._BACKENDS)
    registry._BACKENDS.clear()
    registry.register("null", lambda: _Null())
    yield
    registry._BACKENDS.clear()
    registry._BACKENDS.update(saved)


class _Null:
    name = "null"
    def available(self): return True
    def optimize(self, messages, cfg): return None
    def retrieve(self, handle): return None


def test_resolve_returns_registered_available_backend():
    registry.register("x", lambda: _Null())
    assert registry.resolve("x").name == "null"  # _Null instance


def test_resolve_unknown_name_degrades_to_null():
    assert registry.resolve("does_not_exist").name == "null"


def test_resolve_unavailable_backend_degrades_to_null():
    registry.register("fake", lambda: _FakeUnavailable())
    assert registry.resolve("fake").name == "null"


def test_env_override_wins(monkeypatch):
    registry.register("fake", lambda: _FakeUnavailable())
    monkeypatch.setenv("CONDUCTOR_OPTIMIZER", "fake")
    # env says fake, fake unavailable -> degrade to null
    assert registry.resolve_from_config(OptimizeConfig(backend="x")).name == "null"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest harness/tests/test_optimizer_registry.py -v`
Expected: FAIL — `ModuleNotFoundError` / `AttributeError`.

- [ ] **Step 3: Write minimal implementation**

Create `harness/optimizer/registry.py`:

```python
"""
Backend registry + resolution (ADR-0021). resolve() always returns a usable backend:
an unknown name or an unavailable backend degrades to 'null' so the host never crashes.
Third parties register backends via register(name, factory).
"""
import os
from typing import Any, Callable

from harness.optimizer.base import Compressor, OptimizeConfig

_BACKENDS: dict[str, Callable[[], Compressor]] = {}


def register(name: str, factory: Callable[[], Compressor]) -> None:
    _BACKENDS[name] = factory


def resolve(name: str) -> Compressor:
    factory = _BACKENDS.get(name)
    if factory is None:
        return _BACKENDS["null"]()
    inst = factory()
    if not inst.available():
        return _BACKENDS["null"]()
    return inst


def resolve_from_config(cfg: OptimizeConfig) -> Compressor:
    name = os.environ.get("CONDUCTOR_OPTIMIZER", cfg.backend)
    return resolve(name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest harness/tests/test_optimizer_registry.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add harness/optimizer/registry.py harness/tests/test_optimizer_registry.py
git commit -m "feat(optimizer): add backend registry with degrade-to-null + env override (ADR-0021)"
```

---

## Task 5: Caveman backend (stdlib prose trim)

**Files:**
- Create: `harness/optimizer/backends/caveman.py`
- Test: `harness/tests/test_optimizer_caveman.py`

- [ ] **Step 1: Write the failing test**

Create `harness/tests/test_optimizer_caveman.py`:

```python
from harness.optimizer.base import OptimizeConfig
from harness.optimizer.backends.caveman import CavemanCompressor


def test_caveman_is_available():
    assert CavemanCompressor().available() is True


def test_caveman_trims_filler_and_collapses_whitespace():
    text = "The result is   basically    just the   value."
    msgs = [{"role": "assistant", "content": text}]
    r = CavemanCompressor().optimize(msgs, OptimizeConfig(min_tokens=0))
    out = r.messages[0]["content"]
    assert "basically" not in out
    assert "  " not in out                 # collapsed runs of spaces
    assert r.tokens_after <= r.tokens_before
    assert "caveman" in r.transforms_applied[0]


def test_caveman_is_deterministic():
    msgs = [{"role": "assistant", "content": "This is really just a simple test."}]
    a = CavemanCompressor().optimize(msgs, OptimizeConfig(min_tokens=0)).messages
    b = CavemanCompressor().optimize(msgs, OptimizeConfig(min_tokens=0)).messages
    assert a == b


def test_caveman_preserves_message_count_and_roles():
    msgs = [{"role": "assistant", "content": "really really long " * 30}]
    r = CavemanCompressor().optimize(msgs, OptimizeConfig(min_tokens=0))
    assert len(r.messages) == 1
    assert r.messages[0]["role"] == "assistant"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest harness/tests/test_optimizer_caveman.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Create `harness/optimizer/backends/caveman.py`:

```python
"""
Caveman backend — stdlib prose trim (ADR-0021). Deterministic, zero deps. Drops filler words and
collapses whitespace in string message content. Conservative: only edits content, never structure.
Inspiration: github.com/juliusbrussee/caveman (output-style compression).
"""
import re
from typing import Any, Optional

from harness.optimizer.base import OptimizeConfig, OptimizeResult, count_tokens

_FILLER = (
    "basically", "really", "actually", "simply", "just", "very", "quite",
    "in order to", "of course", "as you can see", "it should be noted that",
)
_FILLER_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in _FILLER) + r")\b", re.IGNORECASE)
_WS_RE = re.compile(r"[ \t]{2,}")


def _trim(text: str) -> str:
    text = _FILLER_RE.sub("", text)
    text = _WS_RE.sub(" ", text)
    text = re.sub(r" +([.,;:!?])", r"\1", text)  # tidy space before punctuation
    return text.strip()


class CavemanCompressor:
    name = "caveman"

    def available(self) -> bool:
        return True

    def optimize(self, messages: list[dict[str, Any]], cfg: OptimizeConfig) -> OptimizeResult:
        before = count_tokens(messages)
        out: list[dict[str, Any]] = []
        for m in messages:
            content = m.get("content")
            if isinstance(content, str):
                out.append({**m, "content": _trim(content)})
            else:
                out.append(m)
        after = count_tokens(out)
        return OptimizeResult(
            messages=out, tokens_before=before, tokens_after=after,
            tokens_saved=max(0, before - after), transforms_applied=["caveman:prose-trim"], backend="caveman",
        )

    def retrieve(self, handle: str) -> Optional[str]:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest harness/tests/test_optimizer_caveman.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add harness/optimizer/backends/caveman.py harness/tests/test_optimizer_caveman.py
git commit -m "feat(optimizer): add caveman stdlib prose-trim backend (ADR-0021)"
```

---

## Task 6: Headroom backend (opt-in, lazy-import)

**Files:**
- Create: `harness/optimizer/backends/headroom.py`
- Test: `harness/tests/test_optimizer_headroom.py`

**Concept:** the heavy backend. `available()` returns True only if `headroom` is importable; `optimize()` lazy-imports and calls `headroom.compress`. In this env (headroom not installed) `available()` is False, so the registry degrades to null — which is exactly the opt-in/degrade behavior we test.

- [ ] **Step 1: Write the failing test**

Create `harness/tests/test_optimizer_headroom.py`:

```python
from harness.optimizer.backends.headroom import HeadroomCompressor


def test_headroom_available_reflects_import(monkeypatch):
    hc = HeadroomCompressor()
    # headroom is not installed in this env -> not available
    assert hc.available() is False


def test_headroom_name():
    assert HeadroomCompressor().name == "headroom"


def test_headroom_retrieve_is_none_without_store():
    assert HeadroomCompressor().retrieve("h") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest harness/tests/test_optimizer_headroom.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Create `harness/optimizer/backends/headroom.py`:

```python
"""
Headroom backend (ADR-0021, opt-in). Lazy-imports the heavy `headroom-ai` dependency; if it is not
installed, available() is False and the registry degrades to null. Real compression via
headroom.compress when present. CCR retrieve() wiring is deferred to the pipeline plan.
"""
import importlib.util
from typing import Any, Optional

from harness.optimizer.base import OptimizeConfig, OptimizeResult, count_tokens


class HeadroomCompressor:
    name = "headroom"

    def available(self) -> bool:
        return importlib.util.find_spec("headroom") is not None

    def optimize(self, messages: list[dict[str, Any]], cfg: OptimizeConfig) -> OptimizeResult:
        from headroom import compress  # lazy — only when available

        kwargs: dict[str, Any] = {}
        if cfg.target_ratio is not None:
            kwargs["target_ratio"] = cfg.target_ratio
        result = compress(messages, **kwargs)
        before = getattr(result, "tokens_before", count_tokens(messages))
        after = getattr(result, "tokens_after", count_tokens(result.messages))
        return OptimizeResult(
            messages=result.messages, tokens_before=before, tokens_after=after,
            tokens_saved=max(0, before - after),
            transforms_applied=list(getattr(result, "transforms_applied", ["headroom"])),
            backend="headroom",
        )

    def retrieve(self, handle: str) -> Optional[str]:
        return None  # CCR retrieve wiring deferred to the pipeline plan
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest harness/tests/test_optimizer_headroom.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add harness/optimizer/backends/headroom.py harness/tests/test_optimizer_headroom.py
git commit -m "feat(optimizer): add opt-in lazy-import headroom backend (ADR-0021)"
```

---

## Task 7: Facade entry point (`__init__.py`)

**Files:**
- Modify: `harness/optimizer/__init__.py` (was empty from Task 1)
- Test: `harness/tests/test_optimizer_facade.py`

- [ ] **Step 1: Write the failing test**

Create `harness/tests/test_optimizer_facade.py`:

```python
from harness.optimizer import optimize
from harness.optimizer.base import OptimizeConfig


def test_default_is_passthrough_null():
    msgs = [{"role": "assistant", "content": "really just a value " * 40}]
    r = optimize(msgs)  # default null
    assert r.backend == "null"
    assert r.messages == msgs


def test_caveman_backend_compresses_but_protects_system():
    msgs = [
        {"role": "system", "content": "really important instructions " * 30},
        {"role": "assistant", "content": "this is really just basically the answer " * 30},
    ]
    r = optimize(msgs, OptimizeConfig(backend="caveman", min_tokens=0))
    assert r.backend == "caveman"
    assert r.messages[0]["content"] == msgs[0]["content"]   # system protected, byte-identical
    assert "basically" not in r.messages[1]["content"]      # assistant trimmed
    assert r.tokens_after <= r.tokens_before


def test_unknown_backend_degrades_to_null():
    msgs = [{"role": "assistant", "content": "x" * 400}]
    r = optimize(msgs, OptimizeConfig(backend="nope"))
    assert r.backend == "null"
    assert r.messages == msgs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest harness/tests/test_optimizer_facade.py -v`
Expected: FAIL — `ImportError: cannot import name 'optimize'`.

- [ ] **Step 3: Write minimal implementation**

Replace the contents of `harness/optimizer/__init__.py` with:

```python
"""
Pluggable context-optimizer facade (ADR-0021). One entry point: optimize(messages, cfg).
Default backend is 'null' (passthrough) so the optimizer is inert out of the box. Backends are
registered below; third parties may register more via harness.optimizer.registry.register.
The facade enforces the safety guard (protect-list restore, degrade-to-null) on every call.
"""
from typing import Any, Optional

from harness.optimizer.base import Compressor, OptimizeConfig, OptimizeResult, count_tokens
from harness.optimizer import registry
from harness.optimizer.guard import restore_protected
from harness.optimizer.backends.null import NullCompressor
from harness.optimizer.backends.caveman import CavemanCompressor
from harness.optimizer.backends.headroom import HeadroomCompressor

# Register built-in backends. null + caveman are baked in (zero deps); headroom is opt-in.
registry.register("null", lambda: NullCompressor())
registry.register("caveman", lambda: CavemanCompressor())
registry.register("headroom", lambda: HeadroomCompressor())


def optimize(messages: list[dict[str, Any]], cfg: Optional[OptimizeConfig] = None) -> OptimizeResult:
    """Compress what the LLM reads via the configured backend, enforcing safety invariants.

    Default (no cfg) is passthrough. Any backend failure degrades to null. Protected messages
    (system role, protect-tagged, or below min_tokens) are restored byte-identical.
    """
    cfg = cfg or OptimizeConfig()
    backend = registry.resolve_from_config(cfg)
    try:
        result = backend.optimize(messages, cfg)
    except Exception:
        result = NullCompressor().optimize(messages, cfg)
    result.messages = restore_protected(messages, result.messages, cfg)
    # recompute after-count in case protected restore changed it
    result.tokens_after = count_tokens(result.messages)
    result.tokens_saved = max(0, result.tokens_before - result.tokens_after)
    return result


__all__ = ["optimize", "OptimizeConfig", "OptimizeResult", "Compressor", "registry"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest harness/tests/test_optimizer_facade.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`
Expected: all prior tests + new optimizer tests pass; still exactly 3 pre-existing `openai`-missing failures.

- [ ] **Step 6: Commit**

```bash
git add harness/optimizer/__init__.py harness/tests/test_optimizer_facade.py
git commit -m "feat(optimizer): wire facade entry point — default null, guard-enforced, degrade-safe (ADR-0021)"
```

---

## Task 8: Final verification

**Files:** none

- [ ] **Step 1: Full suite**

Run: `python3 -m pytest -q`
Expected: green except the 3 pre-existing `openai`-missing failures.

- [ ] **Step 2: Smoke — flag-driven backend swap with protect invariant**

Run:
```bash
python3 -c "
from harness.optimizer import optimize
from harness.optimizer.base import OptimizeConfig
m=[{'role':'system','content':'keep me '*50},{'role':'assistant','content':'this is really just basically it '*30}]
print('null  ->', optimize(m).backend)
r=optimize(m, OptimizeConfig(backend='caveman', min_tokens=0))
print('caveman->', r.backend, 'saved', r.tokens_saved, 'sys-intact', r.messages[0]['content']==m[0]['content'])
print('bad   ->', optimize(m, OptimizeConfig(backend='zzz')).backend)
"
```
Expected: `null -> null`; `caveman-> caveman saved <N>0 sys-intact True`; `bad -> null`.

- [ ] **Step 3: Commit any touch-ups** (only if needed)

```bash
git add -A && git commit -m "test: optimizer facade green"
```

---

## Notes for the pipeline plan
- Call `optimize(messages, cfg)` at the orchestrator read-path and on tier2 maker briefs; tag gate-evidence/code-edit content with `__gate_evidence__` / `__code_edit__` so the guard protects it.
- Wire headroom's CCR `retrieve()` through the backend's `retrieve()` method + expose a retrieval affordance to the orchestrator.
- Add `[optimizer-headroom]` extra to `pyproject.toml` so `pip install conductor[optimizer-headroom]` pulls `headroom-ai`; keep the base install dep-free.
