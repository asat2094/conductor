from harness.evalkit.runner import TrialResult
from harness.evalkit.report import build_scorecard
from harness.evalkit.ingest import ingest_profiles, seed_confidence
from harness.models import CapabilityProfile
from harness.confidence import ConfidenceStore, MIN_SAMPLES


def _tr(model, score, ctx_tokens, ttype="code_gen"):
    return TrialResult(model=model, task_id=f"{ttype}_{ctx_tokens}", task_type=ttype,
                       language="python", context_tokens=ctx_tokens, origin="builtin",
                       output="x", latency_s=1.0, tokens_used=1000,
                       score=score, passed=score >= 70)


def test_ingest_sets_reliable_context_and_accuracy():
    trials = [_tr("gemma4", 90, 1000), _tr("gemma4", 90, 8000), _tr("gemma4", 40, 32000)]
    sc = build_scorecard(trials)
    profiles = {"gemma4": CapabilityProfile(max_reliable_tokens=1, accuracy_by_type={})}
    ingest_profiles(sc, profiles)
    assert profiles["gemma4"].max_reliable_tokens == 8000       # largest passing context
    assert profiles["gemma4"].accuracy_by_type["code_gen"] > 0


def test_ingest_creates_profile_for_unseen_model():
    sc = build_scorecard([_tr("newmodel", 90, 1000)])
    profiles = {}
    ingest_profiles(sc, profiles)
    assert "newmodel" in profiles


def test_ingest_profile_key_maps_identity():
    sc = build_scorecard([_tr("ollama:gemma4:latest", 90, 1000)])
    profiles = {}
    ingest_profiles(sc, profiles, profile_key=lambda n: "gemma4")
    assert "gemma4" in profiles and "ollama:gemma4:latest" not in profiles


def test_seed_confidence_warms_store():
    sc = build_scorecard([_tr("gemma4", 88, 1000, "code_gen")])
    store = seed_confidence(sc, ConfidenceStore())
    # seeded with >= MIN_SAMPLES so the live score is used immediately (not the seed fallback)
    assert store.samples("gemma4", "code_gen") >= MIN_SAMPLES
    assert abs(store.get("gemma4", "code_gen", seed=0.5) - 0.88) < 0.001


def test_ingest_clears_session_failures():
    profiles = {"gemma4": CapabilityProfile(max_reliable_tokens=1, accuracy_by_type={},
                                            session_failures=5)}
    ingest_profiles(build_scorecard([_tr("gemma4", 90, 1000)]), profiles)
    assert profiles["gemma4"].session_failures == 0
