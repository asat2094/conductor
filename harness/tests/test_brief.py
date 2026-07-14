from harness.brief import SubtaskBrief, validate_brief

VALID = {
    "id": "u1",
    "goal": "add type hints to parse_order",
    "task_type": "code_edit",
    "files": ["orders.py"],
    "context_slices": [{"path": "orders.py", "start_line": 1, "end_line": 20}],
    "contract": {"produces": ["parse_order"], "consumes": [], "expected_behavior": "returns Order"},
    "verify_cmd": "pytest tests/test_orders.py::test_parse_order",
    "exit_criteria": "parse_order is fully annotated and tests pass",
    "sensitivity": "low",
}


def test_validate_accepts_well_formed_brief():
    assert validate_brief(VALID) == []


def test_validate_flags_missing_required_key():
    bad = {k: v for k, v in VALID.items() if k != "contract"}
    errs = validate_brief(bad)
    assert any("contract" in e for e in errs)


def test_validate_flags_bad_sensitivity():
    bad = {**VALID, "sensitivity": "medium"}
    errs = validate_brief(bad)
    assert any("sensitivity" in e for e in errs)


def test_subtaskbrief_from_dict_roundtrips_core_fields():
    b = SubtaskBrief.from_dict(VALID)
    assert b.id == "u1"
    assert b.contract.produces == ["parse_order"]
    assert b.context_slices[0].path == "orders.py"


def test_signature_change_requires_new_signature():
    bad = {**VALID, "task_type": "signature_change", "contract": {"produces": [], "consumes": []}}
    errs = validate_brief(bad)
    assert any("signature" in e.lower() for e in errs)


def test_signature_change_ok_with_produces():
    ok = {**VALID, "task_type": "signature_change", "contract": {"produces": ["f"], "consumes": []}}
    assert validate_brief(ok) == []


def test_refactor_requires_characterization_target_or_files():
    bad = {**VALID, "task_type": "refactor", "files": []}
    errs = validate_brief(bad)
    assert any("characterization" in e.lower() for e in errs)


def test_functional_brief_without_test_still_valid():
    # code_gen with no verify_cmd / no test file is allowed (partial-credit semantics preserved)
    ok = {**VALID, "task_type": "code_gen", "verify_cmd": "", "files": ["p.py"]}
    assert validate_brief(ok) == []
