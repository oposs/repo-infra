"""D30: a called workflow can only lower the permissions it receives, and
GitHub checks every job of the called file, skipped or not."""

from repo_infra import callers, workflow

PIECE = """on:
  workflow_call:
permissions:
  contents: read
jobs:
  mark:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions:
      contents: read
      checks: write
    steps:
      - run: echo
"""


def caller(job_permissions="", top="permissions:\n  contents: read\n"):
    return workflow.load(
        "on:\n  push:\n" + top + "jobs:\n  mark:\n    uses: ./.github/workflows/p.yml\n"
        + job_permissions)


def found(ci):
    return callers.permission_problems({"ci.yml": ci, "p.yml": workflow.load(PIECE)})


def test_needed_takes_job_level_permissions_over_the_workflow_level():
    assert callers.needed("p.yml", {"p.yml": workflow.load(PIECE)}) == {"contents": 1,
                                                                       "checks": 2}


def test_a_workflow_level_grant_below_the_need_is_a_problem():
    assert found(caller()) == [(
        "ci.yml", "job mark grants contents: read and p.yml needs checks: write; GitHub "
        "refuses to start the run")]


def test_a_job_level_grant_covers_the_need():
    grant = "    permissions:\n      contents: read\n      checks: write\n"
    assert found(caller(grant)) == []


def test_no_permissions_anywhere_is_a_problem_at_the_top():
    assert found(caller(top="")) == [(
        "ci.yml", "job mark declares no permissions; p.yml needs checks: write, "
        "contents: read. Grant them on the job")]


def test_write_all_covers_everything():
    assert found(caller(top="permissions: write-all\n")) == []


def test_the_need_reaches_through_an_inheriting_call():
    middle = workflow.load("on:\n  workflow_call:\njobs:\n  inner:\n"
                           "    uses: ./.github/workflows/p.yml\n")
    top = workflow.load("on:\n  workflow_dispatch:\njobs:\n  test:\n"
                        "    uses: ./.github/workflows/ci.yml\n"
                        "    permissions:\n      contents: read\n")
    docs = {"release-pr.yml": top, "ci.yml": middle, "p.yml": workflow.load(PIECE)}
    assert callers.permission_problems(docs) == [(
        "release-pr.yml", "job test grants contents: read and ci.yml needs checks: write; "
        "GitHub refuses to start the run")]


def test_a_cycle_does_not_recurse_forever():
    loop = workflow.load("on:\n  workflow_call:\njobs:\n  again:\n"
                         "    uses: ./.github/workflows/loop.yml\n")
    assert callers.needed("loop.yml", {"loop.yml": loop}) == {}


def test_an_empty_permissions_mapping_grants_nothing():
    assert callers.grant({}) == {}
    assert found(caller(top="permissions: {}\n")) == [(
        "ci.yml", "job mark grants nothing and p.yml needs checks: write, contents: read; "
        "GitHub refuses to start the run")]


def test_a_job_level_grant_replaces_a_workflow_level_write_all():
    low = "    permissions:\n      contents: read\n"
    assert found(caller(low, top="permissions: write-all\n")) == [(
        "ci.yml", "job mark grants contents: read and p.yml needs checks: write; GitHub "
        "refuses to start the run")]


def test_read_all_does_not_cover_a_write_need_and_has_no_id_token_level():
    piece = PIECE.replace("checks: write", "id-token: write")
    docs = {"ci.yml": caller(top="permissions: read-all\n"), "p.yml": workflow.load(piece)}
    [(name, text)] = callers.permission_problems(docs)
    assert "id-token: read" not in text
    assert text.endswith("p.yml needs id-token: write; GitHub refuses to start the run")


def test_a_file_with_its_own_trigger_and_workflow_call_is_checked_at_the_top():
    ci = workflow.load("on:\n  push:\n  pull_request:\n  workflow_call:\njobs:\n  mark:\n"
                       "    uses: ./.github/workflows/p.yml\n")
    assert found(ci) == [(
        "ci.yml", "job mark declares no permissions; p.yml needs checks: write, "
        "contents: read. Grant them on the job")]
