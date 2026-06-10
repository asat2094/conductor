import pytest
from harness.decompose import decompose, DecompositionError

A = {
    "id": "a", "goal": "produce parser", "task_type": "code_gen", "files": ["p.py"],
    "context_slices": [], "contract": {"produces": ["parse"], "consumes": []},
    "verify_cmd": "pytest", "exit_criteria": "parse works", "sensitivity": "low",
}
B = {
    "id": "b", "goal": "use parser", "task_type": "code_edit", "files": ["m.py"],
    "context_slices": [], "contract": {"produces": [], "consumes": ["parse"]},
    "verify_cmd": "pytest", "exit_criteria": "main uses parse", "sensitivity": "low",
}


def test_decompose_returns_ordered_waves():
    waves = decompose([B, A])  # deliberately out of order
    assert waves == [["a"], ["b"]]


def test_decompose_raises_on_invalid_brief():
    bad = {k: v for k, v in A.items() if k != "verify_cmd"}
    with pytest.raises(DecompositionError) as ei:
        decompose([bad])
    assert any("verify_cmd" in e for e in ei.value.errors)


def test_decompose_raises_on_lint_failure():
    ghost = {**B, "contract": {"produces": [], "consumes": ["nonexistent"]}}
    with pytest.raises(DecompositionError) as ei:
        decompose([ghost])
    assert any("nonexistent" in e for e in ei.value.errors)
