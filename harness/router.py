from harness.models import SubTask, AgentType, TaskType, CapabilityProfile

_ALWAYS_CLAUDE: set[TaskType] = {TaskType.RESEARCH, TaskType.CROSS_FILE_REFACTOR}


def route(subtask: SubTask, profiles: dict[str, CapabilityProfile]) -> AgentType:
    g = profiles["gemma4"]

    if subtask.type in _ALWAYS_CLAUDE:
        return AgentType.CLAUDE_AGENT

    if subtask.estimated_tokens > g.max_reliable_tokens:
        return AgentType.CLAUDE_AGENT

    if g.session_failures >= g.retry_budget:
        return AgentType.CLAUDE_AGENT

    if g.accuracy_by_type.get(subtask.type.value, 1.0) < 0.70:
        return AgentType.CLAUDE_AGENT

    return AgentType.GEMMA4


if __name__ == "__main__":
    import json
    import os
    import sys
    from pathlib import Path
    from harness.profiles import load_profiles
    from harness.session_stats import log_delegation

    subtask_data = json.loads(sys.argv[1])
    subtask_data["type"] = TaskType(subtask_data["type"])
    subtask = SubTask(**subtask_data)
    profiles = load_profiles()
    agent = route(subtask, profiles)

    session_id = os.environ.get("CONDUCTOR_SESSION_ID", "default")
    log_delegation(
        session_id=session_id,
        task_id=subtask.id,
        task_type=subtask.type.value,
        agent=agent.value,
        estimated_tokens=subtask.estimated_tokens,
    )

    print(agent.value)
