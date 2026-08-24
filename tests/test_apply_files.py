# tests/test_apply_files.py
import json
import subprocess

import pytest

from repo_infra.apply import (
    MERGE_DIR,
    ApplyError,
    NeedsMerge,
    apply_file_item,
    base_version_of,
    write_asset,
)
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
    # Local edits force the refusal, which is what records the snapshot that
    # --from checks against.
    installed(tmp_path, OLD.replace("fmt:", "fmt:\n    timeout-minutes: 15"))
    with pytest.raises(NeedsMerge):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")], plugin_checkout)

    merged = tmp_path / "merged.yml"
    merged.write_text(ASSET.replace("fmt:", "fmt:\n    timeout-minutes: 30"), encoding="utf-8")
    written = apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")],
                              plugin_checkout, merged=merged)
    assert written == [".github/workflows/ci.yml"]
    assert "timeout-minutes: 30" in (tmp_path / ".github/workflows/ci.yml").read_text(encoding="utf-8")


def test_a_successful_from_write_removes_its_own_scratch_files_but_not_anothers(
        tmp_path, plugin_checkout):
    installed(tmp_path, OLD.replace("fmt:", "fmt:\n    timeout-minutes: 15"))
    with pytest.raises(NeedsMerge):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")], plugin_checkout)

    scratch = tmp_path / MERGE_DIR
    # A different item's merge is in progress at the same time; only "ci"'s
    # files must be removed, not the whole directory.
    for suffix in ("base", "new", "current"):
        (scratch / f"other.{suffix}").write_text("unrelated", encoding="utf-8")

    merged = tmp_path / "merged.yml"
    merged.write_text(ASSET.replace("fmt:", "fmt:\n    timeout-minutes: 30"), encoding="utf-8")
    apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")],
                    plugin_checkout, merged=merged)

    for suffix in ("base", "new", "current"):
        assert not (scratch / f"ci.{suffix}").exists()
        assert (scratch / f"other.{suffix}").read_text(encoding="utf-8") == "unrelated"


def test_a_merged_file_at_the_wrong_version_is_refused(tmp_path, plugin_checkout):
    installed(tmp_path, OLD.replace("fmt:", "fmt:\n    timeout-minutes: 15"))
    with pytest.raises(NeedsMerge):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")], plugin_checkout)

    merged = tmp_path / "merged.yml"
    merged.write_text(OLD, encoding="utf-8")   # still says v1
    with pytest.raises(ApplyError, match="v3"):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")],
                        plugin_checkout, merged=merged)


def test_a_merge_prepared_against_a_now_stale_target_is_refused(tmp_path, plugin_checkout):
    edited = OLD.replace("fmt:", "fmt:\n    timeout-minutes: 15")
    installed(tmp_path, edited)
    with pytest.raises(NeedsMerge):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")], plugin_checkout)

    # An unrelated edit lands on the target after the merge was prepared.
    changed = edited.replace("timeout-minutes: 15", "timeout-minutes: 20")
    installed(tmp_path, changed)

    merged = tmp_path / "merged.yml"
    merged.write_text(ASSET.replace("fmt:", "fmt:\n    timeout-minutes: 30"), encoding="utf-8")
    with pytest.raises(ApplyError, match="changed since the merge was prepared"):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")],
                        plugin_checkout, merged=merged)

    # Nothing was written: the target still has the unrelated edit, not the merge.
    assert (tmp_path / ".github/workflows/ci.yml").read_text(encoding="utf-8") == changed


def test_from_without_a_prior_refusal_is_refused(tmp_path, plugin_checkout):
    installed(tmp_path, OLD.replace("fmt:", "fmt:\n    timeout-minutes: 15"))
    merged = tmp_path / "merged.yml"
    merged.write_text(ASSET, encoding="utf-8")
    with pytest.raises(ApplyError, match="apply --item ci"):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")],
                        plugin_checkout, merged=merged)


def test_a_conflict_is_never_applied(tmp_path):
    installed(tmp_path, "name: CI\njobs:\n  fmt:\n")
    with pytest.raises(ApplyError, match="conflict"):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "conflict", "not managed")], tmp_path)


def test_base_version_of_finds_the_base_when_the_plugin_root_is_a_subdirectory(
        tmp_path_factory):
    """The real plugin checkout is a git repository with `skills/repo-infra`
    as a *subdirectory* of its root, not the root itself -- unlike
    `plugin_checkout` above, where the fixture's root and the plugin root are
    the same directory. `git show rev:path` resolves `path` from the
    repository root, never from cwd, so calling it with the asset path alone
    always failed to find a base that plainly exists in history."""
    root = tmp_path_factory.mktemp("plugin-nested")
    plugin_root = root / "skills/repo-infra"
    assets = plugin_root / "assets/ci"
    assets.mkdir(parents=True)

    def run(*args):
        subprocess.run(args, cwd=root, check=True, capture_output=True)

    run("git", "init", "-q")
    run("git", "config", "user.email", "test@example.com")
    run("git", "config", "user.name", "Test")
    (assets / "ci-frame.yml").write_text(OLD, encoding="utf-8")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "v1")

    assert base_version_of(plugin_root, "assets/ci/ci-frame.yml", 1) == OLD


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


# --- directory assets ship more than one file ----------------------------

LIB = {
    ".github/workflows/lib/bump.js": "// repo-infra: workflow-lib v1\nmodule.exports = {};\n",
    ".github/workflows/lib/checks.js": "// repo-infra: workflow-lib v1\nmodule.exports = {};\n",
    ".github/workflows/lib/version.js": "// repo-infra: workflow-lib v1\nmodule.exports = {};\n",
}


def test_a_missing_directory_asset_installs_every_file(tmp_path):
    """One marker, copied into each file, is still one item -- so an item can
    name nine paths. Installing the first alone leaves `check` reporting
    `files disagree` on a conversion that just reported success."""
    written = apply_file_item(
        tmp_path, "workflow-lib", LIB, [Item("workflow-lib", "missing", "")], tmp_path)
    assert written == sorted(LIB)
    for path, text in LIB.items():
        assert (tmp_path / path).read_text(encoding="utf-8") == text


def test_an_outdated_directory_asset_refuses_instead_of_guessing(tmp_path):
    """`_asset_source` finds an asset by its marker, which for a directory
    resolves to whichever file sorts first -- so every later file would be
    compared against the wrong history. D12: the tool never guesses."""
    for path, text in LIB.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    with pytest.raises(ApplyError) as raised:
        apply_file_item(tmp_path, "workflow-lib", LIB,
                        [Item("workflow-lib", "outdated", "")], tmp_path)
    assert "3 files" in str(raised.value)
    for path in LIB:
        assert path in str(raised.value)


def test_a_merge_is_refused_for_a_directory_asset(tmp_path):
    merged = tmp_path / "merged.js"
    merged.write_text("// repo-infra: workflow-lib v1\n", encoding="utf-8")
    with pytest.raises(ApplyError) as raised:
        apply_file_item(tmp_path, "workflow-lib", LIB,
                        [Item("workflow-lib", "missing", "")], tmp_path, merged=str(merged))
    assert "single-file asset" in str(raised.value)


def test_a_single_file_asset_still_reports_exactly_one_written_path(tmp_path):
    """The generalisation must not turn every item into a list of one that
    callers then mishandle -- commit_item stages whatever comes back."""
    written = apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "missing", "")], tmp_path)
    assert written == [".github/workflows/ci.yml"]
