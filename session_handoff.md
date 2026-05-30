# Conductor — Session Handoff

**Date:** 2026-05-30  
**Repo:** https://github.com/asat2094/conductor (branch: `develop`)  
**Working dir:** `/Users/ankitatiwari/Desktop/claude-playground/conductor`  
**Tests:** 97 passing  
**Last commit:** `ba0cd26 feat: per-model rate-limit cooldown tracker + openrouter_poolside`

---

## What this is

Local multi-agent harness. Claude Code (or OpenCode) orchestrates; free local/cloud models execute mechanical coding tasks. Saves Claude API tokens + context on bounded work.

```
Orchestrator (Claude Code / OpenCode)
  ├─ orchestrate_parallel(subtasks) ─────────────────────────────────┐
  │                                                                   ▼
  │   rank_providers() → [gemma4, nim, gemini, openrouter, openrouter_poolside,
  │                        opencode_deepseek, opencode_mimo, ... claude_agent]
  │
  ├─ gemma4              ollama local, 0 cost, 32k ctx
  ├─ nim                 meta/llama-3.1-8b-instruct, free 40RPM
  ├─ gemini              gemini-2.5-flash, free 1500/day
  ├─ openrouter          qwen/qwen3-coder:free, 1M ctx, best free coding model
  ├─ openrouter_poolside poolside/laguna-m.1:free, coding agent, 262k ctx
  ├─ opencode_deepseek   deepseek-v4-flash-free via opencode.ai/zen
  ├─ opencode_mimo       mimo-v2.5-free (Xiaomi) via opencode.ai/zen
  └─ claude_agent        last fallback (escalate to orchestrator)
```

**All providers free.** Routing is cost-normalised accuracy. Fallback is reactive (429 → per-model cooldown tracker → next provider).

---

## Using Claude Code or OpenCode as orchestrator

### Claude Code

Set env vars, then call from any project:

```bash
export NIM_API_KEY=nvapi-X7jqSwP_...
export GEMINI_API_KEY=AIzaSyCSIcQK...
export OPENROUTER_API_KEY=sk-or-v1-3642f...
export OPENCODE_API_KEY=sk-iJcLU5vr...

# Single task — orchestrator picks best available provider
python3 -m harness.pipeline '{
  "id": "t1",
  "description": "Add type hints to validate_order in orders.py",
  "type": "code_edit",
  "files": ["orders.py"]
}' --workdir /your/project

# Parallel dispatch — all subtasks fly concurrently across provider pool
python3 -c "
from harness.orchestrate import orchestrate_parallel
from harness.models import SubTask, TaskType

results = orchestrate_parallel([
    SubTask('t1', 'Add docstrings to parse_order', TaskType.CODE_EDIT, ['orders.py'], 0),
    SubTask('t2', 'Add type hints to validate_email', TaskType.CODE_EDIT, ['validators.py'], 0),
    SubTask('t3', 'Write tests for calculate_discount', TaskType.TEST_WRITE, ['discount.py'], 0),
], workdir='/your/project')

for r in results:
    print(r.agent, r.score, r.details)
"
```

In `~/.claude/CLAUDE.md` (global) the harness is already configured:

```bash
# Route check
python3 -m harness.router '{"id":"t1","description":"<task>","type":"code_edit","files":["<path>"]}'

# Full pipeline
python3 -m harness.pipeline '{"id":"t1",...}' --workdir <abs-workdir>
```

### OpenCode

```json
// ~/.config/opencode/config.json
{
  "agents": {
    "conductor": {
      "command": "python3 /Users/ankitatiwari/Desktop/claude-playground/conductor/harness/pipeline.py",
      "description": "Routes mechanical coding tasks to free local/cloud models"
    }
  }
}
```

Then: `/conductor {"id":"t1","description":"...","type":"code_edit","files":["..."]}`

---

## Architecture overview

### Core flow

```
orchestrate(subtask, workdir)
  │
  ├─ rank_providers()         cost × accuracy ranking; skips busy + rate-limited + low-accuracy
  │
  ├─ for provider in ranked:
  │    ├─ _is_rate_limited()  skip if in cooldown window
  │    ├─ provider_call.run() ollama or OpenAI-compat HTTP call
  │    │   └─ 429 → _set_rate_limit(provider, retry_after)  per-model cooldown
  │    ├─ evaluate()          syntax(25) + tests(35) + scope(20) + semantic(20)
  │    ├─ _record()           update_accuracy() + save_profiles() + log_delegation()
  │    ├─ score ≥ 70 → return ✓
  │    └─ score < 70 → auto_heal(A→B) → score ≥ 70 → return ✓ / else next provider
  │
  └─ all exhausted → EscalateToClaudeError
```

### parallel dispatch

```
orchestrate_parallel(subtasks)
  shared: busy: set[str], lock: threading.Lock
  ThreadPoolExecutor(max_workers=len(providers))
  each subtask → orchestrate(..., _busy=busy, _busy_lock=lock)
  one task per model at a time; rate-limited providers skipped, tried again next task
```

---

## Provider registry (`harness/providers.json`)

| Name | Model | Base URL | Key env |
|---|---|---|---|
| gemma4 | gemma4:latest | localhost:11434 | — |
| deepseek | deepseek-v4-flash | api.deepseek.com | DEEPSEEK_API_KEY |
| nim | meta/llama-3.1-8b-instruct | integrate.api.nvidia.com | NIM_API_KEY |
| gemini | gemini-2.5-flash | generativelanguage.googleapis.com | GEMINI_API_KEY |
| openrouter | qwen/qwen3-coder:free | openrouter.ai | OPENROUTER_API_KEY |
| openrouter_poolside | poolside/laguna-m.1:free | openrouter.ai | OPENROUTER_API_KEY |
| opencode_deepseek | deepseek-v4-flash-free | opencode.ai/zen/v1 | OPENCODE_API_KEY |
| opencode_mimo | mimo-v2.5-free | opencode.ai/zen/v1 | OPENCODE_API_KEY |

Free-tier notes:
- NIM: 40 RPM, no credit card
- Gemini: 1500 req/day, 15 RPM; gemini-2.5-flash-lite = 30 RPM
- OpenRouter: `:free` models ~20 RPM, 200/day; qwen3-coder can be rate-limited upstream
- OpenCode Zen: deepseek-v4-flash-free is a reasoning model (needs generous token budget)

---

## Routing rules (`rank_providers`)

```python
# Always Claude
if subtask.type in {RESEARCH, CROSS_FILE_REFACTOR}: return ["claude_agent"]

# Per provider, score = accuracy / (cost_per_1k + 0.0001)
# Skip if: busy | in rate-limit cooldown | no profile | tokens > max_reliable | failures >= budget | accuracy < 0.70
# Result: [p1, p2, ..., "claude_agent"]   — claude always last
```

`route()` (legacy binary function) still exists for backward compat.

---

## Evaluator scoring

| Check | Max | Method |
|---|---|---|
| Syntax | 25 | `ast.parse()` on .py files |
| Tests | 35 | run pytest if test file exists; 20 partial if no tests |
| Scope | 20 | `_basenames(changed) - _basenames(requested)` |
| Semantic | 20 | word overlap description↔output (or file content if output < 30 words) |

Score ≥ 70 = accept. Score < 70 = healer fires.

---

## Healer strategies

| Strategy | Action |
|---|---|
| A — Shrink | Halve files list, halve token estimate, retry same provider |
| B — Re-prompt | Inject failure detail as constraint, retry same provider |
| C — Escalate | Try next provider in ranked list |

`auto_heal()` tries A then B automatically. If both fail → strategy C → orchestrate loop tries next provider.

---

## Per-model rate limit tracker

Added in `orchestrate.py`:

```python
_rate_limit_until: dict[str, float] = {}   # provider → earliest retry timestamp

# On RateLimitError: parse retry_after from error message, set cooldown
_set_rate_limit(provider_name, error_msg, default_secs=60)

# In rank loop: skip if in cooldown
_is_rate_limited(provider_name) -> bool
```

Cooldown is in-memory per session. Cleared on process restart.

---

## Key files

| File | Role |
|---|---|
| `harness/orchestrate.py` | `orchestrate()`, `orchestrate_parallel()`, `EscalateToClaudeError`, rate-limit tracker |
| `harness/pipeline.py` | `run_pipeline()` → orchestrate; CLI `python3 -m harness.pipeline` |
| `harness/provider_call.py` | Unified caller: ollama adapter + OpenAI-compat adapter; `RateLimitError`, `ProviderError` |
| `harness/providers.py` | `load_providers()` — parses providers.json |
| `harness/providers.json` | Provider registry: model, base_url, cost, tier, api_key_env |
| `harness/router.py` | `rank_providers()` (multi-provider) + legacy `route()` (gemma4/claude binary) |
| `harness/models.py` | `SubTask`, `EvalResult` (agent: str), `CapabilityProfile`, `ProviderConfig` |
| `harness/evaluator.py` | 4-axis scoring; `--auto-heal` CLI flag |
| `harness/healer.py` | `auto_heal(A→B→C)`; uses `result.agent` not hardcoded GEMMA4 |
| `harness/parallel_delegate.py` | `delegate_parallel()` using shared orchestrate provider pool |
| `harness/profiles.py` | `load_profiles()` + cross-session decay + `update_accuracy()` |
| `harness/capability_profiles.json` | Live accuracy profiles for all 9 providers |
| `harness/tokens.py` | `estimate_tokens()` — chars/4 × per-extension multiplier |
| `harness/session_stats.py` | SQLite delegation log |
| `harness/gemma4_call.py` | Direct ollama caller (still used by legacy paths) |

---

## Token estimation multipliers

| Ext | Multiplier |
|---|---|
| .json | 1.4× |
| .yaml/.yml | 1.2× |
| .html | 1.3× |
| .sql/.css | 1.1× |
| .py/.js/.ts/.sh | 1.0× |
| .md/.txt | 0.8× |

---

## Test suite

97 tests, all passing. Run: `/opt/homebrew/bin/pytest -q`

Key test files:
- `test_providers.py` — load_providers, ProviderConfig, _note stripping
- `test_provider_call.py` — ollama/openai adapters, RateLimitError, ProviderError
- `test_orchestrate.py` — fallback loop, rate-limit, escalation, parallel (autouse fixture clears `_rate_limit_until`)
- `test_router.py` — rank_providers (8 cases) + legacy route (5 cases)
- `test_parallel_delegate.py` — provider pool distribution, escalation

---

## Day-to-day commands

```bash
# Start ollama (required for gemma4)
ollama serve &

# Set cloud keys
export NIM_API_KEY=nvapi-...
export GEMINI_API_KEY=AIza...
export OPENROUTER_API_KEY=sk-or-v1-...
export OPENCODE_API_KEY=sk-i...
export CONDUCTOR_SESSION_ID="$(date +%Y%m%d-%H%M%S)"

# Single task
python3 -m harness.pipeline '{"id":"t1","description":"<task>","type":"code_edit","files":["<file>"]}' \
  --workdir /abs/workdir

# Parallel (Python)
python3 -c "
from harness.orchestrate import orchestrate_parallel
from harness.models import SubTask, TaskType
results = orchestrate_parallel([SubTask('t1','<task>',TaskType.CODE_EDIT,['file.py'],0)], workdir='/abs')
print(results[0].agent, results[0].score)
"

# Stats
bash harness/stats.sh

# Tests
/opt/homebrew/bin/pytest -q
```

---

## System

- **Machine:** Apple M3 Pro, 18 GB RAM
- **Ollama:** localhost:11434, gemma4:latest (9.6 GB) + gemma4:e4b
- **Python:** 3.14.5 (`python3`)
- **pytest:** `/opt/homebrew/bin/pytest`
- **openai SDK:** installed (pip)

---

## What's done

| Phase | Items |
|---|---|
| 1 | Parallel delegation, diff mode, auto token counting, healer auto-apply, cross-session decay |
| 2 | Pipeline.py, parallel_cli.py, diff_mode propagation, bench merge via rolling avg |
| 3 | Multi-provider harness: provider_call, orchestrate, rank_providers, providers.json, 8 free providers |
| 4 | E2E tested, per-model rate-limit cooldown, OpenCode Zen integration, correct free model IDs |

## Remaining / known issues

- `session_stats.py` reporting only counts `gemma4` rows — needs update for multi-provider
- `--no-heal` CLI flag in pipeline is no-op (orchestrate always heals internally)
- `qwen/qwen3-coder:free` on OpenRouter is heavily rate-limited at peak; `openrouter_poolside` (laguna-m.1) is the reliable fallback
- `minimax-m2.5-free` Zen promo ended; replaced by `mimo-v2.5-free` (Xiaomi MiMo)
- `deepseek` direct key has no balance; works via `opencode_deepseek` (Zen) instead
- OpenCode Zen models are reasoning models — need generous token budget (no explicit max_tokens cap in provider_call.py, uses model default)
