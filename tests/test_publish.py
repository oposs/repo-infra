import json
import pathlib

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
    assert ("release-publish", 2) in [(m.asset, m.version) for m in parse_markers(text)]


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
    assert ("publish-source-tarball", 2) in [
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


def test_the_crates_io_addon_lands_between_publish_and_finalize():
    text = assemble_publish(ASSETS, ["publish-crates-io"], MANIFEST)
    assert "    needs: [publish, publish-crates-io]" in text
    assert text.index("  publish-crates-io:") < text.index("  finalize:")


def test_the_crates_io_addon_carries_its_marker():
    text = assemble_publish(ASSETS, ["publish-crates-io"], MANIFEST)
    assert ("publish-crates-io", 1) in [
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
        assert "|| true" not in run


def test_the_publish_covers_the_whole_workspace_and_stays_locked():
    # --workspace is what serves the multi-crate consumer in one invocation;
    # --locked is what still guards dependency drift after the update above.
    runs = [s.get("run", "") for s in _crates_io_job()["steps"]]
    publish = next(r for r in runs if "cargo publish" in r)
    assert "--workspace" in publish
    assert "--locked" in publish
