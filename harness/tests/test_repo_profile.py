from harness.repo_profile import detect_language, profile_repo, RepoProfile


def test_detect_python(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool]\n")
    assert detect_language(str(tmp_path)) == "python"


def test_detect_javascript(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    assert detect_language(str(tmp_path)) == "javascript"


def test_detect_go(tmp_path):
    (tmp_path / "go.mod").write_text("module x\n")
    assert detect_language(str(tmp_path)) == "go"


def test_detect_rust(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\n")
    assert detect_language(str(tmp_path)) == "rust"


def test_detect_generic_when_unknown(tmp_path):
    assert detect_language(str(tmp_path)) == "generic"


def test_profile_python_repo(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool]\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / "CONTRIBUTING.md").write_text("be nice")
    p = profile_repo(str(tmp_path))
    assert p.language == "python"
    assert "pytest" in p.test_cmd
    assert p.has_git is True
    assert p.contributing is True


def test_profile_javascript_repo(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    p = profile_repo(str(tmp_path))
    assert p.language == "javascript"
    assert p.test_cmd == "npm test"
    assert p.has_git is False


def test_profile_go_repo(tmp_path):
    (tmp_path / "go.mod").write_text("module x\n")
    p = profile_repo(str(tmp_path))
    assert p.language == "go"
    assert p.test_cmd == "go test ./..."


def test_profile_rust_repo(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\n")
    p = profile_repo(str(tmp_path))
    assert p.language == "rust"
    assert p.test_cmd == "cargo test"


def test_profile_overrides_win(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool]\n")
    p = profile_repo(str(tmp_path), overrides={"language": "javascript", "test_cmd": "yarn test"})
    assert p.language == "javascript"
    assert p.test_cmd == "yarn test"


def test_generic_repo_has_no_test_cmd(tmp_path):
    p = profile_repo(str(tmp_path))
    assert p.language == "generic"
    assert p.test_cmd is None


def test_contributing_case_insensitive(tmp_path):
    # Test that CONTRIBUTING detection is case-insensitive
    (tmp_path / "contributing.md").write_text("guidelines")
    p = profile_repo(str(tmp_path))
    assert p.contributing is True


def test_profile_minimal_no_git_no_contributing(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    p = profile_repo(str(tmp_path))
    assert p.language == "javascript"
    assert p.has_git is False
    assert p.contributing is False
