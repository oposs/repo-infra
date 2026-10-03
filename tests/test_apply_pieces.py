# tests/test_apply_pieces.py
import subprocess

import pytest
from piecekit import install, lib_file, make_assets, workflow_piece

from repo_infra import apply, check, cli
from repo_infra.pieces import load_pieces, load_published
from repo_infra.remote import Facts

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


# --- fix round 1 ------------------------------------------------------------


def log_subjects(repo):
    return git(repo, "log", "--format=%s").splitlines()


def test_a_stamped_dropped_file_is_removed(monkeypatch, store, repo):
    stamped = LIB1["gone.js"].replace("lib-x v1\n", "lib-x v1 sha256=" + "ab" * 32 + "\n", 1)
    install(repo, ".github/workflows/lib-x/gone.js", stamped)
    git(repo, "commit", "-qam", "stamp")
    run_apply(monkeypatch, store, repo, "--item", "lib-x")
    assert not (repo / ".github/workflows/lib-x/gone.js").exists()


def test_apply_commits_only_the_pieces_own_paths(monkeypatch, store, repo):
    (repo / "mine.txt").write_text("staged\n", encoding="utf-8")
    git(repo, "add", "mine.txt")
    run_apply(monkeypatch, store, repo, "--item", "ri-x")
    assert "mine.txt" not in git(repo, "show", "--name-only", "--format=", "HEAD")
    assert git(repo, "diff", "--cached", "--name-only").strip() == "mine.txt"


def test_a_bare_apply_installs_the_other_pieces_before_it_stops_on_an_edited_one(
        monkeypatch, store, repo):
    # lib-x sorts before ri-x, so a loop in name order would stop on it first.
    install(repo, ".github/workflows/lib-x/a.js", LIB1["a.js"] + "// mine\n")
    git(repo, "commit", "-qam", "edit")
    with pytest.raises(apply.NeedsMerge):
        run_apply(monkeypatch, store, repo)
    assert "Install ri-x v2 from the repo-infra standard" in log_subjects(repo)


def test_an_edited_piece_that_claims_the_current_version_is_not_pending(
        monkeypatch, capsys, store, repo):
    install(repo, ".github/workflows/ri-x.yml", NEW + "# mine\n")
    git(repo, "commit", "-qam", "edit")
    run_apply(monkeypatch, store, repo)
    assert (repo / ".github/workflows/ri-x.yml").read_text(encoding="utf-8").endswith("# mine\n")
    assert "Install ri-x" not in "\n".join(log_subjects(repo))


def test_an_edited_dropped_file_does_not_stop_the_other_files_being_written(
        monkeypatch, store, repo):
    install(repo, ".github/workflows/ri-x.yml", NEW)
    install(repo, ".github/workflows/lib-x/gone.js", LIB1["gone.js"] + "// mine\n")
    git(repo, "commit", "-qam", "edit")
    run_apply(monkeypatch, store, repo)
    assert (repo / ".github/workflows/lib-x/a.js").read_text(encoding="utf-8") == LIB2["a.js"]
    assert (repo / ".github/workflows/lib-x/gone.js").is_file()
    assert log_subjects(repo)[0] == "Install lib-x v2 from the repo-infra standard"


@pytest.fixture
def wide_store(tmp_path):
    lib = {"a.js": lib_file("lib-x", 2, "a2"), "b.js": lib_file("lib-x", 2, "b2")}
    history = [("lib-x", f, t) for f, t in LIB1.items()]
    return make_assets(tmp_path / "wide", {"lib-x": lib}, history, core=("lib-x",))


def merge_lib(monkeypatch, wide_store, repo):
    install(repo, ".github/workflows/lib-x/a.js", LIB1["a.js"] + "// mine\n")
    git(repo, "commit", "-qam", "edit")
    with pytest.raises(apply.NeedsMerge):
        run_apply(monkeypatch, wide_store, repo, "--item", "lib-x")
    merged = repo.parent / "merged.js"
    merged.write_text(lib_file("lib-x", 2, "a2") + "// mine\n", encoding="utf-8")
    return merged


def test_a_hand_back_completes_the_piece(monkeypatch, wide_store, repo):
    merged = merge_lib(monkeypatch, wide_store, repo)
    run_apply(monkeypatch, wide_store, repo, "--item", "lib-x", "--from", str(merged))
    lib = repo / ".github/workflows/lib-x"
    assert (lib / "b.js").read_text(encoding="utf-8") == lib_file("lib-x", 2, "b2")
    assert not (lib / "gone.js").exists()
    assert log_subjects(repo)[0] == "Merge lib-x v2 from the repo-infra standard with local edits"


def test_a_merged_piece_prints_the_notes_of_every_version_it_crosses(
        monkeypatch, capsys, wide_store, repo):
    merged = merge_lib(monkeypatch, wide_store, repo)
    capsys.readouterr()
    run_apply(monkeypatch, wide_store, repo, "--item", "lib-x", "--from", str(merged))
    assert "lib-x v2\nNotes for lib-x v2." in capsys.readouterr().out


def test_the_states_are_read_on_the_apply_branch(monkeypatch, store, repo):
    git(repo, "branch", "repo-infra/apply")
    install(repo, ".github/workflows/ri-x.yml", OLD + "# mine\n")
    git(repo, "commit", "-qam", "an edit that only main has")
    run_apply(monkeypatch, store, repo, "--item", "ri-x")
    assert git(repo, "log", "-1", "--format=%s").strip() == (
        "Install ri-x v2 from the repo-infra standard")


def test_from_is_refused_for_an_administration_item(monkeypatch, store, repo):
    with pytest.raises(apply.ApplyError, match="--from"):
        run_apply(monkeypatch, store, repo, "--item", "required-checks", "--from", "x")


# --- release_in_progress ----------------------------------------------------

CHANGES = "# Changes\n\n## [Unreleased]\n\n## 0.6.0 - 2026-09-30\n\n- x\n"


def facts(**over):
    base = dict(cli.CONFORMING_FACTS._asdict())
    base.update(tags=frozenset({"v0.6.0"}))
    base.update(over)
    return Facts(**base)


@pytest.fixture
def changes(tmp_path):
    (tmp_path / "CHANGES.md").write_text(CHANGES, encoding="utf-8")
    return tmp_path


def test_an_open_release_pull_request_is_a_release_in_progress(changes):
    detail = apply.release_in_progress(changes, facts(release_prs=((12, "release/v0.6.1"),)))
    assert "#12" in detail and "release/v0.6.1" in detail and "then run apply" in detail


def test_an_untagged_latest_release_is_a_release_in_progress(changes):
    detail = apply.release_in_progress(changes, facts(tags=frozenset({"v0.5.0"})))
    assert "v0.6.0 is in CHANGES.md but has no tag" in detail


def test_unknown_tags_and_tagged_releases_are_not_a_refusal(changes):
    assert apply.release_in_progress(changes, facts(tags=None)) is None
    assert apply.release_in_progress(changes, facts()) is None


def test_the_latest_release_is_the_first_dated_heading():
    assert apply.latest_release(CHANGES) == "0.6.0"
    assert apply.latest_release("# Changes\n\n## [Unreleased]\n") is None


# --- guards that survive the move to pieces ---------------------------------


def prepared_merge(monkeypatch, store, repo):
    install(repo, ".github/workflows/ri-x.yml", OLD + "# mine\n")
    git(repo, "commit", "-qam", "edit")
    with pytest.raises(apply.NeedsMerge) as stopped:
        run_apply(monkeypatch, store, repo, "--item", "ri-x")
    return stopped.value


def test_a_merged_file_at_the_wrong_version_is_refused(monkeypatch, store, repo):
    prepared_merge(monkeypatch, store, repo)
    merged = repo.parent / "merged.yml"
    merged.write_text(OLD, encoding="utf-8")
    with pytest.raises(apply.ApplyError, match="v1, the piece is v2"):
        run_apply(monkeypatch, store, repo, "--item", "ri-x", "--from", str(merged))


def test_a_merge_prepared_against_a_now_stale_file_is_refused(monkeypatch, store, repo):
    prepared_merge(monkeypatch, store, repo)
    target = repo / ".github/workflows/ri-x.yml"
    target.write_text(OLD + "# someone else\n", encoding="utf-8")
    merged = repo.parent / "merged.yml"
    merged.write_text(NEW, encoding="utf-8")
    with pytest.raises(apply.ApplyError, match="changed since the merge was prepared"):
        run_apply(monkeypatch, store, repo, "--item", "ri-x", "--from", str(merged))
    assert target.read_text(encoding="utf-8") == OLD + "# someone else\n"


def test_from_without_a_prepared_merge_is_refused(monkeypatch, store, repo):
    install(repo, ".github/workflows/ri-x.yml", OLD + "# mine\n")
    merged = repo.parent / "merged.yml"
    merged.write_text(NEW, encoding="utf-8")
    with pytest.raises(apply.ApplyError, match="apply --item ri-x"):
        run_apply(monkeypatch, store, repo, "--item", "ri-x", "--from", str(merged))


def test_a_finished_merge_removes_its_own_scratch_files_but_not_anothers(
        monkeypatch, store, repo):
    prepared_merge(monkeypatch, store, repo)
    scratch = repo / ".git" / apply.MERGE_DIR
    for suffix in ("new", "current", "path", "log"):
        (scratch / f"other.{suffix}").write_text("unrelated", encoding="utf-8")
    merged = repo.parent / "merged.yml"
    merged.write_text(NEW + "# mine\n", encoding="utf-8")
    run_apply(monkeypatch, store, repo, "--item", "ri-x", "--from", str(merged))
    for suffix in ("new", "current", "path", "log"):
        assert not (scratch / f"ri-x.{suffix}").exists()
        assert (scratch / f"other.{suffix}").read_text(encoding="utf-8") == "unrelated"


def test_a_crlf_file_is_never_overwritten_and_can_be_merged(monkeypatch, store, repo):
    target = repo / ".github/workflows/ri-x.yml"
    crlf = (OLD + "# mine\n").replace("\n", "\r\n").encode("utf-8")
    target.write_bytes(crlf)
    git(repo, "commit", "-qam", "crlf")
    with pytest.raises(apply.NeedsMerge):
        run_apply(monkeypatch, store, repo, "--item", "ri-x")
    assert target.read_bytes() == crlf
    merged = repo.parent / "merged.yml"
    merged.write_text(NEW + "# mine\n", encoding="utf-8")
    run_apply(monkeypatch, store, repo, "--item", "ri-x", "--from", str(merged))
    assert target.read_text(encoding="utf-8") == NEW + "# mine\n"


def test_changed_reads_paths_git_would_quote(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "a b.yml").write_text("x\n")
    (tmp_path / 'q"uote.yml').write_text("x\n")
    (tmp_path / "same.yml").write_text("x\n")
    git(tmp_path, "add", "same.yml")
    git(tmp_path, "commit", "-qm", "seed")
    assert apply.changed(tmp_path, ["a b.yml", 'q"uote.yml', "same.yml"]) == [
        "a b.yml", 'q"uote.yml']


def test_a_failed_git_command_says_what_git_printed_on_stdout(tmp_path):
    # `git commit` reports "nothing to commit" on stdout, not stderr.
    git(tmp_path, "init", "-q")
    with pytest.raises(apply.ApplyError, match="nothing to commit"):
        apply.git(tmp_path, "commit", "-m", "x")


def test_the_log_is_read_in_a_linked_worktree_and_from_a_relative_root(
        monkeypatch, store, repo, tmp_path):
    linked = tmp_path / "linked"
    git(repo, "worktree", "add", "-q", "-b", "other", str(linked))
    install(linked, ".github/workflows/ri-x.yml", OLD + "# mine\n")
    git(linked, "commit", "-qam", "edit in the worktree")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "ASSETS", store)
    monkeypatch.setattr(cli, "read_facts", lambda repo_name: cli.CONFORMING_FACTS)
    with pytest.raises(apply.NeedsMerge) as stopped:
        cli.main(["apply", "--root", "linked", "--repo", "o/r", "--item", "ri-x"])
    log = stopped.value.log.read_text(encoding="utf-8")
    assert "edit in the worktree" in log


def test_without_git_history_the_log_says_so(tmp_path):
    (tmp_path / ".git").mkdir()
    install(tmp_path, ".github/workflows/ri-x.yml", OLD)
    with pytest.raises(apply.NeedsMerge) as stopped:
        apply._prepare_merge(tmp_path, "ri-x", ".github/workflows/ri-x.yml", NEW, OLD)
    assert stopped.value.log.read_text(encoding="utf-8").startswith("(no history:")


# --- one rule per file ------------------------------------------------------

P1 = {"a.js": lib_file("lib-y", 1, "a1"), "b.js": lib_file("lib-y", 1, "b1")}
P2 = {"a.js": lib_file("lib-y", 2, "a2"), "b.js": lib_file("lib-y", 2, "b2")}
P3 = lib_file("lib-y", 3, "newer")


@pytest.fixture
def pair(tmp_path):
    history = [("lib-y", f, t) for f, t in P1.items()]
    return make_assets(tmp_path / "pair", {"lib-y": P2}, history)


def lib_y(repo, **files):
    for name, text in files.items():
        install(repo, f".github/workflows/lib-y/{name}.js", text)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "set up lib-y")


def hand_back(monkeypatch, pair, repo, name, text):
    merged = repo.parent / f"merged-{name}"
    merged.write_text(text, encoding="utf-8")
    run_apply(monkeypatch, pair, repo, "--item", "lib-y", "--from", str(merged))


def test_an_edited_file_claiming_a_newer_version_is_neither_merged_nor_written(
        monkeypatch, capsys, pair, repo):
    lib_y(repo, a=P1["a.js"], b=P3)
    run_apply(monkeypatch, pair, repo, "--item", "lib-y")
    folder = repo / ".github/workflows/lib-y"
    assert (folder / "b.js").read_text(encoding="utf-8") == P3
    assert (folder / "a.js").read_text(encoding="utf-8") == P2["a.js"]


def test_an_edited_file_claiming_a_newer_version_alone_is_left_alone(
        monkeypatch, capsys, pair, repo):
    lib_y(repo, a=P3, b=P3)
    run_apply(monkeypatch, pair, repo, "--item", "lib-y")
    assert "lib-y: already v2" in capsys.readouterr().out
    assert (repo / ".github/workflows/lib-y/a.js").read_text(encoding="utf-8") == P3


def test_the_merge_targets_the_file_that_needs_it_not_the_first_edited_one(
        monkeypatch, pair, repo):
    # a.js claims the current version, b.js an older one.
    lib_y(repo, a=P2["a.js"] + "// mine\n", b=P1["b.js"] + "// mine\n")
    with pytest.raises(apply.NeedsMerge) as stopped:
        run_apply(monkeypatch, pair, repo)
    assert stopped.value.target.name == "b.js"


def test_two_edited_files_are_merged_one_after_the_other_and_then_done(
        monkeypatch, capsys, pair, repo):
    lib_y(repo, a=P1["a.js"] + "// mine\n", b=P1["b.js"] + "// mine\n")
    with pytest.raises(apply.NeedsMerge) as first:
        run_apply(monkeypatch, pair, repo)
    assert first.value.target.name == "a.js"
    hand_back(monkeypatch, pair, repo, "a", P2["a.js"] + "// mine\n")
    with pytest.raises(apply.NeedsMerge) as second:
        run_apply(monkeypatch, pair, repo)
    assert second.value.target.name == "b.js"
    hand_back(monkeypatch, pair, repo, "b", P2["b.js"] + "// mine\n")
    count = len(log_subjects(repo))
    capsys.readouterr()
    run_apply(monkeypatch, pair, repo)
    assert len(log_subjects(repo)) == count
    assert "Install lib-y" not in capsys.readouterr().out


def test_an_edited_file_at_the_current_version_is_left_while_an_old_file_is_written(
        monkeypatch, pair, repo):
    mine = P2["a.js"] + "// mine\n"
    lib_y(repo, a=mine, b=P1["b.js"])
    run_apply(monkeypatch, pair, repo)
    folder = repo / ".github/workflows/lib-y"
    assert (folder / "a.js").read_text(encoding="utf-8") == mine
    assert (folder / "b.js").read_text(encoding="utf-8") == P2["b.js"]
    assert log_subjects(repo)[0] == "Install lib-y v2 from the repo-infra standard"


def test_the_notes_of_a_merge_start_at_the_targets_claimed_version(
        monkeypatch, capsys, pair, repo):
    lib_y(repo, a=P2["a.js"] + "// mine\n", b=P1["b.js"] + "// mine\n")
    with pytest.raises(apply.NeedsMerge):
        run_apply(monkeypatch, pair, repo)
    capsys.readouterr()
    hand_back(monkeypatch, pair, repo, "b", P2["b.js"] + "// mine\n")
    assert "lib-y v2\nNotes for lib-y v2." in capsys.readouterr().out
