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


@pytest.mark.parametrize("name", ["release-asset-x", "'release-files'", '"release-asset-"'])
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
