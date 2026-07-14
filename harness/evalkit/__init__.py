"""
evalkit — a generic, model-agnostic evaluation framework with objective merit scoring (ADR-0042).

Usable anywhere model evaluation is needed — not conductor-specific. Pipeline:

    specs -> evaluate() -> trials -> build_scorecard() -> MeritScorecard (objective, ranked)
                                                       -> ingest() [opt-in] -> routing profiles

Extend it: register a Dimension (dimensions.register), bring your own suite (load_suite), or
plug a custom Grader. Everything mechanical/deterministic — no model judges output (Law 1/2).
"""
from typing import Callable, Optional

from harness.evalkit.graders import (
    Grader, SyntaxGrader, KeywordGrader, OracleGrader, CompositeGrader,
)
from harness.evalkit.dimensions import (
    Dimension, DimensionScore, register as register_dimension, resolve as resolve_dimension,
    default_dimensions,
)
from harness.evalkit.task import EvalTask, EvalSuite, default_suite, load_suite
from harness.evalkit.runner import evaluate, TrialResult, model_name
from harness.evalkit.report import build_scorecard, MeritScorecard, ModelScore, score_model
from harness.evalkit.ingest import ingest, ingest_profiles, seed_confidence

__all__ = [
    "Grader", "SyntaxGrader", "KeywordGrader", "OracleGrader", "CompositeGrader",
    "Dimension", "DimensionScore", "register_dimension", "resolve_dimension", "default_dimensions",
    "EvalTask", "EvalSuite", "default_suite", "load_suite",
    "evaluate", "TrialResult", "model_name",
    "build_scorecard", "MeritScorecard", "ModelScore", "score_model",
    "ingest", "ingest_profiles", "seed_confidence",
    "calibrate",
]


def calibrate(
    model_specs: list[dict],
    suite=None,
    *,
    caller: Optional[Callable[[dict, str], str]] = None,
    trials: int = 2,
    dimensions=None,
    weights: Optional[dict] = None,
    ctx_by_model: Optional[dict] = None,
    pass_threshold: int = 70,
) -> MeritScorecard:
    """Evaluate every model spec over `suite` (default: default_suite()) and return a ranked,
    objective MeritScorecard. Pure — persisting to routing is a separate ingest() call.

    ctx_by_model maps model_name -> per-model dimension context (e.g. {"price_per_1k": 0.0014})."""
    suite = suite if suite is not None else default_suite()
    all_trials = []
    for spec in model_specs:
        all_trials.extend(evaluate(spec, suite, caller=caller, trials=trials,
                                   pass_threshold=pass_threshold))
    return build_scorecard(all_trials, dimensions=dimensions,
                           ctx_by_model=ctx_by_model, weights=weights)
