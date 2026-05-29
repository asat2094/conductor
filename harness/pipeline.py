"""
pipeline.py — end-to-end route → delegate → evaluate → auto_heal in one call.

Programmatic API:
    from harness.pipeline import run_pipeline
    result = run_pipeline(subtask, workdir="/my/project", diff_mode=False)
    # PipelineResult.final_score, .strategy, .agent_used, .eval_result

CLI:
    python3 -m harness.pipeline '{
        "id": "t1",
        "description": "Add docstring to validate_order",
        "type": "code_edit",
        "files": ["backend/orders.py"]
    }' [--workdir /path] [--diff] [--no-heal]

    estimated_tokens optional — auto-derived from file sizes.

Exit codes:
    0  accepted (score >= 70 or healed to >= 70)
    2  strategy C needed — escalate to claude_agent
    1  routed to claude_agent (not a failure, just a redirect)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from harness.evaluator import evaluate
from harness.gemma4_call import run as gemma4_run
from harness.healer import auto_heal as _auto_heal
from harness.models import AgentType, EvalResult, SubTask
from harness.profiles import load_profiles, save_profiles, update_accuracy
from harness.router import route
from harness.session_stats import log_delegation, update_score
from harness.tokens import estimate_tokens


@dataclass
class PipelineResult:
    subtask_id: str
    agent_used: AgentType
    final_score: int
    strategy: str | None       # None = no healing needed; "A"/"B"/"C" = healer ran
    eval_result: EvalResult
    routed_to_claude: bool = False  # True when router sent to claude_agent


def run_pipeline(
    subtask: SubTask,
    workdir: str = ".",
    diff_mode: bool = False,
    auto_heal: bool = True,
) -> PipelineResult:
    """
    Full pipeline for a single subtask:
        1. Route — choose gemma4 or claude_agent
        2. Delegate to gemma4 (if routed there)
        3. Evaluate output
        4. Auto-heal (A→B) if score < 70 and auto_heal=True
        5. Return PipelineResult

    When routed to claude_agent, returns a PipelineResult with routed_to_claude=True
    and score=-1 (caller handles claude_agent delegation externally).
    """
    session_id = os.environ.get("CONDUCTOR_SESSION_ID", "default")

    # Auto-estimate tokens if missing
    if not subtask.estimated_tokens:
        subtask.estimated_tokens = estimate_tokens(subtask.files, workdir)

    profiles = load_profiles()
    agent = route(subtask, profiles)

    log_delegation(
        session_id=session_id,
        task_id=subtask.id,
        task_type=subtask.type.value,
        agent=agent.value,
        estimated_tokens=subtask.estimated_tokens,
    )

    if agent == AgentType.CLAUDE_AGENT:
        dummy = EvalResult(
            subtask_id=subtask.id, agent=agent, score=-1,
            syntax_score=0, test_score=0, scope_score=0, semantic_score=0,
            details="routed to claude_agent",
        )
        return PipelineResult(
            subtask_id=subtask.id, agent_used=agent,
            final_score=-1, strategy=None, eval_result=dummy,
            routed_to_claude=True,
        )

    # Delegate to gemma4
    response, code = gemma4_run(workdir, subtask.description, subtask.files, diff_mode=diff_mode)
    changed = [str(Path(workdir) / f) for f in subtask.files]
    result = evaluate(subtask, agent, changed, response if code is None else code)
    update_score(subtask.id, result.score)

    strategy = None
    if auto_heal and result.score < 70:
        healed, strategy = _auto_heal(subtask, result, profiles, workdir, diff_mode=diff_mode)
        if healed is not None:
            result = healed
            update_score(healed.subtask_id, healed.score)

    # Update rolling accuracy and persist
    update_accuracy(profiles, "gemma4", subtask.type.value, result.score)
    save_profiles(profiles)

    return PipelineResult(
        subtask_id=subtask.id, agent_used=agent,
        final_score=result.score, strategy=strategy, eval_result=result,
    )


if __name__ == "__main__":
    import json
    import sys

    from harness.models import TaskType
    from harness.tokens import estimate_tokens

    args = sys.argv[1:]
    diff_mode = "--diff" in args
    no_heal = "--no-heal" in args
    args = [a for a in args if a not in ("--diff", "--no-heal")]

    workdir = "."
    if "--workdir" in args:
        idx = args.index("--workdir")
        workdir = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    if not args:
        print(
            "Usage: python3 -m harness.pipeline '<subtask_json>' [--workdir PATH] [--diff] [--no-heal]",
            file=sys.stderr,
        )
        sys.exit(1)

    st = json.loads(args[0])
    st["type"] = TaskType(st["type"])
    if "estimated_tokens" not in st:
        st["estimated_tokens"] = 0  # pipeline auto-fills
    subtask = SubTask(**st)

    pr = run_pipeline(subtask, workdir=workdir, diff_mode=diff_mode, auto_heal=not no_heal)

    out = {
        "subtask_id": pr.subtask_id,
        "agent_used": pr.agent_used.value,
        "final_score": pr.final_score,
        "strategy": pr.strategy,
        "routed_to_claude": pr.routed_to_claude,
        "eval": vars(pr.eval_result),
    }
    print(json.dumps(out, indent=2))

    if pr.routed_to_claude:
        sys.exit(1)
    if pr.strategy == "C":
        sys.exit(2)
    sys.exit(0)
