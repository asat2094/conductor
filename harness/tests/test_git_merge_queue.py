import subprocess
from harness.git_merge_queue import GitMergeQueue, INTEGRATION_BRANCH


def _repo(tmp_path):
    """Tiny real repo: main branch with one commit."""
    subprocess.run("git init -q -b main && git commit -q --allow-empty -m root",
                   shell=True, cwd=tmp_path, check=True)
    return str(tmp_path)


def _sha(wd, ref):
    return subprocess.run(f"git rev-parse {ref}", shell=True, cwd=wd,
                          capture_output=True, text=True).stdout.strip()


def test_setup_creates_integration_branch_at_target_tip(tmp_path):
    wd = _repo(tmp_path)
    GitMergeQueue(wd, "main")
    assert _sha(wd, INTEGRATION_BRANCH) == _sha(wd, "main")


def test_submit_commits_unit_on_integration_branch(tmp_path):
    wd = _repo(tmp_path)
    q = GitMergeQueue(wd, "main")
    (tmp_path / "a.py").write_text("x = 1\n")
    r = q.submit("u1")
    assert r.merged is True
    log = subprocess.run("git log --oneline", shell=True, cwd=wd,
                         capture_output=True, text=True).stdout
    assert "conductor unit: u1" in log
    assert _sha(wd, "main") != _sha(wd, INTEGRATION_BRANCH)   # main NOT advanced yet


def test_promote_wave_fast_forwards_target(tmp_path):
    wd = _repo(tmp_path)
    q = GitMergeQueue(wd, "main")
    (tmp_path / "a.py").write_text("x = 1\n")
    q.submit("u1")
    assert q.promote_wave(assembly_ok=True) == "ff_wave"
    assert _sha(wd, "main") == _sha(wd, INTEGRATION_BRANCH)   # main physically advanced


def test_held_wave_leaves_target_untouched(tmp_path):
    wd = _repo(tmp_path)
    q = GitMergeQueue(wd, "main", suite_cmd="false")          # suite always red
    main_before = _sha(wd, "main")
    (tmp_path / "a.py").write_text("x = 1\n")
    r = q.submit("u1")                                        # commit ok, suite fails
    assert r.merged is False
    assert q.promote_wave(assembly_ok=False) == "hold"
    assert _sha(wd, "main") == main_before                    # prefix rule: nothing landed


def test_prefix_rule_second_wave_holds_after_failure(tmp_path):
    wd = _repo(tmp_path)
    q = GitMergeQueue(wd, "main")
    (tmp_path / "a.py").write_text("x = 1\n")
    q.submit("u1")
    assert q.promote_wave(assembly_ok=True) == "ff_wave"      # wave0 lands
    landed = _sha(wd, "main")
    (tmp_path / "b.py").write_text("y = 1\n")
    q.submit("u2")
    assert q.promote_wave(assembly_ok=False) == "hold"        # wave1 fails -> held
    (tmp_path / "c.py").write_text("z = 1\n")
    q.submit("u3")
    assert q.promote_wave(assembly_ok=True) == "hold"         # wave2 GREEN but held (prefix)
    assert _sha(wd, "main") == landed                         # target frozen at the GREEN prefix


def test_finalize_dag_mode_single_ff(tmp_path):
    wd = _repo(tmp_path)
    q = GitMergeQueue(wd, "main")
    (tmp_path / "a.py").write_text("x = 1\n")
    q.submit("u1")
    assert q.finalize(assembly_ok=True) == "ff_to_target"
    assert _sha(wd, "main") == _sha(wd, INTEGRATION_BRANCH)


def test_suite_cmd_runs_real_shell(tmp_path):
    wd = _repo(tmp_path)
    q = GitMergeQueue(wd, "main", suite_cmd="true")
    (tmp_path / "a.py").write_text("x = 1\n")
    assert q.submit("u1").suite_passed is True


def test_end_to_end_with_run_dag(tmp_path):
    """run_dag + GitMergeQueue: two waves, second fails -> partial; main holds the GREEN prefix."""
    from harness.run_dag import run_dag
    wd = _repo(tmp_path)
    q = GitMergeQueue(wd, "main")

    A = {"id": "a", "goal": "g", "task_type": "code_gen", "files": ["p.py"], "writes_files": ["p.py"],
         "context_slices": [], "contract": {"produces": ["parse"], "consumes": []},
         "verify_cmd": "", "exit_criteria": "ok", "sensitivity": "low", "estimated_tokens": 5000}
    B = {"id": "b", "goal": "g", "task_type": "code_edit", "files": ["m.py"], "writes_files": ["m.py"],
         "context_slices": [], "contract": {"produces": [], "consumes": ["parse"]},
         "verify_cmd": "", "exit_criteria": "ok", "sensitivity": "low", "estimated_tokens": 5000}

    class _V:
        def __init__(self, s): self.final_score, self.agent_used, self.routed_to_claude = s, "gemma4", False

    def proc(st, w):
        (tmp_path / st.files[0]).write_text(f"# {st.id}\n")   # simulate the maker writing
        return _V(90 if st.id == "a" else 20)

    res = run_dag([B, A], workdir=wd, process_unit=proc, merge_queue=q)
    assert res.assembly == "partial"
    assert res.landed_waves == 1
    log = subprocess.run("git log --oneline main", shell=True, cwd=wd,
                         capture_output=True, text=True).stdout
    assert "conductor unit: a" in log                          # wave0 physically on main
    assert "conductor unit: b" not in log                      # failed wave held off main


def test_writes_for_scopes_commit_to_declared_files(tmp_path):
    wd = _repo(tmp_path)
    q = GitMergeQueue(wd, "main", writes_for={"u1": ["a.py"]}.get)
    (tmp_path / "a.py").write_text("x = 1\n")          # declared
    (tmp_path / "stray.json").write_text("{}\n")       # stray — must NOT land
    q.submit("u1")
    q.promote_wave(assembly_ok=True)
    tracked = subprocess.run("git ls-tree main --name-only", shell=True, cwd=wd,
                             capture_output=True, text=True).stdout
    assert "a.py" in tracked
    assert "stray.json" not in tracked                 # scope guard at the merge boundary


def test_dirty_tree_refuses_to_construct(tmp_path):
    # CRITICAL regression: uncommitted tracked edits must never be swept into unit commits
    import pytest
    wd = _repo(tmp_path)
    (tmp_path / "tracked.py").write_text("original\n")
    subprocess.run("git add tracked.py && git -c core.hooksPath=/dev/null commit -q --no-verify -m t",
                   shell=True, cwd=wd, check=True)
    (tmp_path / "tracked.py").write_text("SECRET-UNCOMMITTED-EDIT\n")   # dirty tracked file
    with pytest.raises(RuntimeError, match="dirty"):
        GitMergeQueue(wd, "main")
    # nothing landed anywhere
    show = subprocess.run("git show main:tracked.py", shell=True, cwd=wd,
                          capture_output=True, text=True).stdout
    assert "SECRET" not in show


def test_untracked_files_also_refuse(tmp_path):
    import pytest
    wd = _repo(tmp_path)
    (tmp_path / "scratch.txt").write_text("wip\n")     # untracked counts as dirty too
    with pytest.raises(RuntimeError, match="dirty"):
        GitMergeQueue(wd, "main")
