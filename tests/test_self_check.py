"""repo-infra is the first repository on its own pieces (D30): check on this
checkout finds nothing to do, and the example callers in the skill are this
repository's own files, so they cannot rot."""

import pathlib

import pytest

from repo_infra import cli

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "skills/repo-infra/references/examples/repo-infra"


def test_this_repository_passes_its_own_check(monkeypatch, capsys):
    monkeypatch.setattr(cli, "read_facts", lambda repo: cli.CONFORMING_FACTS)
    code = cli.main(["check", "--root", str(ROOT), "--repo", "oposs/repo-infra"])
    assert code == 0, capsys.readouterr().out


@pytest.mark.parametrize("name, installed", [
    ("ci.yml", ".github/workflows/ci.yml"),
    ("release-build.yml", ".github/workflows/release-build.yml"),
    ("release-publish.yml", ".github/workflows/release-publish.yml"),
    ("repo-infra.json", ".github/repo-infra.json"),
])
def test_the_examples_are_this_repositorys_files(name, installed):
    assert (EXAMPLES / name).read_text(encoding="utf-8") == (
        ROOT / installed).read_text(encoding="utf-8")
