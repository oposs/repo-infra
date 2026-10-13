"""The release gate (D33) runs mtuspy's CI and release-build jobs as the
example calls them, with the pieces of the commit under test."""

import json
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
GATE = ROOT / ".github/workflows/gate-mtuspy.yml"
EXAMPLE = ROOT / "skills/repo-infra/references/examples/mtuspy"
CI_JOBS = ("rust", "rust-musl", "man")
BUILD_JOBS = ("binaries", "packages", "homebrew")
FROM_SOURCE = {"repository": "${{ needs.source.outputs.repository }}",
               "ref": "${{ needs.source.outputs.ref }}",
               "version": "${{ needs.source.outputs.version }}"}


def load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def gate():
    return load(GATE)


def _needs(job):
    value = job.get("needs", [])
    return [value] if isinstance(value, str) else list(value)


def normal(job, remote):
    """A job without what the gate and the example must differ in (P10):
    repository, ref, version, if:, the source need, and the form of uses:."""
    out = {k: v for k, v in job.items() if k not in ("if", "needs", "with", "uses")}
    uses = job["uses"]
    prefix = "oposs/repo-infra/.github/workflows/" if remote else "./.github/workflows/"
    assert uses.startswith(prefix), uses
    out["uses"] = uses[len(prefix):].removesuffix("@v2")
    out["with"] = {k: v for k, v in job.get("with", {}).items()
                   if k not in ("repository", "ref", "version")}
    out["needs"] = sorted(n for n in _needs(job) if n != "source")
    return out


def test_the_gate_runs_exactly_the_six_jobs_and_the_source_reader():
    assert set(gate()["jobs"]) == {"source", *CI_JOBS, *BUILD_JOBS}


def test_each_gate_job_equals_the_example_job():
    jobs = gate()["jobs"]
    example = {**load(EXAMPLE / "ci.yml")["jobs"], **load(EXAMPLE / "release-build.yml")["jobs"]}
    for job_id in (*CI_JOBS, *BUILD_JOBS):
        assert normal(jobs[job_id], remote=False) == normal(example[job_id], remote=True), job_id


def test_each_gate_job_reads_the_source_record():
    jobs = gate()["jobs"]
    for job_id in (*CI_JOBS, *BUILD_JOBS):
        assert "source" in _needs(jobs[job_id]), job_id
        given = jobs[job_id]["with"]
        assert given["repository"] == FROM_SOURCE["repository"], job_id
        assert given["ref"] == FROM_SOURCE["ref"], job_id
        if job_id in BUILD_JOBS:
            assert given["version"] == FROM_SOURCE["version"], job_id


def test_the_gate_is_dispatched_only_and_needs_no_secret():
    doc = gate()
    assert list(doc.get("on", doc.get(True))) == ["workflow_dispatch"]
    assert doc.get("on", doc.get(True))["workflow_dispatch"] in (None, {})
    assert "secrets" not in GATE.read_text(encoding="utf-8")
    assert doc["permissions"] == {"contents": "read"}


def test_the_source_record_names_a_tag_and_its_version():
    record = json.loads((EXAMPLE / "source.json").read_text(encoding="utf-8"))
    assert set(record) == {"repository", "ref", "version"}
    assert record["ref"] == f"v{record['version']}"
