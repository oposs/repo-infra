import pathlib

from repo_infra.detect import Detection

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
MINI = HERE / "fixtures/detection-mini.json"
REAL = ROOT / "skills/repo-infra/assets/detection.json"


def mini(tmp_path, files):
    for name, body in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return Detection.load(MINI).detect(tmp_path)


def test_a_repo_with_no_signals_still_gets_the_workflow_library_block(tmp_path):
    result = mini(tmp_path, {})
    assert result.ecosystems == []
    assert result.blocks == ["ci-lib"]


def test_one_signal_selects_one_ecosystem(tmp_path):
    result = mini(tmp_path, {"alpha.toml": 'version = "1.0.0"\n'})
    assert result.ecosystems == ["alpha"]
    assert result.blocks == ["ci-lib", "ci-alpha"]
    assert result.version_files[0]["path"] == "alpha.toml"


def test_a_none_signal_suppresses_a_match(tmp_path):
    result = mini(tmp_path, {"beta.json": "{}\n", "not-beta": ""})
    assert result.ecosystems == []


def test_two_ecosystems_produce_one_sorted_block_list(tmp_path):
    result = mini(tmp_path, {"alpha.toml": "\n", "beta.json": "{}\n"})
    assert result.ecosystems == ["alpha", "beta"]
    assert result.blocks == ["ci-lib", "ci-alpha", "ci-beta"]


def test_a_directory_signal_needs_a_directory(tmp_path):
    (tmp_path / "bin").mkdir()
    result = mini(tmp_path, {})
    assert result.candidates == ["man-pages"]


def test_an_ambiguity_is_reported_and_does_not_stop_detection(tmp_path):
    result = mini(tmp_path, {"alpha.toml": "\n", "beta.json": "{}\n"})
    assert [a["id"] for a in result.ambiguities] == ["alpha-or-beta"]
    assert "authoritative" in result.ambiguities[0]["question"]


def test_detection_is_deterministic(tmp_path):
    files = {"alpha.toml": "\n", "beta.json": "{}\n"}
    assert mini(tmp_path, files).blocks == mini(tmp_path, files).blocks


# --- the real detection file ------------------------------------------------

def test_the_real_file_detects_this_repository_as_a_claude_plugin():
    result = Detection.load(REAL).detect(HERE / "fixtures/repo-claude-plugin")
    assert result.ecosystems == ["claude-plugin"]
    assert result.blocks == ["ci-lib", "ci-claude-plugin"]


def test_the_real_file_detects_a_python_repository():
    result = Detection.load(REAL).detect(HERE / "fixtures/repo-python")
    assert result.ecosystems == ["python"]


def test_the_real_file_reports_two_node_lockfiles_as_ambiguous():
    result = Detection.load(REAL).detect(HERE / "fixtures/repo-node-ambiguous")
    assert [a["id"] for a in result.ambiguities] == ["node-lockfiles"]
