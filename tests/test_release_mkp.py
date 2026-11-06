"""ri-release-mkp (D37): the Checkmk package built before the merge (D28)."""

import pathlib
import shutil
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIECE = ROOT / ".github/workflows/ri-release-mkp.yml"
REF = "${{ inputs.ref }}"


def _doc():
    return yaml.safe_load(PIECE.read_text(encoding="utf-8"))


def _job():
    return _doc()["jobs"]["release-mkp"]


def test_the_mkp_piece_takes_the_release_build_inputs():
    inputs = _doc()[True]["workflow_call"]["inputs"]  # PyYAML reads `on` as true
    assert inputs["version"]["required"] is True
    assert inputs["ref"]["required"] is True
    assert inputs["repository"]["required"] is False
    assert inputs["repository"]["default"] == "${{ github.repository }}"
    assert _doc()["permissions"] == {"contents": "read"}


def test_the_mkp_job_builds_the_release_version_at_ref_and_uploads_a_release_asset():
    job = _job()
    checkout = job["steps"][0]
    assert checkout["uses"] == "actions/checkout@v7" and checkout["with"] == {
        "repository": "${{ inputs.repository }}", "ref": REF}
    build = job["steps"][1]
    assert build["uses"] == "oposs/mkp-builder@v2"
    assert build["with"]["version"] == "${{ inputs.version }}"
    locate = job["steps"][2]
    assert locate["name"] == "Locate the package"
    assert locate["env"] == {"VERSION": "${{ inputs.version }}"}
    upload = job["steps"][-1]
    assert upload["uses"] == "actions/upload-artifact@v7"
    assert upload["with"]["name"] == "release-asset-mkp"
    assert upload["with"]["path"] == "${{ runner.temp }}/release-asset-mkp/"
    assert upload["with"]["if-no-files-found"] == "error"
    text = PIECE.read_text(encoding="utf-8")
    assert "# Produces: The artifact release-asset-mkp (`*.mkp`); list `*.mkp` in release_assets.\n" in text
    assert "# Choose: The repository has .mkp-builder.ini.\n" in text


def _locate(tmp_path, packages, version="1.2.0"):
    """Run the job's Locate step in a directory holding `packages`."""
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not installed")
    script = next(s["run"] for s in _job()["steps"] if s.get("name") == "Locate the package")
    work, temp = tmp_path / "src", tmp_path / "runner-temp"
    work.mkdir()
    temp.mkdir()
    for name in packages:
        (work / name).parent.mkdir(parents=True, exist_ok=True)
        (work / name).write_text("x")
    proc = subprocess.run([bash, "-c", script], cwd=work, capture_output=True, text=True,
                          env={"RUNNER_TEMP": str(temp), "VERSION": version,
                               "PATH": "/usr/bin:/bin"})
    out = temp / "release-asset-mkp"
    moved = sorted(p.name for p in out.glob("*")) if out.is_dir() else []
    return proc, moved, sorted(p.name for p in work.glob("*"))


def test_the_mkp_job_uploads_exactly_one_package(tmp_path):
    proc, moved, left = _locate(tmp_path, ["oposs_smart_error-1.2.0.mkp"])
    assert proc.returncode == 0, proc.stderr
    assert moved == ["oposs_smart_error-1.2.0.mkp"]
    assert left == []


def test_the_mkp_job_looks_only_in_the_source_root(tmp_path):
    # mkp-builder writes to the root; a package in a subfolder is an old one.
    proc, moved, _ = _locate(tmp_path, ["new-1.2.0.mkp", "dist/old-1.1.0.mkp"])
    assert proc.returncode == 0, proc.stderr
    assert moved == ["new-1.2.0.mkp"]


@pytest.mark.parametrize("packages,message", [
    ([], "mkp-builder produced no package"),
    (["a-1.2.0.mkp", "b-1.2.0.mkp"], "more than one package in the source root"),
    (["a-1.1.0.mkp"], "unexpected package name: 'a-1.1.0.mkp', expected <name>-1.2.0.mkp"),
    (["a b-1.2.0.mkp"], "unexpected package name: 'a b-1.2.0.mkp'"),
])
def test_the_mkp_job_refuses_a_missing_extra_or_misnamed_package(tmp_path, packages, message):
    proc, moved, _ = _locate(tmp_path, packages)
    assert proc.returncode == 1 and message in proc.stderr, proc.stderr
    assert moved == []
