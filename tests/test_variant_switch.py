"""Turning release_build on or off switches the variant of release-pr.yml (D26)."""

import pathlib
import subprocess

import pytest

from repo_infra.apply import NeedsMerge, apply_file_item
from repo_infra.markers import marker_line
from repo_infra.state import classify_files

MANIFEST = {"assets": {
    "release-pr": {"version": 3, "source": "workflows/release-pr.yml",
                   "target": ".github/workflows/release-pr.yml"},
    "release-pr-build": {"version": 1, "source": "workflows/release-pr-build.yml",
                         "target": ".github/workflows/release-pr.yml",
                         "variant_of": "release-pr", "when": "release_build"},
}}
TARGET = ".github/workflows/release-pr.yml"
PLAIN = "name: Create release PR\n" + marker_line("release-pr", 3) + "\njobs: {}\n"
BUILD = "name: Create release PR\n" + marker_line("release-pr-build", 1) + "\njobs: {a: 1}\n"


@pytest.fixture
def plugin(tmp_path):
    """A plugin checkout whose history holds release-pr v3 and release-pr-build v1."""
    root = tmp_path / "plugin"
    (root / "assets/workflows").mkdir(parents=True)
    (root / "assets/workflows/release-pr.yml").write_text(PLAIN)
    (root / "assets/workflows/release-pr-build.yml").write_text(BUILD)
    for args in (("init", "-q"), ("add", "."), ("-c", "user.name=t", "-c", "user.email=t@t",
                                                 "commit", "-qm", "assets")):
        subprocess.run(("git",) + args, cwd=root, check=True)
    return root


def install(repo, text):
    path = repo / TARGET
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_the_sibling_marker_reads_as_a_variant_switch(tmp_path):
    install(tmp_path, PLAIN)
    (item,) = classify_files(tmp_path, {TARGET: BUILD}, MANIFEST)
    assert (item.name, item.state) == ("release-pr-build", "outdated")
    assert item.detail.startswith("variant switch")
    assert "release-pr v3" in item.detail


def test_switching_back_is_a_variant_switch_too(tmp_path):
    install(tmp_path, BUILD)
    (item,) = classify_files(tmp_path, {TARGET: PLAIN}, MANIFEST)
    assert (item.name, item.state) == ("release-pr", "outdated")


def test_an_unedited_file_is_replaced_whole(tmp_path, plugin):
    repo = tmp_path / "repo"
    install(repo, PLAIN)
    items = classify_files(repo, {TARGET: BUILD}, MANIFEST)
    assert apply_file_item(repo, "release-pr-build", {TARGET: BUILD}, items, plugin) == [TARGET]
    assert (repo / TARGET).read_text() == BUILD


def test_a_local_edit_is_merged_three_ways_with_the_sibling_as_base(tmp_path, plugin):
    # The Rust `cargo update --workspace` step is such an edit, and dropping it
    # is what shipped mdmost v0.1.1 with a stale Cargo.lock.
    repo = tmp_path / "repo"
    edited = PLAIN + "# cargo update --workspace\n"
    install(repo, edited)
    items = classify_files(repo, {TARGET: BUILD}, MANIFEST)
    with pytest.raises(NeedsMerge) as refused:
        apply_file_item(repo, "release-pr-build", {TARGET: BUILD}, items, plugin)
    assert pathlib.Path(refused.value.base).read_text() == PLAIN
    assert pathlib.Path(refused.value.current).read_text() == edited
