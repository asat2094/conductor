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
