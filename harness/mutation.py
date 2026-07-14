"""Mutation-adequacy runner: generates behavior-bearing mutants and measures test kill rate.

This module implements the core mutation testing infrastructure for the conductor harness.
See ADR-0008 and ADR-0025 for rationale: cheap operators (comparison flip, boolean flip,
return-constant swap, arithmetic mutation) applied once per applicable site detect
under-specified test intent. Equivalent mutants are not handled here (kept simple).

References:
  - ADR-0008: Test adequacy gating
  - ADR-0025: Mutation-based test verification
"""

import re
from typing import Callable, Tuple, List


def mutate(source: str) -> List[Tuple[str, str]]:
    """Generate behavior-bearing mutants of a Python source string.

    Applies one mutation per applicable operator site:
    - Comparison operators: == <-> !=, < <-> >=, > <-> <=, <= <-> >, >= <-> <
    - Boolean operators: and <-> or, True <-> False
    - Return constants: return 0 <-> return 1, etc.
    - Arithmetic: + <-> -, * <-> /

    Args:
        source: Python source code string.

    Returns:
        List of (operator_name, mutated_source) tuples. Empty list if no
        behavior-bearing sites found.
    """
    mutants: List[Tuple[str, str]] = []

    # 1. Comparison operators: == != < > <= >=
    # == <-> !=
    if "==" in source and "!=" in source:
        # Both present, flip the first ==
        mutant = source.replace("==", "___TEMP_EQ___", 1)
        mutant = mutant.replace("!=", "==", 1)
        mutant = mutant.replace("___TEMP_EQ___", "!=", 1)
        if mutant != source:
            mutants.append(("comparison_eq_ne", mutant))
    elif "==" in source:
        mutant = source.replace("==", "!=", 1)
        if mutant != source:
            mutants.append(("comparison_eq_ne", mutant))
    elif "!=" in source:
        mutant = source.replace("!=", "==", 1)
        if mutant != source:
            mutants.append(("comparison_ne_eq", mutant))

    # < <-> >=
    if "<" in source and ">=" not in source:
        # Only < exists, flip to >=
        mutant = source.replace("<", ">=", 1)
        if mutant != source and "!=" not in mutant:
            mutants.append(("comparison_lt_gte", mutant))
    elif ">=" in source and "<" not in source:
        mutant = source.replace(">=", "<", 1)
        if mutant != source:
            mutants.append(("comparison_gte_lt", mutant))

    # > <-> <=
    if ">" in source and "<=" not in source and ">=" not in source:
        mutant = source.replace(">", "<=", 1)
        if mutant != source:
            mutants.append(("comparison_gt_lte", mutant))
    elif "<=" in source and ">" not in source:
        mutant = source.replace("<=", ">", 1)
        if mutant != source:
            mutants.append(("comparison_lte_gt", mutant))

    # 2. Boolean operators: and <-> or
    if " and " in source and " or " not in source:
        mutant = source.replace(" and ", " or ", 1)
        if mutant != source:
            mutants.append(("boolean_and_or", mutant))
    elif " or " in source and " and " not in source:
        mutant = source.replace(" or ", " and ", 1)
        if mutant != source:
            mutants.append(("boolean_or_and", mutant))

    # 3. Boolean literals: True <-> False
    if "True" in source and "False" not in source:
        mutant = source.replace("True", "False", 1)
        if mutant != source:
            mutants.append(("boolean_true_false", mutant))
    elif "False" in source and "True" not in source:
        mutant = source.replace("False", "True", 1)
        if mutant != source:
            mutants.append(("boolean_false_true", mutant))

    # 4. Return constants: return 0 <-> return 1, etc.
    # Match "return <digit>" pattern
    return_matches = list(re.finditer(r'\breturn\s+(\d+)\b', source))
    if return_matches:
        match = return_matches[0]
        old_val = match.group(1)
        # Flip 0 to 1, anything else to 0
        new_val = "1" if old_val == "0" else "0"
        mutant = source[:match.start(1)] + new_val + source[match.end(1):]
        if mutant != source:
            mutants.append((f"return_const_{old_val}_{new_val}", mutant))

    # 5. Arithmetic operators: + <-> -, * <-> /
    # Only flip + if not in a string/comment context (simple heuristic: not in quotes)
    if re.search(r'\s\+\s', source):  # space-padded +
        # Look for first occurrence not in string
        lines = source.split('\n')
        for i, line in enumerate(lines):
            if ' + ' in line and '#' not in line:
                mutant_line = line.replace(' + ', ' - ', 1)
                if mutant_line != line:
                    mutant_lines = lines[:i] + [mutant_line] + lines[i+1:]
                    mutant = '\n'.join(mutant_lines)
                    if mutant != source:
                        mutants.append(("arithmetic_plus_minus", mutant))
                        break

    # - (but skip unary minus and double-minus)
    if re.search(r'[^-]\s-\s', source):  # space-padded -, not starting with -
        lines = source.split('\n')
        for i, line in enumerate(lines):
            if ' - ' in line and '#' not in line:
                mutant_line = line.replace(' - ', ' + ', 1)
                if mutant_line != line:
                    mutant_lines = lines[:i] + [mutant_line] + lines[i+1:]
                    mutant = '\n'.join(mutant_lines)
                    if mutant != source:
                        mutants.append(("arithmetic_minus_plus", mutant))
                        break

    # * <-> / (skip if in comments or likely docstrings)
    if re.search(r'\s\*\s', source):
        lines = source.split('\n')
        for i, line in enumerate(lines):
            if ' * ' in line and '#' not in line and '"""' not in line:
                mutant_line = line.replace(' * ', ' / ', 1)
                if mutant_line != line:
                    mutant_lines = lines[:i] + [mutant_line] + lines[i+1:]
                    mutant = '\n'.join(mutant_lines)
                    if mutant != source:
                        mutants.append(("arithmetic_mult_div", mutant))
                        break

    return mutants


def kill_rate(
    source: str,
    *,
    test_runner: Callable[[str], bool],
) -> Tuple[float, List[str]]:
    """Measure test kill rate: fraction of mutants killed by test_runner.

    For each mutant, test_runner is called with the mutated source. If it returns
    False, the test passes on the mutant (mutant survives). If True, the test fails
    on the mutant (mutant is killed).

    Args:
        source: Original Python source code.
        test_runner: Callable(mutated_source) -> bool. True means mutant is killed
                     (test fails), False means mutant survives (test passes).

    Returns:
        (kill_rate, survivors) where kill_rate is [0.0, 1.0] and survivors is a
        list of operator names whose mutants survived. If no mutants exist,
        rate is 1.0 (vacuously adequate) and survivors is [].
    """
    mutants = mutate(source)

    if not mutants:
        # No mutants = vacuously adequate
        return 1.0, []

    survivors: List[str] = []
    killed_count = 0

    for op_name, mutant_src in mutants:
        is_killed = test_runner(mutant_src)
        if is_killed:
            killed_count += 1
        else:
            survivors.append(op_name)

    total = len(mutants)
    rate = killed_count / total if total > 0 else 1.0

    return rate, survivors


def adequacy_ok(
    source: str,
    *,
    test_runner: Callable[[str], bool],
    threshold: float = 0.8,
) -> Tuple[bool, str]:
    """Check if test adequacy meets threshold (kill rate >= threshold).

    Args:
        source: Original Python source code.
        test_runner: Callable(mutated_source) -> bool. True = mutant killed.
        threshold: Minimum required kill rate (default 0.8 = 80%).

    Returns:
        (passed, evidence) where passed is True iff kill_rate >= threshold.
        evidence is a human-readable string explaining the result.
    """
    rate, survivors = kill_rate(source, test_runner=test_runner)

    if rate >= threshold:
        return True, f"Kill rate {rate:.1%} meets threshold {threshold:.1%}"
    else:
        survivor_names = ", ".join(survivors) if survivors else "unknown"
        return (
            False,
            f"Kill rate {rate:.1%} below threshold {threshold:.1%}. "
            f"Surviving operators: {survivor_names}"
        )
