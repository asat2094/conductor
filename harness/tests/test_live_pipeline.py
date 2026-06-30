from harness.live_pipeline import make_live_processor, build_live

A = {"id": "a", "goal": "create p.py with parse()", "task_type": "code_gen", "files": ["p.py"],
     "writes_files": ["p.py"], "context_slices": [], "contract": {"produces": ["parse"], "consumes": []},
     "verify_cmd": "", "exit_criteria": "ok", "sensitivity": "low", "estimated_tokens": 5000}

# a fake model that emits a valid FILE block (no real ollama/claude in unit tests)
_FAKE_MODEL = lambda spec, prompt: "=== FILE: p.py ===\ndef parse():\n    return 1\n=== END ==="


def test_make_live_processor_returns_callable():
    proc = make_live_processor(model_caller=_FAKE_MODEL, test_runner=lambda c, w: (0, ""),
                               differ=lambda w, p: "")
    assert callable(proc)


def test_build_live_runs_real_spine_and_accepts(tmp_path):
    result, tracker = build_live(
        [A], workdir=str(tmp_path),
        model_caller=_FAKE_MODEL,
        test_runner=lambda cmd, wd: (0, "1 passed"),
        differ=lambda wd, paths: "",
    )
    assert result.accepted == 1
    assert result.board["a"]["state"] == "ACCEPTED"
    assert (tmp_path / "p.py").read_text().startswith("def parse")


def test_build_live_escalates_when_test_stays_red(tmp_path):
    result, tracker = build_live(
        [{**A, "files": ["p.py", "test_p.py"]}], workdir=str(tmp_path),
        model_caller=_FAKE_MODEL,
        test_runner=lambda cmd, wd: (1, "AssertionError"),  # in-loop test never green
        differ=lambda wd, paths: "",
        max_attempts=2,
    )
    assert result.accepted == 0
    assert result.board["a"]["state"] in ("INLINE", "FAILED")  # escalated / not accepted (safe)
