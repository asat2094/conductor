from harness.lint_plan import lint_briefs


def _b(uid, produces=None, consumes=None, goal="do a thing", exit_criteria="tests pass"):
    return {
        "id": uid,
        "goal": goal,
        "exit_criteria": exit_criteria,
        "contract": {"produces": produces or [], "consumes": consumes or []},
    }


def test_clean_plan_has_no_errors():
    briefs = [_b("a", produces=["sym"]), _b("b", consumes=["sym"])]
    assert lint_briefs(briefs) == []


def test_flags_consumed_symbol_with_no_producer():
    briefs = [_b("b", consumes=["ghost"])]
    errs = lint_briefs(briefs)
    assert any("ghost" in e for e in errs)


def test_flags_placeholder_in_goal():
    briefs = [_b("a", goal="implement TODO later")]
    errs = lint_briefs(briefs)
    assert any("placeholder" in e.lower() for e in errs)


def test_flags_placeholder_in_exit_criteria():
    briefs = [_b("a", exit_criteria="TBD")]
    errs = lint_briefs(briefs)
    assert any("placeholder" in e.lower() for e in errs)
