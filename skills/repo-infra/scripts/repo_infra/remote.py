"""Everything the checker reads from GitHub.

One class, one injectable runner. `remote.py` never touches the file system and
`assemble.py` never touches the network, which is what lets every rule in this
plugin be tested without a GitHub account.
"""

import json
import subprocess
import urllib.parse
from collections import namedtuple

Facts = namedtuple(
    "Facts",
    "default_branch protected required_contexts labels workflow_permissions can_approve_pr "
    "delete_branch_on_merge strict release_prs tags classic_protection classic_contexts "
    "protection_unavailable",
    defaults=(False, (), None, False, (), None))


def _quote(name):
    """A branch name as one path segment or query value. Git allows `#`, `?`
    and `%` in one, and GitHub reads `feat%2Fx` as the branch `feat/x`."""
    return urllib.parse.quote(name, safe="")


class GhError(Exception):
    """A `gh` invocation failed. Never swallowed, never defaulted."""


def plan_refuses_protection(error):
    """True when GitHub refused a protection endpoint because the repository's
    plan has no branch protection: a private repository of a free account
    answers rulesets and classic protection alike with HTTP 403 "Upgrade to
    GitHub Pro or make this repository public to enable this feature". That
    is a fact about the repository, not a failed read, so `check` reports it
    instead of stopping."""
    text = str(error)
    return "403" in text and "make this repository public to enable this feature" in text


def protects_default_branch(ruleset, default_branch):
    """True if `ruleset`'s ref_name conditions cover `default_branch`.

    A ruleset protects the default branch if it includes:
    - ~ALL (protects all refs, so includes default branch)
    - ~DEFAULT_BRANCH (explicit default branch ref)
    - refs/heads/<default_branch> (explicit branch name)

    Shared with apply.py, which checks a just-created ruleset against this
    same rule -- one place to know the three spellings GitHub accepts, so a
    fourth one discovered later only needs fixing here.
    """
    includes = ruleset.get("conditions", {}).get("ref_name", {}).get("include", [])
    branch_ref = f"refs/heads/{default_branch}"
    return "~ALL" in includes or "~DEFAULT_BRANCH" in includes or branch_ref in includes


class Tags:
    """The repository's tags, each looked up when it is asked about.

    `check` needs one tag, the latest release in CHANGES.md. Listing them all
    paginated through every tag of the repository on every run.
    """

    def __init__(self, gh, repo):
        self._gh, self._repo, self._known = gh, repo, {}

    def __contains__(self, tag):
        if tag not in self._known:
            self._known[tag] = self._gh.tag_exists(self._repo, tag)
        return self._known[tag]


def _subprocess_run(args):
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise GhError(f"{' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


class Gh:
    def __init__(self, run=None):
        self.run = run or _subprocess_run

    def api(self, path):
        return json.loads(self.run(["gh", "api", path]))

    def ruleset_id(self, repo, name):
        """The id of this repository's own ruleset called `name`, or None.

        `apply` could only ever POST, and GitHub answers a second ruleset with
        a name already taken with `422 Validation Failed`. Every repository
        that was protected before it was converted hits that -- which is most
        of them, and it is not even a surprise: `branch-protection` reads `ok`
        from exactly the ruleset the POST then collides with.

        Only `Repository`-source rulesets are candidates. An organisation
        ruleset cannot be written through this endpoint, and its name does not
        collide with a repository one.
        """
        for entry in self.api(f"repos/{repo}/rulesets"):
            if entry.get("name") == name and entry.get("source_type") == "Repository":
                return entry["id"]
        return None

    def path_exists_on_branch(self, repo, ref, path):
        """True/False if confirmed by asking GitHub; None if the check
        itself could not be confirmed -- a network error, a permissions
        problem, anything other than a clean 404.

        Exists so a precondition can ask about the branch GitHub will
        actually gate pull requests against, never about the caller's local
        checkout: a workflow committed to an unpushed branch reads as
        present on disk, but is not present here until it is confirmed on
        `ref`. Callers must refuse on both False and None -- an unverifiable
        result is neither "assume present" nor "assume absent", it is
        "cannot say, so don't proceed."
        """
        try:
            self.run(["gh", "api", f"repos/{repo}/contents/{path}?ref={_quote(ref)}"])
            return True
        except GhError as error:
            return False if "404" in str(error) else None

    def tag_exists(self, repo, tag):
        """A 404 is a missing tag; any other failure is raised, never guessed."""
        try:
            self.run(["gh", "api", f"repos/{repo}/git/ref/tags/{tag}"])
            return True
        except GhError as error:
            if "404" in str(error):
                return False
            raise

    def classic_protection(self, repo, branch):
        """The classic branch protection on `branch`, or None.

        Read beside the rulesets because oetiker/tvision-rs#29, the
        onboarding pull request, stayed blocked with every check green:
        classic protection on main required `test`, a job onboarding had
        replaced, and `check` read only the rulesets. A 404 means the branch
        has none; any other failure is raised, never read as unprotected.
        """
        try:
            return self.api(f"repos/{repo}/branches/{_quote(branch)}/protection")
        except GhError as error:
            if "404" in str(error):
                return None
            raise

    def current_repo(self):
        return self.run(["gh", "repo", "view", "--json", "nameWithOwner",
                         "-q", ".nameWithOwner"]).strip()

    def _api_paginated_list(self, path):
        """Fetch a list endpoint with pagination, returning flattened results.

        Uses --paginate --slurp to get [[page1], [page2], ...] which is then
        flattened to a single list. This ensures repositories with more than
        30 items don't silently truncate results.
        """
        output = self.run(["gh", "api", path, "--paginate", "--slurp"])
        pages = json.loads(output)
        # Flatten array of arrays into a single list
        result = []
        for page in pages:
            result.extend(page)
        return result

    def facts(self, repo):
        repository = self.api(f"repos/{repo}")
        default_branch = repository["default_branch"]

        protected = False
        contexts = set()
        strict = False
        try:
            rulesets = self._api_paginated_list(f"repos/{repo}/rulesets")
        except GhError as error:
            if not plan_refuses_protection(error):
                raise
            unavailable = str(error).rsplit("failed: ", 1)[-1]
            rulesets = []
        else:
            unavailable = None
        for summary in rulesets:
            ruleset = self.api(f"repos/{repo}/rulesets/{summary['id']}")
            if ruleset.get("enforcement") != "active":
                continue
            if not protects_default_branch(ruleset, default_branch):
                continue
            protected = True
            for rule in ruleset.get("rules", []):
                if rule.get("type") == "required_status_checks":
                    parameters = rule["parameters"]
                    strict = strict or parameters.get(
                        "strict_required_status_checks_policy") is True
                    for check in parameters["required_status_checks"]:
                        contexts.add(check["context"])

        # The plan that refuses rulesets refuses classic protection too, so
        # there is none to read.
        classic = None if unavailable else self.classic_protection(repo, default_branch)
        checks = (classic or {}).get("required_status_checks") or {}
        classic_contexts = tuple(sorted(
            set(checks.get("contexts", []))
            | {check["context"] for check in checks.get("checks", [])}))

        labels = {label["name"] for label in self._api_paginated_list(f"repos/{repo}/labels")}
        permissions = self.api(f"repos/{repo}/actions/permissions/workflow")
        release_prs = tuple(
            (pr["number"], pr["head"]["ref"])
            for pr in self._api_paginated_list(f"repos/{repo}/pulls?state=open")
            if pr["head"]["ref"].startswith("release/")
            and (pr["head"].get("repo") or {}).get("full_name") == repo
            and pr["user"]["login"] == "github-actions[bot]")

        return Facts(
            default_branch=default_branch,
            protected=protected,
            required_contexts=contexts,
            labels=labels,
            workflow_permissions=permissions["default_workflow_permissions"],
            can_approve_pr=permissions["can_approve_pull_request_reviews"],
            delete_branch_on_merge=repository["delete_branch_on_merge"],
            strict=strict,
            release_prs=release_prs,
            tags=Tags(self, repo),
            classic_protection=classic is not None,
            classic_contexts=classic_contexts,
            protection_unavailable=unavailable,
        )
