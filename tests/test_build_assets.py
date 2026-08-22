import json
import pathlib

from repo_infra.markers import parse_markers

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
FRAGMENT = ASSETS / "build/container.mk"


def test_the_fragment_is_declared_in_the_manifest():
    spec = MANIFEST["build_assets"]["container"]
    assert spec["source"] == "build/container.mk"
    assert spec["target"] == "build/container.mk"
    assert spec["comment"] == "#"


def test_the_old_test_only_fragment_is_gone():
    # D18 replaced it. Leaving both would ship two answers to one question.
    assert "container-test" not in MANIFEST["build_assets"]
    assert not (ASSETS / "build/container-test.mk").exists()


def test_the_fragment_carries_its_marker_at_the_declared_version():
    text = FRAGMENT.read_text(encoding="utf-8")
    version = MANIFEST["build_assets"]["container"]["version"]
    assert ("container", version) in [(m.asset, m.version) for m in parse_markers(text)]


def test_a_repository_that_did_not_ask_for_it_does_not_get_it():
    # D16: containerization is a decision, not a detection.
    import pathlib as _p

    from repo_infra.assemble import render_all
    from repo_infra.detect import Detection
    result = Detection.load(ASSETS / "detection.json").detect(_p.Path(ROOT))
    assert "build/container.mk" not in render_all(ASSETS, result, MANIFEST)
    assert "build/container.mk" in render_all(
        ASSETS, result, MANIFEST, build=["container"])


def test_every_driver_target_is_inside_the_conditional():
    # The whole point of D18's conditional: inside the container this file must
    # define nothing, or `make test` there would invoke podman inside podman.
    text = FRAGMENT.read_text(encoding="utf-8")
    body = text.split("if CONTAINER_DRIVER", 1)[1].split("\nendif", 1)[0]
    for target in ("container:", "container-base:", "test:", "test-dev:"):
        assert "\n" + target in body, "%s is outside the conditional" % target
    assert "$(DOCKER)" not in text.split("if CONTAINER_DRIVER", 1)[0]


def test_test_dev_does_not_rebuild_the_full_image():
    # Depending on `container` would rebuild on every source edit and delete the
    # entire point of the target.
    text = FRAGMENT.read_text(encoding="utf-8")
    line = [l for l in text.splitlines() if l.startswith("test-dev:")][0]
    assert "container-base" in line
    assert "test-dev: container\n" not in text


def test_test_dev_requires_a_target():
    text = FRAGMENT.read_text(encoding="utf-8")
    assert "TARGET is required" in text
    assert "make test-dev TARGET=" in text


def test_the_fragment_no_longer_carries_the_test_runner_knobs():
    # D18: inside the container the project runs its own native `make test`, so
    # how the suite is invoked is the project's business again.
    text = FRAGMENT.read_text(encoding="utf-8")
    for knob in ("TEST_RUNNER", "TEST_DIR", "SKIP_TESTS"):
        assert knob not in text


def test_the_engine_comes_from_configure_not_a_make_default():
    # AC_CHECK_PROGS finds podman or docker and substitutes it, so a project with
    # only docker installed needs to do nothing.
    text = FRAGMENT.read_text(encoding="utf-8")
    assert "DOCKER ?=" not in text
    assert "$(DOCKER)" in text


def test_the_dev_mounts_are_declared_by_the_project():
    # The fragment cannot know which directories hold interpreted source, and a
    # blanket overlay would hide everything configure generated in the image.
    text = FRAGMENT.read_text(encoding="utf-8")
    assert "TEST_DEV_MOUNTS" in text
    assert "-v $(abs_top_srcdir):/src" not in text


def test_no_ci_block_calls_the_dev_loop():
    # test-dev is a developer convenience. What CI must verify is that the image
    # builds and its contents pass, which is `make test`.
    for path in sorted((ASSETS / "ci").glob("*.yml")) + sorted((ASSETS / "publish").glob("*.yml")):
        assert "test-dev" not in path.read_text(encoding="utf-8"), path.name


def test_the_fragment_has_no_host_package_declaration():
    # D16: wanting one is the trigger to containerize, not a missing feature.
    text = FRAGMENT.read_text(encoding="utf-8")
    for shape in ("apt-packages", "system_packages", "apt-get"):
        assert shape not in text


def test_the_fragment_has_no_substitution_tokens():
    # D15: an asset is the literal file it installs.
    text = FRAGMENT.read_text(encoding="utf-8")
    for token in ("$VERSION", "{{", "@PACKAGE@"):
        assert token not in text
