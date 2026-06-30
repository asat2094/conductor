"""
JavaScript/TypeScript LanguageAdapter (ADR-0035).

Implements the LanguageAdapter protocol for JavaScript, TypeScript, and related extensions.
Uses regex-based extraction and mutation for lightweight analysis without parser dependencies.

Real implementations:
- check_syntax: would use `node --check <path>` or a parser library; here permissive with injectable runner.
- verify_dependency: would query the npm registry; here degrade-safe returning "unverified".
"""
import re
import subprocess
from typing import Callable, Optional


class JavaScriptAdapter:
    """JavaScript/TypeScript language adapter for the harness."""

    name = "javascript"
    extensions = (".js", ".jsx", ".ts", ".tsx", ".mjs")

    def check_syntax(self, path: str, *, syntax_runner: Optional[Callable[[str], bool]] = None) -> bool:
        """
        True if the file at `path` parses/compiles for JavaScript.

        Real implementation would use `node --check <path>` or a parser.
        Here: injectable runner for testing; default is permissive (True).
        In production, pass syntax_runner=lambda p: subprocess.run(['node', '--check', p], ...).returncode == 0
        """
        if syntax_runner is not None:
            return syntax_runner(path)
        return True  # Permissive default; real impl would check AST

    def is_test_file(self, path: str) -> bool:
        """True if `path` follows JavaScript test convention (.test.js, .spec.ts, etc.)."""
        basename = path.rsplit("/", 1)[-1].lower()
        return ".test." in basename or ".spec." in basename or basename.startswith("test")

    def discover_test_cmd(self, files: list, workdir: str = ".") -> Optional[str]:
        """The shell command that runs tests. Jest convention: 'npm test' if any test files found."""
        for f in files:
            if self.is_test_file(f):
                return "npm test"
        return None

    def run_tests(self, cmd: str, workdir: str, *, runner: Optional[Callable] = None) -> tuple:
        """
        Run `cmd` in `workdir`; return (returncode, combined_output).
        runner injectable for testing; default uses subprocess.
        """
        runner = runner or _default_runner
        return runner(cmd, workdir)

    def extract_signatures(self, path: str) -> list:
        """Harness-side extracted exported signatures from the file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            return self.extract_signatures_text(text)
        except Exception:
            return []

    def extract_signatures_text(self, text: str) -> list:
        """
        Lightweight regex-based extraction of function/class signatures.
        Captures: function declarations, arrow function assignments, class declarations.
        """
        sigs = []

        # Export function declaration: export function name(
        for m in re.finditer(r"export\s+function\s+(\w+)\s*\(", text):
            sigs.append(m.group(1))

        # Plain function declaration: function name(
        for m in re.finditer(r"function\s+(\w+)\s*\(", text):
            sigs.append(m.group(1))

        # Const/let/var with arrow: const name = (...) => or const name = (...) =>
        for m in re.finditer(r"(?:const|let|var)\s+(\w+)\s*=\s*(?:\([^)]*\)|[^=>\s]+)\s*=>", text):
            sigs.append(m.group(1))

        # Class declaration: class Name
        for m in re.finditer(r"class\s+(\w+)", text):
            sigs.append(m.group(1))

        # Return distinct signatures
        return list(dict.fromkeys(sigs))  # Preserve order, remove duplicates

    def mutate(self, source: str) -> list:
        """
        Behavior-bearing mutants: flip operators to check test coverage.
        Returns list of (operator_name, mutated_source) tuples.

        Mutants:
        - === <-> !==
        - == <-> !=
        - && <-> ||
        - true <-> false
        - < <-> >=
        """
        mutants = []
        seen = set()

        # === to !==
        m = re.search(r"===", source)
        if m:
            mutant = source[: m.start()] + "!==" + source[m.end() :]
            if mutant not in seen:
                mutants.append(("=== to !==", mutant))
                seen.add(mutant)

        # !== to ===
        m = re.search(r"!==", source)
        if m:
            mutant = source[: m.start()] + "===" + source[m.end() :]
            if mutant not in seen:
                mutants.append(("!== to ===", mutant))
                seen.add(mutant)

        # == to != (avoid matching === or !==)
        m = re.search(r"(?<![!=])==(?!=)", source)  # Negative lookbehind and lookahead
        if m:
            mutant = source[: m.start()] + "!=" + source[m.end() :]
            if mutant not in seen:
                mutants.append(("== to !=", mutant))
                seen.add(mutant)

        # != to == (avoid matching !==)
        m = re.search(r"!=(?!=)", source)  # Negative lookahead to avoid matching !==
        if m:
            mutant = source[: m.start()] + "==" + source[m.end() :]
            if mutant not in seen:
                mutants.append(("!= to ==", mutant))
                seen.add(mutant)

        # && to ||
        m = re.search(r"&&", source)
        if m:
            mutant = source[: m.start()] + "||" + source[m.end() :]
            if mutant not in seen:
                mutants.append(("&& to ||", mutant))
                seen.add(mutant)

        # || to &&
        m = re.search(r"\|\|", source)
        if m:
            mutant = source[: m.start()] + "&&" + source[m.end() :]
            if mutant not in seen:
                mutants.append(("|| to &&", mutant))
                seen.add(mutant)

        # true to false
        m = re.search(r"\btrue\b", source)
        if m:
            mutant = source[: m.start()] + "false" + source[m.end() :]
            if mutant not in seen:
                mutants.append(("true to false", mutant))
                seen.add(mutant)

        # false to true
        m = re.search(r"\bfalse\b", source)
        if m:
            mutant = source[: m.start()] + "true" + source[m.end() :]
            if mutant not in seen:
                mutants.append(("false to true", mutant))
                seen.add(mutant)

        # < to >=
        m = re.search(r"<(?!=)", source)  # Not <=
        if m:
            mutant = source[: m.start()] + ">=" + source[m.end() :]
            if mutant not in seen:
                mutants.append(("< to >=", mutant))
                seen.add(mutant)

        # > to <=
        m = re.search(r">(?!=)", source)  # Not >=
        if m:
            mutant = source[: m.start()] + "<=" + source[m.end() :]
            if mutant not in seen:
                mutants.append(("> to <=", mutant))
                seen.add(mutant)

        return mutants

    def lint_cmd(self, files: list) -> Optional[str]:
        """The repo's lint command for JavaScript files."""
        if not files:
            return None
        files_str = " ".join(files)
        return f"eslint {files_str}"

    def format_check_cmd(self, files: list) -> Optional[str]:
        """The repo's format-check command for JavaScript files."""
        if not files:
            return None
        files_str = " ".join(files)
        return f"prettier --check {files_str}"

    def verify_dependency(self, name: str) -> str:
        """
        Verify npm package name validity and existence.

        Returns:
        - "invalid": package name contains invalid characters
        - "unverified": valid syntax but registry lookup not performed (degrade-safe default)
        - "ok": (only when real registry lookup is enabled)

        Real implementation would query npm registry (npmjs.org/api/v1/search?text=<name>).
        This stub is degrade-safe: never auto-approves, allowing operators to verify manually if needed.
        """
        # Validate npm package name syntax
        # Allowed: lowercase letters, digits, hyphens, and scoped names (@scope/package)
        if not isinstance(name, str) or not name:
            return "invalid"

        # Allow @scope/package format
        if name.startswith("@"):
            parts = name.split("/")
            if len(parts) != 2 or not parts[1]:
                return "invalid"
            scope, pkg_name = parts
            # Scope and package name must contain only lowercase, digits, hyphens
            if not re.match(r"^@[a-z0-9\-]+$", scope) or not re.match(r"^[a-z0-9\-]+$", pkg_name):
                return "invalid"
        else:
            # Plain package name: lowercase, digits, hyphens only
            if not re.match(r"^[a-z0-9\-]+$", name):
                return "invalid"

        # Real impl would query npm registry here; for safety, return unverified
        return "unverified"


def _default_runner(cmd: str, workdir: str) -> tuple:
    """Default subprocess runner for test execution."""
    r = subprocess.run(cmd, shell=True, cwd=workdir, capture_output=True, text=True, timeout=300)
    return (r.returncode, (r.stdout or "") + (r.stderr or ""))


# Register the adapter
from harness.lang.base import register

register("javascript", lambda: JavaScriptAdapter())
