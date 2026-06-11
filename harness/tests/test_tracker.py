from harness.tracker import Tracker, UnitState


def test_record_and_board_projection():
    t = Tracker()
    t.record("u1", UnitState.DISPATCHED, maker="gemma4")
    t.record("u1", UnitState.ACCEPTED, score=82)
    t.record("u2", UnitState.FAILED, score=10)
    board = t.board()
    assert board["u1"]["state"] == "ACCEPTED"
    assert board["u1"]["score"] == 82
    assert board["u2"]["state"] == "FAILED"


def test_board_is_projection_latest_wins():
    t = Tracker()
    t.record("u1", UnitState.PENDING)
    t.record("u1", UnitState.DISPATCHED)
    assert t.board()["u1"]["state"] == "DISPATCHED"


def test_events_are_append_only_history():
    t = Tracker()
    t.record("u1", UnitState.DISPATCHED)
    t.record("u1", UnitState.HEALING, attempt=1)
    t.record("u1", UnitState.ACCEPTED)
    states = [e.state for e in t.events if e.unit_id == "u1"]
    assert states == ["DISPATCHED", "HEALING", "ACCEPTED"]


def test_render_text_contains_units_and_states():
    t = Tracker()
    t.record("u1", UnitState.ACCEPTED, score=90)
    out = t.render_text()
    assert "u1" in out and "ACCEPTED" in out


def test_rollup_counts():
    t = Tracker()
    t.record("u1", UnitState.ACCEPTED)
    t.record("u2", UnitState.FAILED)
    t.record("u3", UnitState.ACCEPTED)
    r = t.rollup()
    assert r["ACCEPTED"] == 2 and r["FAILED"] == 1
