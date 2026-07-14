"""
MeritScorecard — objective, ranked, publishable evaluation report (evalkit, ADR-0042).

Aggregates trial results into per-model dimension scores, a weighted composite "merit", and
per-task-type / per-suite-origin breakdowns, then ranks models into a leaderboard. Everything
here is deterministic arithmetic over mechanical measurements — no subjective input — so the
published report is a defensible, objective basis for decisions (and for the routing ingest).
"""
import json
from dataclasses import dataclass, field
from typing import Optional

from harness.evalkit.dimensions import Dimension, DimensionScore, default_dimensions


@dataclass
class ModelScore:
    model: str
    merit: float                              # weighted composite of dimension.normalized, 0-100
    dimensions: list[DimensionScore]
    by_task_type: dict[str, float]            # mean grader score per task_type
    by_origin: dict[str, float]               # mean grader score per suite origin (builtin/custom)
    trials: int

    def dim(self, name: str) -> Optional[DimensionScore]:
        return next((d for d in self.dimensions if d.name == name), None)


@dataclass
class MeritScorecard:
    models: list[ModelScore] = field(default_factory=list)   # ranked, best merit first
    weights: dict[str, float] = field(default_factory=dict)

    def leader(self) -> Optional[ModelScore]:
        return self.models[0] if self.models else None

    # -- rendering -------------------------------------------------------

    def render_json(self) -> dict:
        return {
            "weights": self.weights,
            "leaderboard": [
                {
                    "model": m.model, "merit": m.merit, "trials": m.trials,
                    "dimensions": [
                        {"name": d.name, "value": d.value, "unit": d.unit,
                         "normalized": d.normalized, "detail": d.detail}
                        for d in m.dimensions
                    ],
                    "by_task_type": m.by_task_type,
                    "by_origin": m.by_origin,
                }
                for m in self.models
            ],
        }

    def render_text(self) -> str:
        lines = ["MERIT SCORECARD (objective, mechanical)", "=" * 40]
        for rank, m in enumerate(self.models, 1):
            lines.append(f"#{rank}  {m.model:<28} merit={m.merit:.1f}  (trials={m.trials})")
            for d in m.dimensions:
                val = "inf" if d.value == float("inf") else f"{d.value:g}"
                lines.append(f"      {d.name:<20} {val:>10} {d.unit:<8} -> {d.normalized:.1f}/100")
            bt = " ".join(f"{k}={v:.0f}" for k, v in sorted(m.by_task_type.items()))
            bo = " ".join(f"{k}={v:.0f}" for k, v in sorted(m.by_origin.items()))
            lines.append(f"      by_task_type: {bt}")
            lines.append(f"      by_origin:    {bo}")
        return "\n".join(lines)

    def publish(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.render_json(), f, indent=2, default=lambda o: None)


def _mean(xs: list) -> float:
    return round(sum(xs) / len(xs), 1) if xs else 0.0


def _group_mean_score(trials: list, key) -> dict:
    buckets: dict[str, list] = {}
    for t in trials:
        buckets.setdefault(getattr(t, key), []).append(t.score)
    return {k: _mean(v) for k, v in buckets.items()}


def score_model(trials: list, *, dimensions: Optional[list[Dimension]] = None,
                ctx: Optional[dict] = None, weights: Optional[dict] = None) -> ModelScore:
    dims = dimensions or default_dimensions()
    ctx = ctx or {}
    computed = [d.compute(trials, ctx) for d in dims]
    w = weights or {d.name: 1.0 for d in computed}
    total_w = sum(w.get(d.name, 1.0) for d in computed) or 1.0
    merit = round(sum(d.normalized * w.get(d.name, 1.0) for d in computed) / total_w, 1)
    return ModelScore(
        model=trials[0].model if trials else "?",
        merit=merit, dimensions=computed,
        by_task_type=_group_mean_score(trials, "task_type"),
        by_origin=_group_mean_score(trials, "origin"),
        trials=len(trials),
    )


def build_scorecard(trials: list, *, dimensions: Optional[list[Dimension]] = None,
                    ctx_by_model: Optional[dict] = None,
                    weights: Optional[dict] = None) -> MeritScorecard:
    """Group a flat trial list by model, score each, rank by merit (desc)."""
    ctx_by_model = ctx_by_model or {}
    by_model: dict[str, list] = {}
    for t in trials:
        by_model.setdefault(t.model, []).append(t)
    scored = [
        score_model(mt, dimensions=dimensions,
                    ctx=ctx_by_model.get(model, {}), weights=weights)
        for model, mt in by_model.items()
    ]
    scored.sort(key=lambda m: m.merit, reverse=True)
    return MeritScorecard(models=scored, weights=weights or {})
