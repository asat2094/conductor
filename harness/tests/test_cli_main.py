"""CLI smoke tests for `python3 -m harness` — network-free: tiny units cost-skip to inline."""
import json


TINY = [{"id": "t1", "goal": "trivial", "task_type": "code_edit", "files": ["x.py"],
         "writes_files": ["x.py"], "context_slices": [],
         "contract": {"produces": ["x"], "consumes": []},
         "verify_cmd": "", "exit_criteria": "ok", "sensitivity": "low", "estimated_tokens": 100}]


def test_cli_runs_briefs_and_exits_zero(tmp_path, capsys):
    from harness.__main__ import main
    p = tmp_path / "briefs.json"
    p.write_text(json.dumps(TINY))
    rc = main([str(p), "--workdir", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "inline=1" in out          # tiny unit cost-skipped, no model call


def test_cli_report_flag_prints_board(tmp_path, capsys):
    from harness.__main__ import main
    p = tmp_path / "briefs.json"
    p.write_text(json.dumps(TINY))
    rc = main([str(p), "--workdir", str(tmp_path), "--report"])
    out = capsys.readouterr().out
    assert "t1" in out and "INLINE" in out


def test_cli_checkpoint_written(tmp_path):
    from harness.__main__ import main
    p = tmp_path / "briefs.json"
    p.write_text(json.dumps(TINY))
    ck = tmp_path / "ck.json"
    main([str(p), "--workdir", str(tmp_path), "--checkpoint", str(ck)])
    assert ck.exists()
