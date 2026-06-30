from harness.progress import live_sink, jsonl_sink, webhook_sink, render_board, rollup_of
from harness.tracker_store import TrackerStore


def test_live_sink_streams_each_event():
    seen = []
    s = live_sink(write=seen.append)
    s({"unit_id": "u1", "state": "DISPATCHED", "meta": {"maker": "gemma4"}})
    s({"unit_id": "u1", "state": "ACCEPTED", "meta": {"score": 90}})
    assert len(seen) == 2
    assert "u1" in seen[0] and "DISPATCHED" in seen[0] and "gemma4" in seen[0]


def test_jsonl_sink_appends_json_lines():
    import io, json
    buf = io.StringIO()
    s = jsonl_sink("ignored", opener=lambda p, m: _NoClose(buf))
    s({"unit_id": "u1", "state": "ACCEPTED", "meta": {}})
    line = buf.getvalue().strip()
    assert json.loads(line)["unit_id"] == "u1"


class _NoClose:
    def __init__(self, buf): self.buf = buf
    def __enter__(self): return self.buf
    def __exit__(self, *a): return False


def test_webhook_sink_swallows_failures():
    s = webhook_sink(post=lambda e: (_ for _ in ()).throw(RuntimeError("down")))
    s({"unit_id": "u1", "state": "X", "meta": {}})   # must not raise


def test_render_board_and_rollup():
    board = {"u1": {"state": "ACCEPTED", "score": 90}, "u2": {"state": "FAILED"}}
    out = render_board(board)
    assert "u1" in out and "ACCEPTED" in out and "rollup" in out
    assert rollup_of(board) == {"ACCEPTED": 1, "FAILED": 1}


def test_store_with_live_sink_streams_through_record():
    seen = []
    store = TrackerStore()
    store.add_sink(live_sink(write=seen.append))
    store.record("u1", "DISPATCHED", maker="gemma4")
    store.record("u1", "ACCEPTED", score=88)
    assert len(seen) == 2
    assert store.render_text()   # drop-in render works
    assert store.rollup()["ACCEPTED"] == 1
