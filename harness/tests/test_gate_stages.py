from harness.unit_gate import evaluate_unit, UnitArtifact, GateSpec
from harness.gate_stages import git_red_stage, mutation_stage, characterization_stage


def _art(**kw):
    base = dict(changed_files=["m.py"], diff_text="+x=1\n", task_type="code_edit",
                in_loop_green=True, oracle_passed=None)
    base.update(kw)
    return UnitArtifact(**base)


# --- extra_gates seam in evaluate_unit ---

def test_extra_gate_failure_short_circuits():
    spec = GateSpec(extra_gates=[("mut", lambda a: (False, "kill rate 40%"))])
    out = evaluate_unit(_art(), spec)
    assert out.passed is False and "mut" in out.evidence


def test_extra_gate_pass_continues():
    spec = GateSpec(extra_gates=[("mut", lambda a: (True, ""))])
    out = evaluate_unit(_art(), spec)
    assert out.passed is True
    assert ("mut", True) in out.results


# --- git_red_stage (ADR-0030) ---

def test_git_red_passes_without_test_impl_pair():
    stage = git_red_stage(".")
    ok, why = stage(_art(changed_files=["m.py"]))       # impl only, nothing to order
    assert ok is True


def test_git_red_uses_git_runner_for_pair(tmp_path):
    import subprocess
    # real tiny repo: test commit BEFORE impl commit -> gate passes
    subprocess.run("git init -q && git commit -q --allow-empty -m root", shell=True, cwd=tmp_path)
    (tmp_path / "test_m.py").write_text("def test_x(): assert m()\n")
    subprocess.run("git add test_m.py && git commit -q -m red", shell=True, cwd=tmp_path)
    (tmp_path / "m.py").write_text("def m(): return True\n")
    subprocess.run("git add m.py && git commit -q -m green", shell=True, cwd=tmp_path)
    ok, why = git_red_stage(str(tmp_path))(_art(changed_files=["test_m.py", "m.py"]))
    assert ok is True, why


def test_git_red_fails_when_impl_precedes_test(tmp_path):
    import subprocess
    subprocess.run("git init -q && git commit -q --allow-empty -m root", shell=True, cwd=tmp_path)
    (tmp_path / "m.py").write_text("def m(): return True\n")
    subprocess.run("git add m.py && git commit -q -m impl-first", shell=True, cwd=tmp_path)
    (tmp_path / "test_m.py").write_text("def test_x(): assert m()\n")
    subprocess.run("git add test_m.py && git commit -q -m test-after", shell=True, cwd=tmp_path)
    ok, why = git_red_stage(str(tmp_path))(_art(changed_files=["test_m.py", "m.py"]))
    assert ok is False


# --- mutation_stage (ADR-0008) ---

def test_mutation_stage_passes_at_full_kill(tmp_path):
    src = tmp_path / "m.py"
    src.write_text("def f(a, b):\n    return a + b\n")
    stage = mutation_stage(test_runner=lambda mutated: True, threshold=0.8)  # all mutants killed
    ok, why = stage(_art(changed_files=[str(src)]))
    assert ok is True


def test_mutation_stage_fails_when_mutants_survive(tmp_path):
    src = tmp_path / "m.py"
    src.write_text("def f(a, b):\n    return a + b\n")
    stage = mutation_stage(test_runner=lambda mutated: False, threshold=0.8)  # nothing killed
    ok, why = stage(_art(changed_files=[str(src)]))
    assert ok is False and "threshold" in why


def test_mutation_stage_skips_non_python():
    stage = mutation_stage(test_runner=lambda m: False)
    ok, _ = stage(_art(changed_files=["app.js"]))
    assert ok is True                                    # nothing to mutate -> pass


# --- characterization_stage (ADR-0010) ---

def test_characterization_detects_drift():
    before = {"f": [1, 2]}
    stage = characterization_stage(before, capture_after=lambda: {"f": [1, 999]})
    ok, why = stage(_art())
    assert ok is False and "f" in why


def test_characterization_passes_when_preserved():
    before = {"f": [1, 2]}
    stage = characterization_stage(before, capture_after=lambda: {"f": [1, 2]})
    ok, _ = stage(_art())
    assert ok is True
