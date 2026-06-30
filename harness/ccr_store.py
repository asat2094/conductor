"""Compress-Cache-Retrieve store for reversible retrieval (ADR-0033, REQ-E4).

This module provides an in-memory store for original values keyed by content handles.
Values are retrieved on demand with TTL-based expiry. The clock is injected for
testability, enabling deterministic expiry testing without real time.

Design principle: Used for caching compressed values — retrieval is optimized for
read-only access, never during gate evidence evaluation (Law 1: read/optimize path
only on gate evidence). Expired entries degrade to None (caller falls back to
compressed text representation).
"""

import hashlib
import time
from typing import Callable, Optional


class CCRStore:
    """In-memory store for original values with TTL-based expiry.

    Stores original uncompressed content keyed by a content handle derived
    from SHA256. Supports deterministic time via injected clock for testing.
    Expired entries are not automatically pruned; they degrade on retrieve.

    Args:
        ttl_seconds: Time-to-live for stored entries in seconds. Default 1800 (30 min).
        clock: Callable returning current time as float (default time.monotonic).
    """

    def __init__(self, ttl_seconds: int = 1800, clock: Optional[Callable[[], float]] = None):
        """Initialize the CCR store.

        Args:
            ttl_seconds: Entry lifetime in seconds.
            clock: Injected time source; defaults to time.monotonic.
        """
        self._ttl_seconds = ttl_seconds
        self._clock = clock if clock is not None else time.monotonic
        self._store: dict[str, tuple[str, float]] = {}  # handle -> (original, timestamp)

    def store(self, original: str) -> str:
        """Store original content and return a stable handle.

        The handle is derived from SHA256 of the original content, ensuring
        identical content always produces the same handle.

        Args:
            original: The uncompressed original content.

        Returns:
            A stable handle of the form "ccr:XXXX..." (ccr prefix + first 16 chars of hash).
        """
        digest = hashlib.sha256(original.encode()).hexdigest()
        handle = f"ccr:{digest[:16]}"
        timestamp = self._clock()
        self._store[handle] = (original, timestamp)
        return handle

    def retrieve(self, handle: str) -> Optional[str]:
        """Retrieve original content by handle if present and not expired.

        Implements degrade-clean on expiry: if the handle exists but the entry
        has exceeded its TTL, returns None (caller should fall back to
        compressed text representation).

        Args:
            handle: The handle returned by store().

        Returns:
            The original content if present and within TTL; None otherwise.
        """
        if handle not in self._store:
            return None

        original, stored_time = self._store[handle]
        elapsed = self._clock() - stored_time

        if elapsed > self._ttl_seconds:
            # Degrade-clean: expired entry
            return None

        return original

    def handles(self) -> list[str]:
        """Return handles that are still live (non-expired at call time). Expired entries are
        excluded so the list matches what retrieve() would actually return."""
        now = self._clock()
        return [h for h, (_, ts) in self._store.items() if (now - ts) <= self._ttl_seconds]
