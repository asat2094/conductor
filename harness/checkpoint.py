"""Checkpoint/resume/replay over the event log.

ADR-0028, REQ-OBS8/9: Snapshots are event-derived (can't diverge);
resume re-runs un-accepted units (maker output non-deterministic).

Pure functions over a board/event projection (no real DB).
"""

import json


def make_checkpoint(board: dict) -> dict:
    """Create a checkpoint from a board state.

    Returns {"accepted": [unit_ids with state=="ACCEPTED"], "board": board}.

    Args:
        board: Dict mapping unit_id -> {state, meta fields...}

    Returns:
        Checkpoint dict with accepted unit list and snapshot of board.
    """
    accepted = [unit_id for unit_id, unit_state in board.items()
                if unit_state.get("state") == "ACCEPTED"]
    return {"accepted": accepted, "board": board}


def save_checkpoint(ckpt: dict, path: str, *, dumper=None) -> None:
    """Save checkpoint to a path.

    Args:
        ckpt: Checkpoint dict to save.
        path: File path (or identifier if using custom dumper).
        dumper: Optional callable(obj, path) -> None. Defaults to json.dump to file.
    """
    if dumper is None:
        with open(path, "w") as f:
            json.dump(ckpt, f)
    else:
        dumper(ckpt, path)


def load_checkpoint(path: str, *, loader=None) -> dict:
    """Load checkpoint from a path.

    Args:
        path: File path (or identifier if using custom loader).
        loader: Optional callable(path) -> dict. Defaults to json.load from file.

    Returns:
        Checkpoint dict.
    """
    if loader is None:
        with open(path, "r") as f:
            return json.load(f)
    else:
        return loader(path)


def units_to_resume(all_unit_ids: list, ckpt: dict) -> list:
    """Return unit IDs that need to be resumed.

    Resume skips already-accepted work, preserving order.

    Args:
        all_unit_ids: Full list of unit IDs in original order.
        ckpt: Checkpoint dict with accepted list.

    Returns:
        List of unit IDs not yet accepted (in original order).
    """
    accepted_set = set(ckpt.get("accepted", []))
    return [uid for uid in all_unit_ids if uid not in accepted_set]


def replay_board(events: list) -> dict:
    """Project latest state-per-unit from a raw event list.

    Latest-state-per-unit projection from raw events.
    Each event: {unit_id, state, meta}; meta is flattened alongside state.

    Args:
        events: List of event dicts, each with unit_id, state, and meta.

    Returns:
        Board dict mapping unit_id -> {state, ...meta fields}.
    """
    board = {}
    for event in events:
        unit_id = event["unit_id"]
        state = event["state"]
        meta = event.get("meta", {})

        # Initialize unit if not seen yet
        if unit_id not in board:
            board[unit_id] = {}

        # Update state
        board[unit_id]["state"] = state

        # Flatten meta fields into unit state
        if isinstance(meta, dict):
            board[unit_id].update(meta)

    return board
