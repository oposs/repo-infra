"""The prepared base image of ri-release-distro-packages (D38) and the
dependency detector that runs in it. Each test builds the `tools` stage of
lib/distro-base.Containerfile on a real release image, layers the fixture's
build-deps stage on top, and runs lib/distro-deps.sh in that container."""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIB = ROOT / ".github/workflows/lib"
BASE = LIB / "distro-base.Containerfile"
FIXTURE = ROOT / "tests/fixtures/distro-hello"

pytestmark = pytest.mark.container


def releases():
    out = subprocess.run(
        ["node", "-p", f"JSON.stringify(require({json.dumps(str(LIB / 'distro.js'))}).RELEASES)"],
        check=True, capture_output=True, text=True)
    return {r["distro"]: r for r in json.loads(out.stdout)}


RELEASES = releases()


def build(tmp_path_factory, containerfile, tag, *args):
    # No build context, as the piece builds it: an empty directory.
    context = tmp_path_factory.mktemp("context")
    subprocess.run(["podman", "build", "-q", "--memory=2g", "-f", str(containerfile),
                    "-t", tag, *args, str(context)],
                   check=True, capture_output=True, timeout=900)
    return tag


@pytest.fixture(scope="session")
def podman():
    if shutil.which("podman") is None:
        pytest.skip("podman is not installed")


@pytest.fixture(scope="session")
def images(tmp_path_factory, podman):
    """The tools image of a release, then the fixture's build-deps on it."""
    cache = {}

    def get(distro):
        if distro not in cache:
            tools = build(tmp_path_factory, BASE, f"localhost/repo-infra-distro-tools-{distro}",
                          "--build-arg", f"IMAGE={RELEASES[distro]['image']}", "--target", "tools")
            hello = build(tmp_path_factory, FIXTURE / "Containerfile",
                          f"localhost/repo-infra-distro-hello-{distro}",
                          "--build-arg", f"BASE={tools}", "--target", "build-deps")
            cache[distro] = hello
        return cache[distro]

    return get


def in_container(image, work, script):
    return subprocess.run(
        ["podman", "run", "--rm", "--memory=2g", "-v", f"{work}:/w:Z", "-v", f"{LIB}:/ri:ro,Z",
         image, "sh", "-ec", script],
        capture_output=True, text=True, timeout=600)


@pytest.fixture
def built_stage(distro, images, tmp_path):
    """The detector's output for hello built and installed in that release."""
    shutil.copytree(FIXTURE, tmp_path / "src")
    family = RELEASES[distro]["family"]
    result = in_container(images(distro), tmp_path,
                          "cd /w/src && { make && make check && make install DESTDIR=/w/stage; } >&2\n"
                          f"sh /ri/distro-deps.sh {family} /w/stage")
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.mark.parametrize("distro,expect", [
    ("debian-13", r"^libc6 \(>= [0-9.]+\)$"),
    ("almalinux-10", r"^libz\.so\.1\(\)\(64bit\)$"),
    ("alpine-3.24", r"^so:libz\.so\.1$"),
])
def test_the_detector_names_zlib(distro, expect, built_stage):
    lines = built_stage.splitlines()
    assert any(re.match(expect, line) for line in lines), built_stage
    assert lines == sorted(set(lines))


def test_debian_names_zlib_with_its_own_package_and_version(images, tmp_path):
    shutil.copytree(FIXTURE, tmp_path / "src")
    result = in_container(images("debian-13"), tmp_path,
                          "cd /w/src && { make && make install DESTDIR=/w/stage; } >&2\n"
                          "sh /ri/distro-deps.sh deb /w/stage")
    assert re.search(r"^zlib1g \(>= [0-9:.]+\)$", result.stdout, re.M), result.stdout


def test_rpm_drops_the_rpmlib_entries(images, tmp_path):
    shutil.copytree(FIXTURE, tmp_path / "src")
    result = in_container(images("almalinux-10"), tmp_path,
                          "cd /w/src && { make && make install DESTDIR=/w/stage; } >&2\n"
                          "sh /ri/distro-deps.sh rpm /w/stage")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()
    assert "rpmlib(" not in result.stdout


def test_alpine_drops_a_soname_the_stage_provides(images, tmp_path):
    # hello linked against a libz copied into the stage: libz is then the
    # package's own and must not be a dependency, libc still is.
    shutil.copytree(FIXTURE, tmp_path / "src")
    result = in_container(images("alpine-3.24"), tmp_path,
                          "cd /w/src && { make && make install DESTDIR=/w/stage; } >&2\n"
                          "mkdir -p /w/stage/usr/lib/hello && cp \"$(find / -xdev -name libz.so.1 | head -n1)\" /w/stage/usr/lib/hello/\n"
                          "sh /ri/distro-deps.sh apk /w/stage")
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert "so:libz.so.1" not in lines
    assert any(line.startswith("so:libc.musl-") for line in lines), result.stdout


@pytest.mark.parametrize("distro", ["debian-13", "almalinux-10", "alpine-3.24"])
def test_a_stage_without_elf_prints_nothing(distro, images, tmp_path):
    family = RELEASES[distro]["family"]
    result = in_container(images(distro), tmp_path,
                          "mkdir -p /w/stage/usr/share/doc/hello /w/stage/usr/bin\n"
                          "echo text > /w/stage/usr/share/doc/hello/README\n"
                          "printf '#!/bin/sh\\necho hi\\n' > /w/stage/usr/bin/hi\n"
                          f"sh /ri/distro-deps.sh {family} /w/stage")
    assert (result.returncode, result.stdout) == (0, ""), result.stderr


def test_a_perl_xs_object_adds_the_perl_api_on_debian(images, tmp_path):
    # Any shared object under a Perl library path stands in for an XS module.
    result = in_container(images("debian-13"), tmp_path,
                          "dir=/w/stage/usr/lib/perl5/auto/Hello\n"
                          "mkdir -p $dir && cp \"$(find /usr/lib -name libz.so.1 | head -n1)\" $dir/Hello.so\n"
                          "sh /ri/distro-deps.sh deb /w/stage")
    assert result.returncode == 0, result.stderr
    assert re.search(r"^perlapi-5\.\d+\.\d+$", result.stdout, re.M), result.stdout


def test_the_detector_refuses_an_unknown_family(images, tmp_path):
    result = in_container(images("debian-13"), tmp_path,
                          "mkdir -p /w/stage && sh /ri/distro-deps.sh pkg /w/stage")
    assert result.returncode != 0
    assert "pkg" in result.stderr


def test_epel_is_enabled_in_the_almalinux_repos_stage(tmp_path_factory, podman):
    repos = build(tmp_path_factory, BASE, "localhost/repo-infra-distro-repos-almalinux-10",
                  "--build-arg", f"IMAGE={RELEASES['almalinux-10']['image']}", "--target", "repos")
    result = subprocess.run(["podman", "run", "--rm", "--memory=2g", repos, "dnf", "repolist"],
                            capture_output=True, text=True, timeout=600)
    ids = [line.split()[0] for line in result.stdout.splitlines()[1:] if line.strip()]
    assert "epel" in ids and "crb" in ids, result.stdout
