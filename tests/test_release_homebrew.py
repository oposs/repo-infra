# tests/test_release_homebrew.py
"""ri-release-homebrew (D32). lib/homebrew.js holds the three formula steps
and homebrew.test.js their cases. Here: the jobs, the piece's calls into the
library, and that the formula the library tests use is the template the
shape reference publishes."""

import json
import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIECE = ROOT / ".github/workflows/ri-release-homebrew.yml"
LIB = ROOT / ".github/workflows/lib"
SHAPE = ROOT / "skills/repo-infra/references/project-shape.md"
FILLED = {"<Class>": "Tool", "<one-line description>": "A tool", "<owner>": "owner",
          "<repo>": "tool", "<SPDX license>": "MIT", "<bin>": "tool"}
LIBRARY = "require(`${process.env.GITHUB_WORKSPACE}/.repo-infra/.github/workflows/lib/homebrew.js`)"


def doc():
    return yaml.safe_load(PIECE.read_text(encoding="utf-8"))


def step(job, name):
    return next(s for s in doc()["jobs"][job]["steps"] if s.get("name") == name)


def test_the_bottle_legs_and_the_formula_condition():
    jobs = doc()["jobs"]
    assert jobs["bottles"]["strategy"]["matrix"]["include"] == [{"os": "macos-14"}]
    assert "continue-on-error" not in jobs["bottles"]
    assert jobs["formula"]["needs"] == "bottles"
    assert "if" not in jobs["formula"]


def test_brew_trust_runs_on_homebrew_6_and_a_failure_is_not_swallowed():
    tap = step("bottles", "Local tap")["run"]
    assert '-ge 6 ]' in tap and "brew trust --formula" in tap and "|| true" not in tap


def test_the_root_url_comes_from_the_repository_input():
    text = PIECE.read_text(encoding="utf-8")
    lib = (LIB / "homebrew.js").read_text(encoding="utf-8")
    assert "env.REPOSITORY" in lib and "GITHUB_REPOSITORY" not in lib
    assert "https://github.com/${repository}/releases/download/v${version}" in lib
    assert "oetiker" not in text and "oetiker" not in lib


@pytest.mark.parametrize("job,name,call", [
    ("bottles", "Point the formula at the built archives", "pointAtArchives(process.env)"),
    ("bottles", "Rename the bottles", "renameBottles()"),
    ("formula", "Rewrite the formula", "rewriteFormula(process.env)"),
])
def test_each_formula_step_runs_the_library_and_fails_with_its_message(job, name, call):
    found = step(job, name)
    assert found["uses"] == "actions/github-script@v9"
    script = found["with"]["script"]
    assert LIBRARY in script and call in script
    assert "core.setFailed(error.message)" in script
    assert "${{" not in script


def test_no_formula_logic_is_left_in_shell():
    runs = [s.get("run", "") for job in doc()["jobs"].values() for s in job["steps"]]
    for tool in ("awk ", "jq ", "sed -i", "sha256sum", "shasum"):
        assert not any(tool in run for run in runs), tool


def test_the_piece_names_the_library_it_runs():
    header = PIECE.read_text(encoding="utf-8").split("\n\n", 1)[0]
    assert "# Pieces: ri-release-rust-binaries" in header


def test_the_library_tests_use_the_template_of_the_shape_reference():
    section = SHAPE.read_text(encoding="utf-8").split("\n## Formula template\n", 1)[1]
    ruby = re.search(r"```ruby\n(.*?)```", section, re.S).group(1)
    for placeholder, value in FILLED.items():
        ruby = ruby.replace(placeholder, value)
    tests = (LIB / "homebrew.test.js").read_text(encoding="utf-8")
    assert re.search(r"const FORMULA = `(.*?)`;\n", tests, re.S).group(1) == ruby


JSONS = sorted((ROOT / "tests/fixtures/homebrew").glob("*.bottle.json"))


def test_the_recorded_bottle_json_has_the_keys_the_library_reads():
    """The json mtuspy's baseline run recorded on macos-14, against the keys
    homebrew.js reads and homebrew.test.js fakes."""
    assert len(JSONS) == 1
    tags = set()
    for path in JSONS:
        for entry in json.loads(path.read_text(encoding="utf-8")).values():
            bottle = entry["bottle"]
            for tag, data in bottle["tags"].items():
                assert {"filename", "local_filename", "sha256"} <= set(data), tag
                assert data.get("cellar") or bottle.get("cellar"), tag
                tags.add(tag)
    assert tags == {"arm64_sonoma"}


def test_the_bottle_root_url_names_the_repository_input():
    text = PIECE.read_text(encoding="utf-8")
    assert '--root-url="https://github.com/$REPOSITORY/releases/download/v$VERSION"' in text
    assert "REPOSITORY: ${{ inputs.repository }}" in text
