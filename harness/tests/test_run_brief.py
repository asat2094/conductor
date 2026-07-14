from harness.models import TaskType
from harness.run_brief import brief_to_subtask, brief_to_messages

BRIEF = {
    "id": "u1", "goal": "add type hints to f", "task_type": "code_edit",
    "files": ["m.py"], "writes_files": ["m.py"], "context_slices": [],
    "contract": {"produces": ["f"], "consumes": []},
    "verify_cmd": "pytest", "exit_criteria": "f annotated", "sensitivity": "low",
}


def test_brief_to_subtask_maps_fields():
    st = brief_to_subtask(BRIEF, workdir=".")
    assert st.id == "u1"
    assert st.type == TaskType.CODE_EDIT
    assert st.files == ["m.py"]
    assert st.sensitivity == "low"


def test_brief_to_subtask_estimates_tokens_when_absent():
    st = brief_to_subtask(BRIEF, workdir=".")
    assert isinstance(st.estimated_tokens, int)


def test_brief_to_messages_has_system_and_user_roles():
    msgs = brief_to_messages(BRIEF)
    roles = [m["role"] for m in msgs]
    assert "system" in roles and "user" in roles
    assert any("add type hints to f" in m["content"] for m in msgs)
