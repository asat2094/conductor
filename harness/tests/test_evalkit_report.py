import json
from harness.evalkit.runner import TrialResult
from harness.evalkit.report import build_scorecard, score_model, MeritScorecard


def _tr(model, score, ctx_tokens=1000, ttype="code_gen", origin="builtin",
        latency=1.0, tokens=1000, passed=None, output="x"):
    return TrialResult(model=model, task_id=f"{ttype}_{ctx_tokens}", task_type=ttype,
                       language="python", context_tokens=ctx_tokens, origin=origin,
                       output=output, latency_s=latency, tokens_used=tokens,
                       score=score, passed=(score >= 70 if passed is None else passed))


def test_scorecard_ranks_by_merit():
    strong = [_tr("A", 100, c) for c in (1000, 8000, 32000)]
    weak = [_tr("B", 30, c) for c in (1000, 8000, 32000)]
    sc = build_scorecard(strong + weak)
    assert [m.model for m in sc.models] == ["A", "B"]     # A ranked first
    assert sc.leader().model == "A"
    assert sc.models[0].merit > sc.models[1].merit


def test_scorecard_by_task_type_and_origin_breakdown():
    trials = [_tr("A", 90, ttype="code_gen", origin="builtin"),
              _tr("A", 50, ttype="test_write", origin="custom")]
    m = score_model(trials)
    assert m.by_task_type == {"code_gen": 90.0, "test_write": 50.0}
    assert set(m.by_origin) == {"builtin", "custom"}


def test_scorecard_includes_all_default_dimensions():
    m = score_model([_tr("A", 100)])
    names = {d.name for d in m.dimensions}
    assert {"accuracy", "reliable_context", "latency", "cost_per_pass",
            "refusal_rate", "context_degradation"} <= names


def test_weights_shift_merit():
    trials = [_tr("A", 100, latency=59.0)]     # perfect accuracy, terrible latency
    acc_heavy = score_model(trials, weights={"accuracy": 10, "latency": 0.1}).merit
    lat_heavy = score_model(trials, weights={"accuracy": 0.1, "latency": 10}).merit
    assert acc_heavy > lat_heavy


def test_ctx_per_model_affects_cost():
    trials = [_tr("paid", 100, tokens=1000, passed=True)]
    # paid model with a price -> cost_per_pass dimension penalized vs a free one
    paid = score_model(trials, ctx={"price_per_1k": 0.02, "cost_budget_per_pass": 0.01})
    free = score_model(trials, ctx={"price_per_1k": 0.0})
    assert paid.dim("cost_per_pass").normalized < free.dim("cost_per_pass").normalized


def test_render_json_and_publish(tmp_path):
    sc = build_scorecard([_tr("A", 100)])
    d = sc.render_json()
    assert d["leaderboard"][0]["model"] == "A"
    p = tmp_path / "report.json"
    sc.publish(str(p))
    loaded = json.loads(p.read_text())
    assert loaded["leaderboard"][0]["merit"] == sc.models[0].merit


def test_render_text_has_leaderboard():
    sc = build_scorecard([_tr("A", 100), _tr("B", 20)])
    txt = sc.render_text()
    assert "#1" in txt and "A" in txt and "merit=" in txt
