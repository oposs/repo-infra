# tests/test_apply_pieces.py
import subprocess

import pytest
from piecekit import install, lib_file, make_assets, workflow_piece

from repo_infra import apply, check, cli
from repo_infra.pieces import load_pieces, load_published

OLD = workflow_piece("ri-x", 1, body="old")
NEW_INPUT = ("      target:\n        description: The make target.\n"
             "        type: string\n        required: true\n")
NEW = workflow_piece("ri-x", 2, body="new", inputs=NEW_INPUT)
LIB1 = {"a.js": lib_file("lib-x", 1, "a1"), "gone.js": lib_file("lib-x", 1, "g1")}
LIB2 = {"a.js": lib_file("lib-x", 2, "a2")}


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True,
                          text=True).stdout


@pytest.fixture
def store(tmp_path):
    history = [("ri-x", None, OLD)] + [("lib-x", f, t) for f, t in LIB1.items()]
    return make_assets(tmp_path / "assets", {"ri-x": NEW, "lib-x": LIB2}, history,
                       core=("lib-x",))


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    install(root, ".github/workflows/ri-x.yml", OLD)
    for f, t in LIB1.items():
        install(root, f".github/workflows/lib-x/{f}", t)
    install(root, ".github/workflows/ci.yml",
            "on:\n  push:\npermissions:\n  contents: read\njobs:\n  x:\n"
            "    uses: ./.github/workflows/ri-x.yml\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "start")
    return root


def run_apply(monkeypatch, store, repo, *extra):
    monkeypatch.setattr(cli, "ASSETS", store)
    monkeypatch.setattr(cli, "read_facts", lambda repo_name: cli.CONFORMING_FACTS)
    return cli.main(["apply", "--root", str(repo), "--repo", "o/r", *extra])


def test_apply_replaces_outdated_pieces_one_commit_each(monkeypatch, capsys, store, repo):
    assert run_apply(monkeypatch, store, repo) == 0
    log = git(repo, "log", "--format=%s").splitlines()
    assert log[:2] == ["Install ri-x v2 from the repo-infra standard",
                       "Install lib-x v2 from the repo-infra standard"]
    assert (repo / ".github/workflows/ri-x.yml").read_text(encoding="utf-8") == NEW
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip() == "repo-infra/apply"


def test_apply_removes_a_file_the_new_version_no_longer_ships(monkeypatch, store, repo):
    run_apply(monkeypatch, store, repo)
    assert not (repo / ".github/workflows/lib-x/gone.js").exists()


def test_apply_prints_the_notes_and_the_new_caller_finding(monkeypatch, capsys, store, repo):
    run_apply(monkeypatch, store, repo)
    out = capsys.readouterr().out
    assert "ri-x v2\nNotes for ri-x v2." in out
    assert "ci.yml: job x calls ri-x.yml without its required input target" in out
    assert "then run check until it exits 0" in out


def test_apply_installs_a_piece_that_is_not_there(monkeypatch, store, repo):
    (repo / ".github/workflows/ri-x.yml").unlink()
    git(repo, "commit", "-qam", "drop")
    run_apply(monkeypatch, store, repo, "--item", "ri-x")
    assert git(repo, "log", "-1", "--format=%s").strip() == (
        "Install ri-x v2 from the repo-infra standard")


def test_an_edited_piece_stops_with_the_merge_files(monkeypatch, store, repo):
    install(repo, ".github/workflows/ri-x.yml", OLD + "# mine\n")
    git(repo, "commit", "-qam", "edit")
    with pytest.raises(apply.NeedsMerge) as stopped:
        run_apply(monkeypatch, store, repo, "--item", "ri-x")
    assert stopped.value.new.read_text(encoding="utf-8") == NEW
    merged = repo.parent / "merged.yml"
    merged.write_text(NEW, encoding="utf-8")
    run_apply(monkeypatch, store, repo, "--item", "ri-x", "--from", str(merged))
    assert git(repo, "log", "-1", "--format=%s").strip() == (
        "Install ri-x v2 from the repo-infra standard")


def test_a_hand_back_with_local_edits_is_committed_as_a_merge(monkeypatch, store, repo):
    install(repo, ".github/workflows/ri-x.yml", OLD + "# mine\n")
    git(repo, "commit", "-qam", "edit")
    with pytest.raises(apply.NeedsMerge):
        run_apply(monkeypatch, store, repo, "--item", "ri-x")
    merged = repo.parent / "merged.yml"
    merged.write_text(NEW + "# mine\n", encoding="utf-8")
    run_apply(monkeypatch, store, repo, "--item", "ri-x", "--from", str(merged))
    assert git(repo, "log", "-1", "--format=%s").strip() == (
        "Merge ri-x v2 from the repo-infra standard with local edits")


def test_a_release_in_progress_stops_apply(monkeypatch, store, repo):
    monkeypatch.setattr(cli, "release_in_progress", lambda root, facts: "pull request #3 is open")
    with pytest.raises(apply.ApplyError, match="release-in-progress: pull request #3"):
        run_apply(monkeypatch, store, repo)


def test_an_unknown_item_is_refused(monkeypatch, store, repo):
    with pytest.raises(apply.ApplyError, match="ri-zz: not a piece"):
        run_apply(monkeypatch, store, repo, "--item", "ri-zz")


def test_state_after_apply_is_current(monkeypatch, store, repo):
    run_apply(monkeypatch, store, repo)
    pieces, published = load_pieces(store), load_published(store)
    assert {n: check.piece_state(repo, p, published[n]).state for n, p in pieces.items()} == {
        "ri-x": "current", "lib-x": "current"}


def test_an_edited_file_the_new_version_dropped_stays_and_is_named(
        monkeypatch, capsys, store, repo):
    install(repo, ".github/workflows/lib-x/gone.js", LIB1["gone.js"] + "// mine\n")
    git(repo, "commit", "-qam", "edit")
    run_apply(monkeypatch, store, repo, "--item", "lib-x")
    assert "// mine" in (repo / ".github/workflows/lib-x/gone.js").read_text(encoding="utf-8")
    assert git(repo, "log", "-1", "--format=%s").strip() == (
        "Install lib-x v2 from the repo-infra standard")
    assert (".github/workflows/lib-x/gone.js: carries local edits and lib-x v2 no longer "
            "ships it") in capsys.readouterr().out


def test_the_merge_targets_the_edited_file_the_new_version_ships(monkeypatch, store, repo):
    install(repo, ".github/workflows/lib-x/gone.js", LIB1["gone.js"] + "// mine\n")
    install(repo, ".github/workflows/lib-x/a.js", LIB1["a.js"] + "// mine\n")
    git(repo, "commit", "-qam", "edit")
    with pytest.raises(apply.NeedsMerge) as stopped:
        run_apply(monkeypatch, store, repo, "--item", "lib-x")
    assert stopped.value.target.name == "a.js"
