from harness.models import SubTask, TaskType, AgentType, CapabilityProfile
from harness.router import route

def _profiles(failures=0, max_tokens=8000, code_edit_acc=0.85):
    return {
        "gemma4": CapabilityProfile(
            max_reliable_tokens=max_tokens,
            accuracy_by_type={"code_edit": code_edit_acc, "code_gen": 0.78, "test_write": 0.75},
            session_failures=failures,
            retry_budget=3,
        ),
        "claude_agent": CapabilityProfile(
            max_reliable_tokens=180000,
            accuracy_by_type={"code_edit": 0.95},
            session_failures=0,
            retry_budget=10,
        ),
    }

def _task(type=TaskType.CODE_EDIT, tokens=2000):
    return SubTask(id="t1", description="fix it", type=type, files=["a.py"], estimated_tokens=tokens)


def test_routes_small_code_edit_to_gemma4():
    assert route(_task(), _profiles()) == AgentType.GEMMA4

def test_routes_research_always_to_claude():
    assert route(_task(type=TaskType.RESEARCH), _profiles()) == AgentType.CLAUDE_AGENT

def test_routes_cross_file_refactor_always_to_claude():
    assert route(_task(type=TaskType.CROSS_FILE_REFACTOR), _profiles()) == AgentType.CLAUDE_AGENT

def test_routes_oversized_task_to_claude():
    assert route(_task(tokens=20000), _profiles(max_tokens=8000)) == AgentType.CLAUDE_AGENT

def test_routes_to_claude_when_failures_at_budget():
    assert route(_task(), _profiles(failures=3)) == AgentType.CLAUDE_AGENT

def test_routes_to_claude_when_accuracy_low():
    assert route(_task(), _profiles(code_edit_acc=0.65)) == AgentType.CLAUDE_AGENT
