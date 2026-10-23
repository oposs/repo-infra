"""What check reports about container-make and the pieces the callers call
(#94): a called remote piece's requirements are checked like an installed
piece's (D-a), a call into a subdirectory or another repository does not
count (D-a2), and container-make's own rules."""

import pathlib

import pytest
from piecekit import install

from repo_infra import check, cli
from repo_infra.pieces import load_pieces, load_published

PIECES = load_pieces()
PUBLISHED = load_published()
FRAGMENT = "build/container-make.mk"
TOOLCHAIN = '[toolchain]\nchannel = "1.85.0"\n'
GUARDED = ("include build/container-make.mk\n"
           "ifeq ($(CONTAINER_DRIVER),no)\n"
           "check: fmt-check lint test-unit\n"
           "endif\n")


def install_piece(root, name):
    for path, text in PIECES[name].files.items():
        install(root, path, text)


def call(*jobs):
    """A ci.yml whose jobs call the given pieces at @v2; a job is a piece name
    or (name, {with}). The jobs are only what the scan reads."""
    lines = ["name: CI", "on: push", "jobs:"]
    for number, job in enumerate(jobs):
        name, given = job if isinstance(job, tuple) else (job, {})
        lines += [f"  job{number}:",
                  f"    uses: oposs/repo-infra/.github/workflows/{name}.yml@v2"]
        if given:
            lines.append("    with:")
            lines += [f"      {key}: {value}" for key, value in given.items()]
    return "\n".join(lines) + "\n"


def repo(tmp_path, *jobs, pieces=()):
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    if jobs:
        install(root, ".github/workflows/ci.yml", call(*jobs))
    for name in pieces:
        install_piece(root, name)
    return root


def called(root):
    docs = check.callers.read_workflows(root)
    return check.called_pieces(docs, check.rendered(PIECES, docs))


def rows(root):
    docs = check.callers.read_workflows(root)
    pieces = check.rendered(PIECES, docs)
    items = check.piece_items(root, pieces, PUBLISHED, check.called_pieces(docs, pieces))
    return [(i.name, i.state, i.detail) for i in items]


def missing(root):
    return [r for r in rows(root) if r[1] == "missing" and r[0] != "dependabot"]


def container_rows(root):
    docs = check.callers.read_workflows(root)
    pieces = check.rendered(PIECES, docs)
    items = check.container_make_items(root, pieces, PUBLISHED,
                                       check.called_pieces(docs, pieces))
    return [(i.name, i.state, i.detail) for i in items]


def test_a_call_of_ri_ci_container_without_the_fragment_is_reported(tmp_path):
    root = repo(tmp_path, "ri-ci-container")
    assert missing(root) == [("container-make", "missing", "ri-ci-container needs it")]


def test_the_fragment_without_a_call_is_reported(tmp_path):
    root = repo(tmp_path, pieces=["container-make"])
    ((name, state, detail),) = missing(root)
    assert (name, state) == ("ri-ci-container", "missing")
    assert detail.startswith("container-make needs it; no caller job calls")
    assert PIECES["ri-ci-container"].uses in detail


def test_the_pair_together_reports_nothing_missing(tmp_path):
    root = repo(tmp_path, "ri-ci-container", pieces=["container-make"])
    assert missing(root) == []
    assert ("container-make", "current", f"v{PIECES['container-make'].version}") in rows(root)


@pytest.mark.parametrize("given", [{"directory": "sub"},
                                   {"repository": "oposs/other"}])
def test_a_call_with_directory_or_repository_is_not_counted(tmp_path, given):
    """D-a2: check reads only the top level; the fragment of such a call
    lives below it, or in another repository."""
    root = repo(tmp_path, ("ri-ci-container", given))
    assert called(root) == set()
    assert missing(root) == []
    install_piece(root, "container-make")
    assert [r[0] for r in missing(root)] == ["ri-ci-container"]


@pytest.mark.parametrize("directory", ['""', ".", "./", "null", "~"])
def test_a_call_at_the_top_level_counts(tmp_path, directory):
    root = repo(tmp_path, ("ri-ci-container", {"directory": directory}))
    assert called(root) == {"ri-ci-container"}


def test_a_local_call_counts_like_a_remote_one(tmp_path):
    """repo-infra calls its pieces through ./ (D33)."""
    root = tmp_path / "repo"
    install(root, ".github/workflows/ci.yml",
            "on: push\njobs:\n  c:\n    uses: ./.github/workflows/ri-ci-container.yml\n")
    assert called(root) == {"ri-ci-container"}


def test_a_called_piece_needs_its_build_files(tmp_path):
    root = repo(tmp_path, "ri-release-rust-binaries")
    assert missing(root) == [("man", "missing", "ri-release-rust-binaries needs it"),
                             ("man-lua", "missing", "ri-release-rust-binaries needs it")]


def test_a_remote_alternative_is_met_only_when_called(tmp_path):
    root = repo(tmp_path, "ri-release-nfpm")
    ((name, state, detail),) = missing(root)
    assert (name, state) == ("ri-release-rust-binaries", "missing")
    assert detail.startswith("ri-release-nfpm needs it; no caller job calls")
    root = repo(tmp_path / "b", "ri-release-nfpm", "ri-release-go-binaries",
                pieces=["man", "man-lua"])
    assert missing(root) == []


def test_missing_dependencies_without_called_keeps_remote_alternatives_met(tmp_path):
    """apply never installs a remote piece: without `called` a remote
    requirement counts as met, as before D-a."""
    root = repo(tmp_path, pieces=["container-make"])
    states = {name: check.piece_state(root, piece, PUBLISHED.get(name, {}))
              for name, piece in PIECES.items() if not piece.remote}
    assert check.missing_dependencies(PIECES, states) == []
    assert check.missing_dependencies(PIECES, states, set()) == [
        ("ri-ci-container", "container-make")]


def pending(root):
    files = cli._files(root, PIECES)
    states = cli._states(root, files, PUBLISHED)
    return cli._pending(root, files, states, PUBLISHED, PIECES)


def test_a_bare_apply_installs_what_a_called_piece_needs_and_no_remote_piece(tmp_path):
    """The loop "run check, then apply" ends clean: apply installs the local
    pieces check reports missing for a called piece, and never a remote one."""
    root = repo(tmp_path, "ri-release-rust-binaries", pieces=["container-make"])
    names = pending(root)
    assert {"man", "man-lua"} <= set(names)
    assert not [name for name in names if PIECES[name].remote]


def test_a_bare_apply_does_not_install_for_a_call_into_a_subdirectory(tmp_path):
    root = repo(tmp_path, ("ri-release-rust-binaries", {"repository": "oposs/other"}))
    assert not {"man", "man-lua"} & set(pending(root))


@pytest.mark.parametrize("autotools", [["container", "container-m4"], ["container-m4"],
                                       ["container"]])
def test_container_make_with_the_autotools_driver_is_a_conflict(tmp_path, autotools):
    root = repo(tmp_path, "ri-ci-container", pieces=["container-make", *autotools])
    ((name, state, detail),) = container_rows(root)
    assert (name, state) == ("container-make", "conflict")
    assert "build/container.mk" in detail and "m4/repo-infra-container.m4" in detail
    assert "autotools" in detail


def test_container_make_alone_reports_nothing(tmp_path):
    root = repo(tmp_path, "ri-ci-container", pieces=["container-make"])
    assert container_rows(root) == []


def test_no_container_make_reports_nothing(tmp_path):
    root = repo(tmp_path, "ri-ci-perl-mkpl", pieces=["container", "container-m4"])
    install(root, "Makefile", "include build/container-make.mk\ncheck:\n\tx\n")
    install(root, "rust-toolchain.toml", TOOLCHAIN)
    install(root, "Containerfile", "FROM debian\n")
    assert container_rows(root) == []


@pytest.mark.parametrize("perl", ["ri-ci-perl-mkpl", "ri-ci-perl-autotools"])
def test_container_make_with_a_perl_ci_piece_is_a_conflict(tmp_path, perl):
    root = repo(tmp_path, "ri-ci-container", perl, pieces=["container-make"])
    ((name, state, detail),) = container_rows(root)
    assert (name, state) == ("container-make", "conflict")
    assert perl in detail and "Makefile" in detail


@pytest.mark.parametrize("text, lines", [
    (GUARDED, []),
    ("include build/container-make.mk\ncheck:\n\tx\n", [2]),
    ("include build/container-make.mk\nifeq ($(CONTAINER_DRIVER),no)\ncheck: a\nelse\n"
     "check:\n\tx\nendif\n", [5]),
    ("include build/container-make.mk\nifeq (${CONTAINER_DRIVER}, no)\nifdef X\ncheck:\n"
     "endif\nendif\n", []),
    ("include build/container-make.mk\n.PHONY: check\n", []),
    ("include build/container-make.mk\ncheck: TEST = x\n", []),
    ("check:\n\tx\n", []),
    ("include build/container-make.mk\nall check:\n", [2]),
])
def test_unguarded_check_lines(text, lines):
    assert check.unguarded_check_lines(text) == lines


def test_an_unguarded_makefile_is_a_problem(tmp_path):
    root = repo(tmp_path, "ri-ci-container", pieces=["container-make"])
    install(root, "Makefile", "include build/container-make.mk\nall check:\n\tx\n")
    ((name, state, detail),) = container_rows(root)
    assert (name, state) == ("container-make", "problem")
    assert "Makefile" in detail and "2" in detail
    assert "ifeq ($(CONTAINER_DRIVER),no)" in detail


def test_only_the_make_file_gnu_make_reads_is_scanned(tmp_path):
    root = repo(tmp_path, "ri-ci-container", pieces=["container-make"])
    install(root, "GNUmakefile", GUARDED)
    install(root, "Makefile", "include build/container-make.mk\ncheck:\n")
    assert container_rows(root) == []


@pytest.mark.parametrize("containerfile, absent", [
    ("FROM rust:1-trixie\nRUN rustup toolchain install 1.85.0\n", None),
    ("FROM docker.io/library/rust:1.85.0-trixie\n", None),
    ("FROM rust:1-trixie\nRUN apt-get update && \\\n    rustup toolchain install 1.85.0\n",
     None),
    ("FROM rust:1-trixie\n# RUN rustup toolchain install 1.85.0\n", "1.85.0"),
    # Docker drops a comment line before it joins the continuation around it.
    ("FROM rust:1-trixie\nRUN apt-get update \\\n    # the pin\n"
     "    && rustup toolchain install 1.85.0\n", None),
    ("FROM rust:1.85-trixie\n", "1.85.0"),
    ("FROM rust:1-trixie\nRUN rustup toolchain install 1.85.01\n", "1.85.0"),
    ("FROM rust:1-trixie\nRUN echo 1.85.0\n", "1.85.0"),
])
def test_toolchain_pin_missing(containerfile, absent):
    assert check.toolchain_pin_missing(TOOLCHAIN, containerfile) == absent


@pytest.mark.parametrize("toolchain", ['[toolchain]\ncomponents = ["clippy"]\n',
                                       "[toolchain\n", 'channel = "1.85.0"\n',
                                       "[toolchain]\nchannel = 1\n"])
def test_toolchain_pin_without_a_channel_is_not_judged(toolchain):
    assert check.toolchain_pin_missing(toolchain, "FROM debian\n") is None


def test_a_missing_pin_is_a_problem(tmp_path):
    root = repo(tmp_path, "ri-ci-container", pieces=["container-make"])
    install(root, "rust-toolchain.toml", TOOLCHAIN)
    install(root, "Containerfile", "FROM rust:1-trixie\n")
    ((name, state, detail),) = container_rows(root)
    assert (name, state) == ("container-make", "problem")
    assert "1.85.0" in detail and "RUN rustup toolchain install 1.85.0" in detail


def test_the_items_appear_in_check_run(tmp_path):
    root = repo(tmp_path, pieces=["container-make"])
    install(root, "Makefile", "include build/container-make.mk\ncheck:\n\tx\n")
    install(root, "rust-toolchain.toml", TOOLCHAIN)
    install(root, "Containerfile", "FROM rust:1-trixie\n")
    items = check.run(root, cli.CONFORMING_FACTS)
    found = [(i.name, i.state) for i in items if i.name in ("container-make",
                                                             "ri-ci-container")]
    assert found == [("container-make", "current"), ("ri-ci-container", "missing"),
                     ("container-make", "problem"), ("container-make", "problem")]
    problems = [i.detail for i in items if (i.name, i.state) == ("container-make", "problem")]
    assert "Makefile" in problems[0] and "1.85.0" in problems[1]


def test_the_real_fixture_guards_its_check():
    """repo-infra's own container-make fixture is a correct project."""
    makefile = pathlib.Path(__file__).parent / "fixtures/container-make/Makefile"
    assert check.unguarded_check_lines(makefile.read_text(encoding="utf-8")) == []
