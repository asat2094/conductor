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


def test_cost_ceiling_audit_mode_never_blocks_but_flags():
    c = CostCeiling(limit=100, mode="audit")
    assert c.spend(80) is True
    assert c.spend(50) is True          # audit never blocks
    assert c.spent == 130
    assert c.breached is True
    assert c.warnings                    # a breach warning recorded


def test_cost_ceiling_enforce_still_blocks():
    c = CostCeiling(limit=100, mode="enforce")
    assert c.spend(80) is True
    assert c.spend(50) is False          # enforce blocks the overspend
    assert c.spent == 80


def test_cost_ceiling_rollup_folds_child_spend():
    c = CostCeiling(limit=100, mode="audit")
    c.spend(40)
    c.rollup(30)                          # sub-build spend rolls into parent
    assert c.spent == 70


def test_warn_unpriced_is_one_time():
    c = CostCeiling(limit=100)
    c.warn_unpriced("mystery-model")
    c.warn_unpriced("mystery-model")
    assert sum("mystery-model" in w for w in c.warnings) == 1


def test_rollup_returns_false_when_enforce_blocks():
    c = CostCeiling(limit=100, mode="enforce")
    c.spend(80)
    assert c.rollup(30) is False        # blocked child rollup is visible, not silent
    assert c.spent == 80
