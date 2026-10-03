"""D28: ci.yml as a reusable workflow, ci-passed's release mode, release-pr-current."""

import json
import os
import pathlib
import shutil
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
BOT = "github-actions[bot]"
REF = "${{ inputs.ref }}"
BUILT = [{"context": "release-built", "state": "success", "creator": {"login": BOT}}]
BLURB = ("the release branch changed after it was built (the Update branch button "
         "does this); close this pull request and dispatch Create release PR again")
STALE = ("main moved after v1.2.0 was built; close this pull request and dispatch "
         "Create release PR again")


def on(doc):
    # PyYAML reads the bare key `on` as the boolean True.
    return doc.get("on", doc.get(True))


def ci_passed_job():
    pattern = yaml.safe_load((ASSETS / "callers/ci-passed.yml").read_text(encoding="utf-8"))
    return pattern["jobs"]["ci-passed"]


def release_pr_current_job():
    piece = yaml.safe_load((ASSETS / "pieces/ri-release-pr-current/ri-release-pr-current.yml")
                           .read_text(encoding="utf-8"))
    return piece["jobs"]["release-pr-current"]


def test_ci_passed_raises_only_what_release_mode_reads():
    assert ci_passed_job()["permissions"] == {
        "contents": "read", "pull-requests": "read", "statuses": "read"}


def test_release_pr_current_runs_on_push_only_and_may_write_checks():
    job = release_pr_current_job()
    assert job["if"] == "github.event_name == 'push'"
    assert job["permissions"] == {
        "contents": "read", "pull-requests": "read", "checks": "write"}


def test_release_mode_loads_the_library_from_the_base_commit():
    steps = ci_passed_job()["steps"]
    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@"))
    assert checkout["with"] == {"ref": "${{ github.event.pull_request.base.sha }}",
                                "path": "repo-infra-base"}
    script = next(s for s in steps if s.get("id") == "release")["with"]["script"]
    assert "repo-infra-base/.github/workflows/lib" in script


def test_the_release_mode_steps_run_on_pull_requests_from_release_branches():
    # The harness never evaluates these expressions, so only an exact
    # comparison notices a dropped condition.
    job = ci_passed_job()
    assert job["env"] == {"RELEASE_BRANCH_PR": "${{ github.event_name == 'pull_request' && "
                                               "startsWith(github.head_ref, 'release/') }}"}
    release_steps = [s for s in job["steps"] if "run" not in s]
    assert len(release_steps) == 3
    for step in release_steps:
        assert step["if"] == "env.RELEASE_BRANCH_PR == 'true'"


def test_an_api_error_in_release_mode_fails_the_step(tmp_path):
    # The exception fails the step and with it the job; the failure step
    # after it is skipped (no always()), so ci-passed cannot turn green.
    out = ci_passed(tmp_path, statuses=BUILT, fail_compare=True)
    assert out["thrown"] == "Server Error"
    assert "always()" not in ci_passed_job()["steps"][-1]["if"]


def test_the_failure_step_is_skipped_in_release_mode():
    last = ci_passed_job()["steps"][-1]
    assert last["run"] == "exit 1"
    assert last["if"] == ("steps.release.outputs.mode != 'release' && "
                          "(contains(needs.*.result, 'failure') || "
                          "contains(needs.*.result, 'cancelled'))")


def _node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    return node


def _workspace(tmp_path, base_too=True):
    ws = tmp_path / "ws"
    shutil.copytree(ROOT / ".github/workflows/lib", ws / ".github/workflows/lib")
    if base_too:
        shutil.copytree(ROOT / ".github/workflows/lib",
                        ws / "repo-infra-base/.github/workflows/lib")
    return ws


def _run(tmp_path, ws, script, prelude):
    # An exception that leaves the script fails the github-script step; the
    # harness records it as `thrown`.
    harness = prelude + "\nlet thrown = null;\n(async () => {\n" + script + \
        "\n})().catch((e) => { thrown = e.message; }).then(() => console.log(" \
        "JSON.stringify({ failures, outputs, warnings, notices, created, thrown })));\n"
    path = tmp_path / "harness.js"
    path.write_text(harness, encoding="utf-8")
    proc = subprocess.run([_node(), str(path)], capture_output=True, text=True, cwd=ws,
                          env={"GITHUB_WORKSPACE": str(ws), "PATH": os.environ["PATH"]})
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


PRELUDE = """
const failures = []; const outputs = {}; const warnings = []; const notices = [];
const created = [];
const core = { setFailed: (m) => failures.push(m), setOutput: (k, v) => { outputs[k] = v; },
  warning: (m) => warnings.push(m), notice: (m) => notices.push(m) };
"""


def ci_passed(tmp_path, *, head_ref="release/v1.2.0", login=BOT, head_repo="o/r",
              statuses=(), behind=0, sabotage_merge_lib=False, fail_compare=False):
    """Run ci-passed's release step against a fake API; the D28 verdict table."""
    script = next(s for s in ci_passed_job()["steps"]
                  if s.get("id") == "release")["with"]["script"]
    ws = _workspace(tmp_path)
    if sabotage_merge_lib:
        (ws / ".github/workflows/lib/release.js").write_text("module.exports = {};\n")
    pr = {"number": 7, "user": {"login": login},
          "head": {"ref": head_ref, "sha": "h",
                   "repo": {"full_name": head_repo} if head_repo else None},
          "base": {"ref": "main", "sha": "b"}}
    prelude = PRELUDE + """
const statuses = %s; const failCompare = %s;
const github = {
  paginate: async (fn) => (fn === 'statuses' ? statuses : []),
  rest: { repos: { listCommitStatusesForRef: 'statuses',
    compareCommitsWithBasehead: async ({ basehead }) => {
      if (failCompare) { const e = new Error('Server Error'); e.status = 500; throw e; }
      if (basehead !== 'main...h') throw new Error(`basehead ${basehead}`);
      return { data: { behind_by: %d } }; } } },
};
const context = { repo: { owner: 'o', repo: 'r' }, payload: { pull_request: %s } };
""" % (json.dumps(list(statuses)), "true" if fail_compare else "false", behind, json.dumps(pr))
    return _run(tmp_path, ws, script, prelude)


def test_a_built_current_release_pull_request_passes_ci_passed(tmp_path):
    out = ci_passed(tmp_path, statuses=BUILT)
    assert out["failures"] == [] and out["outputs"] == {"mode": "release"}


def test_a_stale_release_pull_request_fails_ci_passed(tmp_path):
    assert ci_passed(tmp_path, statuses=BUILT, behind=2)["failures"] == [STALE]


def test_an_unbuilt_release_head_fails_ci_passed(tmp_path):
    assert ci_passed(tmp_path)["failures"] == [BLURB]


@pytest.mark.parametrize("case", [{"login": "oetiker"}, {"head_repo": "fork/r"},
                                  {"head_repo": None}])
def test_someone_elses_release_branch_gets_the_ordinary_rules(tmp_path, case):
    out = ci_passed(tmp_path, head_ref="release/x", **case)
    assert out["failures"] == [] and out["outputs"] == {"mode": "ordinary"}


def test_ci_passed_reads_the_library_of_the_base_commit(tmp_path):
    # A release branch that broke its own release.js still gets the base's verdict.
    assert ci_passed(tmp_path, statuses=BUILT, behind=1,
                     sabotage_merge_lib=True)["failures"] == [STALE]


def release_pr_current(tmp_path, prs, behind, fail_compare=(), fail_list=False):
    script = release_pr_current_job()["steps"][-1]["with"]["script"]
    ws = _workspace(tmp_path, base_too=False)
    prelude = PRELUDE + """
const prs = %s; const behind = %s; const failCompare = %s; const failList = %s;
const github = {
  paginate: async (fn, args) => { if (fn !== 'pulls' || args.state !== 'open') throw new Error(fn);
    if (failList) throw new Error('Server Error');
    return prs; },
  rest: {
    pulls: { list: 'pulls' },
    repos: { compareCommitsWithBasehead: async ({ basehead }) => {
      const sha = basehead.split('...')[1];
      if (failCompare.includes(sha)) {
        const e = new Error(`Server Error on ${sha}`); e.status = 500; throw e;
      }
      return { data: { behind_by: behind[sha] } }; } },
    checks: { create: async (a) => { created.push(a); return { data: {} }; } },
  },
};
const context = { repo: { owner: 'o', repo: 'r' } };
""" % (json.dumps(prs), json.dumps(behind), json.dumps(list(fail_compare)),
       "true" if fail_list else "false")
    return _run(tmp_path, ws, script, prelude)


def _pr(number, ref, sha, login=BOT, repo="o/r"):
    return {"number": number, "user": {"login": login}, "base": {"ref": "main"},
            "head": {"ref": ref, "sha": sha, "repo": {"full_name": repo}}}


def test_release_pr_current_marks_only_the_stale_release_pull_request(tmp_path):
    prs = [_pr(1, "release/v1.2.0", "s1"), _pr(2, "release/v1.3.0", "s2"),
           _pr(3, "release/x", "s3", login="oetiker"), _pr(4, "fix/x", "s4")]
    out = release_pr_current(tmp_path, prs, {"s1": 1, "s2": 0, "s3": 9, "s4": 9})
    assert out["created"] == [{
        "owner": "o", "repo": "r", "name": "ci-passed", "head_sha": "s1",
        "status": "completed", "conclusion": "failure",
        "output": {"title": "main moved after v1.2.0 was built", "summary": STALE}}]
    assert out["failures"] == []


def test_release_pr_current_never_fails_on_an_api_error(tmp_path):
    out = release_pr_current(tmp_path, [_pr(1, "release/v1.2.0", "s1")], {}, fail_list=True)
    assert out["failures"] == [] and out["created"] == [] and out["thrown"] is None
    assert len(out["warnings"]) == 1 and "Server Error" in out["warnings"][0]


def test_an_error_on_one_release_pull_request_leaves_the_others_marked(tmp_path):
    prs = [_pr(1, "release/v1.2.0", "s1"), _pr(2, "release/v1.3.0", "s2")]
    out = release_pr_current(tmp_path, prs, {"s2": 1}, fail_compare=["s1"])
    assert [c["head_sha"] for c in out["created"]] == ["s2"]
    assert out["failures"] == [] and out["thrown"] is None
    assert len(out["warnings"]) == 1 and "#1" in out["warnings"][0]
