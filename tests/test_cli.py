import pathlib
import shutil
import subprocess

import pytest
from piecekit import install, make_assets, workflow_piece

from repo_infra import check as checking
from repo_infra import cli
from repo_infra.pieces import ASSETS, load_pieces


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
    (["--item", "delete-merged-branches", "--from", "m.js"],
     "--from takes the merged file of a piece, not of the administration item "
     "delete-merged-branches"),
    (["--item", "classic-protection", "--from", "m.js"],
     "--from takes the merged file of a piece, not of the administration item "
     "classic-protection"),
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


# --- D33: pieces are called, and a v1 repository is migrated -----------------

V1_MTUSPY = pathlib.Path(__file__).resolve().parent / "fixtures/v1/mtuspy"


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True,
                          text=True).stdout


def test_apply_migrates_a_v1_repository_in_one_commit(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    shutil.copytree(V1_MTUSPY, repo)
    pieces = load_pieces()
    # The byte pieces as published, so the migration is all apply has to do.
    for piece in pieces.values():
        if not piece.remote:
            for path, text in piece.files.items():
                install(repo, path, text)
    (repo / "CHANGES.md").write_text("# Changes\n\n## [Unreleased]\n\n"
                                     "## 0.3.0 - 2026-09-30\n\n- x\n", encoding="utf-8")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "v1")
    facts = cli.CONFORMING_FACTS._replace(release_prs=(), tags=frozenset({"v0.3.0"}))
    monkeypatch.setattr(cli, "read_facts", lambda repo_name: facts)

    assert cli.main(["apply", "--root", str(repo), "--repo", "o/r"]) == 0
    assert git(repo, "log", "--format=%s", "main..HEAD").splitlines() == [
        "Migrate to the repo-infra v2 layout"]
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip() == "repo-infra/apply"
    assert git(repo, "status", "--porcelain") == ""
    left = sorted(p.name for p in (repo / ".github/workflows").iterdir())
    assert left == ["changelog.yml", "ci.yml", "release-build.yml", "release-pr.yml",
                    "release-publish.yml"]
    for name in ("changelog.yml", "release-pr.yml"):
        assert (repo / ".github/workflows" / name).read_text(encoding="utf-8") == (
            ASSETS / "callers" / name).read_text(encoding="utf-8")
    assert checking.layout_items(repo, pieces) == []
    out = capsys.readouterr().out
    assert "migrated to the v2 layout: " in out
    assert "local changes" not in out
    assert "local changes" not in git(repo, "log", "-1", "--format=%b")
    # The removals are in the commit, not left in the work tree.
    removed = git(repo, "show", "--name-status", "--format=", "HEAD").splitlines()
    assert "D\t.github/workflows/lib/release.js" in removed
    assert "D\t.github/workflows/ri-ci-rust.yml" in removed

    # A second apply finds nothing to migrate.
    assert cli.main(["apply", "--root", str(repo), "--repo", "o/r"]) == 0
    assert len(git(repo, "log", "--format=%s", "main..HEAD").splitlines()) == 1


def test_apply_names_the_local_changes_the_migration_removes(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    shutil.copytree(V1_MTUSPY, repo)
    flows = repo / ".github/workflows"
    rust = flows / "ri-ci-rust.yml"
    rust.write_text(rust.read_text(encoding="utf-8") + "# a local fix\n", encoding="utf-8")
    (flows / "lib/mine.js").write_text("module.exports = {};\n", encoding="utf-8")
    pr = flows / "release-pr.yml"
    pr.write_text(pr.read_text(encoding="utf-8")
                  + "  notify:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo\n",
                  encoding="utf-8")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "v1")
    monkeypatch.setattr(cli, "read_facts", lambda repo_name: cli.CONFORMING_FACTS)
    assert cli.main(["apply", "--root", str(repo), "--repo", "o/r"]) == 0
    out = capsys.readouterr().out
    body = git(repo, "log", "--format=%b", "-1", "--grep", "Migrate to the repo-infra v2")
    for said in (".github/workflows/ri-ci-rust.yml: edited locally",
                 ".github/workflows/lib/mine.js: not shipped by repo-infra",
                 ".github/workflows/release-pr.yml: edited locally",
                 ".github/workflows/release-pr.yml: the v2 caller drops its job notify"):
        assert said in out
        assert said in body


def test_a_release_in_progress_stops_the_migration(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    shutil.copytree(V1_MTUSPY, repo)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "v1")
    facts = cli.CONFORMING_FACTS._replace(release_prs=((7, "release/v0.3.1"),))
    monkeypatch.setattr(cli, "read_facts", lambda repo_name: facts)
    assert cli.main(["apply", "--root", str(repo), "--repo", "o/r"]) == 1
    assert capsys.readouterr().err.startswith("refused: release-in-progress: ")
    assert git(repo, "log", "--format=%s").splitlines() == ["v1"]
    assert git(repo, "status", "--porcelain") == ""


def test_apply_item_refuses_a_remote_piece(tmp_path, monkeypatch, capsys):
    def no_network(*_):
        raise AssertionError("asked GitHub before checking the arguments")
    monkeypatch.setattr(cli, "read_facts", no_network)
    monkeypatch.setattr(cli, "Gh", no_network)
    code = cli.main(["apply", "--root", str(tmp_path), "--repo", "o/r", "--item", "ri-ci-rust"])
    assert code == 1
    assert capsys.readouterr().err == (
        "refused: ri-ci-rust is called, not installed (D33): add its Call: from the "
        "catalogue to a caller, as `uses: oposs/repo-infra/.github/workflows/"
        "ri-ci-rust.yml@v2`\n")
