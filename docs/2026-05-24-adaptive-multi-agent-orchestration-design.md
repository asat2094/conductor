# Adaptive Multi-Agent Orchestration with gemma4 Local Harness

**Date:** 2026-05-24  
**Status:** Approved  
**Scope:** claude-playground

---

## Overview

Claude orchestrates complex tasks by decomposing them into subtasks, routing each to the best available agent (gemma4 local via opencode, or a Claude subagent), evaluating output accuracy, and self-healing when accuracy degrades — notifying the user at each failure point.

---

## System Components

### 1. Task Decomposer (`decomposer.py`)

Breaks an incoming task into a directed acyclic graph (DAG) of typed subtasks. Each node carries:

- `type`: `code_edit | code_gen | research | cross_file_refactor | test_write`
- `scope`: list of files, max estimated token count
- `dependencies`: list of subtask IDs that must complete first
- `assigned_agent`: initially null, filled by router

Subtasks with no unresolved dependencies are eligible for parallel execution.

### 2. Agent Registry (`capability_profiles.json`)

Persistent JSON file. Updated after every run. Initial values seeded by benchmark harness.

```json
{
  "gemma4": {
    "max_reliable_tokens": 8000,
    "accuracy_by_type": {
      "code_edit": 0.85,
      "code_gen": 0.78,
      "test_write": 0.75
    },
    "session_failures": 0,
    "retry_budget": 3
  },
  "claude_agent": {
    "max_reliable_tokens": 180000,
    "accuracy_by_type": {
      "code_edit": 0.95,
      "code_gen": 0.92,
      "research": 0.90,
      "cross_file_refactor": 0.90,
      "test_write": 0.93
    },
    "session_failures": 0,
    "retry_budget": 10
  }
}
```

### 3. Router (`router.py`)

Selects agent for each subtask. Decision rules in priority order:

1. If `type` is `research` or `cross_file_refactor` → always `claude_agent`
2. If estimated token count > `gemma4.max_reliable_tokens` → `claude_agent`
3. If `gemma4.session_failures` >= `gemma4.retry_budget` → `claude_agent`
4. If `gemma4.accuracy_by_type[type]` < 0.70 → `claude_agent`
5. Otherwise → `gemma4`

### 4. Execution Layer

**gemma4 path:** Claude calls `gemma4_delegate.sh <task> [file1] [file2...]` via Bash tool.  
Script stages files into a temp dir, runs `opencode run -m ollama/gemma4 "<task>"`, captures stdout/changed files, returns to Claude.

**Claude agent path:** Claude spawns Agent tool with task description and relevant file contents.

Both paths are synchronous from Claude's perspective. Independent subtasks (no shared files, no DAG dependency) are spawned in parallel via multiple Agent/Bash calls in one message.

### 5. Evaluator (`evaluator.py`)

Scores each agent result 0–100. Four checks in order:

| Check | Method | Weight |
|-------|--------|--------|
| Syntax valid | AST parse (Python) or tsc --noEmit (TS/JS) | 25 |
| Tests pass | Run existing test suite scoped to changed files | 35 |
| Diff in scope | Changed files ⊆ requested files, no unrelated lines | 20 |
| Semantic match | Claude reads diff, scores intent alignment | 20 |

Score < 70 → healer triggered. Profile updated: `accuracy_by_type[type]` = rolling average with new score.

### 6. Healer (`healer.py`)

Triggered on score < 70. Evaluates all three strategies, presents to user before acting.

**Strategy A — Shrink:**  
Reduce subtask to half the context (split file list, reduce function scope). Retry same agent.  
*Best when:* failure looks like context overload (output truncated, ignored part of input).

**Strategy B — Re-prompt:**  
Inject failure reason + explicit constraints into task prompt. Retry same agent.  
*Best when:* output was syntactically valid but wrong intent (agent misunderstood scope).

**Strategy C — Escalate:**  
Hand subtask to `claude_agent`. Mark gemma4's `session_failures += 1`.  
*Best when:* both A and B previously failed, or failure is semantic/complex.

User notification format:
```
[ACCURACY ALERT] Subtask "<name>" scored <score>/100
  Strategy A (Shrink):   est. +<Xs> latency, same cost
  Strategy B (Re-prompt): est. +<Xs> latency, same cost  
  Strategy C (Escalate): est. +<Xs> latency, higher cost
  Recommendation: <A|B|C> because <reason>
  → Approve recommendation or pick strategy:
```

After user selects, Claude executes and re-evaluates. If re-evaluation still < 70, repeat healer up to `retry_budget` times, then surface as unresolved to user.

### 7. Orchestrator Loop (`orchestrator.py`)

```
receive task
  → decompose into subtask DAG
  → load capability_profiles.json
  → route each subtask → agent
  → spawn parallel batches (respecting DAG dependencies)
  → for each result:
      → evaluate accuracy
      → if score >= 70: update profile, mark subtask done
      → if score < 70:  run healer, await user, retry
  → when all subtasks done: present summary to user
  → save updated capability_profiles.json
```

---

## Phase 0: opencode + ollama Provider Setup

Before harness runs, opencode must be wired to gemma4 via ollama.

**`~/.config/opencode/opencode.jsonc`:**
```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "ollama": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama (local)",
      "options": { "baseURL": "http://localhost:11434/v1" },
      "models": {
        "gemma4:latest": { "name": "Gemma 4 (local)" }
      }
    }
  },
  "model": "ollama/gemma4:latest"
}
```

Install required package:
```bash
cd ~/.config/opencode && npm install @ai-sdk/openai-compatible
```

---

## Phase 1: Benchmark Harness (`gemma4-bench/bench.py`)

Runs before first real use. Populates initial `capability_profiles.json`.

Test matrix:
- Context sizes: 1k / 4k / 8k / 16k / 32k tokens (payloads from trading project files)
- Task types: `code_edit`, `code_gen`, `test_write`
- 3 trials per cell → average score

Output: `bench_results.json` + printed table. Fields written into `capability_profiles.json`:
- `max_reliable_tokens`: largest context where average score ≥ 70
- `accuracy_by_type`: average score per task type at `max_reliable_tokens`

---

## File Layout

```
claude-playground/
  harness/
    orchestrator.py
    decomposer.py
    router.py
    evaluator.py
    healer.py
    gemma4_delegate.sh
    capability_profiles.json       # seeded by bench, updated each run
  gemma4-bench/
    bench.py
    bench_results.json             # generated
  docs/superpowers/specs/
    2026-05-24-adaptive-multi-agent-orchestration-design.md
```

---

## Constraints & Guardrails

- **Parallel execution:** only spawn agents on subtasks with no shared files or unresolved DAG dependencies. Merge conflicts are a hard blocker.
- **Retry budget:** gemma4 defaults to 3 retries per session before auto-escalating all remaining tasks to Claude agent.
- **Token guard:** router always checks estimated token count against `max_reliable_tokens` before routing to gemma4. Estimation = file sizes + task prompt length.
- **No silent failures:** every agent result is evaluated. Score is always shown to user.
- **Verification is mandatory:** Claude reads every diff before declaring a subtask complete, regardless of evaluator score.
