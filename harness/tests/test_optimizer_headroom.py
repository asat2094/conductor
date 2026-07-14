from harness.optimizer.backends.headroom import HeadroomCompressor


def test_headroom_available_reflects_import():
    hc = HeadroomCompressor()
    # headroom is not installed in this env -> not available
    assert hc.available() is False


def test_headroom_name():
    assert HeadroomCompressor().name == "headroom"


def test_headroom_retrieve_is_none_without_store():
    assert HeadroomCompressor().retrieve("h") is None
