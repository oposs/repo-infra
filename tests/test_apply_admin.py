# tests/test_apply_admin.py
import json
import pathlib

import pytest

from repo_infra.apply import ApplyError, apply_admin_item
from repo_infra.remote import Facts, Gh, GhError

ASSETS = pathlib.Path(__file__).resolve().parents[1] / "skills/repo-infra/assets"

# `gh api repos/o/r/rulesets` -- the listing apply reads to find out whether
# a ruleset of this name already exists. The write call cannot match this
# fragment, because `--method POST`/`--method PUT` sits between `api` and
# the path, so scripting it first keeps the two calls apart.
LIST = "api repos/o/r/rulesets"


class Recorder:
    """A gh runner that records every call and answers reads from a script.

    An answer that is an exception is raised instead of returned, so a test
    can script a failed `gh` call -- a 404, or anything else -- the same way
    `Gh.run` actually fails (module docstring: `GhError` on a non-zero exit).
    """

    def __init__(self, answers):
        self.calls = []
        self.answers = answers

    def __call__(self, args):
        self.calls.append(args)
        joined = " ".join(args)
        for fragment, answer in self.answers.items():
            if fragment in joined:
                if isinstance(answer, BaseException):
                    raise answer
                return answer
        return "{}"


def facts(**overrides):
    base = dict(default_branch="main", protected=False, required_contexts=set(),
                labels=set(), workflow_permissions="read", can_approve_pr=False)
    base.update(overrides)
    return Facts(**base)


def install_required_workflows(tmp_path):
    """Writes the workflows to the local checkout only -- never to GitHub.

    Used by the one test that exists to prove local presence is not
    evidence of anything: the ruleset precondition must ask GitHub about the
    default branch, not this directory, even though this is exactly what the
    old, local-only check used to accept.
    """
    for name in ("ci.yml", "changelog.yml"):
        target = tmp_path / ".github/workflows" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("name: x\n", encoding="utf-8")


def not_found(*paths):
    """Recorder answers that make `Gh.path_exists_on_branch` return False --
    a confirmed, clean 404 -- for each of these repo-relative paths. Text
    matches what `gh api` actually prints on a 404 (verified live against
    `gh api repos/oposs/repo-infra/contents/does-not-exist.yml?ref=main`):
    `gh: Not Found (HTTP 404)` on stderr, non-zero exit.
    """
    return {f"contents/{path}": GhError(f"gh api repos/o/r/contents/{path}?ref=main "
                                        "failed: gh: Not Found (HTTP 404)")
            for path in paths}


def unverifiable(*paths):
    """Recorder answers that make `Gh.path_exists_on_branch` return None --
    the call failed, but not with a 404, so it must not be read as a
    confirmed absence (nor as a confirmed presence)."""
    return {f"contents/{path}": GhError(f"gh api repos/o/r/contents/{path}?ref=main "
                                        "failed: gh: connection reset by peer")
            for path in paths}


def faithful_ruleset(**overrides):
    """What a server that applied the shipped payload without alteration
    would read back. Individual tests corrupt one field to prove the
    assertion in apply_admin_item actually inspects the response."""
    ruleset = {
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": [{"type": "required_status_checks", "parameters": {
            "required_status_checks": [{"context": "ci-passed"},
                                       {"context": "changelog-updated"}]}}],
    }
    ruleset.update(overrides)
    return json.dumps(ruleset)


def test_the_label_is_created_and_read_back(tmp_path):
    recorder = Recorder({"/labels": json.dumps([{"name": "no-changelog"}])})
    apply_admin_item(Gh(run=recorder), "o/r", "no-changelog-label", facts(), ASSETS, tmp_path)
    assert any("POST" in " ".join(c) and "/labels" in " ".join(c) for c in recorder.calls)
    assert any("gh api repos/o/r/labels" == " ".join(c) for c in recorder.calls)


def test_a_label_that_does_not_appear_on_read_back_is_an_error(tmp_path):
    recorder = Recorder({"/labels": json.dumps([])})
    with pytest.raises(ApplyError, match="read back"):
        apply_admin_item(Gh(run=recorder), "o/r", "no-changelog-label", facts(), ASSETS, tmp_path)


def test_workflow_permissions_are_written_and_read_back(tmp_path):
    recorder = Recorder({"/actions/permissions/workflow": json.dumps(
        {"default_workflow_permissions": "write", "can_approve_pull_request_reviews": True})})
    apply_admin_item(Gh(run=recorder), "o/r", "actions-open-pr", facts(), ASSETS, tmp_path)
    assert any("PUT" in " ".join(c) for c in recorder.calls)


def test_workflow_permissions_that_do_not_stick_are_an_error(tmp_path):
    recorder = Recorder({"/actions/permissions/workflow": json.dumps(
        {"default_workflow_permissions": "read", "can_approve_pull_request_reviews": False})})
    with pytest.raises(ApplyError, match="read back"):
        apply_admin_item(Gh(run=recorder), "o/r", "actions-open-pr", facts(), ASSETS, tmp_path)


def test_the_ruleset_is_refused_while_the_workflows_are_not_on_the_default_branch(tmp_path):
    """Asserts the interpolated `missing` list actually appears, not just the
    static prose around it -- the class of bug an f-string typo produces is
    invisible to a match on words that never needed interpolating."""
    recorder = Recorder(not_found(".github/workflows/ci.yml", ".github/workflows/changelog.yml"))
    with pytest.raises(ApplyError, match="not on main yet") as raised:
        apply_admin_item(Gh(run=recorder), "o/r", "required-checks", facts(), ASSETS, tmp_path)
    assert ".github/workflows/ci.yml" in str(raised.value)
    assert ".github/workflows/changelog.yml" in str(raised.value)


def test_the_ruleset_refuses_when_a_workflow_is_present_locally_but_not_on_the_branch(tmp_path):
    """The case the old, local-only check got backwards. `ci.yml` is right
    here on disk -- committed to an unpushed `repo-infra/apply` branch, say
    -- but GitHub confirms it is not on the default branch. The precondition
    must refuse anyway, and name the one that is actually missing."""
    install_required_workflows(tmp_path)
    recorder = Recorder(not_found(".github/workflows/ci.yml"))
    with pytest.raises(ApplyError, match=r"\.github/workflows/ci\.yml") as raised:
        apply_admin_item(Gh(run=recorder), "o/r", "required-checks", facts(), ASSETS, tmp_path)
    assert "changelog.yml" not in str(raised.value)


def test_the_ruleset_refuses_with_a_distinct_message_when_the_check_itself_fails(tmp_path):
    """A non-404 failure is not evidence of anything -- it must refuse, but
    say so differently than a confirmed absence, so an operator does not
    read "not on main yet" and start hunting for a workflow that may well be
    there.

    Asserts the actual repository name is interpolated into the endpoint it
    names, not the literal text "{repo}" -- a missing `f` prefix on that line
    is valid Python (a plain string containing braces), so it produces this
    exact wrong message and nothing else catches it: not ruff, not a test
    that only matches the static prose around the bug.
    """
    recorder = Recorder(unverifiable(".github/workflows/ci.yml"))
    with pytest.raises(ApplyError, match="could not confirm") as raised:
        apply_admin_item(Gh(run=recorder), "o/r", "required-checks", facts(), ASSETS, tmp_path)
    assert "not on main yet" not in str(raised.value)
    assert "repos/o/r/contents" in str(raised.value)
    assert "repos/{repo}/contents" not in str(raised.value)


def test_the_ruleset_is_refused_on_a_master_branch_repository(tmp_path):
    with pytest.raises(ApplyError, match="default branch") as raised:
        apply_admin_item(Gh(run=Recorder({})), "o/r", "required-checks",
                         facts(default_branch="master"), ASSETS, tmp_path)
    assert "'master'" in str(raised.value)


def test_the_ruleset_is_refused_on_a_master_branch_repository_even_with_workflows_present(tmp_path):
    """A non-main default branch is refused before the workflow files are even
    checked -- renaming first is the point, not a side effect of missing files."""
    with pytest.raises(ApplyError, match="default branch") as raised:
        apply_admin_item(Gh(run=Recorder({})), "o/r", "required-checks",
                         facts(default_branch="master"), ASSETS, tmp_path)
    assert "'master'" in str(raised.value)


def test_renaming_the_default_branch_is_never_automatic(tmp_path):
    with pytest.raises(ApplyError, match="by hand"):
        apply_admin_item(Gh(run=Recorder({})), "o/r", "default-branch",
                         facts(default_branch="master"), ASSETS, tmp_path)


def test_the_ruleset_is_installed_once_the_workflows_are_confirmed_on_the_branch(tmp_path):
    """No answer scripted for the `contents/...` calls -- Recorder's default
    is success, so both workflows read as confirmed present on GitHub, with
    nothing installed in `tmp_path` at all. That absence of local files is
    the point: this precondition no longer cares what is on disk."""
    recorder = Recorder({LIST: "[]", "rulesets": faithful_ruleset()})
    apply_admin_item(Gh(run=recorder), "o/r", "required-checks", facts(), ASSETS, tmp_path)
    calls = [" ".join(c) for c in recorder.calls]
    assert any("POST" in c and "repos/o/r/rulesets" in c and "--input" in c for c in calls)
    # The payload is staged under the repository's own scratch dir, not typed
    # onto the command line -- `gh api --input` takes a path, not a string.
    input_path = next(c[c.index("--input") + 1] for c in recorder.calls if "--input" in c)
    staged = json.loads(pathlib.Path(input_path).read_text(encoding="utf-8"))
    expected = json.loads((ASSETS / "gh/ruleset-main.json").read_text(encoding="utf-8"))
    assert staged == expected
    assert pathlib.Path(input_path).is_relative_to(tmp_path / ".git")


def test_the_ruleset_creation_is_refused_when_the_server_drops_a_required_context(tmp_path):
    """A POST replaces the whole object -- if the server rejects or alters part
    of the payload, `apply` must not report success over a ruleset that does
    not actually require both checks."""
    stripped = json.loads(faithful_ruleset())
    stripped["rules"][0]["parameters"]["required_status_checks"] = [{"context": "ci-passed"}]
    recorder = Recorder({LIST: "[]", "rulesets": json.dumps(stripped)})
    with pytest.raises(ApplyError, match="changelog-updated"):
        apply_admin_item(Gh(run=recorder), "o/r", "required-checks", facts(), ASSETS, tmp_path)


def test_the_ruleset_creation_is_refused_when_enforcement_is_not_active(tmp_path):
    recorder = Recorder({LIST: "[]", "rulesets": faithful_ruleset(enforcement="disabled")})
    with pytest.raises(ApplyError, match="active"):
        apply_admin_item(Gh(run=recorder), "o/r", "required-checks", facts(), ASSETS, tmp_path)


def test_the_ruleset_creation_is_refused_when_it_does_not_cover_the_default_branch(tmp_path):
    recorder = Recorder({LIST: "[]", "rulesets": faithful_ruleset(
        conditions={"ref_name": {"include": ["refs/heads/some-other-branch"], "exclude": []}})})
    with pytest.raises(ApplyError, match="default branch"):
        apply_admin_item(Gh(run=recorder), "o/r", "required-checks", facts(), ASSETS, tmp_path)


def test_the_ruleset_creation_is_refused_when_it_grants_a_bypass(tmp_path):
    """A ruleset that grants a bypass is not the ruleset we shipped -- the
    payload's bypass_actors is always [], so any non-empty value here can
    only have come from the server, not from what was sent."""
    recorder = Recorder({LIST: "[]", "rulesets": faithful_ruleset(
        bypass_actors=[{"actor_type": "OrganizationAdmin", "bypass_mode": "always"}])})
    with pytest.raises(ApplyError, match="bypass"):
        apply_admin_item(Gh(run=recorder), "o/r", "required-checks", facts(), ASSETS, tmp_path)


def test_branch_protection_is_the_same_refusal_as_required_checks(tmp_path):
    """Two facts, one underlying ruleset -- both names hit the same guard."""
    recorder = Recorder(not_found(".github/workflows/ci.yml", ".github/workflows/changelog.yml"))
    with pytest.raises(ApplyError, match="not on main yet"):
        apply_admin_item(Gh(run=recorder), "o/r", "branch-protection", facts(), ASSETS, tmp_path)


def test_an_unknown_admin_item_is_an_error(tmp_path):
    with pytest.raises(ApplyError, match="not an administration item"):
        apply_admin_item(Gh(run=Recorder({})), "o/r", "something-else", facts(), ASSETS, tmp_path)


# --- adopting a ruleset that is already there ----------------------------

EXISTING = json.dumps([{"id": 4242, "name": "main", "source_type": "Repository"}])


def test_an_existing_ruleset_of_the_same_name_is_updated_not_recreated(tmp_path):
    """POST creates; it cannot adopt. GitHub answers a second ruleset with a
    name already taken with 422, so `oposs/mkp-builder` -- protected before it
    was converted, like most repositories -- could not be given required checks
    at all. `branch-protection` reading `ok` is the same ruleset saying so."""
    recorder = Recorder({LIST: EXISTING, "rulesets": faithful_ruleset()})
    apply_admin_item(Gh(run=recorder), "o/r", "required-checks", facts(), ASSETS, tmp_path)
    calls = [" ".join(c) for c in recorder.calls]
    assert any("PUT" in c and "repos/o/r/rulesets/4242" in c and "--input" in c for c in calls)
    assert not any("POST" in c and "rulesets" in c for c in calls)


def test_an_organisation_ruleset_of_the_same_name_is_not_adopted(tmp_path):
    """An organisation ruleset cannot be written through the repository
    endpoint, and its name does not collide with a repository one -- so it is
    not a reason to skip the POST."""
    org = json.dumps([{"id": 99, "name": "main", "source_type": "Organization"}])
    recorder = Recorder({LIST: org, "rulesets": faithful_ruleset()})
    apply_admin_item(Gh(run=recorder), "o/r", "required-checks", facts(), ASSETS, tmp_path)
    calls = [" ".join(c) for c in recorder.calls]
    assert any("POST" in c and "repos/o/r/rulesets" in c for c in calls)


def test_a_ruleset_with_another_name_is_left_alone(tmp_path):
    other = json.dumps([{"id": 7, "name": "release-tags", "source_type": "Repository"}])
    recorder = Recorder({LIST: other, "rulesets": faithful_ruleset()})
    apply_admin_item(Gh(run=recorder), "o/r", "required-checks", facts(), ASSETS, tmp_path)
    calls = [" ".join(c) for c in recorder.calls]
    assert any("POST" in c and "repos/o/r/rulesets" in c for c in calls)
    assert not any("rulesets/7" in c for c in calls)


def test_an_updated_ruleset_is_still_read_back_and_checked(tmp_path):
    """The PUT path must keep every guard the POST path has -- a write that
    reports success is not evidence the branch is guarded."""
    stripped = json.loads(faithful_ruleset())
    stripped["rules"] = [r for r in stripped["rules"] if r["type"] != "required_status_checks"]
    recorder = Recorder({LIST: EXISTING, "rulesets": json.dumps(stripped)})
    with pytest.raises(ApplyError):
        apply_admin_item(Gh(run=recorder), "o/r", "required-checks", facts(), ASSETS, tmp_path)
