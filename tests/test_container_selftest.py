import os
import pathlib
import shutil
import subprocess
import tarfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
FIXTURE = ROOT / "tests/fixtures/autotools-driver"

pytestmark = pytest.mark.container


def run(args, cwd, check=True, timeout=900):
    """Run a command and return the CompletedProcess, output captured.

    LC_ALL=C keeps make's own diagnostics (e.g. "No rule to make target")
    in English regardless of the host locale.
    """
    return subprocess.run(args, cwd=cwd, check=check, timeout=timeout,
                          capture_output=True, text=True,
                          env={**os.environ, "LC_ALL": "C"})


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
    # make's own un-silenced recipe echo for `test:` -- forgeable only by
    # the real recipe running, not by a stale image passing on its own.
    assert "make -C /src test" in done.stdout


def test_dist_leaves_a_tarball_on_the_host(tree):
    run(["./configure"], tree)
    done = run(["make", "dist"], tree)
    tarballs = sorted(tree.glob("*.tar.gz"))
    assert len(tarballs) == 1, tarballs
    # Proves the containerised `dist:` override ran, not automake's native
    # dist on the host -- which would also leave exactly one tarball behind
    # and hide the very defect this test exists to catch. ":/out" comes from
    # the echoed `-v $(abs_top_builddir):/out` mount in container.mk's recipe.
    assert ":/out" in done.stdout

    # The release path only works if the tarball can actually be configured
    # after extraction (I3): build/container.mk and m4/repo-infra-container.m4
    # are distributed automatically (an included fragment and a macro
    # directory), but Containerfile is the project's own file and falls out
    # unless the project lists it in EXTRA_DIST -- conventions.md's
    # Containerfile contract, item 4. Read the real member names rather than
    # assuming the "selftest-0.1/" prefix, since a version bump would move it.
    with tarfile.open(tarballs[0]) as tar:
        names = {pathlib.PurePosixPath(member).name for member in tar.getnames()}
    for required in ("Containerfile", "container.mk", "repo-infra-container.m4"):
        assert required in names, f"{required} missing from {tarballs[0].name}: {sorted(names)}"


def test_test_dev_runs_the_live_working_tree(tree):
    """Proven by the post-restore run, never by TAP text.

    `test-dev` depends on `container-base`, whose stamp does not exist yet the
    first time this test breaks t/basic.t -- so that first `make` also builds
    the image, baking the broken script into it, and the resulting failure
    proves nothing about the -v mount (a baked-in failure, or even a podman
    build error, would fail the same way). What actually proves the mount is
    live is the run *after* restoring the file: the stamp already exists and
    the Containerfile is unchanged, so no rebuild happens, and the run can
    only pass if the mount overrides /src/t with the fixed host copy.
    """
    run(["./configure"], tree)
    test_file = tree / "t/basic.t"
    original = test_file.read_text(encoding="utf-8")
    test_file.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    try:
        failed = run(["make", "test-dev", "TARGET=t/basic.t"], tree, check=False)
        assert failed.returncode != 0, "test-dev passed against a failing host copy"
        # Reject a pass bought by an infrastructure failure (bad DOCKER, a
        # podman build error) rather than the test actually running and
        # failing -- only the latter proves anything about t/basic.t itself.
        assert "# FAIL:  1" in failed.stdout, failed.stdout + failed.stderr
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

    # Streams merged, not captured separately: the echo goes to stdout and a
    # dead guard's `mkdir -p` error goes to stderr, so separate capture has no
    # ordering to check the guard actually short-circuited the recipe. The
    # `container` prerequisite -- and everything podman prints for it -- runs
    # to completion before the install recipe starts, so the text after the
    # refusal message is the install recipe and nothing else: a live guard
    # exits right there, a dead one falls through into `mkdir` with an empty
    # operand.
    no_destdir = subprocess.run(
        ["make", "install"], cwd=tree, check=False, timeout=900, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        env={**os.environ, "LC_ALL": "C"},
    )
    assert no_destdir.returncode != 0
    merged = no_destdir.stdout
    assert "Error: DESTDIR is required" in merged
    tail = merged.rsplit("Error: DESTDIR is required", 1)[1]
    assert "mkdir" not in tail, tail
