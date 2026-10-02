import json
import pathlib

import generations

ASSETS = pathlib.Path(__file__).resolve().parents[1] / "skills/repo-infra/assets"
RECORD = ASSETS / "generations.json"


def test_every_asset_text_is_recorded_under_its_marker_version():
    recorded = json.loads(RECORD.read_text(encoding="utf-8"))
    problems = []
    for path, (version, digest) in sorted(generations.scan(ASSETS).items()):
        known = recorded.get(path, {}).get(str(version))
        if known is None:
            problems.append(f"{path}: v{version} is not recorded; run make generations")
        elif known != digest:
            problems.append(f"{path}: the text changed but the marker still says "
                            f"v{version}; bump the marker, then run make generations")
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
