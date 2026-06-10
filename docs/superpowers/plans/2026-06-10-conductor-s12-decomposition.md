# Conductor Decomposition (S12 core + codegraph) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn orchestrator-authored `SubtaskBrief`s into a validated, topologically-ordered producer→consumer DAG of dispatch waves — the deterministic decomposition core, with a codegraph adapter that degrades gracefully when no graph is available.

**Architecture:** Pure, deterministic, fully unit-testable modules. The non-deterministic LLM parts (authoring `logical_deps`, cutting `context_slices`) are *inputs* supplied by the orchestrator; everything here is deterministic given those inputs. `codegraph_adapter` isolates the only external dependency (codegraphcontext MCP) behind an injectable function so the core stays testable and the MCP-absent path is explicit (REQ-D4).

**Tech Stack:** Python 3.11+ (repo runs 3.14), pytest via `python3 -m pytest` (the `/opt/homebrew/bin/pytest` shim is broken in this env), stdlib only (no jsonschema dep — hand-rolled validation).

**Requirements covered:** REQ-D1 (producer→consumer DAG), REQ-D2 (SubtaskBrief), REQ-D3 (lint_plan), REQ-D4 (codegraph + degrade), REQ-D5 (hard-gate: lint failure blocks). ADR-0011. Tasks T0.2, T12.1, T12.2, T12.3 from `docs/specs/conductor/tasks.md`.

**Scope note:** Plan 2 of the spine, on branch `feat/conductor-distributed-build`. Deferred to later plans: orchestrator-output gate REQ-O2/O3 (T12.4), phase-boundary compaction runtime, wiring `cost_skip`+decompose into `orchestrate`, the maker/gate machinery. Baseline: 109 pass / 3 pre-existing `openai`-missing failures — add no new failures.

Brief shape is fixed by `docs/specs/conductor/schemas/subtask_brief.schema.json`; this plan implements a dataclass + light validator matching it (no external jsonschema).

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `harness/brief.py` | `SubtaskBrief` dataclass + `validate_brief(dict)` | Create |
| `harness/dag.py` | build producer→consumer edges, topo-sort into waves, file-overlap | Create |
| `harness/lint_plan.py` | consumed-symbol resolution + placeholder scan over briefs | Create |
| `harness/codegraph_adapter.py` | injectable codegraph dependency lookup + degrade path | Create |
| `harness/decompose.py` | orchestrate: validate → lint (hard gate) → DAG → waves | Create |
| `harness/tests/test_brief.py` | brief validation tests | Create |
| `harness/tests/test_dag.py` | DAG / topo / overlap tests | Create |
| `harness/tests/test_lint_plan.py` | lint tests | Create |
| `harness/tests/test_codegraph_adapter.py` | adapter + degrade tests | Create |
| `harness/tests/test_decompose.py` | end-to-end decomposition tests | Create |

---

## Task 1: `SubtaskBrief` dataclass + validator

**Files:**
- Create: `harness/brief.py`
- Test: `harness/tests/test_brief.py`

- [ ] **Step 1: Write the failing test**

Create `harness/tests/test_brief.py`:

```python
from harness.brief import SubtaskBrief, validate_brief

VALID = {
    "id": "u1",
    "goal": "add type hints to parse_order",
    "task_type": "code_edit",
    "files": ["orders.py"],
    "context_slices": [{"path": "orders.py", "start_line": 1, "end_line": 20}],
    "contract": {"produces": ["parse_order"], "consumes": [], "expected_behavior": "returns Order"},
    "verify_cmd": "pytest tests/test_orders.py::test_parse_order",
    "exit_criteria": "parse_order is fully annotated and tests pass",
    "sensitivity": "low",
}


def test_validate_accepts_well_formed_brief():
    assert validate_brief(VALID) == []


def test_validate_flags_missing_required_key():
    bad = {k: v for k, v in VALID.items() if k != "contract"}
    errs = validate_brief(bad)
    assert any("contract" in e for e in errs)


def test_validate_flags_bad_sensitivity():
    bad = {**VALID, "sensitivity": "medium"}
    errs = validate_brief(bad)
    assert any("sensitivity" in e for e in errs)


def test_subtaskbrief_from_dict_roundtrips_core_fields():
    b = SubtaskBrief.from_dict(VALID)
    assert b.id == "u1"
    assert b.contract.produces == ["parse_order"]
    assert b.context_slices[0].path == "orders.py"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest harness/tests/test_brief.py -v`
Expected: FAIL — `ModuleNotFoundError: harness.brief`.

- [ ] **Step 3: Write minimal implementation**

Create `harness/brief.py`:

```python
"""
SubtaskBrief — the self-contained unit of work emitted by decomposition (REQ-D2, ADR-0011).
Shape matches docs/specs/conductor/schemas/subtask_brief.schema.json. Stdlib-only validation
(no jsonschema dependency).
"""
from dataclasses import dataclass, field

_REQUIRED = ("id", "goal", "task_type", "files", "context_slices", "contract", "verify_cmd", "exit_criteria", "sensitivity")
_VALID_TASK_TYPES = {"code_edit", "code_gen", "test_write", "refactor", "signature_change", "perf"}
_VALID_SENSITIVITY = {"low", "high"}


@dataclass
class ContextSlice:
    path: str
    start_line: int
    end_line: int


@dataclass
class Contract:
    produces: list[str] = field(default_factory=list)
    consumes: list[str] = field(default_factory=list)
    expected_behavior: str = ""


@dataclass
class SubtaskBrief:
    id: str
    goal: str
    task_type: str
    files: list[str]
    context_slices: list[ContextSlice]
    contract: Contract
    verify_cmd: str
    exit_criteria: str
    sensitivity: str = "low"
    writes_files: list[str] = field(default_factory=list)
    logical_deps: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "SubtaskBrief":
        c = d["contract"]
        return cls(
            id=d["id"],
            goal=d["goal"],
            task_type=d["task_type"],
            files=list(d["files"]),
            context_slices=[ContextSlice(**s) for s in d["context_slices"]],
            contract=Contract(
                produces=list(c.get("produces", [])),
                consumes=list(c.get("consumes", [])),
                expected_behavior=c.get("expected_behavior", ""),
            ),
            verify_cmd=d["verify_cmd"],
            exit_criteria=d["exit_criteria"],
            sensitivity=d.get("sensitivity", "low"),
            writes_files=list(d.get("writes_files", [])),
            logical_deps=list(d.get("logical_deps", [])),
        )


def validate_brief(d: dict) -> list[str]:
    """Return a list of human-readable errors. Empty list == valid."""
    errors: list[str] = []
    for key in _REQUIRED:
        if key not in d:
            errors.append(f"missing required key '{key}'")
    if "task_type" in d and d["task_type"] not in _VALID_TASK_TYPES:
        errors.append(f"invalid task_type '{d['task_type']}'")
    if "sensitivity" in d and d["sensitivity"] not in _VALID_SENSITIVITY:
        errors.append(f"invalid sensitivity '{d['sensitivity']}' (must be low|high)")
    if "contract" in d:
        if not isinstance(d["contract"], dict) or "produces" not in d["contract"] or "consumes" not in d["contract"]:
            errors.append("contract must be an object with 'produces' and 'consumes'")
    return errors
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest harness/tests/test_brief.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add harness/brief.py harness/tests/test_brief.py
git commit -m "feat(decompose): add SubtaskBrief dataclass + validator (REQ-D2)"
```

---

## Task 2: Producer→consumer DAG (`dag.py`)

**Files:**
- Create: `harness/dag.py`
- Test: `harness/tests/test_dag.py`

- [ ] **Step 1: Write the failing test**

Create `harness/tests/test_dag.py`:

```python
import pytest
from harness.dag import build_edges, topo_waves, writes_overlap, DagCycleError


def _b(uid, produces=None, consumes=None, logical_deps=None, writes=None):
    return {
        "id": uid,
        "contract": {"produces": produces or [], "consumes": consumes or []},
        "logical_deps": logical_deps or [],
        "writes_files": writes or [],
    }


def test_build_edges_links_consumer_to_producer():
    briefs = [_b("a", produces=["sym"]), _b("b", consumes=["sym"])]
    deps = build_edges(briefs)
    assert deps["b"] == {"a"}
    assert deps["a"] == set()


def test_build_edges_includes_logical_deps():
    briefs = [_b("a"), _b("b", logical_deps=["a"])]
    deps = build_edges(briefs)
    assert deps["b"] == {"a"}


def test_build_edges_ignores_self_produced_symbol():
    briefs = [_b("a", produces=["sym"], consumes=["sym"])]
    assert build_edges(briefs)["a"] == set()


def test_topo_waves_orders_producer_before_consumer():
    briefs = [_b("b", consumes=["sym"]), _b("a", produces=["sym"])]
    waves = topo_waves(build_edges(briefs))
    assert waves == [["a"], ["b"]]


def test_topo_waves_groups_independent_units_in_one_wave():
    briefs = [_b("a"), _b("b")]
    waves = topo_waves(build_edges(briefs))
    assert len(waves) == 1
    assert sorted(waves[0]) == ["a", "b"]


def test_topo_waves_raises_on_cycle():
    briefs = [_b("a", produces=["x"], consumes=["y"]), _b("b", produces=["y"], consumes=["x"])]
    with pytest.raises(DagCycleError):
        topo_waves(build_edges(briefs))


def test_writes_overlap_detects_shared_file():
    assert writes_overlap(_b("a", writes=["f.py"]), _b("b", writes=["f.py"])) is True
    assert writes_overlap(_b("a", writes=["f.py"]), _b("b", writes=["g.py"])) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest harness/tests/test_dag.py -v`
Expected: FAIL — `ModuleNotFoundError: harness.dag`.

- [ ] **Step 3: Write minimal implementation**

Create `harness/dag.py`:

```python
"""
Producer→consumer dependency DAG over SubtaskBriefs (REQ-D1, ADR-0011).
A consumer depends on whichever unit produces a symbol it consumes; logical_deps add
explicit edges even without a shared symbol. topo_waves layers the DAG into dispatch waves;
units in the same wave are mutually independent and may be co-dispatched.
"""


class DagCycleError(Exception):
    """Raised when the dependency graph contains a cycle (cannot be ordered)."""


def build_edges(briefs: list[dict]) -> dict[str, set[str]]:
    """unit_id -> set of unit_ids it depends on."""
    produced_by: dict[str, str] = {}
    for b in briefs:
        for sym in b["contract"].get("produces", []):
            produced_by[sym] = b["id"]

    deps: dict[str, set[str]] = {b["id"]: set() for b in briefs}
    for b in briefs:
        uid = b["id"]
        for sym in b["contract"].get("consumes", []):
            producer = produced_by.get(sym)
            if producer is not None and producer != uid:
                deps[uid].add(producer)
        for ld in b.get("logical_deps", []):
            if ld in deps and ld != uid:
                deps[uid].add(ld)
    return deps


def topo_waves(deps: dict[str, set[str]]) -> list[list[str]]:
    """Kahn layered topological sort. Each wave is a sorted list of mutually-independent unit ids."""
    remaining = {uid: set(d) for uid, d in deps.items()}
    waves: list[list[str]] = []
    while remaining:
        ready = sorted(uid for uid, d in remaining.items() if not d)
        if not ready:
            raise DagCycleError(f"cycle among: {sorted(remaining)}")
        waves.append(ready)
        for uid in ready:
            del remaining[uid]
        for d in remaining.values():
            d.difference_update(ready)
    return waves


def writes_overlap(a: dict, b: dict) -> bool:
    """True if two units write any common file (cannot safely co-dispatch). REQ NFR-PERF-2."""
    return bool(set(a.get("writes_files", [])) & set(b.get("writes_files", [])))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest harness/tests/test_dag.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add harness/dag.py harness/tests/test_dag.py
git commit -m "feat(decompose): add producer-consumer DAG with topo waves + file-overlap (REQ-D1)"
```

---

## Task 3: Plan lint (`lint_plan.py`)

**Files:**
- Create: `harness/lint_plan.py`
- Test: `harness/tests/test_lint_plan.py`

- [ ] **Step 1: Write the failing test**

Create `harness/tests/test_lint_plan.py`:

```python
from harness.lint_plan import lint_briefs


def _b(uid, produces=None, consumes=None, goal="do a thing", exit_criteria="tests pass"):
    return {
        "id": uid,
        "goal": goal,
        "exit_criteria": exit_criteria,
        "contract": {"produces": produces or [], "consumes": consumes or []},
    }


def test_clean_plan_has_no_errors():
    briefs = [_b("a", produces=["sym"]), _b("b", consumes=["sym"])]
    assert lint_briefs(briefs) == []


def test_flags_consumed_symbol_with_no_producer():
    briefs = [_b("b", consumes=["ghost"])]
    errs = lint_briefs(briefs)
    assert any("ghost" in e for e in errs)


def test_flags_placeholder_in_goal():
    briefs = [_b("a", goal="implement TODO later")]
    errs = lint_briefs(briefs)
    assert any("placeholder" in e.lower() for e in errs)


def test_flags_placeholder_in_exit_criteria():
    briefs = [_b("a", exit_criteria="TBD")]
    errs = lint_briefs(briefs)
    assert any("placeholder" in e.lower() for e in errs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest harness/tests/test_lint_plan.py -v`
Expected: FAIL — `ModuleNotFoundError: harness.lint_plan`.

- [ ] **Step 3: Write minimal implementation**

Create `harness/lint_plan.py`:

```python
"""
Deterministic pre-dispatch lint over a set of SubtaskBriefs (REQ-D3, ADR-0011).
Catches dangling consumed symbols (no upstream producer) and placeholder text. This is a
syntactic guard — it catches missing references, NOT wrong groupings (that residual is
bounded by the assembly golden gate, ADR-0004).
"""

_PLACEHOLDERS = ("TODO", "TBD", "FIXME", "XXX", "<placeholder>")
_SCANNED_FIELDS = ("goal", "exit_criteria")


def lint_briefs(briefs: list[dict]) -> list[str]:
    """Return human-readable lint errors. Empty list == clean (decomposition may proceed)."""
    errors: list[str] = []

    produced: set[str] = set()
    for b in briefs:
        produced.update(b["contract"].get("produces", []))

    for b in briefs:
        uid = b["id"]
        for sym in b["contract"].get("consumes", []):
            if sym not in produced:
                errors.append(f"{uid}: consumes '{sym}' but no unit produces it")
        for fieldname in _SCANNED_FIELDS:
            text = b.get(fieldname, "") or ""
            for ph in _PLACEHOLDERS:
                if ph in text:
                    errors.append(f"{uid}: placeholder '{ph}' found in {fieldname}")
    return errors
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest harness/tests/test_lint_plan.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add harness/lint_plan.py harness/tests/test_lint_plan.py
git commit -m "feat(decompose): add lint_plan symbol/placeholder check (REQ-D3)"
```

---

## Task 4: Codegraph adapter with degrade path (`codegraph_adapter.py`)

**Files:**
- Create: `harness/codegraph_adapter.py`
- Test: `harness/tests/test_codegraph_adapter.py`

**Concept:** the real codegraph comes from the codegraphcontext MCP, which is only available in a live session — not in unit tests. So the lookup is behind an injectable `query_fn`. When `query_fn` is `None` or raises, the adapter returns `{}` (no edges) and the caller falls back to `logical_deps`-only coupling (REQ-D4). The `query_fn` wiring to the actual MCP happens in the pipeline plan (Plan 3); this module just defines the contract + degrade.

- [ ] **Step 1: Write the failing test**

Create `harness/tests/test_codegraph_adapter.py`:

```python
from harness.codegraph_adapter import dependency_edges


def test_returns_empty_when_no_query_fn():
    assert dependency_edges(["a.py"], ".", query_fn=None) == {}


def test_uses_query_fn_when_provided():
    def fake(files, workdir):
        return {"foo": ["bar"]}
    assert dependency_edges(["a.py"], ".", query_fn=fake) == {"foo": ["bar"]}


def test_degrades_to_empty_on_query_error():
    def boom(files, workdir):
        raise RuntimeError("MCP down")
    assert dependency_edges(["a.py"], ".", query_fn=boom) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest harness/tests/test_codegraph_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError: harness.codegraph_adapter`.

- [ ] **Step 3: Write minimal implementation**

Create `harness/codegraph_adapter.py`:

```python
"""
Codegraph dependency lookup with an explicit degrade path (REQ-D4, ADR-0011).

The real source is the codegraphcontext MCP, available only in a live session. It is injected
as `query_fn(files, workdir) -> dict[str, list[str]]` so this module stays unit-testable and the
MCP-absent / MCP-error path is explicit: return {} → caller falls back to logical_deps-only.
Wiring query_fn to the live MCP happens in the pipeline plan.
"""
from typing import Callable, Optional

QueryFn = Callable[[list, str], dict]


def dependency_edges(files: list[str], workdir: str, query_fn: Optional[QueryFn] = None) -> dict[str, list[str]]:
    """symbol -> list of symbols it depends on. {} means 'no graph available' (degrade)."""
    if query_fn is None:
        return {}
    try:
        result = query_fn(files, workdir)
    except Exception:
        return {}
    return result if isinstance(result, dict) else {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest harness/tests/test_codegraph_adapter.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add harness/codegraph_adapter.py harness/tests/test_codegraph_adapter.py
git commit -m "feat(decompose): add codegraph adapter with degrade path (REQ-D4)"
```

---

## Task 5: Decomposition orchestration (`decompose.py`)

**Files:**
- Create: `harness/decompose.py`
- Test: `harness/tests/test_decompose.py`

**Concept:** ties the pieces together as the HARD GATE (REQ-D5): validate every brief, run lint, and only if both are clean produce the ordered dispatch waves. Any validation or lint failure raises `DecompositionError` — nothing dispatches.

- [ ] **Step 1: Write the failing test**

Create `harness/tests/test_decompose.py`:

```python
import pytest
from harness.decompose import decompose, DecompositionError

A = {
    "id": "a", "goal": "produce parser", "task_type": "code_gen", "files": ["p.py"],
    "context_slices": [], "contract": {"produces": ["parse"], "consumes": []},
    "verify_cmd": "pytest", "exit_criteria": "parse works", "sensitivity": "low",
}
B = {
    "id": "b", "goal": "use parser", "task_type": "code_edit", "files": ["m.py"],
    "context_slices": [], "contract": {"produces": [], "consumes": ["parse"]},
    "verify_cmd": "pytest", "exit_criteria": "main uses parse", "sensitivity": "low",
}


def test_decompose_returns_ordered_waves():
    waves = decompose([B, A])  # deliberately out of order
    assert waves == [["a"], ["b"]]


def test_decompose_raises_on_invalid_brief():
    bad = {k: v for k, v in A.items() if k != "verify_cmd"}
    with pytest.raises(DecompositionError) as ei:
        decompose([bad])
    assert any("verify_cmd" in e for e in ei.value.errors)


def test_decompose_raises_on_lint_failure():
    ghost = {**B, "contract": {"produces": [], "consumes": ["nonexistent"]}}
    with pytest.raises(DecompositionError) as ei:
        decompose([ghost])
    assert any("nonexistent" in e for e in ei.value.errors)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest harness/tests/test_decompose.py -v`
Expected: FAIL — `ModuleNotFoundError: harness.decompose`.

- [ ] **Step 3: Write minimal implementation**

Create `harness/decompose.py`:

```python
"""
Decomposition hard gate (REQ-D5, ADR-0011). Validates briefs, lints the plan, and only on a
clean result returns the topologically-ordered dispatch waves. Any failure raises
DecompositionError carrying all errors — nothing dispatches until decomposition is clean.

logical_deps + produces/consumes drive the DAG (REQ-D1). Codegraph edges, when available, are a
hint the orchestrator folds into logical_deps upstream; this module is deterministic given briefs.
"""
from harness.brief import validate_brief
from harness.lint_plan import lint_briefs
from harness.dag import build_edges, topo_waves


class DecompositionError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def decompose(briefs: list[dict]) -> list[list[str]]:
    """Return ordered dispatch waves (list of lists of unit ids). Raise DecompositionError on any gate failure."""
    errors: list[str] = []
    for b in briefs:
        for e in validate_brief(b):
            errors.append(f"{b.get('id', '?')}: {e}")
    if errors:
        raise DecompositionError(errors)

    lint_errors = lint_briefs(briefs)
    if lint_errors:
        raise DecompositionError(lint_errors)

    return topo_waves(build_edges(briefs))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest harness/tests/test_decompose.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add harness/decompose.py harness/tests/test_decompose.py
git commit -m "feat(decompose): add decomposition hard gate tying validate+lint+DAG (REQ-D5)"
```

---

## Task 6: Final verification

**Files:** none

- [ ] **Step 1: Run the full suite**

Run: `python3 -m pytest -q`
Expected: all prior tests + the new decomposition tests pass; still exactly 3 pre-existing `openai`-missing failures, no new failures.

- [ ] **Step 2: Smoke the decomposition end-to-end**

Run:
```bash
python3 -c "
from harness.decompose import decompose
A={'id':'a','goal':'g','task_type':'code_gen','files':['p.py'],'context_slices':[],'contract':{'produces':['parse'],'consumes':[]},'verify_cmd':'pytest','exit_criteria':'ok','sensitivity':'low'}
B={'id':'b','goal':'g','task_type':'code_edit','files':['m.py'],'context_slices':[],'contract':{'produces':[],'consumes':['parse']},'verify_cmd':'pytest','exit_criteria':'ok','sensitivity':'low'}
print('waves:', decompose([B, A]))
"
```
Expected: `waves: [['a'], ['b']]`

- [ ] **Step 3: Commit any touch-ups** (only if needed)

```bash
git add -A && git commit -m "test: S12 decomposition core green"
```

---

## Notes for the next plan (Plan 3 — pipeline + orchestrator gate)
- Wire the live codegraphcontext MCP as the `query_fn` for `dependency_edges`; fold returned edges into `logical_deps` during brief authoring.
- Build `orchestrator_gate.py` (REQ-O2/O3): RED-validate orchestrator-authored acceptance tests against HEAD + 2nd-model DAG/contract review.
- Add phase-boundary compaction; wire `cost_skip` → `decompose` → wave dispatch into `orchestrate`.
- `lint_plan` currently flags consumes with no in-plan producer; extend to allow an explicit "external/pre-existing symbol" allowlist so units that legitimately consume existing repo symbols aren't false-flagged.
