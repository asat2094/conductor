"""
Repository profiling and onboarding (ADR-0037, REQ-ONB1/2).

Detects a repo's language, test framework, and standards so the rest of the system
(LanguageAdapter resolution ADR-0035, style gate ADR-0036) is configured once.

Design principles:
  - Deterministic detection from manifests/extensions
  - Detect-then-override: detect defaults, then apply explicit overrides
  - Degrade clean: missing pieces (e.g., no test_cmd) result in None, not fatal

Filesystem I/O only — pure reads on a given workdir path.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class RepoProfile:
    """Repository profile: language, test framework, git status, contributing guidelines."""

    language: str
    """Detected or overridden language identifier (python, javascript, go, rust, generic)."""

    test_cmd: Optional[str]
    """Test command derived from language or overridden. None for generic repos."""

    has_git: bool
    """True if .git directory exists in workdir."""

    contributing: bool
    """True if CONTRIBUTING.md (case-insensitive) exists in workdir."""

    overrides: dict
    """Applied override configuration (for audit/debugging)."""


def detect_language(workdir: str) -> str:
    """
    Detect repository language from manifest files.

    Checks in order (first match wins):
      - pyproject.toml, setup.py, setup.cfg → "python"
      - package.json → "javascript"
      - go.mod → "go"
      - Cargo.toml → "rust"
      - (none found) → "generic"

    Args:
        workdir: Absolute path to repository root.

    Returns:
        Language identifier: "python", "javascript", "go", "rust", or "generic".
    """
    workdir_path = Path(workdir)

    # Python manifests
    if (workdir_path / "pyproject.toml").exists():
        return "python"
    if (workdir_path / "setup.py").exists():
        return "python"
    if (workdir_path / "setup.cfg").exists():
        return "python"

    # JavaScript manifest
    if (workdir_path / "package.json").exists():
        return "javascript"

    # Go manifest
    if (workdir_path / "go.mod").exists():
        return "go"

    # Rust manifest
    if (workdir_path / "Cargo.toml").exists():
        return "rust"

    # Fallback
    return "generic"


def _get_test_cmd(language: str) -> Optional[str]:
    """
    Derive default test command for a given language.

    Args:
        language: Language identifier.

    Returns:
        Test command string or None for generic.
    """
    commands = {
        "python": "python3 -m pytest -q",
        "javascript": "npm test",
        "go": "go test ./...",
        "rust": "cargo test",
    }
    return commands.get(language)


def _has_contributing(workdir: str) -> bool:
    """
    Check if CONTRIBUTING.md exists (case-insensitive).

    Args:
        workdir: Absolute path to repository root.

    Returns:
        True if CONTRIBUTING.md (any case) found.
    """
    workdir_path = Path(workdir)
    # Iterate directory entries to match case-insensitively
    try:
        for entry in workdir_path.iterdir():
            if entry.is_file() and entry.name.lower() == "contributing.md":
                return True
    except (OSError, PermissionError):
        pass
    return False


def profile_repo(workdir: str, *, overrides: Optional[dict] = None) -> RepoProfile:
    """
    Build a repository profile from filesystem inspection and overrides.

    Workflow:
      1. Detect language from manifests.
      2. Check for .git directory.
      3. Check for CONTRIBUTING.md (case-insensitive).
      4. Derive test_cmd from language.
      5. Apply overrides dict (any field can be overridden).

    Args:
        workdir: Absolute path to repository root.
        overrides: Optional dict to override any field (language, test_cmd, has_git, contributing).

    Returns:
        RepoProfile instance with detected/overridden values.

    References:
        - ADR-0037: Repository profiling for system configuration
        - REQ-ONB1: Language detection from manifests
        - REQ-ONB2: Config inference (test_cmd, git status, contributing guidelines)
    """
    overrides = overrides or {}
    workdir_path = Path(workdir)

    # Detect language (or override)
    language = overrides.get("language", detect_language(workdir))

    # Detect git
    has_git = overrides.get("has_git", (workdir_path / ".git").is_dir())

    # Detect contributing
    contributing = overrides.get("contributing", _has_contributing(workdir))

    # Derive test_cmd (or override)
    test_cmd = overrides.get("test_cmd", _get_test_cmd(language))

    return RepoProfile(
        language=language,
        test_cmd=test_cmd,
        has_git=has_git,
        contributing=contributing,
        overrides=overrides,
    )
