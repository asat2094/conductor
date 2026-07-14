from harness.tracker_store import TrackerStore


def test_record_and_board_projection():
    s = TrackerStore()
    s.record("u1", "DISPATCHED", maker="gemma4")
    s.record("u1", "ACCEPTED", score=90)
    s.record("u2", "FAILED")
    b = s.board()
    assert b["u1"]["state"] == "ACCEPTED"
    assert b["u1"]["score"] == 90
    assert b["u2"]["state"] == "FAILED"


def test_events_are_append_only_ordered():
    s = TrackerStore()
    s.record("u1", "DISPATCHED")
    s.record("u1", "HEALING", attempt=1)
    s.record("u1", "ACCEPTED")
    states = [e["state"] for e in s.events()]
    assert states == ["DISPATCHED", "HEALING", "ACCEPTED"]


def test_runs_returns_per_unit_attempt_history():
    s = TrackerStore()
    s.record("u1", "HEALING", attempt=1)
    s.record("u1", "HEALING", attempt=2)
    s.record("u2", "ACCEPTED")
    runs = s.runs("u1")
    assert len(runs) == 2
    assert [r["meta"].get("attempt") for r in runs] == [1, 2]


def test_sink_receives_each_event():
    s = TrackerStore()
    seen = []
    s.add_sink(lambda e: seen.append(e["state"]))
    s.record("u1", "DISPATCHED")
    s.record("u1", "ACCEPTED")
    assert seen == ["DISPATCHED", "ACCEPTED"]


def test_persists_to_file(tmp_path):
    db = str(tmp_path / "t.db")
    s1 = TrackerStore(db); s1.record("u1", "ACCEPTED", score=88)
    s2 = TrackerStore(db)   # reopen same file
    assert s2.board()["u1"]["state"] == "ACCEPTED"
