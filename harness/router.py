from harness.models import SubTask, AgentType, TaskType, CapabilityProfile
from harness.cost_model import should_inline

_ALWAYS_CLAUDE: set[TaskType] = {TaskType.RESEARCH, TaskType.CROSS_FILE_REFACTOR}


def cost_skip(subtask: SubTask) -> AgentType | None:
    """
    ROI meta-gate (REQ-R1, ADR-0016). Returns CLAUDE_INLINE when delegating the task
    would cost the orchestrator more than just doing it inline (task too small for the
    delegation overhead to pay off). Returns None to fall through to rank_providers().

    Research / cross-file-refactor are never inlined here — they reach claude_agent via
    normal routing.
    """
    if subtask.type in _ALWAYS_CLAUDE:
        return None
    if should_inline(subtask):
        return AgentType.CLAUDE_INLINE
    return None


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


def rank_providers(
    subtask: SubTask,
    providers: dict,
    profiles: dict[str, CapabilityProfile],
    busy_providers: set[str] | None = None,
    confidence: "object | None" = None,
) -> list[str]:
    """
    Return provider names ordered by ROI (reliability / cost), claude_agent last.
    Skips providers that are busy, over token limit, below the reliability
    threshold, or at session failure budget.

    ADR-0039: when a `confidence` store (harness.confidence.ConfidenceStore) is
    passed, the live per-(model, task_type) score REPLACES the static profile
    accuracy as the reliability estimate (seeded from that accuracy). A model on
    a cold streak drops below threshold and is skipped until it re-earns. Ranking
    stays deterministic given the score vector. confidence=None -> current behavior.
    """
    busy = busy_providers or set()

    if subtask.type in _ALWAYS_CLAUDE:
        return ["claude_agent"]

    candidates = []
    for name, config in providers.items():
        if name == "claude_agent":
            continue
        if name in busy:
            continue
        profile = profiles.get(name)
        if profile is None:
            continue
        if subtask.estimated_tokens > profile.max_reliable_tokens:
            continue
        if profile.session_failures >= profile.retry_budget:
            continue
        seed = profile.accuracy_by_type.get(subtask.type.value, 0.7)
        reliability = (
            confidence.get(name, subtask.type.value, seed=seed)
            if confidence is not None else seed
        )
        if reliability < 0.70:
            continue
        score = reliability / (config.cost_per_1k_tokens + 0.0001)
        candidates.append((name, score))

    ranked = [name for name, _ in sorted(candidates, key=lambda x: -x[1])]
    return ranked + ["claude_agent"]


if __name__ == "__main__":
    import json
    import os
    import sys
    from pathlib import Path
    from harness.profiles import load_profiles
    from harness.session_stats import log_delegation
    from harness.tokens import estimate_tokens

    subtask_data = json.loads(sys.argv[1])
    subtask_data["type"] = TaskType(subtask_data["type"])
    if not subtask_data.get("estimated_tokens"):
        subtask_data["estimated_tokens"] = estimate_tokens(
            subtask_data.get("files", []),
            subtask_data.get("workdir", "."),
        )
    subtask = SubTask(**subtask_data)
    profiles = load_profiles()
    # NOTE: cost_skip() is intentionally NOT applied here. The CLI exposes raw route()
    # for backward compat; the cost-skip ROI gate is wired into the orchestrate pipeline
    # in the S12 plan (see docs/superpowers/plans). Do not add cost_skip here without
    # updating harness/gemma4_delegate.sh, which consumes this CLI's output.
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
