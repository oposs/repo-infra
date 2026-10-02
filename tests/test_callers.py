# tests/test_callers.py
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


def test_an_unreadable_caller_is_one_problem_and_the_rest_is_still_validated(tmp_path, store):
    found = problems(tmp_path, store, ci_local="jobs:\n  x:\n    with: {ref: y}\n",
                     ci=CI.replace("ri-a.yml", "ri-zz.yml"))
    assert ("ci-local.yml", "problem",
            "cannot be read: line 3: a flow mapping; write it in block style") in found
    assert any(d.endswith("ri-zz.yml, which does not exist") for _, _, d in found)


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
