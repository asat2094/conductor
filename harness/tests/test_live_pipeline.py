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


# --- ADR-0038 end-to-end: judge reachable + logged via the production path ---

def _judge_kw(tmp_path, judge):
    return dict(
        workdir=str(tmp_path), model_caller=_FAKE_MODEL,
        test_runner=lambda cmd, wd: (0, ""), differ=lambda wd, paths: "",
        progress=False, judge=judge, no_test_inconclusive=True,  # no test file -> inconclusive
    )


def test_build_live_judge_fires_and_accepts_inconclusive_unit(tmp_path):
    result, tracker = build_live([A], **_judge_kw(tmp_path, judge=lambda art: True))
    assert result.accepted == 1                       # judge (sonnet ≠ gemma4) actually decided
    ev = [e for e in tracker.events() if e["state"] == "JUDGE_TIEBREAK"]
    assert len(ev) == 1 and ev[0]["meta"]["decision"] == "select"


def test_build_live_judge_author_separation_uses_real_identities(tmp_path):
    # force judge model == impl model via policy -> author-separation escalates, never accepts
    result, tracker = build_live(
        [A], policy={"judge": {"backend": "ollama", "model": "gemma4:latest"}},
        **_judge_kw(tmp_path, judge=lambda art: True))
    assert result.accepted == 0
    ev = [e for e in tracker.events() if e["state"] == "JUDGE_TIEBREAK"]
    assert ev and ev[0]["meta"]["decision"] == "escalate"


def test_build_live_judge_quota_is_shared_per_dag(tmp_path):
    # 2 inconclusive units, quota ceil(0.10*2)=1 -> first judged, second escalates on quota
    B = {**A, "id": "b", "files": ["q.py"], "writes_files": ["q.py"],
         "contract": {"produces": ["q"], "consumes": []}}
    model = lambda spec, prompt: ("=== FILE: p.py ===\nx=1\n=== END ==="
                                  if "p.py" in prompt else "=== FILE: q.py ===\ny=1\n=== END ===")
    kw = _judge_kw(tmp_path, judge=lambda art: True)
    kw["model_caller"] = model
    result, tracker = build_live([A, B], **kw)
    decisions = sorted(e["meta"]["decision"] for e in tracker.events()
                       if e["state"] == "JUDGE_TIEBREAK")
    assert decisions.count("select") == 1             # quota of 1 consumed once
    assert "escalate" in decisions                    # the other unit hit the quota


def test_build_live_webhook_sink_receives_events(tmp_path):
    posted = []
    result, tracker = build_live(
        [A], workdir=str(tmp_path), model_caller=_FAKE_MODEL,
        test_runner=lambda c, w: (0, ""), differ=lambda w, p: "",
        progress=False, webhook_post=posted.append,
    )
    assert result.accepted == 1
    assert any(e.get("state") == "ACCEPTED" for e in posted)   # external PM saw the build


def test_build_live_high_sensitivity_is_high_stakes(tmp_path):
    # high sensitivity -> high_stakes gate -> oracle mandatory -> oracle_passed=None rejects
    hs = {**A, "sensitivity": "high"}
    result, tracker = build_live(
        [hs], workdir=str(tmp_path), model_caller=_FAKE_MODEL,
        test_runner=lambda c, w: (0, ""), differ=lambda w, p: "",
        progress=False, max_attempts=1,
    )
    assert result.accepted == 0        # no held-out oracle ran -> high-stakes unit not accepted


def test_build_live_probes_annotate_advisory_only(tmp_path):
    # probes=True annotates briefs (candidate_criteria) without gating or mutating the caller's list
    briefs = [dict(A)]
    result, tracker = build_live(
        briefs, workdir=str(tmp_path), model_caller=_FAKE_MODEL,
        test_runner=lambda c, w: (0, ""), differ=lambda w, p: "",
        progress=False, probes=True,
    )
    assert result.accepted == 1                        # advisory: never blocks
    assert "candidate_criteria" not in briefs[0]       # caller's brief untouched


def test_build_live_codegraph_reverifies_per_wave_degrade_clean(tmp_path):
    # codegraph=True with no codegraph CLI -> degrade-clean 'unverified'; per-wave reverify runs
    result, tracker = build_live(
        [A], workdir=str(tmp_path), model_caller=_FAKE_MODEL,
        test_runner=lambda c, w: (0, ""), differ=lambda w, p: "",
        progress=False, codegraph=True,
    )
    assert result.accepted == 1
    assert result.verify.status in ("unverified", "verified")   # never blocked the build
