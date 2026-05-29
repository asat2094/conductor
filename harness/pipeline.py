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

from harness.models import EvalResult, SubTask
from harness.orchestrate import EscalateToClaudeError, orchestrate
from harness.tokens import estimate_tokens


@dataclass
class PipelineResult:
    subtask_id: str
    agent_used: str             # was AgentType; widened to str for multi-provider support
    final_score: int
    strategy: str | None       # None = no healing needed; "A"/"B"/"C" = healer ran
    eval_result: EvalResult
    routed_to_claude: bool = False  # True when router sent to claude_agent


def run_pipeline(
    subtask: SubTask,
    workdir: str = ".",
    diff_mode: bool = False,
    auto_heal: bool = True,   # kept for API compat; orchestrate always heals internally
) -> PipelineResult:
    """
    Full pipeline for a single subtask via the multi-provider orchestrator.
    Returns PipelineResult. Sets routed_to_claude=True when all local providers fail.
    """
    if not subtask.estimated_tokens:
        subtask.estimated_tokens = estimate_tokens(subtask.files, workdir)

    try:
        result = orchestrate(subtask, workdir=workdir, diff_mode=diff_mode)
    except EscalateToClaudeError:
        dummy = EvalResult(
            subtask_id=subtask.id, agent="claude_agent", score=-1,
            syntax_score=0, test_score=0, scope_score=0, semantic_score=0,
            details="all providers exhausted — routed to claude_agent",
        )
        return PipelineResult(
            subtask_id=subtask.id, agent_used="claude_agent",
            final_score=-1, strategy=None, eval_result=dummy,
            routed_to_claude=True,
        )

    return PipelineResult(
        subtask_id=subtask.id, agent_used=result.agent,
        final_score=result.score, strategy=None, eval_result=result,
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
        "agent_used": pr.agent_used if isinstance(pr.agent_used, str) else pr.agent_used.value,
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
