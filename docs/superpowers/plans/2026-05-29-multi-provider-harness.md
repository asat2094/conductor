# Multi-Provider Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend conductor to route tasks across NVIDIA NIM, Gemini, DeepSeek, OpenRouter, OpenCode Zen, and gemma4 using cost-normalised accuracy ranking, reactive rate-limit fallback, and incremental per-provider score tracking.

**Architecture:** A unified `provider_call.py` wraps all providers behind one interface (ollama adapter + OpenAI-compat adapter). `orchestrate.py` tries ranked providers in order, falls back on `RateLimitError`/`ProviderError`/low score, and updates provider profiles after every task. `pipeline.py` and `parallel_delegate.py` delegate to the orchestrator instead of calling gemma4 directly.

**Tech Stack:** Python 3.11+, `openai` SDK (pip), sqlite3 (stdlib), `urllib.request` (stdlib), pytest

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Create | `harness/providers.json` | Provider registry (type, model, base_url, cost, tier) |
| Create | `harness/providers.py` | `load_providers()` — parse registry into ProviderConfig dicts |
| Create | `harness/provider_call.py` | Unified caller: `RateLimitError`, `ProviderError`, `run()` |
| Create | `harness/orchestrate.py` | `orchestrate()`, `orchestrate_parallel()`, `EscalateToClaudeError` |
| Create | `harness/tests/test_providers.py` | Tests for load_providers() |
| Create | `harness/tests/test_provider_call.py` | Tests for run(), RateLimitError, ProviderError |
| Create | `harness/tests/test_orchestrate.py` | Tests for orchestrate(), fallback, escalation |
| Modify | `harness/models.py` | Add `ProviderConfig` dataclass; widen `EvalResult.agent` to `str` |
| Modify | `harness/router.py` | Add `rank_providers()` alongside existing `route()` |
| Modify | `harness/capability_profiles.json` | Add entries for all new providers |
| Modify | `harness/pipeline.py` | Replace `route()+gemma4_run()` with `orchestrate()` |
| Modify | `harness/parallel_delegate.py` | Replace `_gemma4_run` with `orchestrate()`, shared busy pool |
| Modify | `harness/tests/test_router.py` | Add `rank_providers()` tests |
| Modify | `harness/tests/test_models.py` | Add `ProviderConfig` tests |

---

## Task 1: ProviderConfig dataclass + providers.json + load_providers()

**Files:**
- Modify: `harness/models.py`
- Create: `harness/providers.json`
- Create: `harness/providers.py`
- Create: `harness/tests/test_providers.py`
- Modify: `harness/tests/test_models.py`

- [ ] **Step 1.1: Write failing tests for ProviderConfig and load_providers**

Create `harness/tests/test_providers.py`:

```python
import json
import pytest
from harness.models import ProviderConfig


def test_provider_config_fields():
    p = ProviderConfig(
        name="deepseek",
        type="openai_compat",
        model="deepseek-coder",
        base_url="https://api.deepseek.com/v1",
        cost_per_1k_tokens=0.0014,
        tier="cloud_cheap",
        api_key_env="DEEPSEEK_API_KEY",
    )
    assert p.name == "deepseek"
    assert p.api_key_env == "DEEPSEEK_API_KEY"


def test_provider_config_api_key_env_defaults_empty():
    p = ProviderConfig("gemma4", "ollama", "gemma4:latest", "http://localhost:11434", 0.0, "local")
    assert p.api_key_env == ""


def test_load_providers_returns_all_entries(tmp_path):
    from harness.providers import load_providers
    cfg = tmp_path / "providers.json"
    cfg.write_text(json.dumps({
        "gemma4": {"type": "ollama", "model": "gemma4:latest",
                   "base_url": "http://localhost:11434", "cost_per_1k_tokens": 0.0, "tier": "local"},
        "deepseek": {"type": "openai_compat", "model": "deepseek-coder",
                     "base_url": "https://api.deepseek.com/v1", "cost_per_1k_tokens": 0.0014,
                     "tier": "cloud_cheap", "api_key_env": "DEEPSEEK_API_KEY"},
    }))
    providers = load_providers(cfg)
    assert set(providers.keys()) == {"gemma4", "deepseek"}
    assert providers["gemma4"].type == "ollama"
    assert providers["deepseek"].api_key_env == "DEEPSEEK_API_KEY"


def test_load_providers_sets_name_from_key(tmp_path):
    from harness.providers import load_providers
    cfg = tmp_path / "providers.json"
    cfg.write_text(json.dumps({
        "nim": {"type": "openai_compat", "model": "nvidia/llama3", "base_url": "http://x",
                "cost_per_1k_tokens": 0.001, "tier": "cloud_cheap"}
    }))
    providers = load_providers(cfg)
    assert providers["nim"].name == "nim"


def test_load_providers_strips_underscore_keys(tmp_path):
    from harness.providers import load_providers
    cfg = tmp_path / "providers.json"
    cfg.write_text(json.dumps({
        "test": {"type": "openai_compat", "model": "m", "base_url": "http://x",
                 "cost_per_1k_tokens": 0.1, "tier": "cloud_cheap",
                 "_note": "should be ignored"}
    }))
    providers = load_providers(cfg)
    assert "test" in providers  # no crash from _note field
```

- [ ] **Step 1.2: Run tests — expect failures**

```bash
cd /Users/ankitatiwari/Desktop/claude-playground/conductor
/opt/homebrew/bin/pytest harness/tests/test_providers.py -v
```

Expected: ImportError or AttributeError — ProviderConfig and load_providers don't exist yet.

- [ ] **Step 1.3: Add ProviderConfig to models.py**

In `harness/models.py`, after the `CapabilityProfile` dataclass, add:

```python
@dataclass
class ProviderConfig:
    name: str
    type: str           # "ollama" | "openai_compat"
    model: str
    base_url: str
    cost_per_1k_tokens: float
    tier: str
    api_key_env: str = ""
```

Also widen `EvalResult.agent` type hint from `AgentType` to `str` (AgentType is already `str, Enum` so no runtime change, but allows new provider name strings):

```python
@dataclass
class EvalResult:
    subtask_id: str
    agent: str          # was AgentType — widened to str; AgentType values still work
    score: int
    syntax_score: int
    test_score: int
    scope_score: int
    semantic_score: int
    details: str
    changed_files: list[str] = field(default_factory=list)
```

- [ ] **Step 1.4: Create harness/providers.py**

```python
import json
from pathlib import Path

from harness.models import ProviderConfig

_DEFAULT_PATH = Path(__file__).parent / "providers.json"


def load_providers(path: Path = _DEFAULT_PATH) -> dict[str, ProviderConfig]:
    data = json.loads(path.read_text())
    result = {}
    for name, cfg in data.items():
        clean = {k: v for k, v in cfg.items() if not k.startswith("_")}
        result[name] = ProviderConfig(name=name, **clean)
    return result
```

- [ ] **Step 1.5: Create harness/providers.json**

```json
{
  "gemma4": {
    "type": "ollama",
    "model": "gemma4:latest",
    "base_url": "http://localhost:11434",
    "cost_per_1k_tokens": 0.0,
    "tier": "local"
  },
  "deepseek": {
    "type": "openai_compat",
    "model": "deepseek-coder",
    "base_url": "https://api.deepseek.com/v1",
    "api_key_env": "DEEPSEEK_API_KEY",
    "cost_per_1k_tokens": 0.0014,
    "tier": "cloud_cheap"
  },
  "nim": {
    "type": "openai_compat",
    "model": "nvidia/llama-3.1-nemotron-70b-instruct",
    "base_url": "https://integrate.api.nvidia.com/v1",
    "api_key_env": "NIM_API_KEY",
    "cost_per_1k_tokens": 0.001,
    "tier": "cloud_cheap"
  },
  "gemini": {
    "type": "openai_compat",
    "model": "gemini-2.0-flash",
    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "api_key_env": "GEMINI_API_KEY",
    "cost_per_1k_tokens": 0.00015,
    "tier": "cloud_cheap"
  },
  "openrouter": {
    "type": "openai_compat",
    "model": "deepseek/deepseek-coder-v2",
    "base_url": "https://openrouter.ai/api/v1",
    "api_key_env": "OPENROUTER_API_KEY",
    "cost_per_1k_tokens": 0.0014,
    "tier": "cloud_cheap"
  },
  "opencode_zen": {
    "type": "openai_compat",
    "model": "zen",
    "base_url": "https://opencode.ai/api/v1",
    "api_key_env": "OPENCODE_API_KEY",
    "cost_per_1k_tokens": 0.002,
    "tier": "cloud_cheap",
    "_note": "verify base_url at opencode.ai/zen before use"
  }
}
```

- [ ] **Step 1.6: Run tests — expect pass**

```bash
/opt/homebrew/bin/pytest harness/tests/test_providers.py harness/tests/test_models.py -v
```

Expected: all PASS. Also run full suite to check no regressions:

```bash
/opt/homebrew/bin/pytest -q
```

Expected: all existing tests still pass (EvalResult.agent type hint change is backward-compatible).

- [ ] **Step 1.7: Commit**

```bash
git add harness/models.py harness/providers.py harness/providers.json harness/tests/test_providers.py
git commit -m "feat: add ProviderConfig dataclass, providers.json registry, load_providers()"
```

---

## Task 2: Install openai + provider_call.py

**Files:**
- Create: `harness/provider_call.py`
- Create: `harness/tests/test_provider_call.py`

- [ ] **Step 2.1: Install openai SDK**

```bash
pip install openai
```

Verify:
```bash
python3 -c "import openai; print(openai.__version__)"
```

Expected: prints a version string (1.x or later).

- [ ] **Step 2.2: Write failing tests**

Create `harness/tests/test_provider_call.py`:

```python
import json
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from harness.models import ProviderConfig


def _ollama_provider():
    return ProviderConfig("gemma4", "ollama", "gemma4:latest",
                          "http://localhost:11434", 0.0, "local")


def _openai_provider():
    return ProviderConfig("deepseek", "openai_compat", "deepseek-coder",
                          "https://api.deepseek.com/v1", 0.0014, "cloud_cheap", "DEEPSEEK_API_KEY")


def _fake_urlopen(response_text: str):
    payload = json.dumps({"response": response_text}).encode()
    mock = MagicMock()
    mock.read.return_value = payload
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def test_ollama_extracts_code_and_writes_file(tmp_path):
    from harness.provider_call import run
    (tmp_path / "f.py").write_text("x = 1")
    with patch("urllib.request.urlopen", return_value=_fake_urlopen("```python\ny = 2\n```")):
        _, code = run(_ollama_provider(), str(tmp_path), "update x to y", ["f.py"])
    assert code == "y = 2\n"
    assert (tmp_path / "f.py").read_text() == "y = 2\n"


def test_ollama_returns_none_when_no_code_block(tmp_path):
    from harness.provider_call import run
    (tmp_path / "f.py").write_text("x = 1")
    with patch("urllib.request.urlopen", return_value=_fake_urlopen("Sorry, I cannot help.")):
        _, code = run(_ollama_provider(), str(tmp_path), "update x", ["f.py"])
    assert code is None


def test_ollama_raises_rate_limit_on_429(tmp_path):
    from harness.provider_call import run, RateLimitError
    (tmp_path / "f.py").write_text("x = 1")
    err = urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(RateLimitError):
            run(_ollama_provider(), str(tmp_path), "task", ["f.py"])


def test_ollama_raises_provider_error_on_500(tmp_path):
    from harness.provider_call import run, ProviderError
    (tmp_path / "f.py").write_text("x = 1")
    err = urllib.error.HTTPError("url", 500, "Internal Server Error", {}, None)
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(ProviderError):
            run(_ollama_provider(), str(tmp_path), "task", ["f.py"])


def test_openai_compat_extracts_code_and_writes_file(tmp_path):
    from harness.provider_call import run
    (tmp_path / "f.py").write_text("x = 1")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = "```python\ny = 2\n```"
    with patch("openai.OpenAI", return_value=mock_client):
        _, code = run(_openai_provider(), str(tmp_path), "update x", ["f.py"])
    assert code == "y = 2\n"
    assert (tmp_path / "f.py").read_text() == "y = 2\n"


def test_openai_compat_raises_rate_limit_on_429(tmp_path):
    import openai as _openai
    from harness.provider_call import run, RateLimitError
    (tmp_path / "f.py").write_text("x = 1")
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = _openai.RateLimitError(
        "rate limit", response=MagicMock(status_code=429), body={}
    )
    with patch("openai.OpenAI", return_value=mock_client):
        with pytest.raises(RateLimitError):
            run(_openai_provider(), str(tmp_path), "task", ["f.py"])


def test_openai_compat_raises_provider_error_on_api_error(tmp_path):
    import openai as _openai
    from harness.provider_call import run, ProviderError
    (tmp_path / "f.py").write_text("x = 1")
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = _openai.APIConnectionError(request=MagicMock())
    with patch("openai.OpenAI", return_value=mock_client):
        with pytest.raises(ProviderError):
            run(_openai_provider(), str(tmp_path), "task", ["f.py"])


def test_run_creates_new_file_when_not_exists(tmp_path):
    from harness.provider_call import run
    # f.py does NOT exist
    with patch("urllib.request.urlopen", return_value=_fake_urlopen("```python\ny = 2\n```")):
        _, code = run(_ollama_provider(), str(tmp_path), "create f.py", ["f.py"])
    assert code == "y = 2\n"
    assert (tmp_path / "f.py").exists()
```

- [ ] **Step 2.3: Run tests — expect failures**

```bash
/opt/homebrew/bin/pytest harness/tests/test_provider_call.py -v
```

Expected: ImportError — `harness.provider_call` doesn't exist yet.

- [ ] **Step 2.4: Create harness/provider_call.py**

```python
"""
provider_call.py — unified model caller.

run(provider, workdir, task, files, diff_mode=False) -> (response_text, code_or_none)

Raises:
    RateLimitError  — HTTP 429 or openai.RateLimitError
    ProviderError   — any other call failure (timeout, 5xx, connection refused)
"""
from __future__ import annotations

import json as _json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from harness.gemma4_call import apply_patch, extract_code_block, extract_diff_block
from harness.models import ProviderConfig


class RateLimitError(Exception):
    pass


class ProviderError(Exception):
    pass


def _build_prompt(workdir: str, task: str, files: list[str], diff_mode: bool = False) -> str:
    root = Path(workdir)
    target = files[0]
    target_exists = (root / target).exists()
    sections = [task, ""]
    for f in files:
        path = root / f
        if path.exists():
            sections.append(f"--- FILE: {f} ---")
            sections.append(path.read_text())
            sections.append("")
    if diff_mode and target_exists:
        sections.append(
            f"Output ONLY a unified diff (--- {target}\n+++ {target}) "
            "of the changes inside a single fenced diff block. No explanation, no other text."
        )
    elif target_exists:
        sections.append(
            f"Output ONLY the complete modified version of {target} "
            "inside a single fenced code block. No explanation, no other text."
        )
    else:
        sections.append(
            f"Output ONLY the complete contents of the new file {target} "
            "inside a single fenced code block. No explanation, no other text."
        )
    return "\n".join(sections)


def _run_ollama(
    provider: ProviderConfig, workdir: str, task: str, files: list[str], diff_mode: bool = False
) -> tuple[str, str | None]:
    root = Path(workdir)
    target = root / files[0]
    target_exists = target.exists()
    prompt = _build_prompt(workdir, task, files, diff_mode)
    url = provider.base_url.rstrip("/") + "/api/generate"
    payload = _json.dumps({"model": provider.model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    print(f"[{provider.name}] Calling ollama ({provider.model})...", file=sys.stderr)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = _json.loads(resp.read())
        text = data.get("response", "")
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimitError(f"{provider.name}: rate limited") from e
        raise ProviderError(f"{provider.name}: HTTP {e.code}") from e
    except Exception as e:
        raise ProviderError(f"{provider.name}: {e}") from e

    if diff_mode and target_exists:
        diff = extract_diff_block(text)
        if diff and apply_patch(diff, target):
            print(f"[{provider.name}] Patch applied to {target}", file=sys.stderr)
            return text, diff
        print(f"\n[{provider.name}] WARNING: diff failed — falling back to full rewrite.", file=sys.stderr)
        return _run_ollama(provider, workdir, task, files, diff_mode=False)

    code = extract_code_block(text)
    if not code:
        print(f"\n[{provider.name}] WARNING: no code block in response.", file=sys.stderr)
        return text, None
    target.write_text(code)
    print(f"[{provider.name}] Written to {target}", file=sys.stderr)
    return text, code


def _run_openai_compat(
    provider: ProviderConfig, workdir: str, task: str, files: list[str], diff_mode: bool = False
) -> tuple[str, str | None]:
    try:
        import openai
    except ImportError:
        raise ProviderError(f"{provider.name}: openai package required — run: pip install openai")

    root = Path(workdir)
    target = root / files[0]
    target_exists = target.exists()
    api_key = os.environ.get(provider.api_key_env, "no-key") if provider.api_key_env else "no-key"
    client = openai.OpenAI(base_url=provider.base_url, api_key=api_key)
    prompt = _build_prompt(workdir, task, files, diff_mode)
    print(f"[{provider.name}] Calling {provider.model}...", file=sys.stderr)
    try:
        resp = client.chat.completions.create(
            model=provider.model,
            messages=[{"role": "user", "content": prompt}],
            timeout=180,
        )
        text = resp.choices[0].message.content or ""
    except openai.RateLimitError as e:
        raise RateLimitError(f"{provider.name}: {e}") from e
    except Exception as e:
        raise ProviderError(f"{provider.name}: {e}") from e

    if diff_mode and target_exists:
        diff = extract_diff_block(text)
        if diff and apply_patch(diff, target):
            print(f"[{provider.name}] Patch applied to {target}", file=sys.stderr)
            return text, diff
        print(f"\n[{provider.name}] WARNING: diff failed — falling back to full rewrite.", file=sys.stderr)
        return _run_openai_compat(provider, workdir, task, files, diff_mode=False)

    code = extract_code_block(text)
    if not code:
        print(f"\n[{provider.name}] WARNING: no code block in response.", file=sys.stderr)
        return text, None
    target.write_text(code)
    print(f"[{provider.name}] Written to {target}", file=sys.stderr)
    return text, code


def run(
    provider: ProviderConfig,
    workdir: str,
    task: str,
    files: list[str],
    diff_mode: bool = False,
) -> tuple[str, str | None]:
    if provider.type == "ollama":
        return _run_ollama(provider, workdir, task, files, diff_mode)
    return _run_openai_compat(provider, workdir, task, files, diff_mode)
```

- [ ] **Step 2.5: Run tests — expect pass**

```bash
/opt/homebrew/bin/pytest harness/tests/test_provider_call.py -v
```

Expected: all 8 tests PASS.

Full suite:
```bash
/opt/homebrew/bin/pytest -q
```

Expected: all pass.

- [ ] **Step 2.6: Commit**

```bash
git add harness/provider_call.py harness/tests/test_provider_call.py
git commit -m "feat: add provider_call.py — unified ollama + OpenAI-compat caller"
```

---

## Task 3: rank_providers() in router.py

**Files:**
- Modify: `harness/router.py`
- Modify: `harness/tests/test_router.py`

- [ ] **Step 3.1: Write failing tests for rank_providers**

Append to `harness/tests/test_router.py`:

```python
# --- rank_providers tests ---

from harness.models import ProviderConfig


def _rp_providers():
    return {
        "gemma4":   ProviderConfig("gemma4",   "ollama",        "gemma4:latest",    "http://localhost:11434",       0.0,    "local"),
        "deepseek": ProviderConfig("deepseek", "openai_compat", "deepseek-coder",   "https://api.deepseek.com/v1", 0.0014, "cloud_cheap", "DEEPSEEK_API_KEY"),
        "gemini":   ProviderConfig("gemini",   "openai_compat", "gemini-2.0-flash", "https://generativelanguage.googleapis.com/v1beta/openai/", 0.00015, "cloud_cheap", "GEMINI_API_KEY"),
    }


def _rp_profiles():
    from harness.models import CapabilityProfile
    return {
        "gemma4":   CapabilityProfile(max_reliable_tokens=32000, accuracy_by_type={"code_edit": 0.85}),
        "deepseek": CapabilityProfile(max_reliable_tokens=32000, accuracy_by_type={"code_edit": 0.80}),
        "gemini":   CapabilityProfile(max_reliable_tokens=32000, accuracy_by_type={"code_edit": 0.82}),
    }


def _rp_task(type=TaskType.CODE_EDIT, tokens=100):
    return SubTask("t1", "add docstring", type, ["f.py"], tokens)


def test_rank_providers_free_provider_first():
    from harness.router import rank_providers
    ranked = rank_providers(_rp_task(), _rp_providers(), _rp_profiles())
    # gemma4 costs 0.0 → highest score (accuracy/cost+eps) → ranked first
    assert ranked[0] == "gemma4"
    assert ranked[-1] == "claude_agent"


def test_rank_providers_claude_always_last():
    from harness.router import rank_providers
    ranked = rank_providers(_rp_task(), _rp_providers(), _rp_profiles())
    assert ranked[-1] == "claude_agent"


def test_rank_providers_skips_busy_provider():
    from harness.router import rank_providers
    ranked = rank_providers(_rp_task(), _rp_providers(), _rp_profiles(), busy_providers={"gemma4"})
    assert "gemma4" not in ranked[:-1]
    assert ranked[-1] == "claude_agent"


def test_rank_providers_always_claude_for_research():
    from harness.router import rank_providers
    ranked = rank_providers(_rp_task(type=TaskType.RESEARCH), _rp_providers(), _rp_profiles())
    assert ranked == ["claude_agent"]


def test_rank_providers_always_claude_for_cross_file_refactor():
    from harness.router import rank_providers
    ranked = rank_providers(_rp_task(type=TaskType.CROSS_FILE_REFACTOR), _rp_providers(), _rp_profiles())
    assert ranked == ["claude_agent"]


def test_rank_providers_skips_low_accuracy():
    from harness.router import rank_providers
    from harness.models import CapabilityProfile
    profiles = {
        "gemma4": CapabilityProfile(max_reliable_tokens=32000, accuracy_by_type={"code_edit": 0.50}),
    }
    ranked = rank_providers(_rp_task(), {"gemma4": _rp_providers()["gemma4"]}, profiles)
    assert ranked == ["claude_agent"]


def test_rank_providers_skips_oversized_tasks():
    from harness.router import rank_providers
    from harness.models import CapabilityProfile
    profiles = {
        "gemma4": CapabilityProfile(max_reliable_tokens=500, accuracy_by_type={"code_edit": 0.85}),
    }
    ranked = rank_providers(_rp_task(tokens=10000), {"gemma4": _rp_providers()["gemma4"]}, profiles)
    assert ranked == ["claude_agent"]


def test_rank_providers_prefers_cheaper_at_equal_accuracy():
    from harness.router import rank_providers
    from harness.models import CapabilityProfile
    # gemini cheaper than deepseek, equal accuracy
    profiles = {
        "deepseek": CapabilityProfile(max_reliable_tokens=32000, accuracy_by_type={"code_edit": 0.80}),
        "gemini":   CapabilityProfile(max_reliable_tokens=32000, accuracy_by_type={"code_edit": 0.80}),
    }
    providers = {k: _rp_providers()[k] for k in ("deepseek", "gemini")}
    ranked = rank_providers(_rp_task(), providers, profiles)
    assert ranked[0] == "gemini"  # cheaper: 0.00015 vs 0.0014
```

- [ ] **Step 3.2: Run tests — expect failures**

```bash
/opt/homebrew/bin/pytest harness/tests/test_router.py -v -k "rank_providers"
```

Expected: ImportError — `rank_providers` not defined yet.

- [ ] **Step 3.3: Add rank_providers to router.py**

Append to `harness/router.py` after the existing `route()` function (before `if __name__ == "__main__"`):

```python
def rank_providers(
    subtask: SubTask,
    providers: dict,
    profiles: dict[str, CapabilityProfile],
    busy_providers: set[str] | None = None,
) -> list[str]:
    """
    Return provider names ordered by cost-normalised accuracy.
    claude_agent is always appended last as the final fallback.
    Skips providers that are busy, over token limit, below accuracy threshold,
    or at session failure budget.
    """
    busy = busy_providers or set()

    if subtask.type in _ALWAYS_CLAUDE:
        return ["claude_agent"]

    candidates = []
    for name, config in providers.items():
        if name == "claude_agent":
            continue
        if name in busy:
            continue
        profile = profiles.get(name)
        if profile is None:
            continue
        if subtask.estimated_tokens > profile.max_reliable_tokens:
            continue
        if profile.session_failures >= profile.retry_budget:
            continue
        accuracy = profile.accuracy_by_type.get(subtask.type.value, 0.7)
        if accuracy < 0.70:
            continue
        score = accuracy / (config.cost_per_1k_tokens + 0.0001)
        candidates.append((name, score))

    ranked = [name for name, _ in sorted(candidates, key=lambda x: -x[1])]
    return ranked + ["claude_agent"]
```

- [ ] **Step 3.4: Run tests — expect pass**

```bash
/opt/homebrew/bin/pytest harness/tests/test_router.py -v
```

Expected: all PASS (existing + new rank_providers tests).

Full suite:
```bash
/opt/homebrew/bin/pytest -q
```

Expected: all pass.

- [ ] **Step 3.5: Commit**

```bash
git add harness/router.py harness/tests/test_router.py
git commit -m "feat: add rank_providers() — cost-normalised accuracy ranking across all providers"
```

---

## Task 4: orchestrate.py

**Files:**
- Create: `harness/orchestrate.py`
- Create: `harness/tests/test_orchestrate.py`

- [ ] **Step 4.1: Write failing tests**

Create `harness/tests/test_orchestrate.py`:

```python
import threading
from unittest.mock import MagicMock, patch

import pytest

from harness.models import (
    AgentType, CapabilityProfile, EvalResult, ProviderConfig, SubTask, TaskType,
)


def _subtask(tokens=100):
    return SubTask("t1", "add docstring", TaskType.CODE_EDIT, ["f.py"], tokens)


def _providers():
    return {
        "deepseek": ProviderConfig("deepseek", "openai_compat", "deepseek-coder",
                                   "https://api.deepseek.com/v1", 0.001, "cloud_cheap", "KEY"),
        "gemini":   ProviderConfig("gemini",   "openai_compat", "gemini-2.0-flash",
                                   "https://api.gemini.com/v1", 0.0001, "cloud_cheap", "KEY2"),
    }


def _profiles():
    return {
        "deepseek": CapabilityProfile(32000, {"code_edit": 0.85}),
        "gemini":   CapabilityProfile(32000, {"code_edit": 0.85}),
    }


def _good_eval(subtask, agent, changed, output):
    return EvalResult(subtask.id, agent, 80, 25, 35, 20, 0, "ok", changed)


def _bad_eval(subtask, agent, changed, output):
    return EvalResult(subtask.id, agent, 30, 0, 0, 0, 30, "fail", changed)


def test_orchestrate_returns_result_on_first_provider_success(tmp_path):
    from harness.orchestrate import orchestrate
    (tmp_path / "f.py").write_text("x=1")
    with patch("harness.orchestrate.provider_run", return_value=("resp", "code")) as mock_run, \
         patch("harness.orchestrate.evaluate", side_effect=_good_eval), \
         patch("harness.orchestrate.save_profiles"), \
         patch("harness.orchestrate.update_score"), \
         patch("harness.orchestrate.log_delegation"):
        result = orchestrate(_subtask(), str(tmp_path), _providers(), _profiles())
    assert result.score == 80
    assert mock_run.call_count == 1


def test_orchestrate_falls_back_on_rate_limit(tmp_path):
    from harness.orchestrate import orchestrate
    from harness.provider_call import RateLimitError
    (tmp_path / "f.py").write_text("x=1")
    call_count = {"n": 0}

    def fake_run(provider, *a, **kw):
        call_count["n"] += 1
        if provider.name == "deepseek":
            raise RateLimitError("rate limited")
        return "resp", "code"

    with patch("harness.orchestrate.provider_run", side_effect=fake_run), \
         patch("harness.orchestrate.evaluate", side_effect=_good_eval), \
         patch("harness.orchestrate.save_profiles"), \
         patch("harness.orchestrate.update_score"), \
         patch("harness.orchestrate.log_delegation"):
        result = orchestrate(_subtask(), str(tmp_path), _providers(), _profiles())

    assert call_count["n"] == 2  # deepseek failed, gemini succeeded
    assert result.score == 80


def test_orchestrate_falls_back_on_provider_error(tmp_path):
    from harness.orchestrate import orchestrate
    from harness.provider_call import ProviderError
    (tmp_path / "f.py").write_text("x=1")

    def fake_run(provider, *a, **kw):
        if provider.name == "deepseek":
            raise ProviderError("timeout")
        return "resp", "code"

    with patch("harness.orchestrate.provider_run", side_effect=fake_run), \
         patch("harness.orchestrate.evaluate", side_effect=_good_eval), \
         patch("harness.orchestrate.save_profiles"), \
         patch("harness.orchestrate.update_score"), \
         patch("harness.orchestrate.log_delegation"):
        result = orchestrate(_subtask(), str(tmp_path), _providers(), _profiles())
    assert result.score == 80


def test_orchestrate_escalates_when_all_providers_fail(tmp_path):
    from harness.orchestrate import orchestrate, EscalateToClaudeError
    from harness.provider_call import ProviderError
    (tmp_path / "f.py").write_text("x=1")
    with patch("harness.orchestrate.provider_run", side_effect=ProviderError("boom")):
        with pytest.raises(EscalateToClaudeError):
            orchestrate(_subtask(), str(tmp_path), _providers(), _profiles())


def test_orchestrate_tries_next_provider_on_soft_failure(tmp_path):
    from harness.orchestrate import orchestrate
    (tmp_path / "f.py").write_text("x=1")
    eval_calls = {"n": 0}

    def fake_eval(subtask, agent, changed, output):
        eval_calls["n"] += 1
        if agent == "deepseek":
            return EvalResult(subtask.id, agent, 30, 0, 0, 0, 30, "fail", changed)
        return EvalResult(subtask.id, agent, 85, 25, 35, 25, 0, "ok", changed)

    def fake_heal(subtask, result, profiles, workdir, delegate_fn=None, evaluate_fn=None):
        return None, "C"  # force escalation from healer → next provider

    with patch("harness.orchestrate.provider_run", return_value=("resp", "code")), \
         patch("harness.orchestrate.evaluate", side_effect=fake_eval), \
         patch("harness.orchestrate.auto_heal", side_effect=fake_heal), \
         patch("harness.orchestrate.save_profiles"), \
         patch("harness.orchestrate.update_score"), \
         patch("harness.orchestrate.log_delegation"):
        result = orchestrate(_subtask(), str(tmp_path), _providers(), _profiles())

    assert result.score == 85
    assert result.agent == "gemini"


def test_orchestrate_parallel_distributes_across_providers(tmp_path):
    from harness.orchestrate import orchestrate_parallel
    (tmp_path / "f1.py").write_text("x=1")
    (tmp_path / "f2.py").write_text("y=2")

    subtasks = [
        SubTask("t1", "task1", TaskType.CODE_EDIT, ["f1.py"], 100),
        SubTask("t2", "task2", TaskType.CODE_EDIT, ["f2.py"], 100),
    ]

    used_providers = []

    def fake_run(provider, *a, **kw):
        used_providers.append(provider.name)
        return "resp", "code"

    with patch("harness.orchestrate.provider_run", side_effect=fake_run), \
         patch("harness.orchestrate.evaluate", side_effect=_good_eval), \
         patch("harness.orchestrate.save_profiles"), \
         patch("harness.orchestrate.update_score"), \
         patch("harness.orchestrate.log_delegation"):
        results = orchestrate_parallel(subtasks, str(tmp_path), _providers(), _profiles())

    assert len(results) == 2
    assert all(r.score == 80 for r in results)
```

- [ ] **Step 4.2: Run tests — expect failures**

```bash
/opt/homebrew/bin/pytest harness/tests/test_orchestrate.py -v
```

Expected: ImportError — `harness.orchestrate` doesn't exist.

- [ ] **Step 4.3: Create harness/orchestrate.py**

```python
"""
orchestrate.py — multi-provider orchestrator.

Single task:
    from harness.orchestrate import orchestrate, EscalateToClaudeError
    result = orchestrate(subtask, workdir="/path")  # raises EscalateToClaudeError if all fail

Parallel tasks (shared provider busy pool):
    results = orchestrate_parallel(subtasks, workdir="/path")
    # list of EvalResult; EscalateToClaudeError instances mark escalations
"""
from __future__ import annotations

import concurrent.futures
import os
import threading
from pathlib import Path

from harness.evaluator import evaluate
from harness.healer import auto_heal
from harness.models import EvalResult, SubTask
from harness.profiles import load_profiles, save_profiles, update_accuracy
from harness.provider_call import ProviderError, RateLimitError, run as provider_run
from harness.providers import load_providers
from harness.router import rank_providers
from harness.session_stats import log_delegation, update_score
from harness.tokens import estimate_tokens

_SESSION_ID = os.environ.get("CONDUCTOR_SESSION_ID", "default")


class EscalateToClaudeError(Exception):
    def __init__(self, subtask: SubTask) -> None:
        self.subtask = subtask
        super().__init__(f"All providers exhausted for subtask {subtask.id!r}")


def _record(subtask: SubTask, provider_name: str, result: EvalResult, profiles: dict) -> None:
    update_accuracy(profiles, provider_name, subtask.type.value, result.score)
    save_profiles(profiles)
    update_score(result.subtask_id, result.score)
    log_delegation(
        session_id=_SESSION_ID,
        task_id=result.subtask_id,
        task_type=subtask.type.value,
        agent=provider_name,
        estimated_tokens=subtask.estimated_tokens,
        score=result.score,
    )


def orchestrate(
    subtask: SubTask,
    workdir: str = ".",
    providers: dict | None = None,
    profiles: dict | None = None,
    diff_mode: bool = False,
    _busy: set | None = None,
    _busy_lock: threading.Lock | None = None,
) -> EvalResult:
    """
    Try ranked providers in order until one scores >= 70.
    Falls back on RateLimitError, ProviderError, or healer strategy C.
    Raises EscalateToClaudeError when all non-Claude providers are exhausted.
    Updates provider profiles after every task (incremental scoring).
    """
    if providers is None:
        providers = load_providers()
    if profiles is None:
        profiles = load_profiles()
    if not subtask.estimated_tokens:
        subtask.estimated_tokens = estimate_tokens(subtask.files, workdir)

    busy = _busy if _busy is not None else set()
    lock = _busy_lock or threading.Lock()

    with lock:
        ranked = rank_providers(subtask, providers, profiles, busy)

    for provider_name in ranked:
        if provider_name == "claude_agent":
            raise EscalateToClaudeError(subtask)

        with lock:
            busy.add(provider_name)

        try:
            response, code = provider_run(
                providers[provider_name], workdir, subtask.description, subtask.files,
                diff_mode=diff_mode,
            )
        except (RateLimitError, ProviderError):
            continue
        finally:
            with lock:
                busy.discard(provider_name)

        if code is None:
            continue

        changed = [str(Path(workdir) / f) for f in subtask.files]
        result = evaluate(subtask, provider_name, changed, response)
        _record(subtask, provider_name, result, profiles)

        if result.score >= 70:
            return result

        healed, strategy = auto_heal(
            subtask, result, profiles, workdir,
            delegate_fn=lambda w, t, f, _pn=provider_name: provider_run(
                providers[_pn], w, t, f, diff_mode=diff_mode
            ),
            evaluate_fn=evaluate,
        )
        if strategy != "C" and healed is not None:
            _record(subtask, provider_name, healed, profiles)
            return healed

    raise EscalateToClaudeError(subtask)


def orchestrate_parallel(
    subtasks: list[SubTask],
    workdir: str = ".",
    providers: dict | None = None,
    profiles: dict | None = None,
    diff_mode: bool = False,
    max_wait_seconds: int = 30,
) -> list[EvalResult | EscalateToClaudeError]:
    """
    Dispatch multiple subtasks concurrently, sharing the provider busy pool.
    Returns results in input order.
    Items that raise EscalateToClaudeError are returned as exception instances.
    """
    if providers is None:
        providers = load_providers()
    if profiles is None:
        profiles = load_profiles()

    busy: set[str] = set()
    lock = threading.Lock()

    def _run_one(st: SubTask) -> EvalResult | EscalateToClaudeError:
        try:
            return orchestrate(st, workdir, providers, profiles, diff_mode,
                               _busy=busy, _busy_lock=lock)
        except EscalateToClaudeError as e:
            return e

    max_workers = max(len(providers), 1)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_run_one, st) for st in subtasks]
        return [f.result(timeout=max_wait_seconds) for f in futures]
```

- [ ] **Step 4.4: Run tests — expect pass**

```bash
/opt/homebrew/bin/pytest harness/tests/test_orchestrate.py -v
```

Expected: all PASS.

Full suite:
```bash
/opt/homebrew/bin/pytest -q
```

Expected: all pass.

- [ ] **Step 4.5: Commit**

```bash
git add harness/orchestrate.py harness/tests/test_orchestrate.py
git commit -m "feat: add orchestrate.py — multi-provider fallback loop with incremental scoring"
```

---

## Task 5: Update pipeline.py to use orchestrate()

**Files:**
- Modify: `harness/pipeline.py`

- [ ] **Step 5.1: Run existing pipeline tests to establish baseline**

```bash
/opt/homebrew/bin/pytest -q -k "pipeline" 2>/dev/null || echo "no pipeline tests"
/opt/homebrew/bin/pytest -q
```

Note the current pass count.

- [ ] **Step 5.2: Replace pipeline.py internals**

Replace the entire `run_pipeline` function body and imports in `harness/pipeline.py`.

Replace the import block (lines 25–37) with:

```python
from __future__ import annotations

import os
from dataclasses import dataclass

from harness.models import EvalResult, SubTask
from harness.orchestrate import EscalateToClaudeError, orchestrate
from harness.tokens import estimate_tokens
```

Replace the `run_pipeline` function (lines 50–116) with:

```python
def run_pipeline(
    subtask: SubTask,
    workdir: str = ".",
    diff_mode: bool = False,
    auto_heal: bool = True,   # kept for API compat; orchestrate always heals internally
) -> PipelineResult:
    """
    Full pipeline for a single subtask via the multi-provider orchestrator.
    Returns PipelineResult. Sets routed_to_claude=True when all local providers fail.
    """
    if not subtask.estimated_tokens:
        subtask.estimated_tokens = estimate_tokens(subtask.files, workdir)

    try:
        result = orchestrate(subtask, workdir=workdir, diff_mode=diff_mode)
    except EscalateToClaudeError:
        dummy = EvalResult(
            subtask_id=subtask.id, agent="claude_agent", score=-1,
            syntax_score=0, test_score=0, scope_score=0, semantic_score=0,
            details="all providers exhausted — routed to claude_agent",
        )
        return PipelineResult(
            subtask_id=subtask.id, agent_used="claude_agent",
            final_score=-1, strategy=None, eval_result=dummy,
            routed_to_claude=True,
        )

    return PipelineResult(
        subtask_id=subtask.id, agent_used=result.agent,
        final_score=result.score, strategy=None, eval_result=result,
    )
```

Also update `PipelineResult.agent_used` type hint from `AgentType` to `str`:

```python
@dataclass
class PipelineResult:
    subtask_id: str
    agent_used: str             # was AgentType; widened to str for multi-provider support
    final_score: int
    strategy: str | None
    eval_result: EvalResult
    routed_to_claude: bool = False
```

And update the `__main__` block — replace `pr.agent_used.value` with `pr.agent_used` (already a str):

In line ~158 of pipeline.py, change:
```python
"agent_used": pr.agent_used.value,
```
to:
```python
"agent_used": pr.agent_used if isinstance(pr.agent_used, str) else pr.agent_used.value,
```

- [ ] **Step 5.3: Run full test suite**

```bash
/opt/homebrew/bin/pytest -q
```

Expected: all pass. Count should be same as baseline.

- [ ] **Step 5.4: Commit**

```bash
git add harness/pipeline.py
git commit -m "feat: wire pipeline.py to multi-provider orchestrator"
```

---

## Task 6: Update parallel_delegate.py to use provider pool

**Files:**
- Modify: `harness/parallel_delegate.py`
- Modify: `harness/tests/test_parallel_delegate.py`

- [ ] **Step 6.1: Run existing parallel_delegate tests to establish baseline**

```bash
/opt/homebrew/bin/pytest harness/tests/test_parallel_delegate.py -v
```

Note which tests pass.

- [ ] **Step 6.2: Rewrite parallel_delegate.py**

Replace the entire file content of `harness/parallel_delegate.py`:

```python
"""
parallel_delegate.py — dispatch multiple independent tasks concurrently across all providers.

Tasks are distributed across the provider pool (each provider handles one task at a time).
Fallback and healing happen inside orchestrate() per task.

Usage:
    from harness.parallel_delegate import delegate_parallel
    from harness.models import SubTask, TaskType

    results = delegate_parallel(
        workdir="/path/to/project",
        tasks=[
            {"task": "Add docstrings to parse_order",    "file": "orders.py"},
            {"task": "Add type hints to validate_email", "file": "validators.py"},
        ],
    )
    # → [{"file": "orders.py", "success": True, "score": 85, "agent": "gemma4", ...}, ...]

    # With explicit SubTask objects (for richer routing):
    results = delegate_parallel(workdir=..., tasks=[...], subtasks=[SubTask(...), ...])
"""
from __future__ import annotations

import concurrent.futures
import threading
from pathlib import Path

from harness.models import SubTask, TaskType
from harness.orchestrate import EscalateToClaudeError, orchestrate
from harness.profiles import load_profiles
from harness.providers import load_providers


def delegate_parallel(
    workdir: str,
    tasks: list[dict],
    max_workers: int | None = None,
    diff_mode: bool = False,
    heal: bool = True,          # kept for API compat; orchestrate always heals
    subtasks: list[SubTask] | None = None,
) -> list[dict]:
    """
    Args:
        workdir:     Absolute path to project root.
        tasks:       List of {"task": str, "file": str}.
        max_workers: Max concurrent tasks. Defaults to number of available providers.
        diff_mode:   Pass diff_mode to each orchestrate() call.
        heal:        Retained for API compatibility. Orchestrate always heals internally.
        subtasks:    Optional SubTask objects in same order as tasks.
                     Auto-built from tasks if not provided.
    Returns:
        List of result dicts in input order:
        {"file", "success", "score", "agent", "output", "escalated"}
    """
    providers = load_providers()
    profiles = load_profiles()

    if subtasks is None:
        subtasks = [
            SubTask(
                id=f"parallel_{i}",
                description=t["task"],
                type=TaskType.CODE_EDIT,
                files=[t["file"]],
                estimated_tokens=0,
            )
            for i, t in enumerate(tasks)
        ]

    busy: set[str] = set()
    lock = threading.Lock()

    def _run_one(task: dict, subtask: SubTask) -> dict:
        try:
            result = orchestrate(
                subtask, workdir, providers, profiles, diff_mode,
                _busy=busy, _busy_lock=lock,
            )
            return {
                "file": task["file"],
                "success": result.score >= 70,
                "score": result.score,
                "agent": result.agent,
                "output": result.details,
                "escalated": False,
                "healer_strategy": None,
            }
        except EscalateToClaudeError:
            return {
                "file": task["file"],
                "success": False,
                "score": -1,
                "agent": "claude_agent",
                "output": "all providers exhausted — escalated to claude_agent",
                "escalated": True,
                "healer_strategy": "C",
            }
        except Exception as exc:
            return {
                "file": task["file"],
                "success": False,
                "score": -1,
                "agent": None,
                "output": str(exc),
                "escalated": False,
                "healer_strategy": None,
            }

    n_workers = max_workers if max_workers is not None else max(len(providers), 1)
    pairs = list(zip(tasks, subtasks))

    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = [executor.submit(_run_one, t, st) for t, st in pairs]
        return [f.result() for f in futures]
```

- [ ] **Step 6.3: Update parallel_delegate tests**

The existing tests call `delegate_parallel` and expect `{"file", "success", "output", "healer_strategy"}`.
The new schema adds `"score"`, `"agent"`, `"escalated"` — the old keys are all still present.

Open `harness/tests/test_parallel_delegate.py`. Find any assertions on the return dict and verify they still hold (the old keys are present). If tests mock `harness.gemma4_call.run` or `harness.parallel_delegate._gemma4_run`, update them to mock `harness.orchestrate.provider_run` or `harness.orchestrate.orchestrate` instead.

Add these new tests at the bottom of `harness/tests/test_parallel_delegate.py`:

```python
def test_delegate_parallel_returns_score_and_agent(tmp_path):
    from harness.parallel_delegate import delegate_parallel
    from harness.models import CapabilityProfile, ProviderConfig
    (tmp_path / "a.py").write_text("x=1")

    mock_result = MagicMock()
    mock_result.score = 82
    mock_result.agent = "gemini"
    mock_result.details = "ok"

    with patch("harness.parallel_delegate.orchestrate", return_value=mock_result), \
         patch("harness.parallel_delegate.load_providers", return_value={"gemini": MagicMock()}), \
         patch("harness.parallel_delegate.load_profiles", return_value={}):
        results = delegate_parallel(str(tmp_path), [{"task": "add docstring", "file": "a.py"}])

    assert results[0]["score"] == 82
    assert results[0]["agent"] == "gemini"
    assert results[0]["success"] is True


def test_delegate_parallel_marks_escalated_on_exhaustion(tmp_path):
    from harness.parallel_delegate import delegate_parallel
    from harness.orchestrate import EscalateToClaudeError
    from harness.models import SubTask, TaskType
    (tmp_path / "a.py").write_text("x=1")
    st = SubTask("t1", "task", TaskType.CODE_EDIT, ["a.py"], 100)

    with patch("harness.parallel_delegate.orchestrate", side_effect=EscalateToClaudeError(st)), \
         patch("harness.parallel_delegate.load_providers", return_value={"gemini": MagicMock()}), \
         patch("harness.parallel_delegate.load_profiles", return_value={}):
        results = delegate_parallel(str(tmp_path), [{"task": "task", "file": "a.py"}])

    assert results[0]["escalated"] is True
    assert results[0]["score"] == -1
```

Also add the import `from unittest.mock import MagicMock, patch` at the top if not already present.

- [ ] **Step 6.4: Run full test suite**

```bash
/opt/homebrew/bin/pytest -q
```

Expected: all pass. If existing parallel_delegate tests fail due to the schema change, update the assertions in those tests to match the new dict shape (add `.get("score", ...)` or update the expected dict keys).

- [ ] **Step 6.5: Commit**

```bash
git add harness/parallel_delegate.py harness/tests/test_parallel_delegate.py
git commit -m "feat: parallel_delegate uses provider pool via orchestrate() — distributes tasks across all providers"
```

---

## Task 7: capability_profiles.json + final wiring

**Files:**
- Modify: `harness/capability_profiles.json`

- [ ] **Step 7.1: Add new provider profiles**

Replace `harness/capability_profiles.json` with:

```json
{
  "gemma4": {
    "max_reliable_tokens": 32000,
    "accuracy_by_type": {
      "code_edit": 0.9,
      "code_gen": 0.9,
      "test_write": 0.9
    },
    "session_failures": 0,
    "retry_budget": 3,
    "decay_per_day": 0.98
  },
  "claude_agent": {
    "max_reliable_tokens": 180000,
    "accuracy_by_type": {
      "code_edit": 0.95,
      "code_gen": 0.92,
      "research": 0.9,
      "cross_file_refactor": 0.9,
      "test_write": 0.93
    },
    "session_failures": 0,
    "retry_budget": 10,
    "decay_per_day": 0.98
  },
  "deepseek": {
    "max_reliable_tokens": 32000,
    "accuracy_by_type": {
      "code_edit": 0.7,
      "code_gen": 0.7,
      "test_write": 0.7
    },
    "session_failures": 0,
    "retry_budget": 3,
    "decay_per_day": 0.98
  },
  "nim": {
    "max_reliable_tokens": 32000,
    "accuracy_by_type": {
      "code_edit": 0.7,
      "code_gen": 0.7,
      "test_write": 0.7
    },
    "session_failures": 0,
    "retry_budget": 3,
    "decay_per_day": 0.98
  },
  "gemini": {
    "max_reliable_tokens": 128000,
    "accuracy_by_type": {
      "code_edit": 0.7,
      "code_gen": 0.7,
      "test_write": 0.7
    },
    "session_failures": 0,
    "retry_budget": 3,
    "decay_per_day": 0.98
  },
  "openrouter": {
    "max_reliable_tokens": 32000,
    "accuracy_by_type": {
      "code_edit": 0.7,
      "code_gen": 0.7,
      "test_write": 0.7
    },
    "session_failures": 0,
    "retry_budget": 3,
    "decay_per_day": 0.98
  },
  "opencode_zen": {
    "max_reliable_tokens": 32000,
    "accuracy_by_type": {
      "code_edit": 0.7,
      "code_gen": 0.7,
      "test_write": 0.7
    },
    "session_failures": 0,
    "retry_budget": 3,
    "decay_per_day": 0.98
  }
}
```

- [ ] **Step 7.2: Verify profiles load correctly**

```bash
cd /Users/ankitatiwari/Desktop/claude-playground/conductor
python3 -c "
from harness.profiles import load_profiles
p = load_profiles()
print(list(p.keys()))
"
```

Expected output:
```
['gemma4', 'claude_agent', 'deepseek', 'nim', 'gemini', 'openrouter', 'opencode_zen']
```

- [ ] **Step 7.3: Verify providers + profiles together**

```bash
python3 -c "
from harness.providers import load_providers
from harness.profiles import load_profiles
from harness.models import SubTask, TaskType
from harness.router import rank_providers

providers = load_providers()
profiles = load_profiles()
subtask = SubTask('t1', 'add docstring', TaskType.CODE_EDIT, ['f.py'], 100)
ranked = rank_providers(subtask, providers, profiles)
print('Provider ranking:', ranked)
"
```

Expected: list starting with `gemma4` (cheapest, highest initial accuracy), ending with `claude_agent`.

- [ ] **Step 7.4: Run full test suite**

```bash
/opt/homebrew/bin/pytest -q
```

Expected: all pass.

- [ ] **Step 7.5: Commit**

```bash
git add harness/capability_profiles.json
git commit -m "feat: add capability profiles for deepseek, nim, gemini, openrouter, opencode_zen (neutral 0.7 baseline)"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Provider registry (`providers.json`) — Task 1
- [x] `ProviderConfig` dataclass — Task 1
- [x] `load_providers()` — Task 1
- [x] `provider_call.py` unified caller — Task 2
- [x] `RateLimitError` / `ProviderError` exceptions — Task 2
- [x] Ollama adapter — Task 2
- [x] OpenAI-compat adapter — Task 2
- [x] `rank_providers()` cost-normalised ranking — Task 3
- [x] `orchestrate()` fallback loop — Task 4
- [x] Incremental scoring (`_record()`) — Task 4
- [x] `orchestrate_parallel()` shared busy pool — Task 4
- [x] `pipeline.py` wired to orchestrate — Task 5
- [x] `parallel_delegate.py` distributes across provider pool — Task 6
- [x] All new provider profiles — Task 7
- [x] `EvalResult.agent` widened to `str` — Task 1 (models.py)
- [x] One task per model (busy set) — Tasks 4 + 6
- [x] Rate limit reactive fallback (no cooldown) — Tasks 2 + 4

**Type consistency:** `ProviderConfig` defined Task 1, used Task 2–6. `EscalateToClaudeError` defined Task 4, used Tasks 5–6. `_record()` defined Task 4 only. `rank_providers()` defined Task 3, used Task 4. All consistent.

**No placeholders:** all steps have actual code. `opencode_zen` base URL marked with `_note` in providers.json for verification before use.
