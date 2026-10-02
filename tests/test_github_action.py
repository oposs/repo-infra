"""The ri-ci-github-action piece (D20): the seam, and the manifest validator.

The validator is a script embedded in a shipped CI block, so these tests run
it the way CI does -- `bash -c` over the block's own `run:` text, against a
throwaway repository tree. String assertions about the asset would pass just
as happily against a script that checks nothing, which is the whole lesson of
D19.
"""

import pathlib
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
PIECE = ASSETS / "pieces/ri-ci-github-action/ri-ci-github-action.yml"

ACTION = """\
name: Example
description: An example action
inputs:
  version:
    description: The version
    required: true
  verbose:
    description: Chatty
    required: false
runs:
  using: composite
  steps:
    - shell: bash
      run: echo hi
"""


def validator_script():
    """The `run:` text of the block's checking step, verbatim.

    Read out of the asset rather than copied here, so a change to the asset
    that these tests do not cover shows up as a test that stopped exercising
    what ships.
    """
    piece = yaml.safe_load(PIECE.read_text(encoding="utf-8"))
    steps = piece["jobs"]["action-manifest"]["steps"]
    checks = [s for s in steps if s.get("name", "").startswith("Check action.yml")]
    assert len(checks) == 1, "the block no longer has exactly one checking step"
    return checks[0]["run"]


def repo(tmp_path, action=ACTION, workflows=None):
    (tmp_path / "action.yml").write_text(action, encoding="utf-8")
    wf = tmp_path / ".github/workflows"
    wf.mkdir(parents=True)
    for name, body in (workflows or {}).items():
        (wf / name).write_text(body, encoding="utf-8")
    return tmp_path


def run(tmp_path):
    return subprocess.run(
        ["bash", "-c", validator_script()],
        cwd=tmp_path, capture_output=True, text=True,
    )


def caller(with_block):
    return (
        "name: Test\n"
        "on: [workflow_call]\n"
        "jobs:\n"
        "  probe:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: ./\n"
        "        with:\n" + with_block
    )


# --- the happy path, so a failure below means something ------------------

def test_a_matching_caller_passes(tmp_path):
    result = run(repo(tmp_path, workflows={"action-test.yml": caller("          version: '1.0.0'\n")}))
    assert result.returncode == 0, result.stderr


def test_a_repository_with_no_local_callers_passes(tmp_path):
    assert run(repo(tmp_path)).returncode == 0


# --- the two silent mismatches this job exists for -----------------------

def test_an_undeclared_input_fails_and_is_named(tmp_path):
    """The defect this job was written for: GitHub only warns, so a test that
    passes an input the action does not declare stays green while the value is
    dropped. `oposs/mkp-builder` shipped exactly this for months."""
    tree = repo(tmp_path, workflows={
        "action-test.yml": caller("          version: '1.0.0'\n          cmk-min-version: '2.3.0p1'\n")})
    result = run(tree)
    assert result.returncode == 1
    assert "cmk-min-version" in result.stderr
    assert "does not declare" in result.stderr


def test_a_missing_required_input_fails_and_is_named(tmp_path):
    """The mirror image, and just as silent: `required: true` is documentation
    to the runner, not something it enforces."""
    result = run(repo(tmp_path, workflows={"action-test.yml": caller("          verbose: 'true'\n")}))
    assert result.returncode == 1
    assert "version" in result.stderr
    assert "omits required input" in result.stderr


def test_every_offending_key_is_reported_not_just_the_first(tmp_path):
    tree = repo(tmp_path, workflows={
        "action-test.yml": caller(
            "          version: '1.0.0'\n          alpha: '1'\n          beta: '2'\n")})
    result = run(tree)
    assert result.returncode == 1
    assert "alpha" in result.stderr and "beta" in result.stderr


def test_a_second_workflow_is_checked_too(tmp_path):
    """Not just the file the seam happens to name."""
    tree = repo(tmp_path, workflows={
        "action-test.yml": caller("          version: '1.0.0'\n"),
        "other.yml": caller("          version: '1.0.0'\n          nope: '1'\n"),
    })
    result = run(tree)
    assert result.returncode == 1
    assert "other.yml" in result.stderr


# --- and the false positives it must not produce -------------------------

def test_a_nested_local_action_is_not_checked_against_the_root_action(tmp_path):
    """`uses: ./tools/thing` is a different action with its own inputs. Checking
    it against the root action's would fail every repository that has one."""
    body = (
        "name: Test\non: [workflow_call]\njobs:\n  probe:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - uses: ./tools/thing\n        with:\n          whatever: '1'\n"
    )
    assert run(repo(tmp_path, workflows={"action-test.yml": body})).returncode == 0


def test_a_marketplace_action_is_not_checked_against_the_root_action(tmp_path):
    body = (
        "name: Test\non: [workflow_call]\njobs:\n  probe:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - uses: actions/checkout@v7\n        with:\n          fetch-depth: 0\n"
    )
    assert run(repo(tmp_path, workflows={"action-test.yml": body})).returncode == 0


def test_a_reusable_workflow_job_has_no_steps_and_does_not_crash_it(tmp_path):
    """ci.yml's own `action-test` job is a `uses:` job. Walking it as if it had
    steps is how a validator like this dies on the very file that calls it."""
    body = "name: CI\non: [push]\njobs:\n  action-test:\n    uses: ./.github/workflows/action-test.yml\n"
    assert run(repo(tmp_path, workflows={"ci.yml": body})).returncode == 0


# --- the manifest's own required fields ----------------------------------

@pytest.mark.parametrize("field", ["name", "description"])
def test_a_missing_top_level_field_fails(tmp_path, field):
    action = yaml.safe_load(ACTION)
    del action[field]
    result = run(repo(tmp_path, action=yaml.safe_dump(action)))
    assert result.returncode == 1
    assert field in result.stderr


def test_a_runs_block_without_using_fails(tmp_path):
    action = yaml.safe_load(ACTION)
    del action["runs"]["using"]
    result = run(repo(tmp_path, action=yaml.safe_dump(action)))
    assert result.returncode == 1
    assert "runs.using" in result.stderr


# --- the seam itself -----------------------------------------------------

def piece_jobs():
    return yaml.safe_load(PIECE.read_text(encoding="utf-8"))["jobs"]


def test_the_seam_names_the_one_path_the_contract_fixes():
    """A fixed path is the point (D20): no substitution token, no entry in
    .github/repo-infra.json, nothing for a repository to configure."""
    assert piece_jobs()["action-test"] == {"uses": "./.github/workflows/action-test.yml",
                                           "with": {"ref": "${{ inputs.ref }}"},
                                           "secrets": "inherit"}


def test_the_seam_job_carries_no_keys_a_uses_job_cannot_have():
    """`runs-on`, `steps` and `timeout-minutes` are all rejected by GitHub on a
    job that calls a reusable workflow -- which is why the contract makes the
    timeout the project's business. `with` and `secrets` are the two keys a
    calling job does carry: the ref and the inherited secrets."""
    assert set(piece_jobs()["action-test"]) == {"uses", "with", "secrets"}


def test_the_piece_declares_both_jobs():
    assert list(piece_jobs()) == ["action-manifest", "action-test"]
