import json
import pathlib

import generations
import pytest

ASSETS = pathlib.Path(__file__).resolve().parents[1] / "skills/repo-infra/assets"
RECORD = ASSETS / "generations.json"


def test_every_asset_text_is_recorded_under_its_version():
    recorded = json.loads(RECORD.read_text(encoding="utf-8"))
    problems = []
    for path, (version, digest) in sorted(generations.scan(ASSETS).items()):
        known = recorded.get(path, {}).get(str(version))
        if known is None:
            problems.append(f"{path}: v{version} is not recorded; run make generations")
        elif known != digest:
            problems.append(f"{path}: the text changed but its version is still "
                            f"v{version}; bump the marker (or, for a block, its "
                            "version in manifest.json), then run make generations")
    scanned = generations.scan(ASSETS)
    problems += generations.vanished(recorded, scanned)
    assert not problems, "\n".join(problems)


def test_record_refuses_to_overwrite_a_version(tmp_path):
    (tmp_path / "a.yml").write_text("# repo-infra: a v1\nx\n", encoding="utf-8")
    record = {"a.yml": {"1": "0" * 64}}
    with pytest.raises(ValueError, match="bump the marker"):
        generations.updated(record, generations.scan(tmp_path))


def test_record_adds_a_new_version_and_keeps_the_old(tmp_path):
    (tmp_path / "a.yml").write_text("# repo-infra: a v2\ny\n", encoding="utf-8")
    record = generations.updated({"a.yml": {"1": "0" * 64}}, generations.scan(tmp_path))
    assert set(record["a.yml"]) == {"1", "2"}


def test_the_ruleset_is_recorded_under_its_manifest_version(tmp_path):
    """The ruleset carries no marker; the manifest gives its version."""
    (tmp_path / "manifest.json").write_text(json.dumps({
        "gh": {"rules": {"version": 2, "source": "gh/rules.json"}},
    }), encoding="utf-8")
    (tmp_path / "gh").mkdir()
    (tmp_path / "gh/rules.json").write_text("{}\n", encoding="utf-8")
    assert generations.scan(tmp_path)["gh/rules.json"][0] == 2


def test_a_recorded_path_that_is_no_longer_scanned_is_reported(tmp_path):
    (tmp_path / "a.yml").write_text("# repo-infra: a v1\nx\n", encoding="utf-8")
    record = {"a.yml": {"1": generations.scan(tmp_path)["a.yml"][1]},
              "gone.yml": {"1": "0" * 64}}
    assert generations.vanished(record, generations.scan(tmp_path)) == [
        "gone.yml is recorded but no longer scanned; if it was removed on "
        "purpose, delete it from generations.json"]


def test_record_refuses_to_drop_a_path_that_is_no_longer_scanned(tmp_path):
    (tmp_path / "a.yml").write_text("# repo-infra: a v1\nx\n", encoding="utf-8")
    record = {"gone.yml": {"1": "0" * 64}}
    with pytest.raises(ValueError, match="gone.yml is recorded but no longer scanned"):
        generations.updated(record, generations.scan(tmp_path))
