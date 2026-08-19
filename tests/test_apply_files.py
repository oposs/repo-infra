# tests/test_apply_files.py
import json

import pytest

from repo_infra.apply import ApplyError, NeedsMerge, apply_file_item, write_asset
from repo_infra.state import Item

ASSET = "name: CI\n# repo-infra: ci v3\njobs:\n  fmt:\n"
OLD = "name: CI\n# repo-infra: ci v1\njobs:\n  fmt:\n"
RENDERED = {".github/workflows/ci.yml": ASSET}


def installed(tmp_path, text):
    target = tmp_path / ".github/workflows/ci.yml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def test_writing_reads_the_file_back_and_asserts_it(tmp_path):
    write_asset(tmp_path, ".github/workflows/ci.yml", ASSET)
    assert (tmp_path / ".github/workflows/ci.yml").read_text(encoding="utf-8") == ASSET


def test_a_missing_file_is_installed(tmp_path):
    written = apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "missing", "")], tmp_path)
    assert written == [".github/workflows/ci.yml"]
    assert (tmp_path / ".github/workflows/ci.yml").read_text(encoding="utf-8") == ASSET


def test_an_item_that_is_already_ok_writes_nothing(tmp_path):
    installed(tmp_path, ASSET)
    assert apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "ok", "")], tmp_path) == []


def test_an_outdated_file_with_no_local_edits_is_upgraded_in_place(tmp_path, plugin_checkout):
    installed(tmp_path, OLD)
    written = apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")],
                              plugin_checkout)
    assert written == [".github/workflows/ci.yml"]


def test_an_outdated_file_with_local_edits_refuses_and_hands_over_the_merge(tmp_path, plugin_checkout):
    installed(tmp_path, OLD.replace("fmt:", "fmt:\n    timeout-minutes: 30"))
    (tmp_path / ".git").mkdir(exist_ok=True)
    with pytest.raises(NeedsMerge) as raised:
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")], plugin_checkout)
    assert raised.value.new.read_text(encoding="utf-8") == ASSET
    assert raised.value.base.read_text(encoding="utf-8") == OLD


def test_a_merged_file_handed_back_is_written_after_its_marker_is_checked(tmp_path, plugin_checkout):
    installed(tmp_path, OLD)
    merged = tmp_path / "merged.yml"
    merged.write_text(ASSET.replace("fmt:", "fmt:\n    timeout-minutes: 30"), encoding="utf-8")
    written = apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")],
                              plugin_checkout, merged=merged)
    assert written == [".github/workflows/ci.yml"]
    assert "timeout-minutes: 30" in (tmp_path / ".github/workflows/ci.yml").read_text(encoding="utf-8")


def test_a_merged_file_at_the_wrong_version_is_refused(tmp_path, plugin_checkout):
    installed(tmp_path, OLD)
    merged = tmp_path / "merged.yml"
    merged.write_text(OLD, encoding="utf-8")   # still says v1
    with pytest.raises(ApplyError, match="v3"):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")],
                        plugin_checkout, merged=merged)


def test_a_conflict_is_never_applied(tmp_path):
    installed(tmp_path, "name: CI\njobs:\n  fmt:\n")
    with pytest.raises(ApplyError, match="conflict"):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "conflict", "not managed")], tmp_path)


def test_the_config_keeps_answers_that_are_already_recorded(tmp_path):
    from repo_infra.apply import write_config
    from repo_infra.detect import DetectResult

    target = tmp_path / ".github/repo-infra.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"skip": {"man-pages": "library, no CLI"},'
                      ' "moving_major_tag": true, "version_files": []}\n', encoding="utf-8")
    write_config(tmp_path, DetectResult(ecosystems=["rust"], version_files=[{"path": "Cargo.toml"}]))
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["skip"] == {"man-pages": "library, no CLI"}
    assert written["moving_major_tag"] is True
    assert written["ecosystems"] == ["rust"]
