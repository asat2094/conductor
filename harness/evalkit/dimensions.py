"""
Dimensions — pluggable, objective scoring axes (evalkit, ADR-0042).

Each Dimension reduces a model's trial results to one DimensionScore: a raw objective
value (seconds, dollars, %, tokens) PLUS a normalized 0-100 (higher = better) so axes with
different units combine into one merit score. All deterministic — no subjective input.

Registry mirrors the optimizer/language facades: register(name, factory) / resolve(name).
Bring your own axis by registering a callable that returns a DimensionScore.
"""
from dataclasses import dataclass, field
from typing import Any, Callable

_REGISTRY: dict[str, Callable[[], "Dimension"]] = {}


@dataclass
class DimensionScore:
    name: str
    value: float          # raw objective measurement (unit below)
    unit: str
    normalized: float     # 0-100, higher = better (comparable across axes)
    detail: dict = field(default_factory=dict)


class Dimension:
    """Base: implement compute(trials, ctx) -> DimensionScore. `trials` are duck-typed objects
    with .score .passed .latency_s .tokens_used .context_tokens .task_type .output attributes."""
    name = "dimension"
    unit = ""

    def compute(self, trials: list, ctx: dict) -> DimensionScore:  # pragma: no cover - abstract
        raise NotImplementedError


def register(name: str, factory: Callable[[], Dimension]) -> None:
    _REGISTRY[name] = factory


def resolve(name: str) -> Dimension:
    if name not in _REGISTRY:
        raise KeyError(f"unknown dimension {name!r}; registered: {sorted(_REGISTRY)}")
    return _REGISTRY[name]()


def default_dimensions() -> list[Dimension]:
    """The standard objective scorecard axes."""
    return [resolve(n) for n in
            ("accuracy", "reliable_context", "latency", "cost_per_pass",
             "refusal_rate", "context_degradation")]


def _clamp(x: float) -> float:
    return max(0.0, min(100.0, x))


class AccuracyDimension(Dimension):
    name = "accuracy"
    unit = "score"

    def compute(self, trials, ctx):
        scores = [t.score for t in trials]
        mean = sum(scores) / len(scores) if scores else 0.0
        return DimensionScore(self.name, round(mean, 1), self.unit, _clamp(mean),
                              {"n": len(scores)})


class ReliableContextDimension(Dimension):
    """Largest context size whose mean score clears the pass threshold (default 70)."""
    name = "reliable_context"
    unit = "tokens"

    def compute(self, trials, ctx):
        threshold = ctx.get("pass_threshold", 70)
        # Bucket PER (task_type, context) so a weak task type can't drag a strong one's ceiling to 0
        # (a pooled cross-type mean did exactly that). Per-type weakness is handled separately by the
        # router's accuracy_by_type gate; this ceiling is the model's best demonstrated context reach.
        by_type: dict[str, dict[int, list]] = {}
        all_ctx: set[int] = set()
        for t in trials:
            by_type.setdefault(t.task_type, {}).setdefault(t.context_tokens, []).append(t.score)
            all_ctx.add(t.context_tokens)
        per_type: dict[str, int] = {}
        for ttype, ctxmap in by_type.items():
            mx = 0
            for tokens, scores in ctxmap.items():
                if sum(scores) / len(scores) >= threshold:
                    mx = max(mx, tokens)
            per_type[ttype] = mx
        reliable = max(per_type.values()) if per_type else 0
        max_ctx = max(all_ctx) if all_ctx else 1
        return DimensionScore(self.name, float(reliable), self.unit,
                              _clamp(100 * reliable / max_ctx) if max_ctx else 0.0,
                              {"max_context": max_ctx, "threshold": threshold,
                               "per_task_type": per_type})


class LatencyDimension(Dimension):
    """Mean wall-clock per call. Normalized against a ceiling (default 60s): at/above ceiling -> 0."""
    name = "latency"
    unit = "s"

    def compute(self, trials, ctx):
        ceiling = ctx.get("latency_ceiling_s", 60.0)
        lat = [t.latency_s for t in trials]
        mean = sum(lat) / len(lat) if lat else 0.0
        return DimensionScore(self.name, round(mean, 2), self.unit,
                              _clamp(100 * (1 - mean / ceiling)),
                              {"ceiling_s": ceiling})


class CostPerPassDimension(Dimension):
    """Dollar cost per PASSING task = total token cost / #passes. Local (price 0) -> cost 0 -> 100.
    No passes -> cost is infinite -> normalized 0."""
    name = "cost_per_pass"
    unit = "usd"

    def compute(self, trials, ctx):
        price_per_1k = ctx.get("price_per_1k", 0.0)
        # A free/local model costs 0 regardless of pass count — must score full BEFORE the
        # no-passes branch, else a struggling-but-free model is unfairly zeroed on cost.
        if price_per_1k == 0:
            return DimensionScore(self.name, 0.0, self.unit, 100.0, {"free": True})
        total_cost = sum(price_per_1k * (t.tokens_used / 1000.0) for t in trials)
        passes = sum(1 for t in trials if t.passed)
        if passes == 0:
            return DimensionScore(self.name, float("inf"), self.unit, 0.0, {"passes": 0})
        cpp = total_cost / passes
        budget = ctx.get("cost_budget_per_pass", 0.05)  # $/pass at which normalized hits 0
        norm = 100.0 if price_per_1k == 0 else _clamp(100 * (1 - cpp / budget))
        return DimensionScore(self.name, round(cpp, 6), self.unit, norm,
                              {"passes": passes, "total_cost": round(total_cost, 6)})


class RefusalRateDimension(Dimension):
    """Fraction of empty/blank outputs (a refusal or timeout). Lower is better."""
    name = "refusal_rate"
    unit = "fraction"

    def compute(self, trials, ctx):
        n = len(trials) or 1
        refusals = sum(1 for t in trials if not (t.output or "").strip())
        rate = refusals / n
        return DimensionScore(self.name, round(rate, 3), self.unit,
                              _clamp(100 * (1 - rate)), {"refusals": refusals, "n": n})


class ContextDegradationDimension(Dimension):
    """Accuracy drop from the smallest to the largest context (percentage points).
    A flat model (no drop) normalizes to 100; a 100-point collapse -> 0."""
    name = "context_degradation"
    unit = "points"

    def compute(self, trials, ctx):
        by_ctx: dict[int, list] = {}
        for t in trials:
            by_ctx.setdefault(t.context_tokens, []).append(t.score)
        if len(by_ctx) < 2:
            # Can't measure degradation from one probe — return NEUTRAL (not a perfect 100), so a
            # thinly-probed model isn't rewarded as if it were proven robust across context sizes.
            return DimensionScore(self.name, 0.0, self.unit, 50.0,
                                  {"note": "insufficient data (<2 context sizes)",
                                   "n_contexts": len(by_ctx)})
        sizes = sorted(by_ctx)
        lo = sum(by_ctx[sizes[0]]) / len(by_ctx[sizes[0]])
        hi = sum(by_ctx[sizes[-1]]) / len(by_ctx[sizes[-1]])
        drop = lo - hi                      # positive = degraded with more context
        return DimensionScore(self.name, round(drop, 1), self.unit,
                              _clamp(100 - max(0.0, drop)),
                              {"low_ctx_acc": round(lo, 1), "high_ctx_acc": round(hi, 1)})


for _d in (AccuracyDimension, ReliableContextDimension, LatencyDimension,
           CostPerPassDimension, RefusalRateDimension, ContextDegradationDimension):
    register(_d.name, _d)
