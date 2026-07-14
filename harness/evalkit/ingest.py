"""
Ingest — feed an objective MeritScorecard into the routing substrate (evalkit, ADR-0042).

Kept SEPARATE from the report on purpose: the scorecard is the objective source of truth;
turning its numbers into routing state is an explicit, opt-in step. Two sinks:
  * capability_profiles (ADR-0006/0015): max_reliable_tokens + accuracy_by_type per model.
  * ConfidenceStore (ADR-0039): seed live scores so a fresh session starts from measured reality.

`profile_key(model_name) -> profile_key` maps an eval model identity to its providers.json key
(default: identity — build eval specs with name=<provider key> and it just works).
"""
from typing import Callable, Optional

from harness.evalkit.report import MeritScorecard


def _identity(name: str) -> str:
    return name


def ingest_profiles(scorecard: MeritScorecard, profiles: dict, *,
                    profile_key: Callable[[str], str] = _identity) -> dict:
    """Merge each model's measured accuracy (rolling avg) + reliable-context ceiling into
    `profiles`. Creates a profile entry for an unseen model. Returns the mutated dict."""
    from harness.models import CapabilityProfile
    from harness.profiles import update_accuracy

    for m in scorecard.models:
        key = profile_key(m.model)
        if key not in profiles:
            profiles[key] = CapabilityProfile(max_reliable_tokens=1000, accuracy_by_type={})
        rc = m.dim("reliable_context")
        if rc is not None:
            profiles[key].max_reliable_tokens = int(rc.value)
        profiles[key].session_failures = 0            # fresh calibration clears the failure count
        for task_type, acc in m.by_task_type.items():
            update_accuracy(profiles, key, task_type, int(round(acc)))
    return profiles


def seed_confidence(scorecard: MeritScorecard, store, *,
                    profile_key: Callable[[str], str] = _identity, min_samples: int = 3):
    """Seed a ConfidenceStore from measured per-task accuracy so ADR-0039 routing starts warm.
    Sets samples to min_samples so the live score is used immediately (not the profile fallback)."""
    from harness.confidence import _key
    for m in scorecard.models:
        key = profile_key(m.model)
        for task_type, acc in m.by_task_type.items():
            store._score[_key(key, task_type)] = acc / 100.0
            store._samples[_key(key, task_type)] = min_samples
    return store


def ingest(scorecard: MeritScorecard, *, profiles_path=None, confidence_db: Optional[str] = None,
           profile_key: Callable[[str], str] = _identity) -> dict:
    """Convenience: persist the scorecard into profiles (+ optionally a confidence db).
    Returns the updated profiles dict. Both writes are opt-in via their path args."""
    from harness.profiles import load_profiles, save_profiles

    profiles = load_profiles(profiles_path) if profiles_path else load_profiles()
    ingest_profiles(scorecard, profiles, profile_key=profile_key)
    if profiles_path:
        save_profiles(profiles, profiles_path)
    else:
        save_profiles(profiles)
    if confidence_db:
        from harness.confidence import ConfidenceStore, save_store
        store = seed_confidence(scorecard, ConfidenceStore(), profile_key=profile_key)
        save_store(store, confidence_db)
    return profiles
