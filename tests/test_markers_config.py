import configparser
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _pytest_ini():
    parser = configparser.ConfigParser()
    parser.read(ROOT / "pytest.ini")
    return parser["pytest"]


def test_the_container_marker_is_registered():
    # An unregistered marker is a warning today and an error under
    # --strict-markers; either way a typo would silently deselect nothing.
    assert "container" in _pytest_ini().get("markers", "")


def test_container_tests_are_deselected_by_default():
    # D19: the ordinary gate must stay sub-second and must not need podman.
    # A developer with no container engine runs the suite unaffected.
    # Exact equality, not containment: addopts (this deselect) and the
    # self-test job's explicit "-m container" (that select) are independent
    # strings that don't cross-check each other. A typo here (e.g. "not
    # containerized") would still let "-m container" select its 5 tests in
    # CI, so the job stays green while the ordinary local gate silently stops
    # deselecting and starts driving podman -- loud on a podman-less
    # developer's machine, silent everywhere else. Containment would not
    # catch that typo; equality does.
    assert _pytest_ini().get("addopts", "").strip() == '-m "not container"'
