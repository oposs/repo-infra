"""The D28 contract of a project-owned reusable workflow, read from text."""

import pytest

from repo_infra.seam import seam_problems

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


def test_a_conforming_file_has_no_problem():
    assert seam_problems(GOOD, reserved_artifacts=True) == []


def test_a_flow_style_trigger_declares_no_ref():
    text = GOOD.replace(GOOD.split("jobs:")[0], "name: x\non: [workflow_call]\n")
    assert seam_problems(text, False) == ["declares no workflow_call input `ref`"]


def test_an_input_of_another_name_is_not_ref():
    text = GOOD.replace("      ref:\n        type", "      reference:\n        type")
    assert "declares no workflow_call input `ref`" in seam_problems(text, False)


def test_a_checkout_in_a_second_job_without_ref_is_named():
    text = GOOD.replace("          fetch-depth: 0\n          ref: ${{ inputs.ref }}\n",
                        "          fetch-depth: 0\n")
    assert seam_problems(text, False) == [
        "has an actions/checkout step that does not check out `ref: ${{ inputs.ref }}`"]


def test_a_checkout_without_with_is_named():
    text = GOOD.replace("      - uses: actions/checkout@v7\n        with:\n"
                        "          ref: ${{ inputs.ref }}\n", "      - uses: actions/checkout@v7\n")
    assert len(seam_problems(text, False)) == 1


def test_a_comment_mentioning_ref_does_not_count():
    text = GOOD.replace("          fetch-depth: 0\n          ref: ${{ inputs.ref }}\n",
                        "          fetch-depth: 0\n          # ref: ${{ inputs.ref }}\n")
    assert len(seam_problems(text, False)) == 1


@pytest.mark.parametrize("name", ["release-asset-x", "'release-files'", '"release-asset-"',
                                  "Release-Files", "RELEASE-ASSET-x"])
def test_a_reserved_artifact_name_is_named_where_it_is_reserved(name):
    text = GOOD + ("      - uses: actions/upload-artifact@v7\n        with:\n"
                   f"          name: {name}\n          path: out/\n")
    problems = seam_problems(text, reserved_artifacts=True)
    assert len(problems) == 1 and "reserved for the release build" in problems[0]
    assert seam_problems(text, reserved_artifacts=False) == []


def test_a_step_display_name_is_not_an_artifact_name():
    text = GOOD + ("      - name: release-files\n        uses: actions/upload-artifact@v7\n"
                   "        with:\n          name: coverage\n          path: out/\n")
    assert seam_problems(text, reserved_artifacts=True) == []


# A form the reader does not follow is a conflict, never a pass: each of these
# checks out the default commit and would otherwise read as conforming.
STEPS = GOOD.split("    steps:\n")[0] + "    steps:\n"
UNREADABLE_CHECKOUT = ("has an actions/checkout step this check cannot read; write each "
                       "step in block style")


@pytest.mark.parametrize("steps", [
    "      -\n        uses: actions/checkout@v7\n",
    "      - run: true\n      - &co\n        uses: actions/checkout@v7\n      - *co\n",
    "      - &co\n        uses: actions/checkout@v7\n      - *co\n",
    "      - {uses: actions/checkout@v7}\n",
    "      - uses: actions/checkout@v7\n        with: {fetch-depth: 0}\n",
    "      - uses: actions/checkout@v7\n        env:\n          ref: ${{ inputs.ref }}\n",
    "      - uses: actions/checkout@v7\n        with:\n          ref: ${{ inputs.ref }}\n"
    "          ref: main\n",
])
def test_a_checkout_that_ignores_ref_in_any_form_is_a_problem(steps):
    assert seam_problems(STEPS + steps, False) != []


def test_a_bare_dash_step_is_read_like_any_other():
    text = STEPS + "      -\n        uses: actions/checkout@v7\n        with:\n" \
                   "          ref: ${{ inputs.ref }}\n"
    assert seam_problems(text, True) == []


def test_a_flow_style_step_is_named_as_unreadable():
    problems = seam_problems(STEPS + "      - {uses: actions/checkout@v7}\n", False)
    assert any(p.startswith(UNREADABLE_CHECKOUT) for p in problems)


def test_a_flow_style_upload_is_a_problem_where_names_are_reserved():
    text = GOOD + "      - uses: actions/upload-artifact@v7\n        with: {name: release-files}\n"
    problems = seam_problems(text, reserved_artifacts=True)
    assert problems and "actions/upload-artifact step this check cannot read" in problems[0]
    assert seam_problems(text, reserved_artifacts=False) == []


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
    text = GOOD.replace("          fetch-depth: 0\n          ref: ${{ inputs.ref }}\n",
                        f"          fetch-depth: 0\n          ref: {ref}\n")
    assert seam_problems(text, False) == [
        "has an actions/checkout step that does not check out `ref: ${{ inputs.ref }}`"]


@pytest.mark.parametrize("ref", ["'${{ inputs.ref }}' # pinned", "${{inputs.ref}}",
                                 "${{ INPUTS.REF }}", "${{ Inputs.Ref }}"])
def test_a_quoted_or_tight_inputs_ref_counts(ref):
    text = GOOD.replace("          fetch-depth: 0\n          ref: ${{ inputs.ref }}\n",
                        f"          fetch-depth: 0\n          ref: {ref}\n")
    assert seam_problems(text, False) == []


def test_the_action_name_is_read_in_any_case():
    text = STEPS + "      - uses: Actions/Checkout@v7\n"
    assert seam_problems(text, False) == [
        "has an actions/checkout step that does not check out `ref: ${{ inputs.ref }}`"]


def test_a_comment_after_with_is_not_a_value():
    text = GOOD.replace("          fetch-depth: 0\n", "").replace("        with:\n",
                                                                   "        with: # pinned\n")
    assert seam_problems(text, True) == []
