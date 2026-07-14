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
    assert seen == ["a", "b"]
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
    assert "t" not in called


def test_run_dag_raises_clean_on_bad_decomposition():
    import pytest
    from harness.decompose import DecompositionError
    ghost = {**B, "contract": {"produces": [], "consumes": ["nonexistent"]}}
    with pytest.raises(DecompositionError):
        run_dag([ghost], workdir=".", process_unit=lambda s, w: _FakeVerdict(90))


def test_run_dag_attaches_verify_report():
    res = run_dag([A, B], workdir=".", process_unit=lambda s, w: _FakeVerdict(90))
    assert res.verify.status == "unverified"


def test_run_dag_routed_to_claude_marks_inline_escalated():
    class _Escalated:
        final_score = -1
        agent_used = "claude_agent"
        routed_to_claude = True
    res = run_dag([A], workdir=".", process_unit=lambda s, w: _Escalated())
    assert res.board["a"]["state"] == UnitState.INLINE
    assert res.board["a"].get("escalated") is True
    assert res.inline == 1


def test_run_dag_merge_queue_finalizes_ff_when_clean():
    from harness.merge_queue import MergeQueue
    mq = MergeQueue(suite_runner=lambda: (True, ""), merger=lambda u: (True, ""))
    res = run_dag([A], workdir=".", process_unit=lambda s, w: _FakeVerdict(90), merge_queue=mq)
    assert res.assembly == "ff_to_target"
    assert res.accepted == 1


def test_run_dag_merge_queue_discards_on_suite_regression():
    from harness.merge_queue import MergeQueue
    mq = MergeQueue(suite_runner=lambda: (False, "sibling broke"), merger=lambda u: (True, ""))
    res = run_dag([A], workdir=".", process_unit=lambda s, w: _FakeVerdict(90), merge_queue=mq)
    assert res.assembly == "discard"      # merge-queue full-suite caught a regression a per-unit gate missed
    assert res.accepted == 0 and res.failed == 1


def test_run_dag_reverify_runs_at_wave_boundary():
    calls = {"n": 0}
    def rv(by_id, accepted):
        calls["n"] += 1
        from harness.verify import VerifyReport
        return VerifyReport(status="verified")
    res = run_dag([B, A], workdir=".", process_unit=lambda s, w: _FakeVerdict(90), reverify=rv)
    assert calls["n"] == 2            # two waves -> two boundary re-verifies
    assert res.verify.status == "verified"


def test_run_dag_fail_fast_aborts_remaining_waves():
    seen = []
    def proc(st, w):
        seen.append(st.id)
        return _FakeVerdict(10)   # everything fails
    # B depends on A; fail_fast should stop after A fails, never dispatch B
    res = run_dag([B, A], workdir=".", process_unit=proc, failure_mode="fail_fast")
    assert seen == ["a"]                # B never dispatched
    assert res.assembly == "discard"


def test_run_dag_all_or_nothing_discards_on_any_failure():
    def proc(st, w):
        return _FakeVerdict(90) if st.id == "a" else _FakeVerdict(10)
    res = run_dag([A, B], workdir=".", process_unit=proc, failure_mode="all_or_nothing")
    assert res.failed == 1
    assert res.assembly == "discard"    # one failure discards the whole build


def test_run_dag_best_of_n_gate_selects_first_passing_candidate():
    # first candidate fails the gate, second passes -> gate selects the second (no vote)
    scores = iter([30, 88])
    def proc(st, w):
        return _FakeVerdict(next(scores))
    res = run_dag([A], workdir=".", process_unit=proc, best_of_n=lambda b: 3)
    assert res.board["a"]["state"] == UnitState.ACCEPTED
    assert res.board["a"]["candidates"] == 2      # stopped at first pass, didn't exhaust N=3
    assert res.accepted == 1


def test_run_dag_best_of_n_fails_when_no_candidate_passes():
    def proc(st, w):
        return _FakeVerdict(20)
    res = run_dag([A], workdir=".", process_unit=proc, best_of_n=lambda b: 3)
    assert res.board["a"]["state"] == UnitState.FAILED
    assert res.failed == 1


def test_run_dag_best_of_n_default_is_single_maker():
    calls = []
    def proc(st, w):
        calls.append(st.id)
        return _FakeVerdict(90)
    res = run_dag([A], workdir=".", process_unit=proc)   # no best_of_n -> N=1
    assert calls == ["a"]
    assert res.board["a"]["candidates"] == 1


def test_run_dag_best_of_n_records_each_candidate_confidence():
    from harness.confidence import ConfidenceStore
    conf = ConfidenceStore()
    seq = iter([_FakeVerdict(20, "gemma4"), _FakeVerdict(20, "gemma4"), _FakeVerdict(90, "gemini")])
    res = run_dag([A], workdir=".", process_unit=lambda s, w: next(seq),
                  best_of_n=lambda b: 3, confidence=conf)
    assert res.accepted == 1
    # both failing gemma4 candidates AND the winning gemini candidate are recorded (not just the last)
    assert conf.samples("gemma4", A["task_type"]) == 2
    assert conf.samples("gemini", A["task_type"]) == 1


def test_run_dag_wave_atomic_does_not_count_resumed_wave_as_landed():
    from harness.merge_queue import MergeQueue
    from harness.checkpoint import make_checkpoint
    mq = MergeQueue(suite_runner=lambda: (True, ""), merger=lambda u: (True, ""))
    ckpt = make_checkpoint({"a": {"state": "ACCEPTED"}})
    # wave 'a' is resumed (nothing merged this run); only 'b' actually lands
    res = run_dag([B, A], workdir=".", process_unit=lambda s, w: _FakeVerdict(90),
                  merge_queue=mq, resume_from=ckpt)
    assert res.landed_waves == 1          # not 2 — resumed wave merged nothing
    assert res.assembly == "ff_to_target"


def test_run_dag_wave_atomic_inline_only_wave_not_counted_landed():
    from harness.merge_queue import MergeQueue
    mq = MergeQueue(suite_runner=lambda: (True, ""), merger=lambda u: (True, ""))
    tiny = {**A, "id": "t", "estimated_tokens": 100}   # cost-skipped to inline, never merged
    res = run_dag([tiny], workdir=".", process_unit=lambda s, w: _FakeVerdict(90), merge_queue=mq)
    assert res.landed_waves == 0 and res.held_waves == 0
    assert res.assembly == "ff_to_target"   # clean: nothing held


def test_run_dag_wave_atomic_lands_all_clean_waves():
    from harness.merge_queue import MergeQueue
    mq = MergeQueue(suite_runner=lambda: (True, ""), merger=lambda u: (True, ""))
    # two waves (a then b); both GREEN -> both land -> ff whole build
    res = run_dag([B, A], workdir=".", process_unit=lambda s, w: _FakeVerdict(90), merge_queue=mq)
    assert res.assembly == "ff_to_target"
    assert res.landed_waves == 2 and res.held_waves == 0


def test_run_dag_wave_atomic_partial_holds_failing_wave_and_successors():
    from harness.merge_queue import MergeQueue
    mq = MergeQueue(suite_runner=lambda: (True, ""), merger=lambda u: (True, ""))
    # wave0=a GREEN (lands), wave1=b FAILS gate -> wave1 held, prefix preserved
    def proc(st, w):
        return _FakeVerdict(90) if st.id == "a" else _FakeVerdict(20)
    res = run_dag([B, A], workdir=".", process_unit=proc, merge_queue=mq)
    assert res.assembly == "partial"
    assert res.landed_waves == 1 and res.held_waves == 1
    assert res.accepted == 1 and res.failed == 1


def test_run_dag_dag_atomicity_opt_in_discards_on_partial():
    from harness.merge_queue import MergeQueue
    mq = MergeQueue(suite_runner=lambda: (True, ""), merger=lambda u: (True, ""))
    def proc(st, w):
        return _FakeVerdict(90) if st.id == "a" else _FakeVerdict(20)
    # strict whole-or-nothing: one failed unit discards the whole build
    res = run_dag([B, A], workdir=".", process_unit=proc, merge_queue=mq, atomicity="dag")
    assert res.assembly == "discard"


def test_run_dag_resume_skips_accepted_units():
    from harness.checkpoint import make_checkpoint
    ckpt = make_checkpoint({"a": {"state": "ACCEPTED"}})
    dispatched = []
    def proc(st, w):
        dispatched.append(st.id)
        return _FakeVerdict(90)
    res = run_dag([B, A], workdir=".", process_unit=proc, resume_from=ckpt)
    assert "a" not in dispatched         # already-accepted 'a' skipped
    assert "b" in dispatched
    assert res.board["a"]["state"] == "ACCEPTED" and res.board["a"].get("resumed") is True
