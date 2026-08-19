# tests/test_apply_admin.py
import json
import pathlib

import pytest

from repo_infra.apply import ApplyError, apply_admin_item
from repo_infra.remote import Facts, Gh

ASSETS = pathlib.Path(__file__).resolve().parents[1] / "skills/repo-infra/assets"


class Recorder:
    """A gh runner that records every call and answers reads from a script."""

    def __init__(self, answers):
        self.calls = []
        self.answers = answers

    def __call__(self, args):
        self.calls.append(args)
        joined = " ".join(args)
        for fragment, answer in self.answers.items():
            if fragment in joined:
                return answer
        return "{}"


def facts(**overrides):
    base = dict(default_branch="main", protected=False, required_contexts=set(),
                labels=set(), workflow_permissions="read", can_approve_pr=False)
    base.update(overrides)
    return Facts(**base)


def install_required_workflows(tmp_path):
    for name in ("ci.yml", "changelog.yml"):
        target = tmp_path / ".github/workflows" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("name: x\n", encoding="utf-8")


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
    with pytest.raises(ApplyError, match="not on main yet"):
        apply_admin_item(Gh(run=Recorder({})), "o/r", "required-checks", facts(), ASSETS, tmp_path)


def test_the_ruleset_is_refused_on_a_master_branch_repository(tmp_path):
    for name in ("ci.yml", "changelog.yml"):
        target = tmp_path / ".github/workflows" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("name: x\n", encoding="utf-8")
    with pytest.raises(ApplyError, match="default branch"):
        apply_admin_item(Gh(run=Recorder({})), "o/r", "required-checks",
                         facts(default_branch="master"), ASSETS, tmp_path)


def test_the_ruleset_is_refused_on_a_master_branch_repository_even_with_workflows_present(tmp_path):
    """A non-main default branch is refused before the workflow files are even
    checked -- renaming first is the point, not a side effect of missing files."""
    with pytest.raises(ApplyError, match="default branch"):
        apply_admin_item(Gh(run=Recorder({})), "o/r", "required-checks",
                         facts(default_branch="master"), ASSETS, tmp_path)


def test_renaming_the_default_branch_is_never_automatic(tmp_path):
    with pytest.raises(ApplyError, match="by hand"):
        apply_admin_item(Gh(run=Recorder({})), "o/r", "default-branch",
                         facts(default_branch="master"), ASSETS, tmp_path)


def test_the_ruleset_is_installed_once_the_workflows_are_on_main(tmp_path):
    install_required_workflows(tmp_path)
    recorder = Recorder({"rulesets": faithful_ruleset()})
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
    install_required_workflows(tmp_path)
    stripped = json.loads(faithful_ruleset())
    stripped["rules"][0]["parameters"]["required_status_checks"] = [{"context": "ci-passed"}]
    recorder = Recorder({"rulesets": json.dumps(stripped)})
    with pytest.raises(ApplyError, match="changelog-updated"):
        apply_admin_item(Gh(run=recorder), "o/r", "required-checks", facts(), ASSETS, tmp_path)


def test_the_ruleset_creation_is_refused_when_enforcement_is_not_active(tmp_path):
    install_required_workflows(tmp_path)
    recorder = Recorder({"rulesets": faithful_ruleset(enforcement="disabled")})
    with pytest.raises(ApplyError, match="active"):
        apply_admin_item(Gh(run=recorder), "o/r", "required-checks", facts(), ASSETS, tmp_path)


def test_the_ruleset_creation_is_refused_when_it_does_not_cover_the_default_branch(tmp_path):
    install_required_workflows(tmp_path)
    recorder = Recorder({"rulesets": faithful_ruleset(
        conditions={"ref_name": {"include": ["refs/heads/some-other-branch"], "exclude": []}})})
    with pytest.raises(ApplyError, match="default branch"):
        apply_admin_item(Gh(run=recorder), "o/r", "required-checks", facts(), ASSETS, tmp_path)


def test_the_ruleset_creation_is_refused_when_it_grants_a_bypass(tmp_path):
    """A ruleset that grants a bypass is not the ruleset we shipped -- the
    payload's bypass_actors is always [], so any non-empty value here can
    only have come from the server, not from what was sent."""
    install_required_workflows(tmp_path)
    recorder = Recorder({"rulesets": faithful_ruleset(
        bypass_actors=[{"actor_type": "OrganizationAdmin", "bypass_mode": "always"}])})
    with pytest.raises(ApplyError, match="bypass"):
        apply_admin_item(Gh(run=recorder), "o/r", "required-checks", facts(), ASSETS, tmp_path)


def test_branch_protection_is_the_same_refusal_as_required_checks(tmp_path):
    """Two facts, one underlying ruleset -- both names hit the same guard."""
    with pytest.raises(ApplyError, match="not on main yet"):
        apply_admin_item(Gh(run=Recorder({})), "o/r", "branch-protection", facts(), ASSETS, tmp_path)


def test_an_unknown_admin_item_is_an_error(tmp_path):
    with pytest.raises(ApplyError, match="not an administration item"):
        apply_admin_item(Gh(run=Recorder({})), "o/r", "something-else", facts(), ASSETS, tmp_path)
