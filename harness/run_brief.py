"""
Adapters between a SubtaskBrief (dict) and the harness's existing types (ADR-0024 — a brief is
the bounded context a role-instance runs from). brief_to_subtask feeds cost_skip/router/run_pipeline;
brief_to_messages builds the message list the optimizer + a (paid) role model would read.
"""
from typing import Any

from harness.models import SubTask, TaskType
from harness.tokens import estimate_tokens


def brief_to_subtask(brief: dict[str, Any], workdir: str = ".") -> SubTask:
    est = int(brief.get("estimated_tokens") or estimate_tokens(brief.get("files", []), workdir))
    return SubTask(
        id=brief["id"],
        description=brief["goal"],
        type=TaskType(brief["task_type"]),
        files=list(brief.get("files", [])),
        estimated_tokens=est,
        sensitivity=brief.get("sensitivity", "low"),
        writes_files=list(brief.get("writes_files", [])),
        produces=list(brief["contract"].get("produces", [])),
        consumes=list(brief["contract"].get("consumes", [])),
        logical_deps=list(brief.get("logical_deps", [])),
        context_slices=list(brief.get("context_slices", [])),
    )


def brief_to_messages(brief: dict[str, Any]) -> list[dict[str, str]]:
    """Bounded context for a role model: a system instruction + the unit brief as a user message."""
    contract = brief.get("contract", {})
    system = (
        "You are a bounded maker. Do ONLY this unit from its brief. "
        f"Exit criteria: {brief.get('exit_criteria', '')}"
    )
    user = (
        f"Goal: {brief['goal']}\n"
        f"Files: {', '.join(brief.get('files', []))}\n"
        f"Produces: {', '.join(contract.get('produces', []))}\n"
        f"Consumes: {', '.join(contract.get('consumes', []))}\n"
        f"Verify: {brief.get('verify_cmd', '')}"
    )
    # NOTE: context_slices are intentionally not inlined yet — the retrieve/optimizer path
    # (REQ-RM3) that cuts + compresses slices into the message is wired in a follow-on plan.
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
