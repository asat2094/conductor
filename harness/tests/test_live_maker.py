from types import SimpleNamespace
from harness.live_maker import build_prompt, make_live_maker, LiveMaker
from harness.unit_gate import UnitArtifact


def _subtask(**kw):
    base = dict(id="u1", description="add parse()", type=SimpleNamespace(value="code_gen"),
                files=["p.py"], produces=["parse"], consumes=[])
    base.update(kw)
    return SimpleNamespace(**base)


def test_build_prompt_includes_goal_and_contract():
    p = build_prompt(_subtask(), feedback=None)
    assert "add parse()" in p
    assert "parse" in p          # produces
    assert "=== FILE:" in p      # instructs the FILE block format


def test_build_prompt_includes_feedback_on_repair():
    p = build_prompt(_subtask(), feedback="pbt counterexample: 3")
    assert "counterexample" in p


def test_make_writes_files_and_returns_artifact(tmp_path):
    # fake model emits a FILE block; injected test_runner says green
    model = lambda spec, prompt: "=== FILE: p.py ===\ndef parse():\n    return 1\n=== END ==="
    lm = LiveMaker(str(tmp_path), role="impl_author",
                   model_caller=model,
                   test_runner=lambda cmd, wd: (0, "1 passed"),
                   differ=lambda wd, paths: "+def parse()")
    art = lm.make(_subtask(), feedback=None)
    assert isinstance(art, UnitArtifact)
    assert "p.py" in art.changed_files
    assert (tmp_path / "p.py").read_text().startswith("def parse")
    assert art.in_loop_green is True
    assert art.task_type == "code_gen"


def test_make_reports_red_when_test_fails(tmp_path):
    model = lambda spec, prompt: "=== FILE: p.py ===\ndef parse():\n    return 0\n=== END ==="
    lm = LiveMaker(str(tmp_path), role="impl_author",
                   model_caller=model,
                   test_runner=lambda cmd, wd: (1, "AssertionError"),
                   differ=lambda wd, paths: "")
    # subtask has a test file -> runner is consulted
    art = lm.make(_subtask(files=["p.py", "test_p.py"]), feedback=None)
    assert art.in_loop_green is False


def test_make_no_test_file_defaults_green(tmp_path):
    model = lambda spec, prompt: "=== FILE: p.py ===\nx=1\n=== END ==="
    called = {"n": 0}
    def runner(cmd, wd):
        called["n"] += 1
        return (0, "")
    lm = LiveMaker(str(tmp_path), role="impl_author", model_caller=model,
                   test_runner=runner, differ=lambda wd, paths: "")
    art = lm.make(_subtask(files=["p.py"]), feedback=None)  # no test_ file
    assert art.in_loop_green is True
    assert called["n"] == 0   # no test file -> runner not called


def test_make_live_maker_factory_is_process_unit_compatible(tmp_path):
    model = lambda spec, prompt: "=== FILE: p.py ===\nx=1\n=== END ==="
    maker = make_live_maker(role="impl_author", model_caller=model,
                            test_runner=lambda cmd, wd: (0, ""), differ=lambda wd, paths: "")
    art = maker(_subtask(), str(tmp_path), None)   # signature: (subtask, workdir, feedback)
    assert isinstance(art, UnitArtifact)
