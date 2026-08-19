import json
import pathlib

from repo_infra import cli

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
