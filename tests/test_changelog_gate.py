"""changelog v4 (D28): every release pull request is gated on its build and on main."""

import json
import os
import pathlib
import shutil
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSET = ROOT / "skills/repo-infra/assets/workflows/changelog.yml"
BOT = "github-actions[bot]"
BLURB = ("the release branch changed after it was built (the Update branch button "
         "does this); close this pull request and dispatch Create release PR again")
SAME = "# Changes\n\n## [Unreleased]\n\n## 1.0.0 - 2026-01-01\n"
MORE = "# Changes\n\n## [Unreleased]\n\n### New\n\n- x\n\n## 1.0.0 - 2026-01-01\n"


def job():
    return yaml.safe_load(ASSET.read_text(encoding="utf-8"))["jobs"]["changelog-updated"]


def gate(tmp_path, *, head_ref, login=BOT, head_repo="o/r", labels=(), statuses=(),
         behind=0, head_changes=SAME, base_changes=SAME, sabotage_merge_lib=False):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = job()["steps"][-1]["with"]["script"]
    ws = tmp_path / "ws"
    # Several tests call gate() twice with one tmp_path: copy over, never fail on an existing tree.
    shutil.copytree(ROOT / ".github/workflows/lib", ws / ".github/workflows/lib", dirs_exist_ok=True)
    shutil.copytree(ROOT / ".github/workflows/lib", ws / "repo-infra-base/.github/workflows/lib",
                    dirs_exist_ok=True)
    if sabotage_merge_lib:
        (ws / ".github/workflows/lib/release.js").write_text("module.exports = {};\n")
    contents = {"CHANGES.md@b": base_changes, "CHANGES.md@h": head_changes}
    contents = {k: v for k, v in contents.items() if v is not None}
    pr = {"number": 1, "labels": [{"name": n} for n in labels], "user": {"login": login},
          "head": {"ref": head_ref, "sha": "h",
                   "repo": {"full_name": head_repo} if head_repo else None},
          "base": {"ref": "main", "sha": "b"}}
    harness = """
const contents = %s;
const statuses = %s;
const failures = [];
const github = {
  paginate: async (fn) => (fn === 'statuses' ? statuses : []),
  rest: { repos: {
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
const core = { setFailed: (m) => failures.push(m), notice: () => {} };
const context = { repo: { owner: 'o', repo: 'r' }, payload: { pull_request: %s } };
(async () => {
%s
})().then(() => console.log(JSON.stringify({ failures })));
""" % (json.dumps(contents), json.dumps(list(statuses)), behind, json.dumps(pr), script)
    path = tmp_path / "gate.js"
    path.write_text(harness, encoding="utf-8")
    proc = subprocess.run([node, str(path)], capture_output=True, text=True, cwd=ws,
                          env={"GITHUB_WORKSPACE": str(ws), "PATH": os.environ["PATH"]})
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)["failures"]


BUILT = [{"context": "release-built", "state": "success", "creator": {"login": BOT}}]
STALE = ("main moved after v1.2.0 was built; close this pull request and dispatch "
         "Create release PR again")


def test_the_job_runs_on_release_branches():
    # The harness never evaluates this expression, so only an exact comparison
    # notices `&&` in place of `||` or a dropped `!`.
    assert job()["if"] == ("startsWith(github.head_ref, 'release/') || "
                           "!contains(github.event.pull_request.labels.*.name, 'no-changelog')")


def test_the_job_may_read_statuses():
    wf = yaml.safe_load(ASSET.read_text(encoding="utf-8"))
    assert wf["permissions"]["statuses"] == "read"


def test_the_base_commit_is_checked_out_beside_the_merge_commit():
    checkouts = [s for s in job()["steps"] if str(s.get("uses", "")).startswith("actions/checkout@")]
    assert checkouts[0].get("with") is None
    assert checkouts[1]["with"] == {"ref": "${{ github.event.pull_request.base.sha }}",
                                    "path": "repo-infra-base"}


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


def test_release_mode_reads_the_library_of_the_base_commit(tmp_path):
    assert gate(tmp_path, head_ref="release/v1.2.0", statuses=BUILT, behind=1,
                sabotage_merge_lib=True) == [STALE]


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


@pytest.mark.parametrize("statuses,behind", [(BUILT, 0), (BUILT, 2), ((), 0), ((), 3)])
def test_both_required_checks_agree_on_a_release_pull_request(tmp_path, statuses, behind):
    # Review Focus 2: an approved parked run must not disagree with finish
    # and release-pr-current.
    from test_release_mode import ci_passed

    (tmp_path / "gate").mkdir()
    (tmp_path / "ci").mkdir()
    ours = gate(tmp_path / "gate", head_ref="release/v1.2.0", statuses=statuses, behind=behind)
    theirs = ci_passed(tmp_path / "ci", statuses=statuses, behind=behind)["failures"]
    assert ours == theirs
