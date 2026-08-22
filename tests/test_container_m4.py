import json
import pathlib

from repo_infra.markers import parse_markers

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
MACRO = ASSETS / "m4/repo-infra-container.m4"


def test_the_macro_is_declared_in_the_manifest():
    spec = MANIFEST["build_assets"]["container-m4"]
    assert spec["source"] == "m4/repo-infra-container.m4"
    assert spec["target"] == "m4/repo-infra-container.m4"
    assert spec["comment"] == "dnl"


def test_the_macro_carries_its_marker_at_the_declared_version():
    version = MANIFEST["build_assets"]["container-m4"]["version"]
    text = MACRO.read_text(encoding="utf-8")
    assert ("container-m4", version) in [(m.asset, m.version) for m in parse_markers(text)]


def test_the_flag_defaults_to_driving_the_container():
    # D18: the default is the caller you do not control. A stranger with a
    # checkout types ./configure and must not be asked for librrd.
    text = MACRO.read_text(encoding="utf-8")
    assert "AC_ARG_ENABLE([container]" in text
    assert "enable_container=yes" in text
    assert "--disable-container" in text
    # The flag names the semantics, not the location.
    assert "in-container" not in text


def test_driver_mode_probes_only_the_engine_and_the_containerfile():
    text = MACRO.read_text(encoding="utf-8")
    assert "AC_CHECK_PROGS([DOCKER], [podman docker])" in text
    assert "Containerfile" in text


def test_the_error_message_names_the_way_out():
    # A missing engine must not read as "this repository is broken".
    text = MACRO.read_text(encoding="utf-8")
    for message in text.split("AC_MSG_ERROR")[1:]:
        assert "--disable-container" in message.split("])")[0]


def test_it_exports_the_conditional_the_fragment_keys_off():
    text = MACRO.read_text(encoding="utf-8")
    assert "AM_CONDITIONAL([CONTAINER_DRIVER]" in text
    # Not the same identifier as the macro itself.
    assert "AM_CONDITIONAL([REPO_INFRA_CONTAINER]" not in text


def test_a_repository_that_did_not_ask_for_it_does_not_get_it():
    # D16: containerization is a decision, not a detection. Both halves of the
    # pair are selected the same way and neither ships unasked.
    import pathlib as _p

    from repo_infra.assemble import render_all
    from repo_infra.detect import Detection
    result = Detection.load(ASSETS / "detection.json").detect(_p.Path(ROOT))
    assert "m4/repo-infra-container.m4" not in render_all(ASSETS, result, MANIFEST)
    assert "m4/repo-infra-container.m4" in render_all(
        ASSETS, result, MANIFEST, build=["container-m4"])


def test_the_macro_has_no_substitution_tokens():
    # D15: an asset is the literal file it installs.
    text = MACRO.read_text(encoding="utf-8")
    for token in ("$VERSION", "{{", "@PACKAGE@"):
        assert token not in text
