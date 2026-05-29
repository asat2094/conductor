# Multi-Provider Harness Design

**Date:** 2026-05-29  
**Status:** Approved  
**Scope:** Extend conductor to support NVIDIA NIM, Gemini, DeepSeek, OpenRouter, OpenCode Zen alongside gemma4. Single orchestrator entry point with metric-based routing, seamless fallback, incremental scoring, and one-task-per-model dispatch.

---

## Goal

Replace the binary gemma4/claude routing with a ranked multi-provider system that:
- Minimises cost without compromising quality
- Automatically learns which provider is best for each task type
- Falls back seamlessly on failure or rate limit
- Handles parallel tasks by distributing across free providers

---

## Architecture

```
orchestrate(subtask, workdir) → EvalResult
        │
        ▼
rank_providers()   reads profiles + busy state → ordered list
        │
        ▼
provider_call.run()   unified OpenAI-compat caller + ollama adapter
        │
        ├── RateLimitError → next provider (same context)
        ├── hard failure   → next provider
        └── soft failure (score < 70) → healer A→B → next provider if still < 70
        │
        ▼
evaluator.evaluate() → EvalResult
        │
        ▼
profiles.update_accuracy()  rolling avg, persisted immediately
session_stats.log_delegation()  raw log
```

**New files:** `provider_call.py`, `orchestrate.py`, `providers.json`  
**Modified:** `router.py`, `models.py`, `capability_profiles.json`, `pipeline.py`, `parallel_delegate.py`  
**Unchanged:** `evaluator.py`, `healer.py`, `session_stats.py`, `tokens.py`, `profiles.py`

---

## Provider Registry (`providers.json`)

One entry per provider. Config shape:

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
    "_note": "base_url needs verification from opencode.ai/zen docs before use"
  }
}
```

All cloud providers use the OpenAI-compatible path. Adding a new provider = one JSON entry + set env var.

---

## Provider Call Layer (`provider_call.py`)

```python
class RateLimitError(Exception): pass
class ProviderError(Exception): pass

def run(provider: ProviderConfig, workdir, task, files, diff_mode=False) -> tuple[str, str|None]:
    if provider.type == "ollama":
        return _run_ollama(provider, workdir, task, files, diff_mode)
    return _run_openai_compat(provider, workdir, task, files, diff_mode)
```

- `_run_openai_compat`: builds prompt (same format as gemma4_call), calls via `openai` SDK with `base_url` + `api_key` overrides, extracts code block or diff
- `_run_ollama`: delegates to existing `gemma4_call.run()` logic
- HTTP 429 → raises `RateLimitError`
- Other HTTP errors / timeouts → raises `ProviderError`
- Returns same `(response, code|None)` tuple as current gemma4_call

---

## Provider State (One Task Per Model)

Each provider is `FREE` or `BUSY`. Tracked in a thread-safe dict in `orchestrate.py`.

```
FREE → [task assigned] → BUSY → [task complete/failed] → FREE
```

No cooldown. Rate limits are reactive: `RateLimitError` → fall to next provider.

---

## Router (`router.py`)

Extends current `route()` to `rank_providers()`:

```python
def rank_providers(subtask, providers, profiles, busy_providers) -> list[str]:
    if subtask.type in _ALWAYS_CLAUDE:
        return ["claude_agent"]

    candidates = []
    for name, config in providers.items():
        if name == "claude_agent": continue
        if name in busy_providers: continue
        profile = profiles.get(name)
        if profile is None: continue
        accuracy = profile.accuracy_by_type.get(subtask.type.value, 0.7)
        if accuracy < 0.70: continue
        # higher accuracy and lower cost = higher score
        score = accuracy / (config.cost_per_1k_tokens + 0.0001)
        candidates.append((name, score))

    ranked = [name for name, _ in sorted(candidates, key=lambda x: -x[1])]
    return ranked + ["claude_agent"]
```

`claude_agent` always last. If all providers fail, escalate to Claude.

---

## Orchestrator (`orchestrate.py`)

```python
def orchestrate(subtask, workdir, providers, profiles) -> EvalResult:
    busy = set()
    ranked = rank_providers(subtask, providers, profiles, busy)

    for provider_name in ranked:
        if provider_name == "claude_agent":
            raise EscalateToClaudeError(subtask)

        busy.add(provider_name)
        try:
            response, code = provider_call.run(providers[provider_name], workdir,
                                                subtask.description, subtask.files)
        except (RateLimitError, ProviderError):
            continue  # hard skip, full context re-used on next provider
        finally:
            busy.discard(provider_name)  # always free after call completes

        if code is None:
            continue

        changed = [str(Path(workdir) / f) for f in subtask.files]
        result = evaluate(subtask, AgentType(provider_name), changed, response)
        _record(subtask, provider_name, result, profiles)

        if result.score >= 70:
            return result

        # soft failure → healer
        healed, strategy = auto_heal(subtask, result, profiles, workdir,
                                     delegate_fn=_make_delegate(providers[provider_name]),
                                     evaluate_fn=evaluate)
        if strategy != "C":
            return healed
        # strategy C → try next provider

    raise OrchestratorExhausted(subtask.id)
```

`_record()` calls `update_accuracy()` + `save_profiles()` + `log_delegation()` after every task.

---

## Incremental Scoring Loop

Every completed task (pass or fail) updates the provider's profile immediately:

1. `evaluator.evaluate()` → score 0–100
2. `session_stats.log_delegation(provider, task_type, score)` — raw immutable log (SQLite)
3. `profiles.update_accuracy(provider, task_type, score)` — rolling avg: `0.7 × old + 0.3 × new`
4. `profiles.save_profiles()` — written to `capability_profiles.json`
5. Next `rank_providers()` call reads updated profiles — routing adjusts automatically

A provider scoring badly consecutively drops below 0.70 and is skipped. Recovers as scores improve.

---

## Parallel Dispatch

`parallel_delegate.py` updated to use orchestrator's provider pool:

- N tasks arrive → assign each to highest-ranked free provider
- `busy_providers` set shared across threads (protected by lock)
- If all providers busy → wait for one to free (bounded by `max_wait_seconds=30`)
- If provider fails → re-queue task, pick next free provider
- Max concurrency = number of registered non-Claude providers

---

## Models (`models.py`)

`AgentType` enum keeps existing hard-coded values (`GEMMA4`, `CLAUDE_AGENT`). New providers are identified by string name (the `providers.json` key). `EvalResult.agent` field type widens to `str` — no enum required for new providers. This avoids brittle dynamic enum extension.

New dataclass:
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

---

## Capability Profiles

`capability_profiles.json` gains one entry per provider with same shape as current gemma4 entry. Initial accuracies set to neutral (0.7) until bench or live tasks calibrate them.

`bench.py` extended: `--provider <name>` or `--all` benchmarks all registered providers using same task suite, writes results through `update_accuracy` → same store as live tasks.

---

## Error Handling

| Error | Action |
|---|---|
| `RateLimitError` (429) | Skip provider, try next with same context |
| `ProviderError` (timeout, 5xx) | Skip provider, try next |
| `code is None` (no parseable block) | Skip provider, try next |
| score < 70 after healer A→B | Skip provider, try next |
| All providers exhausted | `EscalateToClaudeError` — caller handles |

---

## New Files Summary

| File | Purpose |
|---|---|
| `harness/providers.json` | Provider registry (type, model, base_url, cost, tier) |
| `harness/provider_call.py` | Unified caller: ollama adapter + OpenAI-compat adapter |
| `harness/orchestrate.py` | Single entrypoint: rank → call → eval → heal → fallback |

---

## Out of Scope

- Streaming responses
- Provider-specific prompt tuning
- Multi-turn conversations
- Harness integrations (Hermes, OpenCode CLI as subprocess) — future phase
