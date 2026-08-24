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
    assert 'not container' in _pytest_ini().get("addopts", "")
