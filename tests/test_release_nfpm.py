"""ri-release-nfpm (D32). lib/nfpm.js holds the packaging logic and
nfpm.test.js its cases. Here: the piece's call into the library, and, in a
podman container, the pinned nfpm building mtuspy-shaped packages from fake
archives through that library."""

import hashlib
import pathlib
import shutil
import subprocess
import tarfile
import urllib.request

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIECE = ROOT / "skills/repo-infra/assets/pieces/ri-release-nfpm/ri-release-nfpm.yml"
LIB = ROOT / "skills/repo-infra/assets/pieces/workflow-lib/lib"
FIXTURE = ROOT / "tests/fixtures/nfpm"
TARGETS = ["x86_64-unknown-linux-musl", "aarch64-unknown-linux-musl"]
BOTH = '{"deb": {}, "rpm": {}}'
IMAGE = "localhost/repo-infra-nfpm-test"
CONTAINERFILE = ("FROM docker.io/library/debian:trixie\n"
                 "RUN apt-get update && apt-get install -y --no-install-recommends "
                 "rpm git nodejs && rm -rf /var/lib/apt/lists/*\n")
# The step's script with console in place of core: core.setFailed prints its
# message as one ::error:: line and fails the step.
RUNNER = ("const { run } = require('/w/lib/nfpm.js');\n"
          "try {\n"
          "  for (const line of run(process.env)) console.log(line);\n"
          "} catch (error) {\n"
          "  console.log(`::error::${error.message}`);\n"
          "  process.exitCode = 1;\n"
          "}\n")


def doc():
    return yaml.safe_load(PIECE.read_text(encoding="utf-8"))


def steps():
    return {s.get("name"): s for s in doc()["jobs"]["packages"]["steps"]}


def build_step():
    return steps()["Build and read back the packages"]


def test_nfpm_is_pinned_by_version_and_sha256():
    install = steps()["Install nfpm"]
    assert install["env"] == {
        "NFPM_VERSION": "2.47.0",
        "NFPM_SHA256": "0660ca602b2d2d2ae4781a06c692b3eeb9d437ffea05b831d76e41f4a3188783"}
    assert "sha256sum -c -" in install["run"]


def test_the_build_step_runs_the_library_and_fails_with_its_message():
    step = build_step()
    assert step["uses"] == "actions/github-script@v9"
    script = step["with"]["script"]
    assert "require(`${process.env.GITHUB_WORKSPACE}/.github/workflows/lib/nfpm.js`)" in script
    assert "run(process.env)" in script
    assert "core.setFailed(error.message)" in script


def test_the_inputs_reach_the_library_through_env():
    step = build_step()
    assert step["env"] == {"VERSION": "${{ inputs.version }}", "CONFIG": "${{ inputs.config }}",
                           "PACKAGERS": "${{ inputs.packagers }}",
                           "ARCHIVES": "${{ inputs.archives }}"}
    assert "${{" not in step["with"]["script"]


def test_the_piece_names_the_library_it_runs():
    header = PIECE.read_text(encoding="utf-8").split("\n\n", 1)[0]
    assert "# Pieces: ri-release-rust-binaries, workflow-lib" in header
    assert (LIB / "nfpm.js").is_file() and (LIB / "nfpm.test.js").is_file()


def test_the_archives_and_packages_are_where_the_library_looks():
    packages = doc()["jobs"]["packages"]["steps"]
    download = next(s for s in packages if s.get("uses") == "actions/download-artifact@v8")
    assert download["with"] == {"pattern": "release-asset-*", "path": "archives"}
    assert packages[-1]["with"] == {"name": "release-asset-packages", "path": "packages/",
                                    "if-no-files-found": "error"}


def checkout(tmp_path):
    """A checkout with mtuspy's nfpm.yaml and scripts and one commit, the
    archives as download-artifact leaves them, the library and the runner."""
    work = tmp_path / "repo"
    shutil.copytree(FIXTURE / "repo", work)
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.name=test", "-c", "user.email=test@example.org",
                  "commit", "-qm", "fixture"]):
        subprocess.run(["git", *args], cwd=work, check=True)
    stage = tmp_path / "stage" / "mtuspy"
    (stage / "man").mkdir(parents=True)
    (stage / "mtuspy").write_text("#!/bin/sh\necho mtuspy\n")
    (stage / "mtuspy").chmod(0o755)
    (stage / "man" / "mtuspy.1").write_text(".TH MTUSPY 1\n")
    (stage / "README.md").write_text("readme\n")
    (stage / "LICENSE").write_text("license\n")
    for target in TARGETS:
        folder = work / "archives" / f"release-asset-{target}"
        folder.mkdir(parents=True)
        with tarfile.open(folder / f"mtuspy-0.0.0-{target}.tar.gz", "w:gz") as tar:
            tar.add(stage, arcname="mtuspy")
    (tmp_path / "temp").mkdir()
    shutil.copytree(LIB, tmp_path / "lib")
    (tmp_path / "runner.js").write_text(RUNNER)
    return work


@pytest.fixture(scope="session")
def nfpm(tmp_path_factory):
    env = steps()["Install nfpm"]["env"]
    name = f"nfpm_{env['NFPM_VERSION']}_Linux_x86_64.tar.gz"
    url = f"https://github.com/goreleaser/nfpm/releases/download/v{env['NFPM_VERSION']}/{name}"
    data = urllib.request.urlopen(url, timeout=120).read()
    assert hashlib.sha256(data).hexdigest() == env["NFPM_SHA256"]
    folder = tmp_path_factory.mktemp("nfpm")
    (folder / name).write_bytes(data)
    with tarfile.open(folder / name) as tar:
        tar.extract("nfpm", folder, filter="data")
    return folder


@pytest.fixture(scope="session")
def image(tmp_path_factory):
    if shutil.which("podman") is None:
        pytest.skip("podman is not installed")
    context = tmp_path_factory.mktemp("nfpm-image")
    (context / "Containerfile").write_text(CONTAINERFILE)
    subprocess.run(["podman", "build", "-q", "-t", IMAGE, str(context)], check=True,
                   capture_output=True, timeout=900)
    return IMAGE


def in_container(tmp_path, image, nfpm, packagers=BOTH):
    return subprocess.run(
        ["podman", "run", "--rm", "-v", f"{tmp_path}:/w:Z", "-v", f"{nfpm}:/opt/nfpm:ro",
         "-w", "/w/repo", "-e", "PATH=/opt/nfpm:/usr/bin:/bin", "-e", "RUNNER_TEMP=/w/temp",
         "-e", "VERSION=0.0.0", "-e", "CONFIG=nfpm.yaml", "-e", f"PACKAGERS={packagers}",
         "-e", f"ARCHIVES={' '.join(TARGETS)}", image, "node", "/w/runner.js"],
        capture_output=True, text=True, timeout=600)


@pytest.mark.container
def test_the_pinned_nfpm_builds_the_four_packages_and_reads_them_back(tmp_path, image, nfpm):
    work = checkout(tmp_path)
    done = in_container(tmp_path, image, nfpm)
    assert done.returncode == 0, done.stdout + done.stderr
    assert sorted(p.name for p in (work / "packages").iterdir()) == [
        "mtuspy-0.0.0-1.aarch64.rpm", "mtuspy-0.0.0-1.x86_64.rpm",
        "mtuspy_0.0.0-1_amd64.deb", "mtuspy_0.0.0-1_arm64.deb"]
    assert [line for line in done.stdout.splitlines() if ": version " in line] == [
        "mtuspy_0.0.0-1_amd64.deb: version 0.0.0-1, 4 files",
        "mtuspy-0.0.0-1.x86_64.rpm: version 0.0.0, 4 files",
        "mtuspy_0.0.0-1_arm64.deb: version 0.0.0-1, 4 files",
        "mtuspy-0.0.0-1.aarch64.rpm: version 0.0.0, 4 files"]


@pytest.mark.container
def test_a_bad_packagers_input_prints_one_error_line(tmp_path, image, nfpm):
    checkout(tmp_path)
    done = in_container(tmp_path, image, nfpm, packagers='{"deb": "x"}')
    assert done.returncode == 1
    assert done.stdout.splitlines() == [
        '::error::packagers must be a JSON object such as {"deb": {}, "rpm": {"NAME": "value"}}: '
        "one key per packager, each mapping variable names to strings"]
    assert "    at " not in done.stdout + done.stderr
