"""What the ci pieces, the changelog piece and the test setup hold to (D13, D16, D18, D19).

These tests read the shipped pieces. The detector, the assembler and the old
block files they once ran against are gone (D30)."""

import pathlib

import pytest

from repo_infra import check, workflow
from repo_infra.pieces import ASSETS

ROOT = pathlib.Path(__file__).resolve().parents[1]
MAN_TOOLCHAIN_LINE = "          sudo apt-get install -y pandoc groff man-db"


def piece_text(name):
    return (ASSETS / "pieces" / name / (name + ".yml")).read_text(encoding="utf-8")


def ci_pieces():
    return sorted(p.name for p in (ASSETS / "pieces").glob("ri-ci-*") if p.is_dir())


def test_the_ci_piece_set_is_not_empty():
    # The parametrized tests below would pass on nothing otherwise.
    names = ci_pieces()
    assert "ri-ci-python" in names
    assert len(names) >= 10


@pytest.mark.parametrize("name", ci_pieces())
def test_no_ci_piece_filters_on_paths(name):
    # D13: a workflow skipped by paths filtering stays Pending forever and
    # blocks the pull request. A job skipped by a job-level `if:` reports
    # Success. Only the second is safe behind a required check.
    doc = workflow.load(piece_text(name))
    # path_filter_items judges only the REQUIRED_WORKFLOWS names, so feed the piece as ci.yml.
    assert check.path_filter_items({"ci.yml": doc}) == []


def test_the_changelog_piece_filters_on_no_paths():
    # `changelog-updated` must report on every pull request, or the required
    # check never reports for the ones a filter skips (D13).
    text = (ASSETS / "pieces/changelog/changelog.yml").read_text(encoding="utf-8")
    assert check.path_filter_items({"changelog.yml": workflow.load(text)}) == []


def test_the_path_filter_check_catches_a_filter_in_the_changelog_trigger():
    doc = {"on": {"pull_request": {"paths": ["src/**"]}}}
    assert [i.name for i in check.path_filter_items({"changelog.yml": doc})] == ["changelog.yml"]
    doc = {"on": {"pull_request": {"paths-ignore": ["docs/**"]}}}
    assert [i.name for i in check.path_filter_items({"changelog.yml": doc})] == ["changelog.yml"]


def test_a_comment_that_only_mentions_paths_is_not_a_filter():
    text = ("# Never add paths: or paths-ignore: to this workflow (spec D13).\n"
            "on:\n  pull_request:\n    branches: [main]\n")
    assert check.path_filter_items({"changelog.yml": workflow.load(text)}) == []


def test_the_autotools_piece_installs_only_the_fixed_host_toolchain():
    text = piece_text("ri-ci-perl-autotools")
    assert "autoconf automake gettext podman" in text
    # D16: no per-repo package list, in any shape.
    assert "apt-packages" not in text
    assert "system_packages" not in text


def test_the_autotools_piece_runs_make_test():
    text = piece_text("ri-ci-perl-autotools")
    assert "make test" in text
    assert "make check" not in text


def test_the_autotools_piece_no_longer_documents_a_bare_configure_limit():
    # D18 closed it: plain ./configure is driver mode, so the runner never
    # probes the project's system dependencies.
    text = piece_text("ri-ci-perl-autotools")
    assert "Known limit" not in text
    assert "enable-pkgonly" not in text


def test_the_selftest_piece_declares_exactly_its_two_jobs():
    doc = workflow.load(piece_text("ri-ci-repo-infra-selftest"))
    assert list(doc["jobs"]) == ["repo-infra-selftest", "repo-infra-man"]


def test_the_selftest_piece_runs_only_the_container_marked_tests():
    # The marker is what keeps the ordinary pytest job sub-second. A selftest
    # job that ran the whole suite would duplicate it and hide its own cost.
    assert "-m container" in piece_text("ri-ci-repo-infra-selftest")


def test_the_three_pieces_install_a_byte_identical_host_toolchain():
    # D19: podman on an Ubuntu runner is the link the self-test exists to
    # exercise. If any of these three pieces drift, the self-test keeps
    # passing against a toolchain another piece no longer ships. Full-line
    # equality, not substring containment, catches indentation changes and
    # appended packages.
    expected_line = "          sudo apt-get install -y autoconf automake gettext podman"
    for name in (
        "pieces/ri-ci-perl-autotools/ri-ci-perl-autotools.yml",
        "pieces/ri-ci-repo-infra-selftest/ri-ci-repo-infra-selftest.yml",
        "pieces/ri-release-source-tarball/ri-release-source-tarball.yml",
    ):
        text = (ASSETS / name).read_text(encoding="utf-8")
        # The selftest piece also installs the man toolchain for repo-infra-man;
        # that line is pinned separately, against ri-ci-man.
        lines = [line for line in text.split("\n")
                 if "apt-get install" in line and line != MAN_TOOLCHAIN_LINE]
        assert len(lines) == 1, f"{name}: expected 1 apt-get install line, found {len(lines)}"
        assert lines[0] == expected_line, f"{name}: expected {expected_line!r}, got {lines[0]!r}"


@pytest.mark.parametrize("piece", ci_pieces())
def test_a_piece_that_runs_pytest_installs_the_declared_test_dependencies(piece):
    """`-m <marker>` filters selection, not collection.

    pytest imports every module under tests/ before deciding which to run, so a
    job that runs only a subset still needs whatever the whole suite imports.
    The container self-test job learned this the expensive way: it installed
    pytest alone and died with `1 error during collection` on a test file it
    was never going to run.
    """
    text = piece_text(piece)
    if "python3 -m pytest" not in text:
        return
    assert "requirements-dev.txt" in text, (
        "%s runs pytest but never installs the repository's declared test "
        "dependencies" % piece)


def test_the_pytest_pieces_are_among_those_checked():
    # The check above returns early for a piece without pytest; make sure it
    # still has pieces that do run it.
    running = [p for p in ci_pieces() if "python3 -m pytest" in piece_text(p)]
    assert "ri-ci-repo-infra-selftest" in running


def test_the_man_selftest_installs_what_ci_man_installs():
    # repo-infra-man proves the build assets ci-man runs. On a different
    # toolchain it would prove something else, and stay green doing it.
    for name in ("ri-ci-man", "ri-ci-repo-infra-selftest"):
        assert piece_text(name).split("\n").count(MAN_TOOLCHAIN_LINE) == 1, name


def test_the_man_selftest_runs_the_pandoc_marked_tests():
    job = piece_text("ri-ci-repo-infra-selftest").split("  repo-infra-man:", 1)[1]
    assert "python3 -m pytest -m pandoc -v tests" in job
    assert "requirements-dev.txt" in job


def test_the_plain_pytest_run_deselects_the_pandoc_tests():
    # ci-python runs a bare `python3 -m pytest` and installs no pandoc. With CI
    # set, a selected pandoc test fails there, so addopts must deselect them,
    # and `make test` must select them again for local runs.
    ini = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert 'addopts = -m "not container and not pandoc"' in ini
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert 'python3 -m pytest -q $(BASETEMP) -m "not container" tests' in makefile


def test_every_non_yaml_asset_is_covered_by_a_test():
    # Anything under pieces/ other than YAML, JSON, JavaScript and Markdown needs
    # its own test file, or it ships unchecked.
    #   .mk  -> tests/test_build_assets.py, tests/test_man_build.py
    #   .m4  -> tests/test_container_m4.py
    #   .lua -> tests/test_man_build.py
    others = {p.suffix for p in (ASSETS / "pieces").rglob("*") if p.is_file()} - {
        ".yml", ".yaml", ".json", ".js", ".md"}
    assert others == {".mk", ".m4", ".lua"}, "a new asset kind arrived with no test: %s" % others
