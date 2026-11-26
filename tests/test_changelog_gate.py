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
         statuses=(), behind=0, head_changes=SAME, base_changes=SAME, merge_changes=None,
         files=(), fragments=None, tags=(), tree=(), truncated=False, compare_status=None,
         outputs=False):
    """The failures of ri-changelog's step; with `outputs`, also what it set and
    the API calls it made. The merge base is 'm'; `fragments` maps a path to its
    text at head, `tags` names the tags that exist, `tree` lists the paths at head
    (`truncated` as the API flags a cut listing), and `compare_status` makes the
    compare fail with that status."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = job()["steps"][-1]["with"]["script"]
    ws = tmp_path / "ws"
    # Several tests call gate() twice with one tmp_path: copy over, never fail on an existing tree.
    shutil.copytree(ROOT / ".github/workflows/lib", ws / ".repo-infra/.github/workflows/lib",
                    dirs_exist_ok=True)
    contents = {"CHANGES.md@b": base_changes, "CHANGES.md@h": head_changes,
                "CHANGES.md@m": merge_changes}
    contents.update({f"{p}@h": t for p, t in (fragments or {}).items()})
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
const files = %s;
const tags = %s;
const tree = %s;
const truncated = %s;
const compareStatus = %s;
const failures = []; const outputs = {}; const calls = [];
const notFound = () => { const e = new Error('Not Found'); e.status = 404; return e; };
const github = {
  // Pages as the API serves them, so a script that skips paginate sees only the first.
  paginate: async (fn, params) => {
    if (fn === 'statuses') return statuses;
    const out = [];
    for (let page = 1; ; page += 1) {
      const { data } = await fn({ ...params, page });
      out.push(...data);
      if (data.length < (params.per_page || 30)) return out;
    }
  },
  rest: { pulls: {
    get: async ({ pull_number }) => {
      if (pull_number !== 1) throw new Error(`pull_number ${pull_number}`);
      return { data: { labels: current } }; },
    listFiles: async ({ pull_number, per_page = 30, page = 1 }) => {
      calls.push('listFiles');
      if (pull_number !== 1) throw new Error(`pull_number ${pull_number}`);
      const size = Math.min(per_page, 100);
      return { data: files.slice((page - 1) * size, page * size) }; },
  }, git: {
    getRef: async ({ ref }) => {
      calls.push(`getRef ${ref}`);
      if (!ref.startsWith('tags/') || !tags.includes(ref.slice(5))) throw notFound();
      return { data: { ref: `refs/${ref}` } }; },
    getTree: async ({ tree_sha, recursive }) => {
      calls.push('getTree');
      if (tree_sha !== 'h' || !recursive) throw new Error(`tree ${tree_sha} ${recursive}`);
      return { data: { tree: tree.map((path) => ({ path, type: 'blob' })), truncated } }; },
  }, repos: {
    listCommitStatusesForRef: 'statuses',
    compareCommitsWithBasehead: async ({ basehead }) => {
      calls.push('compare');
      if (compareStatus !== null) { const e = new Error('compare'); e.status = compareStatus; throw e; }
      if (basehead !== 'main...h') throw new Error(`basehead ${basehead}`);
      return { data: { behind_by: %d, merge_base_commit: { sha: 'm' } } }; },
    getContent: async ({ path, ref }) => {
      const text = contents[`${path}@${ref}`];
      if (text === undefined) throw notFound();
      return { data: { content: Buffer.from(text).toString('base64') } };
    },
  } },
};
const core = { setFailed: (m) => failures.push(m), notice: () => {},
  setOutput: (k, v) => { outputs[k] = v; } };
const context = { repo: { owner: 'o', repo: 'r' }, payload: { pull_request: %s } };
(async () => {
%s
})().then(() => console.log(JSON.stringify({ failures, outputs, calls })));
""" % (json.dumps(contents), json.dumps(current), json.dumps(list(statuses)),
       json.dumps(list(files)), json.dumps(list(tags)), json.dumps(list(tree)),
       json.dumps(truncated), json.dumps(compare_status), behind,
       json.dumps(pr), script)
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
    assert " ".join(jobs["changelog-updated"]["if"].split()) == f"always() && ({label})"
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


# Changelog fragments (D40): the mode comes from the merge base 'm' and the head.
FRAG = "# Changes\n\nChangelog fragments: `CHANGES.d`\n\n## 1.0.0 - 2026-01-01\n\n- a\n"
FRAG_NEXT = ("# Changes\n\nChangelog fragments: `CHANGES.d`\n\n## 1.1.0 - 2026-02-01\n\n"
             "### Fixed\n\n- y\n\n## 1.0.0 - 2026-01-01\n\n- a\n")
FRAGMENT = "CHANGES.d/new/20261126-1200-ab12-gate.md"
ADDED = [{"filename": FRAGMENT, "status": "added"}]


def fragment_gate(tmp_path, **kwargs):
    args = {"head_ref": "fix/x", "login": "oetiker", "base_changes": FRAG,
            "merge_changes": FRAG, "head_changes": FRAG, "outputs": True, **kwargs}
    return gate(tmp_path, **args)


def test_a_fragment_pull_request_passes(tmp_path):
    out = fragment_gate(tmp_path, files=ADDED, fragments={FRAGMENT: "- x\n"})
    assert out["failures"] == []
    assert "CHANGES.d/" in out["outputs"]["message"]
    # The top release is still at head: no tag to read.
    assert not any(c.startswith("getRef") for c in out["calls"])


def test_a_fragment_pull_request_without_a_fragment_fails(tmp_path):
    out = fragment_gate(tmp_path, files=[{"filename": "src/a.c", "status": "modified"}])
    assert len(out["failures"]) == 1 and "adds no changelog fragment" in out["failures"][0]


def test_a_fragment_pull_request_that_edits_the_header_fails(tmp_path):
    head = FRAG.replace("# Changes\n", "# Changes\n\nSee below.\n")
    out = fragment_gate(tmp_path, head_changes=head, files=ADDED, fragments={FRAGMENT: "- x\n"})
    assert len(out["failures"]) == 1 and "changes the header" in out["failures"][0]


def test_the_gate_reads_every_page_of_changed_files(tmp_path):
    # Review Focus: more than 100 changed files; the fragment is on the second page.
    files = [{"filename": f"src/f{i}.c", "status": "modified"} for i in range(149)] + ADDED
    out = fragment_gate(tmp_path, files=files, fragments={FRAGMENT: "- x\n"})
    assert out["failures"] == []
    assert out["calls"].count("listFiles") == 2


def test_a_broken_fragment_fails_by_name(tmp_path):
    out = fragment_gate(tmp_path, files=ADDED, fragments={FRAGMENT: "## x\n"})
    assert len(out["failures"]) == 1 and FRAGMENT in out["failures"][0]


def test_a_pull_request_from_before_the_switch_is_judged_classic(tmp_path):
    # main has switched since the branch was cut; the merge base and head have not.
    out = gate(tmp_path, head_ref="fix/x", login="oetiker", base_changes=FRAG,
               merge_changes=SAME, head_changes=MORE, outputs=True)
    assert out["failures"] == [] and "listFiles" not in out["calls"]


def test_classic_repositories_make_no_new_api_calls(tmp_path):
    out = gate(tmp_path, head_ref="fix/x", login="oetiker", merge_changes=SAME,
               head_changes=MORE, outputs=True)
    assert out["failures"] == []
    assert "compare" in out["calls"]
    assert [c for c in out["calls"] if c != "compare"] == []


def test_the_switch_to_fragments_passes_with_its_entries_moved(tmp_path):
    head = "# Changes\n\nChangelog fragments: `CHANGES.d`\n\n## 1.0.0 - 2026-01-01\n"
    out = fragment_gate(tmp_path, base_changes=MORE, merge_changes=MORE, head_changes=head,
                        files=ADDED, fragments={FRAGMENT: "- x\n"})
    assert out["failures"] == [] and "switches to fragments" in out["outputs"]["message"]


def test_removing_an_untagged_release_section_passes(tmp_path):
    fixed = "CHANGES.d/fixed/20261126-1200-ab12-gate.md"
    out = fragment_gate(tmp_path, base_changes=FRAG_NEXT, merge_changes=FRAG_NEXT,
                        files=[{"filename": fixed, "status": "added"}],
                        fragments={fixed: "- y\n"}, tags=["v1.0.0"])
    assert out["failures"] == []
    assert "getRef tags/v1.1.0" in out["calls"]


def test_removing_a_tagged_release_section_fails(tmp_path):
    fixed = "CHANGES.d/fixed/20261126-1200-ab12-gate.md"
    out = fragment_gate(tmp_path, base_changes=FRAG_NEXT, merge_changes=FRAG_NEXT,
                        files=[{"filename": fixed, "status": "added"}],
                        fragments={fixed: "- y\n"}, tags=["v1.0.0", "v1.1.0"])
    assert len(out["failures"]) == 1 and "v1.1.0 is tagged" in out["failures"][0]


def test_switching_back_fails_while_fragments_remain(tmp_path):
    out = fragment_gate(tmp_path, head_changes=MORE, tree=["README.md", FRAGMENT])
    assert len(out["failures"]) == 1 and "1 fragment file remains" in out["failures"][0]
    assert fragment_gate(tmp_path, head_changes=MORE, tree=["README.md"])["failures"] == []


def test_a_refused_note_fails_without_an_error(tmp_path):
    head = FRAG.replace("`CHANGES.d`", "`../x`")
    out = fragment_gate(tmp_path, head_changes=head)
    assert len(out["failures"]) == 1 and "contains '..'" in out["failures"][0]


def test_a_truncated_tree_fails_rather_than_undercounting(tmp_path):
    out = fragment_gate(tmp_path, head_changes=MORE, tree=["README.md"], truncated=True)
    assert out["failures"] == [
        "The tree at head is too large to count the fragments left under CHANGES.d/; "
        "the API truncated it."]


def test_branches_without_common_history_fall_back_to_the_base_tip(tmp_path):
    # The compare answers 404 when base and head share no commit.
    assert gate(tmp_path, head_ref="fix/x", login="oetiker", head_changes=MORE,
                compare_status=404) == []
    failures = gate(tmp_path, head_ref="fix/x", login="oetiker", compare_status=404)
    assert len(failures) == 1 and "adds nothing" in failures[0]


def test_the_pass_message_of_one_fragment_is_singular(tmp_path):
    out = fragment_gate(tmp_path, files=ADDED, fragments={FRAGMENT: "- x\n"})
    assert out["outputs"]["message"] == "1 changelog fragment under CHANGES.d/ follows the rules."
