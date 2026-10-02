import json
import pathlib

import pytest

from repo_infra import cli
from repo_infra.markers import strip_stamp
from repo_infra.state import Item

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_check_on_this_repository_reports_every_file_item_ok(capsys, monkeypatch):
    """The plugin's own repository is, by construction, fully converted."""
    monkeypatch.setattr(cli, "read_facts", lambda repo: cli.CONFORMING_FACTS)
    assert cli.main(["check", "--repo", "oposs/repo-infra", "--root", str(ROOT), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert [i for i in data["items"] if i["state"] != "ok"] == []


def test_check_exits_nonzero_when_something_needs_attention(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "read_facts", lambda repo: cli.CONFORMING_FACTS)
    assert cli.main(["check", "--repo", "x/y", "--root", str(tmp_path)]) == 1
    assert "missing" in capsys.readouterr().out


def test_check_reports_an_unresolved_ambiguity_and_exits_nonzero(capsys, monkeypatch):
    """tests/fixtures/repo-node-ambiguous triggers node lockfile ambiguities;
    `check` must not report it clean just because every file item is ok."""
    monkeypatch.setattr(cli, "read_facts", lambda repo: cli.CONFORMING_FACTS)
    root = ROOT / "tests/fixtures/repo-node-ambiguous"
    assert cli.main(["check", "--repo", "x/y", "--root", str(root), "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    ambiguous = [i for i in data["items"] if i["state"] == "ambiguous"]
    assert sorted([i["name"] for i in ambiguous]) == sorted(
        ["node-bun-vs-npm", "node-lockfiles", "node-pnpm-vs-bun"]
    )


def missing(*names):
    return [Item(n, "missing", "") for n in names]


def test_ordered_names_runs_files_before_the_label_before_permissions_before_the_ruleset():
    items = missing("required-checks", "actions-open-pr", "no-changelog-label",
                    "branch-protection", "ci", "dependabot")
    assert cli._ordered_names(items) == [
        "ci", "dependabot", "no-changelog-label", "actions-open-pr", "required-checks"]


def test_ordered_names_never_includes_default_branch():
    """default-branch is never `missing`/`outdated` (state.py reports it as
    `conflict`), but even if it somehow were, it must never be auto-applied."""
    items = [Item("default-branch", "missing", "")]
    assert "default-branch" not in cli._ordered_names(items)


def test_ordered_names_asks_for_the_ruleset_once_when_both_facts_are_missing():
    """branch-protection and required-checks are two facts about the one
    ruleset; on a fresh repository both come back missing at once, and
    applying either would enable it -- so the default run must not ask for
    the ruleset twice."""
    items = missing("branch-protection", "required-checks")
    names = cli._ordered_names(items)
    assert names.count("required-checks") == 1
    assert "branch-protection" not in names


def test_a_chosen_build_add_on_is_no_longer_a_candidate(tmp_path):
    for name in ("configure.ac", "cpanfile"):
        (tmp_path / name).write_text("")
    assert "release-source-tarball" in cli._prepare(tmp_path)[1].candidates
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github/repo-infra.json").write_text(
        json.dumps({"release_build": ["release-source-tarball"]}))
    assert "release-source-tarball" not in cli._prepare(tmp_path)[1].candidates
    # Also when the migration moves the setting there.
    (tmp_path / ".github/repo-infra.json").write_text(
        json.dumps({"publish": ["publish-source-tarball"]}))
    assert "release-source-tarball" not in cli._prepare(tmp_path)[1].candidates


# --- apply re-reads each file item before it acts (C5) -----------------------
#
# `fx` writes a.yml whole, which carries `by` as well; `by` also ships b.yml.
# Its files only partly overlap what `fx` wrote.
A = "# repo-infra: fx v2\n# repo-infra: by v2\na\n"
B = "# repo-infra: by v2\nb\n"


def overlapping(tmp_path, monkeypatch, files):
    import subprocess

    root = tmp_path / "repo"
    root.mkdir()
    for path, text in files.items():
        (root / path).write_text(text)
    (root / "seed").write_text("x\n")
    for args in (("init", "-q", "-b", "main"), ("add", "-A"),
                 ("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "seed")):
        subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True)
    rendered = {"a.yml": A, "b.yml": B}
    monkeypatch.setattr(cli, "_prepare", lambda r: ({}, None, rendered, {}, []))
    monkeypatch.setattr(cli, "read_facts", lambda repo: cli.CONFORMING_FACTS)
    monkeypatch.setattr(cli.migrate, "release_in_progress", lambda r, f: None)
    return root


def log(root):
    import subprocess

    return subprocess.run(["git", "log", "--format=%s", "--name-only"], cwd=root,
                          capture_output=True, text=True, check=True).stdout


def test_an_item_whose_other_files_are_current_makes_no_commit(tmp_path, monkeypatch, capsys):
    root = overlapping(tmp_path, monkeypatch, {"b.yml": B})
    assert cli.main(["apply", "--repo", "o/r", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "applied fx" in out and "by: installed with fx" in out
    assert "applied by" not in out
    assert log(root).count("Install ") == 1


def test_an_item_writes_only_the_files_an_earlier_item_left(tmp_path, monkeypatch, capsys):
    root = overlapping(tmp_path, monkeypatch, {})
    assert cli.main(["apply", "--repo", "o/r", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert out.count("applied by") == 1
    assert "Install by from the repo-infra standard\n\nb.yml\n" in log(root)
    assert strip_stamp((root / "b.yml").read_text()) == B


def test_a_hand_merge_handed_back_with_from_commits_as_a_merge(tmp_path, monkeypatch):
    import subprocess

    from repo_infra.apply import NeedsMerge

    root = overlapping(tmp_path, monkeypatch, {"a.yml": "# repo-infra: fx v1\nlocal\n"})
    argv = ["apply", "--repo", "o/r", "--root", str(root), "--item", "fx"]
    with pytest.raises(NeedsMerge) as raised:
        cli.main(argv)
    assert cli.main(argv + ["--from", str(raised.value.new)]) == 0
    subject = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=root,
                             capture_output=True, text=True, check=True).stdout.strip()
    assert subject == "Merge fx from the repo-infra standard with local edits"
