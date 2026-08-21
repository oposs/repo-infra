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
