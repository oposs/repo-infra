"""D28: ci.yml as a reusable workflow, ci-passed's release mode, release-pr-current."""

import json
import os
import pathlib
import shutil
import subprocess

import pytest
import yaml

from repo_infra.assemble import assemble_ci, render_all
from repo_infra.detect import Detection

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
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


def ci_jobs(blocks=()):
    return yaml.safe_load(assemble_ci(ASSETS, list(blocks), MANIFEST))["jobs"]


def test_ci_yml_is_also_a_reusable_workflow_with_an_optional_ref():
    doc = yaml.safe_load(assemble_ci(ASSETS, [], MANIFEST))
    assert on(doc)["workflow_call"] == {
        "inputs": {"ref": {"type": "string", "required": False, "default": ""}}}
    assert set(on(doc)) == {"push", "pull_request", "workflow_call"}
    assert doc["permissions"] == {"contents": "read"}


@pytest.mark.parametrize("block", sorted(MANIFEST["ci_blocks"]))
def test_every_ci_fragment_checks_out_the_called_ref(block):
    jobs = yaml.safe_load((ASSETS / "ci" / (block + ".yml")).read_text(encoding="utf-8"))
    for job_id, job in jobs.items():
        for step in job.get("steps", []):
            if str(step.get("uses", "")).startswith("actions/checkout@"):
                assert (step.get("with") or {}).get("ref") == REF, "%s: %s" % (block, job_id)


def test_every_called_workflow_gets_ref_and_secrets(tmp_path):
    (tmp_path / "action.yml").write_text("name: x\n")
    result = Detection.load(ASSETS / "detection.json").detect(tmp_path)
    jobs = yaml.safe_load(render_all(ASSETS, result, MANIFEST, ci_local=True)[
        ".github/workflows/ci.yml"])["jobs"]
    called = {k: j for k, j in jobs.items() if str(j.get("uses", "")).startswith("./")}
    assert sorted(called) == ["action-test", "ci-local"]
    for job in called.values():
        assert job["with"] == {"ref": REF}
        assert job["secrets"] == "inherit"


def test_ci_passed_raises_only_what_release_mode_reads():
    assert ci_jobs()["ci-passed"]["permissions"] == {
        "contents": "read", "pull-requests": "read", "statuses": "read"}


def test_release_pr_current_runs_on_push_only_and_may_write_checks():
    job = ci_jobs()["release-pr-current"]
    assert job["if"] == "github.event_name == 'push'"
    assert job["permissions"] == {
        "contents": "read", "pull-requests": "read", "checks": "write"}
    assert "release-pr-current" not in ci_jobs()["ci-passed"]["needs"]


def test_release_mode_loads_the_library_from_the_base_commit():
    steps = ci_jobs()["ci-passed"]["steps"]
    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@"))
    assert checkout["with"] == {"ref": "${{ github.event.pull_request.base.sha }}",
                                "path": "repo-infra-base"}
    script = next(s for s in steps if s.get("id") == "release")["with"]["script"]
    assert "repo-infra-base/.github/workflows/lib" in script


def test_the_failure_step_is_skipped_in_release_mode():
    last = ci_jobs()["ci-passed"]["steps"][-1]
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
    harness = prelude + "\n(async () => {\n" + script + "\n})().then(() => console.log(" \
        "JSON.stringify({ failures, outputs, warnings, notices, created })));\n"
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
              statuses=(), behind=0, sabotage_merge_lib=False):
    """Run ci-passed's release step against a fake API; the D28 verdict table."""
    script = next(s for s in ci_jobs()["ci-passed"]["steps"]
                  if s.get("id") == "release")["with"]["script"]
    ws = _workspace(tmp_path)
    if sabotage_merge_lib:
        (ws / ".github/workflows/lib/release.js").write_text("module.exports = {};\n")
    pr = {"number": 7, "user": {"login": login},
          "head": {"ref": head_ref, "sha": "h",
                   "repo": {"full_name": head_repo} if head_repo else None},
          "base": {"ref": "main", "sha": "b"}}
    prelude = PRELUDE + """
const statuses = %s;
const github = {
  paginate: async (fn) => (fn === 'statuses' ? statuses : []),
  rest: { repos: { listCommitStatusesForRef: 'statuses',
    compareCommitsWithBasehead: async ({ basehead }) => {
      if (basehead !== 'main...h') throw new Error(`basehead ${basehead}`);
      return { data: { behind_by: %d } }; } } },
};
const context = { repo: { owner: 'o', repo: 'r' }, payload: { pull_request: %s } };
""" % (json.dumps(list(statuses)), behind, json.dumps(pr))
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


def release_pr_current(tmp_path, prs, behind, fail_compare=False):
    script = ci_jobs()["release-pr-current"]["steps"][-1]["with"]["script"]
    ws = _workspace(tmp_path, base_too=False)
    prelude = PRELUDE + """
const prs = %s; const behind = %s; const failCompare = %s;
const github = {
  paginate: async (fn, args) => { if (fn !== 'pulls' || args.state !== 'open') throw new Error(fn);
    return prs; },
  rest: {
    pulls: { list: 'pulls' },
    repos: { compareCommitsWithBasehead: async ({ basehead }) => {
      if (failCompare) { const e = new Error('Server Error'); e.status = 500; throw e; }
      return { data: { behind_by: behind[basehead.split('...')[1]] } }; } },
    checks: { create: async (a) => { created.push(a); return { data: {} }; } },
  },
};
const context = { repo: { owner: 'o', repo: 'r' } };
""" % (json.dumps(prs), json.dumps(behind), "true" if fail_compare else "false")
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
    out = release_pr_current(tmp_path, [_pr(1, "release/v1.2.0", "s1")], {},
                             fail_compare=True)
    assert out["failures"] == [] and out["created"] == []
    assert len(out["warnings"]) == 1 and "Server Error" in out["warnings"][0]
