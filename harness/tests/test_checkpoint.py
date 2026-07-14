from harness.checkpoint import make_checkpoint, save_checkpoint, load_checkpoint, units_to_resume, replay_board


def test_make_checkpoint_lists_accepted():
    board = {"a": {"state": "ACCEPTED"}, "b": {"state": "FAILED"}, "c": {"state": "ACCEPTED"}}
    ck = make_checkpoint(board)
    assert sorted(ck["accepted"]) == ["a", "c"]
    assert ck["board"] == board


def test_save_and_load_roundtrip():
    store = {}
    ck = {"accepted": ["a"], "board": {"a": {"state": "ACCEPTED"}}}
    save_checkpoint(ck, "p", dumper=lambda obj, path: store.__setitem__(path, obj))
    out = load_checkpoint("p", loader=lambda path: store[path])
    assert out == ck


def test_units_to_resume_skips_accepted():
    ck = {"accepted": ["a", "c"], "board": {}}
    assert units_to_resume(["a", "b", "c", "d"], ck) == ["b", "d"]


def test_units_to_resume_empty_checkpoint_runs_all():
    assert units_to_resume(["a", "b"], {"accepted": [], "board": {}}) == ["a", "b"]


def test_replay_board_projects_latest_state():
    events = [
        {"unit_id": "a", "state": "DISPATCHED", "meta": {}},
        {"unit_id": "a", "state": "ACCEPTED", "meta": {"score": 90}},
        {"unit_id": "b", "state": "FAILED", "meta": {}},
    ]
    board = replay_board(events)
    assert board["a"]["state"] == "ACCEPTED" and board["a"]["score"] == 90
    assert board["b"]["state"] == "FAILED"
