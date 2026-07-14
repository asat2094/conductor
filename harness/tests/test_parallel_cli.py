"""Tests for harness/parallel_cli.py CLI module."""
import json
from unittest.mock import MagicMock, patch
from harness.parallel_cli import main as cli_main


def _mock_orchestrate_success(*args, **kwargs):
    r = MagicMock()
    r.score = 85
    r.agent = "gemma4"
    r.details = "ok"
    return r


def _mock_orchestrate_failure(*args, **kwargs):
    r = MagicMock()
    r.score = 50
    r.agent = "gemma4"
    r.details = "low score"
    return r


def test_exit_0_on_all_success(tmp_path, monkeypatch):
    tasks = json.dumps([{"task": "add docstring", "file": "a.py"}])
    monkeypatch.setattr("sys.argv", ["parallel_cli", str(tmp_path), tasks])
    with patch("harness.parallel_delegate.orchestrate", side_effect=_mock_orchestrate_success), \
         patch("harness.parallel_delegate.load_providers", return_value={"gemma4": MagicMock()}), \
         patch("harness.parallel_delegate.load_profiles", return_value={}):
        assert cli_main() == 0


def test_exit_1_on_failure(tmp_path, monkeypatch):
    tasks = json.dumps([{"task": "add docstring", "file": "a.py"}])
    monkeypatch.setattr("sys.argv", ["parallel_cli", str(tmp_path), tasks])
    with patch("harness.parallel_delegate.orchestrate", side_effect=_mock_orchestrate_failure), \
         patch("harness.parallel_delegate.load_providers", return_value={"gemma4": MagicMock()}), \
         patch("harness.parallel_delegate.load_profiles", return_value={}):
        assert cli_main() == 1


def test_workers_flag_accepted(tmp_path, monkeypatch, capsys):
    tasks = json.dumps([{"task": "x", "file": "a.py"}])
    monkeypatch.setattr(
        "sys.argv", ["parallel_cli", str(tmp_path), tasks, "--workers", "1"]
    )
    with patch("harness.parallel_delegate.orchestrate", side_effect=_mock_orchestrate_success), \
         patch("harness.parallel_delegate.load_providers", return_value={"gemma4": MagicMock()}), \
         patch("harness.parallel_delegate.load_profiles", return_value={}):
        rc = cli_main()
    assert rc == 0


def test_missing_args_returns_1(monkeypatch):
    monkeypatch.setattr("sys.argv", ["parallel_cli"])
    assert cli_main() == 1
