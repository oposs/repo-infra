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


def verdict_job():
    pattern = yaml.safe_load((ASSETS / "callers/ci-passed.yml").read_text(encoding="utf-8"))
    return pattern["jobs"]["release-verdict"]


def verdict_piece():
    return yaml.safe_load((ROOT / ".github/workflows/ri-release-verdict.yml")
                          .read_text(encoding="utf-8"))


def release_pr_current_job():
    piece = yaml.safe_load((ROOT / ".github/workflows/ri-release-pr-current.yml")
                           .read_text(encoding="utf-8"))
    return piece["jobs"]["release-pr-current"]


def test_the_verdict_job_grants_what_the_piece_reads():
    assert verdict_job()["permissions"] == {
        "contents": "read", "pull-requests": "read", "statuses": "read"}
    assert verdict_job()["uses"] == "oposs/repo-infra/.github/workflows/ri-release-verdict.yml@v2"
    assert "if" not in verdict_job()


def test_ci_passed_needs_the_verdict_and_reads_nothing_else():
    job = ci_passed_job()
    assert job["if"] == "always()"
    assert job["needs"] == ["release-verdict"]
    assert job["permissions"] == {"contents": "read"}


def _judge(tmp_path, **env):
    step = ci_passed_job()["steps"][0]
    script = tmp_path / "judge.sh"
    script.write_text(step["run"], encoding="utf-8")
    full = {"PATH": os.environ["PATH"], "VERDICT": "success", "MODE": "ordinary", "OK": "true",
            "MESSAGE": "", "FAILED": "false", **env}
    return subprocess.run(["bash", "-e", str(script)], env=full, capture_output=True, text=True)


@pytest.mark.parametrize("env, passes", [
    ({}, True),
    ({"FAILED": "true"}, False),
    ({"VERDICT": "failure"}, False),
    ({"VERDICT": "skipped"}, False),
    ({"VERDICT": "cancelled"}, False),
    ({"MODE": "release", "OK": "true", "MESSAGE": "v1.2.0 built and current"}, True),
    ({"MODE": "release", "OK": "true", "FAILED": "true"}, True),
    ({"MODE": "release", "OK": "false", "MESSAGE": STALE}, False),
    ({"MODE": "release", "OK": ""}, False),
])
def test_ci_passed_step_table(tmp_path, env, passes):
    proc = _judge(tmp_path, **env)
    assert (proc.returncode == 0) is passes, proc.stdout
    if env.get("OK") == "false":
        assert f"::error::{STALE}" in proc.stdout


def test_release_pr_current_runs_on_push_only_and_may_write_checks():
    job = release_pr_current_job()
    assert job["if"] == "github.event_name == 'push'"
    assert job["permissions"] == {
        "contents": "read", "pull-requests": "read", "checks": "write"}


SKIP_PATH = ASSETS / "callers/release-pr-skip.yml"
SKIP_IF = ("${{ !(github.event_name == 'pull_request' && startsWith(github.head_ref, "
           "'release/') && github.event.pull_request.head.repo.full_name == "
           "github.repository && github.event.pull_request.user.login == "
           "'github-actions[bot]') }}")


def test_the_release_pr_skip_is_exactly_the_release_pull_request():
    # D31. The harness never evaluates expressions either: a dropped term
    # would skip the tests of a person's or a fork's release/x, which
    # ci-passed judges by the ordinary rules, and it would go green untested.
    assert yaml.safe_load(SKIP_PATH.read_text(encoding="utf-8")) == {"if": SKIP_IF}


def test_each_term_of_the_skip_is_a_test_of_is_release_pr():
    """The skip and lib/release.js:isReleasePr name the same pull request:
    head ref, head repository and author, field by field."""
    source = (ASSETS / "pieces/workflow-lib/lib/release.js").read_text(encoding="utf-8")
    assert f"const BOT = '{BOT}';" in source
    body = source.split("function isReleasePr(pr, fullName) {", 1)[1].split("\n}\n", 1)[0]
    assert " ".join(body.split()) == (
        "return pr.head.ref.startsWith('release/') && Boolean(pr.head.repo) && "
        "pr.head.repo.full_name === fullName && pr.user.login === BOT;")
    for term in ("startsWith(github.head_ref, 'release/')",
                 "github.event.pull_request.head.repo.full_name == github.repository",
                 f"github.event.pull_request.user.login == '{BOT}'"):
        assert term in SKIP_IF


def _node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    return node


def _workspace(tmp_path):
    ws = tmp_path / "ws"
    # A piece reads the library from .repo-infra, repo-infra's own commit (D33).
    shutil.copytree(ROOT / ".github/workflows/lib", ws / ".repo-infra/.github/workflows/lib")
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
              statuses=(), behind=0, fail_compare=False):
    """Run ri-release-verdict's step, which ci-passed reads, against a fake
    API; the D28 verdict table."""
    script = next(s for s in verdict_piece()["jobs"]["verdict"]["steps"]
                  if s.get("id") == "verdict")["with"]["script"]
    ws = _workspace(tmp_path)
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
const context = { repo: { owner: 'o', repo: 'r' }, eventName: 'pull_request',
  payload: { pull_request: %s } };
""" % (json.dumps(list(statuses)), "true" if fail_compare else "false", behind, json.dumps(pr))
    return _run(tmp_path, ws, script, prelude)


def test_a_built_current_release_pull_request_passes_ci_passed(tmp_path):
    out = ci_passed(tmp_path, statuses=BUILT)
    assert out["failures"] == [] and out["thrown"] is None
    assert out["outputs"]["mode"] == "release" and out["outputs"]["ok"] == "true"
    assert out["notices"] == [out["outputs"]["message"]]


def test_a_stale_release_pull_request_fails_ci_passed(tmp_path):
    # The verdict step never fails: ci-passed reads ok and fails itself.
    out = ci_passed(tmp_path, statuses=BUILT, behind=2)
    assert out["failures"] == [] and out["thrown"] is None
    assert out["outputs"] == {"mode": "release", "ok": "false", "message": STALE}


def test_an_unbuilt_release_head_fails_ci_passed(tmp_path):
    out = ci_passed(tmp_path)
    assert out["failures"] == [] and out["thrown"] is None
    assert out["outputs"] == {"mode": "release", "ok": "false", "message": BLURB}


@pytest.mark.parametrize("case", [{"login": "oetiker"}, {"head_repo": "fork/r"},
                                  {"head_repo": None}])
def test_someone_elses_release_branch_gets_the_ordinary_rules(tmp_path, case):
    out = ci_passed(tmp_path, head_ref="release/x", **case)
    assert out["failures"] == [] and out["thrown"] is None
    assert out["outputs"] == {"mode": "ordinary", "ok": "true", "message": ""}


def test_an_api_error_fails_the_verdict_step(tmp_path):
    out = ci_passed(tmp_path, statuses=BUILT, fail_compare=True)
    assert out["thrown"] == "Server Error"


def release_pr_current(tmp_path, prs, behind, fail_compare=(), fail_list=False):
    script = release_pr_current_job()["steps"][-1]["with"]["script"]
    ws = _workspace(tmp_path)
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
