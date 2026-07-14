# Cost Calibration — Current Debt and Rollout Path

## Status

The cost-skip gate (ADR-0016) and budget ceiling (ADR-0014/0034) are **design-complete but not yet load-bearing**. All providers in `harness/providers.json` are priced at `cost_per_1k_tokens: 0.0`, so cost comparisons default to token-count thresholds. This is safe — the pipeline still works — but it leaves ROI decisions on the table.

## Known Calibration Debt

### 1. Provider prices are placeholders (design §7)

File: `harness/providers.json`

```json
{
  "gemma4": {
    "cost_per_1k_tokens": 0.0,   // ← placeholder; local gemma4 is truly free
    "tier": "local"
  },
  "deepseek": {
    "cost_per_1k_tokens": 0.0,   // ← placeholder; check current DeepSeek pricing
    "tier": "cloud_cheap"
  },
  // ... other providers similarly at 0.0
}
```

All providers default to free (`0.0`). To calibrate:

1. **Check current provider pricing** from their API docs or pricing pages (DeepSeek, Gemini, NIM, OpenRouter, OpenCode Zen).
2. **Update `cost_per_1k_tokens`** in `providers.json` to real values (e.g., `0.002` for Haiku, `0.00003` for DeepSeek Flash).
3. **Verify the cost model** uses these values correctly (see ADR-0016).

### 2. Delegation cost projection lacks per-stage accounting

File: `harness/cost_model.py`

The cost model currently projects delegation cost as:

```python
_BRIEF_OVERHEAD_TOKENS = 800       # orchestrator + RED + GREEN overhead (fixed estimate)
MIN_DELEGATION_TOKENS = 800        # below this, inline is cheaper
```

This is a conservative **anchor**, not calibrated from real runs. To improve:

1. **Run a real build in audit mode** (ADR-0034) and capture per-stage token counts from the session ledger.
2. **Analyze the ledger** (`sqlite3 conductor_session.db`) to find real per-stage costs (decompose + RED author + GREEN author + full-suite run + validation).
3. **Update `_BRIEF_OVERHEAD_TOKENS`** to match observed mean + 1σ safety margin.
4. **Re-tune `MIN_DELEGATION_TOKENS`** — the crossover where delegation cost ≤ inline cost.

### 3. No run-ledger analysis tool yet

Currently, the ledger is queryable via raw SQLite. To make calibration easier:

- **Recommended next step:** write a simple `harness/analyze_ledger.py` that groups session runs by model and task type, computes mean tokens per stage, and suggests updated thresholds.

## Safe Rollout Path

### Phase 1: Audit (current, default)

```bash
# Run with budget audit — tracks spend, warns if approaching/exceeding, never blocks
result, tracker = build_live(briefs, policy={"budget_mode": "audit", "budget_usd": 50})
```

This is **safe and recommended while prices are placeholders**. The audit gate:
- Logs every unit's cost to the session ledger.
- Warns once per unpriced model (prevents silent free-counting).
- Approaches/exceeds budget: emits warning, continues.
- Never blocks or fails a unit due to cost.

### Phase 2: Calibrate (after ~5–10 audit runs)

1. Collect real spend data from audit runs.
2. Update `providers.json` with actual per-1k-token prices.
3. Recalibrate `harness/cost_model.py` from the ledger.
4. Validate the cost-skip gate: manually check a few dozen small units to confirm they route inline (< 800 tokens) rather than through the pipeline.

### Phase 3: Enforce (after calibration validated)

```bash
# Switch to enforce — blocks at budget ceiling rather than warning
result, tracker = build_live(briefs, policy={"budget_mode": "enforce", "budget_usd": 50})
```

The enforce gate now:
- Blocks new units if remaining budget is insufficient.
- Queues units on the boundary (cost approaching limit) for follow-up in a separate batch.
- Never silently overspends.

## Configuration Checklist

- [ ] Check current provider prices (DeepSeek API docs, Gemini docs, etc.).
- [ ] Update `harness/providers.json` with real `cost_per_1k_tokens` values.
- [ ] Run a real build in audit mode and capture the session ledger.
- [ ] Analyze the ledger to extract per-stage token costs.
- [ ] Update `harness/cost_model.py`: `_BRIEF_OVERHEAD_TOKENS` and `MIN_DELEGATION_TOKENS`.
- [ ] Run the test suite to ensure no regression: `python3 -m pytest -q`.
- [ ] Manual validation: check 50 small units (< 800 tokens) route to `CLAUDE_INLINE`.
- [ ] Switch to enforce mode in production.

## Related ADRs

- **ADR-0016** (cost-skip gate): Explains when inline vs. delegation is cheaper.
- **ADR-0014** (admission cost ceiling): Hard budget ceiling (enforce mode).
- **ADR-0034** (audit|enforce modes + rollup): Distinguishes audit (safe, warns) from enforce (blocks at limit).

---

**Bottom line:** The harness is fully operational in audit mode. Calibration is a measurement + tuning task, not a correctness risk. Start in audit, gather real spend data, then calibrate threshold costs and switch to enforce.

## Seeded defaults (2026-07-14)

`providers.json` now ships non-zero blended $/1k-token seeds for cloud providers
(deepseek 0.0014, gemini 0.00015, openrouter 0.001, nim 0.0005, opencode 0.001–0.0014;
local gemma4 stays 0.0) so ROI ranking discriminates on cost out of the box. These are
ballparks — run in `CostCeiling(mode="audit")` first and calibrate against real invoices
before trusting enforce-mode budgets.
