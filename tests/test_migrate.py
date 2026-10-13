"""apply's migration from the v1 layout (D30) to remote pieces (D33)."""

import pathlib
import shutil

from piecekit import SKIP_IF

from repo_infra import callers, check, migrate, workflow
from repo_infra.pieces import load_pieces

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
V2 = "oposs/repo-infra/.github/workflows/{}.yml@v2"
PIECES = load_pieces()
REMOTE = {f"{p.name}.yml" for p in PIECES.values() if p.remote}
PATTERN = (ASSETS / "callers/ci-passed.yml").read_text(encoding="utf-8")

# mtuspy as it was before D33: its callers (the example of the v1 skill),
# copies of the pieces they called, the library and the retired pieces, all
# as published then. Task 11 migrates this tree into the v2 example.
V1_MTUSPY = ROOT / "tests/fixtures/v1/mtuspy"
V1_CI = (V1_MTUSPY / ".github/workflows/ci.yml").read_text(encoding="utf-8")


def test_rewrite_uses_turns_local_piece_calls_remote_and_keeps_the_rest():
    text = ("jobs:\n  a:\n    uses: ./.github/workflows/ri-ci-rust.yml\n"
            "  b:\n    uses: './.github/workflows/ri-ci-man.yml'\n"
            "  c:\n    uses: ./.github/workflows/action-test.yml\n"
            "  # uses: ./.github/workflows/ri-ci-rust.yml in a comment stays\n")
    out = migrate.rewrite_uses(text, REMOTE)
    assert f"    uses: {V2.format('ri-ci-rust')}\n" in out
    assert f"    uses: {V2.format('ri-ci-man')}\n" in out
    assert "    uses: ./.github/workflows/action-test.yml\n" in out
    assert "  # uses: ./.github/workflows/ri-ci-rust.yml in a comment stays\n" in out


def test_name_secrets_replaces_inherit_on_remote_calls_only():
    text = (f"jobs:\n  gitea:\n    uses: {V2.format('ri-publish-gitea')}\n"
            "    secrets: inherit\n"
            "  build:\n    uses: ./.github/workflows/release-build.yml\n    secrets: inherit\n")
    out = migrate.name_secrets(text, {"ri-publish-gitea.yml": ["GITEA_PACKAGE_TOKEN"]})
    assert ("    secrets:\n      GITEA_PACKAGE_TOKEN: ${{ secrets.GITEA_PACKAGE_TOKEN }}\n"
            in out)
    assert "  build:\n    uses: ./.github/workflows/release-build.yml\n    secrets: inherit\n" in out


def test_name_secrets_finds_inherit_above_the_uses_line():
    text = (f"jobs:\n  gitea:\n    secrets: inherit  # all of them\n"
            f"    uses: '{V2.format('ri-publish-gitea')}'\n")
    out = migrate.name_secrets(text, {"ri-publish-gitea.yml": ["GITEA_PACKAGE_TOKEN"]})
    assert out == (f"jobs:\n  gitea:\n    secrets:\n"
                   "      GITEA_PACKAGE_TOKEN: ${{ secrets.GITEA_PACKAGE_TOKEN }}\n"
                   f"    uses: '{V2.format('ri-publish-gitea')}'\n")


def test_name_secrets_drops_inherit_when_the_piece_declares_none():
    text = f"jobs:\n  rust:\n    uses: {V2.format('ri-ci-rust')}\n    secrets: inherit\n"
    assert migrate.name_secrets(text, {"ri-ci-rust.yml": []}) == (
        f"jobs:\n  rust:\n    uses: {V2.format('ri-ci-rust')}\n")


def test_passed_secrets_are_the_required_ones_and_the_optional_ones_in_use():
    """inherit passed every secret; named, an optional secret the repository
    never had would read as one it is expected to set (ri-publish-tag's
    app-client-id)."""
    pieces = {"ri-publish-tag": PIECES["ri-publish-tag"],
              "ri-publish-gitea": PIECES["ri-publish-gitea"]}
    used = migrate.used_secrets(["env:\n  T: ${{ secrets.gitea_package_token }}\n"])
    assert migrate.passed_secrets(pieces, used) == {
        "ri-publish-tag.yml": [], "ri-publish-gitea.yml": ["GITEA_PACKAGE_TOKEN"]}
    assert migrate.passed_secrets(pieces, set()) == {
        "ri-publish-tag.yml": [], "ri-publish-gitea.yml": []}


def test_passed_secrets_always_names_a_required_secret():
    piece = PIECES["ri-ci-rust"]
    text = piece.files[piece.target].replace(
        "  workflow_call:\n", "  workflow_call:\n    secrets:\n      TOKEN:\n"
        "        required: true\n      EXTRA:\n        required: false\n", 1)
    fake = type(piece)(**{**piece.__dict__, "files": {piece.target: text}})
    assert migrate.passed_secrets({"ri-ci-rust": fake}, set()) == {"ri-ci-rust.yml": ["TOKEN"]}


def test_job_block_includes_the_jobs_own_comments_and_stops_at_the_next_job():
    text = "jobs:\n  a:\n    run: x\n\n  # about b\n  b:\n    run: y\n  c:\n    run: z\n"
    start, end = migrate.job_block(text, "b")
    assert text.splitlines()[start:end] == ["  # about b", "  b:", "    run: y"]
    assert migrate.job_block(text, "nothing") is None


def test_drop_job_removes_it_from_every_needs_form():
    text = ("jobs:\n  lib:\n    run: x\n\n  a:\n    needs: lib\n    run: y\n"
            "  b:\n    needs: [lib, a]\n    run: z\n"
            "  c:\n    needs:\n      - a\n      - lib\n    run: w\n")
    out = migrate.drop_job(text, "lib")
    assert out == ("jobs:\n  a:\n    run: y\n  b:\n    needs: [a]\n    run: z\n"
                   "  c:\n    needs:\n      - a\n    run: w\n")


def test_set_ci_passed_replaces_only_ci_passed_and_inserts_the_verdict_once():
    text = ("jobs:\n  a:\n    run: x\n\n  ci-passed:\n    if: always()\n    needs: [a, b]\n"
            "    runs-on: ubuntu-latest\n    steps:\n      - run: old\n\n"
            "  # mine, after ci-passed\n  b:\n    run: y\n")
    out = migrate.set_ci_passed(text, PATTERN)
    doc = workflow.load(out)
    assert list(callers.jobs(doc)) == ["a", "release-verdict", "ci-passed", "b"]
    assert callers.needs(callers.jobs(doc)["ci-passed"]) == ["a", "b", "release-verdict"]
    assert "  # mine, after ci-passed\n  b:\n    run: y\n" in out
    assert "run: old" not in out
    assert migrate.set_ci_passed(out, PATTERN) == out


def _without(text, first, last=None):
    """`text` without the lines from job `first` to job `last`, so what is
    left must be the lines the migration had no reason to touch."""
    start, _ = migrate.job_block(text, first)
    _, end = migrate.job_block(text, last or first)
    lines = text.split("\n")
    return "\n".join(lines[:start] + lines[end:])


# The triggers and permissions of a ci.yml, which check reviews too.
HEAD = V1_CI[:V1_CI.index("jobs:\n")]

# Review Focus 4: ci-passed in the middle, comments between the jobs and a
# job of the project's own between two pieces.
AWKWARD = HEAD + f"""jobs:
  # Rust first.
  rust:
    {SKIP_IF}
    uses: ./.github/workflows/ri-ci-rust.yml
    with:
      ref: ${{{{ inputs.ref }}}}

  # Ours: a smoke test between the pieces.
  smoke:
    {SKIP_IF}
    runs-on: ubuntu-latest
    steps:
      - run: make smoke   # not a job
  # The old gate, with comments of its own.
  ci-passed:
    if: always()
    needs: [rust, smoke, man, release-pr-current]
    runs-on: ubuntu-latest
    steps:
      - run: exit 0

  # Written after ci-passed, kept where it is.
  man:
    {SKIP_IF}
    uses: ./.github/workflows/ri-ci-man.yml
    with:
      ref: ${{{{ inputs.ref }}}}
  release-pr-current:
    {SKIP_IF}
    uses: ./.github/workflows/ri-release-pr-current.yml
    with:
      ref: ${{{{ inputs.ref }}}}
    permissions:
      contents: read
      pull-requests: read
      checks: write
# the end
"""


def test_an_awkward_ci_keeps_every_line_but_ci_passed():
    out = migrate.set_ci_passed(migrate.rewrite_uses(AWKWARD, REMOTE), PATTERN)
    assert _without(out, "release-verdict", "ci-passed") == _without(
        migrate.rewrite_uses(AWKWARD, REMOTE), "ci-passed")
    doc = workflow.load(out)
    assert list(callers.jobs(doc)) == ["rust", "smoke", "release-verdict", "ci-passed",
                                       "man", "release-pr-current"]
    assert out.count("  release-verdict:\n") == 1
    assert "  # The old gate" not in out
    assert "  # Written after ci-passed, kept where it is.\n  man:\n" in out
    assert callers.needs(callers.jobs(doc)["ci-passed"]) == [
        "rust", "smoke", "man", "release-pr-current", "release-verdict"]
    assert [i.detail for i in callers.validate({"ci.yml": doc}, PIECES)
            if i.name == "ci.yml"] == []
    assert migrate.set_ci_passed(out, PATTERN) == out


def test_a_verdict_elsewhere_moves_above_ci_passed_and_keeps_who_needs_it():
    text = migrate.set_ci_passed(migrate.rewrite_uses(AWKWARD, REMOTE), PATTERN)
    start, end = migrate.job_block(text, "release-verdict")
    lines = text.split("\n")
    verdict = lines[start:end]
    moved = "\n".join(lines[:start] + lines[end:]).replace(
        "jobs:\n", "jobs:\n" + "\n".join(verdict) + "\n", 1).replace(
        "  smoke:\n", "  smoke:\n    needs: [release-verdict]\n", 1)
    out = migrate.set_ci_passed(moved, PATTERN)
    assert out.count("  release-verdict:\n") == 1
    assert list(callers.jobs(workflow.load(out)))[:4] == [
        "rust", "smoke", "release-verdict", "ci-passed"]
    assert "  smoke:\n    needs: [release-verdict]\n" in out


def test_the_mtuspy_v1_ci_migrates_to_a_ci_check_accepts():
    out = migrate.set_ci_passed(migrate.drop_job(migrate.rewrite_uses(V1_CI, REMOTE), "lib"),
                                PATTERN)
    doc = workflow.load(out)
    assert "lib" not in callers.jobs(doc)
    found = [i.detail for i in callers.validate({"ci.yml": doc}, PIECES)
             if i.name == "ci.yml"]
    assert found == []
    # The smoke test, the project's own job, is untouched.
    start, end = migrate.job_block(V1_CI, "smoke-test")
    assert "\n".join(V1_CI.split("\n")[start:end]) in out


ACTION_CI = HEAD + f"""jobs:
  action:
    {SKIP_IF}
    uses: ./.github/workflows/ri-ci-github-action.yml
    with:
      ref: ${{{{ inputs.ref }}}}
  release-pr-current:
    {SKIP_IF}
    uses: ./.github/workflows/ri-release-pr-current.yml
    permissions:
      contents: read
      pull-requests: read
      checks: write
    with:
      ref: ${{{{ inputs.ref }}}}
  ci-passed:
    if: always()
    needs: [action]
    runs-on: ubuntu-latest
    steps:
      - run: exit 0
"""


def test_add_action_test_puts_one_job_above_ci_passed():
    out = migrate.add_action_test(migrate.rewrite_uses(ACTION_CI, REMOTE))
    assert out.count("  action-test:\n") == 1
    assert out.index("  action-test:\n") < out.index("  ci-passed:\n")
    out = migrate.set_ci_passed(out, PATTERN)
    doc = workflow.load(out)
    assert callers.action_test_problems({"ci.yml": doc}) == []
    assert callers.jobs(doc)["action-test"]["if"] == SKIP_IF[len("if: "):]
    action_test = workflow.load("on:\n  workflow_call:\n    inputs:\n      ref:\n"
                                "        type: string\n        required: false\n"
                                "jobs:\n  t:\n    runs-on: ubuntu-latest\n"
                                "    steps:\n      - run: make test\n")
    assert [i.detail for i in callers.validate({"ci.yml": doc, "action-test.yml": action_test},
                                               PIECES)
            if i.name == "ci.yml"] == []


def v1_repo(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(V1_MTUSPY, repo)
    return repo


def workflows(repo):
    return {p.relative_to(repo).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted((repo / ".github/workflows").rglob("*")) if p.is_file()}


def test_migrate_turns_the_v1_mtuspy_into_the_v2_layout(tmp_path):
    repo = v1_repo(tmp_path)
    touched = migrate.migrate(repo, PIECES, ASSETS)
    assert ".github/workflows/lib/release.js" in touched
    assert ".github/workflows/ri-ci-lib.yml" in touched
    assert sorted(workflows(repo)) == [f".github/workflows/{f}" for f in (
        "changelog.yml", "ci.yml", "release-build.yml", "release-pr.yml",
        "release-publish.yml")]
    for name in ("changelog.yml", "release-pr.yml"):
        assert (repo / ".github/workflows" / name).read_text(encoding="utf-8") == (
            ASSETS / "callers" / name).read_text(encoding="utf-8")
    publish = (repo / ".github/workflows/release-publish.yml").read_text(encoding="utf-8")
    # The v1 copy of ri-publish-gitea used the token, ri-publish-tag no secret.
    assert ("    secrets:\n      GITEA_PACKAGE_TOKEN: ${{ secrets.GITEA_PACKAGE_TOKEN }}\n"
            in publish)
    assert "app-client-id" not in publish
    assert "secrets: inherit" not in publish
    assert check.layout_items(repo, PIECES) == []
    docs = callers.read_workflows(repo)
    assert [i.detail for i in callers.validate(docs, PIECES)] == []


def test_migrate_names_only_required_secrets_without_evidence(tmp_path):
    """No v1 copy of ri-publish-gitea and no reference to its token: there
    is no telling whether the repository has the secret."""
    repo = v1_repo(tmp_path)
    (repo / ".github/workflows/ri-publish-gitea.yml").unlink()
    migrate.migrate(repo, PIECES, ASSETS)
    publish = (repo / ".github/workflows/release-publish.yml").read_text(encoding="utf-8")
    assert "GITEA_PACKAGE_TOKEN" not in publish
    assert "secrets:" not in publish


def test_migrating_twice_changes_nothing(tmp_path):
    repo = v1_repo(tmp_path)
    migrate.migrate(repo, PIECES, ASSETS)
    before = workflows(repo)
    assert migrate.migrate(repo, PIECES, ASSETS) == []
    assert workflows(repo) == before


def test_migrating_the_v1_example_gives_the_v2_example(tmp_path):
    """The v2 example is hand-written; the migration of its v1 form must
    arrive at the same five callers, byte for byte."""
    repo = v1_repo(tmp_path)
    migrate.migrate(repo, PIECES, ASSETS)
    example = ROOT / "skills/repo-infra/references/examples/mtuspy"
    for name in ("ci.yml", "release-build.yml", "release-publish.yml", "changelog.yml",
                 "release-pr.yml"):
        assert (repo / ".github/workflows" / name).read_text(encoding="utf-8") == (
            example / name).read_text(encoding="utf-8"), name


def test_a_v2_caller_without_a_marker_is_not_overwritten(tmp_path):
    """release-pr.yml is a caller in v2 and may carry jobs of its own."""
    repo = v1_repo(tmp_path)
    mine = (ASSETS / "callers/release-pr.yml").read_text(encoding="utf-8") + "# mine\n"
    (repo / ".github/workflows/release-pr.yml").write_text(mine, encoding="utf-8")
    touched = migrate.migrate(repo, PIECES, ASSETS)
    assert ".github/workflows/release-pr.yml" not in touched
    assert (repo / ".github/workflows/release-pr.yml").read_text(encoding="utf-8") == mine


def test_an_unreadable_ci_is_refused_before_anything_is_written(tmp_path):
    import pytest

    from repo_infra.apply import ApplyError
    repo = v1_repo(tmp_path)
    (repo / ".github/workflows/ci.yml").write_text("jobs: [\n", encoding="utf-8")
    before = workflows(repo)
    with pytest.raises(ApplyError, match="ci.yml"):
        migrate.migrate(repo, PIECES, ASSETS)
    assert workflows(repo) == before


# --- what the migration removes that repo-infra never shipped ---------------

def test_an_unedited_v1_repository_has_no_local_changes(tmp_path):
    assert migrate.local_changes(v1_repo(tmp_path), PIECES, ASSETS) == []


def test_local_changes_name_edited_copies_extra_library_files_and_dropped_jobs(tmp_path):
    repo = v1_repo(tmp_path)
    flows = repo / ".github/workflows"
    rust = flows / "ri-ci-rust.yml"
    rust.write_text(rust.read_text(encoding="utf-8") + "# a local fix\n", encoding="utf-8")
    (flows / "lib/mine.js").write_text("module.exports = {};\n", encoding="utf-8")
    pr = flows / "release-pr.yml"
    pr.write_text(pr.read_text(encoding="utf-8")
                  + "  notify:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo\n",
                  encoding="utf-8")
    found = migrate.local_changes(repo, PIECES, ASSETS)
    assert found == [
        ".github/workflows/lib/mine.js: not shipped by repo-infra",
        ".github/workflows/release-pr.yml: edited locally; the v2 caller replaces it",
        ".github/workflows/release-pr.yml: the v2 caller drops its job notify; add it "
        "again by hand",
        ".github/workflows/ri-ci-rust.yml: edited locally; the copy is removed and the "
        "edits no longer run",
    ]
    # Read before the migration: afterwards the files are gone.
    migrate.migrate(repo, PIECES, ASSETS)
    assert migrate.local_changes(repo, PIECES, ASSETS) == []


def test_a_stamped_v1_copy_is_not_an_edit(tmp_path):
    """v0.3.1 wrote ` sha256=<hex>` after the marker; the record holds the
    bytes without it."""
    repo = v1_repo(tmp_path)
    rust = repo / ".github/workflows/ri-ci-rust.yml"
    text = rust.read_text(encoding="utf-8")
    rust.write_text(text.replace("# repo-infra: ri-ci-rust v1", "# repo-infra: ri-ci-rust v1 "
                                 "sha256=00ff", 1), encoding="utf-8")
    assert "sha256=00ff" in rust.read_text(encoding="utf-8")
    assert migrate.local_changes(repo, PIECES, ASSETS) == []
