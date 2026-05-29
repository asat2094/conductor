"""Tests for harness/parallel_cli.py CLI module."""
import json
from harness.parallel_cli import main as cli_main


def test_exit_0_on_all_success(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "harness.parallel_delegate._gemma4_run",
        lambda w, t, f, diff_mode=False: ("resp", "code"),
    )
    tasks = json.dumps([{"task": "add docstring", "file": "a.py"}])
    monkeypatch.setattr("sys.argv", ["parallel_cli", str(tmp_path), tasks])
    assert cli_main() == 0


def test_exit_1_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "harness.parallel_delegate._gemma4_run",
        lambda w, t, f, diff_mode=False: ("resp", None),
    )
    tasks = json.dumps([{"task": "add docstring", "file": "a.py"}])
    monkeypatch.setattr("sys.argv", ["parallel_cli", str(tmp_path), tasks])
    assert cli_main() == 1


def test_workers_flag_accepted(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "harness.parallel_delegate._gemma4_run",
        lambda w, t, f, diff_mode=False: ("resp", "code"),
    )
    tasks = json.dumps([{"task": "x", "file": "a.py"}])
    monkeypatch.setattr(
        "sys.argv", ["parallel_cli", str(tmp_path), tasks, "--workers", "1"]
    )
    rc = cli_main()
    assert rc == 0


def test_missing_args_returns_1(monkeypatch):
    monkeypatch.setattr("sys.argv", ["parallel_cli"])
    assert cli_main() == 1
