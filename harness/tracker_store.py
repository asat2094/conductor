"""
Durable, append-only event store backed by SQLite.

Serves as the persistent sibling to the in-memory Tracker. Records every state change
as an immutable event row, enabling:
  - Ordered, complete event history (required by ADR-0023)
  - Per-unit attempt history (REQ-OBS7: observe every healing attempt)
  - Pluggable sinks for reactive subscriptions
  - Board projection: latest state per unit_id

Design: per-attempt run rows preserved in event table, sinks subscribe to appends.
Note: tracker_store stores whatever caller passes (no model self-report); caller owns
validation per NFR-TRACK-1.
"""

import json
import sqlite3
import time
from typing import Any, Callable


class TrackerStore:
    """SQLite-backed event store for unit processing events."""

    def __init__(self, db_path: str = ":memory:"):
        """
        Initialize TrackerStore.

        Args:
            db_path: Path to SQLite file (":memory:" for in-memory, default).
                     File databases persist across instantiations.
        """
        self.db_path = db_path
        self._sinks: list[Callable[[dict], None]] = []
        # For :memory: databases, keep a persistent connection across the lifetime
        # of this instance. For file databases, reconnect on each operation.
        self._conn: sqlite3.Connection | None = None
        if db_path == ":memory:":
            self._conn = sqlite3.connect(db_path)
        self._setup_schema()

    def _setup_schema(self) -> None:
        """Create events table if it doesn't exist."""
        if self._conn:
            conn = self._conn
            close_after = False
        else:
            conn = sqlite3.connect(self.db_path)
            close_after = True

        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                unit_id   TEXT    NOT NULL,
                state     TEXT    NOT NULL,
                meta      TEXT    NOT NULL,
                ts        REAL    NOT NULL
            )
        """)
        conn.commit()
        if close_after:
            conn.close()

    def record(self, unit_id: str, state: str, **meta: Any) -> None:
        """
        Record a state transition event (append-only).

        Inserts row into events table and notifies all registered sinks.

        Args:
            unit_id: Identifier for the unit being tracked.
            state: New state (e.g., "DISPATCHED", "ACCEPTED", "HEALING", "FAILED").
            **meta: Arbitrary metadata dict (e.g., maker="gemma4", score=90, attempt=1).
        """
        if self._conn:
            conn = self._conn
            close_after = False
        else:
            conn = sqlite3.connect(self.db_path)
            close_after = True

        ts = time.time()
        meta_json = json.dumps(meta)

        conn.execute(
            "INSERT INTO events (unit_id, state, meta, ts) VALUES (?, ?, ?, ?)",
            (unit_id, state, meta_json, ts),
        )
        conn.commit()
        if close_after:
            conn.close()

        # Notify sinks
        event_dict = {
            "unit_id": unit_id,
            "state": state,
            "meta": meta,
            "ts": ts,
        }
        for sink in self._sinks:
            sink(event_dict)

    def events(self) -> list[dict]:
        """
        Return all events in order.

        Returns:
            List of event dicts: {unit_id, state, meta (dict), ts}.
            Ordered by insertion time (ts ascending).
        """
        if self._conn:
            conn = self._conn
            close_after = False
        else:
            conn = sqlite3.connect(self.db_path)
            close_after = True

        cur = conn.execute(
            "SELECT unit_id, state, meta, ts FROM events ORDER BY ts ASC"
        )
        rows = cur.fetchall()
        if close_after:
            conn.close()

        return [
            {
                "unit_id": r[0],
                "state": r[1],
                "meta": json.loads(r[2]),
                "ts": r[3],
            }
            for r in rows
        ]

    def board(self) -> dict[str, dict]:
        """
        Return board projection: latest state per unit_id.

        Returns:
            Dict mapping unit_id -> {state, **meta}.
            Meta fields (from latest event) are flattened into the dict.
        """
        events = self.events()
        board = {}

        for event in events:
            unit_id = event["unit_id"]
            # Latest event wins: overwrite with new state and merged meta
            board[unit_id] = {
                "state": event["state"],
                **event["meta"],
            }

        return board

    def runs(self, unit_id: str) -> list[dict]:
        """
        Return all events for a given unit (per-attempt history).

        Args:
            unit_id: Unit identifier.

        Returns:
            List of event dicts for this unit, in order.
            Each dict has: {unit_id, state, meta (dict), ts}.
        """
        if self._conn:
            conn = self._conn
            close_after = False
        else:
            conn = sqlite3.connect(self.db_path)
            close_after = True

        cur = conn.execute(
            "SELECT unit_id, state, meta, ts FROM events WHERE unit_id = ? ORDER BY ts ASC",
            (unit_id,),
        )
        rows = cur.fetchall()
        if close_after:
            conn.close()

        return [
            {
                "unit_id": r[0],
                "state": r[1],
                "meta": json.loads(r[2]),
                "ts": r[3],
            }
            for r in rows
        ]

    def add_sink(self, fn: Callable[[dict], None]) -> None:
        """
        Register a sink function to be called on each recorded event.

        Args:
            fn: Callable that accepts event dict {unit_id, state, meta, ts}.
        """
        self._sinks.append(fn)

    def rollup(self) -> dict:
        """Count units per latest state (REQ-OBS5)."""
        from harness.progress import rollup_of
        return rollup_of(self.board())

    def render_text(self) -> str:
        """Human program-manager table — makes TrackerStore drop-in for Tracker (REQ-OBS5)."""
        from harness.progress import render_board
        return render_board(self.board())
