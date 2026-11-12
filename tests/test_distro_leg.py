"""One leg of ri-release-distro-packages (D38): lib/distro-leg.sh takes the
fixture in tests/fixtures/distro-hello from a release image to a package
installed in a clean container of that release. Each test runs the script on
this machine with podman as the engine and the pinned nfpm on PATH, as the
runner does, so the packages are packed and read back by the real tools."""

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tarfile
import urllib.request

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIB = ROOT / ".github/workflows/lib"
LEG = LIB / "distro-leg.sh"
FIXTURE = ROOT / "tests/fixtures/distro-hello"
NFPM_PIECE = ROOT / ".github/workflows/ri-release-nfpm.yml"

pytestmark = pytest.mark.container


def releases():
    out = subprocess.run(
        ["node", "-p", f"JSON.stringify(require({json.dumps(str(LIB / 'distro.js'))}).RELEASES)"],
        check=True, capture_output=True, text=True)
    return {r["distro"]: r for r in json.loads(out.stdout)}


RELEASES = releases()
# The tags the legs of this file set and the images they pointed at. A later
# leg of the same release moves a tag, so the earlier image is only found by
# its id.
TAGS = set()
BUILT = set()


@pytest.fixture(scope="session")
def podman():
    real = shutil.which("podman")
    if real is None:
        pytest.skip("podman is not installed")
    return real


@pytest.fixture(scope="session", autouse=True)
def remove_built_images(podman):
    yield
    if TAGS:
        subprocess.run([podman, "rmi", "--ignore", *sorted(TAGS)], capture_output=True)
    # Without --force podman keeps an image that another tag still names,
    # such as the tools image test_distro_deps.py tags as well.
    for image in sorted(BUILT):
        subprocess.run([podman, "rmi", "--ignore", image], capture_output=True)


@pytest.fixture(scope="session")
def tools(tmp_path_factory, podman):
    """A folder for the front of PATH: the nfpm of ri-release-nfpm's pin, a
    podman that caps every container at 2 GiB (rootless containers run
    outside the memory scope of the test), and an rpm that runs in an
    AlmaLinux container where this machine has none (the runner installs
    it with apt)."""
    folder = tmp_path_factory.mktemp("tools")
    steps = yaml.safe_load(NFPM_PIECE.read_text(encoding="utf-8"))["jobs"]["packages"]["steps"]
    env = next(s for s in steps if s.get("name") == "Install nfpm")["env"]
    name = f"nfpm_{env['NFPM_VERSION']}_Linux_x86_64.tar.gz"
    url = f"https://github.com/goreleaser/nfpm/releases/download/v{env['NFPM_VERSION']}/{name}"
    data = urllib.request.urlopen(url, timeout=120).read()
    assert hashlib.sha256(data).hexdigest() == env["NFPM_SHA256"]
    (folder / name).write_bytes(data)
    with tarfile.open(folder / name) as tar:
        tar.extract("nfpm", folder, filter="data")
    wrapper = folder / "podman"
    wrapper.write_text(
        "#!/bin/sh\n"
        "sub=$1; shift\n"
        "case $sub in\n"
        f"  run|build) exec {podman} \"$sub\" --memory=2g \"$@\" ;;\n"
        f"  *) exec {podman} \"$sub\" \"$@\" ;;\n"
        "esac\n")
    wrapper.chmod(0o755)
    if shutil.which("rpm") is None:
        rpm = folder / "rpm"
        rpm.write_text(
            "#!/bin/sh\n"
            f"exec {podman} run --rm --memory=1g --security-opt label=disable "
            "-v \"$PWD:$PWD:ro\" -w \"$PWD\" docker.io/library/almalinux:10 rpm \"$@\"\n")
        rpm.chmod(0o755)
    return folder


def checkout(tmp_path, edit=None):
    """A repository with the fixture in pkg/ and one commit."""
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE, repo / "pkg")
    if edit:
        makefile = repo / "pkg" / "Makefile"
        makefile.write_text(edit(makefile.read_text(encoding="utf-8")), encoding="utf-8")
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.name=test", "-c", "user.email=test@example.org",
                  "commit", "-qm", "fixture"]):
        subprocess.run(["git", *args], cwd=repo, check=True)
    return repo


def leg(tmp_path, tools, distro, image=None):
    (tmp_path / "temp").mkdir()
    env = {
        "PATH": f"{tools}:{os.environ['PATH']}", "HOME": os.environ["HOME"],
        "RUNNER_TEMP": str(tmp_path / "temp"), "TMPDIR": str(tmp_path / "temp"),
        "ENGINE": "podman", "IMAGE": image or RELEASES[distro]["image"], "DISTRO": distro,
        "ARCH": "amd64", "VERSION": "1.4.0", "DIRECTORY": "pkg", "PACKAGERS": "{}",
        "LIB": str(LIB),
    }
    done = subprocess.run(["sh", str(LEG)], cwd=tmp_path / "repo", env=env,
                          capture_output=True, text=True, timeout=1800)
    for stage in ("repos", "tools", "build"):
        tag = f"localhost/repo-infra-distro-leg-{distro}-amd64-{stage}"
        found = subprocess.run(["podman", "image", "inspect", "--format", "{{.Id}}", tag],
                               capture_output=True, text=True)
        if found.returncode == 0:
            TAGS.add(tag)
            BUILT.add(found.stdout.strip())
    return done


def packages(repo):
    folder = repo / "packages"
    return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []


EXPECTED = {
    "debian-13": "hello_1.4.0~trixie-1_amd64.deb",
    "almalinux-10": "hello-1.4.0-1.el10.x86_64.rpm",
    "alpine-3.24": "hello-1.4.0-r0-alpine3.24-x86_64.apk",
}


@pytest.mark.parametrize("distro", sorted(EXPECTED))
def test_a_leg_builds_checks_packs_and_installs_the_fixture(distro, tmp_path, tools):
    repo = checkout(tmp_path)
    done = leg(tmp_path, tools, distro)
    assert done.returncode == 0, done.stdout + done.stderr
    assert packages(repo) == [EXPECTED[distro]]
    assert f"{EXPECTED[distro]}: version " in done.stdout
    assert f"distro-leg.sh: installed {EXPECTED[distro]} on {distro}" in done.stdout
    # GNU tar warns about the checksum headers of apk-tools on every read.
    assert "unknown extended header keyword" not in done.stderr


def test_a_failing_make_check_fails_the_leg(tmp_path, tools):
    repo = checkout(tmp_path, lambda text: text.replace("CHECK_FAIL ?=", "CHECK_FAIL = 1"))
    done = leg(tmp_path, tools, "debian-13")
    assert done.returncode != 0
    assert "distro-leg.sh: make check failed" in done.stderr
    assert packages(repo) == []


def test_make_install_writing_nothing_fails_the_leg(tmp_path, tools):
    def no_install(text):
        head, _, _ = text.partition("install: hello\n")
        return head + "install:\n\t@true\n\n.PHONY: all check install\n"

    repo = checkout(tmp_path, no_install)
    done = leg(tmp_path, tools, "debian-13")
    assert done.returncode != 0
    assert "make install wrote nothing under /stage" in done.stderr
    assert packages(repo) == []


def test_a_drifted_image_fails_with_both_codenames(tmp_path, tools):
    repo = checkout(tmp_path)
    done = leg(tmp_path, tools, "debian-13", image=RELEASES["debian-12"]["image"])
    assert done.returncode != 0
    assert "debian-13 expects trixie, the image says bookworm" in done.stderr
    assert packages(repo) == []


DYNAMIC = LIB / "distro-dynamic.sh"


@pytest.mark.parametrize(("image", "files", "expected"), [
    ("debian-13", ["/bin/ls"], "true"),
    # A shared library has no interpreter but names the libraries it needs.
    ("debian-13", ["/lib/x86_64-linux-gnu/libz.so.1.3.1"], "true"),
    # Debian's ldconfig is a static PIE: a dynamic section, nothing needed.
    ("debian-13", ["/sbin/ldconfig"], "false"),
    ("debian-13", ["/etc/os-release"], "false"),
    ("debian-13", [], "false"),
    ("debian-13", ["/sbin/ldconfig", "/bin/ls"], "true"),
    ("alpine-3.24", ["/bin/busybox"], "true"),
    # The musl loader needs nothing and has no interpreter of its own.
    ("alpine-3.24", ["/lib/ld-musl-x86_64.so.1"], "false"),
])
def test_the_stage_is_dynamic_only_with_an_interpreter_or_a_needed_library(
        image, files, expected, podman):
    copies = " && ".join(f"cp {f} /stage/" for f in files) or ":"
    done = subprocess.run(
        [podman, "run", "--rm", "--memory=1g", "--security-opt", "label=disable",
         "-v", f"{LIB}:/ri:ro", RELEASES[image]["image"], "sh", "-ec",
         f"mkdir /stage && {copies} && sh /ri/distro-dynamic.sh /stage"],
        capture_output=True, text=True, timeout=600)
    assert (done.returncode, done.stdout, done.stderr) == (0, f"{expected}\n", "")


def test_a_static_program_packs_without_dependencies_and_installs(tmp_path, tools):
    repo = checkout(tmp_path, lambda text: text.replace("-O2 -o", "-O2 -static -o"))
    done = leg(tmp_path, tools, "debian-13")
    assert done.returncode == 0, done.stdout + done.stderr
    deb = repo / "packages" / EXPECTED["debian-13"]
    depends = subprocess.run(["dpkg-deb", "--field", str(deb), "Depends"],
                             capture_output=True, text=True, check=True)
    assert depends.stdout.strip() == ""
    assert f"distro-leg.sh: installed {EXPECTED['debian-13']} on debian-13" in done.stdout


def test_a_dynamic_program_whose_config_drops_the_dependencies_fails(tmp_path, tools):
    repo = checkout(tmp_path)
    config = repo / "pkg" / "nfpm.yaml"
    config.write_text(config.read_text(encoding="utf-8").replace("[${DEPENDS}]", "[]"),
                      encoding="utf-8")
    subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.org",
                    "commit", "-qam", "no depends"], cwd=repo, check=True)
    done = leg(tmp_path, tools, "debian-13")
    assert done.returncode != 0
    assert "declares no dependencies although the stage holds ELF files" in done.stderr
