"""The prose skills (D23): present, triggerable, and written in the style
they teach."""

import json
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
PROSE_SKILLS = ["writing-style", "man-pages"]
TERM_EXAMPLE = "- `--listen <ip:port>`: Address and port to listen on."
LUA = ROOT / "skills/repo-infra/assets/pieces/man-lua/man-deflist.lua"


def skill(name):
    return SKILLS / name / "SKILL.md"


def term_list_blocks(path):
    """The skill's own fenced ```markdown examples that are term lists: every
    non-blank line starts with "- `" (the man-deflist filter's input)."""
    text = path.read_text(encoding="utf-8")
    found = []
    for indent, block in re.findall(r"^([ \t]*)```markdown\n((?:.*\n)*?)\1```", text, re.M):
        lines = [line[len(indent):] for line in block.splitlines() if line.strip()]
        if lines and all(line.startswith("- `") for line in lines):
            found.append("\n".join(lines))
    return found


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert match, "%s has no frontmatter" % path
    return dict(line.split(": ", 1) for line in match.group(1).splitlines() if ": " in line)


def prose_lines(path):
    """The lines a reader takes as prose: not frontmatter, not fenced code,
    not table rows."""
    text = path.read_text(encoding="utf-8")
    body = re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.S)
    lines, fenced = [], False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced or line.lstrip().startswith("|"):
            continue
        lines.append(line)
    return lines


def without_code(text):
    return re.sub(r"`[^`]*`", "", text)


def headings(path, min_level=2):
    return [line.lstrip("#").strip() for line in prose_lines(path)
            if re.match(r"^#{%d,6} " % min_level, line)]


@pytest.mark.parametrize("name", PROSE_SKILLS)
def test_the_skill_declares_its_name_and_a_triggering_description(name):
    data = frontmatter(skill(name))
    assert data["name"] == name
    assert 80 < len(data["description"]) <= 1024


@pytest.mark.parametrize("name", PROSE_SKILLS)
def test_the_skill_has_no_em_dash_anywhere(name):
    # Owner ruling, 2026-09-23: not in prose, not in examples, not in lists.
    text = skill(name).read_text(encoding="utf-8")
    assert "\u2014" not in text


@pytest.mark.parametrize("name", PROSE_SKILLS)
def test_the_skill_writes_for_example_in_full(name):
    for line in prose_lines(skill(name)):
        assert "e.g." not in without_code(line), line


@pytest.mark.parametrize("name", PROSE_SKILLS)
def test_the_skill_headings_are_sentence_case_without_emoji(name):
    for heading in headings(skill(name)):
        assert all(ord(c) < 0x2000 for c in heading), "emoji or symbol in %r" % heading
        words = re.findall(r"[A-Za-z][A-Za-z'-]*", without_code(heading))
        for word in words[1:]:
            assert not (word[0].isupper() and not word.isupper()), (
                "%r is not sentence case" % heading)


@pytest.mark.parametrize("name", PROSE_SKILLS)
def test_the_skill_ships_its_eval_set(name):
    evals = json.loads((SKILLS / name / "evals/evals.json").read_text(encoding="utf-8"))
    assert evals["skill_name"] == name
    assert len(evals["evals"]) >= 2
    for case in evals["evals"]:
        assert case["expectations"], case["id"]
        for path in case.get("files", []):
            assert (SKILLS / name / path).is_file(), path
    triggers = json.loads(
        (SKILLS / name / "evals/trigger-evals.json").read_text(encoding="utf-8"))
    assert any(q["should_trigger"] for q in triggers)
    assert any(not q["should_trigger"] for q in triggers)


def test_writing_style_carries_the_manual_before_and_after_pair():
    text = skill("writing-style").read_text(encoding="utf-8")
    assert "so the two\ncannot drift apart" in text   # before, from mdmost fef7f53
    assert "name the bindings in effect" in text        # after


def test_writing_style_states_the_term_list_form():
    text = skill("writing-style").read_text(encoding="utf-8")
    assert TERM_EXAMPLE in text
    assert "No em dashes" in text


@pytest.mark.pandoc
@pytest.mark.parametrize("name", PROSE_SKILLS)
def test_the_skills_own_term_list_examples_convert_to_a_definition_list(name, require):
    # A skill's example is what a reader copies. If it does not survive the
    # filter it teaches, the skill is wrong (D23).
    require("pandoc")
    blocks = term_list_blocks(skill(name))
    assert blocks, "%s has no term-list example for the filter to convert" % name
    for block in blocks:
        done = subprocess.run(
            ["pandoc", "--lua-filter", str(LUA), "-t", "native"],
            input=block, capture_output=True, text=True, timeout=60, check=True)
        assert "DefinitionList" in done.stdout, (name, block, done.stdout)
        assert "BulletList" not in done.stdout, (name, block, done.stdout)


def test_writing_style_carries_the_changelog_rules_and_the_comment_example():
    text = skill("writing-style").read_text(encoding="utf-8")
    for rule in ("Three sentences at most", "round brackets", "release headers",
                 "commit message", "Cargo.lock still at 0.1.0"):
        assert rule in text, rule


SECTION_ORDER = ["NAME", "SYNOPSIS", "CONFIGURATION", "DESCRIPTION", "OPTIONS",
                 "EXIT STATUS", "ENVIRONMENT", "FILES", "VERSIONS", "STANDARDS",
                 "HISTORY", "NOTES", "CAVEATS", "BUGS", "EXAMPLES", "SEE ALSO"]


def test_man_pages_states_the_section_order_of_man_pages_7():
    assert "\n".join(SECTION_ORDER) in skill("man-pages").read_text(encoding="utf-8")


def test_man_pages_shows_the_term_list_form_and_names_every_setup_step():
    text = skill("man-pages").read_text(encoding="utf-8")
    for needle in (TERM_EXAMPLE, "MAN_NAME = ", "include build/man.mk", "man/\n",
                   '"ci": ["ci-man"]', "make man", "usr/share/man/man1/"):
        assert needle in text, needle


def test_man_pages_names_the_warning_ci_man_fails_on():
    text = skill("man-pages").read_text(encoding="utf-8")
    assert "table wider than line length minus indentation" in text


def test_man_pages_leaves_the_voice_to_writing_style():
    # The voice rules live in one place. A second copy drifts from the first.
    text = skill("man-pages").read_text(encoding="utf-8")
    assert "writing-style" in text
    assert "present tense" not in text.lower()
    assert "third person" not in text.lower()
