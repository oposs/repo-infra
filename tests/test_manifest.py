# tests/test_manifest.py
import json
import pathlib
import re

import pytest

from repo_infra.markers import parse_markers, ASSET_ID

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"


def manifest():
    return json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))


def asset_files(name, spec):
    """Every file belonging to one asset."""
    source = ASSETS / spec["source"]
    if spec.get("kind") == "dir":
        return sorted(p for p in source.iterdir() if p.is_file())
    return [source]


def test_manifest_parses():
    data = manifest()
    assert set(data) == {"assets", "ci_blocks", "actions"}


def test_every_declared_asset_exists():
    for name, spec in manifest()["assets"].items():
        assert (ASSETS / spec["source"]).exists(), "%s: missing %s" % (name, spec["source"])


def test_every_asset_id_matches_the_pattern():
    for name in manifest()["assets"]:
        assert ASSET_ID, "ASSET_ID is not exported from markers"
        assert re.match("^" + ASSET_ID + "$", name), "%s does not match ASSET_ID pattern" % name


@pytest.mark.parametrize("name", sorted(manifest()["assets"]))
def test_every_asset_file_carries_its_own_marker_at_the_declared_version(name):
    spec = manifest()["assets"][name]
    for path in asset_files(name, spec):
        found = parse_markers(path.read_text(encoding="utf-8"))
        assert found, "%s: no marker in %s" % (name, path)
        assert found[0].asset == name, "%s: %s claims to be %s" % (name, path, found[0].asset)
        assert found[0].version == spec["version"], "%s: %s is v%d, manifest says v%d" % (
            name, path, found[0].version, spec["version"])


def test_action_majors_are_recorded_as_majors():
    for action, version in manifest()["actions"].items():
        assert version.startswith("v") and version[1:].isdigit(), "%s: %s" % (action, version)
