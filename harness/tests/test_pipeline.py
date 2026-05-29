"""Tests for harness/pipeline.py — run_pipeline() end-to-end flow."""
import pytest
from harness.models import SubTask, TaskType, AgentType, EvalResult, CapabilityProfile
from harness.pipeline import run_pipeline, PipelineResult


def _subtask(**overrides):
    base = dict(
        id="t1", description="add docstring to validate",
        type=TaskType.CODE_EDIT, files=["orders.py"], estimated_tokens=1000,
    )
    base.update(overrides)
    return SubTask(**base)


def _good_profiles():
    return {
        "gemma4": CapabilityProfile(
            max_reliable_tokens=32000,
            accuracy_by_type={"code_edit": 0.9},
        ),
        "claude_agent": CapabilityProfile(
            max_reliable_tokens=180000,
            accuracy_by_type={"code_edit": 0.95},
        ),
    }


def _good_eval(subtask, agent, changed_files, output):
    return EvalResult(
        subtask_id=subtask.id, agent=agent, score=80,
        syntax_score=25, test_score=35, scope_score=20, semantic_score=0,
        details="ok",
    )


def _bad_eval(subtask, agent, changed_files, output):
    return EvalResult(
        subtask_id=subtask.id, agent=agent, score=40,
        syntax_score=25, test_score=0, scope_score=15, semantic_score=0,
        details="fail",
    )


def test_routes_to_gemma4_and_scores_ok(tmp_path, monkeypatch):
    monkeypatch.setattr("harness.pipeline.load_profiles", lambda: _good_profiles())
    monkeypatch.setattr("harness.pipeline.save_profiles", lambda p: None)
    monkeypatch.setattr("harness.pipeline.log_delegation", lambda **kw: None)
    monkeypatch.setattr("harness.pipeline.update_score", lambda *a: None)
    monkeypatch.setattr("harness.pipeline.update_accuracy", lambda *a, **kw: None)
    monkeypatch.setattr("harness.pipeline.gemma4_run", lambda w, t, f, diff_mode=False: ("resp", "code"))
    monkeypatch.setattr("harness.pipeline.evaluate", _good_eval)

    pr = run_pipeline(_subtask(), workdir=str(tmp_path))
    assert pr.agent_used == AgentType.GEMMA4
    assert pr.final_score == 80
    assert pr.strategy is None
    assert not pr.routed_to_claude


def test_routes_to_claude_agent_for_research(tmp_path, monkeypatch):
    monkeypatch.setattr("harness.pipeline.load_profiles", lambda: _good_profiles())
    monkeypatch.setattr("harness.pipeline.save_profiles", lambda p: None)
    monkeypatch.setattr("harness.pipeline.log_delegation", lambda **kw: None)
    monkeypatch.setattr("harness.pipeline.update_score", lambda *a: None)
    monkeypatch.setattr("harness.pipeline.update_accuracy", lambda *a, **kw: None)

    pr = run_pipeline(
        _subtask(type=TaskType.RESEARCH),
        workdir=str(tmp_path),
    )
    assert pr.routed_to_claude is True
    assert pr.final_score == -1
    assert pr.agent_used == AgentType.CLAUDE_AGENT


def test_auto_heal_fires_on_low_score(tmp_path, monkeypatch):
    monkeypatch.setattr("harness.pipeline.load_profiles", lambda: _good_profiles())
    monkeypatch.setattr("harness.pipeline.save_profiles", lambda p: None)
    monkeypatch.setattr("harness.pipeline.log_delegation", lambda **kw: None)
    monkeypatch.setattr("harness.pipeline.update_score", lambda *a: None)
    monkeypatch.setattr("harness.pipeline.update_accuracy", lambda *a, **kw: None)
    monkeypatch.setattr("harness.pipeline.gemma4_run", lambda w, t, f, diff_mode=False: ("resp", "code"))
    monkeypatch.setattr("harness.pipeline.evaluate", _bad_eval)

    healed = EvalResult(
        subtask_id="t1_shrunk", agent=AgentType.GEMMA4, score=75,
        syntax_score=25, test_score=35, scope_score=15, semantic_score=0, details="healed",
    )
    monkeypatch.setattr("harness.pipeline._auto_heal", lambda *a, **kw: (healed, "A"))

    pr = run_pipeline(_subtask(), workdir=str(tmp_path))
    assert pr.strategy == "A"
    assert pr.final_score == 75


def test_no_heal_flag_skips_healer(tmp_path, monkeypatch):
    monkeypatch.setattr("harness.pipeline.load_profiles", lambda: _good_profiles())
    monkeypatch.setattr("harness.pipeline.save_profiles", lambda p: None)
    monkeypatch.setattr("harness.pipeline.log_delegation", lambda **kw: None)
    monkeypatch.setattr("harness.pipeline.update_score", lambda *a: None)
    monkeypatch.setattr("harness.pipeline.update_accuracy", lambda *a, **kw: None)
    monkeypatch.setattr("harness.pipeline.gemma4_run", lambda w, t, f, diff_mode=False: ("resp", "code"))
    monkeypatch.setattr("harness.pipeline.evaluate", _bad_eval)

    heal_called = {"n": 0}

    def track_heal(*a, **kw):
        heal_called["n"] += 1
        return None, "C"

    monkeypatch.setattr("harness.pipeline._auto_heal", track_heal)
    run_pipeline(_subtask(), workdir=str(tmp_path), auto_heal=False)
    assert heal_called["n"] == 0


def test_strategy_c_when_both_fail(tmp_path, monkeypatch):
    monkeypatch.setattr("harness.pipeline.load_profiles", lambda: _good_profiles())
    monkeypatch.setattr("harness.pipeline.save_profiles", lambda p: None)
    monkeypatch.setattr("harness.pipeline.log_delegation", lambda **kw: None)
    monkeypatch.setattr("harness.pipeline.update_score", lambda *a: None)
    monkeypatch.setattr("harness.pipeline.update_accuracy", lambda *a, **kw: None)
    monkeypatch.setattr("harness.pipeline.gemma4_run", lambda w, t, f, diff_mode=False: ("resp", "code"))
    monkeypatch.setattr("harness.pipeline.evaluate", _bad_eval)
    monkeypatch.setattr("harness.pipeline._auto_heal", lambda *a, **kw: (None, "C"))

    pr = run_pipeline(_subtask(), workdir=str(tmp_path))
    assert pr.strategy == "C"
    assert pr.final_score == 40  # original bad score
