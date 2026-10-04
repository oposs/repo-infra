# tests/test_manifest.py
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"


def manifest():
    return json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))


def test_manifest_parses():
    assert set(manifest()) == {"pieces", "actions", "gh"}


def test_action_majors_are_recorded_as_majors():
    for action, version in manifest()["actions"].items():
        assert version.startswith("v") and version[1:].isdigit(), "%s: %s" % (action, version)
