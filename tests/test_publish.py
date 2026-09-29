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
    assert ("release-publish", 4) in [(m.asset, m.version) for m in parse_markers(text)]


def test_an_unknown_addon_is_an_assembly_error():
    with pytest.raises(AssemblyError, match="not declared in the manifest"):
        assemble_publish(ASSETS, ["publish-nonexistent"], MANIFEST)


def test_the_placeholder_must_appear_exactly_once():
    # Guards the asset, not the code: a finalize block that lost its
    # placeholder would silently publish a release before the add-ons ran.
    text = (ASSETS / "publish/publish-finalize.yml").read_text(encoding="utf-8")
    assert text.count("    needs: []") == 1


def test_the_tarball_addon_lands_between_publish_and_finalize():
    text = assemble_publish(ASSETS, ["publish-source-tarball"], MANIFEST)
    assert "    needs: [publish, publish-source-tarball]" in text
    assert text.index("  publish-source-tarball:") < text.index("  finalize:")


def test_the_tarball_addon_carries_its_marker():
    text = assemble_publish(ASSETS, ["publish-source-tarball"], MANIFEST)
    assert ("publish-source-tarball", 3) in [
        (m.asset, m.version) for m in parse_markers(text)]


def test_the_tarball_addon_declares_exactly_the_job_it_contains():
    from repo_infra.assemble import block_job_ids
    text = (ASSETS / "publish/publish-source-tarball.yml").read_text(encoding="utf-8")
    assert block_job_ids(text) == MANIFEST["publish_blocks"]["publish-source-tarball"]["jobs"]


def test_the_tarball_addon_refuses_to_upload_nothing():
    # A `make dist` that produced no tarball must fail the job, not publish a
    # release with no artifact. Guard the guard: this is the whole point of the
    # add-on and it is one easily-deleted line.
    text = (ASSETS / "publish/publish-source-tarball.yml").read_text(encoding="utf-8")
    assert "no tarball" in text


def test_the_tarball_block_can_drive_a_container():
    # `make dist` is a container call in driver mode (D18), so the runner needs
    # an engine. Without it configure fails before dist is ever reached.
    text = (ASSETS / "publish/publish-source-tarball.yml").read_text(encoding="utf-8")
    assert "autoconf automake gettext podman" in text
    assert "Known limit" not in text


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

    The block explains in comments why it does NOT use `--allow-dirty` or
    `|| true`. Those comments live inside the run string, so a plain substring
    search cannot tell the explanation from the thing it warns against.
    """
    return "\n".join(
        line for line in run.splitlines() if not line.strip().startswith("#"))


def test_the_crates_io_addon_lands_between_publish_and_finalize():
    text = assemble_publish(ASSETS, ["publish-crates-io"], MANIFEST)
    assert "    needs: [publish, publish-crates-io]" in text
    assert text.index("  publish-crates-io:") < text.index("  finalize:")


def test_the_crates_io_addon_carries_its_marker():
    text = assemble_publish(ASSETS, ["publish-crates-io"], MANIFEST)
    assert ("publish-crates-io", 2) in [
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


def test_the_lock_is_reconciled_before_the_publish_not_after():
    # Order is the whole fix. Reversed, `--locked` sees the release pull
    # request's Cargo.toml bump against an unbumped Cargo.lock and fails on
    # every release.
    runs = [s.get("run", "") for s in _crates_io_job()["steps"]]
    update = next(i for i, r in enumerate(runs) if "cargo update" in r)
    publish = next(i for i, r in enumerate(runs) if "cargo publish" in r)
    assert update < publish


def test_the_lock_reconciliation_moves_no_dependency():
    # `cargo update` unscoped re-resolves every dependency, which would publish
    # something the tag never locked. `--workspace` keeps it to the workspace's
    # own entries -- that restriction is what makes the step safe here.
    runs = [s.get("run", "") for s in _crates_io_job()["steps"]]
    update = next(r for r in runs if "cargo update" in r)
    assert "--workspace" in update
    assert "--offline" not in update


def test_no_step_swallows_its_own_failure():
    # mdmost v0.1.1: a swallowed bump failure tagged 0.1.1 with the lock still
    # at 0.1.0, and the publish died 6 minutes later.
    for run in (s.get("run", "") for s in _crates_io_job()["steps"]):
        assert "|| true" not in _shell_code(run)


def test_the_publish_covers_the_whole_workspace_and_stays_locked():
    # --workspace is what serves the multi-crate consumer in one invocation;
    # --locked is what still guards dependency drift after the update above.
    runs = [s.get("run", "") for s in _crates_io_job()["steps"]]
    publish = next(r for r in runs if "cargo publish" in r)
    assert "--workspace" in publish
    assert "--locked" in publish


def test_the_reconciled_lock_is_committed_before_packaging():
    # cargo refuses to publish from a tree with uncommitted changes, and the
    # reconcile step rewrites Cargo.lock -- so the commit is what makes the
    # publish reachable at all. Proven against oetiker/tvision-rs: without it
    # the job packages both crates and then dies with "1 files in the working
    # directory contain changes that were not yet committed into git".
    runs = [s.get("run", "") for s in _crates_io_job()["steps"]]
    reconcile = next(r for r in runs if "cargo update" in r)
    assert "git" in reconcile and "commit" in reconcile


def test_the_publish_never_waves_through_a_dirty_tree():
    # --allow-dirty is the tempting one-word alternative to the commit above.
    # It also publishes a modified *source* file that no tag ever pointed at.
    for run in (s.get("run", "") for s in _crates_io_job()["steps"]):
        assert "--allow-dirty" not in _shell_code(run)


def test_the_reconcile_step_actually_leaves_the_tree_clean():
    """Run the block's own reconcile shell against a throwaway git tree.

    The requirement is behavioural -- after this step `cargo publish` must find
    nothing uncommitted -- and no substring assertion can check it: `true; git
    commit ...` still contains the words. Proven necessary against
    oetiker/tvision-rs, where the missing commit made the job package both
    crates and then die on the dirty Cargo.lock.
    """
    import re
    import shutil
    import subprocess
    import tempfile

    run = next(r for r in (s.get("run", "") for s in _crates_io_job()["steps"])
               if "cargo update" in r)
    # The runner expands workflow expressions before bash ever sees them.
    script = re.sub(r"\$\{\{[^}]*\}\}", "v1.2.3", run)

    with tempfile.TemporaryDirectory() as tmp:
        tree = pathlib.Path(tmp) / "tree"
        tree.mkdir()
        git = ["git", "-c", "user.email=t@e", "-c", "user.name=t"]
        subprocess.run(["git", "init", "-q", "-b", "main", str(tree)], check=True)
        (tree / "Cargo.lock").write_text('version = "0.1.0"\n', encoding="utf-8")
        subprocess.run(git + ["add", "Cargo.lock"], cwd=tree, check=True)
        subprocess.run(git + ["commit", "-qm", "seed"], cwd=tree, check=True)

        # A stand-in cargo that does what `cargo update --workspace` does to the
        # tree: rewrite Cargo.lock. Nothing here needs the real toolchain.
        bin_dir = pathlib.Path(tmp) / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "cargo"
        fake.write_text(
            '#!/bin/sh\nprintf \'version = "1.2.3"\\n\' > Cargo.lock\n', encoding="utf-8")
        fake.chmod(0o755)
        env = {
            "PATH": f"{bin_dir}:{shutil.which('git') and '/usr/bin'}:/bin:/usr/bin",
            "HOME": tmp,
        }

        proc = subprocess.run(["bash", "-c", script], cwd=tree, env=env,
                              capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr

        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=tree,
                               capture_output=True, text=True, check=True).stdout
        assert dirty == "", f"cargo publish would refuse this tree:\n{dirty}"

        # And it is idempotent: a re-run has nothing to commit, which `git
        # commit` reports as an error unless the step guards for it.
        again = subprocess.run(["bash", "-c", script], cwd=tree, env=env,
                               capture_output=True, text=True)
        assert again.returncode == 0, again.stderr


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
    assert len(script) == 1
    return script[0]


def test_a_repository_local_publish_job_joins_finalizes_needs():
    # The whole point: smtp-proxy-rs's .deb job is not a standard add-on, so the
    # assembler used to generate `needs: [publish]` and the second entry was
    # added by hand -- and re-added by hand after every `apply`, or lost.
    assert _finalize(local=[DEB])["needs"] == ["publish", "publish-deb-container"]


def test_a_local_job_lands_after_the_standard_addons_in_needs():
    needs = _finalize(addons=["publish-source-tarball"], local=[DEB])["needs"]
    assert needs == ["publish", "publish-source-tarball", "publish-deb-container"]


def test_a_local_job_that_collides_with_a_generated_one_is_refused():
    # A duplicate in `needs:` is not fatal to GitHub, but it means the repository
    # believes it owns a job the assembler generates -- the next version of that
    # add-on would then fight the local block. Say so at assembly time.
    with pytest.raises(AssemblyError, match="already generated"):
        assemble_publish(ASSETS, ["publish-source-tarball"], MANIFEST,
                         [{"job": "publish-source-tarball", "assets": []}])


def test_a_local_entry_without_a_job_id_is_refused():
    with pytest.raises(AssemblyError, match="must name a job"):
        assemble_publish(ASSETS, [], MANIFEST, [{"assets": ["*.deb"]}])


def test_finalize_expects_the_assets_the_installed_blocks_attach():
    script = _finalize_script(addons=["publish-source-tarball"], local=[DEB])
    assert "['*.tar.gz', '*.deb', 'smtp-proxy-*-musl']" in script


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
    import json as _json
    import os
    import re
    import shutil
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
  paginate: async () => attached.map((name, i) => ({ name, id: i + 1 })),
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
""" % (_json.dumps(list(attached)), script)

    path = tmp_path / "finalize.js"
    path.write_text(harness, encoding="utf-8")
    proc = subprocess.run(
        [node, str(path)], capture_output=True, text=True, cwd=workspace,
        env={"GITHUB_WORKSPACE": str(workspace), "PATH": os.environ.get("PATH", "")})
    assert proc.returncode == 0, proc.stderr
    return _json.loads(proc.stdout)


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
        {"version_files": [], "release_build": True, "release_assets": release_assets}))
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
