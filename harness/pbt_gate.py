"""
Property-based + metamorphic checker tier (ADR-0025, REQ-T10/T11). Mechanical: properties run as
real code, no model judges the result. A surviving counterexample is a hard failure that feeds the
repair loop. Hypothesis is OPTIONAL — when present it can fuzz; the deterministic example path is
always available and degrade-clean.
"""
import importlib.util
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class PBTReport:
    passed: bool
    counterexample: Optional[Any] = None
    failed_property_index: Optional[int] = None


def pbt_available() -> bool:
    return importlib.util.find_spec("hypothesis") is not None


def run_properties(properties: list[Callable[[Any], bool]], examples: list[Any]) -> PBTReport:
    """Run each property over each example input. First example that falsifies any property (or
    raises) is the counterexample. Empty properties pass vacuously."""
    for i, prop in enumerate(properties):
        for ex in examples:
            try:
                ok = bool(prop(ex))
            except Exception:
                return PBTReport(passed=False, counterexample=ex, failed_property_index=i)
            if not ok:
                return PBTReport(passed=False, counterexample=ex, failed_property_index=i)
    return PBTReport(passed=True)
