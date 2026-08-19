import pathlib

import pytest

from repo_infra.remote import Gh, GhError

FIX = pathlib.Path(__file__).resolve().parent / "fixtures/gh"


def fake_run(mapping):
    """A runner that answers from recorded responses and refuses anything else."""
    def run(args):
        path = args[-1]  # Last argument is the API path
        # Sort by path specificity: longer, more specific paths are checked first.
        # This ensures "/rulesets/21037721" matches before "/rulesets".
        # Match is by suffix to avoid matching repo name in other paths.
        for fragment, filename in sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True):
            if path.endswith(fragment):
                return (FIX / filename).read_text(encoding="utf-8")
        raise AssertionError("unexpected gh call: %s" % " ".join(args))
    return run


RECORDED = {
    "rulesets/21037721": "ruleset.json",
    "/rulesets": "rulesets.json",
    "/labels": "labels.json",
    "permissions/workflow": "workflow-permissions.json",
    "oposs/repo-infra": "repo.json",
}


def facts():
    return Gh(run=fake_run(RECORDED)).facts("oposs/repo-infra")


def test_reads_the_default_branch():
    assert facts().default_branch == "main"


def test_reads_the_two_required_contexts():
    assert facts().required_contexts == {"ci-passed", "changelog-updated"}


def test_reports_the_default_branch_as_protected():
    assert facts().protected is True


def test_reads_the_labels():
    assert "no-changelog" in facts().labels


def test_reads_the_workflow_permissions():
    assert facts().workflow_permissions == "write"
    assert facts().can_approve_pr is True


def test_a_failing_gh_call_raises_rather_than_returning_a_default():
    def angry(args):
        raise GhError("gh: HTTP 404")

    with pytest.raises(GhError):
        Gh(run=angry).facts("oposs/nope")
