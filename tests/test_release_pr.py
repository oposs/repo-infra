"""release-pr v5 (D28): one release flow, built and tested before the merge."""

import pathlib

import yaml

from repo_infra.markers import parse_markers

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
ASSET = ASSETS / "pieces/release-pr/release-pr.yml"


def workflow():
    return yaml.safe_load(ASSET.read_text(encoding="utf-8"))


def script(job, step_name):
    steps = workflow()["jobs"][job]["steps"]
    return next(s["with"]["script"] for s in steps if s.get("name") == step_name)


FINISH = "Commit the release files, draft the release, open the pull request"
REFUSE = "Refuse an open or unpublished release; delete stale drafts and parked runs"


def test_four_jobs_build_and_test_beside_each_other():
    jobs = workflow()["jobs"]
    assert list(jobs) == ["prepare", "build", "test", "finish"]
    assert jobs["build"]["needs"] == "prepare" and jobs["test"]["needs"] == "prepare"
    assert jobs["finish"]["needs"] == ["prepare", "build", "test"]


def test_build_calls_the_assembled_release_build_with_the_secrets():
    build = workflow()["jobs"]["build"]
    assert build["uses"] == "./.github/workflows/release-build.yml"
    assert build["permissions"] == {"contents": "read"}
    assert build["secrets"] == "inherit"
    assert build["with"] == {"version": "${{ needs.prepare.outputs.version }}",
                             "ref": "${{ needs.prepare.outputs.head }}"}


def test_test_calls_ci_yml_on_the_release_branch_with_the_union_of_permissions():
    test = workflow()["jobs"]["test"]
    assert test["uses"] == "./.github/workflows/ci.yml"
    assert test["with"] == {"ref": "${{ needs.prepare.outputs.head }}"}
    assert test["secrets"] == "inherit"
    assert test["permissions"] == {"contents": "read", "pull-requests": "read",
                                   "statuses": "read", "checks": "write"}


def test_permissions_per_job():
    wf = workflow()
    # Every job grants its own; a write at workflow level would be dead.
    assert wf["permissions"] == {"checks": "read", "actions": "read"}
    assert all("permissions" in job for job in wf["jobs"].values())
    assert wf["jobs"]["prepare"]["permissions"]["actions"] == "write"
    assert wf["jobs"]["finish"]["permissions"] == {
        "contents": "write", "pull-requests": "write", "statuses": "write", "checks": "write"}


def test_prepare_outputs_the_dispatched_main_commit_as_base():
    outputs = workflow()["jobs"]["prepare"]["outputs"]
    assert outputs["base"] == "${{ steps.commit.outputs.base }}"
    assert "core.setOutput('base', context.sha)" in script("prepare", "Commit the release branch")


def test_the_guard_does_not_wait():
    guard = script("prepare", "Guard (right branch, no failed check)")
    assert "checks.guardVerdict(state)" in guard
    for gone in ("waitForChecks", "timedOut", "No checks ran"):
        assert gone not in guard


def test_prepare_refuses_then_cleans_up_before_it_writes_anything():
    steps = [s.get("name") for s in workflow()["jobs"]["prepare"]["steps"]]
    assert steps.index(REFUSE) < steps.index("Compute the version and rewrite the files")
    refuse = script("prepare", REFUSE)
    assert refuse.index("blockingReleasePr") < refuse.index("untaggedMessage") \
        < refuse.index("staleDrafts") < refuse.index("releaseLib.fetchParkedRuns(github, {")
    assert "deleteWorkflowRun" in refuse and "core.warning" in refuse
    # Without a branch: every closed release branch's parked runs, not one.
    assert "releaseLib.fetchParkedRuns(github, { owner, repo })" in refuse
    assert "Re-run the failed jobs" not in refuse


def test_finish_checks_everything_before_it_creates_the_draft():
    s = script("finish", FINISH)
    for guard in ("refusedReleaseFiles", "undeclaredReleaseFiles", "decodeText", "missingAssets"):
        assert s.index(guard) < s.index("createRelease"), guard


def test_finish_records_base_and_head_in_the_build_record():
    assert "{ version, base, head, assets: assetNames }" in script("finish", FINISH)


def test_finish_opens_the_pull_request_before_it_judges_it_against_main():
    s = script("finish", FINISH)
    assert s.index("createRelease") < s.index("'release-built'") \
        < s.index("name: 'changelog-updated'") < s.index("pulls.create") \
        < s.index("compareCommitsWithBasehead") < s.index("finishVerdict") \
        < s.index("name: 'ci-passed'")
    assert "target_commitish: head" in s


def test_finish_downloads_both_artifact_kinds():
    steps = workflow()["jobs"]["finish"]["steps"]
    patterns = [s["with"]["pattern"] for s in steps
                if s.get("uses", "").startswith("actions/download-artifact@")]
    assert patterns == ["release-asset-*", "release-files"]


def test_the_rust_lockfile_note_survives():
    assert "a Rust repository lists Cargo.lock in version_files" in ASSET.read_text(encoding="utf-8")


def test_the_piece_carries_one_marker_naming_itself():
    assert [m.asset for m in parse_markers(ASSET.read_text(encoding="utf-8"))] == ["release-pr"]
