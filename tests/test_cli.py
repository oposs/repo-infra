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


# --- what the user sees on a failure, before and after the network -----------

def test_a_gh_failure_is_a_message_not_a_traceback(monkeypatch, tmp_path, capsys):
    from repo_infra.remote import GhError

    def fail(repo):
        raise GhError("gh api repos/o/r failed: HTTP 401: Bad credentials")
    monkeypatch.setattr(cli, "read_facts", fail)
    assert cli.main(["check", "--root", str(tmp_path), "--repo", "o/r"]) == 1
    out, err = capsys.readouterr()
    assert err == "gh: gh api repos/o/r failed: HTTP 401: Bad credentials\n"
    assert "Traceback" not in out + err


def test_a_broken_asset_store_is_a_message_not_a_traceback(monkeypatch, tmp_path, capsys):
    store = make_assets(tmp_path / "assets", {"ri-x": workflow_piece("ri-x", 1)})
    (store / "pieces/ri-x/ri-x.yml").unlink()
    monkeypatch.setattr(cli, "ASSETS", store)
    monkeypatch.setattr(cli, "read_facts", lambda repo: cli.CONFORMING_FACTS)
    assert cli.main(["check", "--root", str(tmp_path), "--repo", "o/r"]) == 1
    err = capsys.readouterr().err
    assert err == ("the plugin's asset store is broken (reinstall the plugin): ri-x: "
                   "pieces/ri-x/ri-x.yml is missing from the asset store\n")


@pytest.mark.parametrize("args, said", [
    (["--from", "m.js"], "--from needs --item: name the piece the merged file is for"),
    (["--item", "no-changelog-label", "--from", "m.js"],
     "--from takes the merged file of a piece, not of the administration item "
     "no-changelog-label"),
    (["--item", "nothing-like-it"], "nothing-like-it: not a piece and not an administration "
                                    "item"),
])
def test_apply_refuses_bad_arguments_before_asking_github(monkeypatch, tmp_path, capsys,
                                                          args, said):
    """read_facts (and gh repo view) ran first, so a typo waited for the
    network, or failed on it, before the refusal."""
    store = make_assets(tmp_path / "assets", {"ri-x": workflow_piece("ri-x", 1)})
    monkeypatch.setattr(cli, "ASSETS", store)

    def no_network(*_):
        raise AssertionError("asked GitHub before checking the arguments")
    monkeypatch.setattr(cli, "read_facts", no_network)
    monkeypatch.setattr(cli, "Gh", no_network)
    assert cli.main(["apply", "--root", str(tmp_path), *args]) == 1
    assert capsys.readouterr().err == f"refused: {said}\n"
