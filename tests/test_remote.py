import json
import pathlib

import pytest

from repo_infra.remote import Gh, GhError

FIX = pathlib.Path(__file__).resolve().parent / "fixtures/gh"


def fake_run(mapping):
    """A runner that answers from recorded responses and refuses anything else."""
    def run(args):
        # Extract the API path: it's after "api" and before any flags (--paginate, --slurp, etc.)
        try:
            api_index = args.index("api")
            path = args[api_index + 1]
        except (ValueError, IndexError) as e:
            raise AssertionError("unexpected gh call: %s" % " ".join(args)) from e

        # Sort by path specificity: longer, more specific paths are checked first.
        # This ensures "/rulesets/21037721" matches before "/rulesets".
        # Match is by suffix to avoid matching repo name in other paths.
        for fragment, filename in sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True):
            if path.endswith(fragment):
                # Check if this is a paginated call
                is_paginated = "--paginate" in args and "--slurp" in args
                content = (FIX / filename).read_text(encoding="utf-8")
                # If the content is already a slurped response (array of arrays), return as-is
                # Otherwise, if this is a paginated call, wrap it in a single-page array
                if is_paginated and not content.strip().startswith("[["):
                    # Wrap single-page response into array-of-arrays format
                    data = json.loads(content)
                    content = json.dumps([data])
                return content
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


def test_pagination_labels_includes_items_from_all_pages():
    """Test that paginated label responses are flattened and all labels included."""
    mapping = {
        "rulesets/21037721": "ruleset.json",
        "/rulesets": "rulesets.json",
        "/labels": "labels-paginated.json",  # Two-page slurped response
        "permissions/workflow": "workflow-permissions.json",
        "oposs/repo-infra": "repo.json",
    }
    result = Gh(run=fake_run(mapping)).facts("oposs/repo-infra")
    # Both pages should be included: first-page-label, no-changelog, second-page-label
    assert "first-page-label" in result.labels
    assert "no-changelog" in result.labels
    assert "second-page-label" in result.labels
