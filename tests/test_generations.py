import json
import pathlib

import generations

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
    assert not problems, "\n".join(problems)


def test_record_refuses_to_overwrite_a_version(tmp_path):
    (tmp_path / "a.yml").write_text("# repo-infra: a v1\nx\n", encoding="utf-8")
    record = {"a.yml": {"1": "0" * 64}}
    try:
        generations.updated(record, generations.scan(tmp_path))
    except ValueError as error:
        assert "bump the marker" in str(error)
    else:
        raise AssertionError("an existing version was overwritten")


def test_record_adds_a_new_version_and_keeps_the_old(tmp_path):
    (tmp_path / "a.yml").write_text("# repo-infra: a v2\ny\n", encoding="utf-8")
    record = generations.updated({"a.yml": {"1": "0" * 64}}, generations.scan(tmp_path))
    assert set(record["a.yml"]) == {"1", "2"}


def blocks(tmp_path, body):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "manifest.json").write_text(json.dumps({
        "ci_blocks": {"ci-x": {"version": 3, "jobs": ["x"]}},
        "gh": {"rules": {"version": 2, "source": "gh/rules.json"}},
    }), encoding="utf-8")
    (tmp_path / "ci").mkdir()
    (tmp_path / "ci/ci-frame.yml").write_text("# repo-infra: ci v4\njobs:\n", encoding="utf-8")
    (tmp_path / "ci/ci-x.yml").write_text(body, encoding="utf-8")
    (tmp_path / "ci/ci-aggregator.yml").write_text("  ci-passed:\n", encoding="utf-8")
    (tmp_path / "gh").mkdir()
    (tmp_path / "gh/rules.json").write_text("{}\n", encoding="utf-8")
    return generations.scan(tmp_path)


def test_a_block_is_recorded_under_its_manifest_version(tmp_path):
    """A block carries no marker; the manifest gives its version (D11), and
    the frame's tail belongs to the frame's generation."""
    scanned = blocks(tmp_path, "  x:\n")
    assert scanned["ci/ci-x.yml"][0] == 3
    assert scanned["ci/ci-aggregator.yml"][0] == 4
    assert scanned["gh/rules.json"][0] == 2


def test_a_block_reworded_under_the_same_manifest_version_is_refused(tmp_path):
    record = generations.updated({}, blocks(tmp_path, "  x:\n"))
    try:
        generations.updated(record, blocks(tmp_path / "again", "  x:\n    # reworded\n"))
    except ValueError as error:
        assert "ci/ci-x.yml" in str(error)
    else:
        raise AssertionError("a reworded block kept its manifest version")
