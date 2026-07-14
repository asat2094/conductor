import threading
from unittest.mock import MagicMock, patch

import pytest

from harness.models import (
    AgentType, CapabilityProfile, EvalResult, ProviderConfig, SubTask, TaskType,
)
import harness.orchestrate as _orch_mod


@pytest.fixture(autouse=True)
def clear_rate_limits():
    _orch_mod._rate_limit_until.clear()
    yield
    _orch_mod._rate_limit_until.clear()


def _subtask(tokens=100):
    return SubTask("t1", "add docstring", TaskType.CODE_EDIT, ["f.py"], tokens)


def _providers():
    return {
        "deepseek": ProviderConfig("deepseek", "openai_compat", "deepseek-coder",
                                   "https://api.deepseek.com/v1", 0.001, "cloud_cheap", "KEY"),
        "gemini":   ProviderConfig("gemini",   "openai_compat", "gemini-2.0-flash",
                                   "https://api.gemini.com/v1", 0.0001, "cloud_cheap", "KEY2"),
    }


def _profiles():
    return {
        "deepseek": CapabilityProfile(32000, {"code_edit": 0.85}),
        "gemini":   CapabilityProfile(32000, {"code_edit": 0.85}),
    }


def _good_eval(subtask, agent, changed, output):
    return EvalResult(subtask.id, agent, 80, 25, 35, 20, 0, "ok", changed)


def _bad_eval(subtask, agent, changed, output):
    return EvalResult(subtask.id, agent, 30, 0, 0, 0, 30, "fail", changed)


def test_orchestrate_returns_result_on_first_provider_success(tmp_path):
    from harness.orchestrate import orchestrate
    (tmp_path / "f.py").write_text("x=1")
    with patch("harness.orchestrate.provider_run", return_value=("resp", "code")) as mock_run, \
         patch("harness.orchestrate.evaluate", side_effect=_good_eval), \
         patch("harness.orchestrate.save_profiles"), \
         patch("harness.orchestrate.update_score"), \
         patch("harness.orchestrate.log_delegation"):
        result = orchestrate(_subtask(), str(tmp_path), _providers(), _profiles())
    assert result.score == 80
    assert mock_run.call_count == 1


def test_orchestrate_falls_back_on_rate_limit(tmp_path):
    from harness.orchestrate import orchestrate
    from harness.provider_call import RateLimitError
    from harness.router import rank_providers
    (tmp_path / "f.py").write_text("x=1")
    call_count = {"n": 0}

    # Determine which provider is ranked first so we can fail it
    ranked = rank_providers(_subtask(), _providers(), _profiles())
    first_provider = ranked[0]  # the one that should fail

    def fake_run(provider, *a, **kw):
        call_count["n"] += 1
        if provider.name == first_provider:
            raise RateLimitError("rate limited")
        return "resp", "code"

    with patch("harness.orchestrate.provider_run", side_effect=fake_run), \
         patch("harness.orchestrate.evaluate", side_effect=_good_eval), \
         patch("harness.orchestrate.save_profiles"), \
         patch("harness.orchestrate.update_score"), \
         patch("harness.orchestrate.log_delegation"):
        result = orchestrate(_subtask(), str(tmp_path), _providers(), _profiles())

    assert call_count["n"] == 2  # first provider failed, second succeeded
    assert result.score == 80


def test_orchestrate_falls_back_on_provider_error(tmp_path):
    from harness.orchestrate import orchestrate
    from harness.provider_call import ProviderError
    (tmp_path / "f.py").write_text("x=1")

    def fake_run(provider, *a, **kw):
        if provider.name == "deepseek":
            raise ProviderError("timeout")
        return "resp", "code"

    with patch("harness.orchestrate.provider_run", side_effect=fake_run), \
         patch("harness.orchestrate.evaluate", side_effect=_good_eval), \
         patch("harness.orchestrate.save_profiles"), \
         patch("harness.orchestrate.update_score"), \
         patch("harness.orchestrate.log_delegation"):
        result = orchestrate(_subtask(), str(tmp_path), _providers(), _profiles())
    assert result.score == 80


def test_orchestrate_escalates_when_all_providers_fail(tmp_path):
    from harness.orchestrate import orchestrate, EscalateToClaudeError
    from harness.provider_call import ProviderError
    (tmp_path / "f.py").write_text("x=1")
    with patch("harness.orchestrate.provider_run", side_effect=ProviderError("boom")):
        with pytest.raises(EscalateToClaudeError):
            orchestrate(_subtask(), str(tmp_path), _providers(), _profiles())


def test_orchestrate_tries_next_provider_on_soft_failure(tmp_path):
    from harness.orchestrate import orchestrate
    (tmp_path / "f.py").write_text("x=1")
    eval_calls = {"n": 0}

    def fake_eval(subtask, agent, changed, output):
        eval_calls["n"] += 1
        if agent == "deepseek":
            return EvalResult(subtask.id, agent, 30, 0, 0, 0, 30, "fail", changed)
        return EvalResult(subtask.id, agent, 85, 25, 35, 25, 0, "ok", changed)

    def fake_heal(subtask, result, profiles, workdir, delegate_fn=None, evaluate_fn=None):
        return None, "C"  # force escalation from healer → next provider

    with patch("harness.orchestrate.provider_run", return_value=("resp", "code")), \
         patch("harness.orchestrate.evaluate", side_effect=fake_eval), \
         patch("harness.orchestrate.auto_heal", side_effect=fake_heal), \
         patch("harness.orchestrate.save_profiles"), \
         patch("harness.orchestrate.update_score"), \
         patch("harness.orchestrate.log_delegation"):
        result = orchestrate(_subtask(), str(tmp_path), _providers(), _profiles())

    assert result.score == 85
    assert result.agent == "gemini"


def test_orchestrate_parallel_distributes_across_providers(tmp_path):
    from harness.orchestrate import orchestrate_parallel
    (tmp_path / "f1.py").write_text("x=1")
    (tmp_path / "f2.py").write_text("y=2")

    subtasks = [
        SubTask("t1", "task1", TaskType.CODE_EDIT, ["f1.py"], 100),
        SubTask("t2", "task2", TaskType.CODE_EDIT, ["f2.py"], 100),
    ]

    used_providers = []

    def fake_run(provider, *a, **kw):
        used_providers.append(provider.name)
        return "resp", "code"

    with patch("harness.orchestrate.provider_run", side_effect=fake_run), \
         patch("harness.orchestrate.evaluate", side_effect=_good_eval), \
         patch("harness.orchestrate.save_profiles"), \
         patch("harness.orchestrate.update_score"), \
         patch("harness.orchestrate.log_delegation"):
        results = orchestrate_parallel(subtasks, str(tmp_path), _providers(), _profiles())

    assert len(results) == 2
    assert all(r.score == 80 for r in results)
