"""
Python LanguageAdapter — the implementation for ADR-0035 for Python.

This adapter integrates Python-specific tooling: AST parsing for syntax checking and
signature extraction, pytest for test discovery and execution, ruff for linting, black
for formatting, and PyPI resolution via deps_check for dependency verification.

All subprocess/IO is injected (runner parameter in run_tests) to enable testing and
harness control.
"""

import ast
import subprocess
from typing import Callable, Optional, List, Tuple

from harness.lang.base import LanguageAdapter, register
from harness.mutation import mutate
from harness.deps_check import check_dependencies


class PythonAdapter:
    """
    Python LanguageAdapter implementing the Protocol from harness.lang.base.
    See ADR-0035 for design and integration rationale.
    """

    name = "python"
    extensions = (".py",)

    def check_syntax(self, path: str) -> bool:
        """
        Check if the file at `path` parses as valid Python.

        Returns True if:
        - The file exists and parses successfully with ast.parse()
        - The file is not a .py file (don't block non-Python files)
        - The file doesn't exist (don't block missing files)

        Returns False only if the file exists, is a .py file, and has syntax errors.
        """
        # Only check .py files
        if not path.endswith(".py"):
            return True

        try:
            with open(path, "r", encoding="utf-8") as f:
                ast.parse(f.read())
            return True
        except FileNotFoundError:
            # Missing file: don't block
            return True
        except SyntaxError:
            # Syntax error in .py file: block
            return False
        except Exception:
            # Other errors (encoding, etc.): don't block
            return True

    def is_test_file(self, path: str) -> bool:
        """
        Check if `path` follows Python test-file convention.

        Returns True if the basename starts with "test_" or ends with "_test.py".
        """
        basename = path.rsplit("/", 1)[-1]
        return basename.startswith("test_") or basename.endswith("_test.py")

    def discover_test_cmd(self, files: list, workdir: str = ".") -> Optional[str]:
        """
        Discover pytest command for test files.

        If any file in `files` is a test file (per is_test_file), return the pytest
        command to run all test files. Otherwise return None.
        """
        test_files = [f for f in files if self.is_test_file(f)]
        if not test_files:
            return None
        return f"python3 -m pytest {' '.join(test_files)} -q"

    def run_tests(
        self,
        cmd: str,
        workdir: str,
        *,
        runner: Optional[Callable[[str, str], Tuple[int, str]]] = None,
    ) -> Tuple[int, str]:
        """
        Run `cmd` in `workdir`; return (returncode, combined_output).

        If runner is provided, use it (injectable for testing). Otherwise use
        the default subprocess runner.
        """
        if runner is None:
            runner = _default_runner
        return runner(cmd, workdir)

    def extract_signatures(self, path: str) -> list:
        """
        Extract top-level function and class signatures from a Python file.

        Returns a list of signature strings, e.g., ["def foo(a, b)", "class Bar"].
        Returns an empty list if the file has syntax errors or cannot be read.
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except Exception:
            return []

        sigs = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node in tree.body:
                # Top-level function
                args_str = self._format_args(node.args)
                sigs.append(f"def {node.name}({args_str})")
            elif isinstance(node, ast.ClassDef) and node in tree.body:
                # Top-level class
                sigs.append(f"class {node.name}")

        return sigs

    def mutate(self, source: str) -> List[Tuple[str, str]]:
        """
        Generate behavior-bearing mutants of Python source code.

        Delegates to harness.mutation.mutate() which applies lightweight
        operators (comparison flip, boolean flip, etc.).

        Returns a list of (operator_name, mutated_source) tuples.
        """
        return mutate(source)

    def lint_cmd(self, files: list) -> Optional[str]:
        """
        Return the ruff lint command for the given files.
        """
        if not files:
            return None
        return f"ruff check {' '.join(files)}"

    def format_check_cmd(self, files: list) -> Optional[str]:
        """Return the black format-check command for the given files."""
        if not files:
            return None
        return f"black --check {' '.join(files)}"

    def format_fix_cmd(self, files: list) -> Optional[str]:
        """Return the black auto-format (fix) command — formatting is mechanically reversible and not
        a behavior change (still gated by tests), so we may fix before the style check (ADR-0036)."""
        if not files:
            return None
        return f"black {' '.join(files)}"

    def verify_dependency(self, name: str) -> str:
        """
        Verify that a package name resolves on PyPI.

        Returns one of:
        - 'ok': Package exists on PyPI
        - 'unresolvable': Package name does not exist on PyPI
        - 'unverified': Network error or resolver error
        - 'invalid': Package name fails PEP 508 validation (e.g., contains /)

        Delegates to harness.deps_check.check_dependencies().
        """
        result = check_dependencies([name])
        return result.get(name, "unverified")

    def _format_args(self, args: ast.arguments) -> str:
        """Format function arguments from an ast.arguments node."""
        arg_names = [arg.arg for arg in args.args]
        return ", ".join(arg_names)


def _default_runner(cmd: str, workdir: str) -> Tuple[int, str]:
    """Default subprocess runner for run_tests()."""
    r = subprocess.run(
        cmd,
        shell=True,
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return (r.returncode, (r.stdout or "") + (r.stderr or ""))


# Register the PythonAdapter with the base system
register("python", lambda: PythonAdapter())
