import json
import pathlib
from types import SimpleNamespace

import pytest
from piecekit import digest, install, lib_file, make_assets, workflow_piece

from repo_infra import callers, check
from repo_infra.check import layout_items
from repo_infra.pieces import load_pieces, load_published
from repo_infra.remote import Facts

ASSETS = pathlib.Path(__file__).resolve().parents[1] / "skills/repo-infra/assets"
OLD = workflow_piece("ri-x", 1, body="old")
NEW = workflow_piece("ri-x", 2, body="new")
LIB1 = {"a.js": lib_file("lib-x", 1, "a1"), "b.js": lib_file("lib-x", 1, "b1")}
LIB2 = {"a.js": lib_file("lib-x", 2, "a2"), "b.js": lib_file("lib-x", 2, "b2")}


@pytest.fixture
def store(tmp_path):
    history = [("ri-x", None, OLD)] + [("lib-x", f, t) for f, t in LIB1.items()]
    return make_assets(tmp_path / "assets", {"ri-x": NEW, "lib-x": LIB2}, history,
                       core=("lib-x",))


def rows(root, store):
    items = check.piece_items(root, load_pieces(store), load_published(store))
    return [(i.name, i.state, i.detail) for i in items]


def test_a_copy_of_the_latest_version_is_current(tmp_path, store):
    root = tmp_path / "repo"
    install(root, ".github/workflows/ri-x.yml", NEW)
    for f, t in LIB2.items():
        install(root, f".github/workflows/lib-x/{f}", t)
    assert rows(root, store) == [("lib-x", "current", "v2"), ("ri-x", "current", "v2")]


def test_a_copy_of_an_older_version_is_outdated(tmp_path, store):
    root = tmp_path / "repo"
    install(root, ".github/workflows/ri-x.yml", OLD)
    assert ("ri-x", "outdated", "v1 installed, v2 available; apply replaces it") in rows(
        root, store)


def test_a_copy_that_matches_no_version_is_edited(tmp_path, store):
    root = tmp_path / "repo"
    install(root, ".github/workflows/ri-x.yml", OLD + "# mine\n")
    (name, state, detail), = [r for r in rows(root, store) if r[0] == "ri-x"]
    assert state == "edited"
    assert detail.startswith(".github/workflows/ri-x.yml matches no published version")


def test_an_edited_file_claiming_the_current_version_says_how_to_restore_it(
        tmp_path, store):
    """A finished --from merge leaves exactly this state; apply has nothing to
    merge into it, so the way back is to delete the file and install it again."""
    root = tmp_path / "repo"
    install(root, ".github/workflows/ri-x.yml", NEW + "# mine\n")
    (detail,) = [d for n, s, d in rows(root, store) if n == "ri-x"]
    assert "hand merge" not in detail
    assert detail == (".github/workflows/ri-x.yml claims v2, the current version, but "
                      "matches no published version of ri-x. Pieces are used as published: "
                      "move the change into a caller, then delete "
                      ".github/workflows/ri-x.yml and run `apply --item ri-x` to restore it")


def test_an_edited_file_claiming_an_older_version_is_left_for_a_hand_merge(tmp_path, store):
    root = tmp_path / "repo"
    install(root, ".github/workflows/ri-x.yml", OLD + "# mine\n")
    (detail,) = [d for n, s, d in rows(root, store) if n == "ri-x"]
    assert "apply stops here with the files for a hand merge" in detail


def test_a_marker_newer_than_the_plugin_says_update_the_plugin(tmp_path, store):
    root = tmp_path / "repo"
    install(root, ".github/workflows/ri-x.yml", workflow_piece("ri-x", 9))
    assert ("ri-x", "edited", ".github/workflows/ri-x.yml says v9, newer than this "
            "plugin's v2; update the plugin") in rows(root, store)


def test_a_core_piece_that_is_absent_is_missing_and_another_is_not_reported(tmp_path, store):
    assert rows(tmp_path / "repo", store) == [
        ("lib-x", "missing", "not installed; every repository carries it")]


def test_a_half_upgraded_directory_is_outdated(tmp_path, store):
    root = tmp_path / "repo"
    install(root, ".github/workflows/lib-x/a.js", LIB2["a.js"])
    install(root, ".github/workflows/lib-x/b.js", LIB1["b.js"])
    assert ("lib-x", "outdated", "v1 installed, v2 available; apply replaces it") in rows(
        root, store)


def test_a_project_file_in_a_piece_directory_is_ignored(tmp_path, store):
    root = tmp_path / "repo"
    for f, t in LIB2.items():
        install(root, f".github/workflows/lib-x/{f}", t)
    install(root, ".github/workflows/lib-x/own.js", "module.exports = {};\n")
    assert ("lib-x", "current", "v2") in rows(root, store)


def test_a_dependency_that_is_absent_is_missing(tmp_path):
    needy = workflow_piece("ri-y", 1, header="# Pieces: ri-x\n")
    store = make_assets(tmp_path / "assets", {"ri-x": NEW, "ri-y": needy})
    root = tmp_path / "repo"
    install(root, ".github/workflows/ri-y.yml", needy)
    assert ("ri-x", "missing", "ri-y needs it") in rows(root, store)


def test_an_assembled_file_is_unknown_and_points_at_onboarding(tmp_path, store):
    root = tmp_path / "repo"
    install(root, ".github/workflows/ci.yml", "name: CI\n# repo-infra: ci v2\n"
            "jobs:\n  # repo-infra: ci-rust v3\n  rust-plan:\n    runs-on: x\n")
    (row,) = [r for r in rows(root, store) if r[1] == "unknown"]
    assert row[0] == "ci"
    assert row[2].startswith(".github/workflows/ci.yml carries `repo-infra: ci v2`")
    assert "references/onboarding.md" in row[2]


def config(tmp_path, data, docs=None):
    root = tmp_path / "repo"
    if data is not None:
        install(root, ".github/repo-infra.json",
                data if isinstance(data, str) else json.dumps(data))
    return [(i.name, i.state, i.detail) for i in check.config_items(root, docs or {})]


VERSIONS = [{"path": "pyproject.toml", "pattern": "x", "replacement": "y", "verify": "z"}]


def test_a_missing_config_is_missing(tmp_path):
    assert config(tmp_path, None)[0][1] == "missing"


def test_a_config_that_is_not_json(tmp_path):
    assert config(tmp_path, "{")[0][1] == "problem"


def test_obsolete_and_unknown_keys_are_problems(tmp_path):
    found = config(tmp_path, {"version_files": VERSIONS, "ci": ["ci-man"],
                              "ecosystems": [], "colour": 1, "_comment": "fine"})
    assert ("repo-infra.json", "problem", "ci, ecosystems: no longer read; the callers "
            "state this now (D30). Remove them") in found
    assert ("repo-infra.json", "problem", "colour: not a key repo-infra reads") in found


def test_empty_version_files_is_a_problem(tmp_path):
    assert config(tmp_path, {})[0][2].startswith("version_files is empty")


def test_refused_release_files_are_reported(tmp_path):
    found = config(tmp_path, {"version_files": VERSIONS,
                              "release_files": ["CHANGES.md", ".github/x", "dist/a"]})
    assert ("release_files", "problem",
            "CHANGES.md is CHANGES.md, which the release pull request rolls; .github/x is "
            "under .github/") in found


def test_gitea_config_is_needed_only_when_the_gitea_piece_is_called(tmp_path):
    docs = {"release-publish.yml": {"jobs": {"gitea": {
        "uses": "./.github/workflows/ri-publish-gitea.yml"}}}}
    base = {"version_files": VERSIONS}
    assert config(tmp_path, base) == []
    found = config(tmp_path, base, docs)
    assert found[0][0] == "gitea_packages" and "url and owner" in found[0][2]


def test_a_required_workflow_with_a_paths_filter_is_a_conflict():
    docs = {"ci.yml": {"on": {"pull_request": {"paths": ["src/**"]}}}}
    assert [(i.name, i.state) for i in check.path_filter_items(docs)] == [("ci.yml", "conflict")]


CONFORMING = Facts(default_branch="main", protected=True,
                   required_contexts={"ci-passed", "changelog-updated"},
                   labels={"no-changelog"}, workflow_permissions="write",
                   can_approve_pr=True, delete_branch_on_merge=True, strict=True)


def test_administration_items_are_their_own_section():
    assert {(i.section, i.state) for i in check.classify_remote(CONFORMING)} == {
        ("administration", "ok")}


def test_run_puts_the_sections_together(tmp_path, store):
    root = tmp_path / "repo"
    install(root, ".github/workflows/ri-x.yml", OLD)
    items = check.run(root, CONFORMING, store)
    assert {i.section for i in items} == {"pieces", "callers", "config", "administration"}
    assert ("pieces", "ri-x", "outdated") in {(i.section, i.name, i.state) for i in items}
    assert ("config", "repo-infra.json", "missing") in {
        (i.section, i.name, i.state) for i in items}
    assert "ri-x.yml" in callers.read_workflows(root)


def test_a_copy_carrying_the_d29_stamp_of_an_old_version_is_outdated(tmp_path, store):
    root = tmp_path / "repo"
    first, rest = OLD.split("\n", 1)
    install(root, ".github/workflows/ri-x.yml", f"{first} sha256={'ab' * 8}\n{rest}")
    assert ("ri-x", "outdated", "v1 installed, v2 available; apply replaces it") in rows(
        root, store)


def test_a_stamped_copy_that_was_edited_afterwards_is_still_edited(tmp_path, store):
    root = tmp_path / "repo"
    first, rest = OLD.split("\n", 1)
    install(root, ".github/workflows/ri-x.yml", f"{first} sha256={'ab' * 8}\n{rest}# mine\n")
    assert [r[1] for r in rows(root, store) if r[0] == "ri-x"] == ["edited"]


def test_check_reads_an_assembled_repository_without_a_traceback(tmp_path, store):
    root = tmp_path / "repo"
    install(root, ".github/workflows/ci.yml", "name: CI\n# repo-infra: ci v2\n"
            "jobs:\n  # repo-infra: ci-rust v3\n  rust-plan:\n    runs-on: x\n")
    items = check.run(root, CONFORMING, store)
    assert [i.name for i in items if i.state == "unknown"] == ["ci"]


def remote(**overrides):
    base = dict(default_branch="main", protected=True,
                required_contexts={"ci-passed", "changelog-updated"},
                labels={"no-changelog"}, workflow_permissions="write", can_approve_pr=True,
                delete_branch_on_merge=True, strict=True)
    base.update(overrides)
    return check.classify_remote(Facts(**base))


def remote_states(items):
    return {i.name: i.state for i in items}


def test_a_conforming_repository_reports_every_remote_item_ok():
    assert set(remote_states(remote()).values()) == {"ok"}


def test_a_master_branch_is_a_conflict_and_is_reported_first():
    items = remote(default_branch="master")
    assert items[0].name == "default-branch"
    assert items[0].state == "conflict"
    assert "main" in items[0].detail


def test_a_missing_required_context_is_missing_not_ok():
    assert remote_states(remote(required_contexts={"ci-passed"}))["required-checks"] == "missing"


def test_a_missing_label_is_reported_because_dependabot_will_not_create_it():
    assert remote_states(remote(labels=set()))["no-changelog-label"] == "missing"


def test_actions_that_cannot_open_a_pull_request_is_missing():
    assert remote_states(remote(can_approve_pr=False))["actions-open-pr"] == "missing"


def test_merged_branches_left_behind_are_missing():
    item = next(i for i in remote(delete_branch_on_merge=False)
                if i.name == "delete-merged-branches")
    assert (item.section, item.state) == ("administration", "missing")
    assert "delete_branch_on_merge" in item.detail


def test_merged_branches_deleted_automatically_are_ok():
    assert remote_states(remote())["delete-merged-branches"] == "ok"


def test_a_ruleset_without_the_up_to_date_rule_is_outdated():
    item = next(i for i in remote(strict=False) if i.name == "required-checks")
    assert item.state == "outdated"
    assert "strict_required_status_checks_policy" in item.detail


def test_missing_contexts_win_over_the_up_to_date_rule():
    items = remote_states(remote(strict=False, required_contexts={"ci-passed"}))
    assert items["required-checks"] == "missing"


def test_a_stamp_on_a_marker_below_a_name_line_is_stripped(tmp_path):
    path = ".github/workflows/changelog.yml"
    old = "name: Changelog\n# repo-infra: changelog v1 do not delete\n#\nbody: 1\n"
    new = old.replace("v1", "v2").replace("1\n", "2\n")
    piece = SimpleNamespace(name="changelog", version=2, files={path: new})
    history = {path: {1: digest(old), 2: digest(new)}}
    line = "# repo-infra: changelog v1 do not delete"
    install(tmp_path, path, old.replace(line, f"{line} sha256=0123456789abcdef"))
    assert check.piece_state(tmp_path, piece, history) == ("outdated", 1, [])


def test_a_directory_piece_with_a_deleted_file_says_which_file(tmp_path, store):
    root = tmp_path / "repo"
    install(root, ".github/workflows/lib-x/a.js", LIB2["a.js"])
    assert ("lib-x", "outdated", ".github/workflows/lib-x/b.js is missing; apply restores it"
            ) in rows(root, store)


@pytest.mark.parametrize("data", [
    {"version_files": "pyproject.toml"},
    {"version_files": [{"pattern": "x"}]},
    {"version_files": ["a"]},
])
def test_malformed_version_files_are_a_problem_not_a_traceback(tmp_path, data):
    found = config(tmp_path, data)
    assert ("repo-infra.json", "problem") not in found
    assert any(n == "version_files" and s == "problem" for n, s, _ in found)


def test_a_string_release_files_is_a_problem_not_a_traceback(tmp_path):
    found = config(tmp_path, {"version_files": VERSIONS, "release_files": "CHANGES.md"})
    assert [(n, s) for n, s, _ in found] == [("release_files", "problem")]


@pytest.mark.parametrize("entry", [
    "CHANGES.md", "./CHANGES.md", "Formula/../CHANGES.md", "Cargo.toml",
    ".github/repo-infra.json", ".github//workflows/ci.yml", "/etc/passwd", "../x", "",
])
def test_a_release_file_that_reopens_the_channel_is_refused(entry):
    refused = check.refused_release_files([entry], [{"path": "Cargo.toml"}])
    assert [path for path, _ in refused] == [entry]


def test_the_formula_is_an_acceptable_release_file():
    assert check.refused_release_files(["Formula/mdmost.rb"], [{"path": "Cargo.toml"}]) == []


GITEA_DOCS = {"release-publish.yml": {"jobs": {"gitea": {
    "uses": "./.github/workflows/ri-publish-gitea.yml"}}}}


def test_gitea_packages_with_its_config_is_fine(tmp_path):
    base = {"version_files": VERSIONS,
            "gitea_packages": {"url": "https://gitea.example.org", "owner": "acme"}}
    assert config(tmp_path, base, GITEA_DOCS) == []


@pytest.mark.parametrize("packages,absent", [
    (None, "url and owner"),
    ({"owner": "acme"}, "url"),
    ({"url": "https://gitea.example.org"}, "owner"),
])
def test_gitea_packages_without_url_or_owner_is_a_problem(tmp_path, packages, absent):
    found = config(tmp_path, {"version_files": VERSIONS, "gitea_packages": packages},
                   GITEA_DOCS)
    assert [(n, s) for n, s, _ in found] == [("gitea_packages", "problem")]
    assert f"lacks {absent};" in found[0][2]


EXCEPTIONS_PROBLEM = ("exceptions", "problem",
                      "exceptions must be an object that maps each rule id of "
                      "references/project-shape.md to a non-empty reason")


def test_exceptions_that_map_rule_ids_to_reasons_are_accepted(tmp_path):
    assert config(tmp_path, {"version_files": VERSIONS,
                             "exceptions": {"homebrew": "a service that needs root"}}) == []


def test_an_empty_exceptions_object_is_accepted(tmp_path):
    assert config(tmp_path, {"version_files": VERSIONS, "exceptions": {}}) == []


@pytest.mark.parametrize("value", [
    [], "homebrew", 1, None, {"homebrew": ""}, {"homebrew": "   "}, {"homebrew": 1},
    {"homebrew": None}, {"homebrew": ["a reason"]},
])
def test_exceptions_that_are_not_an_object_of_reasons_are_a_problem(tmp_path, value):
    found = config(tmp_path, {"version_files": VERSIONS, "exceptions": value})
    assert found == [EXCEPTIONS_PROBLEM]


def test_skip_is_told_to_become_exceptions(tmp_path):
    found = config(tmp_path, {"version_files": VERSIONS, "skip": {"ci-man": True}})
    assert found == [("skip", "problem",
                      "skip is now exceptions (D32): rename the key, and rewrite each of "
                      "its keys as a rule id of references/project-shape.md with the reason "
                      "the rule does not apply")]


def remote_store(tmp_path):
    return make_assets(tmp_path / "assets", {}, core=("ri-r",),
                       remote={"ri-r": workflow_piece("ri-r", 2)})


def test_a_remote_piece_is_not_a_copy_to_compare(tmp_path):
    store = remote_store(tmp_path)
    assert rows(tmp_path / "repo", store) == []


def test_a_core_remote_piece_nobody_calls_is_missing(tmp_path):
    pieces = load_pieces(remote_store(tmp_path))
    (item,) = check.core_call_items({}, pieces)
    assert (item.name, item.state) == ("ri-r", "missing")
    assert "oposs/repo-infra/.github/workflows/ri-r.yml@v2" in item.detail


def test_a_core_remote_piece_that_a_workflow_calls_is_not_reported(tmp_path):
    pieces = load_pieces(remote_store(tmp_path))
    docs = {"ci.yml": {"jobs": {"r": {"uses": "./.github/workflows/ri-r.yml"}}}}
    assert check.core_call_items(docs, pieces) == []


def test_home_is_the_checkout_that_holds_the_manifest(tmp_path):
    assert not check.is_home(tmp_path)
    install(tmp_path, "skills/repo-infra/assets/manifest.json", "{}")
    assert check.is_home(tmp_path)


def test_a_core_remote_piece_called_at_v2_is_not_reported(tmp_path):
    pieces = load_pieces(remote_store(tmp_path))
    docs = {"ci.yml": {"jobs": {"r": {
        "uses": "oposs/repo-infra/.github/workflows/ri-r.yml@v2"}}}}
    assert check.core_call_items(docs, pieces) == []


# --- the v1 layout (D33) ------------------------------------------------------

def test_a_copied_piece_and_the_library_are_the_v1_layout(tmp_path):
    install(tmp_path, ".github/workflows/ri-ci-rust.yml", "# repo-infra: ri-ci-rust v1\n")
    install(tmp_path, ".github/workflows/lib/release.js", "// repo-infra: workflow-lib v9\n")
    install(tmp_path, ".github/workflows/changelog.yml", "name: Changelog\n# repo-infra: changelog v6\n")
    install(tmp_path, ".github/workflows/release-pr.yml", "name: Create release PR\n# repo-infra: release-pr v6\n")
    install(tmp_path, ".github/workflows/ri-ci-lib.yml", "# repo-infra: ri-ci-lib v3\n")
    found = {(i.name, i.state): i.detail for i in layout_items(tmp_path, load_pieces())}
    assert found[("ri-ci-rust", "outdated")] == (
        ".github/workflows/ri-ci-rust.yml is a copy (v1 layout); repositories call "
        "oposs/repo-infra/.github/workflows/ri-ci-rust.yml@v2. Run apply to migrate (D33)")
    assert found[("workflow-lib", "outdated")] == (
        ".github/workflows/lib/ is a copy of the library (v1 layout); the pieces load it "
        "from repo-infra. Run apply to migrate (D33)")
    assert found[("changelog", "outdated")] == (
        ".github/workflows/changelog.yml is the v1 changelog piece; it is a caller now. "
        "Run apply to migrate (D33)")
    assert found[("release-pr", "outdated")] == (
        ".github/workflows/release-pr.yml is the v1 release-pr piece; it is a caller now. "
        "Run apply to migrate (D33)")
    assert found[("ri-ci-lib", "outdated")] == (
        ".github/workflows/ri-ci-lib.yml is the v1 ri-ci-lib piece; repositories no longer "
        "test a library of their own. Run apply to migrate (D33)")
    assert len(found) == 5


def test_a_v2_changelog_caller_is_not_the_v1_layout(tmp_path):
    install(tmp_path, ".github/workflows/changelog.yml",
            (ASSETS / "callers/changelog.yml").read_text(encoding="utf-8"))
    install(tmp_path, ".github/workflows/release-pr.yml",
            (ASSETS / "callers/release-pr.yml").read_text(encoding="utf-8"))
    assert layout_items(tmp_path, load_pieces()) == []


def test_repo_infra_itself_has_no_v1_layout():
    root = pathlib.Path(__file__).resolve().parents[1]
    assert check.is_home(root)
    assert [i for i in check.run(root, CONFORMING) if "v1 layout" in i.detail
            or "v1 " in i.detail] == []


def test_check_reports_the_v1_layout_of_a_consumer(tmp_path):
    install(tmp_path, ".github/workflows/lib/release.js", "// repo-infra: workflow-lib v9\n")
    assert ("pieces", "workflow-lib", "outdated") in {
        (i.section, i.name, i.state) for i in check.run(tmp_path, CONFORMING)}


def test_the_retired_markers_are_not_reported_as_unknown(tmp_path):
    install(tmp_path, ".github/workflows/release-pr.yml",
            "name: Create release PR\n# repo-infra: release-pr v6\n")
    install(tmp_path, ".github/workflows/lib/release.js", "// repo-infra: workflow-lib v9\n")
    install(tmp_path, ".github/workflows/ri-ci-lib.yml", "# repo-infra: ri-ci-lib v3\n")
    assert [i for i in check.unknown_items(tmp_path, load_pieces())] == []


# --- action pins older than the pieces' (#59) ---------------------------------

UPLOAD = "      - uses: actions/upload-artifact@v7\n"


def pin_store(tmp_path):
    return make_assets(tmp_path / "assets", {}, remote={
        "ri-up": workflow_piece("ri-up", 2) + UPLOAD})


def pins(tmp_path, text, name="docs.yml"):
    root = tmp_path / "repo"
    install(root, f".github/workflows/{name}", text)
    items = check.action_pin_items(root, load_pieces(pin_store(tmp_path)))
    return [(i.section, i.name, i.state, i.detail) for i in items]


def steps(*uses):
    return ("name: Docs\non: push\njobs:\n  docs:\n    runs-on: ubuntu-latest\n"
            "    steps:\n" + "".join(f"      - uses: {u}\n" for u in uses))


def test_a_workflow_pinning_an_older_major_than_the_pieces_is_reported(tmp_path):
    assert pins(tmp_path, steps("actions/upload-artifact@v4")) == [(
        "callers", "docs.yml", "outdated",
        "docs.yml pins actions/upload-artifact@v4 and repo-infra's workflows pin v7. "
        "Dependabot moves an action to one version in every workflow, so its update "
        "from v4 can downgrade the files already past it. Pin v7")]


def test_each_action_older_than_the_pieces_is_its_own_row(tmp_path):
    found = pins(tmp_path, steps("actions/checkout@v4.2.1", "actions/upload-artifact@v6",
                                 "actions/upload-artifact@v7"))
    assert [(name, detail.split(" and ")[0]) for _, name, _, detail in found] == [
        ("docs.yml", "docs.yml pins actions/checkout@v4"),
        ("docs.yml", "docs.yml pins actions/upload-artifact@v6")]


@pytest.mark.parametrize("uses", [
    "actions/upload-artifact@v7", "actions/upload-artifact@v8",
    "actions/upload-artifact@v7.1.0", "actions/checkout@v7",
    "actions/upload-artifact@0123456789abcdef0123456789abcdef01234567",
    "actions/upload-artifact@main", "actions/cache@v1",
    "./.github/actions/local", "docker://alpine:3",
    "actions/upload-artifact/.github/workflows/build.yml@v1",
])
def test_a_pin_as_new_as_the_pieces_or_not_a_major_is_not_reported(tmp_path, uses):
    assert pins(tmp_path, steps(uses)) == []


def test_a_commented_out_pin_is_not_reported(tmp_path):
    assert pins(tmp_path, steps("actions/checkout@v7")
                + "      # - uses: actions/upload-artifact@v4\n") == []


def test_a_copy_of_a_piece_is_not_a_repository_owned_workflow(tmp_path):
    copy = workflow_piece("ri-up", 2) + "      - uses: actions/upload-artifact@v4\n"
    assert pins(tmp_path, copy, name="ri-up.yml") == []


def test_check_reports_an_older_pin_than_the_pieces(tmp_path):
    install(tmp_path, ".github/workflows/docs.yml", steps("actions/checkout@v4"))
    assert ("callers", "docs.yml", "outdated") in {
        (i.section, i.name, i.state) for i in check.run(tmp_path, CONFORMING)}


def own_pins(tmp_path, files):
    root = tmp_path / "repo"
    for name, text in files.items():
        install(root, f".github/workflows/{name}", text)
    items = check.action_pin_items(root, load_pieces(pin_store(tmp_path)))
    return [(i.name, i.detail) for i in items]


def test_a_workflow_pinning_an_older_major_than_another_workflow_is_reported(tmp_path):
    assert own_pins(tmp_path, {"docs.yml": steps("actions/cache@v4"),
                               "build.yml": steps("actions/cache@v6")}) == [(
        "docs.yml",
        "docs.yml pins actions/cache@v4 and build.yml pins v6. Dependabot moves an "
        "action to one version in every workflow, so its update from v4 can downgrade "
        "the files already past it. Pin v6")]


def test_workflows_pinning_the_same_major_are_not_reported(tmp_path):
    assert own_pins(tmp_path, {"docs.yml": steps("actions/cache@v6.1"),
                               "build.yml": steps("actions/cache@v6")}) == []


def test_a_workflow_newer_than_the_pieces_raises_the_floor_for_the_others(tmp_path):
    found = own_pins(tmp_path, {"docs.yml": steps("actions/upload-artifact@v7"),
                                "build.yml": steps("actions/upload-artifact@v8")})
    assert [(name, detail.split(". ")[0]) for name, detail in found] == [
        ("docs.yml", "docs.yml pins actions/upload-artifact@v7 and build.yml pins v8")]


def test_a_sha_pin_does_not_raise_the_floor(tmp_path):
    assert own_pins(tmp_path, {
        "docs.yml": steps("actions/cache@v4"),
        "build.yml": steps("actions/cache@0123456789abcdef0123456789abcdef01234567")}) == []
