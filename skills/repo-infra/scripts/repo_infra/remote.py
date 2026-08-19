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

    def facts(self, repo):
        repository = self.api(f"repos/{repo}")
        default_branch = repository["default_branch"]

        protected = False
        contexts = set()
        for summary in self.api(f"repos/{repo}/rulesets"):
            ruleset = self.api(f"repos/{repo}/rulesets/{summary['id']}")
            if ruleset.get("enforcement") != "active":
                continue
            includes = ruleset.get("conditions", {}).get("ref_name", {}).get("include", [])
            if "~DEFAULT_BRANCH" not in includes and f"refs/heads/{default_branch}" not in includes:
                continue
            protected = True
            for rule in ruleset.get("rules", []):
                if rule.get("type") == "required_status_checks":
                    for check in rule["parameters"]["required_status_checks"]:
                        contexts.add(check["context"])

        labels = {label["name"] for label in self.api(f"repos/{repo}/labels")}
        permissions = self.api(f"repos/{repo}/actions/permissions/workflow")

        return Facts(
            default_branch=default_branch,
            protected=protected,
            required_contexts=contexts,
            labels=labels,
            workflow_permissions=permissions["default_workflow_permissions"],
            can_approve_pr=permissions["can_approve_pull_request_reviews"],
        )
