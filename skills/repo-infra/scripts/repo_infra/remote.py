"""Everything the checker reads from GitHub.

One class, one injectable runner. `remote.py` never touches the file system and
`assemble.py` never touches the network, which is what lets every rule in this
plugin be tested without a GitHub account.
"""

import json
import subprocess
from collections import namedtuple

Facts = namedtuple(
    "Facts",
    "default_branch protected required_contexts labels workflow_permissions can_approve_pr")


class GhError(Exception):
    """A `gh` invocation failed. Never swallowed, never defaulted."""


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
        for summary in self._api_paginated_list(f"repos/{repo}/rulesets"):
            ruleset = self.api(f"repos/{repo}/rulesets/{summary['id']}")
            if ruleset.get("enforcement") != "active":
                continue
            if not protects_default_branch(ruleset, default_branch):
                continue
            protected = True
            for rule in ruleset.get("rules", []):
                if rule.get("type") == "required_status_checks":
                    for check in rule["parameters"]["required_status_checks"]:
                        contexts.add(check["context"])

        labels = {label["name"] for label in self._api_paginated_list(f"repos/{repo}/labels")}
        permissions = self.api(f"repos/{repo}/actions/permissions/workflow")

        return Facts(
            default_branch=default_branch,
            protected=protected,
            required_contexts=contexts,
            labels=labels,
            workflow_permissions=permissions["default_workflow_permissions"],
            can_approve_pr=permissions["can_approve_pull_request_reviews"],
        )
