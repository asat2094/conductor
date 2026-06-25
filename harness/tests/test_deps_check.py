from harness.deps_check import check_dependencies, OFFLINE


def test_known_package_ok():
    res = check_dependencies(["requests"], resolver=lambda n: True)
    assert res["requests"] == "ok"


def test_unresolvable_package_flagged():
    res = check_dependencies(["totally-not-real-pkg-xyz"], resolver=lambda n: False)
    assert res["totally-not-real-pkg-xyz"] == "unresolvable"


def test_offline_resolver_marks_unverified():
    def offline(name):
        raise ConnectionError("no network")
    res = check_dependencies(["requests"], resolver=offline)
    assert res["requests"] == "unverified"


def test_resolver_returning_offline_sentinel_marks_unverified():
    res = check_dependencies(["requests"], resolver=lambda n: OFFLINE)
    assert res["requests"] == "unverified"


def test_multiple_names_mixed():
    def r(name):
        return name == "real"
    res = check_dependencies(["real", "fake"], resolver=r)
    assert res == {"real": "ok", "fake": "unresolvable"}


def test_empty_list():
    assert check_dependencies([], resolver=lambda n: True) == {}
