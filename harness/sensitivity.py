"""
Data boundary enforcement and exposure audit for the conductor harness.

Enforces that high-sensitivity workloads (source code, proprietary data) never
egress to free third-party cloud providers. Enforces local (ollama) or Claude-only backends
for high-sensitivity tasks.

References: S6 (sensitivity classification), ADR-0017 (data governance),
REQ-R4 (egress restriction).

IMPORTANT: Sensitivity tagging is heuristic—once bytes leave this system,
we have no control over provider data retention, access logs, or reuse policies.
This module provides a boundary enforcement point but cannot guarantee provider behavior.
"""

import hashlib
from typing import Dict, Any, List, Literal


# Allowed local and Claude-controlled backends
LOCAL_BACKENDS = {"ollama"}
CLAUDE_BACKENDS = {"claude_cli"}
SAFE_BACKENDS = LOCAL_BACKENDS | CLAUDE_BACKENDS


class SensitivityViolation(Exception):
    """Raised when a model spec violates sensitivity constraints."""
    pass


def allowed_for_sensitivity(spec: Dict[str, Any], sensitivity: Literal["high", "low"]) -> bool:
    """
    Check if a model spec is allowed for the given sensitivity level.

    Args:
        spec: Model specification dict with "backend" and "model" keys.
        sensitivity: Either "high" (restricted) or "low" (unrestricted).

    Returns:
        True if the spec is allowed; False otherwise.

    Rules:
        - high sensitivity: only LOCAL or CLAUDE backends allowed
        - low sensitivity: any backend allowed
    """
    backend = spec.get("backend", "")

    if sensitivity == "high":
        return backend in SAFE_BACKENDS
    else:  # "low"
        return True


def enforce(spec: Dict[str, Any], sensitivity: Literal["high", "low"]) -> Dict[str, Any]:
    """
    Enforce sensitivity constraints on a model spec.

    Args:
        spec: Model specification dict.
        sensitivity: Sensitivity level ("high" or "low").

    Returns:
        The spec dict if allowed.

    Raises:
        SensitivityViolation: If the spec violates the sensitivity constraint.
    """
    if not allowed_for_sensitivity(spec, sensitivity):
        backend = spec.get("backend", "unknown")
        raise SensitivityViolation(
            f"Backend '{backend}' not allowed for sensitivity level '{sensitivity}'. "
            f"High sensitivity requires backends in {SAFE_BACKENDS}."
        )
    return spec


class ExposureAudit:
    """
    Append-only audit log of data exposure to external providers.

    Records hash digests (not raw payloads) to track which providers
    have received egress data and payload sizes.
    """

    def __init__(self):
        """Initialize an empty exposure audit."""
        self.entries: List[Dict[str, Any]] = []

    def record(self, provider: str, payload: str) -> None:
        """
        Record an exposure event (provider, hashed payload, size).

        Args:
            provider: Name of the external provider (e.g., "openrouter", "openai_compat").
            payload: Raw payload string (NOT stored; only hashed).

        Side effect: Appends a dict with provider, hash (first 16 chars of sha256),
        and nbytes to self.entries.
        """
        payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        nbytes = len(payload.encode("utf-8"))

        self.entries.append({
            "provider": provider,
            "hash": payload_hash,
            "nbytes": nbytes,
        })
