import json
import pathlib
import shutil

import pytest
import yaml

from repo_infra.assemble import AssemblyError, assemble_publish
from repo_infra.markers import parse_markers

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))


def test_with_no_addons_finalize_needs_only_publish():
    text = assemble_publish(ASSETS, [], MANIFEST)
    assert "    needs: [publish]" in text


def test_the_frame_marker_survives_assembly():
    text = assemble_publish(ASSETS, [], MANIFEST)
    assert ("release-publish", 5) in [(m.asset, m.version) for m in parse_markers(text)]


def test_an_unknown_addon_is_an_assembly_error():
    with pytest.raises(AssemblyError, match="not declared in the manifest"):
        assemble_publish(ASSETS, ["publish-nonexistent"], MANIFEST)


def test_the_placeholder_must_appear_exactly_once():
    # Guards the asset, not the code: a finalize block that lost its
    # placeholder would silently publish a release before the add-ons ran.
    text = (ASSETS / "publish/publish-finalize.yml").read_text(encoding="utf-8")
    assert text.count("    needs: []") == 1


# --- publish-crates-io (D21) -------------------------------------------------
#
# These parse the assembled workflow rather than grepping the asset. A substring
# assertion passes on a block that YAML cannot load, and every claim below is
# about structure -- which key, which order, which value -- not about text.


def _crates_io_job():
    text = assemble_publish(ASSETS, ["publish-crates-io"], MANIFEST)
    return yaml.safe_load(text)["jobs"]["publish-crates-io"]


def _shell_code(run):
    """A `run:` block with its shell comments removed.

    A comment inside the run string that names `--allow-dirty` or `|| true`
    would otherwise read as a use of it.
    """
    return "\n".join(
        line for line in run.splitlines() if not line.strip().startswith("#"))


def test_the_crates_io_addon_lands_between_publish_and_finalize():
    text = assemble_publish(ASSETS, ["publish-crates-io"], MANIFEST)
    assert "    needs: [publish, publish-crates-io]" in text
    assert text.index("  publish-crates-io:") < text.index("  finalize:")


def test_the_crates_io_addon_carries_its_marker():
    text = assemble_publish(ASSETS, ["publish-crates-io"], MANIFEST)
    assert ("publish-crates-io", 3) in [
        (m.asset, m.version) for m in parse_markers(text)]


def test_the_crates_io_addon_declares_exactly_the_job_it_contains():
    from repo_infra.assemble import block_job_ids
    text = (ASSETS / "publish/publish-crates-io.yml").read_text(encoding="utf-8")
    assert block_job_ids(text) == MANIFEST["publish_blocks"]["publish-crates-io"]["jobs"]


def test_the_assembled_publish_workflow_is_loadable_yaml():
    # The block is pasted into a frame at a fixed indent. A block that is valid
    # on its own but wrong by one space produces a file GitHub silently refuses
    # to run, and every string assertion below would still pass.
    doc = yaml.safe_load(assemble_publish(ASSETS, ["publish-crates-io"], MANIFEST))
    assert set(doc["jobs"]) == {"publish", "publish-crates-io", "finalize"}


def test_the_crates_io_addon_waits_for_publish_and_honours_the_guard():
    job = _crates_io_job()
    assert job["needs"] == ["publish"]
    assert job["if"] == "needs.publish.outputs.release_id != ''"


def test_the_crates_io_addon_requests_an_oidc_identity():
    # D21: without `id-token: write` the token exchange cannot mint an identity
    # and Trusted Publishing fails. Job-level permissions REPLACE the frame's
    # workflow-level block, so this must be complete, not additive.
    job = _crates_io_job()
    assert job["permissions"] == {"contents": "read", "id-token": "write"}


def test_the_crates_io_addon_holds_no_long_lived_credential():
    # The whole point of D21. One `secrets.` reference reintroduces the
    # per-repository crates.io token the decision exists to avoid.
    #
    # Assert over the parsed step values, not the file text: the block's own
    # comments name CRATES_IO_TOKEN to explain why it is absent, and a text
    # search cannot tell an explanation from a reference.
    for step in _crates_io_job()["steps"]:
        for value in [step.get("uses", ""), step.get("run", "")] + [
            str(v) for v in (step.get("env") or {}).values()
        ]:
            assert "secrets." not in value, value


def test_the_crates_io_token_comes_from_the_auth_action():
    steps = _crates_io_job()["steps"]
    auth = [s for s in steps if s.get("id") == "auth"]
    assert len(auth) == 1
    assert auth[0]["uses"].startswith("rust-lang/crates-io-auth-action@")
    publish = [s for s in steps if "cargo publish" in s.get("run", "")]
    assert len(publish) == 1
    assert publish[0]["env"]["CARGO_REGISTRY_TOKEN"] == "${{ steps.auth.outputs.token }}"


def test_no_step_swallows_its_own_failure():
    # mdmost v0.1.1: a swallowed bump failure tagged 0.1.1 with the lock still
    # at 0.1.0, and the publish died 6 minutes later.
    for run in (s.get("run", "") for s in _crates_io_job()["steps"]):
        assert "|| true" not in _shell_code(run)


def test_the_publish_covers_the_whole_workspace_and_stays_locked():
    # --workspace publishes every crate in one invocation; --locked keeps the
    # Cargo.lock the release pull request bumped instead of re-resolving it.
    runs = [s.get("run", "") for s in _crates_io_job()["steps"]]
    publish = next(r for r in runs if "cargo publish" in r)
    assert "--workspace" in publish
    assert "--locked" in publish


def test_the_publish_never_waves_through_a_dirty_tree():
    # --allow-dirty would publish a modified source file no tag points at.
    for run in (s.get("run", "") for s in _crates_io_job()["steps"]):
        assert "--allow-dirty" not in _shell_code(run)


# --- finalize asserts what it is about to publish (A1) -----------------------
#
# `finalize` flips the release from draft to public. Its only safeguard used to
# be its own `needs:` list, and a `needs:` list is a generated line: revert it
# and nothing fails -- finalize stops waiting and publishes a release with no
# artifacts on it. Ordering cannot report its own absence. These tests pin the
# two halves of the fix: a repository-local publish job is DECLARED rather than
# hand-edited into `needs:`, and finalize asks the release what it carries
# before it publishes.

DEB = {"job": "publish-deb-container", "assets": ["*.deb", "smtp-proxy-*-musl"]}


def _finalize(addons=(), local=()):
    text = assemble_publish(ASSETS, addons, MANIFEST, local)
    return yaml.safe_load(text)["jobs"]["finalize"]


def _finalize_script(addons=(), local=()):
    steps = _finalize(addons, local)["steps"]
    script = [s["with"]["script"] for s in steps if "github-script" in s.get("uses", "")]
    assert len(script) == 2
    return script[0]


def test_a_repository_local_publish_job_joins_finalizes_needs():
    # The whole point: smtp-proxy-rs's .deb job is not a standard add-on, so the
    # assembler used to generate `needs: [publish]` and the second entry was
    # added by hand -- and re-added by hand after every `apply`, or lost.
    assert _finalize(local=[DEB])["needs"] == ["publish", "publish-deb-container"]


def test_a_local_job_lands_after_the_standard_addons_in_needs():
    needs = _finalize(addons=["publish-crates-io"], local=[DEB])["needs"]
    assert needs == ["publish", "publish-crates-io", "publish-deb-container"]


def test_a_local_job_that_collides_with_a_generated_one_is_refused():
    # A duplicate in `needs:` is not fatal to GitHub, but it means the repository
    # believes it owns a job the assembler generates -- the next version of that
    # add-on would then fight the local block. Say so at assembly time.
    with pytest.raises(AssemblyError, match="already generated"):
        assemble_publish(ASSETS, ["publish-crates-io"], MANIFEST,
                         [{"job": "publish-crates-io", "assets": []}])


def test_a_local_entry_without_a_job_id_is_refused():
    with pytest.raises(AssemblyError, match="must name a job"):
        assemble_publish(ASSETS, [], MANIFEST, [{"assets": ["*.deb"]}])


def test_finalize_expects_the_assets_the_installed_blocks_attach():
    script = _finalize_script(addons=["publish-crates-io"], local=[DEB])
    assert "['*.deb', 'smtp-proxy-*-musl']" in script


def test_finalize_expects_nothing_from_a_block_that_attaches_nothing():
    # publish-crates-io uploads to an external registry and deliberately puts no
    # asset on the GitHub release. Expecting one would go red on every release.
    assert "const expected = [];" in _finalize_script(addons=["publish-crates-io"])


def test_finalize_asserts_the_assets_before_it_publishes():
    # Order is the fix. Asserting after updateRelease would report the fault on
    # a release that is already public, which is the state it exists to prevent.
    script = _finalize_script(local=[DEB])
    assert script.index("missingAssets") < script.index("draft: false")


def test_finalize_reads_the_release_rather_than_trusting_its_needs_list():
    script = _finalize_script(local=[DEB])
    assert "listReleaseAssets" in script


def test_finalize_fails_the_job_when_an_expected_asset_is_absent():
    script = _finalize_script(local=[DEB])
    assert "core.setFailed" in script


def test_the_assets_placeholder_appears_exactly_once():
    # Guards the asset the way the `needs:` placeholder is guarded: a finalize
    # block that lost this line would publish without asserting anything.
    text = (ASSETS / "publish/publish-finalize.yml").read_text(encoding="utf-8")
    assert text.count("            const expected = [];") == 1


def test_every_publish_block_declares_what_it_attaches():
    # Not optional: a new add-on that forgets this silently contributes nothing
    # to finalize's expectations, and the guard quietly stops covering it.
    for name, meta in MANIFEST["publish_blocks"].items():
        assert isinstance(meta.get("assets"), list), name


def test_an_asset_pattern_that_could_break_out_of_the_literal_is_refused():
    # The patterns are interpolated into a JavaScript string literal in the
    # generated workflow. A quote from a hand-written config would end that
    # literal and turn a declaration into code, in a job that holds
    # `contents: write`.
    with pytest.raises(AssemblyError, match="not an asset name pattern"):
        assemble_publish(ASSETS, [], MANIFEST,
                         [{"job": "x", "assets": ["'); throw new Error('"]}])


def _run_finalize(tmp_path, attached, local=(DEB,), workspace=ROOT):
    """Run the generated finalize script under node against a fake release.

    Substring assertions cannot answer the question that matters -- does this
    job publish a release that is missing its .deb? -- so this runs the real
    generated code, the same way test_the_reconcile_step_actually_leaves_the
    _tree_clean runs the real generated shell. `assets.js` is required from
    this repository's own installed copy, which test_self_render.py pins to
    the asset.
    """
    import os
    import re
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")

    script = _finalize_script(local=local)
    # The runner expands workflow expressions before node ever sees them.
    script = re.sub(r"\$\{\{[^}]*\}\}", "v1.2.3", script)

    harness = """
const assert = require('node:assert/strict');
const attached = %s;
const published = [];
const failures = [];
const deleted = [];
const order = [];
const github = {
  paginate: async () => attached.map((a, i) => (typeof a === 'string'
    ? { name: a, id: i + 1, state: 'uploaded' } : { id: i + 1, ...a })),
  rest: { repos: { listReleaseAssets: 'listReleaseAssets',
                   deleteReleaseAsset: async (a) => { order.push('delete'); deleted.push(a.asset_id); },
                   updateRelease: async (a) => { order.push('publish'); published.push(a); return { data: { html_url: 'u' } }; } } },
};
const core = {
  setFailed: (m) => failures.push(m),
  notice: () => {},
  summary: { addHeading() { return this; }, addRaw() { return this; },
             addLink() { return this; }, async write() {} },
};
const context = { repo: { owner: 'o', repo: 'r' } };
(async () => {
%s
})().then(() => {
  console.log(JSON.stringify({ published: published.length, failures, deleted, order }));
});
""" % (json.dumps(list(attached)), script)

    path = tmp_path / "finalize.js"
    path.write_text(harness, encoding="utf-8")
    proc = subprocess.run(
        [node, str(path)], capture_output=True, text=True, cwd=workspace,
        env={"GITHUB_WORKSPACE": str(workspace), "PATH": os.environ.get("PATH", "")})
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_the_generated_finalize_publishes_a_complete_release(tmp_path):
    out = _run_finalize(tmp_path, ["smtp-proxy_1.2.3-1_amd64.deb", "smtp-proxy-1.2.3-musl"])
    assert out["failures"] == []
    assert out["published"] == 1


def test_the_generated_finalize_refuses_a_release_with_no_assets(tmp_path):
    # A1 exactly: finalize's `needs:` was reverted, so it ran before the add-on
    # attached anything. Before this guard the release went public regardless.
    out = _run_finalize(tmp_path, [])
    assert out["published"] == 0
    assert len(out["failures"]) == 1
    assert "*.deb" in out["failures"][0]


def test_the_generated_finalize_refuses_a_release_that_is_missing_one_asset(tmp_path):
    out = _run_finalize(tmp_path, ["smtp-proxy-1.2.3-musl"])
    assert out["published"] == 0
    assert "*.deb" in out["failures"][0]


def test_the_generated_finalize_publishes_when_nothing_is_expected(tmp_path):
    # Most repositories install no asset-attaching block at all. The guard must
    # be a no-op for them, not a release that can never be published.
    out = _run_finalize(tmp_path, [], local=())
    assert out["failures"] == []
    assert out["published"] == 1


def _build_workspace(tmp_path, release_assets):
    ws = tmp_path / "ws"
    shutil.copytree(ROOT / ".github/workflows/lib", ws / ".github/workflows/lib")
    (ws / ".github/repo-infra.json").write_text(json.dumps(
        {"version_files": [], "release_assets": release_assets}))
    return ws


def test_finalize_asserts_release_assets_when_the_release_was_built(tmp_path):
    ws = _build_workspace(tmp_path, ["*.rpm"])
    out = _run_finalize(tmp_path, ["x_1.2.3_amd64.deb", "release-build.json"],
                        local=(), workspace=ws)
    assert out["published"] == 0 and "*.rpm" in out["failures"][0]
    assert out["deleted"] == []


def test_finalize_deletes_the_build_record_before_it_publishes(tmp_path):
    ws = _build_workspace(tmp_path, ["*.deb"])
    out = _run_finalize(tmp_path, ["x_1.2.3_amd64.deb", "release-build.json"],
                        local=(), workspace=ws)
    assert out["failures"] == [] and out["published"] == 1
    assert out["deleted"] == [2]
    assert out["order"] == ["delete", "publish"]


CRATES = {"packages": [
    {"name": "core-a", "version": "1.2.3", "publish": None},
    {"name": "app-b", "version": "1.2.3", "publish": None},
    {"name": "helper", "version": "0.0.0", "publish": []},
]}


def _run_crates_publish(tmp_path, on_crates_io, status_other="404"):
    """Run the block's own shell for the crates.io check and the publish.

    A fake cargo prints metadata and records `cargo publish` arguments; a fake
    curl answers 200 for every name/version in `on_crates_io`.
    """
    import os
    import subprocess

    if shutil.which("jq") is None:
        pytest.skip("jq is not installed")
    steps = _crates_io_job()["steps"]
    pending = next(s for s in steps if s.get("id") == "pending")["run"]
    publish = next(s for s in steps if "cargo publish" in s.get("run", ""))["run"]

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "log"
    (tmp_path / "metadata.json").write_text(json.dumps(CRATES), encoding="utf-8")
    (bin_dir / "cargo").write_text(
        '#!/bin/sh\n'
        f'if [ "$1" = metadata ]; then cat {tmp_path}/metadata.json; exit 0; fi\n'
        f'echo "cargo $*" >> {log}\n', encoding="utf-8")
    (bin_dir / "curl").write_text(
        '#!/bin/bash\n'
        'url="${@: -1}"\n'
        f'echo "curl $url" >> {log}\n'
        'case " $ON_CRATES_IO " in *" ${url#https://crates.io/api/v1/crates/} "*) '
        'printf 200;; *) printf "$STATUS_OTHER";; esac\n', encoding="utf-8")
    for tool in ("cargo", "curl"):
        (bin_dir / tool).chmod(0o755)
    output = tmp_path / "github_output"
    output.write_text("")
    env = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "GITHUB_OUTPUT": str(output),
           "ON_CRATES_IO": " ".join(on_crates_io), "STATUS_OTHER": status_other}

    first = subprocess.run(["bash", "-c", pending], cwd=tmp_path, env=env,
                           capture_output=True, text=True)
    result = {"pending_rc": first.returncode, "stdout": first.stdout, "stderr": first.stderr}
    if first.returncode == 0:
        outputs = dict(line.split("=", 1) for line in output.read_text().splitlines())
        second = subprocess.run(
            ["bash", "-c", publish], cwd=tmp_path, capture_output=True, text=True,
            env={**env, "PENDING": outputs["pending"], "EXCLUDE": outputs["exclude"]})
        result.update(publish_rc=second.returncode, publish_stdout=second.stdout)
    result["log"] = log.read_text().splitlines() if log.exists() else []
    return result


def test_the_crates_io_addon_publishes_every_crate_on_a_first_run(tmp_path):
    out = _run_crates_publish(tmp_path, [])
    assert out["publish_rc"] == 0
    assert "cargo publish --workspace --locked" in out["log"]


def test_the_crates_io_addon_excludes_a_crate_an_earlier_attempt_published(tmp_path):
    out = _run_crates_publish(tmp_path, ["core-a/1.2.3"])
    assert out["publish_rc"] == 0
    assert "cargo publish --workspace --locked --exclude core-a" in out["log"]
    assert "core-a 1.2.3 is already on crates.io" in out["stdout"]
    # publish = false is cargo's to skip; crates.io is never asked about it.
    assert not any("helper" in line for line in out["log"])


def test_the_crates_io_addon_skips_the_publish_when_every_crate_is_there(tmp_path):
    out = _run_crates_publish(tmp_path, ["core-a/1.2.3", "app-b/1.2.3"])
    assert out["publish_rc"] == 0
    assert not any(line.startswith("cargo publish") for line in out["log"])
    assert "already on crates.io" in out["publish_stdout"]


def test_the_crates_io_addon_fails_when_crates_io_does_not_answer(tmp_path):
    out = _run_crates_publish(tmp_path, [], status_other="503")
    assert out["pending_rc"] != 0
    assert "HTTP 503" in out["stderr"]


def test_the_generated_finalize_refuses_an_asset_whose_upload_did_not_finish(tmp_path):
    # GitHub lists a half-uploaded asset by name, so the name check passes it.
    out = _run_finalize(tmp_path, ["a.tar.gz", {"name": "x_1_amd64.deb", "state": "starter"}],
                        local=())
    assert out["published"] == 0
    assert len(out["failures"]) == 1
    assert "x_1_amd64.deb" in out["failures"][0] and "a.tar.gz" not in out["failures"][0]


def test_the_crates_io_addon_never_rewrites_the_lock():
    # The release pull request bumps Cargo.lock through version_files (D28).
    for run in (s.get("run", "") for s in _crates_io_job()["steps"]):
        assert "cargo update" not in _shell_code(run)
        assert "git" not in _shell_code(run).split()


def test_finalize_may_delete_runs():
    assert _finalize()["permissions"] == {"contents": "write", "actions": "write"}


def _parked_step():
    steps = _finalize()["steps"]
    return next(s for s in steps if s.get("name") == "Delete the parked runs of the release branch")


def _run_parked(tmp_path, runs, fail_list=False, fail_delete=()):
    import os
    import re
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = re.sub(r"\$\{\{[^}]*\}\}", "v1.2.3", _parked_step()["with"]["script"])
    # The helper under test is the installed copy of lib/release.js, driven
    # through a fake github: only the listing and the deletion are faked.
    harness = """
const runs = %s; const failList = %s; const failDelete = %s;
const deleted = []; const warnings = []; const listed = [];
const github = {
  // As GitHub does, the listing returns the runs whose status or conclusion
  // matches the `status` filter.
  paginate: async (fn, a) => {
    if (failList) throw new Error('Server Error');
    listed.push(a);
    return runs.filter((x) => x.status === a.status || x.conclusion === a.status);
  },
  rest: { actions: { listWorkflowRunsForRepo: 'list',
    listJobsForWorkflowRun: async (a) => ({
      data: { total_count: runs.find((x) => x.id === a.run_id).jobs } }),
    deleteWorkflowRun: async (a) => {
      if (failDelete.includes(a.run_id)) throw new Error(`Server Error on ${a.run_id}`);
      deleted.push(a.run_id);
    } } },
};
const core = { warning: (m) => warnings.push(m), setFailed: (m) => { throw new Error(m); } };
const context = { repo: { owner: 'o', repo: 'r' } };
(async () => {
%s
})().then(() => console.log(JSON.stringify({ deleted, warnings, listed })));
""" % (json.dumps(runs), "true" if fail_list else "false", json.dumps(list(fail_delete)),
       script)
    path = tmp_path / "parked.js"
    path.write_text(harness, encoding="utf-8")
    proc = subprocess.run([node, str(path)], capture_output=True, text=True, cwd=ROOT,
                          env={"GITHUB_WORKSPACE": str(ROOT), "PATH": os.environ["PATH"]})
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _parked(id, branch, conclusion="action_required", repo="o/r", jobs=0):
    # `jobs` is what the fake listJobsForWorkflowRun answers for this run.
    return {"id": id, "event": "pull_request", "head_branch": branch, "status": "completed",
            "conclusion": conclusion, "head_repository": {"full_name": repo}, "jobs": jobs,
            "actor": {"login": "github-actions[bot]"}}


def test_finalize_deletes_only_the_parked_runs_of_its_release_branch(tmp_path):
    out = _run_parked(tmp_path, [_parked(1, "release/v1.2.3"),
                                 _parked(2, "release/v1.2.3", conclusion="success"),
                                 _parked(3, "release/v1.2.2"),
                                 _parked(4, "release/v1.2.3", repo="fork/r"),
                                 # parked, then turned into failure by the merge
                                 _parked(5, "release/v1.2.3", conclusion="failure"),
                                 # approved, ran its jobs, failed: kept
                                 _parked(6, "release/v1.2.3", conclusion="failure", jobs=2)])
    assert out["deleted"] == [1, 5]
    assert {a["branch"] for a in out["listed"]} == {"release/v1.2.3"}
    assert {a["event"] for a in out["listed"]} == {"pull_request"}


def test_a_failed_listing_is_a_warning(tmp_path):
    out = _run_parked(tmp_path, [_parked(1, "release/v1.2.3")], fail_list=True)
    assert out["deleted"] == [] and "Server Error" in out["warnings"][0]


def test_a_failed_deletion_is_a_warning_and_the_others_are_deleted(tmp_path):
    runs = [_parked(1, "release/v1.2.3"), _parked(2, "release/v1.2.3"),
            _parked(3, "release/v1.2.3")]
    out = _run_parked(tmp_path, runs, fail_delete=[1])
    assert out["deleted"] == [2, 3]
    assert len(out["warnings"]) == 1 and "Server Error on 1" in out["warnings"][0]


def test_finalize_asserts_release_assets_for_every_repository(tmp_path):
    ws = _build_workspace(tmp_path, ["*.tar.gz"])
    out = _run_finalize(tmp_path, ["x.deb"], local=(), workspace=ws)
    assert out["published"] == 0 and "*.tar.gz" in out["failures"][0]
