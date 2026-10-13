"""ri-changelog (D28, D33): every release pull request is gated on its build and
on main; changelog-updated reads the verdict inline."""

import json
import os
import pathlib
import shutil
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSET = ROOT / ".github/workflows/ri-changelog.yml"
BOT = "github-actions[bot]"
BLURB = ("the release branch changed after it was built (the Update branch button "
         "does this); close this pull request and dispatch Create release PR again")
SAME = "# Changes\n\n## [Unreleased]\n\n## 1.0.0 - 2026-01-01\n"
MORE = "# Changes\n\n## [Unreleased]\n\n### New\n\n- x\n\n## 1.0.0 - 2026-01-01\n"


def job():
    return yaml.safe_load(ASSET.read_text(encoding="utf-8"))["jobs"]["changelog"]


# The tests of the base-commit fallback (a pull request that edits
# lib/changes.js, or a base on workflow-lib v4) are gone with it: D33 loads
# the library from repo-infra's commit, which no consumer pull request changes.
def gate(tmp_path, *, head_ref, login=BOT, head_repo="o/r", labels=(), current_labels=None,
         statuses=(), behind=0, head_changes=SAME, base_changes=SAME, outputs=False):
    """The failures of ri-changelog's step; with `outputs`, also what it set."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = job()["steps"][-1]["with"]["script"]
    ws = tmp_path / "ws"
    # Several tests call gate() twice with one tmp_path: copy over, never fail on an existing tree.
    shutil.copytree(ROOT / ".github/workflows/lib", ws / ".repo-infra/.github/workflows/lib",
                    dirs_exist_ok=True)
    contents = {"CHANGES.md@b": base_changes, "CHANGES.md@h": head_changes}
    contents = {k: v for k, v in contents.items() if v is not None}
    pr = {"number": 1, "labels": [{"name": n} for n in labels], "user": {"login": login},
          "head": {"ref": head_ref, "sha": "h",
                   "repo": {"full_name": head_repo} if head_repo else None},
          "base": {"ref": "main", "sha": "b"}}
    # The labels the API returns when the script runs; the event's by default.
    current = [{"name": n} for n in (labels if current_labels is None else current_labels)]
    harness = """
const contents = %s;
const current = %s;
const statuses = %s;
const failures = []; const outputs = {};
const github = {
  paginate: async (fn) => (fn === 'statuses' ? statuses : []),
  rest: { pulls: {
    get: async ({ pull_number }) => {
      if (pull_number !== 1) throw new Error(`pull_number ${pull_number}`);
      return { data: { labels: current } }; },
  }, repos: {
    listCommitStatusesForRef: 'statuses',
    compareCommitsWithBasehead: async ({ basehead }) => {
      if (basehead !== 'main...h') throw new Error(`basehead ${basehead}`);
      return { data: { behind_by: %d } }; },
    getContent: async ({ path, ref }) => {
      const text = contents[`${path}@${ref}`];
      if (text === undefined) { const e = new Error('Not Found'); e.status = 404; throw e; }
      return { data: { content: Buffer.from(text).toString('base64') } };
    },
  } },
};
const core = { setFailed: (m) => failures.push(m), notice: () => {},
  setOutput: (k, v) => { outputs[k] = v; } };
const context = { repo: { owner: 'o', repo: 'r' }, payload: { pull_request: %s } };
(async () => {
%s
})().then(() => console.log(JSON.stringify({ failures, outputs })));
""" % (json.dumps(contents), json.dumps(current), json.dumps(list(statuses)), behind, json.dumps(pr), script)
    path = tmp_path / "gate.js"
    path.write_text(harness, encoding="utf-8")
    proc = subprocess.run([node, str(path)], capture_output=True, text=True, cwd=ws,
                          env={"GITHUB_WORKSPACE": str(ws), "PATH": os.environ["PATH"]})
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    # The inline changelog-updated job prints the message: on a refusal it
    # is the failure, word for word.
    for failure in result["failures"]:
        assert result["outputs"]["message"] == failure
    return result if outputs else result["failures"]


BUILT = [{"context": "release-built", "state": "success", "creator": {"login": BOT}}]
STALE = ("main moved after v1.2.0 was built; close this pull request and dispatch "
         "Create release PR again")


def callers_doc():
    return yaml.safe_load((ROOT / "skills/repo-infra/assets/callers/changelog.yml")
                          .read_text(encoding="utf-8"))


def test_changelog_updated_runs_unless_cancelled_and_reads_the_result():
    # The harness never evaluates these expressions, so only an exact comparison
    # notices `&&` in place of `||` or a dropped `!`.
    jobs = callers_doc()["jobs"]
    label = ("startsWith(github.head_ref, 'release/') || "
             "!contains(github.event.pull_request.labels.*.name, 'no-changelog')")
    assert " ".join(jobs["changelog"]["if"].split()) == label
    assert " ".join(jobs["changelog-updated"]["if"].split()) == f"!cancelled() && ({label})"
    assert jobs["changelog-updated"]["needs"] == "changelog"


@pytest.mark.parametrize("result, passes", [
    ("success", True), ("failure", False), ("cancelled", False), ("skipped", False)])
def test_changelog_updated_step(tmp_path, result, passes):
    run = callers_doc()["jobs"]["changelog-updated"]["steps"][0]["run"]
    script = tmp_path / "step.sh"
    script.write_text(run, encoding="utf-8")
    proc = subprocess.run(["bash", "-e", str(script)], capture_output=True, text=True,
                          env={"PATH": os.environ["PATH"], "RESULT": result,
                               "MESSAGE": "no entry under [Unreleased]"})
    assert (proc.returncode == 0) is passes


def test_the_job_may_read_statuses():
    wf = yaml.safe_load(ASSET.read_text(encoding="utf-8"))
    assert wf["permissions"]["statuses"] == "read"
    assert callers_doc()["jobs"]["changelog"]["permissions"]["statuses"] == "read"


def test_a_passing_verdict_is_the_message_too(tmp_path):
    out = gate(tmp_path, head_ref="fix/x", login="oetiker", head_changes=MORE, outputs=True)
    assert out["failures"] == [] and out["outputs"]["message"]


def test_every_repository_gates_its_release_pull_requests(tmp_path):
    # D28: no release_build switch any more; the exemption is gone.
    assert gate(tmp_path, head_ref="release/v1.2.0") == [BLURB]


def test_a_built_current_release_pull_request_passes(tmp_path):
    assert gate(tmp_path, head_ref="release/v1.2.0", statuses=BUILT) == []


def test_a_release_pull_request_main_moved_past_fails(tmp_path):
    assert gate(tmp_path, head_ref="release/v1.2.0", statuses=BUILT, behind=1) == [STALE]


def test_the_label_does_not_rescue_a_release_pull_request(tmp_path):
    assert gate(tmp_path, head_ref="release/v1.2.0", labels=["no-changelog"]) == [BLURB]


def test_a_status_someone_else_set_does_not_count(tmp_path):
    fake = [{**BUILT[0], "creator": {"login": "oetiker"}}]
    assert gate(tmp_path, head_ref="release/v1.2.0", statuses=fake) == [BLURB]


def test_a_persons_release_branch_gets_the_ordinary_rules(tmp_path):
    failures = gate(tmp_path, head_ref="release/x", login="oetiker")
    assert len(failures) == 1 and "[Unreleased]" in failures[0]
    assert gate(tmp_path, head_ref="release/x", login="oetiker", labels=["no-changelog"]) == []


def test_a_forks_release_branch_gets_the_ordinary_rules(tmp_path):
    assert gate(tmp_path, head_ref="release/x", head_repo="fork/r", head_changes=MORE) == []


def test_an_ordinary_pull_request_is_checked_as_before(tmp_path):
    assert gate(tmp_path, head_ref="fix/x", login="oetiker", head_changes=MORE) == []
    assert len(gate(tmp_path, head_ref="fix/x", login="oetiker")) == 1


BARE = "# Changes\n\n## Unreleased\n\n- x\n"


def test_the_pull_request_that_introduces_the_heading_passes(tmp_path):
    assert gate(tmp_path, head_ref="repo-infra/apply", login="oetiker",
                base_changes=BARE, head_changes=MORE) == []
    assert gate(tmp_path, head_ref="repo-infra/apply", login="oetiker",
                base_changes=None, head_changes=MORE) == []


def test_introducing_an_empty_heading_still_fails(tmp_path):
    failures = gate(tmp_path, head_ref="repo-infra/apply", login="oetiker",
                    base_changes=BARE, head_changes=SAME)
    assert len(failures) == 1 and "adds nothing" in failures[0]


def test_a_head_without_the_heading_fails_by_name(tmp_path):
    failures = gate(tmp_path, head_ref="fix/x", login="oetiker", head_changes=BARE)
    assert len(failures) == 1 and "no '## [Unreleased]' heading" in failures[0]


@pytest.mark.parametrize("statuses,behind,expected", [
    (BUILT, 0, []), (BUILT, 2, [STALE]), ((), 0, [BLURB]), ((), 3, [BLURB])])
def test_both_required_checks_agree_on_a_release_pull_request(tmp_path, statuses, behind,
                                                              expected):
    # Review Focus 2: an approved parked run must not disagree with finish
    # and release-pr-current.
    from test_release_mode import ci_passed

    (tmp_path / "gate").mkdir()
    (tmp_path / "ci").mkdir()
    ours = gate(tmp_path / "gate", head_ref="release/v1.2.0", statuses=statuses, behind=behind)
    verdict = ci_passed(tmp_path / "ci", statuses=statuses, behind=behind)["outputs"]
    theirs = [] if verdict["ok"] == "true" else [verdict["message"]]
    assert ours == theirs == expected


def test_a_label_added_after_the_event_counts(tmp_path):
    # `gh pr create --label` opens the pull request and labels it in a second
    # call: the opened run's payload has no label, the pull request has one.
    assert gate(tmp_path, head_ref="fix", labels=(), current_labels=["no-changelog"]) == []


def test_a_label_removed_after_the_event_no_longer_counts(tmp_path):
    found = gate(tmp_path, head_ref="fix", labels=["no-changelog"], current_labels=[])
    assert len(found) == 1 and "adds nothing under '## [Unreleased]'" in found[0]
