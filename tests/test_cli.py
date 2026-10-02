import pytest
from piecekit import install, make_assets, workflow_piece

from repo_infra import cli


def test_help_lists_check_and_apply(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    assert "check" in out and "apply" in out


def test_check_exits_1_when_something_needs_attention(monkeypatch, tmp_path, capsys):
    store = make_assets(tmp_path / "assets", {"ri-x": workflow_piece("ri-x", 1)})
    monkeypatch.setattr(cli, "ASSETS", store)
    monkeypatch.setattr(cli, "read_facts", lambda repo: cli.CONFORMING_FACTS)
    install(tmp_path / "repo", ".github/workflows/ri-x.yml", workflow_piece("ri-x", 1) + "#\n")
    assert cli.main(["check", "--root", str(tmp_path / "repo"), "--repo", "o/r"]) == 1
    assert "edited" in capsys.readouterr().out


def test_check_json(monkeypatch, tmp_path, capsys):
    store = make_assets(tmp_path / "assets", {"ri-x": workflow_piece("ri-x", 1)})
    monkeypatch.setattr(cli, "ASSETS", store)
    monkeypatch.setattr(cli, "read_facts", lambda repo: cli.CONFORMING_FACTS)
    cli.main(["check", "--json", "--root", str(tmp_path), "--repo", "o/r"])
    assert '"section": "callers"' in capsys.readouterr().out
