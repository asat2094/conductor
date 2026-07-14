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


def test_cli_merge_target_lands_on_clean_repo(tmp_path):
    """--merge-target end-to-end on a CLEAN repo: inline unit -> no merge, main untouched, rc 0."""
    import subprocess
    from harness.__main__ import main
    subprocess.run("git init -q -b main && git -c core.hooksPath=/dev/null commit -q --no-verify --allow-empty -m root",
                   shell=True, cwd=tmp_path, check=True)
    p = tmp_path / "briefs.json"
    p.write_text(json.dumps(TINY))
    subprocess.run("git add briefs.json && git -c core.hooksPath=/dev/null commit -q --no-verify -m briefs",
                   shell=True, cwd=tmp_path, check=True)
    rc = main([str(p), "--workdir", str(tmp_path), "--merge-target", "main"])
    assert rc == 0


def test_cli_merge_target_dirty_tree_fails_loud(tmp_path):
    import subprocess, pytest
    from harness.__main__ import main
    subprocess.run("git init -q -b main && git -c core.hooksPath=/dev/null commit -q --no-verify --allow-empty -m root",
                   shell=True, cwd=tmp_path, check=True)
    p = tmp_path / "briefs.json"
    p.write_text(json.dumps(TINY))                      # untracked -> dirty
    with pytest.raises(RuntimeError, match="dirty"):
        main([str(p), "--workdir", str(tmp_path), "--merge-target", "main"])
