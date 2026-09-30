"""The release_build variant of the release workflow (D26)."""

import json
import pathlib

import pytest
import yaml

from repo_infra.assemble import AssemblyError, render_all
from repo_infra.detect import Detection
from repo_infra.markers import parse_markers
from repo_infra.state import classify_contracts, refused_release_files

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
TARGET = ".github/workflows/release-pr.yml"
VARIANT = ASSETS / "workflows/release-pr-build.yml"


def result(tmp_path):
    return Detection.load(ASSETS / "detection.json").detect(tmp_path)


def workflow():
    return yaml.safe_load(VARIANT.read_text(encoding="utf-8"))


def script(job, step_name):
    steps = workflow()["jobs"][job]["steps"]
    return next(s["with"]["script"] for s in steps if s.get("name") == step_name)


def test_release_build_selects_the_variant_for_the_same_target(tmp_path):
    files = render_all(ASSETS, result(tmp_path), MANIFEST, release_build=True)
    assert [m.asset for m in parse_markers(files[TARGET])][0] == "release-pr-build"


def test_without_release_build_the_plain_workflow_is_installed(tmp_path):
    files = render_all(ASSETS, result(tmp_path), MANIFEST)
    assert [m.asset for m in parse_markers(files[TARGET])][0] == "release-pr"


def test_an_unknown_when_key_is_an_assembly_error(tmp_path):
    manifest = json.loads(json.dumps(MANIFEST))
    manifest["assets"]["release-pr-build"]["when"] = "no_such_key"
    with pytest.raises(AssemblyError, match="no_such_key"):
        render_all(ASSETS, result(tmp_path), manifest)


def test_three_jobs_and_the_build_is_the_project_seam():
    jobs = workflow()["jobs"]
    assert list(jobs) == ["prepare", "build", "finish"]
    assert jobs["build"]["uses"] == "./.github/workflows/release-build.yml"
    assert jobs["build"]["permissions"] == {"contents": "read"}
    assert "secrets" not in jobs["build"]
    assert jobs["build"]["with"] == {
        "version": "${{ needs.prepare.outputs.version }}",
        "ref": "${{ needs.prepare.outputs.head }}",
    }
    assert jobs["finish"]["needs"] == ["prepare", "build"]


def test_the_guard_is_the_same_text_as_in_release_pr():
    # The two variants differ in job structure only (spec D26).
    plain = yaml.safe_load((ASSETS / "workflows/release-pr.yml").read_text(encoding="utf-8"))
    guard = next(s for s in plain["jobs"]["release-pr"]["steps"]
                 if s.get("name") == "Guard (right branch, green checks)")
    assert script("prepare", "Guard (right branch, green checks)") == guard["with"]["script"]


def test_the_compute_step_is_the_same_text_as_in_release_pr():
    plain = yaml.safe_load((ASSETS / "workflows/release-pr.yml").read_text(encoding="utf-8"))
    compute = next(s for s in plain["jobs"]["release-pr"]["steps"]
                   if s.get("name") == "Compute the version and rewrite the files")
    assert script("prepare", "Compute the version and rewrite the files") == compute["with"]["script"]


def test_prepare_refuses_before_it_writes_anything():
    steps = [s.get("name") for s in workflow()["jobs"]["prepare"]["steps"]]
    assert steps.index("Refuse an open or unpublished release; delete stale drafts") < steps.index(
        "Compute the version and rewrite the files")
    refuse = script("prepare", "Refuse an open or unpublished release; delete stale drafts")
    assert "blockingReleasePr" in refuse
    assert "is in CHANGES.md on main but has no tag" in refuse
    assert "staleDrafts" in refuse


def test_finish_checks_everything_before_it_creates_the_draft():
    s = script("finish", "Commit the release files, draft the release, open the pull request")
    for guard in ("refusedReleaseFiles", "undeclaredReleaseFiles", "decodeText", "missingAssets"):
        assert s.index(guard) < s.index("createRelease"), guard


def test_finish_marks_the_head_before_it_opens_the_pull_request():
    s = script("finish", "Commit the release files, draft the release, open the pull request")
    assert s.index("ownDrafts") < s.index("createRelease")
    assert s.index("createRelease") < s.index("'release-built'") < s.index("pulls.create")
    assert "target_commitish: head" in s


def test_finish_downloads_both_artifact_kinds():
    steps = workflow()["jobs"]["finish"]["steps"]
    patterns = [s["with"]["pattern"] for s in steps
                if s.get("uses", "").startswith("actions/download-artifact@")]
    assert patterns == ["release-asset-*", "release-files"]


def test_the_rust_lockfile_note_survives_in_the_variant():
    # Its absence is what shipped mdmost v0.1.1 with a stale Cargo.lock.
    assert "cargo update --workspace" in VARIANT.read_text(encoding="utf-8")


@pytest.mark.parametrize("entry", [
    "CHANGES.md", "./CHANGES.md", "Formula/../CHANGES.md", "Cargo.toml",
    ".github/repo-infra.json", ".github//workflows/ci.yml", "/etc/passwd", "../x", "",
])
def test_check_refuses_a_release_file_that_reopens_the_channel(entry):
    assert [p for p, _ in refused_release_files([entry], [{"path": "Cargo.toml"}])] == [entry]


def test_check_accepts_the_formula():
    assert refused_release_files(["Formula/mdmost.rb"], [{"path": "Cargo.toml"}]) == []


def test_release_build_without_the_project_build_is_a_conflict(tmp_path):
    items = classify_contracts(tmp_path, result(tmp_path), {"release_build": True})
    assert [(i.name, i.state) for i in items] == [("release-build", "conflict")]


def test_a_refused_release_file_is_a_conflict(tmp_path):
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/release-build.yml").write_text("on: [workflow_call]\n")
    config = {"release_build": True, "release_files": ["./CHANGES.md"], "version_files": []}
    items = classify_contracts(tmp_path, result(tmp_path), config)
    assert [(i.name, i.state) for i in items] == [("release-files", "conflict")]
    assert "./CHANGES.md" in items[0].detail


GITEA_OK = {"url": "https://gitea.example.org", "owner": "acme"}


def gitea_config(tmp_path, **over):
    (tmp_path / ".github/workflows").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".github/workflows/release-build.yml").write_text("on: [workflow_call]\n")
    config = {"publish": ["publish-gitea-packages"], "release_build": True,
              "gitea_packages": GITEA_OK}
    config.update(over)
    return classify_contracts(tmp_path, result(tmp_path), config)


def test_gitea_packages_with_release_build_and_config_is_fine(tmp_path):
    assert gitea_config(tmp_path) == []


def test_gitea_packages_without_release_build_is_a_conflict(tmp_path):
    items = gitea_config(tmp_path, release_build=False)
    assert [(i.name, i.state) for i in items] == [("gitea-packages-build", "conflict")]
    assert "release_build" in items[0].detail


@pytest.mark.parametrize("packages,absent", [
    (None, "url and owner"),
    ({"owner": "acme"}, "url"),
    ({"url": "https://gitea.example.org"}, "owner"),
])
def test_gitea_packages_without_url_or_owner_is_a_conflict(tmp_path, packages, absent):
    config = {"gitea_packages": packages} if packages is not None else {"gitea_packages": None}
    items = gitea_config(tmp_path, **config)
    assert [(i.name, i.state) for i in items] == [("gitea-packages-config", "conflict")]
    assert absent in items[0].detail
