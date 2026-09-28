"""No em dash in anything the plugin ships (owner ruling, 2026-09-23).

Dated history keeps its dashes: the specs and plans under docs/superpowers/ and
the released sections of CHANGES.md. The writing-style eval inputs carry em
dashes on purpose, because the skill is tested on removing them.
"""

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DASH = "\u2014"


def shipped():
    files = [ROOT / "README.md", ROOT / "RELEASING.md"]
    for top in ("skills", "commands", ".claude-plugin", ".github"):
        files += [p for p in (ROOT / top).rglob("*") if p.is_file()]
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        if "/evals/" in rel or path.suffix in (".pyc",):
            continue
        yield rel


@pytest.mark.parametrize("rel", sorted(shipped()))
def test_a_shipped_file_carries_no_em_dash(rel):
    text = (ROOT / rel).read_text(encoding="utf-8")
    lines = [n for n, line in enumerate(text.splitlines(), 1) if DASH in line]
    assert not lines, "%s: em dash on line(s) %s" % (rel, lines)


def test_the_unreleased_changelog_section_carries_no_em_dash():
    text = (ROOT / "CHANGES.md").read_text(encoding="utf-8")
    unreleased = text.split("## [Unreleased]", 1)[1].split("\n## ", 1)[0]
    assert DASH not in unreleased

