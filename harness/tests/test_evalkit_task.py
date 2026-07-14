import json
import pytest
from harness.evalkit.task import default_suite, load_suite, EvalTask, EvalSuite


def test_default_suite_grid_shape():
    s = default_suite(context_sizes=[1000, 8000], task_types=["code_gen", "test_write"])
    assert len(s) == 4
    assert all(t.origin == "builtin" for t in s)
    assert {t.context_tokens for t in s} == {1000, 8000}


def test_default_suite_prompt_embeds_context():
    s = default_suite(context_sizes=[4000], task_types=["code_gen"])
    t = s.tasks[0]
    assert len(t.prompt) > 4000               # payload embedded
    assert "validate_input" in t.prompt


def test_default_suite_grader_scores_valid_codegen():
    s = default_suite(context_sizes=[1000], task_types=["code_gen"])
    t = s.tasks[0]
    assert t.grader.grade("def validate_input(d):\n    return 'symbol' in d\n", t) == 100
    assert t.grader.grade("garbage(", t) == 0     # syntax 0 + keyword 0


def test_default_suite_language_propagates():
    s = default_suite(language="javascript", context_sizes=[1000], task_types=["code_gen"])
    assert s.tasks[0].language == "javascript"


def test_load_suite_from_list_marks_custom():
    data = [{"id": "c1", "task_type": "code_gen", "prompt": "do x",
             "context_tokens": 500, "grader": {"type": "keyword", "keywords": ["foo"]}}]
    s = load_suite(data)
    assert len(s) == 1 and s.tasks[0].origin == "custom"
    assert s.tasks[0].grader.grade("has foo", s.tasks[0]) == 100


def test_load_suite_composite_grader():
    data = {"name": "mine", "tasks": [{
        "id": "c1", "task_type": "code_gen", "prompt": "p", "context_tokens": 0,
        "grader": {"type": "composite", "graders": [
            {"type": "syntax", "weight": 1}, {"type": "keyword", "keywords": ["def"], "weight": 1}]},
    }]}
    s = load_suite(data)
    assert s.name == "mine"
    assert s.tasks[0].grader.grade("def f():\n    pass\n", s.tasks[0]) == 100


def test_load_suite_from_file(tmp_path):
    p = tmp_path / "suite.json"
    p.write_text(json.dumps([{"id": "c1", "task_type": "code_gen", "prompt": "p",
                              "context_tokens": 0, "grader": {"type": "syntax"}}]))
    s = load_suite(str(p))
    assert len(s) == 1 and s.tasks[0].origin == "custom"


def test_load_suite_unknown_grader_raises():
    with pytest.raises(ValueError):
        load_suite([{"id": "x", "task_type": "t", "prompt": "p", "context_tokens": 0,
                     "grader": {"type": "bogus"}}])


def test_default_suite_invalid_but_keyword_scores_zero():
    # regression: syntax gates keyword in the default suite (no 50 for broken-but-matching code)
    s = default_suite(context_sizes=[1000], task_types=["code_gen"])
    t = s.tasks[0]
    assert t.grader.grade("def validate_input(d)\n  return broken(", t) == 0
