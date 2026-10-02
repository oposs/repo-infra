# tests/test_apply_files.py
import json
import subprocess

import pytest

from repo_infra.apply import (
    MERGE_DIR,
    ApplyError,
    NeedsMerge,
    apply_file_item,
    commit_item,
    config_text,
    write_asset,
)
from repo_infra.markers import pristine, stamp, strip_stamp
from repo_infra.state import Item

ASSET = "name: CI\n# repo-infra: ci v3\njobs:\n  fmt:\n"
OLD = "name: CI\n# repo-infra: ci v1\njobs:\n  fmt:\n"
RENDERED = {".github/workflows/ci.yml": ASSET}


def git_repo(path):
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)
    return path


def commit_all(path, message):
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=path, check=True, capture_output=True)


def installed(tmp_path, text):
    target = tmp_path / ".github/workflows/ci.yml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def test_writing_reads_the_file_back_and_asserts_it(tmp_path):
    write_asset(tmp_path, ".github/workflows/ci.yml", ASSET)
    assert (tmp_path / ".github/workflows/ci.yml").read_text(encoding="utf-8") == ASSET


def test_a_missing_file_is_installed_stamped(tmp_path):
    written = apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "missing", "")])
    assert written == [".github/workflows/ci.yml"]
    text = (tmp_path / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert strip_stamp(text) == ASSET and pristine(text) is True


def test_an_item_that_is_already_ok_writes_nothing(tmp_path):
    installed(tmp_path, ASSET)
    assert apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "ok", "")]) == []


def test_an_unedited_stamped_file_is_upgraded_in_place(tmp_path):
    installed(tmp_path, stamp(OLD))
    written = apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")])
    assert written == [".github/workflows/ci.yml"]
    text = (tmp_path / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert strip_stamp(text) == ASSET and pristine(text) is True


def test_an_edited_stamped_file_hands_over_new_current_path_and_log(tmp_path):
    git_repo(tmp_path)
    installed(tmp_path, stamp(OLD))
    commit_all(tmp_path, "Install ci from the repo-infra standard")
    edited = stamp(OLD).replace("fmt:", "fmt:\n    timeout-minutes: 30")
    installed(tmp_path, edited)
    commit_all(tmp_path, "ci: longer timeout")
    with pytest.raises(NeedsMerge) as raised:
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")])
    scratch = tmp_path / ".git" / MERGE_DIR
    assert raised.value.new.read_text(encoding="utf-8") == ASSET
    assert raised.value.current.read_text(encoding="utf-8") == edited
    assert (scratch / "ci.path").read_text(encoding="utf-8") == ".github/workflows/ci.yml\n"
    log = raised.value.log.read_text(encoding="utf-8").splitlines()
    assert [line.split(" ", 2)[2] for line in log] == [
        "ci: longer timeout", "Install ci from the repo-infra standard"]
    assert not (scratch / "ci.base").exists()
    assert (tmp_path / ".github/workflows/ci.yml").read_text(encoding="utf-8") == edited


def test_an_unstamped_old_file_hands_over_the_merge(tmp_path):
    # Files installed before D29 carry no stamp; the LLM decides from the log.
    git_repo(tmp_path)
    installed(tmp_path, OLD)
    with pytest.raises(NeedsMerge):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")])
    assert (tmp_path / ".github/workflows/ci.yml").read_text(encoding="utf-8") == OLD


def test_a_crlf_checkout_is_never_overwritten(tmp_path):
    git_repo(tmp_path)
    installed(tmp_path, stamp(OLD).replace("\n", "\r\n"))
    with pytest.raises(NeedsMerge):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")])


def test_a_deleted_stamp_hands_over_the_merge(tmp_path):
    git_repo(tmp_path)
    installed(tmp_path, strip_stamp(stamp(OLD)))
    with pytest.raises(NeedsMerge):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")])


def test_without_git_history_the_log_says_so(tmp_path):
    (tmp_path / ".git").mkdir()
    installed(tmp_path, OLD)
    with pytest.raises(NeedsMerge) as raised:
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")])
    assert raised.value.log.read_text(encoding="utf-8").startswith("(no history:")


def test_a_file_no_commit_touches_yet_says_so_in_the_log(tmp_path):
    git_repo(tmp_path)
    # A first commit, so `git log` succeeds and prints nothing for the file.
    (tmp_path / "README").write_text("x\n", encoding="utf-8")
    commit_all(tmp_path, "Start")
    installed(tmp_path, OLD)
    with pytest.raises(NeedsMerge) as raised:
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")])
    assert raised.value.log.read_text(encoding="utf-8") == (
        "(no history: no commit touches .github/workflows/ci.yml)\n")


def test_a_merge_handed_back_is_written_without_a_stamp(tmp_path):
    git_repo(tmp_path)
    installed(tmp_path, OLD.replace("fmt:", "fmt:\n    timeout-minutes: 15"))
    with pytest.raises(NeedsMerge):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")])
    merged = tmp_path / "merged.yml"
    # Carries a stamp copied from somewhere: apply must strip it.
    merged.write_text(stamp(ASSET.replace("fmt:", "fmt:\n    timeout-minutes: 30")),
                      encoding="utf-8")
    apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")], merged=str(merged))
    text = (tmp_path / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert pristine(text) is None
    assert "timeout-minutes: 30" in text
    for suffix in ("new", "current", "path", "log"):
        assert not (tmp_path / ".git" / MERGE_DIR / f"ci.{suffix}").exists()


def test_a_successful_from_write_removes_its_own_scratch_files_but_not_anothers(tmp_path):
    git_repo(tmp_path)
    installed(tmp_path, OLD.replace("fmt:", "fmt:\n    timeout-minutes: 15"))
    with pytest.raises(NeedsMerge):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")])

    scratch = tmp_path / ".git" / MERGE_DIR
    # A different item's merge is in progress at the same time; only "ci"'s
    # files must be removed, not the whole directory.
    for suffix in ("new", "current", "path", "log"):
        (scratch / f"other.{suffix}").write_text("unrelated", encoding="utf-8")

    merged = tmp_path / "merged.yml"
    merged.write_text(ASSET.replace("fmt:", "fmt:\n    timeout-minutes: 30"), encoding="utf-8")
    apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")], merged=merged)

    for suffix in ("new", "current", "path", "log"):
        assert not (scratch / f"ci.{suffix}").exists()
        assert (scratch / f"other.{suffix}").read_text(encoding="utf-8") == "unrelated"


def test_a_merged_file_at_the_wrong_version_is_refused(tmp_path):
    git_repo(tmp_path)
    installed(tmp_path, OLD.replace("fmt:", "fmt:\n    timeout-minutes: 15"))
    with pytest.raises(NeedsMerge):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")])

    merged = tmp_path / "merged.yml"
    merged.write_text(OLD, encoding="utf-8")   # still says v1
    with pytest.raises(ApplyError, match="v3"):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")], merged=merged)


def test_a_merge_prepared_against_a_now_stale_target_is_refused(tmp_path):
    git_repo(tmp_path)
    edited = OLD.replace("fmt:", "fmt:\n    timeout-minutes: 15")
    installed(tmp_path, edited)
    with pytest.raises(NeedsMerge):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")])

    # An unrelated edit lands on the target after the merge was prepared.
    changed = edited.replace("timeout-minutes: 15", "timeout-minutes: 20")
    installed(tmp_path, changed)

    merged = tmp_path / "merged.yml"
    merged.write_text(ASSET.replace("fmt:", "fmt:\n    timeout-minutes: 30"), encoding="utf-8")
    with pytest.raises(ApplyError, match="changed since the merge was prepared"):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")], merged=merged)

    # Nothing was written: the target still has the unrelated edit, not the merge.
    assert (tmp_path / ".github/workflows/ci.yml").read_text(encoding="utf-8") == changed


def test_from_without_a_prior_refusal_is_refused(tmp_path):
    installed(tmp_path, OLD.replace("fmt:", "fmt:\n    timeout-minutes: 15"))
    merged = tmp_path / "merged.yml"
    merged.write_text(ASSET, encoding="utf-8")
    with pytest.raises(ApplyError, match="apply --item ci"):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")], merged=merged)


def test_a_conflict_is_never_applied(tmp_path):
    installed(tmp_path, "name: CI\njobs:\n  fmt:\n")
    with pytest.raises(ApplyError, match="conflict"):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "conflict", "not managed")])


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
        tmp_path, "workflow-lib", LIB, [Item("workflow-lib", "missing", "")])
    assert written == sorted(LIB)
    for path, text in LIB.items():
        assert strip_stamp((tmp_path / path).read_text(encoding="utf-8")) == text


# workflow-lib v1 (two files) and v2, which changes both and adds a third.
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


def install(tmp_path, files):
    for name, text in files.items():
        target = tmp_path / LIB_TARGET / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def on_disk(tmp_path, name):
    return (tmp_path / LIB_TARGET / name).read_text(encoding="utf-8")


def stamped(files):
    return {name: stamp(text) for name, text in files.items()}


def upgrade(tmp_path, merged=None):
    return apply_file_item(tmp_path, "workflow-lib", RENDERED_V2,
                           [Item("workflow-lib", "outdated", "")], merged=merged)


def test_an_unedited_directory_asset_is_upgraded_file_by_file(tmp_path):
    install(tmp_path, stamped(LIB_V1))
    assert upgrade(tmp_path) == sorted(RENDERED_V2)
    for name, text in LIB_V2.items():
        assert strip_stamp(on_disk(tmp_path, name)) == text
        assert pristine(on_disk(tmp_path, name)) is True


def test_a_file_already_at_the_new_generation_keeps_its_local_edits(tmp_path):
    # A local edit at the current version is healthy (conventions.md), so a
    # file that was merged by hand earlier must survive the rest of the upgrade.
    edited = LIB_V2["bump.js"] + "// local\n"
    install(tmp_path, {"bump.js": edited, "version.js": stamp(LIB_V1["version.js"])})
    assert upgrade(tmp_path) == [LIB_TARGET + "assets.js", LIB_TARGET + "version.js"]
    assert on_disk(tmp_path, "bump.js") == edited


def test_an_edited_old_file_stops_the_upgrade_before_anything_is_written(tmp_path):
    git_repo(tmp_path)
    install(tmp_path, {"bump.js": stamp(LIB_V1["bump.js"]) + "// local\n",
                       "version.js": stamp(LIB_V1["version.js"])})
    with pytest.raises(NeedsMerge):
        upgrade(tmp_path)
    # Writing the unedited files first would leave a half-upgraded directory
    # behind a refusal; nothing moves until the merge is in.
    assert on_disk(tmp_path, "version.js") == stamp(LIB_V1["version.js"])
    assert not (tmp_path / LIB_TARGET / "assets.js").exists()


def test_a_merged_file_goes_back_to_the_file_the_merge_was_prepared_for(tmp_path):
    git_repo(tmp_path)
    install(tmp_path, {"bump.js": stamp(LIB_V1["bump.js"]),
                       "version.js": stamp(LIB_V1["version.js"]) + "// local\n"})
    with pytest.raises(NeedsMerge):
        upgrade(tmp_path)
    merged = tmp_path / "merged.js"
    merged.write_text(LIB_V2["version.js"] + "// local\n", encoding="utf-8")
    assert upgrade(tmp_path, merged=str(merged)) == [LIB_TARGET + "version.js"]
    assert on_disk(tmp_path, "version.js").endswith("// local\n")
    assert list((tmp_path / ".git" / MERGE_DIR).iterdir()) == []
    # The next run finishes the directory and leaves the merged file alone.
    assert upgrade(tmp_path) == [LIB_TARGET + "assets.js", LIB_TARGET + "bump.js"]
    assert on_disk(tmp_path, "version.js").endswith("// local\n")


def test_a_merge_for_a_directory_asset_needs_a_prepared_merge(tmp_path):
    install(tmp_path, stamped(LIB_V1))
    merged = tmp_path / "merged.js"
    merged.write_text(LIB_V2["bump.js"], encoding="utf-8")
    with pytest.raises(ApplyError) as raised:
        upgrade(tmp_path, merged=str(merged))
    assert "no merge is in progress" in str(raised.value)


def test_a_single_file_asset_still_reports_exactly_one_written_path(tmp_path):
    """The generalisation must not turn every item into a list of one that
    callers then mishandle -- commit_item stages whatever comes back."""
    written = apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "missing", "")])
    assert written == [".github/workflows/ci.yml"]


def test_a_failed_git_command_says_what_git_printed_on_stdout(tmp_path):
    # `git commit` reports "nothing to commit" on stdout, not stderr.
    from repo_infra.apply import git

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    with pytest.raises(ApplyError, match="nothing to commit"):
        git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "x")


def test_changed_reads_paths_git_would_quote(tmp_path):
    from repo_infra.apply import changed, git

    git(tmp_path, "init", "-q")
    (tmp_path / "a b.yml").write_text("x\n")
    (tmp_path / 'q"uote.yml').write_text("x\n")
    (tmp_path / "same.yml").write_text("x\n")
    git(tmp_path, "add", "same.yml")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "seed")
    assert changed(tmp_path, ["a b.yml", 'q"uote.yml', "same.yml"]) == ["a b.yml", 'q"uote.yml']


def subject(path):
    return subprocess.run(["git", "log", "-1", "--format=%s"], cwd=path,
                          capture_output=True, text=True, check=True).stdout.strip()


def test_a_hand_merge_is_committed_under_its_own_subject(tmp_path):
    git_repo(tmp_path)
    installed(tmp_path, ASSET)
    commit_item(tmp_path, "ci", [".github/workflows/ci.yml"], merged=True)
    assert subject(tmp_path) == "Merge ci from the repo-infra standard with local edits"


def test_an_install_keeps_the_install_subject(tmp_path):
    git_repo(tmp_path)
    installed(tmp_path, ASSET)
    commit_item(tmp_path, "ci", [".github/workflows/ci.yml"])
    assert subject(tmp_path) == "Install ci from the repo-infra standard"


# --- config_text keeps short lists on one line ----------------------------

MDMOST = {
    "ecosystems": ["rust"],
    "ci": ["ci-man", "ci-rust-musl"],
    "release_assets": ["mdmost-*-x86_64-unknown-linux-musl.tar.gz",
                       "mdmost-*-aarch64-unknown-linux-musl.tar.gz",
                       "mdmost_*_amd64.deb"],
    "rust": {"lint": ["mdmost"], "test": ["mdmost", "pulldown-latex"]},
    "debian": {"distribution": "stable", "component": "main"},
    "empty": [],
}


def test_short_scalar_lists_stay_on_one_line():
    text = config_text(MDMOST)
    assert '  "ecosystems": ["rust"],\n' in text
    assert '  "ci": ["ci-man", "ci-rust-musl"],\n' in text
    assert '  "debian": {"distribution": "stable", "component": "main"},\n' in text
    assert '  "empty": []\n' in text


def test_a_list_wider_than_80_columns_breaks_one_value_per_line():
    text = config_text(MDMOST)
    assert '  "release_assets": [\n    "mdmost-*-x86_64-unknown-linux-musl.tar.gz",\n' in text


def test_a_nested_object_breaks_but_its_short_lists_do_not():
    text = config_text(MDMOST)
    assert '  "rust": {\n    "lint": ["mdmost"],\n    "test": ["mdmost", "pulldown-latex"]\n  },\n' in text


def test_the_text_reads_back_as_the_same_data():
    assert json.loads(config_text(MDMOST)) == MDMOST


def test_the_indent_of_the_original_is_kept():
    text = config_text({"a": {"b": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]}},
                       original='{\n    "a": 1\n}\n')
    assert text.startswith('{\n    "a": {\n        "b": [')
