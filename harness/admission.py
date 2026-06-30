"""
Provider admission control — per-provider AIMD concurrency limiter, retry-allowlist, cost ceiling.

Per ADR-0014: Admission is separate from routing. Throttling cuts concurrency cap,
not escalation. Retryable errors (429, timeout, connection, 5xx, 503, 502) retry
at same maker; non-retryable escalate. Cost ceiling blocks rather than balloons.
"""


class AIMDLimiter:
    """
    Additive Increase, Multiplicative Decrease concurrency limiter.

    Models congestion control: on success, additively increase cap (+1 up to max_cap).
    On throttle, multiplicatively halve cap (//2 down to min_cap).
    """

    def __init__(self, start: int = 4, min_cap: int = 1, max_cap: int = 16):
        """Initialize AIMD limiter.

        Args:
            start: Initial in-flight capacity.
            min_cap: Floor for cap (multiplicative decrease stops here).
            max_cap: Ceiling for cap (additive increase stops here).
        """
        self.cap = start
        self.min_cap = min_cap
        self.max_cap = max_cap

    def on_success(self) -> None:
        """On successful request: additively increase cap by 1 (up to max_cap)."""
        self.cap = min(self.cap + 1, self.max_cap)

    def on_throttle(self) -> None:
        """On throttle (429, etc.): multiplicatively halve cap (down to min_cap)."""
        self.cap = max(self.cap // 2, self.min_cap)

    def can_admit(self, in_flight: int) -> bool:
        """Check if in_flight count is within cap.

        Args:
            in_flight: Current in-flight request count.

        Returns:
            True if in_flight < cap, False otherwise.
        """
        return in_flight < self.cap


# Retryable error tokens (case-insensitive)
RETRYABLE = {"429", "timeout", "connection", "5xx", "503", "502"}


def is_retryable(error_msg: str) -> bool:
    """Check if error is retryable.

    Retryable errors include: 429, timeout, connection, 5xx, 503, 502.
    Non-retryable: quality misses, validation errors, etc.
    Matching is case-insensitive substring of any token.

    Args:
        error_msg: Error message to check.

    Returns:
        True if error is retryable, False otherwise.
    """
    msg_lower = error_msg.lower()
    for token in RETRYABLE:
        if token.lower() in msg_lower:
            return True
    return False


class CostCeiling:
    """Per-run cost ceiling (ADR-0014/0034). Two modes:
    - 'enforce' (default): blocks spend that would exceed the limit (does not record it).
    - 'audit': never blocks — records all spend, sets `breached` + a warning once the limit is
      crossed (safe audit-before-enforce rollout while the cost model is uncalibrated, design §7).
    `rollup(child_spent)` folds a sub-build's spend into this parent ceiling."""

    def __init__(self, limit: int, mode: str = "enforce"):
        self.limit = limit
        self.mode = mode
        self._spent = 0
        self.breached = False
        self.warnings: list = []

    def spend(self, amount: int) -> bool:
        """enforce: returns False (and does not record) if it would exceed. audit: always records,
        returns True, sets breached + a one-time warning once the limit is crossed."""
        would = self._spent + amount
        if would > self.limit:
            if self.mode == "audit":
                self._spent = would
                if not self.breached:
                    self.breached = True
                    self.warnings.append(f"budget breached (audit): {self._spent} > {self.limit}")
                return True
            return False  # enforce: block, do not record
        self._spent += amount
        return True

    def rollup(self, child_spent: int) -> None:
        """Roll a sub-build's spend up into this (parent) ceiling (ADR-0034)."""
        self.spend(child_spent)

    def warn_unpriced(self, model: str) -> None:
        """One-time warning for a model with no price entry (don't silently count it free)."""
        msg = f"unpriced model '{model}' — counted as 0"
        if msg not in self.warnings:
            self.warnings.append(msg)

    @property
    def spent(self) -> int:
        """Total cumulative spend."""
        return self._spent

    @property
    def remaining(self) -> int:
        """Remaining budget."""
        return self.limit - self._spent
