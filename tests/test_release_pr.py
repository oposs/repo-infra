"""release-pr (D28, D33): prepare and finish are pieces; the caller wires the
repository's own build and CI between them."""

import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CALLER = ROOT / "skills/repo-infra/assets/callers/release-pr.yml"
PREPARE = ROOT / ".github/workflows/ri-release-prepare.yml"
FINISH_PIECE = ROOT / ".github/workflows/ri-release-finish.yml"
FINISH = "Commit the release files, draft the release, open the pull request"
REFUSE = "Refuse an open or unpublished release; delete stale drafts and parked runs"


def load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def caller():
    return load(CALLER)


def script(path, job, step_name):
    steps = load(path)["jobs"][job]["steps"]
    return next(s["with"]["script"] for s in steps if s.get("name") == step_name)


def test_the_caller_wires_four_jobs():
    jobs = caller()["jobs"]
    assert list(jobs) == ["prepare", "build", "test", "finish"]
    assert jobs["prepare"]["uses"] == (
        "oposs/repo-infra/.github/workflows/ri-release-prepare.yml@v2")
    assert jobs["finish"]["uses"] == (
        "oposs/repo-infra/.github/workflows/ri-release-finish.yml@v2")
    assert jobs["build"]["needs"] == "prepare" and jobs["test"]["needs"] == "prepare"
    assert jobs["finish"]["needs"] == ["prepare", "build", "test"]


def test_only_the_repositorys_own_workflows_inherit_secrets():
    jobs = caller()["jobs"]
    assert jobs["build"]["secrets"] == "inherit" and jobs["test"]["secrets"] == "inherit"
    assert "secrets" not in jobs["prepare"] and "secrets" not in jobs["finish"]


def test_the_caller_passes_prepares_outputs():
    jobs = caller()["jobs"]
    assert jobs["prepare"]["with"] == {"release_type": "${{ inputs.release_type }}"}
    assert jobs["build"]["with"] == {"version": "${{ needs.prepare.outputs.version }}",
                                     "ref": "${{ needs.prepare.outputs.head }}"}
    assert jobs["finish"]["with"] == {
        key: f"${{{{ needs.prepare.outputs.{key} }}}}"
        for key in ("version", "date", "head", "base")}


def test_permissions_per_job():
    wf = caller()
    assert wf["permissions"] == {"checks": "read", "actions": "read"}
    assert wf["jobs"]["prepare"]["permissions"] == {
        "contents": "write", "pull-requests": "read", "checks": "read", "actions": "write"}
    assert wf["jobs"]["build"]["permissions"] == {"contents": "read"}
    assert wf["jobs"]["test"]["permissions"] == {
        "contents": "read", "pull-requests": "read", "statuses": "read", "checks": "write"}
    assert wf["jobs"]["finish"]["permissions"] == {
        "contents": "write", "pull-requests": "write", "statuses": "write", "checks": "write"}


def test_prepare_takes_the_release_type_through_env():
    s = script(PREPARE, "prepare", "Compute the version and rewrite the files")
    assert "process.env.RELEASE_TYPE" in s
    assert "context.payload.inputs" not in s


def test_prepare_outputs_the_dispatched_main_commit_as_base():
    outputs = load(PREPARE)["jobs"]["prepare"]["outputs"]
    assert outputs["base"] == "${{ steps.commit.outputs.base }}"
    assert "core.setOutput('base', context.sha)" in script(
        PREPARE, "prepare", "Commit the release branch")


def test_finish_reads_its_inputs_through_env():
    s = script(FINISH_PIECE, "finish", FINISH)
    for name in ("VERSION", "DATE", "HEAD", "BASE"):
        assert f"process.env.{name}" in s
    assert "needs.prepare" not in s and "${{" not in s


def test_the_guard_does_not_wait():
    guard = script(PREPARE, "prepare", "Guard (right branch, no failed check)")
    assert "checks.guardVerdict(state)" in guard
    for gone in ("waitForChecks", "timedOut", "No checks ran"):
        assert gone not in guard


def test_prepare_refuses_then_cleans_up_before_it_writes_anything():
    steps = [s.get("name") for s in load(PREPARE)["jobs"]["prepare"]["steps"]]
    assert steps.index(REFUSE) < steps.index("Compute the version and rewrite the files")
    refuse = script(PREPARE, "prepare", REFUSE)
    assert refuse.index("blockingReleasePr") < refuse.index("untaggedMessage") \
        < refuse.index("staleDrafts") < refuse.index("releaseLib.fetchParkedRuns(github, {")
    assert "deleteWorkflowRun" in refuse and "core.warning" in refuse
    # Without a branch: every closed release branch's parked runs, not one.
    assert "releaseLib.fetchParkedRuns(github, { owner, repo })" in refuse
    assert "Re-run the failed jobs" not in refuse


def test_finish_checks_everything_before_it_creates_the_draft():
    s = script(FINISH_PIECE, "finish", FINISH)
    for guard in ("refusedReleaseFiles", "undeclaredReleaseFiles", "decodeText", "missingAssets"):
        assert s.index(guard) < s.index("createRelease"), guard


def test_finish_records_base_and_head_in_the_build_record():
    assert "{ version, base, head, assets: assetNames }" in script(FINISH_PIECE, "finish", FINISH)


def test_finish_opens_the_pull_request_before_it_judges_it_against_main():
    s = script(FINISH_PIECE, "finish", FINISH)
    assert s.index("createRelease") < s.index("'release-built'") \
        < s.index("name: 'changelog-updated'") < s.index("pulls.create") \
        < s.index("compareCommitsWithBasehead") < s.index("finishVerdict") \
        < s.index("name: 'ci-passed'")
    assert "target_commitish: head" in s


def test_finish_downloads_both_artifact_kinds():
    steps = load(FINISH_PIECE)["jobs"]["finish"]["steps"]
    patterns = [s["with"]["pattern"] for s in steps
                if s.get("uses", "").startswith("actions/download-artifact@")]
    assert patterns == ["release-asset-*", "release-files"]


def test_the_rust_lockfile_note_survives():
    assert "a Rust repository lists Cargo.lock in version_files" in PREPARE.read_text(
        encoding="utf-8")


OWN = ROOT / ".github/workflows/release-pr.yml"


def test_repo_infra_gates_its_release_on_mtuspy():
    jobs = load(OWN)["jobs"]
    assert list(jobs) == ["prepare", "build", "test", "gate", "finish"]
    assert jobs["gate"]["needs"] == "prepare"
    assert jobs["gate"]["permissions"] == {"contents": "read", "actions": "write"}
    assert jobs["finish"]["needs"] == ["prepare", "build", "test", "gate"]
    script = jobs["gate"]["steps"][-1]["with"]["script"]
    assert "workflow: 'gate-mtuspy.yml'" in script and "process.env.BRANCH" in script


def test_no_other_job_of_the_release_flow_may_write_actions():
    caller_jobs = caller()["jobs"]
    assert all(job["permissions"].get("actions") != "write"
               for job_id, job in caller_jobs.items() if job_id != "prepare")
    own_jobs = load(OWN)["jobs"]
    assert all(job["permissions"].get("actions") != "write"
               for job_id, job in own_jobs.items() if job_id not in ("prepare", "gate"))
