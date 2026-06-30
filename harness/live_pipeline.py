"""
Live pipeline wiring (completes the spine, ADR-0011/0024/0027). Composes the built pieces into the
real per-unit processor and a one-call live build:

    live_maker (model -> files -> diff -> in-loop test)
      wrapped by make_processor (bounded repair loop against the composed unit_gate)
      driven by run_dag (decompose -> verify -> per-wave cost_skip -> dispatch -> track)

`make_live_processor` returns a process_unit(subtask, workdir) usable as run_dag's process_unit.
`build_live` is the convenience entrypoint: decompose+verify+dispatch with REAL makers. All maker IO
(model_caller, test_runner, differ) is pass-through via **maker_kw so it stays unit-testable with fakes
and uses real Claude-CLI/ollama + pytest in production.
"""
from typing import Any, Callable, Optional

from harness.process_unit import make_processor
from harness.live_maker import make_live_maker
from harness.conductor import build, build_report, default_gate_spec_for


def make_live_processor(
    *,
    role: str = "impl_author",
    policy: Optional[dict] = None,
    gate_spec_for: Optional[Callable[[Any], Any]] = None,
    max_attempts: int = 3,
    stuck_window: int = 2,
    **maker_kw: Any,
) -> Callable[[Any, str], Any]:
    """Compose the real maker + bounded repair loop + composed unit gate into a process_unit."""
    maker = make_live_maker(role=role, policy=policy, **maker_kw)
    return make_processor(
        maker,
        gate_spec_for or default_gate_spec_for,
        max_attempts=max_attempts,
        stuck_window=stuck_window,
    )


def build_live(
    briefs: list[dict],
    workdir: str = ".",
    *,
    policy: Optional[dict] = None,
    edges: Optional[dict] = None,
    max_attempts: int = 3,
    **maker_kw: Any,
):
    """One-call live build: decompose -> verify -> per-wave dispatch through REAL makers.
    Returns (DagRunResult, Tracker). maker_kw flows to the live maker (model_caller/test_runner/... )."""
    proc = make_live_processor(policy=policy, max_attempts=max_attempts, **maker_kw)
    return build(briefs, workdir=workdir, process_unit=proc, edges=edges)


__all__ = ["make_live_processor", "build_live", "build_report"]
