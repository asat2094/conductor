# Adaptive Multi-Agent Orchestration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a harness in `conductor/` that lets Claude decompose tasks, route subtasks to gemma4 (local via opencode) or Claude subagents based on capability profiles, evaluate accuracy, and self-heal when accuracy degrades.

**Architecture:** Claude is the orchestrator — it calls standalone Python CLI tools and the delegate shell script via Bash. Each tool (router, evaluator, healer) is independently testable. Capability profiles persist to JSON and update each run. The benchmark harness seeds the initial profiles.

**Tech Stack:** Python 3.11+, pytest, opencode CLI (`ollama/gemma4:latest`), ollama REST API (`localhost:11434`), stdlib only (no heavy deps).

---

## File Map

```
conductor/
  harness/
    __init__.py              # empty
    models.py                # SubTask, EvalResult, CapabilityProfile dataclasses
    profiles.py              # load/save/update capability_profiles.json
    router.py                # subtask → agent assignment (CLI + importable)
    evaluator.py             # accuracy scoring (CLI + importable)
    healer.py                # 3-strategy repair report (CLI + importable)
    gemma4_delegate.sh       # opencode/gemma4 wrapper
    capability_profiles.json # persistent agent state (seeded by bench)
    tests/
      __init__.py
      test_models.py
      test_profiles.py
      test_router.py
      test_evaluator.py
      test_healer.py
  gemma4-bench/
    bench.py                 # benchmark harness
    bench_results.json       # generated — do not hand-edit
  docs/
    2026-05-24-adaptive-multi-agent-orchestration-design.md
    superpowers/plans/
      2026-05-24-adaptive-multi-agent-orchestration.md  ← this file
```

---

## Task 1: opencode + ollama provider wiring

**Files:**
- Modify: `~/.config/opencode/opencode.jsonc`
- Modify: `~/.config/opencode/` (npm install)

- [ ] **Step 1: Install `@ai-sdk/openai-compatible` into opencode config dir**

```bash
cd ~/.config/opencode && npm install @ai-sdk/openai-compatible
```

Expected: `added 1 package` (or similar), no errors.

- [ ] **Step 2: Read current opencode config**

```bash
cat ~/.config/opencode/opencode.jsonc
```

Expected current content:
```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "ollama/gemma4"
}
```

- [ ] **Step 3: Replace config with full provider block**

Write this to `~/.config/opencode/opencode.jsonc` (overwrite):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "ollama": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama (local)",
      "options": {
        "baseURL": "http://localhost:11434/v1"
      },
      "models": {
        "gemma4:latest": {
          "name": "Gemma 4 (local)"
        }
      }
    }
  },
  "model": "ollama/gemma4:latest"
}
```

- [ ] **Step 4: Verify ollama is running and gemma4 is available**

```bash
curl -s http://localhost:11434/api/tags | python3 -c "import json,sys; [print(m['name']) for m in json.load(sys.stdin)['models']]"
```

Expected: `gemma4:latest` in output.

- [ ] **Step 5: Smoke test opencode with gemma4**

```bash
opencode run -m ollama/gemma4:latest "Reply with exactly: HARNESS_OK"
```

Expected: output contains `HARNESS_OK` (gemma4 may add surrounding text — that's fine).

- [ ] **Step 6: Commit note** (no git repo yet — skip commit, move on)

---

## Task 2: Project bootstrap

**Files:**
- Create: `harness/__init__.py`
- Create: `harness/tests/__init__.py`
- Create: `pyproject.toml`

- [ ] **Step 1: Create empty init files**

```bash
touch /Users/ankitatiwari/Desktop/claude-playground/conductor/harness/__init__.py
touch /Users/ankitatiwari/Desktop/claude-playground/conductor/harness/tests/__init__.py
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "conductor"
version = "0.1.0"
requires-python = ">=3.11"

[tool.pytest.ini_options]
testpaths = ["harness/tests"]
```

Save to `conductor/pyproject.toml`.

- [ ] **Step 3: Verify pytest discovers tests (no tests yet — just check it runs)**

```bash
cd /Users/ankitatiwari/Desktop/claude-playground/conductor && python -m pytest --collect-only
```

Expected: `no tests ran` or empty collection — no errors.

---

## Task 3: Data models

**Files:**
- Create: `harness/models.py`
- Create: `harness/tests/test_models.py`

- [ ] **Step 1: Write failing test**

```python
# harness/tests/test_models.py
from harness.models import SubTask, TaskType, AgentType, EvalResult, CapabilityProfile

def test_subtask_defaults():
    t = SubTask(
        id="t1",
        description="fix RSI calc",
        type=TaskType.CODE_EDIT,
        files=["backend/indicators.py"],
        estimated_tokens=2000,
    )
    assert t.dependencies == []
    assert t.assigned_agent is None

def test_eval_result_total():
    r = EvalResult(
        subtask_id="t1",
        agent=AgentType.GEMMA4,
        score=80,
        syntax_score=25,
        test_score=30,
        scope_score=15,
        semantic_score=10,
        details="ok",
    )
    assert r.score == 80
    assert r.changed_files == []

def test_capability_profile_defaults():
    p = CapabilityProfile(
        max_reliable_tokens=8000,
        accuracy_by_type={"code_edit": 0.85},
    )
    assert p.session_failures == 0
    assert p.retry_budget == 3
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd /Users/ankitatiwari/Desktop/claude-playground/conductor && python -m pytest harness/tests/test_models.py -v
```

Expected: `ImportError: No module named 'harness.models'`

- [ ] **Step 3: Write `harness/models.py`**

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TaskType(str, Enum):
    CODE_EDIT = "code_edit"
    CODE_GEN = "code_gen"
    RESEARCH = "research"
    CROSS_FILE_REFACTOR = "cross_file_refactor"
    TEST_WRITE = "test_write"


class AgentType(str, Enum):
    GEMMA4 = "gemma4"
    CLAUDE_AGENT = "claude_agent"


@dataclass
class SubTask:
    id: str
    description: str
    type: TaskType
    files: list[str]
    estimated_tokens: int
    dependencies: list[str] = field(default_factory=list)
    assigned_agent: Optional[AgentType] = None


@dataclass
class EvalResult:
    subtask_id: str
    agent: AgentType
    score: int          # 0-100
    syntax_score: int   # 0-25
    test_score: int     # 0-35
    scope_score: int    # 0-20
    semantic_score: int # 0-20
    details: str
    changed_files: list[str] = field(default_factory=list)


@dataclass
class CapabilityProfile:
    max_reliable_tokens: int
    accuracy_by_type: dict[str, float]
    session_failures: int = 0
    retry_budget: int = 3
```

- [ ] **Step 4: Run test — verify it passes**

```bash
cd /Users/ankitatiwari/Desktop/claude-playground/conductor && python -m pytest harness/tests/test_models.py -v
```

Expected: `3 passed`

---

## Task 4: Capability profiles — load / save / update

**Files:**
- Create: `harness/capability_profiles.json`
- Create: `harness/profiles.py`
- Create: `harness/tests/test_profiles.py`

- [ ] **Step 1: Write `harness/capability_profiles.json` (initial seed)**

```json
{
  "gemma4": {
    "max_reliable_tokens": 8000,
    "accuracy_by_type": {
      "code_edit": 0.80,
      "code_gen": 0.75,
      "test_write": 0.72
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

- [ ] **Step 2: Write failing test**

```python
# harness/tests/test_profiles.py
import json
import tempfile
from pathlib import Path
from harness.models import CapabilityProfile
import harness.profiles as profiles_mod


def _write_tmp_profiles(tmp_path: Path) -> Path:
    data = {
        "gemma4": {
            "max_reliable_tokens": 8000,
            "accuracy_by_type": {"code_edit": 0.80},
            "session_failures": 0,
            "retry_budget": 3,
        }
    }
    p = tmp_path / "capability_profiles.json"
    p.write_text(json.dumps(data))
    return p


def test_load_profiles(tmp_path):
    path = _write_tmp_profiles(tmp_path)
    profiles = profiles_mod.load_profiles(path)
    assert "gemma4" in profiles
    assert isinstance(profiles["gemma4"], CapabilityProfile)
    assert profiles["gemma4"].max_reliable_tokens == 8000


def test_save_and_reload(tmp_path):
    path = _write_tmp_profiles(tmp_path)
    profiles = profiles_mod.load_profiles(path)
    profiles["gemma4"].session_failures = 2
    profiles_mod.save_profiles(profiles, path)
    reloaded = profiles_mod.load_profiles(path)
    assert reloaded["gemma4"].session_failures == 2


def test_update_accuracy_rolling_average(tmp_path):
    path = _write_tmp_profiles(tmp_path)
    profiles = profiles_mod.load_profiles(path)
    profiles_mod.update_accuracy(profiles, "gemma4", "code_edit", 40)
    # 0.80 * 0.7 + 0.40 * 0.3 = 0.56 + 0.12 = 0.68
    assert abs(profiles["gemma4"].accuracy_by_type["code_edit"] - 0.68) < 0.01
```

- [ ] **Step 3: Run test — verify it fails**

```bash
cd /Users/ankitatiwari/Desktop/claude-playground/conductor && python -m pytest harness/tests/test_profiles.py -v
```

Expected: `ImportError: cannot import name 'load_profiles' from 'harness.profiles'`

- [ ] **Step 4: Write `harness/profiles.py`**

```python
import json
from pathlib import Path
from harness.models import CapabilityProfile

_DEFAULT_PATH = Path(__file__).parent / "capability_profiles.json"


def load_profiles(path: Path = _DEFAULT_PATH) -> dict[str, CapabilityProfile]:
    data = json.loads(path.read_text())
    return {k: CapabilityProfile(**v) for k, v in data.items()}


def save_profiles(profiles: dict[str, CapabilityProfile], path: Path = _DEFAULT_PATH) -> None:
    data = {k: vars(v) for k, v in profiles.items()}
    path.write_text(json.dumps(data, indent=2))


def update_accuracy(
    profiles: dict[str, CapabilityProfile],
    agent: str,
    task_type: str,
    score: int,
) -> None:
    profile = profiles[agent]
    current = profile.accuracy_by_type.get(task_type, score / 100)
    profile.accuracy_by_type[task_type] = round(current * 0.7 + (score / 100) * 0.3, 3)
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
cd /Users/ankitatiwari/Desktop/claude-playground/conductor && python -m pytest harness/tests/test_profiles.py -v
```

Expected: `3 passed`

---

## Task 5: Router

**Files:**
- Create: `harness/router.py`
- Create: `harness/tests/test_router.py`

- [ ] **Step 1: Write failing tests**

```python
# harness/tests/test_router.py
from harness.models import SubTask, TaskType, AgentType, CapabilityProfile
from harness.router import route

def _profiles(failures=0, max_tokens=8000, code_edit_acc=0.85):
    return {
        "gemma4": CapabilityProfile(
            max_reliable_tokens=max_tokens,
            accuracy_by_type={"code_edit": code_edit_acc, "code_gen": 0.78, "test_write": 0.75},
            session_failures=failures,
            retry_budget=3,
        ),
        "claude_agent": CapabilityProfile(
            max_reliable_tokens=180000,
            accuracy_by_type={"code_edit": 0.95},
            session_failures=0,
            retry_budget=10,
        ),
    }

def _task(type=TaskType.CODE_EDIT, tokens=2000):
    return SubTask(id="t1", description="fix it", type=type, files=["a.py"], estimated_tokens=tokens)


def test_routes_small_code_edit_to_gemma4():
    assert route(_task(), _profiles()) == AgentType.GEMMA4


def test_routes_research_always_to_claude():
    assert route(_task(type=TaskType.RESEARCH), _profiles()) == AgentType.CLAUDE_AGENT


def test_routes_cross_file_refactor_always_to_claude():
    assert route(_task(type=TaskType.CROSS_FILE_REFACTOR), _profiles()) == AgentType.CLAUDE_AGENT


def test_routes_oversized_task_to_claude():
    assert route(_task(tokens=20000), _profiles(max_tokens=8000)) == AgentType.CLAUDE_AGENT


def test_routes_to_claude_when_failures_at_budget():
    assert route(_task(), _profiles(failures=3)) == AgentType.CLAUDE_AGENT


def test_routes_to_claude_when_accuracy_low():
    assert route(_task(), _profiles(code_edit_acc=0.65)) == AgentType.CLAUDE_AGENT
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd /Users/ankitatiwari/Desktop/claude-playground/conductor && python -m pytest harness/tests/test_router.py -v
```

Expected: `ImportError: No module named 'harness.router'`

- [ ] **Step 3: Write `harness/router.py`**

```python
from harness.models import SubTask, AgentType, TaskType, CapabilityProfile

_ALWAYS_CLAUDE: set[TaskType] = {TaskType.RESEARCH, TaskType.CROSS_FILE_REFACTOR}


def route(subtask: SubTask, profiles: dict[str, CapabilityProfile]) -> AgentType:
    g = profiles["gemma4"]

    if subtask.type in _ALWAYS_CLAUDE:
        return AgentType.CLAUDE_AGENT

    if subtask.estimated_tokens > g.max_reliable_tokens:
        return AgentType.CLAUDE_AGENT

    if g.session_failures >= g.retry_budget:
        return AgentType.CLAUDE_AGENT

    if g.accuracy_by_type.get(subtask.type.value, 1.0) < 0.70:
        return AgentType.CLAUDE_AGENT

    return AgentType.GEMMA4


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path
    from harness.profiles import load_profiles

    subtask_data = json.loads(sys.argv[1])
    subtask = SubTask(**subtask_data)
    profiles = load_profiles()
    agent = route(subtask, profiles)
    print(agent.value)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd /Users/ankitatiwari/Desktop/claude-playground/conductor && python -m pytest harness/tests/test_router.py -v
```

Expected: `6 passed`

---

## Task 6: gemma4 delegate script

**Files:**
- Create: `harness/gemma4_delegate.sh`

- [ ] **Step 1: Write `harness/gemma4_delegate.sh`**

```bash
#!/usr/bin/env bash
# Usage: gemma4_delegate.sh <workdir> <task_description>
# Runs opencode with gemma4 in workdir, prints output to stdout.
# Exit 0 on success, 1 if opencode errors.

set -euo pipefail

WORKDIR="${1:?workdir required}"
TASK="${2:?task description required}"

cd "$WORKDIR"

opencode run -m ollama/gemma4:latest "$TASK" 2>/dev/null
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x /Users/ankitatiwari/Desktop/claude-playground/conductor/harness/gemma4_delegate.sh
```

- [ ] **Step 3: Smoke test against a real file**

```bash
cd /Users/ankitatiwari/Desktop/claude-playground/conductor && \
  bash harness/gemma4_delegate.sh \
    /Users/ankitatiwari/Desktop/claude-playground/backtest-engine \
    "List the public functions in backend/metrics/engine.py — one per line, no explanation."
```

Expected: output lists function names (e.g. `calculate_metrics`, etc.) within ~30s. If opencode hangs >60s, `Ctrl+C` and check ollama is running (`ollama ps`).

---

## Task 7: Evaluator

**Files:**
- Create: `harness/evaluator.py`
- Create: `harness/tests/test_evaluator.py`

- [ ] **Step 1: Write failing tests**

```python
# harness/tests/test_evaluator.py
import textwrap
from pathlib import Path
from harness.models import SubTask, TaskType, AgentType
from harness.evaluator import (
    check_syntax,
    check_scope,
    estimate_semantic,
    evaluate,
)


def test_syntax_valid_python(tmp_path):
    f = tmp_path / "ok.py"
    f.write_text("def foo():\n    return 1\n")
    assert check_syntax([str(f)]) == 25


def test_syntax_invalid_python(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text("def foo(\n")
    assert check_syntax([str(f)]) == 0


def test_syntax_skips_non_python(tmp_path):
    f = tmp_path / "data.json"
    f.write_text('{"key": 1}')
    assert check_syntax([str(f)]) == 25


def test_scope_exact_match():
    assert check_scope(["a.py", "b.py"], ["a.py", "b.py"]) == 20


def test_scope_minor_overshoot():
    assert check_scope(["a.py", "b.py", "c.py"], ["a.py", "b.py"]) == 10


def test_scope_major_overshoot():
    assert check_scope(["a.py", "b.py", "c.py", "d.py"], ["a.py"]) == 0


def test_semantic_high_overlap():
    score = estimate_semantic("fix RSI calculation indicator", "fix RSI calculation")
    assert score >= 15


def test_semantic_low_overlap():
    score = estimate_semantic("unrelated output about weather", "fix RSI calculation")
    assert score <= 8


def test_evaluate_perfect_score(tmp_path):
    f = tmp_path / "ok.py"
    f.write_text("def foo():\n    return 1\n")
    subtask = SubTask(
        id="t1", description="fix foo function",
        type=TaskType.CODE_EDIT, files=[str(f)], estimated_tokens=100,
    )
    result = evaluate(subtask, AgentType.GEMMA4, [str(f)], "fix foo function done")
    # syntax=25, scope=20, semantic≥15, test=20 (no tests ran)
    assert result.score >= 70
```

- [ ] **Step 2: Run — verify it fails**

```bash
cd /Users/ankitatiwari/Desktop/claude-playground/conductor && python -m pytest harness/tests/test_evaluator.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Write `harness/evaluator.py`**

```python
import ast
import subprocess
from pathlib import Path

from harness.models import AgentType, EvalResult, SubTask


def check_syntax(files: list[str]) -> int:
    for f in files:
        path = Path(f)
        if path.suffix == ".py" and path.exists():
            try:
                ast.parse(path.read_text())
            except SyntaxError:
                return 0
    return 25


def _run_tests(files: list[str]) -> int:
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "--tb=no", "-q"] + files,
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            return 35
        if "no tests ran" in result.stdout or result.stdout.strip() == "":
            return 20
        return 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 0


def check_scope(changed: list[str], requested: list[str]) -> int:
    extra = set(changed) - set(requested)
    if not extra:
        return 20
    if len(extra) == 1:
        return 10
    return 0


def estimate_semantic(output: str, description: str) -> int:
    desc_words = set(description.lower().split())
    out_words = set(output.lower().split())
    if not desc_words:
        return 10
    overlap = len(desc_words & out_words) / len(desc_words)
    return int(overlap * 20)


def evaluate(
    subtask: SubTask,
    agent: AgentType,
    changed_files: list[str],
    output: str,
) -> EvalResult:
    syntax = check_syntax(changed_files)
    tests = _run_tests(changed_files)
    scope = check_scope(changed_files, subtask.files)
    semantic = estimate_semantic(output, subtask.description)
    total = syntax + tests + scope + semantic

    return EvalResult(
        subtask_id=subtask.id,
        agent=agent,
        score=total,
        syntax_score=syntax,
        test_score=tests,
        scope_score=scope,
        semantic_score=semantic,
        details=f"syntax={syntax}/25 tests={tests}/35 scope={scope}/20 semantic={semantic}/20",
        changed_files=changed_files,
    )


if __name__ == "__main__":
    import json
    import sys
    from harness.profiles import load_profiles

    data = json.loads(sys.argv[1])
    subtask = SubTask(**data["subtask"])
    agent = AgentType(data["agent"])
    changed = data["changed_files"]
    output = data["output"]
    result = evaluate(subtask, agent, changed, output)
    print(json.dumps(vars(result)))
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd /Users/ankitatiwari/Desktop/claude-playground/conductor && python -m pytest harness/tests/test_evaluator.py -v
```

Expected: `9 passed`

---

## Task 8: Healer

**Files:**
- Create: `harness/healer.py`
- Create: `harness/tests/test_healer.py`

- [ ] **Step 1: Write failing tests**

```python
# harness/tests/test_healer.py
from harness.models import SubTask, TaskType, AgentType, EvalResult, CapabilityProfile
from harness.healer import build_healer_report, apply_shrink, apply_reprompt


def _subtask():
    return SubTask(
        id="t1", description="fix RSI", type=TaskType.CODE_EDIT,
        files=["a.py", "b.py", "c.py", "d.py"], estimated_tokens=6000,
        assigned_agent=AgentType.GEMMA4,
    )


def _result():
    return EvalResult(
        subtask_id="t1", agent=AgentType.GEMMA4, score=55,
        syntax_score=25, test_score=0, scope_score=20, semantic_score=10,
        details="syntax=25/25 tests=0/35 scope=20/20 semantic=10/20",
    )


def _profiles():
    return {
        "gemma4": CapabilityProfile(
            max_reliable_tokens=8000,
            accuracy_by_type={"code_edit": 0.80},
            session_failures=1,
            retry_budget=3,
        )
    }


def test_report_contains_all_strategies():
    report = build_healer_report(_subtask(), _result(), _profiles())
    assert "Strategy A" in report
    assert "Strategy B" in report
    assert "Strategy C" in report
    assert "55/100" in report


def test_apply_shrink_halves_files():
    shrunk = apply_shrink(_subtask())
    assert len(shrunk.files) == 2
    assert shrunk.estimated_tokens == 3000
    assert "_shrunk" in shrunk.id


def test_apply_shrink_at_least_one_file():
    t = SubTask(id="t1", description="x", type=TaskType.CODE_EDIT, files=["a.py"], estimated_tokens=100)
    shrunk = apply_shrink(t)
    assert len(shrunk.files) == 1


def test_apply_reprompt_injects_failure():
    reprompted = apply_reprompt(_subtask(), "tests failed: assertion error on line 42")
    assert "tests failed" in reprompted.description
    assert "_reprompt" in reprompted.id
```

- [ ] **Step 2: Run — verify it fails**

```bash
cd /Users/ankitatiwari/Desktop/claude-playground/conductor && python -m pytest harness/tests/test_healer.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Write `harness/healer.py`**

```python
from harness.models import AgentType, CapabilityProfile, EvalResult, SubTask


def build_healer_report(
    subtask: SubTask,
    result: EvalResult,
    profiles: dict[str, CapabilityProfile],
) -> str:
    agent_name = result.agent.value
    failures = profiles.get("gemma4", CapabilityProfile(0, {})).session_failures
    budget = profiles.get("gemma4", CapabilityProfile(0, {}, retry_budget=3)).retry_budget

    return (
        f"\n[ACCURACY ALERT] Subtask \"{subtask.description}\" scored {result.score}/100\n"
        f"  Details: {result.details}\n\n"
        f"  Strategy A (Shrink):    Split file scope in half, retry {agent_name}. +~30s, same cost.\n"
        f"  Strategy B (Re-prompt): Inject failure reason as constraint, retry {agent_name}. +~30s, same cost.\n"
        f"  Strategy C (Escalate):  Hand to claude_agent. +~60s, higher cost. "
        f"Marks gemma4 failure ({failures + 1}/{budget}).\n\n"
        f"  → Choose A, B, or C:"
    )


def apply_shrink(subtask: SubTask) -> SubTask:
    half = max(1, len(subtask.files) // 2)
    return SubTask(
        id=subtask.id + "_shrunk",
        description=subtask.description,
        type=subtask.type,
        files=subtask.files[:half],
        estimated_tokens=subtask.estimated_tokens // 2,
        dependencies=subtask.dependencies,
        assigned_agent=subtask.assigned_agent,
    )


def apply_reprompt(subtask: SubTask, failure_detail: str) -> SubTask:
    return SubTask(
        id=subtask.id + "_reprompt",
        description=(
            f"{subtask.description}\n\n"
            f"Previous attempt failed: {failure_detail}. "
            f"Strictly modify only the requested scope."
        ),
        type=subtask.type,
        files=subtask.files,
        estimated_tokens=subtask.estimated_tokens,
        dependencies=subtask.dependencies,
        assigned_agent=subtask.assigned_agent,
    )
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd /Users/ankitatiwari/Desktop/claude-playground/conductor && python -m pytest harness/tests/test_healer.py -v
```

Expected: `4 passed`

---

## Task 9: Benchmark harness

**Files:**
- Create: `gemma4-bench/bench.py`

- [ ] **Step 1: Write `gemma4-bench/bench.py`**

```python
#!/usr/bin/env python3
"""
Benchmark gemma4 across context sizes and task types.
Writes results to gemma4-bench/bench_results.json
Updates harness/capability_profiles.json with discovered thresholds.
"""
import json
import subprocess
import sys
import time
import ast
from pathlib import Path

BENCH_DIR = Path(__file__).parent
HARNESS_DIR = BENCH_DIR.parent / "harness"
PROFILES_PATH = HARNESS_DIR / "capability_profiles.json"
RESULTS_PATH = BENCH_DIR / "bench_results.json"

# Real source files used as payload — adjust paths if structure changes
SOURCE_FILES = [
    Path("/Users/ankitatiwari/Desktop/claude-playground/backtest-engine/backend/metrics/engine.py"),
    Path("/Users/ankitatiwari/Desktop/claude-playground/backtest-engine/backend/costs/engine.py"),
    Path("/Users/ankitatiwari/Desktop/claude-playground/trading-system/backend/llm/tools.py"),
]

TOKEN_TARGETS = [1000, 4000, 8000, 16000, 32000]
TASK_TYPES = ["code_edit", "code_gen", "test_write"]
TRIALS = 2  # per cell — increase to 3 for more accuracy


def _build_payload(target_tokens: int) -> str:
    """Repeat source files until we hit target token count (approx chars/4)."""
    target_chars = target_tokens * 4
    parts = []
    total = 0
    sources = [f.read_text() for f in SOURCE_FILES if f.exists()]
    if not sources:
        sources = ["def placeholder(): pass\n" * 50]
    while total < target_chars:
        for s in sources:
            parts.append(s)
            total += len(s)
            if total >= target_chars:
                break
    return "\n\n".join(parts)[:target_chars]


def _task_prompt(task_type: str, payload: str) -> str:
    prompts = {
        "code_edit": (
            f"Given this code:\n\n{payload}\n\n"
            "Add a docstring to the first function you see. Output only the modified function, nothing else."
        ),
        "code_gen": (
            f"Given this code context:\n\n{payload[:2000]}\n\n"
            "Write a new standalone Python function called `validate_input` that checks if a dict has a 'symbol' key. "
            "Output only the function, no explanation."
        ),
        "test_write": (
            f"Given this code:\n\n{payload[:2000]}\n\n"
            "Write one pytest test for any function you see. Output only the test function, no explanation."
        ),
    }
    return prompts[task_type]


def _score_output(output: str, task_type: str) -> int:
    """Heuristic: 0-100. Checks output is non-empty Python-ish."""
    if not output.strip():
        return 0
    # Try parsing as Python snippet
    try:
        ast.parse(output)
        syntax_ok = True
    except SyntaxError:
        syntax_ok = False

    if task_type == "code_edit":
        has_docstring = '"""' in output or "'''" in output
        return 90 if (syntax_ok and has_docstring) else 50 if syntax_ok else 20

    if task_type == "code_gen":
        has_func = "def validate_input" in output
        return 90 if (syntax_ok and has_func) else 50 if has_func else 20

    if task_type == "test_write":
        has_test = "def test_" in output
        return 90 if (syntax_ok and has_test) else 50 if has_test else 20

    return 30


def _run_gemma4(prompt: str) -> tuple[str, float]:
    """Returns (output, latency_seconds). Output is '' on failure."""
    start = time.time()
    try:
        result = subprocess.run(
            ["opencode", "run", "-m", "ollama/gemma4:latest", prompt],
            capture_output=True, text=True, timeout=120,
        )
        latency = time.time() - start
        if result.returncode != 0:
            return "", latency
        return result.stdout.strip(), latency
    except subprocess.TimeoutExpired:
        return "", 120.0


def run_benchmark() -> dict:
    results = {}

    for token_target in TOKEN_TARGETS:
        payload = _build_payload(token_target)
        actual_tokens = len(payload) // 4
        print(f"\n=== Context: ~{actual_tokens:,} tokens ===")

        for task_type in TASK_TYPES:
            prompt = _task_prompt(task_type, payload)
            scores = []
            latencies = []

            for trial in range(TRIALS):
                print(f"  {task_type} trial {trial+1}/{TRIALS}...", end=" ", flush=True)
                output, latency = _run_gemma4(prompt)
                score = _score_output(output, task_type)
                scores.append(score)
                latencies.append(latency)
                print(f"score={score} latency={latency:.1f}s")

            key = f"{actual_tokens}_{task_type}"
            results[key] = {
                "tokens": actual_tokens,
                "task_type": task_type,
                "avg_score": round(sum(scores) / len(scores), 1),
                "avg_latency": round(sum(latencies) / len(latencies), 1),
                "scores": scores,
            }

    return results


def derive_thresholds(results: dict) -> dict[str, object]:
    """Find max reliable token count (avg_score >= 70) per task type."""
    by_type: dict[str, list] = {}
    for cell in results.values():
        t = cell["task_type"]
        by_type.setdefault(t, []).append(cell)

    thresholds = {}
    for task_type, cells in by_type.items():
        cells.sort(key=lambda c: c["tokens"])
        max_reliable = 1000
        acc_scores = {}
        for cell in cells:
            if cell["avg_score"] >= 70:
                max_reliable = cell["tokens"]
                acc_scores[task_type] = round(cell["avg_score"] / 100, 3)
        thresholds[task_type] = {
            "max_reliable_tokens": max_reliable,
            "accuracy": acc_scores.get(task_type, 0.5),
        }
    return thresholds


def update_profiles(thresholds: dict) -> None:
    profiles = json.loads(PROFILES_PATH.read_text())
    gemma = profiles["gemma4"]

    token_limits = [v["max_reliable_tokens"] for v in thresholds.values()]
    gemma["max_reliable_tokens"] = min(token_limits) if token_limits else 8000

    for task_type, data in thresholds.items():
        gemma["accuracy_by_type"][task_type] = data["accuracy"]

    gemma["session_failures"] = 0
    PROFILES_PATH.write_text(json.dumps(profiles, indent=2))
    print(f"\nUpdated {PROFILES_PATH}")


def main():
    print("Benchmarking gemma4 via opencode...")
    print(f"Trials per cell: {TRIALS}, Task types: {TASK_TYPES}")
    print(f"Token targets: {TOKEN_TARGETS}")

    results = run_benchmark()
    RESULTS_PATH.write_text(json.dumps(results, indent=2))
    print(f"\nRaw results saved to {RESULTS_PATH}")

    thresholds = derive_thresholds(results)
    print("\n--- Derived thresholds ---")
    for task_type, data in thresholds.items():
        print(f"  {task_type}: max_reliable_tokens={data['max_reliable_tokens']:,}  accuracy={data['accuracy']}")

    update_profiles(thresholds)
    print("\nBenchmark complete. Run the full test suite next:")
    print("  cd conductor && python -m pytest -v")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run bench (this takes several minutes — grab a coffee)**

```bash
cd /Users/ankitatiwari/Desktop/claude-playground/conductor && python gemma4-bench/bench.py
```

Expected: table of scores printed, `bench_results.json` written, `capability_profiles.json` updated. Each cell takes 10-30s. Total ~10-30 min depending on trials × context sizes.

- [ ] **Step 3: Verify profiles were updated**

```bash
cat /Users/ankitatiwari/Desktop/claude-playground/conductor/harness/capability_profiles.json
```

Expected: `max_reliable_tokens` and `accuracy_by_type` for `gemma4` reflect benchmark results.

---

## Task 10: Full test suite

- [ ] **Step 1: Run all tests**

```bash
cd /Users/ankitatiwari/Desktop/claude-playground/conductor && python -m pytest -v
```

Expected: all tests from Tasks 3-8 pass. Minimum `16 passed`.

- [ ] **Step 2: Verify router CLI works end-to-end**

```bash
cd /Users/ankitatiwari/Desktop/claude-playground/conductor && python -m harness.router '{"id":"t1","description":"fix foo","type":"code_edit","files":["a.py"],"estimated_tokens":2000}'
```

Expected: prints `gemma4` or `claude_agent` (depending on current profiles).

- [ ] **Step 3: Verify evaluator CLI works**

```bash
cd /Users/ankitatiwari/Desktop/claude-playground/conductor && python -m harness.evaluator '{"subtask":{"id":"t1","description":"fix foo","type":"code_edit","files":["/tmp/x.py"],"estimated_tokens":100},"agent":"gemma4","changed_files":[],"output":"fix foo done"}'
```

Expected: JSON blob with `score` field printed.

---

## Usage Reference (for Claude the orchestrator)

When executing a real task, Claude follows this sequence:

```
1. Decompose task → list of SubTask JSON objects with DAG dependencies
2. Load profiles:
     python -m harness.profiles  (or just read capability_profiles.json)
3. Route each subtask:
     python -m harness.router '<subtask_json>'
4. Execute:
     gemma4 → bash harness/gemma4_delegate.sh <workdir> "<task>"
     claude  → Agent tool with task + file contents
5. Evaluate result:
     python -m harness.evaluator '<eval_input_json>'
6. If score < 70:
     python -m harness.healer   (or call healer functions directly)
     → present report to user, await A/B/C choice
     → apply_shrink / apply_reprompt / escalate
     → re-execute and re-evaluate
7. Update profiles:
     profiles.update_accuracy(profiles, agent, task_type, score)
     profiles.save_profiles(profiles)
```
