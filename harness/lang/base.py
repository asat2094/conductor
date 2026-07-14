"""
LanguageAdapter — the one seam for every language-specific operation (ADR-0035).

The base system (gates, decompose, run_dag, repair loop, merge queue, tracker) NEVER branches on
language. It resolves an adapter and calls it. Swapping `python` -> `javascript` swaps one registered
block; no structural change elsewhere. The mantra/guardrails are adapter-independent: the adapter
only changes HOW a mechanical fact is computed (AST parse, test run, lint run) — never WHETHER the
gate is mechanical (Law 2), and never substitutes a maker self-report (Law 1).

Resolution is by language name (from the repo profile, ADR-0037); an unknown language degrades to the
GenericAdapter (best-effort) rather than crashing.
"""
from typing import Callable, Optional, Protocol, runtime_checkable


@runtime_checkable
class LanguageAdapter(Protocol):
    name: str
    extensions: tuple  # file extensions this adapter owns, e.g. (".py",)

    def check_syntax(self, path: str) -> bool:
        """True if the file at `path` parses/compiles for this language."""
        ...

    def is_test_file(self, path: str) -> bool:
        """True if `path` follows this language's test-file convention."""
        ...

    def discover_test_cmd(self, files: list, workdir: str = ".") -> Optional[str]:
        """The shell command that runs the relevant tests (or None if none found)."""
        ...

    def run_tests(self, cmd: str, workdir: str, *, runner: Optional[Callable] = None) -> tuple:
        """Run `cmd` in `workdir`; return (returncode, combined_output). runner injectable for tests."""
        ...

    def extract_signatures(self, path: str) -> list:
        """Harness-side extracted exported signatures (for contract conformance) — NOT maker-reported."""
        ...

    def mutate(self, source: str) -> list:
        """Behavior-bearing mutants of source: list of (operator_name, mutated_source)."""
        ...

    def lint_cmd(self, files: list) -> Optional[str]:
        """The repo's lint command for these files (or None if no linter)."""
        ...

    def format_check_cmd(self, files: list) -> Optional[str]:
        """The repo's format-check command (or None)."""
        ...

    def verify_dependency(self, name: str) -> str:
        """Registry-existence of a package: 'ok' | 'unresolvable' | 'unverified' | 'invalid'."""
        ...


_ADAPTERS: dict = {}


def register(name: str, factory: Callable[[], "LanguageAdapter"]) -> None:
    _ADAPTERS[name] = factory


def resolve(language: Optional[str]) -> "LanguageAdapter":
    """Return the adapter for `language`; unknown/None -> GenericAdapter (degrade-clean)."""
    factory = _ADAPTERS.get((language or "").lower())
    if factory is None:
        return GenericAdapter()
    return factory()


def adapter_for_path(path: str) -> "LanguageAdapter":
    """Resolve by file extension (for polyglot repos / per-unit resolution)."""
    for factory in _ADAPTERS.values():
        a = factory()
        if any(path.endswith(ext) for ext in getattr(a, "extensions", ())):
            return a
    return GenericAdapter()


class GenericAdapter:
    """Best-effort fallback for an unregistered language (ADR-0035 degrade path). Honest degradation:
    syntax/lint unknown -> permissive/None; tests via a discovered cmd if any; no mutation."""

    name = "generic"
    extensions = ()

    def check_syntax(self, path: str) -> bool:
        return True  # cannot parse an unknown language -> do not block on syntax

    def is_test_file(self, path: str) -> bool:
        base = path.rsplit("/", 1)[-1].lower()
        return base.startswith("test") or "test" in base or "spec" in base

    def discover_test_cmd(self, files: list, workdir: str = ".") -> Optional[str]:
        return None  # unknown how to test -> caller treats as no-test (weak GREEN, logged)

    def run_tests(self, cmd: str, workdir: str, *, runner: Optional[Callable] = None) -> tuple:
        runner = runner or _default_runner
        return runner(cmd, workdir)

    def extract_signatures(self, path: str) -> list:
        return []

    def mutate(self, source: str) -> list:
        return []  # no mutation adequacy for an unknown language

    def lint_cmd(self, files: list) -> Optional[str]:
        return None

    def format_check_cmd(self, files: list) -> Optional[str]:
        return None

    def verify_dependency(self, name: str) -> str:
        return "unverified"  # unknown ecosystem -> fail safe, do not auto-approve


def _default_runner(cmd: str, workdir: str) -> tuple:
    import subprocess
    r = subprocess.run(cmd, shell=True, cwd=workdir, capture_output=True, text=True, timeout=300)
    return (r.returncode, (r.stdout or "") + (r.stderr or ""))


register("generic", lambda: GenericAdapter())
