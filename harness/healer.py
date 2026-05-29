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


def auto_heal(
    subtask: SubTask,
    result: EvalResult,
    profiles: dict[str, CapabilityProfile],
    workdir: str,
    delegate_fn=None,
    evaluate_fn=None,
) -> tuple[EvalResult | None, str]:
    """
    Automatically try strategy A (shrink) then B (re-prompt) before giving up.

    Returns (new_result, strategy) where strategy is "A", "B", or "C".
    "C" means both auto strategies failed — caller should escalate to claude_agent.

    delegate_fn(workdir, task, files) → (response, code|None)
    evaluate_fn(subtask, agent, changed_files, output) → EvalResult
    """
    from harness.gemma4_call import run as _default_delegate
    from harness.evaluator import evaluate as _default_evaluate

    _delegate = delegate_fn or _default_delegate
    _evaluate = evaluate_fn or _default_evaluate

    # Strategy A: shrink scope
    shrunk = apply_shrink(subtask)
    response_a, code_a = _delegate(workdir, shrunk.description, shrunk.files)
    if code_a is not None:
        changed_a = [str(__import__("pathlib").Path(workdir) / f) for f in shrunk.files]
        result_a = _evaluate(shrunk, AgentType.GEMMA4, changed_a, response_a)
        if result_a.score >= 70:
            return result_a, "A"

    # Strategy B: re-prompt with failure detail
    reprompted = apply_reprompt(subtask, result.details)
    response_b, code_b = _delegate(workdir, reprompted.description, reprompted.files)
    if code_b is not None:
        changed_b = [str(__import__("pathlib").Path(workdir) / f) for f in reprompted.files]
        result_b = _evaluate(reprompted, AgentType.GEMMA4, changed_b, response_b)
        if result_b.score >= 70:
            return result_b, "B"

    # Both failed — escalate
    return None, "C"
