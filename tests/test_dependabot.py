"""The dependabot piece lists the ecosystems of the CI pieces the callers call
(#92). Its asset is the text for a repository that calls none of them; check
and apply append one entry per ecosystem."""

import pathlib
import subprocess

import pytest

from repo_infra import apply, callers, check, cli, pieces
from repo_infra.pieces import ASSETS, load_pieces, load_published

TARGET = ".github/dependabot.yml"
BASE = (ASSETS / "pieces/dependabot/dependabot.yml").read_text(encoding="utf-8")
# v2 as it shipped in v2.3.1.
V2 = """version: 2
# repo-infra: dependabot v2
#
# Purpose: Keep the pinned GitHub Actions current.
# Choose: Always.
# Supplies: The no-changelog label.
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
    labels:
      - dependencies
      - no-changelog
"""


def entry(ecosystem):
    return (f"  - package-ecosystem: {ecosystem}\n"
            "    directory: /\n"
            "    schedule:\n"
            "      interval: weekly\n"
            "    labels:\n"
            "      - dependencies\n"
            "      - no-changelog\n")


def ci(*called):
    jobs = "".join(f"  {name}:\n    uses: oposs/repo-infra/.github/workflows/{name}.yml@v2\n"
                   for name in called)
    return f"name: CI\non:\n  push:\njobs:\n{jobs}"


def repo(tmp_path, *called, dependabot=None):
    root = tmp_path / "repo"
    (root / ".github/workflows").mkdir(parents=True)
    (root / ".github/workflows/ci.yml").write_text(ci(*called), encoding="utf-8")
    if dependabot is not None:
        (root / TARGET).write_text(dependabot, encoding="utf-8")
    return root


def rendered(root):
    piece = check.rendered(load_pieces(), callers.read_workflows(root))["dependabot"]
    return piece.files[TARGET]


def state(root):
    found = [(i.state, i.detail) for i in check.piece_items(
        root, check.rendered(load_pieces(), callers.read_workflows(root)), load_published())
             if i.name == "dependabot"]
    return found[0]


def test_the_asset_is_v3():
    assert load_pieces()["dependabot"].version == 3


@pytest.mark.parametrize("called, ecosystems", [
    ((), ()),
    (("ri-ci-perl-mkpl", "ri-ci-man", "ri-ci-checkmk-plugin"), ()),
    (("ri-ci-rust",), ("cargo",)),
    (("ri-ci-rust", "ri-ci-rust-musl"), ("cargo",)),
    (("ri-ci-node-pnpm",), ("npm",)),
    (("ri-ci-node-bun",), ("bun",)),
    (("ri-ci-python",), ("pip",)),
    (("ri-ci-go",), ("gomod",)),
    (("ri-ci-rust", "ri-ci-python", "ri-ci-go"), ("cargo", "gomod", "pip")),
])
def test_one_entry_per_ecosystem_the_callers_build(tmp_path, called, ecosystems):
    assert rendered(repo(tmp_path, *called)) == BASE + "".join(map(entry, ecosystems))


def test_a_local_call_in_repo_infra_counts(tmp_path):
    root = repo(tmp_path)
    (root / ".github/workflows/ci.yml").write_text(
        "name: CI\non:\n  push:\njobs:\n  python:\n"
        "    uses: ./.github/workflows/ri-ci-python.yml\n", encoding="utf-8")
    assert rendered(root) == BASE + entry("pip")


def test_a_call_that_checks_another_repository_adds_nothing(tmp_path):
    """repo-infra's gate-mtuspy.yml calls ri-ci-rust on mtuspy."""
    root = repo(tmp_path)
    (root / ".github/workflows/gate.yml").write_text(
        "name: Gate\non:\n  push:\njobs:\n  rust:\n"
        "    uses: ./.github/workflows/ri-ci-rust.yml\n"
        "    with:\n      repository: oposs/mtuspy\n", encoding="utf-8")
    assert rendered(root) == BASE


def test_every_ecosystem_is_named_in_the_header():
    header = " ".join(load_pieces()["dependabot"].header["Produces"].split())
    for name, ecosystem in pieces.ECOSYSTEMS.items():
        assert f"{ecosystem} for {name}" in header or f"and {name}" in header, name


def test_the_rendered_file_is_current(tmp_path):
    root = repo(tmp_path, "ri-ci-rust")
    (root / TARGET).write_text(BASE + entry("cargo"), encoding="utf-8")
    assert state(root) == ("current", "v3")


def test_a_v3_file_for_other_callers_is_outdated(tmp_path):
    root = repo(tmp_path, "ri-ci-rust", dependabot=BASE)
    assert state(root) == ("outdated", f"{TARGET} lists other ecosystems than the CI "
                                       "pieces the callers call; apply rewrites it")


def test_a_v3_file_with_an_ecosystem_no_caller_builds_is_outdated(tmp_path):
    root = repo(tmp_path, dependabot=BASE + entry("cargo") + entry("npm"))
    assert state(root)[0] == "outdated"


def test_v2_reads_outdated(tmp_path):
    root = repo(tmp_path, "ri-ci-rust", dependabot=V2)
    assert state(root) == ("outdated", "v2 installed, v3 available; apply replaces it")


def test_v2_with_a_hand_added_entry_reads_outdated(tmp_path):
    root = repo(tmp_path, "ri-ci-rust", dependabot=V2 + entry("cargo"))
    assert state(root)[0] == "outdated"


def test_an_edited_entry_is_edited(tmp_path):
    root = repo(tmp_path, "ri-ci-rust",
                dependabot=BASE + entry("cargo").replace("weekly", "daily"))
    assert state(root)[0] == "edited"


def test_install_writes_the_rendered_text(tmp_path):
    root = repo(tmp_path, "ri-ci-go", dependabot=BASE)
    docs = callers.read_workflows(root)
    piece = check.rendered(load_pieces(), docs)["dependabot"]
    history = load_published()["dependabot"]
    plan = apply.plan_piece(root, piece, check.piece_state(root, piece, history), history)
    assert plan.write == [TARGET] and plan.since == 3
    apply.install_piece(root, piece, check.piece_state(root, piece, history), history)
    assert (root / TARGET).read_text(encoding="utf-8") == BASE + entry("gomod")


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True,
                          text=True).stdout


def test_apply_installs_the_entries_for_the_callers(tmp_path, monkeypatch):
    root = repo(tmp_path, "ri-ci-rust", dependabot=V2)
    for piece in load_pieces().values():
        if not piece.remote and piece.name != "dependabot":
            for path, text in piece.files.items():
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_text(text, encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", ".")
    git(root, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "start")
    facts = cli.CONFORMING_FACTS._replace(release_prs=(), tags=frozenset())
    monkeypatch.setattr(cli, "read_facts", lambda name: facts)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "t")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@e")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "t")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@e")
    assert cli.main(["apply", "--root", str(root), "--repo", "o/r"]) == 0
    assert (root / TARGET).read_text(encoding="utf-8") == BASE + entry("cargo")
    assert git(root, "log", "-1", "--format=%s") == (
        "Install dependabot v3 from the repo-infra standard\n")


def test_repo_infra_lists_pip():
    root = pathlib.Path(__file__).resolve().parents[1]
    assert (root / TARGET).read_text(encoding="utf-8") == BASE + entry("pip")
