from harness.admission import AIMDLimiter, is_retryable, CostCeiling


def test_aimd_additive_increase_multiplicative_decrease():
    lim = AIMDLimiter(start=4, min_cap=1, max_cap=8)
    lim.on_success(); assert lim.cap == 5
    lim.on_throttle(); assert lim.cap == 2      # halved
    lim.on_throttle(); assert lim.cap == 1      # floor at min_cap


def test_aimd_caps_at_max():
    lim = AIMDLimiter(start=7, max_cap=8)
    lim.on_success(); lim.on_success(); lim.on_success()
    assert lim.cap == 8


def test_can_admit():
    lim = AIMDLimiter(start=2)
    assert lim.can_admit(1) is True
    assert lim.can_admit(2) is False


def test_is_retryable():
    assert is_retryable("HTTP 429 Too Many Requests") is True
    assert is_retryable("connection reset") is True
    assert is_retryable("quality score 40 below threshold") is False


def test_cost_ceiling_allows_then_blocks():
    c = CostCeiling(limit=100)
    assert c.spend(60) is True
    assert c.spend(30) is True
    assert c.spent == 90
    assert c.spend(20) is False    # would exceed -> blocked, not recorded
    assert c.spent == 90
    assert c.remaining == 10
