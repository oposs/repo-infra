import json
from types import SimpleNamespace

import pytest
from piecekit import digest, install, lib_file, make_assets, workflow_piece

from repo_infra import callers, check
from repo_infra.pieces import load_pieces, load_published
from repo_infra.remote import Facts

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
    install(root, ".github/workflows/ri-x.yml", NEW + "# mine\n")
    (name, state, detail), = [r for r in rows(root, store) if r[0] == "ri-x"]
    assert state == "edited"
    assert detail.startswith(".github/workflows/ri-x.yml matches no published version")


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
                   can_approve_pr=True, strict=True)


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
                strict=True)
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
