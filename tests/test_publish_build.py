"""The publish job with release_build set (D26), run under node against a fake API."""

import json
import os
import pathlib
import shutil
import subprocess

import pytest
import yaml

from repo_infra.assemble import assemble_publish

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
MAIN = "m" * 40
HEAD = "a" * 40
CHANGES = "# Changes\n\n## [Unreleased]\n\n## 1.2.0 - 2026-09-29\n\n### New\n\n- x\n"
AT_HEAD_OLD = "# Changes\n\n## [Unreleased]\n\n## 1.1.0 - 2026-09-01\n"


def workflow(addons=()):
    return yaml.safe_load(assemble_publish(ASSETS, list(addons), MANIFEST))


def publish_script():
    steps = workflow()["jobs"]["publish"]["steps"]
    return next(s["with"]["script"] for s in steps if s.get("id") == "publish")


def draft(record=True, rid=5, published=False):
    assets = [{"id": 901, "name": "x.deb"}]
    if record:
        assets.append({"id": 900, "name": "release-build.json"})
    return {"id": rid, "tag_name": "v1.2.0", "draft": not published, "assets": assets}


def run(tmp_path, *, release_build=True, tag=None, releases=(), record=None,
        changes_at_head=CHANGES, compare="ahead", lightweight=False, head_exists=True, record_throws=False):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    ws = tmp_path / "ws"
    shutil.copytree(ROOT / ".github/workflows/lib", ws / ".github/workflows/lib")
    (ws / "CHANGES.md").write_text(CHANGES)
    (ws / ".github/repo-infra.json").write_text(json.dumps(
        {"version_files": [], "release_build": release_build}))
    state = {"tag": tag, "releases": list(releases), "record": record,
             "changesAtHead": changes_at_head, "compare": compare,
             "lightweight": lightweight, "headExists": head_exists,
             "recordThrows": record_throws}
    harness = """
const state = %s;
const calls = [];
const outputs = {};
const failures = [];
const notices = [];
const warnings = [];
const notFound = () => { const e = new Error('Not Found'); e.status = 404; return e; };
const github = {
  paginate: async (fn) => (fn === 'listReleases' ? state.releases : []),
  rest: {
    git: {
      getRef: async () => { if (!state.tag) throw notFound();
        return { data: { object: state.lightweight
          ? { type: 'commit', sha: state.tag }
          : { type: 'tag', sha: 'tagobject' } } }; },
      getTag: async () => { if (state.lightweight) throw new Error('getTag on a commit');
        return { data: { object: { sha: state.tag } } }; },
      createTag: async (a) => { calls.push(['createTag', a]); return { data: { sha: `obj-${a.tag}` } }; },
      createRef: async (a) => { calls.push(['createRef', a]); return { data: {} }; },
      updateRef: async (a) => { calls.push(['updateRef', a]); return { data: {} }; },
      getCommit: async () => { if (!state.headExists) throw notFound(); return { data: {} }; },
    },
    repos: {
      listReleases: 'listReleases',
      getReleaseAsset: async (a) => { calls.push(['getReleaseAsset', a]);
        if (state.recordThrows) throw new Error('503');
        return { data: Buffer.from(JSON.stringify(state.record)) }; },
      getContent: async (a) => { calls.push(['getContent', a]);
        if (state.changesAtHead === null) throw notFound();
        return { data: { content: Buffer.from(state.changesAtHead).toString('base64') } }; },
      updateRelease: async (a) => { calls.push(['updateRelease', a]); return { data: {} }; },
      createRelease: async (a) => { calls.push(['createRelease', a]); return { data: { id: 77 } }; },
      compareCommitsWithBasehead: async (a) => ({ data: { status: state.compare } }),
    },
  },
};
const core = {
  setFailed: (m) => failures.push(m), notice: (m) => notices.push(m),
  warning: (m) => warnings.push(m),
  setOutput: (k, v) => { outputs[k] = v; },
};
const context = { repo: { owner: 'o', repo: 'r' }, sha: '%s' };
(async () => {
%s
})().then(() => console.log(JSON.stringify({ calls, outputs, failures, notices, warnings })));
""" % (json.dumps(state), MAIN, publish_script())
    path = tmp_path / "publish.js"
    path.write_text(harness, encoding="utf-8")
    proc = subprocess.run([node, str(path)], capture_output=True, text=True, cwd=ws,
                          env={"GITHUB_WORKSPACE": str(ws), "PATH": os.environ["PATH"]})
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def called(out, name):
    return [args for n, args in out["calls"] if n == name]


def test_without_release_build_the_merge_commit_is_tagged_as_before(tmp_path):
    out = run(tmp_path, release_build=False)
    assert [t["object"] for t in called(out, "createTag")] == [MAIN]
    assert out["outputs"]["head"] == MAIN
    assert len(called(out, "createRelease")) == 1


def test_case_3_tags_the_recorded_head_not_the_merge_commit(tmp_path):
    out = run(tmp_path, releases=[draft()], record={"head": HEAD})
    assert out["failures"] == []
    assert [t["object"] for t in called(out, "createTag")] == [HEAD]
    assert called(out, "createRef")[0]["ref"] == "refs/tags/v1.2.0"
    (update,) = called(out, "updateRelease")
    assert (update["release_id"], update["tag_name"], update["target_commitish"]) == (
        5, "v1.2.0", HEAD)
    assert out["outputs"] == {"version": "1.2.0", "tag": "v1.2.0", "release_id": "5",
                              "head": HEAD}
    assert called(out, "createRelease") == []


def test_case_3_refuses_a_head_whose_changes_name_another_version(tmp_path):
    out = run(tmp_path, releases=[draft()], record={"head": HEAD},
              changes_at_head=AT_HEAD_OLD)
    assert len(out["failures"]) == 1 and "1.1.0" in out["failures"][0]
    assert called(out, "createTag") == [] and out["outputs"] == {}


def test_case_3_refuses_a_head_that_does_not_exist(tmp_path):
    out = run(tmp_path, releases=[draft()], record={"head": HEAD}, changes_at_head=None,
              head_exists=False)
    assert out["failures"] == [
        f"v1.2.0: release-build.json names {HEAD}, which does not exist in this "
        "repository. Nothing was tagged."]
    assert called(out, "createTag") == []


def test_case_3_refuses_a_head_without_changes(tmp_path):
    out = run(tmp_path, releases=[draft()], record={"head": HEAD}, changes_at_head=None)
    assert len(out["failures"]) == 1 and "has no released version" in out["failures"][0]
    assert called(out, "createTag") == []


def test_case_2_resumes_at_the_tag_commit_without_retagging(tmp_path):
    out = run(tmp_path, tag=HEAD, releases=[draft(record=False)])
    assert out["failures"] == []
    assert called(out, "createTag") == [] and called(out, "createRef") == []
    assert out["outputs"]["head"] == HEAD
    assert called(out, "updateRelease")[0]["target_commitish"] == HEAD


def test_a_whole_workflow_rerun_after_tagging_resumes_the_draft(tmp_path):
    # The first run tagged and stopped before finalize: the draft still carries
    # the build record. A whole-workflow re-run must finish it, not strand it.
    out = run(tmp_path, tag=HEAD, releases=[draft()], record={"head": "b" * 40})
    assert out["failures"] == []
    assert called(out, "createTag") == []
    assert out["outputs"] == {"version": "1.2.0", "tag": "v1.2.0", "release_id": "5",
                              "head": HEAD}
    # The record names another commit than the tag: resume, but say so.
    (warning,) = out["warnings"]
    assert HEAD in warning and "b" * 40 in warning


def test_a_resume_at_the_built_commit_warns_of_nothing(tmp_path):
    out = run(tmp_path, tag=HEAD, releases=[draft()], record={"head": HEAD})
    assert out["failures"] == [] and out["warnings"] == []


def test_a_lightweight_tag_is_taken_as_the_tag_commit(tmp_path):
    out = run(tmp_path, tag=HEAD, releases=[draft(record=False)], lightweight=True)
    assert out["failures"] == []
    assert called(out, "createTag") == [] and called(out, "createRef") == []
    assert out["outputs"]["head"] == HEAD
    assert called(out, "updateRelease")[0]["target_commitish"] == HEAD


def test_case_1_an_ordinary_merge_after_the_release_does_nothing(tmp_path):
    out = run(tmp_path, tag=HEAD, releases=[draft(record=False, published=True)])
    assert out["failures"] == [] and out["outputs"] == {} and out["calls"] == []


def test_case_4_a_tag_without_a_release_fails_and_says_so(tmp_path):
    out = run(tmp_path, tag=HEAD, releases=[])
    assert len(out["failures"]) == 1 and "no release" in out["failures"][0]


def test_a_squash_merge_is_noticed(tmp_path):
    out = run(tmp_path, releases=[draft()], record={"head": HEAD}, compare="diverged")
    assert any("merge commit" in n for n in out["notices"])


@pytest.mark.parametrize("addon", ["publish-source-tarball", "publish-crates-io"])
def test_every_addon_checks_out_the_tagged_head(addon):
    job = workflow([addon])["jobs"][addon]
    checkout = next(s for s in job["steps"] if s.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["ref"] == "${{ needs.publish.outputs.head }}"


def test_finalize_checks_out_the_tagged_head():
    job = workflow()["jobs"]["finalize"]
    checkout = next(s for s in job["steps"] if s.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["ref"] == "${{ needs.publish.outputs.head }}"


def test_publish_exposes_the_head():
    assert workflow()["jobs"]["publish"]["outputs"]["head"] == "${{ steps.publish.outputs.head }}"


def test_a_failed_record_download_does_not_stop_a_resume(tmp_path):
    out = run(tmp_path, tag=HEAD, releases=[draft()], record={"head": HEAD},
              record_throws=True)
    assert out["failures"] == []
    assert out["outputs"]["head"] == HEAD
    (warning,) = out["warnings"]
    assert "503" in warning and "release-build.json" in warning
