# Conductor Pipeline Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Wire the built spine end-to-end — `decompose` (S12) → `verify` (ADR-0022, advisory) → per-wave [`cost_skip` (S5) → dispatch → harness-derived tracking] — into one `run_dag` orchestrator, building `verify.py` and a minimal event-sourced tracker as part of it, with every external/unbuilt piece (per-unit TDD gates, role-model router, codegraph source, full pluggable tracker, per-wave re-verify) behind an injectable seam so the whole thing is unit-testable with fakes.

**Architecture:** `run_dag` is pure orchestration: it calls the built modules and delegates per-unit work to an injected `process_unit` (default adapter wraps the existing `run_pipeline`). Roles are model-assignments in isolated context (ADR-0024) — the pipeline takes an injected `role_router`; the invariant it enforces is that each unit is processed from its own `SubtaskBrief`, never the main-thread history. `verify` is advisory (warn + annotate) at decompose-time per ADR-0022/REQ-D9. The tracker records only harness-derived states (NFR-TRACK-1).

**Tech Stack:** Python 3.11+, `python3 -m pytest` (the homebrew shim is broken), stdlib only.

**Requirements:** REQ-D6/D7/D8/D9 (verify), REQ-OBS5/OBS7 (tracker slice), REQ-RM2/RM3 (context isolation + optimize-at-paid-reader), REQ-R1 (cost_skip wired), REQ-I2 (assembly is the backstop — noted). ADR-0022, ADR-0023 (slice), ADR-0024. Branch `feat/conductor-distributed-build`. Baseline 158 pass / 3 pre-existing `openai`-missing fails — add no new failures. No Co-Authored-By lines.

**Scope / seams (honest):** Built here = `verify.py`, minimal `tracker`, `run_brief` adapter, `run_dag`. Reused = `decompose`, `cost_skip`, `optimize`, `run_pipeline`. **Seams (injected, NOT built here):** the per-unit TDD gate sequence (RED/GREEN/mutation — default `process_unit` uses the existing `run_pipeline`/evaluator), the live codegraph source (default `None` → verify declaration-only), the `role_model_policy` resolver (default trivial), per-wave re-index re-verify (REQ-D9 — the hook exists; the live re-index is deferred), full pluggable render sinks (Plan T).

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `harness/verify.py` | codegraph-backed contract verifier (advisory) — ADR-0022 | Create |
| `harness/tracker.py` | minimal event-sourced board (record/board/render_text) — ADR-0023 slice | Create |
| `harness/run_brief.py` | `brief_to_subtask` + `brief_to_messages` adapters | Create |
| `harness/run_dag.py` | the `run_dag` orchestrator wiring everything | Create |
| `harness/tests/test_verify.py` / `test_tracker.py` / `test_run_brief.py` / `test_run_dag.py` | tests | Create |

---

## Task 1: `verify.py` — codegraph-backed contract verifier (advisory)

**Files:** Create `harness/verify.py`, `harness/tests/test_verify.py`.

- [ ] **Step 1: Write the failing test** — create `harness/tests/test_verify.py`:

```python
from harness.verify import verify_decomposition, VerifyReport


def _b(uid, produces=None, consumes=None, files=None):
    return {"id": uid, "files": files or [], "writes_files": files or [],
            "contract": {"produces": produces or [], "consumes": consumes or []}}


def test_clean_when_no_codegraph_returns_unverified():
    briefs = [_b("a", produces=["x"]), _b("b", consumes=["x"])]
    rep = verify_decomposition(briefs, edges=None)
    assert rep.status == "unverified"     # degrade-clean (REQ-D4)
    assert rep.errors == []


def test_under_declared_edge_is_flagged_when_codegraph_present():
    # codegraph says b's file references symbol 'x' (owned/produced by a), but b didn't declare consumes
    briefs = [_b("a", produces=["x"], files=["a.py"]), _b("b", consumes=[], files=["b.py"])]
    edges = {"b.py": ["x"]}   # b.py references symbol x
    rep = verify_decomposition(briefs, edges=edges)
    assert rep.status == "verified"
    assert any("b" in e and "x" in e for e in rep.warnings + rep.errors)


def test_over_declared_consume_is_a_warning():
    briefs = [_b("a", produces=["x"], files=["a.py"]), _b("b", consumes=["x"], files=["b.py"])]
    edges = {"b.py": []}      # b.py does NOT actually reference x
    rep = verify_decomposition(briefs, edges=edges)
    assert any("over-declared" in w.lower() and "x" in w for w in rep.warnings)


def test_coverage_metric_present():
    briefs = [_b("a", produces=["x"], files=["a.py"]), _b("b", consumes=["x"], files=["b.py"])]
    edges = {"b.py": ["x"]}
    rep = verify_decomposition(briefs, edges=edges)
    assert 0.0 <= rep.coverage <= 1.0


def test_density_signal_flags_dense_graph():
    # 3 units all consuming each other's produces -> dense
    briefs = [
        _b("a", produces=["pa"], consumes=["pb", "pc"]),
        _b("b", produces=["pb"], consumes=["pa", "pc"]),
        _b("c", produces=["pc"], consumes=["pa", "pb"]),
    ]
    rep = verify_decomposition(briefs, edges=None)
    assert rep.dense is True
```

- [ ] **Step 2: Run** `python3 -m pytest harness/tests/test_verify.py -v` → FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement** — create `harness/verify.py`:

```python
"""
Codegraph-backed decomposition verifier (ADR-0022, REQ-D6/D7/D8). ADVISORY and degrade-clean:
when no codegraph edges are supplied, returns status 'unverified' (declaration-only) and the
build proceeds on the lint-only gate. Never mutates the DAG. Bounded by static-analysis accuracy.

`edges` maps a file path -> list of symbols that file actually references (from codegraph).
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VerifyReport:
    status: str = "unverified"          # "unverified" (no codegraph) | "verified"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    coverage: float = 0.0               # % of declared consumes corroborated by codegraph
    dense: bool = False                 # advisory decomposability signal (REQ-D8)


_DENSITY_RATIO = 0.6   # edges / (n*(n-1)); above this the graph is "dense" (tunable, design §7)


def _producer_of(briefs: list[dict]) -> dict[str, str]:
    owner: dict[str, str] = {}
    for b in briefs:
        for sym in b["contract"].get("produces", []):
            owner[sym] = b["id"]
    return owner


def _density(briefs: list[dict]) -> bool:
    n = len(briefs)
    if n < 2:
        return False
    edge_count = 0
    produced = _producer_of(briefs)
    for b in briefs:
        for sym in b["contract"].get("consumes", []):
            if produced.get(sym) not in (None, b["id"]):
                edge_count += 1
    return (edge_count / (n * (n - 1))) >= _DENSITY_RATIO


def verify_decomposition(briefs: list[dict], edges: Optional[dict] = None) -> VerifyReport:
    rep = VerifyReport(dense=_density(briefs))
    if edges is None:
        rep.status = "unverified"
        return rep

    rep.status = "verified"
    produced = _producer_of(briefs)

    declared_total = 0
    corroborated = 0
    for b in briefs:
        uid = b["id"]
        declared = set(b["contract"].get("consumes", []))
        referenced: set[str] = set()
        for f in b.get("files", []):
            referenced.update(edges.get(f, []))

        # under-declared: a referenced symbol owned by ANOTHER unit, not in declared consumes
        for sym in referenced:
            owner = produced.get(sym)
            if owner is not None and owner != uid and sym not in declared:
                rep.warnings.append(f"{uid}: references '{sym}' (produced by {owner}) but does not declare consumes it (under-declared edge)")

        # over-declared: declared consume never actually referenced
        for sym in declared:
            declared_total += 1
            if sym in referenced:
                corroborated += 1
            else:
                rep.warnings.append(f"{uid}: over-declared consume '{sym}' (never referenced in its files)")

    rep.coverage = (corroborated / declared_total) if declared_total else 1.0
    return rep
```

- [ ] **Step 4: Run** `python3 -m pytest harness/tests/test_verify.py -v` → PASS (5).
- [ ] **Step 5: Commit** — `git add harness/verify.py harness/tests/test_verify.py && git commit -m "feat(verify): codegraph-backed decomposition verifier (advisory, degrade-clean) — ADR-0022 REQ-D6/D7/D8"`

---

## Task 2: `tracker.py` — minimal event-sourced board (harness-derived)

**Files:** Create `harness/tracker.py`, `harness/tests/test_tracker.py`.

- [ ] **Step 1: Write the failing test** — create `harness/tests/test_tracker.py`:

```python
from harness.tracker import Tracker, UnitState


def test_record_and_board_projection():
    t = Tracker()
    t.record("u1", UnitState.DISPATCHED, maker="gemma4")
    t.record("u1", UnitState.ACCEPTED, score=82)
    t.record("u2", UnitState.FAILED, score=10)
    board = t.board()
    assert board["u1"]["state"] == "ACCEPTED"
    assert board["u1"]["score"] == 82
    assert board["u2"]["state"] == "FAILED"


def test_board_is_projection_latest_wins():
    t = Tracker()
    t.record("u1", UnitState.PENDING)
    t.record("u1", UnitState.DISPATCHED)
    assert t.board()["u1"]["state"] == "DISPATCHED"


def test_events_are_append_only_history():
    t = Tracker()
    t.record("u1", UnitState.DISPATCHED)
    t.record("u1", UnitState.HEALING, attempt=1)
    t.record("u1", UnitState.ACCEPTED)
    states = [e.state for e in t.events if e.unit_id == "u1"]
    assert states == ["DISPATCHED", "HEALING", "ACCEPTED"]   # full attempt history preserved (REQ-OBS7)


def test_render_text_contains_units_and_states():
    t = Tracker()
    t.record("u1", UnitState.ACCEPTED, score=90)
    out = t.render_text()
    assert "u1" in out and "ACCEPTED" in out


def test_rollup_counts():
    t = Tracker()
    t.record("u1", UnitState.ACCEPTED)
    t.record("u2", UnitState.FAILED)
    t.record("u3", UnitState.ACCEPTED)
    r = t.rollup()
    assert r["ACCEPTED"] == 2 and r["FAILED"] == 1
```

- [ ] **Step 2: Run** `python3 -m pytest harness/tests/test_tracker.py -v` → FAIL.

- [ ] **Step 3: Implement** — create `harness/tracker.py`:

```python
"""
Minimal event-sourced development board (ADR-0023 slice; REQ-OBS5/OBS7). Board is a pure
projection over an append-only event log. Progress is HARNESS-DERIVED (NFR-TRACK-1): the caller
records a state only from a harness fact (dispatch happened, gate passed) — never a maker claim.
Full pluggable render sinks (rich/MCP/webhook/external-PM) are deferred to the tracker plan.
"""
from dataclasses import dataclass, field
from typing import Any


class UnitState:
    PENDING = "PENDING"
    READY = "READY"
    DISPATCHED = "DISPATCHED"
    HEALING = "HEALING"
    ESCALATED = "ESCALATED"
    INTERVENE = "INTERVENE"
    INLINE = "INLINE"
    ACCEPTED = "ACCEPTED"
    FAILED = "FAILED"


@dataclass
class Event:
    unit_id: str
    state: str
    meta: dict[str, Any] = field(default_factory=dict)


class Tracker:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def record(self, unit_id: str, state: str, **meta: Any) -> None:
        self.events.append(Event(unit_id=unit_id, state=state, meta=meta))

    def board(self) -> dict[str, dict[str, Any]]:
        """Latest-state projection per unit (for the orchestrator/system-leader view)."""
        out: dict[str, dict[str, Any]] = {}
        for e in self.events:
            out[e.unit_id] = {"state": e.state, **e.meta}
        return out

    def rollup(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for unit, info in self.board().items():
            counts[info["state"]] = counts.get(info["state"], 0) + 1
        return counts

    def render_text(self) -> str:
        """Human program-manager view (stdlib, baked-in sink)."""
        lines = ["unit                 state         detail"]
        for unit, info in sorted(self.board().items()):
            detail = " ".join(f"{k}={v}" for k, v in info.items() if k != "state")
            lines.append(f"{unit:<20} {info['state']:<13} {detail}")
        roll = self.rollup()
        lines.append("rollup: " + " ".join(f"{k}={v}" for k, v in sorted(roll.items())))
        return "\n".join(lines)
```

- [ ] **Step 4: Run** `python3 -m pytest harness/tests/test_tracker.py -v` → PASS (5).
- [ ] **Step 5: Commit** — `git add harness/tracker.py harness/tests/test_tracker.py && git commit -m "feat(tracker): minimal event-sourced board, harness-derived (ADR-0023 slice REQ-OBS5/OBS7)"`

---

## Task 3: `run_brief.py` — brief→subtask / brief→messages adapters

**Files:** Create `harness/run_brief.py`, `harness/tests/test_run_brief.py`.

- [ ] **Step 1: Write the failing test** — create `harness/tests/test_run_brief.py`:

```python
from harness.models import TaskType
from harness.run_brief import brief_to_subtask, brief_to_messages

BRIEF = {
    "id": "u1", "goal": "add type hints to f", "task_type": "code_edit",
    "files": ["m.py"], "writes_files": ["m.py"], "context_slices": [],
    "contract": {"produces": ["f"], "consumes": []},
    "verify_cmd": "pytest", "exit_criteria": "f annotated", "sensitivity": "low",
}


def test_brief_to_subtask_maps_fields():
    st = brief_to_subtask(BRIEF, workdir=".")
    assert st.id == "u1"
    assert st.type == TaskType.CODE_EDIT
    assert st.files == ["m.py"]
    assert st.sensitivity == "low"


def test_brief_to_subtask_estimates_tokens_when_absent():
    st = brief_to_subtask(BRIEF, workdir=".")
    assert isinstance(st.estimated_tokens, int)


def test_brief_to_messages_has_system_and_user_roles():
    msgs = brief_to_messages(BRIEF)
    roles = [m["role"] for m in msgs]
    assert "system" in roles and "user" in roles
    assert any("add type hints to f" in m["content"] for m in msgs)
```

- [ ] **Step 2: Run** `python3 -m pytest harness/tests/test_run_brief.py -v` → FAIL.

- [ ] **Step 3: Implement** — create `harness/run_brief.py`:

```python
"""
Adapters between a SubtaskBrief (dict) and the harness's existing types (ADR-0024 — a brief is
the bounded context a role-instance runs from). brief_to_subtask feeds cost_skip/router/run_pipeline;
brief_to_messages builds the message list the optimizer + a (paid) role model would read.
"""
from typing import Any

from harness.models import SubTask, TaskType
from harness.tokens import estimate_tokens


def brief_to_subtask(brief: dict[str, Any], workdir: str = ".") -> SubTask:
    est = int(brief.get("estimated_tokens") or estimate_tokens(brief.get("files", []), workdir))
    return SubTask(
        id=brief["id"],
        description=brief["goal"],
        type=TaskType(brief["task_type"]),
        files=list(brief.get("files", [])),
        estimated_tokens=est,
        sensitivity=brief.get("sensitivity", "low"),
        writes_files=list(brief.get("writes_files", [])),
        produces=list(brief["contract"].get("produces", [])),
        consumes=list(brief["contract"].get("consumes", [])),
        logical_deps=list(brief.get("logical_deps", [])),
    )


def brief_to_messages(brief: dict[str, Any]) -> list[dict[str, str]]:
    """Bounded context for a role model: a system instruction + the unit brief as a user message."""
    contract = brief.get("contract", {})
    system = (
        "You are a bounded maker. Do ONLY this unit from its brief. "
        f"Exit criteria: {brief.get('exit_criteria', '')}"
    )
    user = (
        f"Goal: {brief['goal']}\n"
        f"Files: {', '.join(brief.get('files', []))}\n"
        f"Produces: {', '.join(contract.get('produces', []))}\n"
        f"Consumes: {', '.join(contract.get('consumes', []))}\n"
        f"Verify: {brief.get('verify_cmd', '')}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
```

- [ ] **Step 4: Run** `python3 -m pytest harness/tests/test_run_brief.py -v` → PASS (3).
- [ ] **Step 5: Commit** — `git add harness/run_brief.py harness/tests/test_run_brief.py && git commit -m "feat(pipeline): brief->subtask / brief->messages adapters (ADR-0024)"`

---

## Task 4: `run_dag.py` — the integration orchestrator

**Files:** Create `harness/run_dag.py`, `harness/tests/test_run_dag.py`.

- [ ] **Step 1: Write the failing test** — create `harness/tests/test_run_dag.py`:

```python
from harness.run_dag import run_dag, DagRunResult
from harness.tracker import UnitState

A = {"id": "a", "goal": "produce parser", "task_type": "code_gen", "files": ["p.py"],
     "writes_files": ["p.py"], "context_slices": [], "contract": {"produces": ["parse"], "consumes": []},
     "verify_cmd": "pytest", "exit_criteria": "ok", "sensitivity": "low", "estimated_tokens": 5000}
B = {"id": "b", "goal": "use parser", "task_type": "code_edit", "files": ["m.py"],
     "writes_files": ["m.py"], "context_slices": [], "contract": {"produces": [], "consumes": ["parse"]},
     "verify_cmd": "pytest", "exit_criteria": "ok", "sensitivity": "low", "estimated_tokens": 5000}


class _FakeVerdict:
    def __init__(self, score, agent="gemma4"):
        self.final_score = score
        self.agent_used = agent
        self.routed_to_claude = False


def test_run_dag_processes_units_in_wave_order_and_tracks():
    seen = []
    def fake_process(subtask, workdir):
        seen.append(subtask.id)
        return _FakeVerdict(85)
    res = run_dag([B, A], workdir=".", process_unit=fake_process)
    assert seen == ["a", "b"]                       # topo order (a before b)
    assert res.board["a"]["state"] == UnitState.ACCEPTED
    assert res.board["b"]["state"] == UnitState.ACCEPTED
    assert res.accepted == 2


def test_run_dag_marks_failed_below_threshold():
    def fake_process(subtask, workdir):
        return _FakeVerdict(40)
    res = run_dag([A], workdir=".", process_unit=fake_process)
    assert res.board["a"]["state"] == UnitState.FAILED
    assert res.failed == 1


def test_run_dag_cost_skips_tiny_unit_to_inline():
    tiny = {**A, "id": "t", "estimated_tokens": 100}
    called = []
    def fake_process(subtask, workdir):
        called.append(subtask.id)
        return _FakeVerdict(90)
    res = run_dag([tiny], workdir=".", process_unit=fake_process)
    assert res.board["t"]["state"] == UnitState.INLINE
    assert "t" not in called                         # tiny unit never dispatched (cost_skip)


def test_run_dag_raises_clean_on_bad_decomposition():
    import pytest
    from harness.decompose import DecompositionError
    ghost = {**B, "contract": {"produces": [], "consumes": ["nonexistent"]}}
    with pytest.raises(DecompositionError):
        run_dag([ghost], workdir=".", process_unit=lambda s, w: _FakeVerdict(90))


def test_run_dag_attaches_verify_report():
    res = run_dag([A, B], workdir=".", process_unit=lambda s, w: _FakeVerdict(90))
    assert res.verify.status == "unverified"         # no codegraph supplied -> degrade-clean
```

- [ ] **Step 2: Run** `python3 -m pytest harness/tests/test_run_dag.py -v` → FAIL.

- [ ] **Step 3: Implement** — create `harness/run_dag.py`:

```python
"""
run_dag — the integration orchestrator (ADR-0011/0022/0023/0024). Wires the built spine:
decompose (hard gate) -> verify (advisory) -> per-wave [cost_skip -> dispatch -> harness-derived tracking].

process_unit(subtask, workdir) -> verdict  is INJECTED. Default wraps the existing run_pipeline
(full provider engine). Tests inject a fake. codegraph `edges` default None -> verify is
declaration-only (degrade-clean). Roles are model-assignments in isolated context (ADR-0024):
each unit is processed from its own brief, never the main-thread history.

SEAMS (not built here): per-unit TDD gate sequence (RED/GREEN/mutation — lives inside process_unit),
role_model_policy resolver, per-wave codegraph re-index re-verify (REQ-D9), full pluggable tracker sinks.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from harness.decompose import decompose
from harness.verify import verify_decomposition, VerifyReport
from harness.router import cost_skip
from harness.run_brief import brief_to_subtask
from harness.tracker import Tracker, UnitState
from harness.models import AgentType

ProcessUnit = Callable[[Any, str], Any]   # (SubTask, workdir) -> verdict with .final_score/.routed_to_claude


@dataclass
class DagRunResult:
    waves: list[list[str]]
    board: dict[str, dict[str, Any]]
    verify: VerifyReport
    accepted: int = 0
    failed: int = 0
    inline: int = 0
    verdicts: dict[str, Any] = field(default_factory=dict)


def _default_process_unit(subtask: Any, workdir: str) -> Any:
    from harness.pipeline import run_pipeline   # lazy: avoids importing the live engine in tests
    return run_pipeline(subtask, workdir=workdir)


def run_dag(
    briefs: list[dict],
    workdir: str = ".",
    *,
    process_unit: Optional[ProcessUnit] = None,
    tracker: Optional[Tracker] = None,
    edges: Optional[dict] = None,
    accept_threshold: int = 70,
) -> DagRunResult:
    process_unit = process_unit or _default_process_unit
    tracker = tracker or Tracker()

    waves = decompose(briefs)                      # S12 hard gate (raises DecompositionError)
    report = verify_decomposition(briefs, edges=edges)   # ADR-0022 advisory; degrade-clean when edges None
    by_id = {b["id"]: b for b in briefs}

    accepted = failed = inline = 0
    verdicts: dict[str, Any] = {}
    for wave in waves:
        for uid in wave:
            brief = by_id[uid]
            st = brief_to_subtask(brief, workdir)
            if cost_skip(st) == AgentType.CLAUDE_INLINE:    # S5 ROI meta-gate
                tracker.record(uid, UnitState.INLINE)
                inline += 1
                continue
            tracker.record(uid, UnitState.DISPATCHED)
            verdict = process_unit(st, workdir)
            verdicts[uid] = verdict
            if getattr(verdict, "routed_to_claude", False):
                tracker.record(uid, UnitState.INLINE, escalated=True)
                inline += 1
            elif getattr(verdict, "final_score", 0) >= accept_threshold:
                tracker.record(uid, UnitState.ACCEPTED, score=verdict.final_score, maker=getattr(verdict, "agent_used", "?"))
                accepted += 1
            else:
                tracker.record(uid, UnitState.FAILED, score=getattr(verdict, "final_score", 0))
                failed += 1
        # SEAM (REQ-D9): re-index codegraph on this wave's accrued GREEN code, re-verify next wave.

    return DagRunResult(
        waves=waves, board=tracker.board(), verify=report,
        accepted=accepted, failed=failed, inline=inline, verdicts=verdicts,
    )
```

- [ ] **Step 4: Run** `python3 -m pytest harness/tests/test_run_dag.py -v` → PASS (5).
- [ ] **Step 5: Run full suite** `python3 -m pytest -q` → expect prior + new pass; 3 pre-existing fails only.
- [ ] **Step 6: Commit** — `git add harness/run_dag.py harness/tests/test_run_dag.py && git commit -m "feat(pipeline): run_dag integration — decompose+verify+cost_skip+dispatch+tracker (ADR-0011/0022/0023/0024)"`

---

## Task 5: Final verification + smoke

- [ ] **Step 1: Full suite** — `python3 -m pytest -q` → green except the 3 pre-existing `openai`-missing fails.
- [ ] **Step 2: End-to-end smoke with a fake maker** — run:
```bash
python3 -c "
from harness.run_dag import run_dag
A={'id':'a','goal':'produce parser','task_type':'code_gen','files':['p.py'],'writes_files':['p.py'],'context_slices':[],'contract':{'produces':['parse'],'consumes':[]},'verify_cmd':'pytest','exit_criteria':'ok','sensitivity':'low','estimated_tokens':5000}
B={'id':'b','goal':'use parser','task_type':'code_edit','files':['m.py'],'writes_files':['m.py'],'context_slices':[],'contract':{'produces':[],'consumes':['parse']},'verify_cmd':'pytest','exit_criteria':'ok','sensitivity':'low','estimated_tokens':5000}
class V:
    def __init__(s,sc): s.final_score=sc; s.agent_used='gemma4'; s.routed_to_claude=False
res=run_dag([B,A], process_unit=lambda st,w: V(88))
print('waves:', res.waves)
print('accepted/failed/inline:', res.accepted, res.failed, res.inline)
from harness.tracker import Tracker
"
```
Expected: `waves: [['a'], ['b']]`, `accepted/failed/inline: 2 0 0`.
- [ ] **Step 3: Commit any touch-ups** (only if needed).

---

## Notes for follow-on plans
- Replace the default `process_unit` with the full TDD gate sequence (RED→author-sep→impl→GREEN→mutation) once those gates exist.
- Wire a live `edges` provider (codegraphcontext MCP) + per-wave re-index re-verify (REQ-D9).
- Add the `role_model_policy` resolver (ADR-0024) so each role-instance gets its model by capability×cost×availability; log the choice (REQ-RM3).
- Apply `optimize()` on paid-model role briefs + orchestrator-facing verdict text (REQ-RM3); promote the minimal `Tracker` to the full pluggable-sink `tracker/` package (Plan T).
