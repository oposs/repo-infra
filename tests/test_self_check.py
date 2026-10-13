"""repo-infra is the first repository on its own pieces (D30): check on this
checkout finds nothing to do, and the example callers in the skill are this
repository's own files, so they cannot rot."""

import pathlib

import pytest

from repo_infra import check, cli

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "skills/repo-infra/references/examples/repo-infra"


# Known defect, retired by Task 6 of D33: ri-ci-github-action calls
# ./.github/workflows/action-test.yml, and in a cross-repo call `./` resolves in
# repo-infra, which has no such file. Every consumer of the piece at @v2 would
# fail. When the piece drops the call this test fails; delete KNOWN then.
KNOWN = [("ri-ci-github-action.yml",
          "job action-test calls action-test.yml, which does not exist")]


def test_this_repository_passes_its_own_check_but_for_the_known_defect(monkeypatch):
    monkeypatch.setattr(cli, "read_facts", lambda repo: cli.CONFORMING_FACTS)
    items = check.run(ROOT, cli.CONFORMING_FACTS)
    found = [(i.name, " ".join(i.detail.split())) for i in items
             if i.state not in ("current", "ok")]
    assert found == KNOWN


@pytest.mark.parametrize("name, installed", [
    ("ci.yml", ".github/workflows/ci.yml"),
    ("release-build.yml", ".github/workflows/release-build.yml"),
    ("release-publish.yml", ".github/workflows/release-publish.yml"),
    ("repo-infra.json", ".github/repo-infra.json"),
])
def test_the_examples_are_this_repositorys_files(name, installed):
    assert (EXAMPLES / name).read_text(encoding="utf-8") == (
        ROOT / installed).read_text(encoding="utf-8")
