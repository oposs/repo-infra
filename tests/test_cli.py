import json
import pathlib

from repo_infra import cli
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
    """tests/fixtures/repo-node-ambiguous triggers the node-lockfiles ambiguity;
    `check` must not report it clean just because every file item is ok."""
    monkeypatch.setattr(cli, "read_facts", lambda repo: cli.CONFORMING_FACTS)
    root = ROOT / "tests/fixtures/repo-node-ambiguous"
    assert cli.main(["check", "--repo", "x/y", "--root", str(root), "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    ambiguous = [i for i in data["items"] if i["state"] == "ambiguous"]
    assert [i["name"] for i in ambiguous] == ["node-lockfiles"]


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
