"""ri-release-source-tarball: the make dist tarball built before the merge (D28)."""

import pathlib

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
PIECE = ASSETS / "pieces/ri-release-source-tarball/ri-release-source-tarball.yml"
REF = "${{ inputs.ref }}"


def _job():
    return yaml.safe_load(PIECE.read_text(encoding="utf-8"))["jobs"]["release-source-tarball"]


def test_the_tarball_job_builds_at_ref_and_uploads_a_release_asset():
    job = _job()
    checkout = job["steps"][0]
    assert checkout["uses"] == "actions/checkout@v7" and checkout["with"] == {"ref": REF}
    runs = [s.get("run", "") for s in job["steps"]]
    assert "./bootstrap" in runs and "./configure" in runs
    assert any("make dist" in r for r in runs)
    upload = job["steps"][-1]
    assert upload["uses"].startswith("actions/upload-artifact@")
    assert upload["with"]["name"] == "release-asset-source"
    assert upload["with"]["if-no-files-found"] == "error"
    assert job["timeout-minutes"] == 30


def _locate(tmp_path, tarballs):
    """Run the job's Locate step in a directory holding `tarballs`."""
    import shutil
    import subprocess

    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not installed")
    script = next(s["run"] for s in _job()["steps"] if s.get("name") == "Locate the tarball")
    work, temp = tmp_path / "src", tmp_path / "runner-temp"
    work.mkdir()
    temp.mkdir()
    for name in tarballs:
        (work / name).write_text("x")
    proc = subprocess.run([bash, "-c", script], cwd=work, capture_output=True, text=True,
                          env={"RUNNER_TEMP": str(temp), "PATH": "/usr/bin:/bin"})
    return proc, sorted(p.name for p in (temp / "release-asset-source").glob("*")) \
        if (temp / "release-asset-source").is_dir() else []


def test_the_tarball_job_uploads_exactly_one_tarball(tmp_path):
    proc, moved = _locate(tmp_path, ["app-1.2.0.tar.gz"])
    assert proc.returncode == 0, proc.stderr
    assert moved == ["app-1.2.0.tar.gz"]


@pytest.mark.parametrize("tarballs,message", [
    ([], "make dist produced no tarball"),
    (["a-1.tar.gz", "b-1.tar.gz"], "more than one tarball in the source root"),
])
def test_the_tarball_job_refuses_zero_or_two_tarballs(tmp_path, tarballs, message):
    proc, moved = _locate(tmp_path, tarballs)
    assert proc.returncode == 1 and message in proc.stderr
    assert moved == []
