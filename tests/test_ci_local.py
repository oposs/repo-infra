"""The ci-local seam (D25): project-owned jobs, required through one fixed path."""

import json
import pathlib

import pytest
import yaml

from repo_infra import cli
from repo_infra.assemble import AssemblyError, render_all
from repo_infra.detect import Detection
from repo_infra.state import classify_contracts

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))


def rust_repo(tmp_path, config=None):
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\nversion = "0.1.0"\n')
    if config is not None:
        (tmp_path / ".github").mkdir()
        (tmp_path / ".github/repo-infra.json").write_text(json.dumps(config))
    return Detection.load(ASSETS / "detection.json").detect(tmp_path)


def ci_jobs(files):
    return yaml.safe_load(files[".github/workflows/ci.yml"])["jobs"]


def test_ci_local_renders_the_seam_job_and_requires_it(tmp_path):
    files = render_all(ASSETS, rust_repo(tmp_path), MANIFEST, ci_local=True)
    jobs = ci_jobs(files)
    assert jobs["ci-local"] == {"uses": "./.github/workflows/ci-local.yml"}
    assert jobs["ci-passed"]["needs"][-1] == "ci-local"


def test_without_the_key_there_is_no_seam(tmp_path):
    jobs = ci_jobs(render_all(ASSETS, rust_repo(tmp_path), MANIFEST))
    assert "ci-local" not in jobs


def test_the_seam_cannot_be_named_as_an_ordinary_add_on(tmp_path):
    with pytest.raises(AssemblyError, match='"ci_local": true'):
        render_all(ASSETS, rust_repo(tmp_path), MANIFEST, ci=["ci-local"])


def test_a_missing_ci_local_workflow_is_a_conflict(tmp_path):
    result = rust_repo(tmp_path)
    items = classify_contracts(tmp_path, result, {"ci_local": True})
    assert [(i.name, i.state) for i in items] == [("ci-local-workflow", "conflict")]
    assert ".github/workflows/ci-local.yml" in items[0].detail


def test_a_present_ci_local_workflow_reports_nothing(tmp_path):
    result = rust_repo(tmp_path)
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/ci-local.yml").write_text("on: [workflow_call]\n")
    assert classify_contracts(tmp_path, result, {"ci_local": True}) == []


def test_load_reads_ci_local_from_the_config(tmp_path):
    rust_repo(tmp_path, {"ci_local": True})
    _manifest, _result, rendered = cli._load(tmp_path)
    assert "ci-local" in ci_jobs(rendered)
