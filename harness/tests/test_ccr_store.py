from harness.ccr_store import CCRStore


def test_store_returns_stable_handle():
    s = CCRStore()
    h1 = s.store("some original text")
    h2 = s.store("some original text")
    assert h1 == h2 and h1.startswith("ccr:")


def test_retrieve_returns_original():
    s = CCRStore()
    h = s.store("the full uncompressed detail")
    assert s.retrieve(h) == "the full uncompressed detail"


def test_retrieve_unknown_handle_is_none():
    s = CCRStore()
    assert s.retrieve("ccr:doesnotexist") is None


def test_retrieve_expired_is_none():
    t = {"now": 0.0}
    s = CCRStore(ttl_seconds=100, clock=lambda: t["now"])
    h = s.store("x")
    t["now"] = 50.0
    assert s.retrieve(h) == "x"      # within ttl
    t["now"] = 200.0
    assert s.retrieve(h) is None     # expired -> degrade-clean


def test_different_content_different_handle():
    s = CCRStore()
    assert s.store("a") != s.store("b")


def test_handles_excludes_expired():
    t = {"now": 0.0}
    s = CCRStore(ttl_seconds=100, clock=lambda: t["now"])
    h = s.store("x")
    assert h in s.handles()
    t["now"] = 200.0
    assert s.handles() == []            # expired handle excluded (matches retrieve)
