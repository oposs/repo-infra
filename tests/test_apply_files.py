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

    scratch = tmp_path / ".git" / MERGE_DIR
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


def test_the_config_keeps_every_decision_it_does_not_compute(tmp_path):
    """`ci` and `publish_local` are decisions only the repository can make, and a
    key this function has never heard of is one too. Rewriting the file used to
    keep a fixed list of keys, so a repository that had chosen ci-rust-musl lost
    it -- and its required musl check -- the first time `apply` recorded an answer."""
    from repo_infra.apply import write_config
    from repo_infra.detect import DetectResult

    target = tmp_path / ".github/repo-infra.json"
    target.parent.mkdir(parents=True)
    kept = {
        "_comment": ["hand-written notes survive a rewrite"],
        "ci": ["ci-rust-musl"],
        "publish_local": [{"job": "publish-deb-container", "assets": ["*.deb"]}],
    }
    target.write_text(json.dumps({**kept, "ecosystems": ["python"]}) + "\n", encoding="utf-8")
    write_config(tmp_path, DetectResult(ecosystems=["rust"], version_files=[{"path": "Cargo.toml"}]))
    written = json.loads(target.read_text(encoding="utf-8"))
    for key, value in kept.items():
        assert written[key] == value, key
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


# A plugin whose history holds workflow-lib v1 (two files) and v2, which
# changes both and adds a third. Each file's base is looked up under its own
# path, so no file is ever compared against a sibling's history.
LIB_V1 = {
    "bump.js": "// repo-infra: workflow-lib v1\nconst bump = 1;\n",
    "version.js": "// repo-infra: workflow-lib v1\nconst version = 1;\n",
}
LIB_V2 = {
    "assets.js": "// repo-infra: workflow-lib v2\nconst assets = 2;\n",
    "bump.js": "// repo-infra: workflow-lib v2\nconst bump = 2;\n",
    "version.js": "// repo-infra: workflow-lib v2\nconst version = 2;\n",
}
LIB_TARGET = ".github/workflows/lib/"
RENDERED_V2 = {LIB_TARGET + name: text for name, text in LIB_V2.items()}


@pytest.fixture(scope="module")
def lib_plugin(tmp_path_factory):
    root = tmp_path_factory.mktemp("lib-plugin")
    lib = root / "assets/workflows/lib"
    lib.mkdir(parents=True)

    def run(*args):
        subprocess.run(args, cwd=root, check=True, capture_output=True)

    run("git", "init", "-q")
    run("git", "config", "user.email", "test@example.com")
    run("git", "config", "user.name", "Test")
    for generation in (LIB_V1, LIB_V2):
        for name, text in generation.items():
            (lib / name).write_text(text, encoding="utf-8")
        run("git", "add", "-A")
        run("git", "commit", "-qm", "generation")
    return root


def install(tmp_path, files):
    for name, text in files.items():
        target = tmp_path / LIB_TARGET / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def on_disk(tmp_path, name):
    return (tmp_path / LIB_TARGET / name).read_text(encoding="utf-8")


def upgrade(tmp_path, plugin, merged=None):
    return apply_file_item(tmp_path, "workflow-lib", RENDERED_V2,
                           [Item("workflow-lib", "outdated", "")], plugin, merged=merged)


def test_an_unedited_directory_asset_is_upgraded_file_by_file(tmp_path, lib_plugin):
    install(tmp_path, LIB_V1)
    written = upgrade(tmp_path, lib_plugin)
    assert written == sorted(RENDERED_V2)
    for name, text in LIB_V2.items():
        assert on_disk(tmp_path, name) == text


def test_a_file_already_at_the_new_generation_keeps_its_local_edits(tmp_path, lib_plugin):
    # A local edit at the current version is healthy (conventions.md), so a
    # file that was merged by hand earlier must survive the rest of the upgrade.
    edited = LIB_V2["bump.js"] + "// local\n"
    install(tmp_path, {"bump.js": edited, "version.js": LIB_V1["version.js"]})
    written = upgrade(tmp_path, lib_plugin)
    assert written == [LIB_TARGET + "assets.js", LIB_TARGET + "version.js"]
    assert on_disk(tmp_path, "bump.js") == edited


def test_an_edited_old_file_stops_the_upgrade_before_anything_is_written(tmp_path, lib_plugin):
    (tmp_path / ".git").mkdir()
    edited = LIB_V1["version.js"] + "// local\n"
    install(tmp_path, {"bump.js": LIB_V1["bump.js"], "version.js": edited})
    with pytest.raises(NeedsMerge) as raised:
        upgrade(tmp_path, lib_plugin)
    # Writing the unedited files first would leave a half-upgraded directory
    # behind a refusal; nothing moves until the merge is in.
    assert on_disk(tmp_path, "bump.js") == LIB_V1["bump.js"]
    assert not (tmp_path / LIB_TARGET / "assets.js").exists()
    scratch = tmp_path / ".git" / MERGE_DIR
    assert (scratch / "workflow-lib.base").read_text(encoding="utf-8") == LIB_V1["version.js"]
    assert (scratch / "workflow-lib.new").read_text(encoding="utf-8") == LIB_V2["version.js"]
    assert (scratch / "workflow-lib.current").read_text(encoding="utf-8") == edited
    assert str(raised.value.current).endswith(LIB_TARGET + "version.js")


def test_a_merged_file_goes_back_to_the_file_the_merge_was_prepared_for(tmp_path, lib_plugin):
    (tmp_path / ".git").mkdir()
    install(tmp_path, {"bump.js": LIB_V1["bump.js"],
                       "version.js": LIB_V1["version.js"] + "// local\n"})
    with pytest.raises(NeedsMerge):
        upgrade(tmp_path, lib_plugin)
    merged = tmp_path / "merged.js"
    merged.write_text(LIB_V2["version.js"] + "// local\n", encoding="utf-8")
    assert upgrade(tmp_path, lib_plugin, merged=str(merged)) == [LIB_TARGET + "version.js"]
    assert on_disk(tmp_path, "version.js").endswith("// local\n")
    assert list((tmp_path / ".git" / MERGE_DIR).iterdir()) == []
    # The next run finishes the directory and leaves the merged file alone.
    assert upgrade(tmp_path, lib_plugin) == [LIB_TARGET + "assets.js", LIB_TARGET + "bump.js"]
    assert on_disk(tmp_path, "version.js").endswith("// local\n")


def test_a_merge_for_a_directory_asset_needs_a_prepared_merge(tmp_path, lib_plugin):
    install(tmp_path, LIB_V1)
    merged = tmp_path / "merged.js"
    merged.write_text(LIB_V2["bump.js"], encoding="utf-8")
    with pytest.raises(ApplyError) as raised:
        upgrade(tmp_path, lib_plugin, merged=str(merged))
    assert "no merge is in progress" in str(raised.value)


def test_without_the_plugin_history_an_old_file_counts_as_edited(tmp_path):
    # No history means no proof the file is unedited. Overwriting it anyway
    # would be the guess D12 forbids.
    (tmp_path / ".git").mkdir()
    install(tmp_path, LIB_V1)
    with pytest.raises(NeedsMerge):
        upgrade(tmp_path, tmp_path / "not-a-plugin")
    assert on_disk(tmp_path, "bump.js") == LIB_V1["bump.js"]


def test_a_single_file_asset_still_reports_exactly_one_written_path(tmp_path):
    """The generalisation must not turn every item into a list of one that
    callers then mishandle -- commit_item stages whatever comes back."""
    written = apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "missing", "")], tmp_path)
    assert written == [".github/workflows/ci.yml"]


def test_a_failed_git_command_says_what_git_printed_on_stdout(tmp_path):
    # `git commit` reports "nothing to commit" on stdout, not stderr.
    from repo_infra.apply import _git

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    with pytest.raises(ApplyError, match="nothing to commit"):
        _git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "x")
