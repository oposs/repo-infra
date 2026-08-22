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


def test_the_report_points_at_a_reference_that_exists():
    # report.py names this file by path. A rename that misses one of the two
    # leaves an operator following a dead pointer at exactly the moment the
    # tool has told them it cannot help.
    from repo_infra import report
    source = pathlib.Path(report.__file__).read_text(encoding="utf-8")
    assert "references/teaching-the-standard.md" in source
    assert (ROOT / "skills/repo-infra/references/teaching-the-standard.md").is_file()


def test_conventions_states_the_containerfile_contract():
    # D18: repo-infra owns the shape, the project owns the file. The contract is
    # the only thing standing between them, so it has to be written down.
    text = (ROOT / "skills/repo-infra/references/conventions.md").read_text(encoding="utf-8")
    assert "--disable-container" in text
    assert "/src" in text
    assert "container-m4" in text
    # The old test-only asset id must not survive anywhere in the docs.
    assert "container-test" not in text


def test_the_teach_reference_points_at_the_driver_not_the_test_fragment():
    text = (ROOT / "skills/repo-infra/references/teaching-the-standard.md").read_text(
        encoding="utf-8")
    assert "container-test" not in text
    assert "build/container.mk" in text


def test_conventions_documents_the_makefile_am_guard_against_the_automake_warning():
    # A project that defines its own `test:` for the native case AND includes
    # build/container.mk gets an automake "was already defined in condition
    # TRUE" warning unless it guards its own target with the negated
    # conditional. This is as load-bearing as the Containerfile contract, so it
    # has to be written down too.
    text = (ROOT / "skills/repo-infra/references/conventions.md").read_text(encoding="utf-8")
    assert "if !CONTAINER_DRIVER" in text
