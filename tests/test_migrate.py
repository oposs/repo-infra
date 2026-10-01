"""D28 migration: what check reports and what apply moves."""

import json
import pathlib
import subprocess

import pytest

from repo_infra import cli
from repo_infra.apply import ApplyError
from repo_infra.migrate import release_in_progress
from repo_infra.remote import Facts

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
D26_BUILD = ("name: Release build\non:\n  workflow_call:\n    inputs:\n      version:\n"
             "        type: string\n      ref:\n        type: string\njobs:\n  b:\n"
             "    runs-on: x\n    timeout-minutes: 5\n    steps:\n"
             "      - uses: actions/checkout@v7\n        with:\n          ref: ${{ inputs.ref }}\n")
CHANGES = "# Changes\n\n## [Unreleased]\n\n## 0.6.0 - 2026-09-30\n\n- x\n"


def facts(**over):
    base = dict(cli.CONFORMING_FACTS._asdict())
    base.update(tags=frozenset({"v0.6.0"}))
    base.update(over)
    return Facts(**base)


def repo(tmp_path, config, files=None):
    root = tmp_path / "repo"
    (root / ".github/workflows").mkdir(parents=True)
    (root / ".github/repo-infra.json").write_text(json.dumps(config, indent=2) + "\n")
    (root / "CHANGES.md").write_text(CHANGES)
    for path, text in (files or {}).items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    for args in (("init", "-q", "-b", "main"), ("add", "-A"),
                 ("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "seed")):
        subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True)
    return root


def migrations(root):
    return {i.name: i.state for i in cli._prepare(root)[4]}


def test_the_d26_build_is_renamed_not_reported_as_unmanaged(tmp_path):
    root = repo(tmp_path, {"release_build": True, "version_files": []},
                {".github/workflows/release-build.yml": D26_BUILD})
    assert migrations(root) == {"release-build-rename": "outdated",
                                "release-build-config": "outdated"}
    config = cli._prepare(root)[3]
    assert config["release_build"] == [] and config["release_build_local"] is True


def test_boolean_release_build_without_a_d26_file_only_becomes_a_list(tmp_path):
    root = repo(tmp_path, {"release_build": False, "version_files": []})
    assert migrations(root) == {"release-build-config": "outdated"}


def test_the_source_tarball_moves_to_the_build(tmp_path):
    root = repo(tmp_path, {"publish": ["publish-source-tarball", "publish-crates-io"],
                           "version_files": []})
    assert migrations(root) == {"publish-source-tarball": "outdated",
                                "release-assets": "conflict"}
    config = cli._prepare(root)[3]
    assert config["publish"] == ["publish-crates-io"]
    assert config["release_build"] == ["release-source-tarball"]
    assert config["release_assets"] == ["*.tar.gz"]


def test_an_add_on_pattern_missing_from_release_assets_is_a_conflict(tmp_path):
    root = repo(tmp_path, {"release_build": ["release-source-tarball"],
                           "release_assets": ["x-*.zip"], "version_files": []})
    assert migrations(root) == {"release-assets": "conflict"}
    assert cli._prepare(root)[3]["release_assets"] == ["x-*.zip", "*.tar.gz"]


def test_missing_cargo_lock_entries_are_reported_and_added(tmp_path):
    root = repo(tmp_path, {"version_files": [{"path": "Cargo.toml", "pattern": "^version",
                                              "replacement": "x", "verify": "x"}]},
                {"Cargo.toml": '[package]\nname = "app"\nversion = "0.6.0"\n',
                 "Cargo.lock": '[[package]]\nname = "app"\nversion = "0.6.0"\n'})
    assert migrations(root) == {"cargo-lock-version-files": "missing"}
    lock = [e for e in cli._prepare(root)[3]["version_files"] if e["path"] == "Cargo.lock"]
    assert [e["pattern"] for e in lock] == ['^name = "app"\nversion = "[^"]*"']


def test_present_cargo_lock_entries_are_left_alone(tmp_path):
    entry = {"path": "Cargo.lock", "pattern": '^name = "app"\nversion = "[^"]*"',
             "replacement": 'name = "app"\nversion = "$VERSION"',
             "verify": '^name = "app"\nversion = "$VERSION"'}
    root = repo(tmp_path, {"version_files": [entry]},
                {"Cargo.toml": '[package]\nname = "app"\nversion = "0.6.0"\n',
                 "Cargo.lock": '[[package]]\nname = "app"\nversion = "0.6.0"\n'})
    assert migrations(root) == {}


def test_a_current_config_needs_no_migration(tmp_path):
    root = repo(tmp_path, {"release_build": [], "version_files": []})
    assert migrations(root) == {}


def test_an_open_release_pull_request_is_a_release_in_progress(tmp_path):
    root = repo(tmp_path, {"version_files": []})
    item = release_in_progress(root, facts(release_prs=((12, "release/v0.6.1"),)))
    assert (item.name, item.state) == ("release-in-progress", "conflict")
    assert "#12" in item.detail and "release/v0.6.1" in item.detail


def test_an_untagged_latest_release_is_a_release_in_progress(tmp_path):
    root = repo(tmp_path, {"version_files": []})
    item = release_in_progress(root, facts(tags=frozenset({"v0.5.0"})))
    assert "v0.6.0 is in CHANGES.md but has no tag" in item.detail


def test_unknown_tags_are_not_a_refusal(tmp_path):
    root = repo(tmp_path, {"version_files": []})
    assert release_in_progress(root, facts(tags=None)) is None


def run_check(root, monkeypatch, capsys, the_facts):
    monkeypatch.setattr(cli, "read_facts", lambda repo: the_facts)
    code = cli.main(["check", "--repo", "o/r", "--root", str(root), "--json"])
    return code, {i["name"]: i for i in json.loads(capsys.readouterr().out)["items"]}


def test_check_reports_migrations_and_the_refusal(tmp_path, monkeypatch, capsys):
    root = repo(tmp_path, {"release_build": True, "version_files": []},
                {".github/workflows/release-build.yml": D26_BUILD})
    code, items = run_check(root, monkeypatch, capsys,
                            facts(release_prs=((12, "release/v0.6.1"),)))
    assert code == 1
    assert items["release-build-rename"]["state"] == "outdated"
    assert items["release-in-progress"]["state"] == "conflict"
    # The D26 file is not reported as unmanaged while its rename is pending.
    assert items.get("release-build", {}).get("state") != "conflict"


def test_the_d26_build_is_named_by_one_item_only(tmp_path, monkeypatch, capsys):
    # The assembled release-build.yml carries two markers, release-build and
    # release-build-local-job; neither may read as an unmanaged file, so the
    # rename is the one item that names the D26 file.
    root = repo(tmp_path, {"release_build": True, "version_files": []},
                {".github/workflows/release-build.yml": D26_BUILD})
    _code, items = run_check(root, monkeypatch, capsys, facts())
    assert [n for n, i in items.items() if i["state"] == "conflict"] == []
    assert [n for n, i in items.items()
            if ".github/workflows/release-build.yml" in i["detail"]] == ["release-build-rename"]


def test_check_says_nothing_about_a_release_when_nothing_migrates(tmp_path, monkeypatch, capsys):
    root = ROOT  # repo-infra itself is current
    code, items = run_check(root, monkeypatch, capsys,
                            facts(release_prs=((12, "release/v0.6.1"),)))
    assert "release-in-progress" not in items


def test_apply_refuses_while_a_release_is_in_progress(tmp_path, monkeypatch):
    root = repo(tmp_path, {"release_build": True, "version_files": []},
                {".github/workflows/release-build.yml": D26_BUILD})
    monkeypatch.setattr(cli, "read_facts",
                        lambda repo: facts(release_prs=((12, "release/v0.6.1"),)))
    with pytest.raises(ApplyError, match="release-in-progress"):
        cli.main(["apply", "--repo", "o/r", "--root", str(root),
                  "--item", "release-build-rename"])
    head = subprocess.run(["git", "log", "--oneline"], cwd=root, capture_output=True,
                          text=True).stdout
    assert head.count("\n") == 1  # nothing committed


def git(root, *args):
    return subprocess.run(("git",) + args, cwd=root, capture_output=True, text=True).stdout


def test_apply_item_refuses_another_item_while_a_migration_is_pending(tmp_path, monkeypatch):
    root = repo(tmp_path, {"publish": ["publish-source-tarball"], "version_files": []})
    monkeypatch.setattr(cli, "read_facts", lambda repo: facts())
    with pytest.raises(ApplyError, match="publish-source-tarball, release-assets"):
        cli.main(["apply", "--repo", "o/r", "--root", str(root), "--item", "release-publish"])
    assert git(root, "branch", "--format=%(refname:short)") == "main\n"
    assert git(root, "status", "--porcelain") == ""
    assert git(root, "log", "--oneline").count("\n") == 1


def test_apply_item_runs_once_nothing_migrates(tmp_path, monkeypatch):
    root = repo(tmp_path, {"release_build": [], "version_files": []})
    monkeypatch.setattr(cli, "read_facts", lambda repo: facts())
    cli.main(["apply", "--repo", "o/r", "--root", str(root), "--item", "release-publish"])
    assert git(root, "log", "-1", "--format=%s") == \
        "Install release-publish from the repo-infra standard\n"


def test_any_migration_item_applies_the_whole_migration(tmp_path, monkeypatch):
    root = repo(tmp_path, {"publish": ["publish-source-tarball"], "version_files": []})
    monkeypatch.setattr(cli, "read_facts", lambda repo: facts())
    cli.main(["apply", "--repo", "o/r", "--root", str(root), "--item", "release-assets"])
    config = json.loads((root / ".github/repo-infra.json").read_text())
    assert config["publish"] == [] and config["release_build"] == ["release-source-tarball"]
    assert config["release_assets"] == ["*.tar.gz"]
    assert migrations(root) == {}


def test_apply_renames_the_d26_build_unchanged_and_rewrites_the_config(tmp_path, monkeypatch):
    root = repo(tmp_path, {"release_build": True, "version_files": []},
                {".github/workflows/release-build.yml": D26_BUILD})
    monkeypatch.setattr(cli, "read_facts", lambda repo: facts())
    cli.main(["apply", "--repo", "o/r", "--root", str(root), "--item", "release-build-rename"])
    status = subprocess.run(["git", "show", "--name-status", "-M", "--format=", "HEAD"],
                            cwd=root, capture_output=True, text=True).stdout.splitlines()
    assert ("R100\t.github/workflows/release-build.yml\t"
            ".github/workflows/release-build-local.yml") in status
    assert "M\t.github/repo-infra.json" in status
    config = json.loads((root / ".github/repo-infra.json").read_text())
    assert config["release_build"] == [] and config["release_build_local"] is True
    assert (root / ".github/workflows/release-build-local.yml").read_text() == D26_BUILD


def test_the_assembled_build_is_installed_after_the_rename(tmp_path, monkeypatch):
    root = repo(tmp_path, {"release_build": True, "version_files": []},
                {".github/workflows/release-build.yml": D26_BUILD})
    monkeypatch.setattr(cli, "read_facts", lambda repo: facts())
    cli.main(["apply", "--repo", "o/r", "--root", str(root), "--item", "release-build-rename"])
    cli.main(["apply", "--repo", "o/r", "--root", str(root), "--item", "release-build"])
    text = (root / ".github/workflows/release-build.yml").read_text()
    assert "# repo-infra: release-build v1" in text
    assert "uses: ./.github/workflows/release-build-local.yml" in text
