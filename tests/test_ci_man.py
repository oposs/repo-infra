"""The ri-ci-man piece (D23): its job and the warning check it runs."""

import os
import pathlib
import stat
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
PIECE = ASSETS / "pieces/ri-ci-man/ri-ci-man.yml"


def test_the_piece_declares_exactly_its_one_job():
    doc = yaml.safe_load(PIECE.read_text(encoding="utf-8"))
    assert list(doc["jobs"]) == ["man"]


# --- the warning check, run for real -------------------------------------------
#
# Its requirement is behavioural (a page roff cannot lay out fails, pandoc's own
# font noise does not), so the step's own shell runs against man/ pages and a
# stand-in `man` that prints each page's text as its warnings.

FONT = ("troff:<standard input>:5: warning: cannot select font 'C'\n"
        "troff:<standard input>:6: warning: cannot select font 'CB'\n")
TABLE = "<standard input>:35: warning: table wider than line length minus indentation\n"


def check_script():
    job = yaml.safe_load(PIECE.read_text(encoding="utf-8"))["jobs"]["man"]
    step = next(s for s in job["steps"]
                if s.get("name", "").startswith("Render"))
    return step["run"]


def _stub(directory, name, body):
    path = directory / name
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def run_check(tmp_path, pages):
    root = tmp_path / "tree"
    (root / "man").mkdir(parents=True)
    for name, text in pages.items():
        (root / "man" / name).write_text(text, encoding="utf-8")
    stubs = tmp_path / "bin"
    stubs.mkdir()
    # Called as `man --warnings -l PAGE`, so the page is $3.
    _stub(stubs, "man", 'cat "$3" >&2\n')
    env = dict(os.environ, PATH="%s:%s" % (stubs, os.environ["PATH"]))
    return subprocess.run(["bash", "-e", "-c", check_script()], cwd=root, env=env,
                          capture_output=True, text=True, timeout=60)


def test_pandocs_own_font_warnings_pass(tmp_path):
    done = run_check(tmp_path, {"tool.1": FONT})
    assert done.returncode == 0, done.stdout + done.stderr


def test_a_table_roff_cannot_fit_fails_the_job(tmp_path):
    done = run_check(tmp_path, {"tool.1": FONT + TABLE})
    assert done.returncode == 1
    assert "table wider than line length minus indentation" in done.stdout


def test_a_font_warning_other_than_c_and_cb_fails_the_job(tmp_path):
    done = run_check(tmp_path, {"tool.1": "troff: warning: cannot select font 'CI'\n"})
    assert done.returncode == 1
    assert "cannot select font 'CI'" in done.stdout


def test_a_page_in_a_section_other_than_1_is_checked(tmp_path):
    # The page's section comes from the manual's front matter, so a daemon's
    # page is man/<name>.8, and the check must not pass it by never looking.
    done = run_check(tmp_path, {"tool.8": TABLE})
    assert done.returncode == 1
    assert "man/tool.8" in done.stdout


def test_a_build_that_produced_no_page_fails_the_job(tmp_path):
    # Otherwise a make man that wrote nothing reports success by checking nothing.
    done = run_check(tmp_path, {})
    assert done.returncode == 1
    assert "produced no page" in done.stdout


def test_one_bad_page_among_several_fails_and_is_named(tmp_path):
    done = run_check(tmp_path, {"a.1": FONT, "b.1": TABLE})
    assert done.returncode == 1
    assert "man/a.1: no warnings" in done.stdout
    assert "man/b.1" in done.stdout


@pytest.mark.pandoc
def test_the_real_toolchain_fails_a_prose_table_and_passes_a_list(tmp_path, require):
    require("pandoc", "man")
    lua = str(ASSETS / "pieces/man-lua/man-deflist.lua")
    head = ("---\ntitle: T\nsection: 1\nheader: t\nfooter: t\ndate: 2026-09-23\n---\n\n"
            "# NAME\n\nt - test\n\n")
    wide = head + ("| Key | Meaning |\n|---|---|\n| a | " + "word " * 60 + "|\n")
    listed = head + "# OPTIONS\n\n- `--flag`: " + "word " * 60 + "\n"
    for name, source, expected in (("wide", wide, 1), ("list", listed, 0)):
        md = tmp_path / (name + ".md")
        md.write_text(source, encoding="utf-8")
        out = tmp_path / name / "man"
        out.mkdir(parents=True)
        subprocess.run(["pandoc", "--standalone", "--to", "man", "--lua-filter", lua,
                        str(md), "-o", str(out / "t.1")], check=True, timeout=60)
        done = subprocess.run(["bash", "-e", "-c", check_script()], cwd=out.parent,
                              capture_output=True, text=True, timeout=60)
        assert done.returncode == expected, name + ": " + done.stdout + done.stderr
