"""release-pr (D28, D33): prepare and finish are pieces; the caller wires the
repository's own build and CI between them."""

import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CALLER = ROOT / "skills/repo-infra/assets/callers/release-pr.yml"
PREPARE = ROOT / ".github/workflows/ri-release-prepare.yml"
FINISH_PIECE = ROOT / ".github/workflows/ri-release-finish.yml"
FINISH = "Commit the release files, draft the release, open the pull request"
OWN = ROOT / ".github/workflows/release-pr.yml"
MTUSPY = ROOT / "skills/repo-infra/references/examples/mtuspy/release-pr.yml"
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
        "contents": "write", "pull-requests": "write", "statuses": "write", "checks": "write",
        "actions": "write"}


def test_finish_may_delete_the_runs_github_parks_on_its_pull_request():
    """#58: finish deletes the parked runs of the pull request it opens, which
    is `actions: write` on the piece and on every caller's finish job."""
    assert load(FINISH_PIECE)["permissions"]["actions"] == "write"
    for path in (CALLER, OWN, MTUSPY):
        assert load(path)["jobs"]["finish"]["permissions"]["actions"] == "write", path


def test_finish_deletes_the_parked_runs_of_its_head_after_the_required_checks():
    s = script(FINISH_PIECE, "finish", FINISH)
    assert s.index("pulls.create") < s.index("name: 'ci-passed'") \
        < s.index("unparkLib.deleteParkedRuns(github, {") \
        < s.index("verdict.conclusion !== 'success'")
    assert "branch, headSha: head," in s
    assert "timeoutMs: 60 * 1000" in s


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
    for guard in ("refusedReleaseFiles", "undeclaredReleaseFiles", "decodeText", "missingAssets",
                  "collidingAssets"):
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




def test_repo_infra_gates_its_release_on_mtuspy():
    jobs = load(OWN)["jobs"]
    assert list(jobs) == ["prepare", "build", "test", "gate", "finish"]
    assert jobs["gate"]["needs"] == "prepare"
    assert jobs["gate"]["permissions"] == {"contents": "write", "actions": "write"}
    assert jobs["finish"]["needs"] == ["prepare", "build", "test", "gate"]
    # contents: write must not stay in the checkout's git config.
    assert jobs["gate"]["steps"][0]["with"]["persist-credentials"] is False
    step = jobs["gate"]["steps"][-1]
    assert step["env"] == {"HEAD_SHA": "${{ needs.prepare.outputs.head }}",
                           "VERSION": "${{ needs.prepare.outputs.version }}"}
    script = step["with"]["script"]
    assert "workflow: 'gate-mtuspy.yml'" in script
    assert "head: process.env.HEAD_SHA, version: process.env.VERSION" in script
    assert "${{" not in script


def test_no_other_job_of_the_release_flow_may_write_actions():
    caller_jobs = caller()["jobs"]
    assert all(job["permissions"].get("actions") != "write"
               for job_id, job in caller_jobs.items() if job_id not in ("prepare", "finish"))
    own_jobs = load(OWN)["jobs"]
    assert all(job["permissions"].get("actions") != "write"
               for job_id, job in own_jobs.items()
               if job_id not in ("prepare", "gate", "finish"))


# --- D40: the release pull request in fragment mode -------------------------

COMMIT = "Commit the release branch"
COMPUTE = "Compute the version and rewrite the files"
VERSION_FILE = {"path": "VERSION", "pattern": "^version = .*$",
                "replacement": "version = $VERSION", "verify": "^version = $VERSION"}
NOTE_HEADER = "# Changes\n\nChangelog fragments: `CHANGES.d/`\n\n"
RELEASED = "## 1.1.0 - 2026-01-01\n\n### Fixed\n\n- old\n"
ALPHA = "CHANGES.d/new/20261120-1000-abcd-alpha.md"
BETA = "CHANGES.d/fixed/20261121-0900-beef-beta.md"
FRAGMENTS = {ALPHA: "- alpha\n", BETA: "- beta one\n  continued\n\n- beta two\n",
             "CHANGES.d/README.md": "How to write a fragment.\n"}
FINISH_ENV = {"VERSION": "1.2.0", "DATE": "2026-11-26", "HEAD": "h", "BASE": "b"}


def step_env(path, job, step_name):
    """The step's env that reads prepare's step outputs, as variable -> output name."""
    steps = load(path)["jobs"][job]["steps"]
    env = next(s for s in steps if s.get("name") == step_name).get("env", {})
    return {k: re.fullmatch(r"\$\{\{ steps\.prepare\.outputs\.(\w+) \}\}", v).group(1)
            for k, v in env.items() if v.startswith("${{ steps.")}


def workspace(tmp_path, files):
    ws = tmp_path / "ws"
    shutil.copytree(ROOT / ".github/workflows/lib", ws / ".repo-infra/.github/workflows/lib")
    for rel, text in files.items():
        (ws / rel).parent.mkdir(parents=True, exist_ok=True)
        (ws / rel).write_text(text, encoding="utf-8")
    return ws


def run_node(tmp_path, ws, harness, env):
    node = shutil.which("node")
    if node is None:
        # A CI job exists to run these; skipping there would hide the check.
        if os.environ.get("CI"):
            pytest.fail("node is not installed (CI is set, so this test must run, not skip)")
        pytest.skip("node is not installed")
    path = tmp_path / "harness.js"
    path.write_text(harness, encoding="utf-8")
    runner = tmp_path / "runner"
    runner.mkdir(exist_ok=True)
    proc = subprocess.run([node, str(path)], capture_output=True, text=True, cwd=ws,
                          env={"GITHUB_WORKSPACE": str(ws), "RUNNER_TEMP": str(runner),
                               "PATH": os.environ["PATH"], **env})
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def prepare(tmp_path, files):
    """Runs prepare's compute and commit steps on a workspace; returns the
    failures, the step outputs and the trees and blobs the commit wrote."""
    ws = workspace(tmp_path, {
        ".github/repo-infra.json": json.dumps({"version_files": [VERSION_FILE]}),
        "VERSION": "version = 1.1.0\n", **files})
    harness = """
const commitEnv = %s;
const failures = []; const outputs = {}; const trees = []; const blobs = {};
const github = {
  paginate: async (fn, params) => (await fn(params)).data,
  rest: { git: {
    listMatchingRefs: async () => ({ data: [{ ref: 'refs/tags/v1.1.0' }] }),
    getCommit: async () => ({ data: { tree: { sha: 'base-tree' } } }),
    getTree: async () => ({ data: { tree: [] } }),
    createBlob: async ({ content }) => {
      const sha = `blob${Object.keys(blobs).length}`;
      blobs[sha] = content;
      return { data: { sha } }; },
    createTree: async ({ tree }) => { trees.push(tree); return { data: { sha: 'new-tree' } }; },
    createCommit: async () => ({ data: { sha: 'new-commit' } }),
    createRef: async () => ({}),
  } },
};
const core = { setFailed: (m) => failures.push(m), notice: () => {}, warning: () => {},
  setOutput: (k, v) => { outputs[k] = v; } };
const context = { repo: { owner: 'o', repo: 'r' }, sha: 'dispatched' };
(async () => {
  await (async () => {
%s
  })();
  if (failures.length > 0) return;
  for (const [name, output] of Object.entries(commitEnv)) process.env[name] = outputs[output];
  await (async () => {
%s
  })();
})().then(() => console.log(JSON.stringify({ failures, outputs, trees, blobs })));
""" % (json.dumps(step_env(PREPARE, "prepare", COMMIT)),
       script(PREPARE, "prepare", COMPUTE), script(PREPARE, "prepare", COMMIT))
    return run_node(tmp_path, ws, harness, {"RELEASE_TYPE": "feature"})


def written(out, path):
    entry = next(e for e in out["trees"][0] if e["path"] == path)
    return out["blobs"][entry["sha"]]


def test_prepare_rolls_the_fragments_and_deletes_them_in_the_release_commit(tmp_path):
    out = prepare(tmp_path, {"CHANGES.md": NOTE_HEADER + RELEASED, **FRAGMENTS})
    assert out["failures"] == []
    date = out["outputs"]["date"]
    assert written(out, "CHANGES.md") == NOTE_HEADER + (
        f"## 1.2.0 - {date}\n\n### New\n\n- alpha\n\n"
        "### Fixed\n\n- beta one\n  continued\n- beta two\n\n") + RELEASED
    assert written(out, "VERSION") == "version = 1.2.0\n"
    assert json.loads(out["outputs"]["deletions"]) == [ALPHA, BETA]
    # README.md at the top of the directory stays.
    deleted = [e for e in out["trees"][0] if e["sha"] is None]
    assert deleted == [{"path": p, "mode": "100644", "type": "blob", "sha": None}
                       for p in (ALPHA, BETA)]


def test_prepare_refuses_a_file_under_a_section_directory_that_is_no_fragment(tmp_path):
    out = prepare(tmp_path, {"CHANGES.md": NOTE_HEADER + RELEASED, **FRAGMENTS,
                             "CHANGES.d/new/notes.md": "- stray\n",
                             "CHANGES.d/fixed/sub/20261121-0900-beef-x.md": "- deep\n"})
    assert len(out["failures"]) == 1 and out["trees"] == []
    failure = out["failures"][0]
    assert failure.startswith("The release cannot roll these files under CHANGES.d/: ")
    assert "CHANGES.d/new/notes.md: 'notes.md' does not match" in failure
    assert "CHANGES.d/fixed/sub/20261121-0900-beef-x.md: " in failure


def test_prepare_in_classic_mode_deletes_nothing(tmp_path):
    out = prepare(tmp_path, {"CHANGES.md": "# Changes\n\n## [Unreleased]\n\n### New\n\n- x\n\n"
                             + RELEASED})
    assert out["failures"] == []
    assert out["outputs"]["deletions"] == "[]"
    assert sorted(e["path"] for e in out["trees"][0]) == ["CHANGES.md", "VERSION"]
    assert all(e["sha"] is not None for e in out["trees"][0])


def finish(tmp_path, changes, rolled):
    """Runs finish up to the pull request, which the fake API refuses as the
    Actions setting does, so the run ends there; returns the failures, the
    checks written and the body of the pull request."""
    ws = workspace(tmp_path, {
        ".github/repo-infra.json": json.dumps({"version_files": [VERSION_FILE]}),
        "CHANGES.md": changes})
    harness = """
const rolled = %s;
const failures = []; const checks = []; const bodies = [];
const github = {
  paginate: async (fn, params) => (await fn(params)).data,
  rest: { repos: {
    listReleases: async () => ({ data: [] }),
    getContent: async ({ path, ref }) => {
      if (path !== 'CHANGES.md' || ref !== 'h') throw new Error(`${path}@${ref}`);
      return { data: { content: Buffer.from(rolled).toString('base64') } }; },
    createRelease: async () => ({ data: { id: 7 } }),
    uploadReleaseAsset: async () => ({}),
    createCommitStatus: async () => ({}),
  }, checks: {
    create: async (params) => { checks.push(params); return {}; },
  }, pulls: {
    create: async ({ body }) => {
      bodies.push(body);
      const e = new Error('GitHub Actions is not permitted to create or approve pull requests.');
      e.status = 403;
      throw e; },
  } },
};
const core = { setFailed: (m) => failures.push(m), notice: () => {}, warning: () => {} };
const context = { repo: { owner: 'o', repo: 'r' },
  payload: { repository: { default_branch: 'main' } } };
(async () => {
%s
})().then(() => console.log(JSON.stringify({ failures, checks, bodies })));
""" % (json.dumps(rolled), script(FINISH_PIECE, "finish", FINISH))
    return run_node(tmp_path, ws, harness, FINISH_ENV)


def test_finish_says_how_many_entries_it_collected_from_the_fragments(tmp_path):
    section = ("## 1.2.0 - 2026-11-26\n\n### New\n\n- alpha\n  - nested, part of alpha\n\n"
               "### Fixed\n\n- beta one\n  continued\n- beta two\n\n")
    out = finish(tmp_path, NOTE_HEADER + RELEASED, NOTE_HEADER + section + RELEASED)
    # The refused pull request ends the run there.
    assert len(out["failures"]) == 1 and "may not open pull requests" in out["failures"][0]
    lines = out["bodies"][0].split("\n")
    assert ("- collects 3 entries from `CHANGES.d/` into "
            "`## 1.2.0 - 2026-11-26`") in lines
    assert not any("[Unreleased]" in line for line in lines)
    check = next(c for c in out["checks"] if c["name"] == "changelog-updated")
    assert check["output"] == {
        "title": "v1.2.0 collects 3 entries from CHANGES.d/",
        "summary": "Create release PR collected 3 entries from CHANGES.d/ into this version."}


def test_finish_in_classic_mode_still_says_it_rolled_unreleased(tmp_path):
    classic = "# Changes\n\n## [Unreleased]\n\n### New\n\n- x\n\n" + RELEASED
    rolled = ("# Changes\n\n## [Unreleased]\n\n### New\n\n### Changed\n\n### Fixed\n\n"
              "## 1.2.0 - 2026-11-26\n\n### New\n\n- x\n\n" + RELEASED)
    out = finish(tmp_path, classic, rolled)
    lines = out["bodies"][0].split("\n")
    assert ("- rolls `CHANGES.md` `[Unreleased]` into "
            "`## 1.2.0 - 2026-11-26`") in lines
    check = next(c for c in out["checks"] if c["name"] == "changelog-updated")
    assert check["output"] == {
        "title": "v1.2.0 rolls CHANGES.md",
        "summary": "Create release PR rolled [Unreleased] into this version."}


def test_finish_refuses_a_release_file_under_the_fragment_directory(tmp_path):
    ws = workspace(tmp_path, {
        ".github/repo-infra.json": json.dumps({"version_files": [VERSION_FILE],
                                               "release_files": [ALPHA]}),
        "CHANGES.md": NOTE_HEADER + RELEASED})
    harness = """
const failures = [];
const core = { setFailed: (m) => failures.push(m) };
const context = { repo: { owner: 'o', repo: 'r' } };
const github = null;
(async () => {
%s
})().then(() => console.log(JSON.stringify({ failures })));
""" % script(FINISH_PIECE, "finish", FINISH)
    out = run_node(tmp_path, ws, harness, FINISH_ENV)
    assert out["failures"] == [f"release_files in .github/repo-infra.json: {ALPHA} is under "
                               "CHANGES.d/, which the release pull request rolls"]


def test_prepare_refuses_a_symbolic_link_in_a_section_directory(tmp_path):
    ws = workspace(tmp_path, {
        ".github/repo-infra.json": json.dumps({"version_files": [VERSION_FILE]}),
        "VERSION": "version = 1.1.0\n", "CHANGES.md": NOTE_HEADER + RELEASED, **FRAGMENTS,
        "elsewhere/secret.md": "- not a fragment\n"})
    (ws / "CHANGES.d/new/20261122-1000-cafe-link.md").symlink_to(ws / "elsewhere/secret.md")
    (ws / "CHANGES.d/changed").symlink_to(ws / "elsewhere")
    harness = """
const failures = []; const outputs = {};
const core = { setFailed: (m) => failures.push(m), notice: () => {}, warning: () => {},
  setOutput: (k, v) => { outputs[k] = v; } };
const context = { repo: { owner: 'o', repo: 'r' }, sha: 'dispatched' };
const github = {
  paginate: async (fn, params) => (await fn(params)).data,
  rest: { git: { listMatchingRefs: async () => ({ data: [{ ref: 'refs/tags/v1.1.0' }] }) } },
};
(async () => {
%s
})().then(() => console.log(JSON.stringify({ failures, outputs })));
""" % script(PREPARE, "prepare", COMPUTE)
    out = run_node(tmp_path, ws, harness, {"RELEASE_TYPE": "feature"})
    assert out["outputs"] == {}
    assert len(out["failures"]) == 1
    assert ("CHANGES.d/changed: is a symbolic link; "
            "CHANGES.d/new/20261122-1000-cafe-link.md: is a symbolic link") in out["failures"][0]


def test_finish_runs_on_after_the_pull_request_is_opened(tmp_path):
    """The steps after pulls.create: the staleness check, the parked runs, the summary."""
    section = "## 1.2.0 - 2026-11-26\n\n### New\n\n- alpha\n\n"
    ws = workspace(tmp_path, {
        ".github/repo-infra.json": json.dumps({"version_files": [VERSION_FILE]}),
        "CHANGES.md": NOTE_HEADER + RELEASED})
    harness = """
const rolled = %s;
const failures = []; const checks = []; const calls = []; const summary = [];
const github = {
  paginate: async (fn, params) => (await fn(params)).data,
  rest: { repos: {
    listReleases: async () => ({ data: [] }),
    getContent: async () => ({ data: { content: Buffer.from(rolled).toString('base64') } }),
    createRelease: async () => ({ data: { id: 7 } }),
    uploadReleaseAsset: async () => ({}),
    createCommitStatus: async () => ({}),
    compareCommitsWithBasehead: async ({ basehead }) => {
      calls.push(['compare', basehead]); return { data: { behind_by: 0 } }; },
  }, checks: {
    create: async (params) => { checks.push(params.name + ':' + params.conclusion); return {}; },
  }, pulls: {
    create: async () => { calls.push(['pulls.create']); return { data: { html_url: 'https://pr' } }; },
  }, actions: {
    listWorkflowRunsForRepo: async () => { calls.push(['list-parked']); return { data: [] }; },
  } },
};
// The parked-run poll waits up to a minute; run it on a clock that jumps.
let clock = 0;
Date.now = () => clock;
setTimeout = (fn, ms) => { clock += ms; fn(); };
const core = { setFailed: (m) => failures.push(m), notice: () => {}, warning: () => {},
  summary: { addHeading(h) { summary.push(h); return this; },
    addLink(text, url) { summary.push(url); return this; }, write: async () => {} } };
const context = { repo: { owner: 'o', repo: 'r' },
  payload: { repository: { default_branch: 'main' } } };
(async () => {
%s
})().then(() => console.log(JSON.stringify({ failures, checks, calls, summary })));
""" % (json.dumps(NOTE_HEADER + section + RELEASED), script(FINISH_PIECE, "finish", FINISH))
    out = run_node(tmp_path, ws, harness, FINISH_ENV)
    assert out["failures"] == []
    assert out["checks"] == ["changelog-updated:success", "ci-passed:success"]
    names = [c[0] for c in out["calls"]]
    assert names[:2] == ["pulls.create", "compare"]
    assert "list-parked" in names
    assert out["summary"] == ["Release v1.2.0 built and tested", "https://pr"]


def test_publish_words_its_abandon_hint_from_the_fragment_note(tmp_path):
    """A draft with no build record and no tag: the failure says how to abandon."""
    ws = workspace(tmp_path, {
        ".github/repo-infra.json": json.dumps({"version_files": [VERSION_FILE]}),
        "VERSION": "version = 1.2.0\n",
        "CHANGES.md": NOTE_HEADER + "## 1.2.0 - 2026-11-26\n\n### New\n\n- alpha\n"})
    harness = """
const failures = [];
const github = {
  paginate: async (fn, params) => (await fn(params)).data,
  rest: { git: { getRef: async () => { const e = new Error('none'); e.status = 404; throw e; } },
    repos: { listReleases: async () => ({ data: [
      { id: 1, draft: true, tag_name: 'v1.2.0', assets: [] }] }) } },
};
const core = { setFailed: (m) => failures.push(m), notice: () => {}, warning: () => {},
  setOutput: () => {} };
const context = { repo: { owner: 'o', repo: 'r' } };
(async () => {
%s
})().then(() => console.log(JSON.stringify({ failures })));
""" % script(ROOT / ".github/workflows/ri-publish-tag.yml", "publish",
             "Tag and create the draft release")
    out = run_node(tmp_path, ws, harness, {})
    assert len(out["failures"]) == 1
    assert ("or abandon the release: merge a pull request that removes the `## 1.2.0` "
            "section from CHANGES.md and restores its fragments under `CHANGES.d/`."
            ) in out["failures"][0]
    assert "[Unreleased]" not in out["failures"][0]
