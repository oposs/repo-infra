import json
import pathlib

import pytest

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
