"""
Runner — execute an EvalSuite against one model and collect objective trial results
(evalkit, ADR-0042).

Model-agnostic: the call goes through an injected `caller(spec, prompt) -> str`, defaulting
to harness.model_call.call_model, so any backend the harness speaks (ollama / claude CLI /
cloud) is evaluable — nothing here is gemma4-specific. A caller error/timeout becomes an empty
output (a refusal), scored 0 — never crashes the sweep.
"""
import time
import urllib.error
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class TrialResult:
    model: str
    task_id: str
    task_type: str
    language: str
    context_tokens: int
    origin: str
    output: str
    latency_s: float
    tokens_used: int
    score: int
    passed: bool


def model_name(spec: dict) -> str:
    return spec.get("name") or f"{spec.get('backend', '?')}:{spec.get('model', '?')}"


def evaluate(
    model_spec: dict,
    suite,
    *,
    caller: Optional[Callable[[dict, str], str]] = None,
    trials: int = 2,
    pass_threshold: int = 70,
    clock: Callable[[], float] = time.perf_counter,
) -> list[TrialResult]:
    """Run every task in `suite` `trials` times against `model_spec`; grade each output
    mechanically. Returns a flat list of TrialResults for the report/dimensions to aggregate."""
    if caller is None:
        from harness.model_call import call_model
        caller = call_model

    name = model_name(model_spec)
    results: list[TrialResult] = []
    for task in suite:
        for _ in range(max(1, trials)):
            start = clock()
            try:
                output = caller(model_spec, task.prompt) or ""
            except (TimeoutError, ConnectionError, OSError, urllib.error.URLError):
                output = ""     # GENUINE transient/model failure -> refusal (scored 0 below).
                # Config/programming errors (unknown backend, missing key, bad spec) are NOT caught:
                # they propagate so a broken calibration fails loud instead of poisoning profiles.
            latency = clock() - start
            score = task.grader.grade(output, task) if output.strip() else 0
            results.append(TrialResult(
                model=name, task_id=task.id, task_type=task.task_type,
                language=task.language, context_tokens=task.context_tokens,
                origin=task.origin, output=output, latency_s=round(latency, 3),
                tokens_used=(len(task.prompt) + len(output)) // 4,
                score=score, passed=score >= pass_threshold,
            ))
    return results
