import json
import pytest
from harness.evalkit.__main__ import main, resolve_spec


def _good(spec, prompt):
    return "def validate_input(d):\n    return 'symbol' in d\n"


def test_resolve_spec_claude_tier():
    spec, price = resolve_spec("sonnet")
    assert spec["backend"] == "claude_cli" and spec["model"] == "sonnet" and price > 0


def test_resolve_spec_providers_json_gemma4():
    spec, price = resolve_spec("gemma4")
    assert spec["backend"] == "ollama" and spec["name"] == "gemma4" and price == 0.0


def test_resolve_spec_unknown_best_effort_ollama():
    spec, price = resolve_spec("some-new-local-model")
    assert spec["backend"] == "ollama" and price == 0.0


def test_cli_runs_and_prints_leader(monkeypatch, capsys):
    monkeypatch.setattr("harness.model_call.call_model", _good)
    rc = main(["--model", "gemma4", "--sizes", "1000", "--trials", "1", "--text"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "leader: gemma4" in out and "MERIT SCORECARD" in out


def test_cli_writes_report(monkeypatch, tmp_path):
    monkeypatch.setattr("harness.model_call.call_model", _good)
    rep = tmp_path / "r.json"
    main(["--model", "gemma4", "--sizes", "1000", "--trials", "1", "--report", str(rep)])
    data = json.loads(rep.read_text())
    assert data["leaderboard"][0]["model"] == "gemma4"


def test_cli_ingest_writes_profiles(monkeypatch, tmp_path):
    monkeypatch.setattr("harness.model_call.call_model", _good)
    prof = tmp_path / "profiles.json"
    prof.write_text(json.dumps({"gemma4": {"max_reliable_tokens": 1, "accuracy_by_type": {},
                                           "session_failures": 0, "retry_budget": 3,
                                           "last_updated": 0, "decay_per_day": 0.98}}))
    main(["--model", "gemma4", "--sizes", "1000", "--trials", "1",
          "--ingest", "--profiles-path", str(prof)])
    updated = json.loads(prof.read_text())
    assert updated["gemma4"]["accuracy_by_type"].get("code_gen", 0) > 0


def test_cli_custom_suite(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("harness.model_call.call_model", lambda s, p: "foo")
    suite = tmp_path / "s.json"
    suite.write_text(json.dumps([{"id": "c1", "task_type": "code_gen", "prompt": "p",
                                  "context_tokens": 500,
                                  "grader": {"type": "keyword", "keywords": ["foo"]}}]))
    rc = main(["--model", "gemma4", "--suite", str(suite), "--trials", "1"])
    assert rc == 0


def test_resolve_spec_openai_compat_carries_config():
    spec, price = resolve_spec("deepseek")
    assert spec["backend"] == "openai_compat"
    assert spec["base_url"].startswith("http") and "api_key_env" in spec
    assert price > 0


def test_cli_cloud_missing_key_fails_loud_not_poison(monkeypatch, tmp_path, capsys):
    # deepseek needs DEEPSEEK_API_KEY; unset -> CLI returns nonzero, writes NOTHING to profiles
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    prof = tmp_path / "profiles.json"
    prof.write_text('{"deepseek": {"max_reliable_tokens": 32000, "accuracy_by_type": {"code_gen": 0.8}, "session_failures": 0, "retry_budget": 3, "last_updated": 0, "decay_per_day": 0.98}}')
    rc = main(["--model", "deepseek", "--sizes", "1000", "--trials", "1",
               "--ingest", "--profiles-path", str(prof)])
    assert rc == 2                                    # fail loud
    import json
    assert json.loads(prof.read_text())["deepseek"]["accuracy_by_type"]["code_gen"] == 0.8  # untouched
