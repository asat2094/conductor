"""
Adaptive confidence-scored routing (ADR-0039, REQ-ROUTE-ADAPTIVE).

A live reliability estimate per (model, task_type), seeded from the offline
capability profile and moved by every gate outcome within a run. The router
ranks admissible models by ROI = live_score / cost, so a model on a hot/cold
streak is preferred/avoided accordingly — WITHOUT the score ever deciding
correctness (Law 2 intact: it only picks WHO makes, gates still decide GREEN).

Bounded exponential update (recency-weighted, one result never swings routing
wildly), a min-sample guard (fall back to the seed until enough live data), and
a floor below which a model is skipped for that task_type until it re-earns.
"""
from dataclasses import dataclass, field

ALPHA = 0.3          # EMA weight — higher = more recency-sensitive
MIN_SAMPLES = 3      # below this, use the seed (avoid one bad draw blacklisting a model)
FLOOR = 0.2          # live score below this -> model skipped for the task_type until re-proven
DEFAULT_SEED = 0.7   # when the profile has no accuracy for a task_type


def _key(model: str, task_type: str) -> tuple[str, str]:
    return (model, task_type)


@dataclass
class ConfidenceStore:
    """In-memory, session-scoped confidence state. Seeded from profile accuracy."""
    _score: dict[tuple[str, str], float] = field(default_factory=dict)
    _samples: dict[tuple[str, str], int] = field(default_factory=dict)

    def get(self, model: str, task_type: str, seed: float | None = None) -> float:
        """Live score if enough samples exist, else the seed (profile accuracy)."""
        k = _key(model, task_type)
        base = DEFAULT_SEED if seed is None else seed
        if self._samples.get(k, 0) < MIN_SAMPLES:
            return base
        return self._score[k]

    def update(self, model: str, task_type: str, passed: bool, seed: float | None = None) -> float:
        """Nudge the score by a gate outcome. ACCEPT -> up, FAIL/escalate -> down."""
        k = _key(model, task_type)
        base = DEFAULT_SEED if seed is None else seed
        prev = self._score.get(k, base)
        target = 1.0 if passed else 0.0
        new = prev + ALPHA * (target - prev)
        self._score[k] = new
        self._samples[k] = self._samples.get(k, 0) + 1
        return new

    def samples(self, model: str, task_type: str) -> int:
        return self._samples.get(_key(model, task_type), 0)

    def admissible(self, model: str, task_type: str, seed: float | None = None) -> bool:
        """False only once we have enough live data AND the score is below the floor.
        Cold-start (few samples) is always admissible — the seed/profile filters still apply."""
        k = _key(model, task_type)
        if self._samples.get(k, 0) < MIN_SAMPLES:
            return True
        return self._score[k] >= FLOOR
