import pytest
from harness.judge import tiebreak, JudgeQuota, JudgeError, TiebreakResult


def _q(limit=5):
    return JudgeQuota(limit=limit)


def test_tiebreak_selects_winner_when_inconclusive():
    r = tiebreak(
        candidates=["c1", "c2"], inconclusive=True, mechanical_fail=False,
        quota=_q(), judge_call=lambda cs: "c2", impl_author="gemma4", judge_model="sonnet",
    )
    assert r.decision == "select" and r.winner == "c2"


def test_tiebreak_never_overrides_a_mechanical_fail():
    with pytest.raises(JudgeError):
        tiebreak(
            candidates=["c1"], inconclusive=True, mechanical_fail=True,
            quota=_q(), judge_call=lambda cs: "c1", impl_author="gemma4", judge_model="sonnet",
        )


def test_tiebreak_refuses_when_not_inconclusive():
    with pytest.raises(JudgeError):
        tiebreak(
            candidates=["c1"], inconclusive=False, mechanical_fail=False,
            quota=_q(), judge_call=lambda cs: "c1", impl_author="gemma4", judge_model="sonnet",
        )


def test_tiebreak_escalates_on_author_collision():
    called = []
    r = tiebreak(
        candidates=["c1"], inconclusive=True, mechanical_fail=False,
        quota=_q(), judge_call=lambda cs: called.append(1) or "c1",
        impl_author="gemma4", judge_model="gemma4",     # same model -> cannot judge
    )
    assert r.decision == "escalate"
    assert not called                                    # judge never invoked


def test_tiebreak_escalates_when_quota_exhausted():
    q = JudgeQuota(limit=1)
    q.consume()                                          # already at limit
    r = tiebreak(
        candidates=["c1"], inconclusive=True, mechanical_fail=False,
        quota=q, judge_call=lambda cs: "c1", impl_author="gemma4", judge_model="sonnet",
    )
    assert r.decision == "escalate" and "quota" in r.reason


def test_tiebreak_consumes_quota_only_on_a_real_judgement():
    q = JudgeQuota(limit=2)
    tiebreak(candidates=["c1"], inconclusive=True, mechanical_fail=False, quota=q,
             judge_call=lambda cs: "c1", impl_author="gemma4", judge_model="sonnet")
    assert q.used == 1
    # author-collision escalation must NOT consume quota
    tiebreak(candidates=["c1"], inconclusive=True, mechanical_fail=False, quota=q,
             judge_call=lambda cs: "c1", impl_author="x", judge_model="x")
    assert q.used == 1


def test_tiebreak_reject_returns_reject():
    r = tiebreak(candidates=["c1"], inconclusive=True, mechanical_fail=False, quota=_q(),
                 judge_call=lambda cs: None, impl_author="gemma4", judge_model="sonnet")
    assert r.decision == "reject"


def test_tiebreak_rejects_unknown_candidate():
    with pytest.raises(JudgeError):
        tiebreak(candidates=["c1"], inconclusive=True, mechanical_fail=False, quota=_q(),
                 judge_call=lambda cs: "ghost", impl_author="gemma4", judge_model="sonnet")
