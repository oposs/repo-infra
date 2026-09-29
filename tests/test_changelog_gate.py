"""changelog v3 (D26): release/* branches of release_build repositories are gated."""

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


def gate(tmp_path, *, head_ref, login=BOT, head_repo="o/r", labels=(), config=None,
         statuses=(), head_changes=SAME):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = job()["steps"][-1]["with"]["script"]
    contents = {"CHANGES.md@b": SAME, "CHANGES.md@h": head_changes}
    if config is not None:
        contents[".github/repo-infra.json@b"] = json.dumps(config)
    pr = {"number": 1, "labels": [{"name": n} for n in labels], "user": {"login": login},
          "head": {"ref": head_ref, "sha": "h",
                   "repo": {"full_name": head_repo} if head_repo else None},
          "base": {"sha": "b"}}
    harness = """
const contents = %s;
const statuses = %s;
const failures = [];
const github = {
  paginate: async (fn) => (fn === 'statuses' ? statuses : []),
  rest: { repos: {
    listCommitStatusesForRef: 'statuses',
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
""" % (json.dumps(contents), json.dumps(list(statuses)), json.dumps(pr), script)
    path = tmp_path / "gate.js"
    path.write_text(harness, encoding="utf-8")
    proc = subprocess.run([node, str(path)], capture_output=True, text=True, cwd=ROOT,
                          env={"GITHUB_WORKSPACE": str(ROOT), "PATH": os.environ["PATH"]})
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)["failures"]


BUILT = [{"context": "release-built", "state": "success", "creator": {"login": BOT}}]


def test_the_job_runs_on_release_branches_now():
    condition = job()["if"]
    assert "startsWith(github.head_ref, 'release/') ||" in condition
    assert "no-changelog" in condition


def test_the_job_may_read_statuses():
    wf = yaml.safe_load(ASSET.read_text(encoding="utf-8"))
    assert wf["permissions"]["statuses"] == "read"


def test_a_repository_without_release_build_keeps_release_branches_exempt(tmp_path):
    assert gate(tmp_path, head_ref="release/v1.2.0", config={}) == []
    assert gate(tmp_path, head_ref="release/v1.2.0", config=None) == []


def test_a_built_release_pull_request_passes(tmp_path):
    assert gate(tmp_path, head_ref="release/v1.2.0", config={"release_build": True},
                statuses=BUILT) == []


def test_a_release_branch_that_moved_after_the_build_fails(tmp_path):
    assert gate(tmp_path, head_ref="release/v1.2.0",
                config={"release_build": True}) == [BLURB]


def test_the_label_does_not_rescue_a_moved_release_branch(tmp_path):
    assert gate(tmp_path, head_ref="release/v1.2.0", labels=["no-changelog"],
                config={"release_build": True}) == [BLURB]


def test_a_status_someone_else_set_does_not_count(tmp_path):
    fake = [{**BUILT[0], "creator": {"login": "oetiker"}}]
    assert gate(tmp_path, head_ref="release/v1.2.0", config={"release_build": True},
                statuses=fake) == [BLURB]


def test_a_persons_release_branch_gets_the_ordinary_rules(tmp_path):
    failures = gate(tmp_path, head_ref="release/x", login="oetiker",
                    config={"release_build": True})
    assert len(failures) == 1 and "[Unreleased]" in failures[0]
    assert gate(tmp_path, head_ref="release/x", login="oetiker", labels=["no-changelog"],
                config={"release_build": True}) == []


def test_a_forks_release_branch_gets_the_ordinary_rules(tmp_path):
    assert gate(tmp_path, head_ref="release/x", head_repo="fork/r",
                config={"release_build": True}, head_changes=MORE) == []


def test_an_ordinary_pull_request_is_checked_as_before(tmp_path):
    assert gate(tmp_path, head_ref="fix/x", login="oetiker", head_changes=MORE) == []
    assert len(gate(tmp_path, head_ref="fix/x", login="oetiker")) == 1
