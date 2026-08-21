import json
import pathlib

from repo_infra.markers import parse_markers

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
FRAGMENT = ASSETS / "build/container-test.mk"


def test_the_fragment_is_declared_in_the_manifest():
    spec = MANIFEST["build_assets"]["container-test"]
    assert spec["source"] == "build/container-test.mk"
    assert spec["target"] == "build/container-test.mk"
    assert spec["comment"] == "#"


def test_the_fragment_carries_its_marker_at_the_declared_version():
    text = FRAGMENT.read_text(encoding="utf-8")
    version = MANIFEST["build_assets"]["container-test"]["version"]
    assert ("container-test", version) in [(m.asset, m.version) for m in parse_markers(text)]


def test_a_repository_that_did_not_ask_for_it_does_not_get_it():
    # D16: containerization is a decision, not a detection. An autotools repo
    # that stayed native must not be told it is missing a file it never chose.
    import pathlib as _p

    from repo_infra.assemble import render_all
    from repo_infra.detect import Detection
    result = Detection.load(ASSETS / "detection.json").detect(_p.Path(ROOT))
    assert "build/container-test.mk" not in render_all(ASSETS, result, MANIFEST)
    assert "build/container-test.mk" in render_all(
        ASSETS, result, MANIFEST, build=["container-test"])


def test_the_fragment_defines_the_two_targets_the_ci_block_calls():
    text = FRAGMENT.read_text(encoding="utf-8")
    assert "\ncontainer:" in text
    assert "\ntest: container" in text


def test_the_fragment_has_no_substitution_tokens():
    # D15: an asset is the literal file it installs. Parameterization is by make
    # variable at run time, never by rewriting the file at install time.
    text = FRAGMENT.read_text(encoding="utf-8")
    for token in ("$VERSION", "{{", "@PACKAGE@"):
        assert token not in text


def test_the_fragment_fails_when_no_tests_are_found():
    # An empty test glob must not report success. Silence is the failure mode
    # that makes a containerized suite look green while running nothing.
    text = FRAGMENT.read_text(encoding="utf-8")
    assert "no test files" in text
