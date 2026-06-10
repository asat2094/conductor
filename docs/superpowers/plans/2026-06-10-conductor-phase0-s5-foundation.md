# Conductor Foundation (Phase 0 + S5 cost-skip) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the ROI meta-gate — route uneconomically-small tasks to a new `CLAUDE_INLINE` target instead of the delegation pipeline — plus the data-model and bench prerequisites it rests on, without breaking the 97 existing tests.

**Architecture:** Additive only. Extend `models.py` enums/dataclass with defaulted fields (non-breaking). Add a deterministic `cost_model.py` that compares the orchestrator's *inline* token cost (loading file bodies into main context) against its *delegation* cost (seeing only briefs + verdicts). Add a standalone `cost_skip()` pre-check in `router.py` that the pipeline consults *before* `rank_providers()`, so `rank_providers` stays pure and its tests untouched. Un-hardcode `bench.py`'s foreign source paths so the baseline generator runs on any machine.

**Tech Stack:** Python 3.11+ (repo runs 3.14), pytest (`/opt/homebrew/bin/pytest`), stdlib only.

**Requirements covered:** REQ-R1 (cost-skip), partial REQ-R2 prerequisite (bench runnable), NFR-MIG-1 (additive migration). ADR-0016, ADR-0005. Tasks T0.1, T0.3, T0.4, T5.1 from `docs/specs/conductor/tasks.md`.

**Scope note:** This is plan 1 of the spine. Demand-driven decomposition (T5.2), `codegraph_adapter` (T0.2), and full `baseline.json` seeding (S9) are deferred to later plans — they depend on the decomposition subsystem (S12) which is not built here.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `harness/models.py` | data model: enums + `SubTask` | Modify — add enum values + defaulted `SubTask` fields |
| `harness/cost_model.py` | deterministic inline-vs-delegation token-cost projection | Create |
| `harness/router.py` | routing — add `cost_skip()` pre-check | Modify |
| `harness/tests/test_models.py` | model tests | Modify — assert new values/fields |
| `harness/tests/test_cost_model.py` | cost-model tests | Create |
| `harness/tests/test_router.py` | router tests | Modify — add cost_skip cases |
| `gemma4-bench/bench.py` | capability benchmark | Modify — un-hardcode source paths |
| `harness/tests/test_bench_sources.py` | bench source-resolution test | Create |

---

## Task 1: Extend the data model (non-breaking)

**Files:**
- Modify: `harness/models.py`
- Test: `harness/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Add to `harness/tests/test_models.py`:

```python
from harness.models import TaskType, AgentType, SubTask


def test_new_task_types_exist():
    assert TaskType.REFACTOR.value == "refactor"
    assert TaskType.SIGNATURE_CHANGE.value == "signature_change"
    assert TaskType.PERF.value == "perf"


def test_claude_inline_agent_exists():
    assert AgentType.CLAUDE_INLINE.value == "claude_inline"


def test_subtask_new_fields_default_empty_and_low():
    st = SubTask(id="t1", description="d", type=TaskType.CODE_EDIT, files=["a.py"], estimated_tokens=100)
    assert st.sensitivity == "low"
    assert st.writes_files == []
    assert st.produces == []
    assert st.consumes == []
    assert st.logical_deps == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/opt/homebrew/bin/pytest harness/tests/test_models.py -v`
Expected: FAIL — `AttributeError: REFACTOR` / `CLAUDE_INLINE`, and `TypeError` on unknown `SubTask` fields.

- [ ] **Step 3: Write minimal implementation**

In `harness/models.py`, extend the two enums and `SubTask` (keep existing members; add new ones). `TaskType` becomes:

```python
class TaskType(str, Enum):
    CODE_EDIT = "code_edit"
    CODE_GEN = "code_gen"
    RESEARCH = "research"
    CROSS_FILE_REFACTOR = "cross_file_refactor"
    TEST_WRITE = "test_write"
    REFACTOR = "refactor"
    SIGNATURE_CHANGE = "signature_change"
    PERF = "perf"


class AgentType(str, Enum):
    GEMMA4 = "gemma4"
    CLAUDE_AGENT = "claude_agent"
    CLAUDE_INLINE = "claude_inline"
```

Add the new defaulted fields to `SubTask` (after `assigned_agent`):

```python
@dataclass
class SubTask:
    id: str
    description: str
    type: TaskType
    files: list[str]
    estimated_tokens: int
    dependencies: list[str] = field(default_factory=list)
    assigned_agent: Optional[AgentType] = None
    sensitivity: str = "low"                       # "low" | "high" (REQ-R4)
    writes_files: list[str] = field(default_factory=list)
    produces: list[str] = field(default_factory=list)
    consumes: list[str] = field(default_factory=list)
    logical_deps: list[str] = field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/opt/homebrew/bin/pytest harness/tests/test_models.py -v`
Expected: PASS (new tests + all pre-existing model tests).

- [ ] **Step 5: Run the full suite to confirm no regression**

Run: `/opt/homebrew/bin/pytest -q`
Expected: all pre-existing tests still pass (additive change; defaults make new fields optional).

- [ ] **Step 6: Commit**

```bash
git add harness/models.py harness/tests/test_models.py
git commit -m "feat(models): add REFACTOR/SIGNATURE_CHANGE/PERF task types, CLAUDE_INLINE agent, SubTask DAG/sensitivity fields"
```

---

## Task 2: Deterministic cost model

**Files:**
- Create: `harness/cost_model.py`
- Test: `harness/tests/test_cost_model.py`

**Concept:** the orchestrator's *paid* token cost differs by route. **Inline** = it loads the file bodies into its own (bloating) context ≈ `estimated_tokens`. **Delegation** = it sees only a fixed-size brief + lean verdict (`_BRIEF_OVERHEAD_TOKENS`), makers bear the file tokens (free/cheap). So delegation wins for large tasks; inline wins for small ones. The crossover is `min_delegation_tokens`. The two constants are **calibration debts** (design §7) — conservative v1 anchors, retuned from the run-ledger later.

- [ ] **Step 1: Write the failing test**

Create `harness/tests/test_cost_model.py`:

```python
from harness.models import SubTask, TaskType
from harness.cost_model import (
    estimate_inline_cost,
    estimate_delegation_orchestrator_cost,
    should_inline,
    MIN_DELEGATION_TOKENS,
)


def _st(tokens: int) -> SubTask:
    return SubTask(id="t", description="d", type=TaskType.CODE_EDIT, files=["a.py"], estimated_tokens=tokens)


def test_inline_cost_is_the_context_load():
    assert estimate_inline_cost(_st(5000)) == 5000


def test_delegation_orchestrator_cost_is_fixed_overhead_not_bodies():
    cheap = estimate_delegation_orchestrator_cost(_st(5000))
    big = estimate_delegation_orchestrator_cost(_st(50000))
    assert cheap == big  # orchestrator never sees the bodies, so cost is independent of file size


def test_small_task_should_inline():
    assert should_inline(_st(MIN_DELEGATION_TOKENS - 1)) is True


def test_large_task_should_not_inline():
    assert should_inline(_st(MIN_DELEGATION_TOKENS + 10_000)) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/opt/homebrew/bin/pytest harness/tests/test_cost_model.py -v`
Expected: FAIL — `ModuleNotFoundError: harness.cost_model`.

- [ ] **Step 3: Write minimal implementation**

Create `harness/cost_model.py`:

```python
"""
Deterministic projection of the orchestrator's PAID token cost per route (ADR-0016, REQ-R1).

inline      = orchestrator loads file bodies into its own (bloating) context ≈ estimated_tokens.
delegation  = orchestrator sees only a fixed-size brief + lean verdict; makers bear the file tokens.

So delegation pays off only above a crossover (MIN_DELEGATION_TOKENS). Below it, inline is cheaper.

CALIBRATION DEBT (design §7): these constants are conservative v1 anchors. Retune from the
run-ledger once real per-stage token accounting exists.
"""
from harness.models import SubTask

# Orchestrator tokens to author a brief + read a lean verdict for one delegated unit.
_BRIEF_OVERHEAD_TOKENS = 800

# Below this estimated size, delegation overhead is not worth it → inline.
MIN_DELEGATION_TOKENS = _BRIEF_OVERHEAD_TOKENS


def estimate_inline_cost(subtask: SubTask) -> int:
    """Paid orchestrator tokens if it does the unit inline: it loads the bodies."""
    return subtask.estimated_tokens


def estimate_delegation_orchestrator_cost(subtask: SubTask) -> int:
    """Paid orchestrator tokens if delegated: only brief + verdict, independent of file size."""
    return _BRIEF_OVERHEAD_TOKENS


def should_inline(subtask: SubTask, min_delegation_tokens: int = MIN_DELEGATION_TOKENS) -> bool:
    """True when the task is too small for delegation overhead to pay off (REQ-R1)."""
    return subtask.estimated_tokens < min_delegation_tokens
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/opt/homebrew/bin/pytest harness/tests/test_cost_model.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add harness/cost_model.py harness/tests/test_cost_model.py
git commit -m "feat(cost): add deterministic inline-vs-delegation cost model (ADR-0016)"
```

---

## Task 3: `cost_skip()` pre-check in the router

**Files:**
- Modify: `harness/router.py` (add function; do NOT touch `rank_providers` core loop)
- Test: `harness/tests/test_router.py`

**Why standalone:** the pipeline calls `cost_skip()` *before* `rank_providers()`. If it returns an `AgentType`, the pipeline short-circuits to inline and skips ranking entirely. Keeping it out of `rank_providers`' loop means every existing `rank_providers`/`route` test stays green.

- [ ] **Step 1: Write the failing test**

Add to `harness/tests/test_router.py`:

```python
from harness.models import SubTask, TaskType, AgentType
from harness.router import cost_skip


def _st(tokens, ttype=TaskType.CODE_EDIT):
    return SubTask(id="t", description="d", type=ttype, files=["a.py"], estimated_tokens=tokens)


def test_cost_skip_routes_tiny_task_to_inline():
    assert cost_skip(_st(100)) == AgentType.CLAUDE_INLINE


def test_cost_skip_passes_large_task_through():
    assert cost_skip(_st(20_000)) is None  # None → fall through to rank_providers


def test_cost_skip_does_not_inline_always_claude_types():
    # research/cross_file_refactor must reach claude_agent via normal routing, not inline
    assert cost_skip(_st(50, ttype=TaskType.RESEARCH)) is None
    assert cost_skip(_st(50, ttype=TaskType.CROSS_FILE_REFACTOR)) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/opt/homebrew/bin/pytest harness/tests/test_router.py::test_cost_skip_routes_tiny_task_to_inline -v`
Expected: FAIL — `ImportError: cannot import name 'cost_skip'`.

- [ ] **Step 3: Write minimal implementation**

In `harness/router.py`, add the import and the function (place after the `_ALWAYS_CLAUDE` definition):

```python
from harness.models import SubTask, AgentType, TaskType, CapabilityProfile
from harness.cost_model import should_inline

# ... existing _ALWAYS_CLAUDE ...


def cost_skip(subtask: SubTask) -> AgentType | None:
    """
    ROI meta-gate (REQ-R1, ADR-0016). Returns CLAUDE_INLINE when delegating the task
    would cost the orchestrator more than just doing it inline (task too small for the
    delegation overhead to pay off). Returns None to fall through to rank_providers().

    Research / cross-file-refactor are never inlined here — they reach claude_agent via
    normal routing.
    """
    if subtask.type in _ALWAYS_CLAUDE:
        return None
    if should_inline(subtask):
        return AgentType.CLAUDE_INLINE
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/opt/homebrew/bin/pytest harness/tests/test_router.py -v`
Expected: PASS (new cost_skip tests + all pre-existing router tests, which never call `cost_skip`).

- [ ] **Step 5: Run the full suite**

Run: `/opt/homebrew/bin/pytest -q`
Expected: all green — `rank_providers`/`route` untouched.

- [ ] **Step 6: Commit**

```bash
git add harness/router.py harness/tests/test_router.py
git commit -m "feat(router): add cost_skip() ROI meta-gate routing tiny tasks to CLAUDE_INLINE (REQ-R1)"
```

---

## Task 4: Un-hardcode the bench source paths

**Files:**
- Modify: `gemma4-bench/bench.py` (the `SOURCE_FILES` definition near the top)
- Test: `harness/tests/test_bench_sources.py`

**Problem (review C2/M2):** `bench.py` hardcodes `/Users/ankitatiwari/...` absolute paths, so its baseline generator is non-runnable on any other machine. Resolve sources from an env var or repo-relative defaults, with the existing synthetic fallback preserved.

- [ ] **Step 1: Write the failing test**

Create `harness/tests/test_bench_sources.py`:

```python
import importlib.util
from pathlib import Path

BENCH = Path(__file__).resolve().parents[2] / "gemma4-bench" / "bench.py"


def _load_bench():
    spec = importlib.util.spec_from_file_location("bench", BENCH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_no_hardcoded_foreign_paths():
    text = BENCH.read_text()
    assert "/Users/ankitatiwari" not in text


def test_resolve_sources_env_override(tmp_path, monkeypatch):
    f = tmp_path / "sample.py"
    f.write_text("def x():\n    return 1\n")
    monkeypatch.setenv("CONDUCTOR_BENCH_SOURCES", str(f))
    mod = _load_bench()
    sources = mod.resolve_sources()
    assert any("def x()" in s for s in sources)


def test_resolve_sources_falls_back_to_synthetic(monkeypatch):
    monkeypatch.delenv("CONDUCTOR_BENCH_SOURCES", raising=False)
    mod = _load_bench()
    sources = mod.resolve_sources(candidates=[])  # no real files
    assert sources and all(isinstance(s, str) for s in sources)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/opt/homebrew/bin/pytest harness/tests/test_bench_sources.py -v`
Expected: FAIL — `test_no_hardcoded_foreign_paths` (foreign path present) and `AttributeError: resolve_sources`.

- [ ] **Step 3: Write minimal implementation**

In `gemma4-bench/bench.py`, replace the hardcoded `SOURCE_FILES = [...]` block with an env/repo-relative resolver:

```python
import os

# Default source candidates: this repo's own harness files (always present),
# overridable via CONDUCTOR_BENCH_SOURCES (os.pathsep-separated absolute paths).
_DEFAULT_SOURCE_CANDIDATES = [
    HARNESS_DIR / "orchestrate.py",
    HARNESS_DIR / "evaluator.py",
    HARNESS_DIR / "provider_call.py",
]


def resolve_sources(candidates: list | None = None) -> list[str]:
    """Return source texts for payload synthesis. Env override → candidates → synthetic fallback."""
    env = os.environ.get("CONDUCTOR_BENCH_SOURCES")
    if env:
        paths = [Path(p) for p in env.split(os.pathsep) if p]
    elif candidates is not None:
        paths = list(candidates)
    else:
        paths = list(_DEFAULT_SOURCE_CANDIDATES)
    texts = [p.read_text() for p in paths if isinstance(p, Path) and p.exists()]
    if not texts:
        texts = ["def placeholder(): pass\n" * 50]
    return texts
```

Then update `_build_payload` to use the resolver instead of the old module-level `SOURCE_FILES`:

```python
def _build_payload(target_tokens: int) -> str:
    target_chars = target_tokens * 4
    parts = []
    total = 0
    sources = resolve_sources()
    while total < target_chars:
        for s in sources:
            parts.append(s)
            total += len(s)
            if total >= target_chars:
                break
    return "\n\n".join(parts)[:target_chars]
```

Delete the old `SOURCE_FILES = [Path("/Users/ankitatiwari/...")]` list entirely.

- [ ] **Step 4: Run test to verify it passes**

Run: `/opt/homebrew/bin/pytest harness/tests/test_bench_sources.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gemma4-bench/bench.py harness/tests/test_bench_sources.py
git commit -m "fix(bench): resolve sources from env/repo-relative paths, drop hardcoded foreign abs paths (C2)"
```

---

## Task 5: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Run the entire suite**

Run: `/opt/homebrew/bin/pytest -q`
Expected: all pre-existing tests PASS + the new `test_cost_model.py`, `test_bench_sources.py`, and added cases in `test_models.py` / `test_router.py`. No regressions (every change was additive or isolated).

- [ ] **Step 2: Manual smoke of the cost-skip decision**

Run:
```bash
python3 -c "
from harness.models import SubTask, TaskType
from harness.router import cost_skip
print('tiny  ->', cost_skip(SubTask('a','x',TaskType.CODE_EDIT,['f.py'],100)))
print('large ->', cost_skip(SubTask('b','y',TaskType.CODE_EDIT,['f.py'],20000)))
"
```
Expected:
```
tiny  -> AgentType.CLAUDE_INLINE
large -> None
```

- [ ] **Step 3: Commit any final touch-ups** (only if needed)

```bash
git add -A && git commit -m "test: foundation milestone (Phase 0 + S5 cost-skip) green"
```

---

## Notes for the next plan (S12 — decomposition)
- Wire `cost_skip()` into the orchestrate/pipeline entrypoint as the first routing step.
- Build `codegraph_adapter.py` (T0.2) with the codegraphcontext MCP + degrade path (REQ-D4).
- Add `baseline.json` emission + the 3 new task-type scorers to `bench.py`, then S9 cold-start seeding (REQ-R2).
- Implement demand-driven decomposition (T5.2) once `decompose.py` exists.
