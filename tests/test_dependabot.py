"""The dependabot piece lists the ecosystems of the CI pieces the callers call
(#92). Its asset is the text for a repository that calls none of them; check
and apply append one entry per ecosystem."""

import hashlib
import json
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


def repo(tmp_path, *called, dependabot=None, config=None):
    root = tmp_path / "repo"
    (root / ".github/workflows").mkdir(parents=True)
    (root / ".github/workflows/ci.yml").write_text(ci(*called), encoding="utf-8")
    if dependabot is not None:
        (root / TARGET).write_text(dependabot, encoding="utf-8")
    if config is not None:
        (root / ".github/repo-infra.json").write_text(json.dumps(config), encoding="utf-8")
    return root


def pieces_of(root):
    return check.rendered(load_pieces(), callers.read_workflows(root), check.read_config(root))


def rendered(root):
    return pieces_of(root)["dependabot"].files[TARGET]


def state(root):
    found = [(i.state, i.detail) for i in check.piece_items(
        root, pieces_of(root), load_published()) if i.name == "dependabot"]
    return found[0]


def test_the_asset_is_v4():
    assert load_pieces()["dependabot"].version == 4


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
    assert state(root) == ("current", "v4")


OTHER = (f"{TARGET} lists other ecosystems or directories than the callers' CI pieces "
         "and \"dependabot\" in .github/repo-infra.json ask for; apply rewrites it")


def test_a_current_file_for_other_callers_is_outdated(tmp_path):
    root = repo(tmp_path, "ri-ci-rust", dependabot=BASE)
    assert state(root) == ("outdated", OTHER)


def test_a_v3_file_with_an_ecosystem_no_caller_builds_is_outdated(tmp_path):
    root = repo(tmp_path, dependabot=BASE + entry("cargo") + entry("npm"))
    assert state(root)[0] == "outdated"


def test_v2_reads_outdated(tmp_path):
    root = repo(tmp_path, "ri-ci-rust", dependabot=V2)
    assert state(root) == ("outdated", "v2 installed, v4 available; apply replaces it")


def test_v2_with_a_hand_added_entry_reads_outdated(tmp_path):
    root = repo(tmp_path, "ri-ci-rust", dependabot=V2 + entry("cargo"))
    assert state(root)[0] == "outdated"


def test_an_edited_entry_is_edited(tmp_path):
    root = repo(tmp_path, "ri-ci-rust",
                dependabot=BASE + entry("cargo").replace("weekly", "daily"))
    assert state(root)[0] == "edited"


FROZEN = pathlib.Path(__file__).resolve().parent / "fixtures/dependabot/v3-cargo-npm.yml"


def test_a_frozen_v3_file_keeps_its_version():
    """The bytes v3 wrote for a Rust and pnpm repository, frozen. A change to
    the entry text that stops published_base stripping this file's entries
    fails here, before every v3 copy reads edited."""
    data = FROZEN.read_bytes()
    base = pieces.published_base("dependabot", data)
    assert hashlib.sha256(base).hexdigest() == load_published()["dependabot"][TARGET][3]


def test_a_frozen_v3_file_reads_current_or_outdated(tmp_path):
    root = repo(tmp_path, "ri-ci-rust", "ri-ci-node-pnpm",
                dependabot=FROZEN.read_text(encoding="utf-8"))
    if load_pieces()["dependabot"].version == 3:
        assert state(root) == ("current", "v4")
    else:
        assert state(root)[0] == "outdated"
        assert state(root)[1].startswith("v3 installed")


def test_install_writes_the_rendered_text(tmp_path):
    root = repo(tmp_path, "ri-ci-go", dependabot=BASE)
    docs = callers.read_workflows(root)
    piece = check.rendered(load_pieces(), docs)["dependabot"]
    history = load_published()["dependabot"]
    plan = apply.plan_piece(root, piece, check.piece_state(root, piece, history), history)
    assert plan.write == [TARGET] and plan.since == 4
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
        "Install dependabot v4 from the repo-infra standard\n")


def test_repo_infra_lists_pip():
    root = pathlib.Path(__file__).resolve().parents[1]
    assert (root / TARGET).read_text(encoding="utf-8") == BASE + entry("pip")


# #117: further directories per ecosystem, from the "dependabot" key of
# .github/repo-infra.json.
SHADCN = {"dependabot": {"cargo": ["/tools/stylegen", "/tools/icongen", "/tools/fontgen"]}}
SHADCN_CARGO = """  - package-ecosystem: cargo
    directories:
      - /
      - /tools/stylegen
      - /tools/icongen
      - /tools/fontgen
    schedule:
      interval: weekly
    labels:
      - dependencies
      - no-changelog
"""


def test_listed_directories_follow_the_top_in_their_order(tmp_path):
    root = repo(tmp_path, "ri-ci-rust", "ri-ci-node-pnpm", config=SHADCN)
    assert rendered(root) == BASE + SHADCN_CARGO + entry("npm")


def test_the_listed_entry_is_the_entry_function():
    assert pieces.dependabot_entry(
        "cargo", ["/", "/tools/stylegen", "/tools/icongen", "/tools/fontgen"]) == SHADCN_CARGO


def test_an_ecosystem_without_a_list_keeps_the_v3_entry(tmp_path):
    root = repo(tmp_path, "ri-ci-rust", "ri-ci-node-pnpm", config={"dependabot": {}})
    assert rendered(root) == BASE + entry("cargo") + entry("npm")


def test_a_configured_file_is_current(tmp_path):
    root = repo(tmp_path, "ri-ci-rust", dependabot=BASE + SHADCN_CARGO, config=SHADCN)
    assert state(root) == ("current", "v4")


def test_a_listed_entry_without_the_key_is_outdated(tmp_path):
    root = repo(tmp_path, "ri-ci-rust", dependabot=BASE + SHADCN_CARGO)
    assert state(root) == ("outdated", OTHER)


def test_a_key_the_file_does_not_carry_yet_is_outdated(tmp_path):
    root = repo(tmp_path, "ri-ci-rust", dependabot=BASE + entry("cargo"), config=SHADCN)
    assert state(root) == ("outdated", OTHER)


def test_published_base_strips_the_listed_entry():
    data = (BASE + SHADCN_CARGO + entry("npm")).encode("utf-8")
    assert pieces.published_base("dependabot", data) == BASE.encode("utf-8")


def test_an_edited_listed_entry_is_edited(tmp_path):
    root = repo(tmp_path, "ri-ci-rust", config=SHADCN,
                dependabot=BASE + SHADCN_CARGO.replace("weekly", "daily"))
    assert state(root)[0] == "edited"


def test_an_invalid_key_renders_no_directories(tmp_path):
    root = repo(tmp_path, "ri-ci-rust",
                config={"dependabot": {"cargo": ["/tools/a", "tools/b"]}})
    assert rendered(root) == BASE + entry("cargo")


def test_install_writes_the_listed_directories(tmp_path):
    root = repo(tmp_path, "ri-ci-rust", dependabot=BASE, config=SHADCN)
    piece = pieces_of(root)["dependabot"]
    history = load_published()["dependabot"]
    apply.install_piece(root, piece, check.piece_state(root, piece, history), history)
    assert (root / TARGET).read_text(encoding="utf-8") == BASE + SHADCN_CARGO


def dependabot_config(root):
    return [i.detail for i in check.config_items(root, callers.read_workflows(root))
            if i.name in ("dependabot", "repo-infra.json")]


def test_the_key_is_known(tmp_path):
    root = repo(tmp_path, "ri-ci-rust", config=SHADCN)
    assert dependabot_config(root) == []


WHERE = '"dependabot.cargo" in .github/repo-infra.json'


@pytest.mark.parametrize("value, problem", [
    (["/a"], '"dependabot" in .github/repo-infra.json must be an object that maps an '
             "ecosystem to a list of directories"),
    ({"cargo": "/a"}, f"{WHERE} must be a list of directories"),
    ({"cargo": [1]}, f"{WHERE} must be a list of directories"),
    ({"cargo": []}, f"{WHERE} is empty; list a directory or remove the key"),
    ({"cargo": ["/"]}, f'{WHERE}: "/" is in the entry when a caller builds cargo at '
                       "the top; list only the other directories"),
    ({"cargo": ["/a", "/a"]}, f'{WHERE}: "/a" is listed twice'),
    ({"github-actions": ["/a"]},
     '"dependabot.github-actions" in .github/repo-infra.json: the github-actions entry '
     "is the piece's own text and stays at directory /"),
    ({"maven": ["/a"]},
     '"dependabot.maven" in .github/repo-infra.json: maven is no ecosystem the pieces '
     "write an entry for; the keys are bun, cargo, gomod, npm, pip"),
    ({"npm": ["/web"]},
     '"dependabot.npm" in .github/repo-infra.json: no caller calls ri-ci-node-pnpm, so '
     "there is no npm entry to add directories to"),
])
def test_a_wrong_key_is_a_problem(tmp_path, value, problem):
    root = repo(tmp_path, "ri-ci-rust", config={"dependabot": value})
    assert dependabot_config(root) == [problem]


def test_an_ecosystem_names_every_piece_that_builds_it(tmp_path):
    root = repo(tmp_path, "ri-ci-python", config={"dependabot": {"cargo": ["/a"]}})
    assert dependabot_config(root) == [
        f"{WHERE}: no caller calls ri-ci-rust or ri-ci-rust-musl, so "
        "there is no cargo entry to add directories to"]


@pytest.mark.parametrize("directory", [
    "tools/a", "/tools/a/", "/tools//a", "/../a", "/tools/../a", "/./a", "/a b",
    "/a#b", "/a:b", ""])
def test_a_directory_must_be_a_clean_path_below_the_top(tmp_path, directory):
    root = repo(tmp_path, "ri-ci-rust", config={"dependabot": {"cargo": [directory]}})
    assert dependabot_config(root) == [
        f'{WHERE}: "{directory}" must start with /, end without /, hold no . or .. and '
        "use only letters, digits and . _ - *"]


@pytest.mark.parametrize("directory", ["/tools/a", "/.config/x", "/lib-*", "/a_b.c-d"])
def test_a_clean_directory_passes(tmp_path, directory):
    root = repo(tmp_path, "ri-ci-rust", config={"dependabot": {"cargo": [directory]}})
    assert dependabot_config(root) == []


# #151: a CI piece called with a `directory` below the top builds the project
# there, so its ecosystem's entry covers that directory, and / only when a
# caller also calls a piece of that ecosystem at the top.
def player(tmp_path, *top, config=None, dependabot=None):
    root = repo(tmp_path, *top, config=config, dependabot=dependabot)
    with open(root / ".github/workflows/ci.yml", "a", encoding="utf-8") as f:
        f.write("  player:\n    uses: oposs/repo-infra/.github/workflows/ri-ci-node-pnpm.yml@v2\n"
                "    with:\n      directory: player\n")
    return root


def single(ecosystem, directory):
    return entry(ecosystem).replace("    directory: /\n", f"    directory: {directory}\n")


def test_a_call_in_a_directory_gives_its_ecosystem_that_directory(tmp_path):
    assert rendered(player(tmp_path)) == BASE + single("npm", "/player")


def test_a_call_in_a_directory_leaves_the_top_level_ecosystems_at_the_top(tmp_path):
    assert rendered(player(tmp_path, "ri-ci-rust")) == BASE + entry("cargo") + single(
        "npm", "/player")


def test_a_top_level_call_and_a_directory_call_list_both(tmp_path):
    root = player(tmp_path, "ri-ci-node-pnpm")
    assert rendered(root) == BASE + pieces.dependabot_entry("npm", ["/", "/player"])


def test_the_key_adds_to_an_ecosystem_built_only_below_the_top(tmp_path):
    root = player(tmp_path, config={"dependabot": {"npm": ["/web"]}})
    assert rendered(root) == BASE + pieces.dependabot_entry("npm", ["/player", "/web"])
    assert not [i for i in check.config_items(root, callers.read_workflows(root))
                if i.name == "dependabot"]


def test_an_entry_at_a_directory_reads_current(tmp_path):
    root = player(tmp_path, dependabot=BASE + single("npm", "/player"))
    assert state(root) == ("current", "v4")
