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
    """Per-run cost ceiling: blocks spend if it would exceed limit."""

    def __init__(self, limit: int):
        """Initialize cost ceiling.

        Args:
            limit: Maximum cumulative spend allowed.
        """
        self.limit = limit
        self._spent = 0

    def spend(self, amount: int) -> bool:
        """Attempt to spend cost.

        If cumulative spend would exceed limit, returns False without recording.
        Otherwise records the spend and returns True.

        Args:
            amount: Cost to spend.

        Returns:
            True if spend allowed and recorded, False if would exceed (not recorded).
        """
        if self._spent + amount > self.limit:
            return False
        self._spent += amount
        return True

    @property
    def spent(self) -> int:
        """Total cumulative spend."""
        return self._spent

    @property
    def remaining(self) -> int:
        """Remaining budget."""
        return self.limit - self._spent
