import json
import os
import pathlib

import generations
import pytest

from repo_infra import check
from repo_infra.pieces import _source, load_pieces, load_published

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
    problems += generations.vanished(recorded, scanned, generations.piece_sources(ASSETS))
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


ON_CI = os.environ.get("GITHUB_ACTIONS") == "true"


def _tags():
    """The release tags, fetched first on GitHub Actions: actions/checkout
    clones one commit and no tags, and the tests that need them skipped
    there on every run. On CI a missing tag fails, so the guard cannot go
    quiet again; elsewhere it skips."""
    try:
        tags = generations.release_tags()
        if not tags and ON_CI:
            generations.fetch_release_tags()
            tags = generations.release_tags()
    except generations.NoHistory as error:
        (pytest.fail if ON_CI else pytest.skip)(str(error))
    if not tags:
        (pytest.fail if ON_CI else pytest.skip)(
            "this checkout has no release tags (a shallow clone)")
    return tags


def test_every_released_piece_file_is_recorded_under_its_version():
    """Decision L: a repository still on a released version reads outdated,
    never edited. v0.2.0 shipped changelog v2, release-pr v3, workflow-lib v4
    and container v1, and none was recorded, so an unedited v0.2.0 repository
    read edited and apply asked for a hand merge of every file."""
    tags = _tags()
    recorded = json.loads(RECORD.read_text(encoding="utf-8"))
    problems = []
    for tag in tags:
        for path, (version, digest) in generations.released(tag).items():
            known = recorded.get(path, {}).get(str(version))
            if known != digest:
                problems.append(f"{tag}: {path} v{version} is "
                                f"{'not recorded' if known is None else 'recorded with other text'}"
                                "; run make generations")
    assert not problems, "\n".join(problems)


def test_a_release_maps_old_asset_paths_to_the_piece_paths():
    if "v0.2.0" not in _tags():
        pytest.skip("this checkout lacks the v0.2.0 tag")
    found = generations.released("v0.2.0")
    assert found["pieces/changelog/changelog.yml"][0] == 2
    assert found["pieces/release-pr/release-pr.yml"][0] == 3
    assert found["pieces/container/container.mk"][0] == 1
    assert found["pieces/workflow-lib/lib/bump.js"][0] == 4
    assert found["pieces/workflow-lib/lib/bump.test.js"][0] == 4


def test_a_released_version_is_added_and_a_conflicting_one_refused():
    record = {"a.yml": {"2": "1" * 64}}
    merged = generations.with_released(record, {"a.yml": (1, "0" * 64)})
    assert merged == {"a.yml": {"1": "0" * 64, "2": "1" * 64}}
    with pytest.raises(ValueError, match="a.yml: v2 is recorded with other text"):
        generations.with_released(record, {"a.yml": (2, "0" * 64)})


def test_an_unedited_repository_of_every_release_reads_outdated_or_current(tmp_path):
    """The repository side of the record: every piece copied as a release
    shipped it reads outdated or current, never edited."""
    tags = _tags()
    pieces, published = load_pieces(ASSETS), load_published(ASSETS)
    wrong = []
    for tag in tags:
        root = tmp_path / tag
        files = generations.released_files(tag)
        for name, piece in pieces.items():
            source = _source(name, {"target": piece.target})
            for path, (_, data) in files.items():
                if path == source or path.startswith(source + "/"):
                    target = root / (piece.target + path[len(source):])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
        wrong += [f"{tag}: {name} reads edited" for name, piece in pieces.items()
                  if check.piece_state(root, piece, published.get(name, {})).state
                  == "edited"]
    assert not wrong, "\n".join(wrong)


def _dir_piece_store(tmp_path, files):
    (tmp_path / "manifest.json").write_text(json.dumps({"pieces": {
        "lib-x": {"target": ".github/workflows/lib", "kind": "dir", "header": "a.js"}}}),
        encoding="utf-8")
    folder = tmp_path / "pieces/lib-x/lib"
    folder.mkdir(parents=True)
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_a_file_a_piece_dropped_stays_recorded_and_the_record_is_stable(tmp_path):
    """A piece version that stops shipping a file keeps the file's published
    bytes in the record: apply removes a copy at those bytes, and only them.
    `make generations` used to refuse the dropped path and advise deleting it,
    and the next run re-added it from the release tags, round after round."""
    store = _dir_piece_store(tmp_path, {"a.js": "// repo-infra: lib-x v2\na2\n"})
    record = {"pieces/lib-x/lib/a.js": {"1": "1" * 64},
              "pieces/lib-x/lib/gone.js": {"1": "2" * 64}}
    scanned = generations.scan(store)
    shipped = generations.piece_sources(store)
    assert generations.vanished(record, scanned, shipped) == []
    once = generations.updated(record, scanned, shipped)
    assert once["pieces/lib-x/lib/gone.js"] == {"1": "2" * 64}
    assert generations.updated(once, scanned, shipped) == once


def test_a_file_of_a_piece_the_manifest_no_longer_names_is_still_reported(tmp_path):
    store = _dir_piece_store(tmp_path, {"a.js": "// repo-infra: lib-x v2\na2\n"})
    record = {"pieces/old-piece/old.yml": {"1": "2" * 64}}
    assert generations.vanished(record, generations.scan(store),
                                generations.piece_sources(store)) == [
        "pieces/old-piece/old.yml is recorded but no longer scanned; if it was "
        "removed on purpose, delete it from generations.json"]


def test_the_shipped_store_survives_a_dropped_file_twice():
    """The repro of the follow-up review on the real store: drop one file of
    workflow-lib from the scan and run the update twice."""
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    scanned = generations.scan(ASSETS)
    scanned.pop("pieces/workflow-lib/lib/bump.test.js")
    shipped = generations.piece_sources(ASSETS)
    once = generations.updated(record, scanned, shipped)
    assert "pieces/workflow-lib/lib/bump.test.js" in once
    assert generations.updated(once, scanned, shipped) == once
