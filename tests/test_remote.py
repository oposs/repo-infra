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
                if isinstance(filename, BaseException):
                    raise filename
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


# What `gh api repos/<repo>/branches/main/protection` raises on a branch
# without classic protection: GitHub answers 404 "Branch not protected".
NOT_PROTECTED = GhError("gh api repos/oposs/repo-infra/branches/main/protection failed: "
                        "gh: Branch not protected (HTTP 404)")


RECORDED = {
    "rulesets/21037721": "ruleset.json",
    "/rulesets": "rulesets.json",
    "/labels": "labels.json",
    "permissions/workflow": "workflow-permissions.json",
    "/pulls?state=open": "pulls-open.json",
    "oposs/repo-infra": "repo.json",
    "branches/main/protection": NOT_PROTECTED,
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


def test_reads_whether_merged_branches_are_deleted():
    # The recording is of oposs/repo-infra with the setting off.
    assert facts().delete_branch_on_merge is False


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
    "/pulls?state=open": "pulls-open.json",
        "oposs/repo-infra": "repo.json",
        "branches/main/protection": NOT_PROTECTED,
    }
    result = Gh(run=fake_run(mapping)).facts("oposs/repo-infra")
    # Both pages should be included: first-page-label, no-changelog, second-page-label
    assert "first-page-label" in result.labels
    assert "no-changelog" in result.labels
    assert "second-page-label" in result.labels


def test_ruleset_with_all_scope_protects_default_branch():
    """Test that rulesets with ~ALL scope are recognized as protecting the default branch."""
    mapping = {
        "rulesets/21037721": "ruleset-all-scope.json",
        "/rulesets": "rulesets.json",
        "/labels": "labels.json",
        "permissions/workflow": "workflow-permissions.json",
    "/pulls?state=open": "pulls-open.json",
        "oposs/repo-infra": "repo.json",
        "branches/main/protection": NOT_PROTECTED,
    }
    result = Gh(run=fake_run(mapping)).facts("oposs/repo-infra")
    assert result.protected is True


def test_ruleset_with_explicit_branch_protects_default_branch():
    """Test that rulesets with refs/heads/<branch> are recognized as protecting the default."""
    mapping = {
        "rulesets/21037721": "ruleset-explicit-branch.json",
        "/rulesets": "rulesets.json",
        "/labels": "labels.json",
        "permissions/workflow": "workflow-permissions.json",
    "/pulls?state=open": "pulls-open.json",
        "oposs/repo-infra": "repo.json",
        "branches/main/protection": NOT_PROTECTED,
    }
    result = Gh(run=fake_run(mapping)).facts("oposs/repo-infra")
    assert result.protected is True


def test_current_repo_reads_the_checkout_gh_is_run_from():
    calls = []

    def run(args):
        calls.append(args)
        return "oposs/repo-infra\n"

    assert Gh(run=run).current_repo() == "oposs/repo-infra"
    assert calls == [["gh", "repo", "view", "--json", "nameWithOwner",
                      "-q", ".nameWithOwner"]]


def test_reads_the_up_to_date_rule():
    assert facts().strict is False  # the recorded ruleset predates D28


def test_reads_the_up_to_date_rule_when_it_is_on():
    recorded = fake_run(RECORDED)

    def run(args):
        text = recorded(args)
        if args[2].endswith("rulesets/21037721"):
            text = text.replace('"strict_required_status_checks_policy":false',
                                '"strict_required_status_checks_policy":true')
            assert "policy\":true" in text
        return text
    assert Gh(run=run).facts("oposs/repo-infra").strict is True


def test_reads_the_open_release_pull_requests_of_the_bot_only():
    assert facts().release_prs == ((12, "release/v0.3.0"),)


def tag_run(missing="v9.9.9", status="404"):
    """The recorded fakes, plus one tag GitHub answers with an error."""
    recorded = fake_run({**RECORDED, "git/ref/tags/v0.2.0": "tag-ref.json"})

    def run(args):
        if any(a.endswith(f"git/ref/tags/{missing}") for a in args):
            raise GhError(f"{' '.join(args)} failed: gh: Not Found (HTTP {status})")
        return recorded(args)
    return run


def test_looks_up_one_tag_instead_of_listing_them_all():
    calls = []
    run = tag_run()

    def counting(args):
        calls.append(args)
        return run(args)

    tags = Gh(run=counting).facts("oposs/repo-infra").tags
    assert "v0.2.0" in tags and "v9.9.9" not in tags
    assert "v0.2.0" in tags  # asked once, answered from memory
    assert [c for c in calls if any("tags" in a for a in c)] == [
        ["gh", "api", "repos/oposs/repo-infra/git/ref/tags/v0.2.0"],
        ["gh", "api", "repos/oposs/repo-infra/git/ref/tags/v9.9.9"]]


def test_a_tag_lookup_that_fails_otherwise_is_an_error():
    tags = Gh(run=tag_run(status="502")).facts("oposs/repo-infra").tags
    with pytest.raises(GhError, match="502"):
        assert "v9.9.9" not in tags


def test_a_branch_without_classic_protection_reads_as_none():
    assert facts().classic_protection is False
    assert facts().classic_contexts == ()


def test_reads_classic_protection_and_its_required_contexts():
    """oetiker/tvision-rs#29 stayed blocked with every check green: classic
    protection on main required `test`, and check read only the rulesets."""
    result = Gh(run=fake_run({**RECORDED, "branches/main/protection":
                              "classic-protection.json"})).facts("oposs/repo-infra")
    assert result.classic_protection is True
    assert result.classic_contexts == ("test",)


def test_classic_protection_that_cannot_be_read_is_an_error():
    """Only a 404 means no classic protection. A 403 says nothing about the
    branch, and reading it as unprotected would hide the rule that blocks."""
    denied = GhError("gh api repos/oposs/repo-infra/branches/main/protection failed: "
                     "gh: Resource not accessible by integration (HTTP 403)")
    with pytest.raises(GhError, match="403"):
        Gh(run=fake_run({**RECORDED, "branches/main/protection": denied})).facts(
            "oposs/repo-infra")
