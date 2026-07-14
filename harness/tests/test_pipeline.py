"""Tests for harness/pipeline.py — run_pipeline() end-to-end flow."""
import pytest
from harness.models import SubTask, TaskType, EvalResult
from harness.orchestrate import EscalateToClaudeError
from harness.pipeline import run_pipeline, PipelineResult


def _subtask(**overrides):
    base = dict(
        id="t1", description="add docstring to validate",
        type=TaskType.CODE_EDIT, files=["orders.py"], estimated_tokens=1000,
    )
    base.update(overrides)
    return SubTask(**base)


def _good_result(subtask):
    return EvalResult(
        subtask_id=subtask.id, agent="gemma4", score=80,
        syntax_score=25, test_score=35, scope_score=20, semantic_score=0,
        details="ok",
    )


def _bad_result(subtask):
    return EvalResult(
        subtask_id=subtask.id, agent="gemma4", score=40,
        syntax_score=25, test_score=0, scope_score=15, semantic_score=0,
        details="fail",
    )


def test_routes_to_gemma4_and_scores_ok(tmp_path, monkeypatch):
    st = _subtask()
    monkeypatch.setattr("harness.pipeline.orchestrate", lambda s, workdir, diff_mode: _good_result(s))

    pr = run_pipeline(st, workdir=str(tmp_path))
    assert pr.agent_used == "gemma4"
    assert pr.final_score == 80
    assert pr.strategy is None
    assert not pr.routed_to_claude


def test_routes_to_claude_agent_for_research(tmp_path, monkeypatch):
    st = _subtask(type=TaskType.RESEARCH)

    def raise_escalate(s, workdir, diff_mode):
        raise EscalateToClaudeError(s)

    monkeypatch.setattr("harness.pipeline.orchestrate", raise_escalate)

    pr = run_pipeline(st, workdir=str(tmp_path))
    assert pr.routed_to_claude is True
    assert pr.final_score == -1
    assert pr.agent_used == "claude_agent"


def test_auto_heal_fires_on_low_score(tmp_path, monkeypatch):
    """orchestrate() handles healing internally; pipeline gets the healed result."""
    st = _subtask()
    healed = EvalResult(
        subtask_id="t1", agent="gemma4", score=75,
        syntax_score=25, test_score=35, scope_score=15, semantic_score=0, details="healed",
    )
    monkeypatch.setattr("harness.pipeline.orchestrate", lambda s, workdir, diff_mode: healed)

    pr = run_pipeline(st, workdir=str(tmp_path))
    # strategy is None because orchestrate handles healing; pipeline sets None always
    assert pr.final_score == 75
    assert pr.agent_used == "gemma4"


def test_no_heal_flag_skips_healer(tmp_path, monkeypatch):
    """auto_heal=False is accepted for API compat; orchestrate is still called once."""
    st = _subtask()
    calls = {"n": 0}

    def track_orchestrate(s, workdir, diff_mode):
        calls["n"] += 1
        return _bad_result(s)

    monkeypatch.setattr("harness.pipeline.orchestrate", track_orchestrate)
    pr = run_pipeline(st, workdir=str(tmp_path), auto_heal=False)
    assert calls["n"] == 1
    assert pr.final_score == 40


def test_strategy_c_when_both_fail(tmp_path, monkeypatch):
    """All providers exhausted → EscalateToClaudeError → routed_to_claude."""
    st = _subtask()

    def raise_escalate(s, workdir, diff_mode):
        raise EscalateToClaudeError(s)

    monkeypatch.setattr("harness.pipeline.orchestrate", raise_escalate)

    pr = run_pipeline(st, workdir=str(tmp_path))
    assert pr.routed_to_claude is True
    assert pr.final_score == -1
    assert pr.agent_used == "claude_agent"
