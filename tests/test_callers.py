# tests/test_callers.py
import json
import pathlib
import re

import piecekit
import pytest
from piecekit import (
    CHANGELOG,
    CI_PASSED,
    RELEASE_PR,
    SHIPPED_REMOTE,
    SKIP_IF,
    install,
    workflow_piece,
)

from repo_infra import callers, workflow
from repo_infra.pieces import load_pieces

ASSETS = pathlib.Path(__file__).resolve().parents[1] / "skills/repo-infra/assets"
PIECE_INPUTS = ("      target:\n        description: The make target.\n"
                "        type: string\n        required: true\n")


def make_assets(root, current, history=(), core=(), remote=None):
    """A test store that also holds the pieces the shipped callers call."""
    return piecekit.make_assets(root, current, history, core,
                                {**SHIPPED_REMOTE, **(remote or {})})


@pytest.fixture
def store(tmp_path):
    return make_assets(tmp_path / "assets", {
        "ri-a": workflow_piece("ri-a", 1),
        "ri-b": workflow_piece("ri-b", 1, inputs=PIECE_INPUTS)})


def repo(tmp_path, store, files):
    """The callers in `files` and the pieces they name; a piece nothing
    names would be reported as installed and never called."""
    root = tmp_path / "repo"
    for piece in load_pieces(store).values():
        if any(pathlib.PurePosixPath(piece.target).name in text for text in files.values()):
            install(root, piece.target, piece.files[piece.target])
    for name, text in files.items():
        install(root, f".github/workflows/{name}", text)
    return root


CI = """name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_call:
    inputs:
      ref:
        description: The commit.
        type: string
        required: false
        default: ''
permissions:
  contents: read
jobs:
  a:
    """ + SKIP_IF + """
    uses: ./.github/workflows/ri-a.yml
    with:
      ref: ${{ inputs.ref }}
""" + CI_PASSED.split("\njobs:\n", 1)[1].replace("needs: [release-verdict]",
                                                 "needs: [a, release-verdict]")
# The release-verdict job of the shipped pattern, as CI carries it (D33).
VERDICT_JOB = ("  release-verdict:\n    uses: oposs/repo-infra/.github/workflows/"
               "ri-release-verdict.yml@v2\n    permissions:\n      contents: read\n"
               "      pull-requests: read\n      statuses: read\n")
# Where job a ends and the shipped jobs begin.
A_END = "ref: ${{ inputs.ref }}\n  # D28"

BUILD = """name: Release build
on:
  workflow_call:
    inputs:
      version:
        description: v
        type: string
        required: true
      ref:
        description: r
        type: string
        required: true
permissions:
  contents: read
jobs:
  noop:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - run: echo ok
"""

PUBLISH = """name: Publish
on:
  push:
    branches: [main]
    paths: [CHANGES.md]
concurrency:
  group: release-publish
  cancel-in-progress: false
permissions:
  contents: read
jobs:
  publish:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - run: echo publish
  finalize:
    needs: [publish]
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - run: echo finalize
"""


def problems(tmp_path, store, **files):
    base = {"ci.yml": CI, "release-build.yml": BUILD, "release-publish.yml": PUBLISH,
            "changelog.yml": CHANGELOG, "release-pr.yml": RELEASE_PR}
    base.update({k.replace("_", "-") + ".yml": v for k, v in files.items()})
    docs = callers.read_workflows(repo(tmp_path, store, base))
    return [(i.name, i.state, i.detail) for i in
            callers.validate(docs, load_pieces(store), store)]


def test_a_conforming_set_of_callers_has_no_problem(tmp_path, store):
    assert problems(tmp_path, store) == []


def test_a_missing_core_caller_is_named(tmp_path, store):
    root = repo(tmp_path, store, {"ci.yml": CI, "release-build.yml": BUILD,
                                  "changelog.yml": CHANGELOG, "release-pr.yml": RELEASE_PR})
    found = callers.validate(callers.read_workflows(root), load_pieces(store), store)
    assert [(i.name, i.state) for i in found] == [("release-publish.yml", "missing")]


def test_calling_a_file_that_does_not_exist(tmp_path, store):
    found = problems(tmp_path, store, ci=CI.replace("ri-a.yml", "ri-zz.yml"))
    assert ("ci.yml", "problem", "job a calls ri-zz.yml, which does not exist") in found


def test_an_input_the_piece_does_not_declare(tmp_path, store):
    found = problems(tmp_path, store,
                     ci=CI.replace("      ref: ${{ inputs.ref }}\n",
                                   "      ref: ${{ inputs.ref }}\n      colour: red\n", 1))
    assert ("ci.yml", "problem",
            "job a calls ri-a.yml with the input colour, which ri-a.yml does not declare"
            ) in found


def test_a_required_input_not_passed(tmp_path, store):
    found = problems(tmp_path, store, ci=CI.replace("ri-a.yml", "ri-b.yml"))
    assert ("ci.yml", "problem",
            "job a calls ri-b.yml without its required input target") in found


def test_a_required_secret_needs_passing_or_inherit(tmp_path, store):
    secret = ("    secrets:\n      TOKEN:\n        description: t\n"
              "        required: true\n")
    called = workflow_piece("ri-a", 1).replace("permissions:\n", secret + "permissions:\n", 1)
    own = called.replace("repo-infra: ri-a v1", "own").replace("# Purpose", "# P")
    found = problems(tmp_path, store, ci=CI.replace("ri-a.yml", "own.yml"), own=own)
    assert any("without its required secret TOKEN" in d for _, _, d in found)
    inherited = CI.replace("ri-a.yml", "own.yml").replace(
        "      ref: ${{ inputs.ref }}\n", "      ref: ${{ inputs.ref }}\n    secrets: inherit\n", 1)
    assert not any("TOKEN" in d for _, _, d in problems(tmp_path / "2", store,
                                                        ci=inherited, own=own))


def test_a_workflow_of_another_repository_is_not_reviewed(tmp_path, store):
    """P9 of D33: only calls of repo-infra's pieces are reviewed; D30's
    "copy the piece" is gone."""
    found = problems(tmp_path, store, ci=CI.replace(
        "./.github/workflows/ri-a.yml", "other/repo/.github/workflows/ri-a.yml@v1"))
    assert not [d for name, _, d in found if name == "ci.yml" and "job a " in d]


def test_a_call_to_a_repo_infra_piece_is_not_a_workflow_in_another_repository(tmp_path, store):
    # D33: the consumer calls repo-infra's pieces; CI's release-verdict does.
    assert VERDICT_JOB in CI
    assert not any("another repository" in d for _, _, d in problems(tmp_path, store))


def test_a_repo_infra_call_at_another_ref_is_a_problem(tmp_path, store):
    ci = CI.replace("ri-release-verdict.yml@v2", "ri-release-verdict.yml@main")
    assert ci != CI
    assert ("ci.yml", "problem",
            "job release-verdict calls oposs/repo-infra/.github/workflows/"
            "ri-release-verdict.yml@main; call repo-infra's pieces at @v2, the tag every "
            "release moves (D33)") in problems(tmp_path, store, ci=ci)


FLOW = "jobs:\n  x:\n    with: {ref: y}\n"
UNREADABLE = "cannot be read: line 3: a flow mapping; write it in block style"


def test_an_unreadable_caller_is_one_problem_and_the_rest_is_still_validated(tmp_path, store):
    found = problems(tmp_path, store, release_build=FLOW,
                     ci=CI.replace("ri-a.yml", "ri-zz.yml"))
    assert ("release-build.yml", "problem", UNREADABLE) in found
    assert any(d.endswith("ri-zz.yml, which does not exist") for _, _, d in found)


@pytest.mark.parametrize("text", [
    FLOW,
    "env: &shared\n  A: 1\njobs:\n  x:\n    env: *shared\n    runs-on: ubuntu-latest\n",
    "jobs:\n  x:\n    strategy:\n      matrix:\n        os: [ubuntu-latest,\n"
    "             macos-latest]\n",
])
def test_an_unrelated_workflow_the_reader_cannot_follow_is_skipped(tmp_path, store, text):
    """GitHub accepts flow mappings, anchors and multi-line flow sequences; a
    repository's own deploy workflow written that way is none of check's
    business and must not hold its exit code at 1."""
    with pytest.raises(workflow.ReadError):
        workflow.load(text)
    assert problems(tmp_path, store, deploy=text) == []


def test_an_unreadable_workflow_a_caller_calls_is_a_problem(tmp_path, store):
    ci = CI.replace("ri-a.yml", "ci-local.yml")
    found = problems(tmp_path, store, ci=ci, ci_local=FLOW)
    assert ("ci-local.yml", "problem", UNREADABLE) in found


def test_an_unreadable_file_carrying_a_piece_marker_is_a_problem(tmp_path, store):
    found = problems(tmp_path, store, ri_a="# repo-infra: ri-a v1\n" + FLOW,
                     ci=CI.replace("ri-a.yml", "ri-b.yml").replace(
                         "      ref: ${{ inputs.ref }}\n",
                         "      ref: ${{ inputs.ref }}\n      target: x\n", 1))
    assert ("ri-a.yml", "problem", UNREADABLE.replace("line 3", "line 4")) in found


def test_ci_passed_must_need_every_other_job(tmp_path, store):
    found = problems(tmp_path, store, ci=CI.replace("needs: [a, release-verdict]",
                                                    "needs: [release-verdict]"))
    assert ("ci.yml", "problem",
            "ci-passed does not need a; it would report green while that job fails") in found


def test_ci_passed_must_run_always(tmp_path, store):
    found = problems(tmp_path, store, ci=CI.replace("if: always()", "if: success()"))
    assert any("lacks `if: always()`" in d for _, _, d in found)


def test_ci_passed_must_follow_the_pattern(tmp_path, store):
    ci = CI.replace('if [ "$FAILED" = true ]', 'if [ "$FAILED" = maybe ]')
    assert ci != CI
    found = problems(tmp_path, store, ci=ci)
    assert any("ci-passed differs from the pattern" in d for _, _, d in found)


def test_a_ci_yml_without_the_verdict_job_is_a_problem(tmp_path, store):
    ci = CI.replace(VERDICT_JOB, "").replace(", release-verdict]", "]")
    assert ("ci.yml", "problem", "ci.yml calls no ri-release-verdict; ci-passed has no "
            "release verdict to read. Copy release-verdict from assets/callers/ci-passed.yml "
            "in the repo-infra skill") in problems(tmp_path, store, ci=ci)


def test_a_verdict_job_that_differs_from_the_pattern_is_a_problem(tmp_path, store):
    ci = CI.replace(VERDICT_JOB, VERDICT_JOB.replace("      statuses: read\n", ""))
    assert ("ci.yml", "problem", "release-verdict differs from the pattern (assets/callers/"
            "ci-passed.yml in the repo-infra skill); copy it word for word"
            ) in problems(tmp_path, store, ci=ci)


def test_the_verdict_job_needs_no_skip():
    doc = workflow.load("jobs:\n" + VERDICT_JOB)
    assert callers.release_skip_problems({"ci.yml": doc}) == []


@pytest.mark.parametrize("guard", ["(", "!cancelled() && (", "success() && ("])
def test_a_changelog_yml_without_always_is_a_problem(guard):
    # Without always() a failed or cancelled changelog job skips
    # changelog-updated, and a skipped required check counts as passed.
    pattern = (ASSETS / "callers/changelog.yml").read_text(encoding="utf-8")
    broken = pattern.replace("always() && (", guard)
    assert broken != pattern
    docs = {"changelog.yml": workflow.load(broken)}
    assert callers.changelog_problems(docs) == [(
        "changelog.yml", "changelog-updated differs from the pattern "
        "(assets/callers/changelog.yml in the repo-infra skill); copy it word for word")]


def test_a_repository_without_changelog_yml_is_missing_it(tmp_path, store):
    root = repo(tmp_path, store, {"ci.yml": CI, "release-build.yml": BUILD,
                                  "release-publish.yml": PUBLISH, "release-pr.yml": RELEASE_PR})
    found = callers.validate(callers.read_workflows(root), load_pieces(store), store)
    assert [(i.name, i.state) for i in found] == [("changelog.yml", "missing")]


def test_this_repositorys_changelog_yml_matches_the_pattern():
    assert callers.changelog_problems({"changelog.yml": workflow.load(own("changelog.yml"))}) == []


def test_finalize_must_need_every_other_job(tmp_path, store):
    extra = PUBLISH + ("  crates:\n    needs: [publish]\n    runs-on: ubuntu-latest\n"
                       "    timeout-minutes: 5\n    steps:\n      - run: echo\n")
    found = problems(tmp_path, store, release_publish=extra)
    assert ("release-publish.yml", "problem",
            "finalize does not need crates; it would publish the release before that job "
            "attached its files") in found


def test_an_inline_job_of_ci_yml_must_check_out_ref(tmp_path, store):
    job = ("  own:\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    steps:\n"
           "      - uses: actions/checkout@v7\n")
    found = problems(tmp_path, store, ci=CI.replace("jobs:\n", "jobs:\n" + job, 1)
                     .replace("needs: [a]", "needs: [own, a]"))
    assert any(d.startswith("job own has an actions/checkout step without") for _, _, d in found)


def test_a_project_workflow_called_with_ref_is_held_to_the_contract(tmp_path, store):
    local = """on:
  workflow_call:
    inputs:
      ref:
        description: r
        type: string
        required: false
        default: ''
jobs:
  t:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ inputs.ref }}
      - uses: actions/upload-artifact@v7
        with:
          name: release-asset-x
"""
    ci = CI.replace("ri-a.yml", "ci-local.yml")
    found = problems(tmp_path, store, ci=ci, ci_local=local)
    assert ("ci-local.yml", "problem",
            "job t uploads an artifact named release-asset-x, a name reserved for the "
            "release build") in found
    clean = local.replace("release-asset-x", "coverage")
    assert problems(tmp_path / "2", store, ci=ci, ci_local=clean) == []


def test_the_ci_passed_pattern_checks_out_nothing():
    # D33: release mode moved to ri-release-verdict, with the library checkout.
    assert callers.ref_problems(workflow.load(CI_PASSED), True) == []


def test_a_called_piece_without_workflow_call_is_a_problem(tmp_path, store):
    plain = "name: plain\non:\n  push:\n    branches: [main]\njobs:\n  x:\n" \
            "    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    steps:\n      - run: echo\n"
    found = problems(tmp_path, store, ci=CI.replace("ri-a.yml", "plain.yml"), plain=plain)
    assert ("ci.yml", "problem",
            "job a calls plain.yml, which has no `on: workflow_call` trigger") in found


def test_ci_without_ci_passed_is_a_problem(tmp_path, store):
    bare = CI.split("  ci-passed:")[0]
    found = problems(tmp_path, store, ci=bare)
    assert ("ci.yml", "problem", "has no ci-passed job") in found


def test_release_publish_without_finalize_is_a_problem(tmp_path, store):
    found = problems(tmp_path, store, release_publish=PUBLISH.split("  finalize:")[0])
    assert ("release-publish.yml", "problem", "has no finalize job") in found


def test_the_shipped_ci_passed_pattern_is_accepted_in_a_ci_yml():
    text = (callers.ASSETS / "callers/ci-passed.yml").read_text(encoding="utf-8")
    ci = workflow.load(
        "jobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: 'true'\n"
        + text.split("\njobs:\n", 1)[1].replace("needs: [release-verdict]",
                                                "needs: [a, release-verdict]"))
    assert callers.closing_problems({"ci.yml": ci}) == []
    assert callers.release_skip_problems({"ci.yml": ci}) == [
        ("ci.yml", NO_SKIP.format("a"))]


# The ref contract of a project workflow (D28), ported from the retired seam
# reader's tests: each case is a form that must not read as conforming.
GOOD = """\
name: Local CI
on:
  workflow_call:
    inputs:
      ref:
        type: string
        required: false
        default: ''
jobs:
  windows:
    runs-on: windows-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ inputs.ref }}
      - run: cargo check
  lint:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Check out
        uses: "actions/checkout@v7"
        with:
          fetch-depth: 0
          ref: ${{ inputs.ref }}
"""
NO_REF_LINE = "          fetch-depth: 0\n          ref: ${{ inputs.ref }}\n"
STEPS = GOOD.split("    steps:\n")[0] + "    steps:\n"


def ref_found(text, reserved=False):
    return callers.ref_problems(workflow.load(text), reserved)


def test_the_library_checkout_of_a_piece_needs_no_ref_input():
    library = ("      - uses: actions/checkout@v7\n        with:\n"
               "          repository: ${{ job.workflow_repository }}\n"
               "          ref: ${{ job.workflow_sha }}\n          path: .repo-infra\n")
    assert ref_found(GOOD + library, reserved=True) == []
    assert ref_found(GOOD + library.replace("job.workflow_repository", "other/repo"),
                     reserved=True) != []


def test_a_checkout_of_the_calling_repository_without_ref_is_a_problem():
    """In a consumer's ci.yml job.workflow_repository is the consumer itself:
    without `ref` the checkout tests main (D28). Only the library checkout of
    a piece, at job.workflow_sha into .repo-infra, needs no ref input."""
    plain = ("      - uses: actions/checkout@v7\n        with:\n"
             "          repository: ${{ job.workflow_repository }}\n")
    assert ref_found(GOOD + plain) != []
    assert ref_found(GOOD + plain + "          path: .repo-infra\n") != []
    assert ref_found(GOOD + plain + "          ref: ${{ job.workflow_sha }}\n") != []


def test_a_conforming_project_workflow_has_no_ref_problem():
    assert ref_found(GOOD, reserved=True) == []


def test_a_checkout_in_a_second_job_without_ref_is_named():
    found = ref_found(GOOD.replace(NO_REF_LINE, "          fetch-depth: 0\n"))
    assert len(found) == 1 and found[0].startswith("job lint has an actions/checkout step")


def test_a_checkout_without_with_is_named():
    text = GOOD.replace("      - uses: actions/checkout@v7\n        with:\n"
                        "          ref: ${{ inputs.ref }}\n", "      - uses: actions/checkout@v7\n")
    assert len(ref_found(text)) == 1


def test_a_comment_mentioning_ref_does_not_count():
    text = GOOD.replace(NO_REF_LINE, "          fetch-depth: 0\n          # ref: ${{ inputs.ref }}\n")
    assert len(ref_found(text)) == 1


@pytest.mark.parametrize("name", ["release-asset-x", "'release-files'", '"release-asset-"',
                                  "Release-Files", "RELEASE-ASSET-x"])
def test_a_reserved_artifact_name_is_named_where_it_is_reserved(name):
    text = GOOD + ("      - uses: actions/upload-artifact@v7\n        with:\n"
                   f"          name: {name}\n          path: out/\n")
    found = ref_found(text, reserved=True)
    assert len(found) == 1 and "reserved for the release build" in found[0]
    assert ref_found(text, reserved=False) == []


def test_a_step_display_name_is_not_an_artifact_name():
    text = GOOD + ("      - name: release-files\n        uses: actions/upload-artifact@v7\n"
                   "        with:\n          name: coverage\n          path: out/\n")
    assert ref_found(text, reserved=True) == []


@pytest.mark.parametrize("steps", [
    "      -\n        uses: actions/checkout@v7\n",
    "      - uses: actions/checkout@v7\n        env:\n          ref: ${{ inputs.ref }}\n",
])
def test_a_checkout_that_ignores_ref_in_any_form_is_a_problem(steps):
    assert ref_found(STEPS + steps) != []


@pytest.mark.parametrize("steps", [
    "      - run: 'true'\n      - &co\n        uses: actions/checkout@v7\n      - *co\n",
    "      - {uses: actions/checkout@v7}\n",
    "      - uses: actions/checkout@v7\n        with: {fetch-depth: 0}\n",
    "      - uses: actions/upload-artifact@v7\n        with: {name: release-files}\n",
])
def test_a_form_the_reader_does_not_follow_is_refused_never_passed(steps):
    # Each of these checks out the default commit or uploads a reserved name;
    # the reader refuses them, and check reports the file as unreadable.
    with pytest.raises(workflow.ReadError):
        ref_found(STEPS + steps, reserved=True)


@pytest.mark.parametrize("ref", [
    "'${{ github.sha }}' # ${{ inputs.ref }}",
    '"main" # ${{ inputs.ref }}',
    "main # ${{ inputs.ref }}",
    "${{ inputs.ref || github.sha }}",
    # The quotes inside are part of the value: the ref named is '<sha>', quotes included.
    "\"'${{ inputs.ref }}'\"",
    "'\"${{ inputs.ref }}\"'",
])
def test_only_the_whole_value_inputs_ref_counts(ref):
    text = GOOD.replace(NO_REF_LINE, f"          fetch-depth: 0\n          ref: {ref}\n")
    assert len(ref_found(text)) == 1


@pytest.mark.parametrize("ref", ["'${{ inputs.ref }}' # pinned", "${{inputs.ref}}",
                                 "${{ INPUTS.REF }}", "${{ Inputs.Ref }}"])
def test_a_quoted_or_tight_inputs_ref_counts(ref):
    text = GOOD.replace(NO_REF_LINE, f"          fetch-depth: 0\n          ref: {ref}\n")
    assert ref_found(text) == []


def test_the_action_name_is_read_in_any_case():
    assert len(ref_found(STEPS + "      - uses: Actions/Checkout@v7\n")) == 1


def test_a_comment_after_with_is_not_a_value():
    text = GOOD.replace("          fetch-depth: 0\n", "").replace("        with:\n",
                                                                   "        with: # pinned\n")
    assert ref_found(text, reserved=True) == []


# D28: a call that takes `ref` must be handed `${{ inputs.ref }}`, or the release
# pull request tests the triggering commit and reports it as the release.
WITH_REF = "    with:\n      ref: ${{ inputs.ref }}\n"


def ref_problems_found(tmp_path, store, ci):
    found = problems(tmp_path, store, ci=ci)
    return [d for _, _, d in found if "inputs.ref" in d and "triggering commit" in d]


def test_a_piece_call_without_with_is_a_problem(tmp_path, store):
    found = ref_problems_found(tmp_path, store, CI.replace(WITH_REF, ""))
    assert found == ["job a calls ri-a.yml, which takes `ref`, without `with: ref: "
                     "${{ inputs.ref }}`; the release pull request would test the "
                     "triggering commit instead of the release commit (D28). Add it"]


@pytest.mark.parametrize("value", ["${{ github.sha }}", "main", "${{ inputs.ref || 'x' }}"])
def test_a_call_passing_another_ref_is_a_problem(tmp_path, store, value):
    ci = CI.replace(A_END, A_END.replace("${{ inputs.ref }}", value))
    assert ci != CI
    assert len(ref_problems_found(tmp_path, store, ci)) == 1


@pytest.mark.parametrize("value", ["${{ inputs.ref }}", "${{inputs.ref}}", "'${{ inputs.ref }}'"])
def test_a_correct_ref_call_is_clean(tmp_path, store, value):
    ci = CI.replace(A_END, A_END.replace("${{ inputs.ref }}", value))
    assert ref_problems_found(tmp_path, store, ci) == []


def test_a_project_workflow_taking_ref_is_held_to_it_too(tmp_path, store):
    local = ("name: x\non:\n  workflow_call:\n    inputs:\n      ref:\n        type: string\n"
             "        required: false\n        default: ''\njobs:\n  t:\n    runs-on: ubuntu-latest\n"
             "    timeout-minutes: 5\n    steps:\n      - run: echo\n")
    ci = CI.replace("ri-a.yml", "ci-local.yml").replace(WITH_REF, "")
    found = [d for _, _, d in problems(tmp_path, store, ci=ci, ci_local=local)
             if "triggering commit" in d]
    assert len(found) == 1 and "ci-local.yml" in found[0]


def test_a_call_to_a_workflow_without_a_ref_input_is_not_affected(tmp_path, store):
    plain = ("name: x\non:\n  workflow_call:\n    inputs: {}\njobs:\n  t:\n"
             "    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    steps:\n      - run: echo\n")
    plain = plain.replace("inputs: {}\n", "secrets:\n      k:\n        required: false\n")
    ci = CI.replace("ri-a.yml", "plain.yml").replace(WITH_REF, "")
    found = [d for _, _, d in problems(tmp_path, store, ci=ci, plain=plain)
             if "triggering commit" in d]
    assert found == []


def test_a_call_from_release_publish_is_not_affected(tmp_path, store):
    publish = PUBLISH.replace("  publish:\n    runs-on", "  other:\n    uses: ./.github/workflows/ri-a.yml\n"
                              "  publish:\n    runs-on", 1).replace("needs: [publish]",
                                                                    "needs: [publish, other]")
    found = [d for _, _, d in problems(tmp_path, store, release_publish=publish)
             if "triggering commit" in d]
    assert found == []


def test_a_bare_dash_step_is_read_like_any_other():
    text = STEPS + "      -\n        uses: actions/checkout@v7\n        with:\n" \
                   "          ref: ${{ inputs.ref }}\n"
    assert ref_found(text, True) == []


def test_an_anchor_without_a_preceding_run_step_is_refused():
    text = STEPS + "      - &co\n        uses: actions/checkout@v7\n      - *co\n"
    with pytest.raises(workflow.ReadError):
        ref_found(text, True)


@pytest.mark.parametrize("path", sorted((callers.ASSETS / "callers").glob("*.yml")),
                         ids=lambda p: p.name)
def test_a_caller_template_pins_its_actions_to_the_manifest(path):
    manifest = json.loads((callers.ASSETS / "manifest.json").read_text(encoding="utf-8"))
    wrong = []
    for job in jobs_of(path).values():
        for step in job.get("steps", []):
            match = re.match(r"^([\w.-]+/[\w.-]+)@(v\d+)$", step.get("uses", ""))
            if match and manifest["actions"].get(match[1]) != match[2]:
                wrong.append(step["uses"])
    assert wrong == []


def jobs_of(path):
    return callers.jobs(workflow.load(path.read_text(encoding="utf-8")))


# --- finalize's guard and wiring (M1) ---------------------------------------

REPO = pathlib.Path(__file__).resolve().parents[1]
GUARD = "    if: needs.publish.outputs.release_id != ''\n"


def finalize_problems(tmp_path, publish):
    """This repository's own workflows, with release-publish.yml replaced,
    validated against the shipped pieces."""
    folder = tmp_path / ".github/workflows"
    folder.mkdir(parents=True)
    for path in (REPO / ".github/workflows").glob("*.yml"):
        (folder / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    (folder / "release-publish.yml").write_text(publish, encoding="utf-8")
    docs = callers.read_workflows(tmp_path)
    return [i.detail for i in callers.validate(docs, load_pieces(), home=True) if
            i.name == "release-publish.yml"]


def own_publish():
    return (REPO / ".github/workflows/release-publish.yml").read_text(encoding="utf-8")


def test_the_shipped_finalize_call_has_no_problem(tmp_path):
    assert GUARD in own_publish()
    assert finalize_problems(tmp_path, own_publish()) == []


def test_finalize_without_its_release_id_guard_is_a_problem(tmp_path):
    found = finalize_problems(tmp_path, own_publish().replace(GUARD, ""))
    assert found == [
        "finalize lacks `if: needs.publish.outputs.release_id != ''`; it would run "
        "after every push of CHANGES.md that publishes nothing, with an empty "
        "release_id, and fail"]


def test_a_finalize_guard_written_as_an_expression_counts(tmp_path):
    wrapped = "    if: ${{ needs.publish.outputs.release_id != '' }}\n"
    assert finalize_problems(tmp_path, own_publish().replace(GUARD, wrapped)) == []


def test_finalize_wired_to_another_output_is_a_problem(tmp_path):
    text = own_publish().replace("tag: ${{ needs.publish.outputs.tag }}",
                                 "tag: ${{ needs.publish.outputs.head }}")
    assert finalize_problems(tmp_path, text) == [
        "finalize passes tag: ${{ needs.publish.outputs.head }}; ri-publish-finalize.yml "
        "takes tag: ${{ needs.publish.outputs.tag }} (its Call: header)"]


# --- the frame of ci.yml and release-publish.yml (M2) -----------------------

def own(name):
    return (REPO / ".github/workflows" / name).read_text(encoding="utf-8")


def problems_of(tmp_path, name, text):
    """This repository's own workflows, with `name` replaced, validated
    against the shipped pieces: the problems reported for `name`."""
    folder = tmp_path / ".github/workflows"
    folder.mkdir(parents=True)
    for path in (REPO / ".github/workflows").glob("*.yml"):
        (folder / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    (folder / name).write_text(text, encoding="utf-8")
    docs = callers.read_workflows(tmp_path)
    return [i.detail for i in callers.validate(docs, load_pieces(), home=True)
            if i.name == name]


CI_PUSH = "  push:\n    branches: [main]\n"
CI_PR = "  pull_request:\n    branches: [main]\n"
NO_PUSH = ("ci.yml does not run on push to main; main is not tested after a merge, and "
           "an open release pull request is not marked stale when main moves (D28)")
NO_PR = ("ci.yml does not run on pull_request to main; ci-passed never reports on a pull "
         "request, and the ruleset that requires it keeps every pull request waiting")


@pytest.mark.parametrize("name", ["ci.yml", "release-publish.yml"])
def test_this_repositorys_frames_have_no_problem(tmp_path, name):
    assert problems_of(tmp_path, name, own(name)) == []


@pytest.mark.parametrize("name", ["ci.yml", "release-publish.yml"])
def test_the_example_frames_have_no_problem(tmp_path, name):
    example = REPO / "skills/repo-infra/references/examples/repo-infra" / name
    assert problems_of(tmp_path, name, example.read_text(encoding="utf-8")) == []


def test_ci_without_a_push_trigger_is_a_problem(tmp_path):
    assert CI_PUSH in own("ci.yml")
    assert problems_of(tmp_path, "ci.yml", own("ci.yml").replace(CI_PUSH, "")) == [NO_PUSH]


def test_ci_pushing_only_another_branch_is_a_problem(tmp_path):
    text = own("ci.yml").replace(CI_PUSH, "  push:\n    branches: [develop]\n")
    assert problems_of(tmp_path, "ci.yml", text) == [NO_PUSH]


def test_ci_ignoring_main_on_push_is_a_problem(tmp_path):
    text = own("ci.yml").replace(CI_PUSH, "  push:\n    branches-ignore: [main]\n")
    assert problems_of(tmp_path, "ci.yml", text) == [NO_PUSH]


@pytest.mark.parametrize("push", ["  push:\n", "  push:\n    branches: ['**']\n",
                                  "  push:\n    branches: [main, 'release/*']\n"])
def test_ci_pushing_main_in_another_form_counts(tmp_path, push):
    text = own("ci.yml").replace(CI_PUSH, push)
    assert problems_of(tmp_path, "ci.yml", text) == []


def test_ci_without_a_pull_request_trigger_is_a_problem(tmp_path):
    assert CI_PR in own("ci.yml")
    assert problems_of(tmp_path, "ci.yml", own("ci.yml").replace(CI_PR, "")) == [NO_PR]


def test_ci_without_release_pr_current_is_a_problem(tmp_path):
    job = ("  release-pr-current:\n    " + SKIP_IF + "\n    uses: ./.github/workflows/ri-release-pr-current.yml\n"
           "    permissions:\n      contents: read\n      pull-requests: read\n"
           "      checks: write\n    with:\n      ref: ${{ inputs.ref }}\n\n")
    assert job in own("ci.yml")
    text = own("ci.yml").replace(job, "").replace(", release-pr-current, ", ", ")
    assert problems_of(tmp_path, "ci.yml", text) == [
        "ci.yml calls no ri-release-pr-current.yml; an open release pull request is not "
        "marked stale when main moves (D28). Add its Call: from the catalogue"]


PUBLISH_ON = "  push:\n    branches: [main]\n    paths:\n      - CHANGES.md\n"
CONCURRENCY = "concurrency:\n  group: release-publish\n  cancel-in-progress: false\n"


@pytest.mark.parametrize("old, new", [
    (CONCURRENCY, ""), ("group: release-publish", "group: publish-${{ github.ref }}")])
def test_release_publish_without_its_concurrency_group_is_a_problem(tmp_path, old, new):
    assert CONCURRENCY in own("release-publish.yml")
    text = own("release-publish.yml").replace(old, new)
    assert problems_of(tmp_path, "release-publish.yml", text) == [
        "release-publish.yml lacks `concurrency: group: release-publish`; a second "
        "merge would start a publish run while the first is still attaching files"]


def test_release_publish_cancelling_a_running_publish_is_a_problem(tmp_path):
    text = own("release-publish.yml").replace("cancel-in-progress: false",
                                              "cancel-in-progress: true")
    assert problems_of(tmp_path, "release-publish.yml", text) == [
        "release-publish.yml sets `cancel-in-progress: true`; the next push would cancel a "
        "publish run half way, with the release partly published"]


def test_release_publish_with_a_plain_concurrency_group_counts(tmp_path):
    text = own("release-publish.yml").replace(CONCURRENCY, "concurrency: release-publish\n")
    assert problems_of(tmp_path, "release-publish.yml", text) == []


def test_release_publish_with_workflow_dispatch_is_a_problem(tmp_path):
    text = own("release-publish.yml").replace(PUBLISH_ON, PUBLISH_ON + "  workflow_dispatch:\n")
    assert PUBLISH_ON in own("release-publish.yml")
    assert problems_of(tmp_path, "release-publish.yml", text) == [
        "release-publish.yml has a workflow_dispatch trigger; a release is published by "
        "merging its pull request, and a dispatch would publish whatever CHANGES.md says "
        "on the branch it runs on. Remove it"]


@pytest.mark.parametrize("on", [
    "  push:\n    branches: [main]\n",
    "  push:\n    branches: [main]\n    paths:\n      - CHANGES.md\n      - src/**\n"])
def test_release_publish_on_other_pushes_is_a_problem(tmp_path, on):
    text = own("release-publish.yml").replace(PUBLISH_ON, on)
    assert problems_of(tmp_path, "release-publish.yml", text) == [
        "release-publish.yml runs on pushes to main beyond CHANGES.md; filter on "
        "`paths: [CHANGES.md]` alone, since a release reaches main as a change to that file"]


@pytest.mark.parametrize("on", [
    "  push:\n    branches: [develop]\n    paths:\n      - CHANGES.md\n",
    "  push:\n    branches: [main]\n    paths:\n      - docs/**\n",
    "  workflow_run:\n    workflows: [CI]\n"])
def test_release_publish_that_never_runs_on_a_release_is_a_problem(tmp_path, on):
    text = own("release-publish.yml").replace(PUBLISH_ON, on)
    assert problems_of(tmp_path, "release-publish.yml", text) == [
        "release-publish.yml does not run on a push of CHANGES.md to main; a merged "
        "release pull request would never be published"]


LACKS_GUARD = ("finalize lacks `if: needs.publish.outputs.release_id != ''`; it would run "
               "after every push of CHANGES.md that publishes nothing, with an empty "
               "release_id, and fail")


@pytest.mark.parametrize("guard", [
    "${{ needs.publish.outputs.release_id != '' && !cancelled() }}",
    "!cancelled() && needs.publish.outputs.release_id != ''",
    "(needs.publish.outputs.release_id != '') && success()",
    "${{ success() && (needs.publish.outputs.release_id != '') }}",
    "needs.publish.outputs.release_id != '' && (github.ref == 'refs/heads/main' || false)"])
def test_a_stricter_finalize_guard_counts(tmp_path, guard):
    text = own_publish().replace(GUARD, f"    if: \"{guard}\"\n")
    assert finalize_problems(tmp_path, text) == []


@pytest.mark.parametrize("guard", [
    "always()",
    "always() && needs.publish.outputs.release_id != ''",
    "needs.publish.outputs.release_id != '' || always()",
    "needs.publish.outputs.release_id != '' || github.event_name == 'push'",
    "(needs.publish.outputs.release_id != '' || true) && success()",
    "needs.publish.outputs.release_id != 'x'",
    "needs.publish.outputs.release_id"])
def test_a_finalize_guard_that_lets_an_empty_release_id_through_is_a_problem(tmp_path, guard):
    text = own_publish().replace(GUARD, f"    if: \"{guard}\"\n")
    assert finalize_problems(tmp_path, text) == [LACKS_GUARD]


# --- unreadable files behind unreadable callers, non-UTF-8 files ------------

def calling(target, flow=True):
    """An unreadable workflow (a flow mapping) whose job calls `target`."""
    return ("on:\n  workflow_call:\njobs:\n  x:\n"
            f"    uses: ./.github/workflows/{target}\n"
            + ("    with: {ref: y}\n" if flow else ""))


def unreadable_names(found):
    return sorted(name for name, _, detail in found if detail.startswith("cannot be read"))


def test_an_unreadable_file_an_unreadable_core_caller_calls_is_a_problem(tmp_path, store):
    """calls() reads only the files that parse, so a file called by an
    unreadable release-build.yml was skipped."""
    found = problems(tmp_path, store, release_build=calling("build-local.yml"),
                     build_local=FLOW)
    assert unreadable_names(found) == ["build-local.yml", "release-build.yml"]


def test_an_unreadable_chain_below_a_core_caller_is_followed(tmp_path, store):
    found = problems(tmp_path, store, release_build=calling("one.yml"),
                     one=calling("two.yml"), two=FLOW)
    assert unreadable_names(found) == ["one.yml", "release-build.yml", "two.yml"]


def test_an_unreadable_file_only_an_unrelated_unreadable_file_calls_is_skipped(tmp_path,
                                                                             store):
    assert problems(tmp_path, store, deploy=calling("deploy-lib.yml"),
                    deploy_lib=FLOW) == []


def test_a_call_in_a_comment_of_an_unreadable_file_does_not_count(tmp_path, store):
    release_build = calling("x.yml").replace("    uses:", "    # uses:")
    found = problems(tmp_path, store, release_build=release_build, x=FLOW)
    assert unreadable_names(found) == ["release-build.yml"]


def with_bytes(tmp_path, store, name, data):
    root = repo(tmp_path, store, {"ci.yml": CI, "release-build.yml": BUILD,
                                  "release-publish.yml": PUBLISH, "changelog.yml": CHANGELOG,
                                  "release-pr.yml": RELEASE_PR})
    (root / ".github/workflows" / name).write_bytes(data)
    docs = callers.read_workflows(root)
    return [(i.name, i.state, i.detail) for i in
            callers.validate(docs, load_pieces(store), store)]


LATIN1 = "name: D\xe9ploiement\non:\n  push:\n".encode("latin-1")


def test_an_unrelated_workflow_that_is_not_utf8_is_skipped(tmp_path, store):
    """read_workflows let the UnicodeDecodeError escape and check crashed."""
    assert with_bytes(tmp_path, store, "deploy.yml", LATIN1) == []


def test_a_core_caller_that_is_not_utf8_is_a_problem(tmp_path, store):
    found = with_bytes(tmp_path, store, "release-build.yml", LATIN1)
    assert ("release-build.yml", "problem",
            "cannot be read: it is not UTF-8 text (byte 0xe9 at offset 7)") in found


def test_a_piece_marker_in_a_file_that_is_not_utf8_is_still_found(tmp_path, store):
    found = with_bytes(tmp_path, store, "ri-old.yml", b"# repo-infra: ri-a v1\n" + LATIN1)
    assert ("ri-old.yml", "problem",
            "cannot be read: it is not UTF-8 text (byte 0xe9 at offset 29)") in found


# --- an installed piece nothing calls ---------------------------------------

UNCALLED = ("{} is installed and no workflow calls it, so it never runs. Add its Call: "
            "from the catalogue to a caller, or remove the file")


def test_a_remote_piece_no_workflow_calls_is_not_an_installed_copy_problem(tmp_path):
    """A remote piece is called, never installed (D33); a core one that no
    workflow calls is reported by check.core_call_items instead."""
    job = "  python:\n    " + SKIP_IF + "\n    uses: ./.github/workflows/ri-ci-python.yml\n    with:\n" \
          "      ref: ${{ inputs.ref }}\n\n"
    assert job in own("ci.yml")
    text = own("ci.yml").replace(job, "").replace("plugin, python,", "plugin,")
    folder = tmp_path / ".github/workflows"
    folder.mkdir(parents=True)
    for path in (REPO / ".github/workflows").glob("*.yml"):
        (folder / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    (folder / "ci.yml").write_text(text, encoding="utf-8")
    found = [(i.name, i.detail) for i in
             callers.validate(callers.read_workflows(tmp_path), load_pieces(), home=True)]
    assert found == []


def test_a_piece_called_only_from_an_unreadable_workflow_is_not_called_unused(tmp_path,
                                                                            store):
    found = problems(tmp_path, store, release_build=calling("ri-a.yml"))
    assert ("ri-a.yml", "problem", UNCALLED.format("ri-a.yml")) not in found
    assert unreadable_names(found) == ["release-build.yml"]


def test_an_installed_piece_in_the_store_fixture_nothing_calls_is_a_problem(tmp_path, store):
    found = problems(tmp_path, store, deploy="# ri-b.yml is installed\non: push\njobs: {}\n")
    assert ("ri-b.yml", "problem", UNCALLED.format("ri-b.yml")) in found


def test_a_call_omitting_a_required_ref_is_reported_once(tmp_path, store):
    """call_problems and the D28 rule both named it."""
    store_ = make_assets(tmp_path / "required", {
        "ri-a": workflow_piece("ri-a", 1).replace(
            "        required: false\n        default: ''\n", "        required: true\n", 1)})
    ci = CI.replace("    with:\n      ref: ${{ inputs.ref }}\n", "", 1)
    found = [detail for name, _, detail in problems(tmp_path, store_, ci=ci)
             if name == "ci.yml" and "ref" in detail]
    assert found == ["job a calls ri-a.yml without its required input ref"]


# --- review of the follow-up wave -------------------------------------------

def own_validated(tmp_path, ci):
    folder = tmp_path / ".github/workflows"
    folder.mkdir(parents=True)
    for path in (REPO / ".github/workflows").glob("*.yml"):
        (folder / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    (folder / "ci.yml").write_text(ci, encoding="utf-8")
    return [(i.name, i.detail) for i in
            callers.validate(callers.read_workflows(tmp_path), load_pieces(), home=True)]


def test_the_home_only_library_tests_are_not_a_piece_to_call(tmp_path):
    """ri-ci-lib.yml left the manifest (D33): repo-infra keeps it for itself."""
    job = "  lib:\n    " + SKIP_IF + "\n    uses: ./.github/workflows/ri-ci-lib.yml\n    with:\n" \
          "      ref: ${{ inputs.ref }}\n\n"
    assert job in own("ci.yml")
    text = own("ci.yml").replace(job, "").replace("needs: [lib, ", "needs: [")
    assert own_validated(tmp_path, text) == []


def test_the_home_only_selftest_is_not_a_piece_to_call(tmp_path):
    """ri-ci-repo-infra-selftest.yml left the manifest like ri-ci-lib.yml:
    repo-infra calls it through ./ and nothing asks a repository for it."""
    job = "  selftest:\n    " + SKIP_IF + "\n    uses: ./.github/workflows/" \
          "ri-ci-repo-infra-selftest.yml\n    with:\n      ref: ${{ inputs.ref }}\n\n"
    assert job in own("ci.yml")
    assert own_validated(tmp_path / "with", own("ci.yml")) == []
    text = own("ci.yml").replace(job, "").replace(", selftest", "")
    assert "selftest" not in text
    assert own_validated(tmp_path / "without", text) == []


def test_ci_without_release_pr_current_is_one_item(tmp_path):
    job = ("  release-pr-current:\n    " + SKIP_IF + "\n    uses: ./.github/workflows/ri-release-pr-current.yml\n"
           "    permissions:\n      contents: read\n      pull-requests: read\n"
           "      checks: write\n    with:\n      ref: ${{ inputs.ref }}\n\n")
    text = own("ci.yml").replace(job, "").replace(", release-pr-current, ", ", ")
    assert own_validated(tmp_path, text) == [(
        "ci.yml", "ci.yml calls no ri-release-pr-current.yml; an open release pull request "
        "is not marked stale when main moves (D28). Add its Call: from the catalogue")]


# --- the release pull request skips ci.yml's jobs (D31) ---------------------

SKIP = callers._expression(SKIP_IF.removeprefix("if: "))
NO_SKIP = ("job {} lacks the `if:` of assets/callers/release-pr-skip.yml in the repo-infra "
           "skill; approving the parked run on a release pull request would build and test "
           "everything a second time (D31). Add it, or join it to the job's own `if:` with &&")


def skip_problems(guard, name="ci.yml", job="build"):
    """release_skip_problems for a file `name` with a job `job` guarded by
    `guard` (no `if:` when None) and a ci-passed without the skip."""
    line = f"    if: {guard}\n" if guard is not None else ""
    text = (f"jobs:\n  {job}:\n{line}    runs-on: ubuntu-latest\n    steps:\n"
            "      - run: 'true'\n  ci-passed:\n    if: always()\n    needs: [build]\n"
            "    runs-on: ubuntu-latest\n    steps:\n      - run: 'true'\n")
    return callers.release_skip_problems({name: workflow.load(text)})


def test_a_ci_job_without_the_skip_is_a_problem():
    assert skip_problems(None) == [("ci.yml", NO_SKIP.format("build"))]


def test_the_canonical_skip_passes():
    assert skip_problems(SKIP_IF.removeprefix("if: ")) == []


def test_the_skip_in_other_spacing_and_parentheses_passes():
    assert skip_problems("${{(" + SKIP.replace(" ", "") + ")}}") == []


def test_a_stricter_guard_joined_with_and_passes():
    assert skip_problems("${{ github.event_name == 'push' && " + SKIP + " }}") == []


def test_the_skip_joined_with_or_is_a_problem():
    assert skip_problems("${{ github.event_name == 'push' || " + SKIP + " }}") == [
        ("ci.yml", NO_SKIP.format("build"))]


@pytest.mark.parametrize("dropped", [
    " && github.event.pull_request.user.login == 'github-actions[bot]'",
    " && github.event.pull_request.head.repo.full_name == github.repository"])
def test_a_looser_skip_is_a_problem(dropped):
    """A term short of isReleasePr skips a person's or a fork's release/x,
    which ci-passed judges by the ordinary rules: green untested."""
    assert dropped in SKIP
    assert skip_problems("${{ " + SKIP.replace(dropped, "") + " }}") == [("ci.yml", NO_SKIP.format("build"))]


def test_ci_passed_needs_no_skip():
    assert callers.release_skip_problems({"ci.yml": workflow.load(CI_PASSED)}) == []


def test_jobs_of_other_files_are_not_checked():
    assert skip_problems(None, name="release-build.yml") == []
    assert skip_problems(None, name="ci-local.yml") == []


def test_this_repositorys_ci_yml_skips_on_every_job_but_the_closing_two():
    doc = workflow.load(own("ci.yml"))
    guarded = {job_id for job_id, job in callers.jobs(doc).items()
               if callers._unwrapped(SKIP) in callers.conjuncts(job.get("if", ""))}
    assert guarded == set(callers.jobs(doc)) - {"ci-passed", "release-verdict"}


MTUSPY_CALLERS = ["ci.yml", "release-build.yml", "release-publish.yml", "changelog.yml",
                  "release-pr.yml"]


@pytest.mark.parametrize("name", MTUSPY_CALLERS)
def test_the_mtuspy_example_callers_have_no_problem(tmp_path, name):
    # The callers are read as a v2 consumer holds them: alone, calling
    # repo-infra's pieces remotely.
    example = REPO / "skills/repo-infra/references/examples/mtuspy"
    folder = tmp_path / ".github/workflows"
    folder.mkdir(parents=True)
    for caller in MTUSPY_CALLERS:
        (folder / caller).write_text((example / caller).read_text(encoding="utf-8"),
                                     encoding="utf-8")
    docs = callers.read_workflows(tmp_path)
    assert [i.detail for i in callers.validate(docs, load_pieces()) if i.name == name] == []


# --- release-pr.yml (D33) -------------------------------------------------------


def release_pr(text):
    return callers.release_pr_problems({"release-pr.yml": workflow.load(text)}, {})


def test_the_shipped_release_pr_has_no_problem():
    assert release_pr(RELEASE_PR) == []


def test_a_job_between_prepare_and_finish_that_finish_needs_is_fine():
    text = RELEASE_PR.replace(
        "  finish:\n    needs: [prepare, build, test]",
        "  gate:\n    needs: prepare\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - run: 'true'\n\n  finish:\n    needs: [prepare, build, test, gate]")
    assert release_pr(text) == []


def test_finish_that_does_not_need_an_added_job_is_a_problem():
    text = RELEASE_PR.replace(
        "  finish:\n", "  gate:\n    needs: prepare\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: 'true'\n\n  finish:\n")
    assert release_pr(text) == [("release-pr.yml", "finish does not need gate; it would "
                                 "open the pull request before they finished")]


def test_a_release_pr_without_ci_is_a_problem():
    text = RELEASE_PR.replace("uses: ./.github/workflows/ci.yml", "uses: ./.github/workflows/x.yml")
    assert ("release-pr.yml", "does not call ci.yml; the release pull request would open "
            "untested or unbuilt") in release_pr(text)


def test_a_release_pr_without_finish_is_a_problem():
    text = RELEASE_PR.replace("ri-release-finish.yml", "ri-release-other.yml")
    assert ("release-pr.yml", "calls no ri-release-finish; copy assets/callers/release-pr.yml "
            "in the repo-infra skill") in release_pr(text)


def test_a_build_that_does_not_need_prepare_is_a_problem():
    text = RELEASE_PR.replace("  build:\n    needs: prepare\n", "  build:\n")
    assert release_pr(text) == [("release-pr.yml", "job build does not need prepare; it "
                                 "would build or test before the release branch exists")]


def test_a_release_pr_without_workflow_dispatch_is_a_problem():
    text = RELEASE_PR.replace("  workflow_dispatch:\n", "  workflow_call:\n")
    assert release_pr(text) == [("release-pr.yml", "has no workflow_dispatch trigger; "
                                 "nobody can start a release")]


def test_no_release_pr_is_no_problem_of_its_own():
    """CORE_CALLERS reports the missing file; release_pr_problems adds nothing."""
    assert callers.release_pr_problems({}, {}) == []


def test_a_missing_release_pr_is_reported_by_validate(tmp_path):
    found = problems_of(tmp_path, "ci.yml", own("ci.yml"))
    assert found == []
    (tmp_path / ".github/workflows/release-pr.yml").unlink()
    docs = callers.read_workflows(tmp_path)
    assert [(i.name, i.state) for i in callers.validate(docs, load_pieces(), home=True)
            if i.name == "release-pr.yml"] == [("release-pr.yml", "missing")]


def test_validate_reviews_release_pr(tmp_path):
    text = own("release-pr.yml").replace("  build:\n    needs: prepare\n", "  build:\n")
    assert "job build does not need prepare; it would build or test before the release " \
           "branch exists" in problems_of(tmp_path, "release-pr.yml", text)


def test_this_repositorys_release_pr_has_no_problem():
    assert release_pr(own("release-pr.yml")) == []


# --- the action's own test (D33) --------------------------------------------

def test_a_ci_yml_that_calls_the_action_piece_must_call_action_test():
    ci = workflow.load(
        "jobs:\n  action:\n    uses: oposs/repo-infra/.github/workflows/"
        "ri-ci-github-action.yml@v2\n")
    assert callers.action_test_problems({"ci.yml": ci}) == [(
        "ci.yml", "ci.yml calls ri-ci-github-action and not ./.github/workflows/"
        "action-test.yml; the action's own test never runs. Add the job `action-test` "
        "from the catalogue entry of ri-ci-github-action")]


def test_a_ci_yml_that_calls_both_is_fine():
    ci = workflow.load(
        "jobs:\n  action:\n    uses: oposs/repo-infra/.github/workflows/"
        "ri-ci-github-action.yml@v2\n  action-test:\n"
        "    uses: ./.github/workflows/action-test.yml\n")
    assert callers.action_test_problems({"ci.yml": ci}) == []


def test_validate_reports_a_ci_yml_without_the_action_test():
    ci = workflow.load(
        "jobs:\n  action:\n    uses: oposs/repo-infra/.github/workflows/"
        "ri-ci-github-action.yml@v2\n")
    found = [i.detail for i in callers.validate({"ci.yml": ci}, load_pieces())
             if "action-test.yml" in i.detail]
    assert len(found) == 1


def test_a_job_without_uses_and_a_ci_yml_without_jobs_are_tolerated():
    for text in ("jobs:\n  build:\n    runs-on: x\n", "on: push\n"):
        assert callers.action_test_problems({"ci.yml": workflow.load(text)}) == []


def test_the_consumers_action_test_keeps_the_ref_contract():
    ci = workflow.load(
        "jobs:\n  action-test:\n    uses: ./.github/workflows/action-test.yml\n"
        "    with:\n      ref: ${{ inputs.ref }}\n")
    bad = workflow.load(
        "on:\n  workflow_call:\n    inputs:\n      ref:\n        type: string\n"
        "jobs:\n  t:\n    runs-on: x\n    steps:\n      - uses: actions/checkout@v7\n")
    found = callers.ref_contract_problems({"ci.yml": ci, "action-test.yml": bad}, set())
    assert any(name == "action-test.yml" for name, _ in found)


# --- calls of repo-infra's pieces (D33) -------------------------------------

REAL = load_pieces()
V2 = "oposs/repo-infra/.github/workflows/{}.yml@v2"


def consumer(ci_jobs, files=None):
    """A consumer whose ci.yml holds `ci_jobs` (text under jobs:), validated
    against the real pieces."""
    text = ("on:\n  push:\n    branches: [main]\n  pull_request:\n    branches: [main]\n"
            "  workflow_call:\n    inputs:\n      ref:\n        description: x\n"
            "        type: string\n        required: false\n        default: ''\n"
            "permissions:\n  contents: read\njobs:\n" + ci_jobs)
    docs = {"ci.yml": workflow.load(text), **(files or {})}
    return [i.detail for i in callers.validate(docs, REAL) if i.name == "ci.yml"]


def job(uses, extra=""):
    return (f"  rust:\n    {SKIP_IF}\n    uses: {uses}\n    with:\n"
            f"      ref: ${{{{ inputs.ref }}}}\n{extra}")


@pytest.mark.parametrize("ref", ["main", "v2.0.0", "V2", "v1", "", " v2"])
def test_a_piece_called_at_another_ref_is_a_problem(ref):
    uses = f"oposs/repo-infra/.github/workflows/ri-ci-rust.yml@{ref}"
    assert (f"job rust calls {uses}; call repo-infra's pieces at @v2, the tag every "
            "release moves (D33)") in consumer(job(f"'{uses}'"))


def test_a_piece_called_without_a_ref_is_a_problem():
    uses = "oposs/repo-infra/.github/workflows/ri-ci-rust.yml"
    assert (f"job rust calls {uses}; call repo-infra's pieces at @v2, the tag every "
            "release moves (D33)") in consumer(job(uses))


def test_the_owner_and_repository_are_matched_in_any_case():
    """GitHub finds a repository whatever the case of its name."""
    uses = "OPOSS/Repo-Infra/.github/workflows/ri-ci-rust.yml@main"
    assert (f"job rust calls {uses}; call repo-infra's pieces at @v2, the tag every "
            "release moves (D33)") in consumer(job(uses))


def test_a_piece_called_at_v2_is_fine():
    assert not [d for d in consumer(job(V2.format("ri-ci-rust"))) if "job rust" in d]


def test_a_call_to_a_file_that_is_no_piece_is_a_problem():
    uses = V2.format("ri-nothing")
    assert f"job rust calls {uses}, which is not a piece of repo-infra" in consumer(job(uses))


def test_a_local_call_to_a_remote_piece_is_the_v1_layout():
    found = consumer(job("./.github/workflows/ri-ci-rust.yml"))
    assert ("job rust calls ./.github/workflows/ri-ci-rust.yml, a copy of the piece (v1 "
            f"layout); call {V2.format('ri-ci-rust')} and run apply to migrate (D33)") in found


def test_inherit_on_a_remote_call_is_a_problem():
    found = consumer(job(V2.format("ri-ci-rust"), "    secrets: inherit\n"))
    assert (f"job rust passes secrets: inherit to {V2.format('ri-ci-rust')}; GitHub does not "
            "pass inherited secrets to a workflow of another organisation. Pass each secret "
            "by name") in found


def test_inherit_does_not_hide_a_missing_required_secret(tmp_path):
    secret = ("    secrets:\n      TOKEN:\n        description: t\n"
              "        required: true\n")
    piece = workflow_piece("ri-r", 2).replace("permissions:\n", secret + "permissions:\n", 1)
    store_ = make_assets(tmp_path, {}, remote={"ri-r": piece})
    uses = V2.format("ri-r")
    ci = workflow.load(f"jobs:\n  r:\n    uses: {uses}\n    secrets: inherit\n")
    found = [i.detail for i in callers.validate({"ci.yml": ci}, load_pieces(store_), store_)]
    assert f"job r passes secrets: inherit to {uses}; GitHub does not pass inherited " \
           "secrets to a workflow of another organisation. Pass each secret by name" in found
    assert "job r calls ri-r.yml without its required secret TOKEN; pass it, or write " \
           "`secrets: inherit`" not in found
    assert [d for d in found if d.startswith("job r calls ri-r.yml without its required "
                                             "secret TOKEN")] != []


def test_an_input_the_remote_piece_lacks_is_a_problem():
    found = consumer(job(V2.format("ri-ci-rust"), "      nonsense: 1\n"))
    assert ("job rust calls ri-ci-rust.yml with the input nonsense, which ri-ci-rust.yml "
            "does not declare") in found


def test_a_remote_call_in_repo_infra_itself_is_a_problem():
    text = own("ci.yml").replace("uses: ./.github/workflows/ri-ci-python.yml",
                                 "uses: " + V2.format("ri-ci-python"))
    docs = callers.read_workflows(REPO)
    docs["ci.yml"] = workflow.load(text)
    found = [i.detail for i in callers.validate(docs, REAL, home=True)]
    assert (f"job python calls {V2.format('ri-ci-python')}; repo-infra calls its own pieces "
            "through ./ so a pull request runs the pieces it changes (D33)") in found


def test_permissions_of_a_remote_call_are_checked_against_the_piece():
    text = job(V2.format("ri-release-pr-current")).replace("  rust:", "  current:")
    assert ("job current grants contents: read and ri-release-pr-current.yml needs checks: "
            "write, pull-requests: read; GitHub refuses to start the run") in consumer(text)


def test_a_remote_call_without_ref_input_is_a_ref_problem():
    found = consumer(f"  rust:\n    {SKIP_IF}\n    uses: {V2.format('ri-ci-rust')}\n")
    assert any(d.startswith("job rust calls ri-ci-rust.yml, which takes `ref`, without")
               for d in found)


def test_a_finish_job_without_actions_write_is_a_problem(tmp_path):
    """#58: finish deletes the parked runs of the pull request it opens."""
    grant = "      checks: write\n      actions: write\n    with:\n      version:"
    text = own("release-pr.yml")
    assert text.count(grant) == 1
    found = problems_of(tmp_path, "release-pr.yml",
                        text.replace(grant, "      checks: write\n    with:\n      version:"))
    assert any(d.startswith("job finish grants") and "actions: write" in d for d in found), found
