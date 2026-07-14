from harness.retrieve import slice_file, build_slices, slice_bytes


def test_slice_single_range():
    text = "a\nb\nc\nd\ne\n"
    out = slice_file(text, [(2, 4)])   # lines b,c,d
    assert out == "b\nc\nd"


def test_slice_clamps_out_of_range():
    text = "a\nb\nc\n"
    out = slice_file(text, [(1, 99)])
    assert out == "a\nb\nc"


def test_slice_multiple_noncontiguous_ranges_separated():
    text = "1\n2\n3\n4\n5\n6\n"
    out = slice_file(text, [(1, 2), (5, 6)])
    assert "1\n2" in out and "5\n6" in out
    assert "..." in out   # separator between non-contiguous spans


def test_build_slices_omits_undeclared_files():
    files = {"a.py": "x\ny\nz\n", "b.py": "p\nq\n"}
    slices = [{"path": "a.py", "start_line": 1, "end_line": 2}]
    out = build_slices(files, slices)
    assert "a.py" in out and "b.py" not in out   # only declared slice (minimal)
    assert out["a.py"] == "x\ny"


def test_slice_bytes_counts_total():
    assert slice_bytes({"a.py": "abc", "b.py": "de"}) == 5
