"""
Production CLI for the conductor distributed build (the ADR-gated spine).

    python3 -m harness briefs.json [--workdir DIR] [--style] [--tdd-gates] [--codegraph]
                        [--probes] [--atomicity wave|dag] [--failure-mode MODE]
                        [--checkpoint PATH] [--resume PATH] [--budget N] [--budget-mode audit|enforce]
                        [--progress-path FILE] [--report]

Runs decompose -> verify -> per-wave dispatch through REAL makers (ollama gemma4 /
Claude CLI per role policy) with mechanical gates. Exit code 0 iff nothing failed.

This is the entry point for the NEW DAG/gate stack (build_live). The legacy
single-task path (`python3 -m harness.router` / `harness.pipeline`) remains for
one-off delegations.
"""
import argparse
import json
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m harness", description=__doc__)
    ap.add_argument("briefs", help="path to a JSON list of SubtaskBriefs")
    ap.add_argument("--workdir", default=".")
    ap.add_argument("--style", action="store_true", help="repo-native style gate (ADR-0036)")
    ap.add_argument("--tdd-gates", action="store_true", help="git-RED commit-order gate (ADR-0030)")
    ap.add_argument("--codegraph", action="store_true", help="codegraph verify + per-wave reverify (ADR-0022)")
    ap.add_argument("--probes", action="store_true", help="advisory spec-completeness probes (ADR-0032)")
    ap.add_argument("--atomicity", choices=["wave", "dag"], default="wave", help="merge granularity (ADR-0041)")
    ap.add_argument("--failure-mode", choices=["continue_on_error", "fail_fast", "all_or_nothing"],
                    default="continue_on_error")
    ap.add_argument("--checkpoint", default=None, help="checkpoint path, saved per wave (ADR-0028)")
    ap.add_argument("--resume", default=None, help="resume from a checkpoint file (ADR-0028)")
    ap.add_argument("--budget", type=int, default=None, help="token budget (ADR-0034)")
    ap.add_argument("--budget-mode", choices=["audit", "enforce"], default="audit")
    ap.add_argument("--progress-path", default=None, help="JSONL sink for external PM tools (ADR-0023)")
    ap.add_argument("--report", action="store_true", help="print the PM board at the end")
    ap.add_argument("--merge-target", default=None, metavar="BRANCH",
                    help="git-backed merge queue: land GREEN waves onto this branch (ADR-0041)")
    ap.add_argument("--suite-cmd", default=None, help="full-suite command run after each unit merge")
    ap.add_argument("--judge", action="store_true",
                    help="inconclusive-only judge tiebreak (ADR-0038): a judge-role model decides "
                         "units with NO mechanical signal; never overrides a FAIL; per-DAG quota")
    args = ap.parse_args(argv)

    with open(args.briefs) as f:
        briefs = json.load(f)

    from harness.live_pipeline import build_live, build_report

    kw = {}
    if args.budget is not None:
        from harness.admission import CostCeiling
        kw["cost_ceiling"] = CostCeiling(limit=args.budget, mode=args.budget_mode)
    if args.resume:
        from harness.checkpoint import load_checkpoint
        kw["resume_from"] = load_checkpoint(args.resume)
    if args.merge_target:
        from harness.git_merge_queue import GitMergeQueue
        writes = {b["id"]: b.get("writes_files", []) for b in briefs}
        kw["merge_queue"] = GitMergeQueue(args.workdir, args.merge_target, suite_cmd=args.suite_cmd,
                                          writes_for=writes.get)
    if args.judge:
        from harness.model_call import call_model
        from harness.role_policy import resolve_model

        def _judge(artifact) -> bool:
            # ADR-0038: only ever invoked on inconclusive slices (the gate guarantees it);
            # strict parse — anything other than a leading ACCEPT is a reject.
            spec = resolve_model("judge")
            reply = call_model(spec, (
                "You are a tiebreak judge for a code unit that has NO mechanical test signal.\n"
                "Files changed: " + ", ".join(artifact.changed_files) + "\n"
                "Diff:\n" + (artifact.diff_text or "(no diff captured)") + "\n\n"
                "Reply with exactly one word — ACCEPT if the change is plausibly correct and "
                "in-scope, REJECT otherwise."))
            return reply.strip().upper().startswith("ACCEPT")

        kw["judge"] = _judge
        kw["no_test_inconclusive"] = True

    result, tracker = build_live(
        briefs, workdir=args.workdir,
        style=args.style, tdd_gates=args.tdd_gates, codegraph=args.codegraph, probes=args.probes,
        atomicity=args.atomicity, failure_mode=args.failure_mode,
        checkpoint_path=args.checkpoint, progress_path=args.progress_path,
        **kw,
    )
    if args.report:
        print(build_report(result, tracker))
    print(f"accepted={result.accepted} failed={result.failed} inline={result.inline} "
          f"assembly={result.assembly} landed_waves={result.landed_waves}")
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
