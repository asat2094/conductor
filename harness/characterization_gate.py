"""
Golden-I/O gate for non-functional units (refactor/rename/perf).

ADR-0010, REQ-T6: Capture observable I/O of touched symbols BEFORE and AFTER
edits, then diff. Behavior must be preserved (golden match) for refactor/rename;
a drift = fail.

The I/O capture is INJECTED as `capture(symbol, inputs) -> outputs` so tests
need no real code-loading. Pure logic.
"""


def capture_golden(symbols, input_sets, *, capture):
    """
    Capture observable I/O of symbols over input sets.

    Args:
        symbols: List of symbol names (strings) to characterize
        input_sets: List of inputs to feed to each symbol
        capture: Callable(symbol, input) -> output. Exceptions are caught
                 and recorded as the string "ERROR:<exception_type>".

    Returns:
        dict: {symbol: [outputs over input_sets]}. Each exception is stored
              as the string "ERROR:<exception_type>".

    Note: This captures only the given input_sets (seed-input ceiling).
          Property-generated inputs strengthen it; off-sample drift can pass.
    """
    result = {}
    for symbol in symbols:
        outputs = []
        for inp in input_sets:
            try:
                output = capture(symbol, inp)
                outputs.append(output)
            except Exception as e:
                outputs.append(f"ERROR:{type(e).__name__}")
        result[symbol] = outputs
    return result


def diff_golden(before, after):
    """
    Compare two golden I/O captures and detect behavior drift.

    Args:
        before: dict {symbol: [outputs]} from capture_golden
        after: dict {symbol: [outputs]} from capture_golden

    Returns:
        list[str]: Names of symbols whose outputs changed (drift).
                   Empty list = behavior preserved.
    """
    drifted = []
    for symbol in before:
        if before[symbol] != after.get(symbol):
            drifted.append(symbol)
    return drifted


def characterization_ok(before, after):
    """
    Check if behavior is preserved between two golden I/O captures.

    Args:
        before: dict {symbol: [outputs]} from capture_golden
        after: dict {symbol: [outputs]} from capture_golden

    Returns:
        tuple: (passed: bool, evidence: str or list[str]).
               passed=True iff no drift.
               evidence names drifted symbols on failure.
    """
    drifted = diff_golden(before, after)
    if not drifted:
        return True, ""
    return False, drifted
