# tests/test_release_guard.py
"""The seam between the guard's logic and the workflow that runs it.

`lib/checks.test.js` proves `guardIgnoreIds` gathers the right ids. Those tests
run under node, which `make check` does not have -- and neither proves the
shipped workflow actually calls the function. A guard whose logic is perfect and
unreferenced is the bug it replaced, so these three lines are checked here, in
the gate that always runs.
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
RELEASE_PR = ASSETS / "workflows/release-pr.yml"
CHECKS_JS = ASSETS / "workflows/lib/checks.js"


@pytest.fixture
def workflow():
    return RELEASE_PR.read_text(encoding="utf-8")


def test_the_guard_gathers_its_ignore_ids_through_the_tested_function(workflow):
    assert "checks.guardIgnoreIds(github, {" in workflow
    assert "ignoreCheckRunIds }" in workflow, "the gathered ids must reach waitForChecks"
    assert "guardIgnoreIds" in CHECKS_JS.read_text(encoding="utf-8")


def test_the_guard_does_not_gather_ids_inline(workflow):
    """v1 called listJobsForWorkflowRun straight from the YAML, which is why the
    one-run-only rule could never be tested. Inline again means untested again.
    """
    assert "listJobsForWorkflowRun" not in workflow


def test_the_guard_passes_the_workflow_ref_it_needs_to_find_earlier_attempts(workflow):
    """Without GITHUB_WORKFLOW_REF, guardIgnoreIds falls back to this run alone
    -- silently, and with exactly the behaviour of the bug: a failed attempt
    leaves a check run that blocks every retry of that commit, forever.
    """
    assert "workflowRef: process.env.GITHUB_WORKFLOW_REF" in workflow
    assert "runId: context.runId" in workflow


def test_the_workflow_may_read_the_actions_api(workflow):
    """Listing this workflow's runs and their jobs is `actions: read`. Without
    it the guard step dies on a 403 instead of guarding.
    """
    permissions = workflow.split("permissions:", 1)[1].split("\njobs:", 1)[0]
    assert "actions: read" in permissions
