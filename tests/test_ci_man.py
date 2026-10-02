"""The ci-man add-on (D23): an opt-in block that belongs to no ecosystem, and
that carries the build assets its job runs."""

import json
import os
import pathlib
import stat
import subprocess

import pytest
import yaml

from repo_infra.assemble import (
    AssemblyError,
    assemble_ci,
    block_job_ids,
    ci_addon_blocks,
    render_all,
)
from repo_infra.detect import Detection, DetectResult

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
DETECTION = Detection.load(ASSETS / "detection.json")
BLOCK = ASSETS / "ci/ci-man.yml"
CI_YML = ".github/workflows/ci.yml"


def detected(fixture):
    return DETECTION.detect(ROOT / "tests/fixtures" / fixture)


def rendered(fixture="repo-python", ci=("ci-man",), build=()):
    return render_all(ASSETS, detected(fixture), MANIFEST,
                      build=list(build), ci=list(ci))


def jobs(files):
    return yaml.safe_load(files[CI_YML])["jobs"]


def asset(path):
    return (ASSETS / path).read_text(encoding="utf-8")


# --- the seam -----------------------------------------------------------------


def test_the_block_is_absent_unless_the_repository_asks_for_it():
    # A manual existing does not say its owner wants a required check on it.
    files = rendered(ci=())
    assert "man" not in jobs(files)
    assert "build/man.mk" not in files
    assert "build/man-deflist.lua" not in files


def test_naming_the_block_installs_it_and_makes_it_required():
    files = rendered()
    assert "man" in jobs(files)
    assert "man" in jobs(files)["ci-passed"]["needs"]


def test_the_block_lands_after_the_detected_blocks():
    text = assemble_ci(ASSETS, detected("repo-python").blocks + ["ci-man"], MANIFEST)
    assert text.index("  pytest:") < text.index("  man:") < text.index("  ci-passed:")


def test_choosing_the_block_installs_the_build_assets_its_job_runs():
    # One choice, not two. `make man` needs build/man.mk; a repository that
    # named the block and not the fragment would get a red CI and no reason.
    files = rendered()
    assert files["build/man.mk"] == asset("build/man.mk")
    assert files["build/man-deflist.lua"] == asset("build/man-deflist.lua")


def test_naming_a_carried_build_asset_in_build_as_well_is_not_a_duplicate():
    files = rendered(build=["man", "man-lua"])
    assert files["build/man.mk"] == asset("build/man.mk")
    assert files["build/man-deflist.lua"] == asset("build/man-deflist.lua")
    assert files[CI_YML].count("\n  man:\n") == 1


@pytest.mark.parametrize("fixture", ["repo-python", "repo-rust", "repo-go", "repo-perl-mkpl"])
def test_the_block_fits_any_ecosystem(fixture):
    # A man page has no ecosystem: mdmost is Rust, and a Perl or Go tool ships
    # one the same way.
    assert "man" in jobs(rendered(fixture))


def test_the_block_fits_a_repository_with_no_ecosystem():
    result = DetectResult(ecosystems=[], blocks=["ci-lib"])
    files = render_all(ASSETS, result, MANIFEST, ci=["ci-man"])
    assert "man" in jobs(files)
    assert "build/man.mk" in files


def test_an_optional_block_without_requires_keeps_the_other_refusals():
    result = DetectResult(ecosystems=[], blocks=["ci-lib"])
    assert ci_addon_blocks(result, ["ci-man"], MANIFEST) == ["ci-man"]
    with pytest.raises(AssemblyError, match="already installed"):
        ci_addon_blocks(result, ["ci-man", "ci-man"], MANIFEST)


def test_the_block_declares_exactly_its_one_job():
    assert block_job_ids(BLOCK.read_text(encoding="utf-8")) == ["man"]
    assert MANIFEST["ci_blocks"]["ci-man"]["jobs"] == ["man"]


def test_every_build_asset_a_ci_block_carries_is_declared():
    for name, meta in MANIFEST["ci_blocks"].items():
        for carried in meta.get("build", []):
            assert carried in MANIFEST["build_assets"], (
                "%s carries %s, which build_assets does not declare" % (name, carried))


def test_only_an_opt_in_block_carries_build_assets():
    # render_all installs carried assets for the blocks a repository chose. A
    # detected block that declared some would have them silently ignored.
    for name, meta in MANIFEST["ci_blocks"].items():
        if meta.get("build"):
            assert meta.get("optional"), "%s carries build assets but is not optional" % name


def test_the_config_key_reaches_the_assembler(tmp_path):
    from repo_infra import cli

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/manual.md").write_text("# NAME\n", encoding="utf-8")
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github/repo-infra.json").write_text(
        json.dumps({"ci": ["ci-man"], "publish": [], "build": []}), encoding="utf-8")
    _, _, files = cli._load(tmp_path)
    assert "man" in jobs(files)
    assert "build/man.mk" in files


# --- the warning check, run for real -------------------------------------------
#
# Its requirement is behavioural (a page roff cannot lay out fails, pandoc's own
# font noise does not), so the step's own shell runs against man/ pages and a
# stand-in `man` that prints each page's text as its warnings.

FONT = ("troff:<standard input>:5: warning: cannot select font 'C'\n"
        "troff:<standard input>:6: warning: cannot select font 'CB'\n")
TABLE = "<standard input>:35: warning: table wider than line length minus indentation\n"


def check_script():
    path = ASSETS / "pieces/ri-ci-man/ri-ci-man.yml"
    job = yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"]["man"]
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
    lua = str(ASSETS / "build/man-deflist.lua")
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


# --- the candidate hint ---------------------------------------------------------


def _config(root, ci):
    (root / ".github").mkdir(exist_ok=True)
    (root / ".github/repo-infra.json").write_text(
        json.dumps({"ci": ci, "publish": [], "build": []}), encoding="utf-8")


def test_the_man_pages_hint_stands_until_the_block_is_chosen(tmp_path):
    from repo_infra import cli

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/manual.md").write_text("# NAME\n", encoding="utf-8")
    assert cli._load(tmp_path)[1].candidates == ["man-pages"]
    _config(tmp_path, ["ci-man"])
    assert cli._load(tmp_path)[1].candidates == []


def test_choosing_the_block_leaves_other_candidates_alone(tmp_path):
    from repo_infra import cli

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/manual.md").write_text("# NAME\n", encoding="utf-8")
    (tmp_path / "book.toml").write_text("[book]\n", encoding="utf-8")
    _config(tmp_path, ["ci-man"])
    assert cli._load(tmp_path)[1].candidates == ["docs-site"]


def test_a_candidate_that_names_a_block_names_an_optional_one():
    # A hint answered by a block detection installs would never be answered:
    # nobody can put that block in the `ci` list.
    detection = json.loads((ASSETS / "detection.json").read_text(encoding="utf-8"))
    for entry in detection["candidates"]:
        if "ci_block" in entry:
            meta = MANIFEST["ci_blocks"].get(entry["ci_block"])
            assert meta and meta.get("optional"), entry


def test_the_report_no_longer_prints_an_answered_hint(tmp_path):
    from repo_infra import cli, report

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/manual.md").write_text("# NAME\n", encoding="utf-8")
    _config(tmp_path, ["ci-man"])
    _, result, _ = cli._load(tmp_path)
    assert "man-pages" not in report.render_text("o/r", result, [])
    assert json.loads(report.render_json("o/r", result, []))["candidates"] == []
