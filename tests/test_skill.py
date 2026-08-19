import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/repo-infra/SKILL.md"
ENTRY_POINT = ROOT / "skills/repo-infra/scripts/repo_infra"


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert match, "%s has no frontmatter" % path
    return dict(line.split(": ", 1) for line in match.group(1).splitlines() if ": " in line)


def test_the_skill_declares_a_name_and_a_triggering_description():
    data = frontmatter(SKILL)
    assert data["name"] == "repo-infra"
    assert len(data["description"]) > 80, "a thin description will not trigger"


def test_both_commands_exist_and_declare_a_description():
    for name in ("check", "apply"):
        assert frontmatter(ROOT / "commands" / (name + ".md"))["description"]


def test_the_skill_points_at_the_entry_point_that_exists():
    assert (ROOT / "skills/repo-infra/scripts/repo_infra/__main__.py").is_file()
    assert "scripts/repo_infra" in SKILL.read_text(encoding="utf-8")


def test_the_references_the_skill_names_are_there():
    for name in ("release-flow", "conventions"):
        assert (ROOT / "skills/repo-infra/references" / (name + ".md")).is_file()


def test_the_entry_point_runs_exactly_as_the_skill_and_commands_invoke_it():
    """Every doc in this plugin says `python3 "${CLAUDE_PLUGIN_ROOT}/skills/
    repo-infra/scripts/repo_infra" check|apply` -- running the package
    directory directly, no PYTHONPATH, no pip install. That is a different
    invocation from `python3 -m repo_infra` (cli.py's own docstring) and
    fails with "attempted relative import with no known parent package"
    unless __main__.py puts scripts/ on sys.path itself: a plain `python3
    <package dir>` only adds that directory, not its parent, so `from .cli
    import main` has no package context. No prior test exercised this
    subprocess form, so nothing caught it landing broken.
    """
    result = subprocess.run([sys.executable, str(ENTRY_POINT), "--help"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "check" in result.stdout and "apply" in result.stdout
