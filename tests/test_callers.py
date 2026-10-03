# tests/test_callers.py
import json
import pathlib
import re

import pytest
from piecekit import CI_PASSED, install, make_assets, workflow_piece

from repo_infra import callers, workflow
from repo_infra.pieces import load_pieces

PIECE_INPUTS = ("      target:\n        description: The make target.\n"
                "        type: string\n        required: true\n")


@pytest.fixture
def store(tmp_path):
    return make_assets(tmp_path / "assets", {
        "ri-a": workflow_piece("ri-a", 1),
        "ri-b": workflow_piece("ri-b", 1, inputs=PIECE_INPUTS)})


def repo(tmp_path, store, files):
    root = tmp_path / "repo"
    for piece in load_pieces(store).values():
        install(root, piece.target, piece.files[piece.target])
    for name, text in files.items():
        install(root, f".github/workflows/{name}", text)
    return root


CI = """name: CI
on:
  push:
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
    uses: ./.github/workflows/ri-a.yml
    with:
      ref: ${{ inputs.ref }}
""" + CI_PASSED.replace("jobs:\n", "").replace("needs: []", "needs: [a]")

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
    base = {"ci.yml": CI, "release-build.yml": BUILD, "release-publish.yml": PUBLISH}
    base.update({k.replace("_", "-") + ".yml": v for k, v in files.items()})
    docs = callers.read_workflows(repo(tmp_path, store, base))
    return [(i.name, i.state, i.detail) for i in
            callers.validate(docs, load_pieces(store), store)]


def test_a_conforming_set_of_callers_has_no_problem(tmp_path, store):
    assert problems(tmp_path, store) == []


def test_a_missing_core_caller_is_named(tmp_path, store):
    root = repo(tmp_path, store, {"ci.yml": CI, "release-build.yml": BUILD})
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


def test_a_remote_reusable_workflow_is_a_problem(tmp_path, store):
    found = problems(tmp_path, store, ci=CI.replace(
        "./.github/workflows/ri-a.yml", "oposs/repo-infra/.github/workflows/ri-a.yml@v1"))
    assert any("another repository" in d for _, _, d in found)


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
    found = problems(tmp_path, store, ci=CI.replace("needs: [a]", "needs: []"))
    assert ("ci.yml", "problem",
            "ci-passed does not need a; it would report green while that job fails") in found


def test_ci_passed_must_run_always(tmp_path, store):
    found = problems(tmp_path, store, ci=CI.replace("if: always()", "if: success()"))
    assert any("lacks `if: always()`" in d for _, _, d in found)


def test_ci_passed_must_follow_the_pattern(tmp_path, store):
    found = problems(tmp_path, store, ci=CI.replace("timeout-minutes: 5\n    steps:\n      - uses",
                                                    "timeout-minutes: 9\n    steps:\n      - uses"))
    assert any("differs from the pattern" in d for _, _, d in found)


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


def test_ci_passed_may_check_out_the_base_commit():
    pattern = workflow.load(CI_PASSED)
    assert callers.ref_problems(pattern, True) != []
    assert callers.ref_problems(pattern, True, skip=("ci-passed",)) == []


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
        + text.split("jobs:\n", 1)[1].replace("needs: []", "needs: [a]"))
    assert callers.closing_problems({"ci.yml": ci}) == []
    # The release-mode steps load the library of the base commit: the pattern
    # keeps that checkout, which the ref contract exempts for ci-passed alone.
    checkout = callers.jobs(ci)["ci-passed"]["steps"][0]
    assert checkout["with"]["ref"] == "${{ github.event.pull_request.base.sha }}"
    assert checkout["with"]["path"] == "repo-infra-base"
    assert callers.ref_problems(ci, True) != []
    assert callers.ref_problems(ci, True, skip=("ci-passed",)) == []


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
    ci = CI.replace("ref: ${{ inputs.ref }}\n  ci-passed", f"ref: {value}\n  ci-passed")
    assert ci != CI
    assert len(ref_problems_found(tmp_path, store, ci)) == 1


@pytest.mark.parametrize("value", ["${{ inputs.ref }}", "${{inputs.ref}}", "'${{ inputs.ref }}'"])
def test_a_correct_ref_call_is_clean(tmp_path, store, value):
    ci = CI.replace("ref: ${{ inputs.ref }}\n  ci-passed", f"ref: {value}\n  ci-passed")
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
    return [i.detail for i in callers.validate(docs, load_pieces()) if
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
