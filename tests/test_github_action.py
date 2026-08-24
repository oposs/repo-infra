"""The `github-action` ecosystem (D20): the seam, and the manifest validator.

The validator is a script embedded in a shipped CI block, so these tests run
it the way CI does -- `bash -c` over the block's own `run:` text, against a
throwaway repository tree. String assertions about the asset would pass just
as happily against a script that checks nothing, which is the whole lesson of
D19.
"""

import json
import pathlib
import subprocess

import pytest
import yaml

from repo_infra.detect import Detection
from repo_infra.state import NEEDS_ATTENTION_STATES, classify_contracts

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
BLOCK = ASSETS / "ci/ci-github-action.yml"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))

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
    block = yaml.safe_load(BLOCK.read_text(encoding="utf-8"))
    steps = block["action-manifest"]["steps"]
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

def test_the_seam_names_the_one_path_the_contract_fixes(tmp_path):
    """A fixed path is the point (D20): no substitution token, no entry in
    .github/repo-infra.json, nothing for a repository to configure."""
    block = yaml.safe_load(BLOCK.read_text(encoding="utf-8"))
    assert block["action-test"] == {"uses": "./.github/workflows/action-test.yml"}


def test_the_seam_job_carries_no_keys_a_uses_job_cannot_have():
    """`runs-on`, `steps` and `timeout-minutes` are all rejected by GitHub on a
    job that calls a reusable workflow -- which is why the contract makes the
    timeout the project's business."""
    block = yaml.safe_load(BLOCK.read_text(encoding="utf-8"))
    assert set(block["action-test"]) == {"uses"}


def test_the_block_declares_both_jobs():
    assert MANIFEST["ci_blocks"]["ci-github-action"]["jobs"] == ["action-manifest", "action-test"]


# --- detection -----------------------------------------------------------

def test_action_yml_selects_the_github_action_ecosystem(tmp_path):
    (tmp_path / "action.yml").write_text(ACTION, encoding="utf-8")
    result = Detection.load(ASSETS / "detection.json").detect(tmp_path)
    assert result.ecosystems == ["github-action"]
    assert result.blocks == ["ci-lib", "ci-github-action"]


def test_the_ecosystem_stacks_with_a_language_ecosystem(tmp_path):
    """An action repository is still written in something. Being an action is
    not a claim about the language, so the blocks add up rather than compete."""
    (tmp_path / "action.yml").write_text(ACTION, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('version = "1.0.0"\n', encoding="utf-8")
    result = Detection.load(ASSETS / "detection.json").detect(tmp_path)
    assert result.ecosystems == ["github-action", "python"]
    assert result.blocks == ["ci-lib", "ci-github-action", "ci-python"]


def test_an_action_repository_declares_no_version_file(tmp_path):
    """Actions are tag-versioned; there is no file for the release workflow to
    write a version into."""
    (tmp_path / "action.yml").write_text(ACTION, encoding="utf-8")
    result = Detection.load(ASSETS / "detection.json").detect(tmp_path)
    assert result.version_files == []


# --- the contract check --------------------------------------------------

def action_repo_result(tmp_path, seam=None):
    (tmp_path / "action.yml").write_text(ACTION, encoding="utf-8")
    if seam is not None:
        wf = tmp_path / ".github/workflows"
        wf.mkdir(parents=True, exist_ok=True)
        (wf / "action-test.yml").write_text(seam, encoding="utf-8")
    return Detection.load(ASSETS / "detection.json").detect(tmp_path)


def test_check_reports_a_missing_action_test_workflow(tmp_path):
    """Installing the block without the project's half does not leave a gap --
    it makes ci.yml invalid, so no job in the repository reports at all."""
    items = classify_contracts(tmp_path, action_repo_result(tmp_path))
    assert [i.name for i in items] == ["action-test"]
    assert items[0].state == "conflict"
    assert "action-test.yml" in items[0].detail


def test_a_present_action_test_workflow_reports_nothing(tmp_path):
    result = action_repo_result(tmp_path, seam="on: [workflow_call]\njobs: {}\n")
    assert classify_contracts(tmp_path, result) == []


def test_a_repository_that_is_not_an_action_is_not_asked_for_the_seam(tmp_path):
    (tmp_path / "pyproject.toml").write_text('version = "1.0.0"\n', encoding="utf-8")
    result = Detection.load(ASSETS / "detection.json").detect(tmp_path)
    assert classify_contracts(tmp_path, result) == []


def test_the_contract_item_needs_attention_so_check_exits_nonzero(tmp_path):
    """`conflict` and not `missing`: there is nothing for `apply` to install,
    and _ordered_names only ever hands apply `missing`/`outdated` items."""
    items = classify_contracts(tmp_path, action_repo_result(tmp_path))
    assert items[0].state in NEEDS_ATTENTION_STATES
    assert items[0].state not in ("missing", "outdated")
