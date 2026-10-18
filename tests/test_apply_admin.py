# tests/test_apply_admin.py
import json
import pathlib
import subprocess

import pytest

from repo_infra import check
from repo_infra.apply import BRANCH, ApplyError, apply_admin_item
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
    An answer that is a list is handed out one entry per call, and its last
    entry repeats, so a test can script a read-back that is stale at first.
    """

    def __init__(self, answers):
        self.calls = []
        self.answers = answers

    def __call__(self, args):
        self.calls.append(args)
        joined = " ".join(args)
        for fragment, answer in self.answers.items():
            if fragment in joined:
                if isinstance(answer, list):
                    answer = answer.pop(0) if len(answer) > 1 else answer[0]
                if isinstance(answer, BaseException):
                    raise answer
                return answer
        return "{}"


@pytest.fixture(autouse=True)
def sleeps(monkeypatch):
    """The read-back poll waits between reads. The tests record the waits
    instead of sleeping through them."""
    waited = []
    monkeypatch.setattr("repo_infra.apply._sleep", waited.append)
    return waited


def facts(**overrides):
    base = dict(default_branch="main", protected=False, required_contexts=set(),
                labels=set(), workflow_permissions="read", can_approve_pr=False,
                delete_branch_on_merge=False)
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
            "strict_required_status_checks_policy": True,
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


WORKFLOW = "api repos/o/r/actions/permissions/workflow"
STALE = json.dumps({"default_workflow_permissions": "read",
                    "can_approve_pull_request_reviews": False})
WRITTEN = json.dumps({"default_workflow_permissions": "write",
                      "can_approve_pull_request_reviews": True})


def reads_of(recorder, path):
    return [c for c in recorder.calls if c == ["gh", "api", path]]


def test_workflow_permissions_that_read_back_stale_at_first_are_accepted(tmp_path, sleeps):
    # oetiker/tvision-rs, plugin 2.3.1: the first read after the PUT still said
    # read/False, and a minute later GitHub said write/True.
    recorder = Recorder({WORKFLOW: [STALE, STALE, WRITTEN]})
    message = apply_admin_item(Gh(run=recorder), "o/r", "actions-open-pr", facts(), ASSETS,
                               tmp_path)
    assert message == "allowed Actions to create and approve pull requests"
    assert len(reads_of(recorder, "repos/o/r/actions/permissions/workflow")) == 3
    assert len(sleeps) == 2


def test_workflow_permissions_are_read_back_five_times_before_refusing(tmp_path, sleeps):
    recorder = Recorder({WORKFLOW: STALE,
                         "api repos/o/r": json.dumps({"owner": {"type": "User"}})})
    with pytest.raises(ApplyError):
        apply_admin_item(Gh(run=recorder), "o/r", "actions-open-pr", facts(), ASSETS, tmp_path)
    assert len(reads_of(recorder, "repos/o/r/actions/permissions/workflow")) == 5
    assert len(sleeps) == 4


def test_a_user_owned_repository_is_not_told_about_an_organisation_policy(tmp_path):
    recorder = Recorder({WORKFLOW: STALE,
                         "api repos/o/r": json.dumps({"owner": {"type": "User"}})})
    with pytest.raises(ApplyError) as refused:
        apply_admin_item(Gh(run=recorder), "o/r", "actions-open-pr", facts(), ASSETS, tmp_path)
    assert "organisation" not in str(refused.value)
    assert "re-run" in str(refused.value)


def test_an_organisation_owned_repository_is_pointed_at_the_organisation_policy(tmp_path):
    recorder = Recorder({WORKFLOW: STALE,
                         "api repos/o/r": json.dumps({"owner": {"type": "Organization"}})})
    with pytest.raises(ApplyError, match="organisation policy"):
        apply_admin_item(Gh(run=recorder), "o/r", "actions-open-pr", facts(), ASSETS, tmp_path)


def test_a_failed_owner_lookup_still_refuses_with_the_read_back(tmp_path):
    recorder = Recorder({WORKFLOW: STALE, "api repos/o/r": GhError("gh: HTTP 502")})
    with pytest.raises(ApplyError, match="read back"):
        apply_admin_item(Gh(run=recorder), "o/r", "actions-open-pr", facts(), ASSETS, tmp_path)


def test_deleting_merged_branches_that_reads_back_stale_at_first_is_accepted(tmp_path,
                                                                              sleeps):
    recorder = Recorder({"api repos/o/r": [json.dumps({"delete_branch_on_merge": False}),
                                           json.dumps({"delete_branch_on_merge": True})]})
    apply_admin_item(Gh(run=recorder), "o/r", "delete-merged-branches", facts(), ASSETS,
                     tmp_path)
    assert len(reads_of(recorder, "repos/o/r")) == 2
    assert len(sleeps) == 1


def test_deleting_merged_branches_is_read_back_five_times_before_refusing(tmp_path, sleeps):
    recorder = Recorder({"api repos/o/r": json.dumps({"delete_branch_on_merge": False})})
    with pytest.raises(ApplyError):
        apply_admin_item(Gh(run=recorder), "o/r", "delete-merged-branches", facts(), ASSETS,
                         tmp_path)
    assert len(reads_of(recorder, "repos/o/r")) == 5
    assert len(sleeps) == 4


def test_a_label_that_reads_back_missing_at_first_is_accepted(tmp_path, sleeps):
    # "api repos/o/r/labels" rather than "/labels": the POST that creates the
    # label must not take the first, stale answer.
    recorder = Recorder({"api repos/o/r/labels": [json.dumps([]),
                                                  json.dumps([{"name": "no-changelog"}])]})
    apply_admin_item(Gh(run=recorder), "o/r", "no-changelog-label", facts(), ASSETS, tmp_path)
    assert len(reads_of(recorder, "repos/o/r/labels")) == 2
    assert len(sleeps) == 1


def test_a_written_setting_that_reads_back_at_once_does_not_wait(tmp_path, sleeps):
    recorder = Recorder({WORKFLOW: WRITTEN})
    apply_admin_item(Gh(run=recorder), "o/r", "actions-open-pr", facts(), ASSETS, tmp_path)
    assert sleeps == []


def test_deleting_merged_branches_is_switched_on_and_read_back(tmp_path):
    recorder = Recorder({"api repos/o/r": json.dumps({"delete_branch_on_merge": True})})
    apply_admin_item(Gh(run=recorder), "o/r", "delete-merged-branches", facts(), ASSETS,
                     tmp_path)
    assert ["gh", "api", "--method", "PATCH", "repos/o/r",
            "-F", "delete_branch_on_merge=true"] in recorder.calls
    assert ["gh", "api", "repos/o/r"] in recorder.calls


def test_deleting_merged_branches_that_does_not_stick_is_an_error(tmp_path):
    recorder = Recorder({"api repos/o/r": json.dumps({"delete_branch_on_merge": False})})
    with pytest.raises(ApplyError, match="read back"):
        apply_admin_item(Gh(run=recorder), "o/r", "delete-merged-branches", facts(), ASSETS,
                         tmp_path)


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


def test_the_ruleset_payload_is_staged_in_a_worktree_too(tmp_path):
    """In a linked worktree `.git` is a file naming the real git dir; staging
    under `<root>/.git/...` failed there with NotADirectoryError (found
    converting mdmost from a worktree)."""
    def git(*args, cwd):
        subprocess.run(("git",) + args, cwd=cwd, check=True, capture_output=True)
    main = tmp_path / "main"
    main.mkdir()
    git("init", "-q", cwd=main)
    git("-c", "user.email=t@example.com", "-c", "user.name=T",
        "commit", "-q", "--allow-empty", "-m", "init", cwd=main)
    tree = tmp_path / "tree"
    git("worktree", "add", "-q", str(tree), cwd=main)
    assert (tree / ".git").is_file()
    recorder = Recorder({LIST: "[]", "rulesets": faithful_ruleset()})
    apply_admin_item(Gh(run=recorder), "o/r", "required-checks", facts(), ASSETS, tree)
    input_path = next(c[c.index("--input") + 1] for c in recorder.calls if "--input" in c)
    assert pathlib.Path(input_path).is_relative_to(main / ".git/worktrees")


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


def test_the_shipped_ruleset_requires_up_to_date_branches():
    payload = json.loads((ASSETS / "gh/ruleset-main.json").read_text(encoding="utf-8"))
    rule = next(r for r in payload["rules"] if r["type"] == "required_status_checks")
    assert rule["parameters"]["strict_required_status_checks_policy"] is True


def test_a_ruleset_that_reads_back_without_the_up_to_date_rule_is_refused(tmp_path):
    lax = json.loads(faithful_ruleset())
    lax["rules"][0]["parameters"]["strict_required_status_checks_policy"] = False
    recorder = Recorder({LIST: EXISTING, "rulesets": json.dumps(lax)})
    with pytest.raises(ApplyError, match="strict_required_status_checks_policy"):
        apply_admin_item(Gh(run=recorder), "o/r", "required-checks", facts(), ASSETS, tmp_path)


# --- classic branch protection (#91) -------------------------------------
#
# oetiker/tvision-rs#29, the onboarding pull request, stayed BLOCKED with
# every check green: classic protection on main required `test`, a job the
# onboarding had replaced.

DELETE = "--method DELETE repos/o/r/branches/main/protection"
PROTECTION = "api repos/o/r/branches/main/protection"
NOT_PROTECTED = GhError("gh api repos/o/r/branches/main/protection failed: "
                        "gh: Branch not protected (HTTP 404)")


def classic(**overrides):
    """A repository with classic protection on main and the standard ruleset."""
    base = dict(protected=True, required_contexts={"ci-passed", "changelog-updated"},
                strict=True, classic_protection=True, classic_contexts=("test",))
    base.update(overrides)
    return facts(**base)


def test_classic_protection_is_deleted_and_read_back_as_gone(tmp_path):
    recorder = Recorder({DELETE: "", PROTECTION: NOT_PROTECTED})
    apply_admin_item(Gh(run=recorder), "o/r", "classic-protection", classic(), ASSETS, tmp_path)
    assert ["gh", "api", "--method", "DELETE",
            "repos/o/r/branches/main/protection"] in recorder.calls
    assert ["gh", "api", "repos/o/r/branches/main/protection"] in recorder.calls


def test_classic_protection_that_is_still_there_after_the_delete_is_an_error(tmp_path):
    recorder = Recorder({DELETE: "", PROTECTION: json.dumps({"url": "x"})})
    with pytest.raises(ApplyError, match="read back"):
        apply_admin_item(Gh(run=recorder), "o/r", "classic-protection", classic(), ASSETS,
                         tmp_path)


def test_a_read_back_that_fails_otherwise_is_an_error(tmp_path):
    recorder = Recorder({DELETE: "", PROTECTION: GhError("gh: HTTP 502")})
    with pytest.raises(ApplyError, match="could not confirm"):
        apply_admin_item(Gh(run=recorder), "o/r", "classic-protection", classic(), ASSETS,
                         tmp_path)


@pytest.mark.parametrize("ruleset", [
    dict(protected=False, required_contexts=set()),
    dict(required_contexts={"ci-passed"}),
])
def test_classic_protection_is_kept_until_the_ruleset_requires_both_checks(tmp_path,
                                                                           ruleset):
    """Removing it first would leave main without any protection."""
    recorder = Recorder({})
    with pytest.raises(ApplyError, match="changelog-updated"):
        apply_admin_item(Gh(run=recorder), "o/r", "classic-protection", classic(**ruleset),
                         ASSETS, tmp_path)
    assert not any("DELETE" in c for c in recorder.calls)


def test_no_classic_protection_is_nothing_to_delete(tmp_path):
    recorder = Recorder({})
    said = apply_admin_item(Gh(run=recorder), "o/r", "classic-protection",
                            classic(classic_protection=False, classic_contexts=()),
                            ASSETS, tmp_path)
    assert "no classic branch protection" in said
    assert recorder.calls == []


def workflows_on(main=(), apply_branch=()):
    """`contents/` answers: each required workflow present on the refs named."""
    answers = {}
    for name in ("ci.yml", "changelog.yml"):
        path = f".github/workflows/{name}"
        for ref, present in (("main", name in main), (BRANCH, name in apply_branch)):
            if not present:
                answers[f"contents/{path}?ref={ref}"] = GhError(
                    f"gh api repos/o/r/contents/{path}?ref={ref} failed: "
                    "gh: Not Found (HTTP 404)")
    return answers


BOTH = ("ci.yml", "changelog.yml")


def test_with_classic_protection_the_ruleset_takes_the_workflows_on_the_apply_branch(tmp_path):
    """The onboarding pull request cannot merge while classic protection waits
    for a check nobody produces, and classic protection is not removed before
    the ruleset exists. The pushed repo-infra/apply branch is that pull
    request's head, which produces ci-passed and changelog-updated."""
    recorder = Recorder({**workflows_on(apply_branch=BOTH), LIST: "[]",
                         "rulesets": faithful_ruleset()})
    apply_admin_item(Gh(run=recorder), "o/r", "required-checks",
                     facts(classic_protection=True, classic_contexts=("test",)),
                     ASSETS, tmp_path)
    assert any("POST" in " ".join(c) for c in recorder.calls)


def test_with_classic_protection_the_ruleset_refusal_says_to_push_the_branch(tmp_path):
    recorder = Recorder(workflows_on())
    with pytest.raises(ApplyError, match=f"push {BRANCH}") as raised:
        apply_admin_item(Gh(run=recorder), "o/r", "required-checks",
                         facts(classic_protection=True, classic_contexts=("test",)),
                         ASSETS, tmp_path)
    assert ".github/workflows/ci.yml" in str(raised.value)


def test_without_classic_protection_the_apply_branch_does_not_count(tmp_path):
    recorder = Recorder(workflows_on(apply_branch=BOTH))
    with pytest.raises(ApplyError, match="not on main yet"):
        apply_admin_item(Gh(run=recorder), "o/r", "required-checks", facts(), ASSETS,
                         tmp_path)
    assert not any(f"ref={BRANCH}" in " ".join(c) for c in recorder.calls)


class GitHub:
    """A gh that keeps the rulesets and the classic protection it is asked
    to write, so facts, check and apply can run in sequence."""

    def __init__(self, classic_contexts, files):
        self.rulesets = {}
        checks = [{"context": c, "app_id": 15368} for c in classic_contexts]
        self.classic = {"required_status_checks": {
            "strict": True, "contexts": list(classic_contexts), "checks": checks}}
        self.files = files

    def __call__(self, args):
        method = args[args.index("--method") + 1] if "--method" in args else "GET"
        path = next(a for a in args if a.startswith("repos/"))

        def answer(data):
            return json.dumps([data] if "--paginate" in args else data)

        def not_found():
            raise GhError(f"gh api {path} failed: gh: Not Found (HTTP 404)")

        if method == "DELETE" and path == "repos/o/r/branches/main/protection":
            self.classic = None
            return ""
        if method == "POST" and path == "repos/o/r/rulesets":
            ruleset = json.loads(pathlib.Path(args[args.index("--input") + 1]).read_text())
            self.rulesets[len(self.rulesets) + 1] = ruleset
            return json.dumps(ruleset)
        assert method == "GET", args
        if path == "repos/o/r":
            return answer({"default_branch": "main", "delete_branch_on_merge": True})
        if path == "repos/o/r/rulesets":
            return answer([{"id": i, "name": r["name"], "source_type": "Repository"}
                           for i, r in self.rulesets.items()])
        if path.startswith("repos/o/r/rulesets/"):
            return answer(self.rulesets[int(path.rsplit("/", 1)[1])])
        if path == "repos/o/r/labels":
            return answer([{"name": "no-changelog"}])
        if path == "repos/o/r/actions/permissions/workflow":
            return answer({"default_workflow_permissions": "write",
                           "can_approve_pull_request_reviews": True})
        if path == "repos/o/r/pulls?state=open":
            return answer([])
        if path == "repos/o/r/branches/main/protection":
            return answer(self.classic) if self.classic else not_found()
        if path.startswith("repos/o/r/contents/"):
            file, ref = path.removeprefix("repos/o/r/contents/").split("?ref=")
            return "{}" if file in self.files.get(ref, ()) else not_found()
        raise AssertionError(f"unexpected gh call: {' '.join(args)}")


def test_an_onboarding_blocked_by_classic_protection_gets_unblocked(tmp_path):
    """tvision-rs#29 end to end: classic protection requires `test`, the
    workflows are only on the pushed repo-infra/apply branch. required-checks
    and then classic-protection both go through, and check is clean after."""
    gh = Gh(run=GitHub(("test",), {BRANCH: {".github/workflows/ci.yml",
                                            ".github/workflows/changelog.yml"}}))
    before = {i.name: i for i in check.classify_remote(gh.facts("o/r"))}
    assert before["classic-protection"].state == "conflict"
    assert "`test`" in before["classic-protection"].detail
    apply_admin_item(gh, "o/r", "required-checks", gh.facts("o/r"), ASSETS, tmp_path)
    apply_admin_item(gh, "o/r", "classic-protection", gh.facts("o/r"), ASSETS, tmp_path)
    after = gh.facts("o/r")
    assert after.classic_protection is False
    assert {i.state for i in check.classify_remote(after)} == {"ok"}
