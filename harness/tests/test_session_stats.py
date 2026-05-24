import tempfile
from pathlib import Path
from unittest.mock import patch

import harness.session_stats as ss


def _tmp_db(tmp_path: Path):
    return patch.object(ss, "DB_PATH", tmp_path / "test_stats.db")


def test_log_and_report(tmp_path):
    with _tmp_db(tmp_path):
        ss.log_delegation("ses1", "t1", "code_edit", "gemma4", 1200)
        ss.log_delegation("ses1", "t2", "code_gen", "gemma4", 800)
        ss.log_delegation("ses1", "t3", "research", "claude_agent", 5000)

        r = ss.session_report("ses1")
        assert r["total_delegations"] == 3
        assert r["gemma4_delegations"] == 2
        assert r["claude_delegations"] == 1
        assert r["gemma4_tokens_handled"] == 2000
        assert r["tokens_saved_from_claude"] == 2000
        assert r["gemma4_avg_score"] is None  # no scores yet


def test_update_score(tmp_path):
    with _tmp_db(tmp_path):
        ss.log_delegation("ses2", "task_a", "code_edit", "gemma4", 1000)
        ss.update_score("task_a", 85)

        r = ss.session_report("ses2")
        assert r["gemma4_avg_score"] == 85.0


def test_all_sessions_report(tmp_path):
    with _tmp_db(tmp_path):
        ss.log_delegation("A", "t1", "code_edit", "gemma4", 500)
        ss.log_delegation("B", "t2", "code_gen", "gemma4", 700)
        ss.log_delegation("B", "t3", "research", "claude_agent", 3000)

        report = ss.all_sessions_report()
        assert len(report["sessions"]) == 2
        assert report["totals"]["total_delegations"] == 3
        assert report["totals"]["gemma4_tokens_handled"] == 1200
        assert report["totals"]["claude_delegations"] == 1


def test_empty_db(tmp_path):
    with _tmp_db(tmp_path):
        report = ss.all_sessions_report()
        assert report["sessions"] == []
        assert report["totals"]["total_delegations"] == 0
        assert report["totals"]["tokens_saved_from_claude"] == 0


def test_print_report_runs(tmp_path, capsys):
    with _tmp_db(tmp_path):
        ss.log_delegation("ses3", "tx", "code_gen", "gemma4", 2000)
        ss.update_score("tx", 90)
        ss.print_report()

    out = capsys.readouterr().out
    assert "Conductor Session Stats" in out
    assert "2,000" in out  # token count formatted
    assert "90" in out
