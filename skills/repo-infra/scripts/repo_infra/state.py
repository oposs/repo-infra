"""Compare what is installed against what the plugin ships.

Drift is measured by version marker, never by content hash (D11). Every
repository legitimately edits its workflows -- the project name, the matrix
targets, an extra publish job -- so a hash would report drift on every
repository forever. The marker records only which generation this is, and a
local edit at the current generation is a perfectly healthy `ok`.
"""

import json
import pathlib
import re
from collections import namedtuple

from .markers import parse_markers

Item = namedtuple("Item", "name state detail")

# report.py and cli.py both import this rather than each spelling out the same
# tuple, so the report's count and `check`'s exit code can never disagree
# about what counts as drift.
NEEDS_ATTENTION_STATES = ("missing", "outdated", "conflict", "ambiguous")

# Reported as `missing`, a path-filtered required workflow would let `apply`
# proceed and the breakage -- pull requests pending forever -- would only
# surface at the next release. This must be a `conflict` instead (spec D13).
_REQUIRED_WORKFLOWS = (".github/workflows/ci.yml", ".github/workflows/changelog.yml")

_PATH_FILTER_KEY = re.compile(r"paths(-ignore)?:")


def carries_a_path_filter(text):
    """A `paths:`/`paths-ignore:` YAML key, not a comment that merely names one.

    Shared with tests/test_blocks.py, which guards the plugin's own assets --
    this guards the repositories the plugin converts. One helper so the two
    checks cannot drift apart.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if _PATH_FILTER_KEY.match(stripped):
            return True
    return False


def classify_files(repo_root, rendered, manifest):
    items = []
    for path, expected_text in sorted(rendered.items()):
        installed = pathlib.Path(repo_root) / path
        expected = parse_markers(expected_text)
        if not installed.is_file():
            items.extend(Item(m.asset, "missing", "not installed") for m in expected)
            continue

        text = installed.read_text(encoding="utf-8")
        found = {m.asset: m.version for m in parse_markers(text)}
        edited = text != expected_text
        filtered = path in _REQUIRED_WORKFLOWS and carries_a_path_filter(text)
        for marker in expected:
            have = found.get(marker.asset)
            if filtered and marker is expected[0]:
                items.append(Item(marker.asset, "conflict",
                                  f"{path} filters on paths; required checks would leave "
                                  "every unmatched pull request pending forever. Move "
                                  "the condition into the job."))
            elif have is None:
                items.append(Item(marker.asset, "conflict",
                                  f"{path} exists but is not managed by repo-infra"))
            elif have < marker.version:
                items.append(Item(marker.asset, "outdated",
                                  f"v{have} installed, v{marker.version} available"))
            elif have > marker.version:
                items.append(Item(marker.asset, "conflict",
                                  f"v{have} installed is newer than the plugin's "
                                  f"v{marker.version}; update the plugin"))
            else:
                # Attribute an edit to the file's frame marker only: with several
                # blocks in one file there is no honest way to say which block
                # was touched, and guessing would be worse than saying nothing.
                detail = "local edits" if edited and marker is expected[0] else ""
                items.append(Item(marker.asset, "ok", detail))
    return items


def classify_remote(facts):
    items = []

    if facts.default_branch == "main":
        items.append(Item("default-branch", "ok", "main"))
    else:
        items.append(Item(
            "default-branch", "conflict",
            f"'{facts.default_branch}' -- the standard is 'main'. Rename before anything "
            "else is applied: the ruleset targets the default branch while the workflows "
            f"run on main, so on '{facts.default_branch}' every required check stays "
            "pending forever. Renaming breaks links, forks and clones that pin it."))

    items.append(Item("branch-protection", "ok" if facts.protected else "missing",
                      "" if facts.protected else "the default branch is unprotected"))

    wanted = {"ci-passed", "changelog-updated"}
    missing = sorted(wanted - facts.required_contexts)
    items.append(Item(
        "required-checks", "ok" if not missing else "missing",
        "" if not missing else "the ruleset does not require " + " or ".join(missing)))

    has_label = "no-changelog" in facts.labels
    items.append(Item("no-changelog-label", "ok" if has_label else "missing",
                      "" if has_label else "dependabot requests it; it does not exist"))

    ok = facts.can_approve_pr and facts.workflow_permissions == "write"
    items.append(Item(
        "actions-open-pr", "ok" if ok else "missing",
        "" if ok else f"can_approve_pull_request_reviews = {facts.can_approve_pr}, "
                      f"default_workflow_permissions = {facts.workflow_permissions}"))
    return items


def classify_ambiguities(result):
    """Unresolved questions from detection, one item per ambiguity.

    `apply` refuses to run while any of these stand, so they must count as
    needing attention here too -- otherwise the report can say "nothing to
    do" on a repository that `apply` then blocks on.
    """
    return [Item(a["id"], "ambiguous", a["question"]) for a in result.ambiguities]


def _skips(repo_root):
    """Deliberate refusals, recorded once in .github/repo-infra.json.

    Without this the checker nags about man pages on every library crate
    forever. It is the only way to record a considered "no", so a skipped item
    keeps its reason in the report rather than disappearing from it.
    """
    config = pathlib.Path(repo_root) / ".github/repo-infra.json"
    if not config.is_file():
        return {}
    return json.loads(config.read_text(encoding="utf-8")).get("skip", {})


def classify(repo_root, rendered, manifest, facts):
    items = classify_remote(facts) + classify_files(repo_root, rendered, manifest)
    skip = _skips(repo_root)
    return [Item(i.name, "skipped", skip[i.name]) if i.name in skip else i for i in items]
