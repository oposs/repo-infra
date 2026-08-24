import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
FIXTURE = ROOT / "tests/fixtures/autotools-driver"

pytestmark = pytest.mark.container


def run(args, cwd, check=True, timeout=900):
    """Run a command and return the CompletedProcess, output captured."""
    return subprocess.run(args, cwd=cwd, check=check, timeout=timeout,
                          capture_output=True, text=True)


@pytest.fixture(scope="session")
def tree(tmp_path_factory):
    """The fixture project with the shipped assets installed, bootstrapped."""
    work = tmp_path_factory.mktemp("autotools-driver")
    shutil.copytree(FIXTURE, work, dirs_exist_ok=True)
    (work / "m4").mkdir()
    (work / "build").mkdir()
    shutil.copy(ASSETS / "m4/repo-infra-container.m4", work / "m4")
    shutil.copy(ASSETS / "build/container.mk", work / "build")
    done = run(["autoreconf", "-i"], work)
    # D18's contract guards the project's own `test:` with `if !CONTAINER_DRIVER`
    # precisely so automake does not warn about a duplicate definition.
    assert "warning" not in done.stderr.lower(), done.stderr
    return work


def test_native_mode_runs_the_real_suite_and_defines_no_driver_targets(tree):
    run(["./configure", "--disable-container"], tree)
    done = run(["make", "test"], tree)
    assert "# TOTAL: 1" in done.stdout and "# PASS:  1" in done.stdout
    for target in ("container", "test-dev"):
        missing = run(["make", target], tree, check=False)
        assert missing.returncode != 0, "%s exists in native mode" % target
        assert "No rule to make target" in missing.stderr


def test_driver_mode_builds_the_image_and_tests_inside_it(tree):
    run(["./configure"], tree)
    done = run(["make", "test"], tree)
    assert "# TOTAL: 1" in done.stdout and "# PASS:  1" in done.stdout


def test_dist_leaves_a_tarball_on_the_host(tree):
    run(["./configure"], tree)
    run(["make", "dist"], tree)
    tarballs = sorted(tree.glob("*.tar.gz"))
    assert len(tarballs) == 1, tarballs


def test_test_dev_runs_the_live_working_tree(tree):
    """Proven by exit status, never by TAP text.

    Automake's default driver judges a test by its exit status, so a script
    printing `not ok 1` while exiting 0 reports PASS and proves nothing. Make
    the host copy fail and require test-dev to fail with it.
    """
    run(["./configure"], tree)
    test_file = tree / "t/basic.t"
    original = test_file.read_text(encoding="utf-8")
    test_file.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    try:
        failed = run(["make", "test-dev", "TARGET=t/basic.t"], tree, check=False)
        assert failed.returncode != 0, "test-dev passed against a failing host copy"
    finally:
        test_file.write_text(original, encoding="utf-8")
        test_file.chmod(0o755)
    passed = run(["make", "test-dev", "TARGET=t/basic.t"], tree)
    assert "# PASS:  1" in passed.stdout


def test_the_refusals_abort_make(tree):
    run(["./configure"], tree)
    no_target = run(["make", "test-dev"], tree, check=False)
    assert no_target.returncode != 0
    assert "TARGET is required" in no_target.stdout + no_target.stderr

    no_destdir = run(["make", "install"], tree, check=False)
    assert no_destdir.returncode != 0
    assert "DESTDIR is required" in no_destdir.stdout + no_destdir.stderr
