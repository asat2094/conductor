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
