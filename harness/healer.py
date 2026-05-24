from harness.models import AgentType, CapabilityProfile, EvalResult, SubTask


def build_healer_report(
    subtask: SubTask,
    result: EvalResult,
    profiles: dict[str, CapabilityProfile],
) -> str:
    agent_name = result.agent.value
    failures = profiles.get("gemma4", CapabilityProfile(0, {})).session_failures
    budget = profiles.get("gemma4", CapabilityProfile(0, {}, retry_budget=3)).retry_budget

    return (
        f"\n[ACCURACY ALERT] Subtask \"{subtask.description}\" scored {result.score}/100\n"
        f"  Details: {result.details}\n\n"
        f"  Strategy A (Shrink):    Split file scope in half, retry {agent_name}. +~30s, same cost.\n"
        f"  Strategy B (Re-prompt): Inject failure reason as constraint, retry {agent_name}. +~30s, same cost.\n"
        f"  Strategy C (Escalate):  Hand to claude_agent. +~60s, higher cost. "
        f"Marks gemma4 failure ({failures + 1}/{budget}).\n\n"
        f"  → Choose A, B, or C:"
    )


def apply_shrink(subtask: SubTask) -> SubTask:
    half = max(1, len(subtask.files) // 2)
    return SubTask(
        id=subtask.id + "_shrunk",
        description=subtask.description,
        type=subtask.type,
        files=subtask.files[:half],
        estimated_tokens=subtask.estimated_tokens // 2,
        dependencies=subtask.dependencies,
        assigned_agent=subtask.assigned_agent,
    )


def apply_reprompt(subtask: SubTask, failure_detail: str) -> SubTask:
    return SubTask(
        id=subtask.id + "_reprompt",
        description=(
            f"{subtask.description}\n\n"
            f"Previous attempt failed: {failure_detail}. "
            f"Strictly modify only the requested scope."
        ),
        type=subtask.type,
        files=subtask.files,
        estimated_tokens=subtask.estimated_tokens,
        dependencies=subtask.dependencies,
        assigned_agent=subtask.assigned_agent,
    )
