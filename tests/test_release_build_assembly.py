"""release-build.yml, the third assembled file (D28)."""

import json
import pathlib

import pytest
import yaml

from repo_infra import cli
from repo_infra.assemble import AssemblyError, assemble_release_build, render_all
from repo_infra.detect import Detection
from repo_infra.markers import parse_markers

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
TARGET = ".github/workflows/release-build.yml"
REF = "${{ inputs.ref }}"
SEAM_JOB = "release-build-local"
SEAM_BLOCK = "release-build-local-job"


def doc(addons=(), local=False):
    return yaml.safe_load(assemble_release_build(ASSETS, list(addons), MANIFEST, local))


def on(d):
    return d.get("on", d.get(True))


def test_every_repository_gets_a_valid_release_build(tmp_path):
    result = Detection.load(ASSETS / "detection.json").detect(tmp_path)
    files = render_all(ASSETS, result, MANIFEST)
    d = yaml.safe_load(files[TARGET])
    assert on(d) == {"workflow_call": {"inputs": {
        "version": {"type": "string", "required": True},
        "ref": {"type": "string", "required": True}}}}
    assert d["permissions"] == {"contents": "read"}
    assert list(d["jobs"]) == ["release-version"]
    assert [m.asset for m in parse_markers(files[TARGET])] == ["release-build"]


def test_the_tarball_add_on_lands_after_the_frame_with_its_marker():
    text = assemble_release_build(ASSETS, ["release-source-tarball"], MANIFEST)
    assert [(m.asset, m.version) for m in parse_markers(text)] == [
        ("release-build", 1), ("release-source-tarball", 1)]
    assert list(yaml.safe_load(text)["jobs"]) == ["release-version", "release-source-tarball"]


def test_the_tarball_add_on_builds_at_ref_and_uploads_a_release_asset():
    job = doc(["release-source-tarball"])["jobs"]["release-source-tarball"]
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
    """Run the add-on's Locate step in a directory holding `tarballs`."""
    import shutil
    import subprocess

    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not installed")
    steps = doc(["release-source-tarball"])["jobs"]["release-source-tarball"]["steps"]
    script = next(s["run"] for s in steps if s.get("name") == "Locate the tarball")
    work, temp = tmp_path / "src", tmp_path / "runner-temp"
    work.mkdir()
    temp.mkdir()
    for name in tarballs:
        (work / name).write_text("x")
    proc = subprocess.run([bash, "-c", script], cwd=work, capture_output=True, text=True,
                          env={"RUNNER_TEMP": str(temp), "PATH": "/usr/bin:/bin"})
    return proc, sorted(p.name for p in (temp / "release-asset-source").glob("*")) \
        if (temp / "release-asset-source").is_dir() else []


def test_the_tarball_add_on_uploads_exactly_one_tarball(tmp_path):
    proc, moved = _locate(tmp_path, ["app-1.2.0.tar.gz"])
    assert proc.returncode == 0, proc.stderr
    assert moved == ["app-1.2.0.tar.gz"]


@pytest.mark.parametrize("tarballs,message", [
    ([], "make dist produced no tarball"),
    (["a-1.tar.gz", "b-1.tar.gz"], "more than one tarball in the source root"),
])
def test_the_tarball_add_on_refuses_zero_or_two_tarballs(tmp_path, tarballs, message):
    proc, moved = _locate(tmp_path, tarballs)
    assert proc.returncode == 1 and message in proc.stderr
    assert moved == []


def test_the_local_seam_passes_version_ref_and_the_secrets():
    job = doc(local=True)["jobs"][SEAM_JOB]
    assert job == {"uses": "./.github/workflows/release-build-local.yml",
                   "with": {"version": "${{ inputs.version }}", "ref": REF},
                   "secrets": "inherit"}


def test_the_local_seam_carries_its_marker():
    text = assemble_release_build(ASSETS, [], MANIFEST, True)
    assert [m.asset for m in parse_markers(text)] == ["release-build", SEAM_BLOCK]


def test_add_ons_come_before_the_local_seam():
    jobs = list(doc(["release-source-tarball"], local=True)["jobs"])
    assert jobs == ["release-version", "release-source-tarball", SEAM_JOB]


def test_every_build_block_declares_its_assets_and_jobs():
    from repo_infra.assemble import block_job_ids
    for name, meta in MANIFEST["release_build_blocks"].items():
        assert isinstance(meta.get("assets"), list), name
        text = (ASSETS / "release-build" / (name + ".yml")).read_text(encoding="utf-8")
        assert block_job_ids(text) == meta["jobs"], name
    assert MANIFEST["release_build_blocks"]["release-source-tarball"]["assets"] == ["*.tar.gz"]
    assert MANIFEST["release_build_blocks"][SEAM_BLOCK]["seam"] == "release_build_local"


@pytest.mark.parametrize("addons,match", [
    (["release-nothing"], "not declared in the manifest"),
    ([SEAM_BLOCK], '"release_build_local": true'),
    (["release-source-tarball", "release-source-tarball"], "named twice"),
    (True, "must be a list"),
])
def test_a_bad_release_build_value_is_an_assembly_error(addons, match):
    with pytest.raises(AssemblyError, match=match):
        assemble_release_build(ASSETS, addons, MANIFEST)


def test_publish_source_tarball_is_gone():
    assert "publish-source-tarball" not in MANIFEST["publish_blocks"]
    assert not (ASSETS / "publish/publish-source-tarball.yml").exists()


def test_load_reads_release_build_and_release_build_local(tmp_path):
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github/repo-infra.json").write_text(json.dumps(
        {"release_build": ["release-source-tarball"], "release_build_local": True}))
    _m, _r, rendered = cli._load(tmp_path)
    assert list(yaml.safe_load(rendered[TARGET])["jobs"]) == [
        "release-version", "release-source-tarball", SEAM_JOB]
