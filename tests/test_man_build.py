"""The man page build assets: build/man.mk and build/man-deflist.lua (D23).

Tests that need pandoc are marked `pandoc`: ci-python's plain pytest run
deselects them, `make test` and the repo-infra-man job run them. The make
error paths need no pandoc and run everywhere.
"""

import json
import os
import pathlib
import shutil
import subprocess

import pytest

from repo_infra.assemble import render_all
from repo_infra.detect import Detection
from repo_infra.markers import parse_markers

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
MK = ASSETS / "pieces/man/man.mk"
LUA = ASSETS / "pieces/man-lua/man-deflist.lua"

FIXTURE_MANUAL = """\
---
title: FIXTURE
section: 1
header: fixture manual
footer: fixture
date: 2026-09-23
---

# NAME

fixture - a two-section test manual

# OPTIONS

- `--listen <ip:port>`: Address and port to listen on.

- `--count N`: Do the thing *N* times.
"""


def make_env():
    # `make test` runs pytest, so MAKEFLAGS and MAKELEVEL arrive set. A nested
    # make reading the parent's flags is not the build a repository runs.
    return {k: v for k, v in os.environ.items()
            if k not in ("MAKEFLAGS", "MAKELEVEL", "MFLAGS")}


def tree(root, manual=FIXTURE_MANUAL,
         makefile="MAN_NAME = fixture\ninclude build/man.mk\n"):
    """A repository that includes the fragment the way the man-pages skill says."""
    (root / "build").mkdir(parents=True)
    shutil.copy(MK, root / "build/man.mk")
    shutil.copy(LUA, root / "build/man-deflist.lua")
    if manual is not None:
        (root / "docs").mkdir()
        (root / "docs/manual.md").write_text(manual, encoding="utf-8")
    (root / "Makefile").write_text(makefile, encoding="utf-8")
    return root


def make_man(root):
    return subprocess.run(["make", "man"], cwd=root, env=make_env(),
                          capture_output=True, text=True, timeout=120)


def to_native(tmp_path, markdown):
    source = tmp_path / "in.md"
    source.write_text(markdown, encoding="utf-8")
    done = subprocess.run(["pandoc", "--lua-filter", str(LUA), "--to", "native",
                           str(source)], capture_output=True, text=True, timeout=60,
                          check=True)
    return done.stdout


# --- declaration --------------------------------------------------------------


def test_both_assets_are_declared_in_the_manifest():
    assert MANIFEST["build_assets"]["man"] == {
        "version": 3, "source": "build/man.mk", "target": "build/man.mk",
        "comment": "#"}
    assert MANIFEST["build_assets"]["man-lua"] == {
        "version": 1, "source": "build/man-deflist.lua",
        "target": "build/man-deflist.lua", "comment": "--"}


@pytest.mark.parametrize("name", ["man", "man-lua"])
def test_each_asset_carries_its_marker_at_the_declared_version(name):
    spec = MANIFEST["build_assets"][name]
    found = parse_markers((ASSETS / spec["source"]).read_text(encoding="utf-8"))
    assert found, "%s has no readable marker" % spec["source"]
    assert (found[0].asset, found[0].version) == (name, spec["version"])


def test_a_repository_that_did_not_ask_for_them_does_not_get_them():
    result = Detection.load(ASSETS / "detection.json").detect(
        ROOT / "tests/fixtures/repo-rust")
    plain = render_all(ASSETS, result, MANIFEST)
    assert "build/man.mk" not in plain
    assert "build/man-deflist.lua" not in plain
    named = render_all(ASSETS, result, MANIFEST, build=["man", "man-lua"])
    # render_all still reads the old assets until they go (D30).
    assert named["build/man.mk"] == (ASSETS / "build/man.mk").read_text(encoding="utf-8")
    assert named["build/man-deflist.lua"] == (
        ASSETS / "build/man-deflist.lua").read_text(encoding="utf-8")


def test_the_assets_carry_no_em_dash():
    # Owner ruling, 2026-09-23: no em dash anywhere, the filter's input included.
    for path in (MK, LUA):
        assert "\u2014" not in path.read_text(encoding="utf-8"), path.name


def test_the_fragment_has_no_substitution_tokens():
    # D15: an asset is the literal file it installs.
    for path in (MK, LUA):
        text = path.read_text(encoding="utf-8")
        for token in ("$VERSION", "{{", "@PACKAGE@"):
            assert token not in text, "%s carries %s" % (path.name, token)


# --- the require fixture -------------------------------------------------------


def test_a_missing_tool_fails_when_ci_is_set(require, monkeypatch):
    # The gate must not go green by skipping everything it exists to run.
    monkeypatch.setenv("CI", "true")
    with pytest.raises(pytest.fail.Exception, match="CI is set"):
        require("no-such-tool-d23")


def test_a_missing_tool_skips_outside_ci(require, monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    with pytest.raises(pytest.skip.Exception, match="no-such-tool-d23"):
        require("no-such-tool-d23")


# --- the filter ---------------------------------------------------------------


@pytest.mark.pandoc
def test_the_filter_turns_a_code_colon_list_into_a_definition_list(tmp_path, require):
    require("pandoc")
    native = to_native(tmp_path, "- `--listen <ip:port>`: Address.\n- `SIGTERM`: Starts.\n")
    assert "DefinitionList" in native
    assert "BulletList" not in native
    # The term is the code span set in bold; the colon and the space are gone.
    assert 'Strong [ Code ( "" , [] , [] ) "--listen <ip:port>" ]' in native
    assert '[ Para [ Str "Address." ] ]' in native


@pytest.mark.pandoc
@pytest.mark.parametrize("markdown", [
    "- **--x** \u2014 text\n- **--y** \u2014 more\n",   # mdmost's form
    "- `--x` : text\n- `--y` : more\n",                 # space before the colon
    "- `--x`: text\n- plain item\n",                     # only some items match
    "- `code` mentioned in prose\n- more prose\n",       # code, no colon
], ids=["bold-dash", "spaced-colon", "partial", "prose"])
def test_a_list_that_does_not_match_throughout_stays_a_bullet_list(
        tmp_path, require, markdown):
    require("pandoc")
    native = to_native(tmp_path, markdown)
    assert "BulletList" in native
    assert "DefinitionList" not in native


# --- the fragment -------------------------------------------------------------


@pytest.mark.pandoc
def test_make_man_builds_the_page_from_the_manual(tmp_path, require):
    require("pandoc", "make")
    root = tree(tmp_path / "repo")
    done = make_man(root)
    assert done.returncode == 0, done.stderr
    page = (root / "man/fixture.1").read_text(encoding="utf-8")
    assert ".SH NAME" in page
    assert ".SH OPTIONS" in page
    # The filter ran: options are bold hanging-indent entries, not bullets.
    assert ".TP\n\\f[B]" in page
    assert "\\[bu]" not in page


@pytest.mark.pandoc
@pytest.mark.parametrize("line", ["section: 8", 'section: "8"', "section: '8'"],
                         ids=["bare", "double-quoted", "single-quoted"])
def test_the_page_lands_in_the_section_its_front_matter_names(tmp_path, require, line):
    # The manual states its section once; the Makefile has no knob to disagree.
    require("pandoc", "make")
    root = tree(tmp_path / "repo", manual=FIXTURE_MANUAL.replace("section: 1", line))
    done = make_man(root)
    assert done.returncode == 0, done.stderr
    assert sorted(p.name for p in (root / "man").iterdir()) == ["fixture.8"]
    assert '.TH "FIXTURE" "8"' in (root / "man/fixture.8").read_text(encoding="utf-8")


def test_a_section_line_after_the_front_matter_is_not_read(tmp_path, require):
    # Only the front matter names the section. A body line that happens to
    # start with `section:` must not decide where the page goes.
    require("make")
    manual = FIXTURE_MANUAL.replace("section: 1\n", "") + "\nsection: 5\n"
    root = tree(tmp_path / "repo", manual=manual)
    done = make_man(root)
    assert done.returncode != 0
    assert "no section: line in its front matter" in done.stderr
    assert not (root / "man").exists()


@pytest.mark.parametrize("manual", [FIXTURE_MANUAL.replace("section: 1\n", ""),
                                    FIXTURE_MANUAL.replace("section: 1", "section: eight")],
                         ids=["missing", "not-a-section"])
def test_make_man_refuses_a_manual_without_a_usable_section(tmp_path, require, manual):
    require("make")
    root = tree(tmp_path / "repo", manual=manual)
    done = make_man(root)
    assert done.returncode != 0
    assert "docs/manual.md" in done.stderr
    assert not (root / "man").exists()


def test_other_targets_still_work_when_the_manual_is_missing(tmp_path, require):
    # The section is read when make parses the Makefile. A missing or broken
    # manual may stop `make man`, never a repository's own build or tests.
    require("make")
    makefile = (".PHONY: build\nbuild:\n\t@echo BUILD_RAN\n\n"
                "MAN_NAME = fixture\ninclude build/man.mk\n")
    root = tree(tmp_path / "repo", manual=None, makefile=makefile)
    done = subprocess.run(["make", "build"], cwd=root, env=make_env(),
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert "BUILD_RAN" in done.stdout
    assert make_man(root).returncode != 0


@pytest.mark.pandoc
def test_an_option_in_running_text_keeps_its_two_hyphens(tmp_path, require):
    # pandoc's markdown reader has `smart` on by default and turns `--` into an
    # en dash, so **--api** in a sentence came out as `–api` in the page.
    # Code spans are never touched, which is why the option lists looked fine.
    require("pandoc", "make")
    manual = FIXTURE_MANUAL + "\n# DESCRIPTION\n\nStart with **--api** to serve it.\n"
    root = tree(tmp_path / "repo", manual=manual)
    done = make_man(root)
    assert done.returncode == 0, done.stderr
    page = (root / "man/fixture.1").read_text(encoding="utf-8")
    # pandoc 3.1 writes the hyphens bare, later releases escape them as `\-`.
    assert ("\\f[B]--api\\f[R]" in page) or ("\\f[B]\\-\\-api\\f[R]" in page), page
    assert "\\[en]" not in page


@pytest.mark.pandoc
def test_two_builds_of_one_source_produce_one_page(tmp_path, require):
    # The date is the front matter's, never the build's.
    require("pandoc", "make")
    root = tree(tmp_path / "repo")
    assert make_man(root).returncode == 0
    first = (root / "man/fixture.1").read_bytes()
    (root / "man/fixture.1").unlink()
    assert make_man(root).returncode == 0
    assert (root / "man/fixture.1").read_bytes() == first
    assert b'.TH "FIXTURE" "1" "2026-09-23"' in first


def test_bare_make_builds_the_makefiles_own_default_not_the_man_page(tmp_path, require):
    # The fragment must not steal .DEFAULT_GOAL merely by being included
    # (finding 1): a bare `make` has to build the repository's own default
    # target, whichever side of `include build/man.mk` it is declared on.
    require("make")
    orders = {
        "include-first": ("MAN_NAME = fixture\ninclude build/man.mk\n\n"
                          ".PHONY: build\nbuild:\n\t@echo BUILD_RAN\n"),
        "build-first": (".PHONY: build\nbuild:\n\t@echo BUILD_RAN\n\n"
                        "MAN_NAME = fixture\ninclude build/man.mk\n"),
    }
    for label, makefile in orders.items():
        root = tree(tmp_path / label, makefile=makefile)
        done = subprocess.run(["make", "-n"], cwd=root, env=make_env(),
                              capture_output=True, text=True, timeout=120)
        assert done.returncode == 0, (label, done.stderr)
        assert "echo BUILD_RAN" in done.stdout, (label, done.stdout)
        assert "pandoc" not in done.stdout, (label, done.stdout)


def test_an_unset_man_name_stops_make_before_anything_is_written(tmp_path, require):
    require("make")
    for index, makefile in enumerate(("include build/man.mk\n",
                                      "MAN_NAME =\ninclude build/man.mk\n")):
        root = tree(tmp_path / str(index), makefile=makefile)
        done = make_man(root)
        assert done.returncode != 0
        assert "MAN_NAME is not set" in done.stderr
        assert not (root / "man").exists()


def test_a_missing_manual_is_named(tmp_path, require):
    require("make")
    root = tree(tmp_path / "repo", manual=None)
    done = make_man(root)
    assert done.returncode != 0
    assert "docs/manual.md" in done.stderr
    assert not (root / "man").exists()
