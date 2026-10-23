import fcntl
import os
import pathlib
import pty
import select
import shutil
import signal
import subprocess
import termios
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/container-make"
ALPINE = ("docker.io/library/alpine@sha256:"
          "28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b")
OPTS = "--cpus=4 --memory=2g"

pytestmark = pytest.mark.container

ENGINES = os.environ.get("RI_TEST_ENGINES", "podman docker").split()


def run(args, cwd, env=None, check=True, timeout=900):
    """Run a command and return the CompletedProcess, output captured."""
    return subprocess.run(args, cwd=cwd, check=check, timeout=timeout,
                          capture_output=True, text=True,
                          env={**os.environ, "LC_ALL": "C", **(env or {})})


def git(cwd, *args):
    return run(["git", *args], cwd)


def make_repo(dest, subdir=None):
    """A git repository holding the fixture, at dest or at dest/subdir.

    copytree follows the build/container-make.mk symlink, so the repository
    holds the file itself, as a project that ran `ri-apply` does.
    """
    project = dest / subdir if subdir else dest
    shutil.copytree(FIXTURE, project, dirs_exist_ok=True)
    git(dest, "init", "-q")
    git(dest, "add", "-A")
    git(dest, "commit", "-q", "-m", "fixture")
    return project


@pytest.fixture(params=ENGINES)
def engine(request, require):
    """An engine that answers `info`: skipped when absent, a failure under CI."""
    name = request.param
    require(name)
    if run([name, "info"], ROOT, check=False, timeout=120).returncode != 0:
        if os.environ.get("CI"):
            pytest.fail("%s info fails (CI is set, so this test must run, not skip)" % name)
        pytest.skip("%s info fails" % name)
    return name


class Tree:
    """The fixture repository plus the engine settings every run shares."""

    def __init__(self, engine, path, tag):
        self.engine = engine
        self.path = path
        self.tag = tag

    def env(self, **extra):
        return {"CONTAINER_ENGINE": self.engine, "CONTAINER_TAG": self.tag,
                "CONTAINER_OPTS": OPTS, **extra}

    def make(self, target, cwd=None, check=True, env=None, **knobs):
        """Run make with the fixture knobs as command-line overrides."""
        args = ["%s=%s" % pair for pair in knobs.items()]
        return run(["make", target, *args], cwd or self.path,
                   env=self.env(**(env or {})), check=check)

    def popen(self, *args, **kwargs):
        return subprocess.Popen(["make", "check", *args], cwd=self.path,
                                env={**os.environ, "LC_ALL": "C", **self.env()},
                                **kwargs)

    def running(self):
        done = run([self.engine, "ps", "-q", "--filter", "ancestor=" + self.tag],
                   self.path)
        return done.stdout.split()


@pytest.fixture(scope="module")
def trees(tmp_path_factory):
    """One Tree per engine for the module, with the image and volume removed after.

    Removes only what the tests created: the tagged image and the volume the
    tag names. The shared alpine base image is left alone.
    """
    made = {}

    def get(engine, name="main", subdir=None):
        key = (engine, name)
        if key not in made:
            path = make_repo(tmp_path_factory.mktemp("cm-" + engine + "-" + name), subdir)
            made[key] = Tree(engine, path, "ri-cm-test-%s-%s:local" % (engine, name))
        return made[key]

    yield get
    for tree in made.values():
        run(["make", "container-clean"], tree.path, env=tree.env(), check=False)
        run([tree.engine, "rmi", "-f", tree.tag], tree.path, check=False)


@pytest.fixture
def tree(engine, trees):
    return trees(engine)


def handed_back(path):
    return os.lstat(path).st_uid == os.getuid()


def test_check_runs_as_root_and_leaves_files_to_the_caller(tree):
    done = tree.make("check", TEST="plain")
    assert "fixture: check ran as root" in done.stdout
    assert (tree.path / "check-ran.txt").read_text() == "plain\n"
    assert handed_back(tree.path / "check-ran.txt")
    assert handed_back(tree.path / "out")
    assert handed_back(tree.path / "out/sub/file")


def test_a_failing_check_fails_make_and_still_hands_back(tree):
    done = tree.make("check", check=False, FAIL="1", TEST="failing")
    assert done.returncode != 0
    assert (tree.path / "check-ran.txt").read_text() == "failing\n"
    assert handed_back(tree.path / "check-ran.txt")


def test_an_override_reaches_the_fixture(tree):
    tree.make("check", TEST="a b")
    assert (tree.path / "check-ran.txt").read_text() == "a b\n"


def test_a_worktree_runs_git_in_the_container(tree, tmp_path):
    work = tmp_path / "wt"
    git(tree.path, "worktree", "add", "-q", str(work), "-b", "wt-" + tree.engine)
    try:
        done = tree.make("check", cwd=work, TEST="worktree")
        assert "fixture: check ran as root" in done.stdout
        assert (work / "check-ran.txt").read_text() == "worktree\n"
        foreign = [p for p in (tree.path / ".git").rglob("*")
                   if os.lstat(p).st_uid != os.getuid()]
        assert foreign == []
    finally:
        git(tree.path, "worktree", "remove", "--force", str(work))


def test_a_subdirectory_project_sees_the_whole_repository(engine, trees):
    sub = trees(engine, "sub", subdir="sub")
    top = sub.path.parent
    done = run(["make", "-C", "sub", "check", "TEST=sub"], top, env=sub.env())
    assert "fixture: check ran as root" in done.stdout
    assert (sub.path / "check-ran.txt").read_text() == "sub\n"


def test_a_second_run_reuses_the_cache_volume(tree):
    tree.make("check", CACHE="write")
    done = tree.make("check", CACHE="read")
    assert "fixture: check ran as root" in done.stdout


def test_an_offline_build_uses_the_local_base_image(engine, trees):
    base = "localhost:1/ri-offline-base:1"
    run([engine, "pull", "-q", ALPINE], ROOT)
    run([engine, "tag", ALPINE, base], ROOT)
    try:
        offline = trees(engine, "offline")
        containerfile = offline.path / "Containerfile"
        containerfile.write_text(containerfile.read_text().replace(ALPINE, base))
        done = offline.make("check", TEST="offline")
        assert "fixture: check ran as root" in done.stdout
        if engine == "docker":
            assert "building again on the local copy" in done.stderr
    finally:
        run([engine, "rmi", base], ROOT, check=False)


def wait_for(read_chunk, marker, seconds=300):
    """Collect output until marker appears; return everything read."""
    seen = ""
    deadline = time.monotonic() + seconds
    while marker not in seen:
        assert time.monotonic() < deadline, "no %r in:\n%s" % (marker, seen)
        seen += read_chunk(deadline - time.monotonic())
    return seen


def assert_interrupted_cleanly(tree, proc, name):
    assert proc.wait(timeout=30) != 0
    assert tree.running() == []
    made = tree.path / ("interrupted-" + name) / "made-by-root"
    assert made.exists()
    assert handed_back(made.parent) and handed_back(made)


def test_sigint_without_a_terminal_stops_the_container(tree):
    name = "sigint"
    proc = tree.popen("SLEEP=120", "TEST=" + name, start_new_session=True,
                      stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                      stderr=subprocess.STDOUT, text=True)
    try:
        def read_line(left):
            ready, _, _ = select.select([proc.stdout], [], [], max(left, 0))
            return proc.stdout.readline() if ready else ""
        wait_for(read_line, "fixture: sleeping")
        os.killpg(proc.pid, signal.SIGINT)
        assert_interrupted_cleanly(tree, proc, name)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
        proc.stdout.close()


def test_ctrl_c_on_a_terminal_stops_the_container(tree):
    name = "ctrlc"
    master, slave = pty.openpty()

    def controlling_terminal():
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)

    proc = tree.popen("SLEEP=120", "TEST=" + name, start_new_session=True,
                      stdin=slave, stdout=slave, stderr=slave,
                      preexec_fn=controlling_terminal)
    os.close(slave)
    try:
        def read_chunk(left):
            ready, _, _ = select.select([master], [], [], max(left, 0))
            return os.read(master, 4096).decode(errors="replace") if ready else ""
        wait_for(read_chunk, "fixture: sleeping")
        os.write(master, b"\x03")
        assert_interrupted_cleanly(tree, proc, name)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
        os.close(master)


def test_a_missing_init_names_catatonit(trees, require):
    require("podman")
    if run(["podman", "info"], ROOT, check=False, timeout=120).returncode != 0:
        pytest.skip("podman info fails")
    tree = trees("podman")
    done = run(["make", "check"], tree.path,
               env=tree.env(CONTAINER_OPTS="--init-path=/nonexistent"), check=False)
    assert done.returncode != 0
    assert "catatonit" in done.stdout + done.stderr


def test_kvm_opens_when_the_host_has_it(tree):
    if not os.access("/dev/kvm", os.R_OK | os.W_OK):
        pytest.skip("/dev/kvm is not readable and writable by this user")
    done = tree.make("check", TEST="kvm")
    assert "fixture: /dev/kvm opens" in done.stdout
