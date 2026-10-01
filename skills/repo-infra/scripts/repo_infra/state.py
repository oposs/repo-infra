"""Compare what is installed against what the plugin ships.

Drift is measured by version marker, never by content hash (D11). Every
repository legitimately edits its workflows -- the project name, the matrix
targets, an extra publish job -- so a hash would report drift on every
repository forever. The marker records only which generation this is, and a
local edit at the current generation is a perfectly healthy `ok`.
"""

import json
import pathlib
import posixpath
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


# The JS `refusedReleaseFiles` in workflows/lib/release.js enforces the same rule; change both.
def refused_release_files(entries, version_files):
    """release_files entries that would reopen the channel D26 closes.

    The read-only build writes the repository only through the files `finish`
    commits. A path that is, after normalising, CHANGES.md, a version file or
    anything under .github/ would let it rewrite the changelog, a version or a
    workflow. `finish` checks the same rule at run time (release.js).
    """
    versions = {posixpath.normpath(f["path"]) for f in version_files or []}
    refused = []
    for entry in entries:
        if not isinstance(entry, str) or entry == "":
            refused.append((entry, "is empty"))
            continue
        if entry.startswith("/"):
            refused.append((entry, "is an absolute path"))
            continue
        path = posixpath.normpath(entry)
        if path == ".." or path.startswith("../"):
            refused.append((entry, "points outside the repository"))
        elif path == "CHANGES.md":
            refused.append((entry, "is CHANGES.md, which the release pull request rolls"))
        elif path in versions:
            refused.append((entry, "is a version file, which the release pull request bumps"))
        elif path == ".github" or path.startswith(".github/"):
            refused.append((entry, "is under .github/"))
    return refused


def _dir_asset_names(manifest):
    """Assets installed as a directory of files sharing one marker and one version.

    `classify_files` still classifies every file in the directory separately --
    a per-file marker check is what catches one stray file out of ten -- but
    those per-file results are collapsed to a single row per asset before
    they reach the caller. See `_collapse_dir_asset`.
    """
    return {name for name, spec in manifest.get("assets", {}).items()
            if spec.get("kind") == "dir"}


def _normalize_detail(path, item):
    """`detail` for a per-path conflict names the path; strip it so that ten
    files hitting the *same* conflict compare equal instead of looking like
    ten different conflicts."""
    detail = item.detail
    if detail.startswith(path):
        detail = detail[len(path):].strip()
    return detail


def _collapse_dir_asset(name, entries):
    """`entries` is every per-file `(path, Item)` for one directory asset.

    The manifest versions a directory asset as a single unit -- one marker, one
    version, copied into every file it ships -- so a directory where every file
    agrees is one row, not one per file. A directory where files differ (a
    stray older version, one file missing while the rest are installed) is real
    drift that an averaged single verdict would hide, so the row names the
    files instead of picking one state for them.
    """
    states = {item.state for _, item in entries}

    if states == {"ok"}:
        # A local edit at the current version is a healthy `ok` (module
        # docstring); which particular file was touched doesn't change that.
        edited = any(item.detail for _, item in entries)
        return Item(name, "ok", "local edits" if edited else "")

    if states == {"missing"}:
        return Item(name, "missing", "not installed")

    if len(states) == 1:
        (state,) = states
        details = {_normalize_detail(path, item) for path, item in entries}
        if len(details) == 1:
            return Item(name, state, details.pop())

    groups = {}
    for path, item in entries:
        label = _normalize_detail(path, item) or item.state
        groups.setdefault(label, []).append(pathlib.Path(path).name)
    summary = "; ".join(f"{label} in {', '.join(sorted(files))}"
                        for label, files in sorted(groups.items()))
    # Files at older generations, files a newer generation adds, and files
    # already current are an upgrade that stopped half way or has not started;
    # `apply` finishes it file by file. Anything else in the mix (an unmanaged
    # file, one newer than the plugin) needs a human first.
    if states <= {"ok", "outdated", "missing"}:
        return Item(name, "outdated", f"files differ: {summary}")
    return Item(name, "conflict", f"files disagree: {summary}")


def classify_files(repo_root, rendered, manifest):
    dir_assets = _dir_asset_names(manifest)
    per_path = []
    for path, expected_text in sorted(rendered.items()):
        installed = pathlib.Path(repo_root) / path
        expected = parse_markers(expected_text)
        if not installed.is_file():
            per_path.extend((path, Item(m.asset, "missing", "not installed")) for m in expected)
            continue

        text = installed.read_text(encoding="utf-8")
        found = {m.asset: m.version for m in parse_markers(text)}
        edited = text != expected_text
        filtered = path in _REQUIRED_WORKFLOWS and carries_a_path_filter(text)
        for marker in expected:
            have = found.get(marker.asset)
            if filtered and marker is expected[0]:
                per_path.append((path, Item(marker.asset, "conflict",
                                  f"{path} filters on paths; required checks would leave "
                                  "every unmatched pull request pending forever. Move "
                                  "the condition into the job.")))
            elif have is None:
                per_path.append((path, Item(marker.asset, "conflict",
                                  f"{path} exists but is not managed by repo-infra")))
            elif have < marker.version:
                per_path.append((path, Item(marker.asset, "outdated",
                                  f"v{have} installed, v{marker.version} available")))
            elif have > marker.version:
                per_path.append((path, Item(marker.asset, "conflict",
                                  f"v{have} installed is newer than the plugin's "
                                  f"v{marker.version}; update the plugin")))
            else:
                # Attribute an edit to the file's frame marker only: with several
                # blocks in one file there is no honest way to say which block
                # was touched, and guessing would be worse than saying nothing.
                detail = "local edits" if edited and marker is expected[0] else ""
                per_path.append((path, Item(marker.asset, "ok", detail)))

    grouped = {}
    for path, item in per_path:
        if item.name in dir_assets:
            grouped.setdefault(item.name, []).append((path, item))

    items = []
    collapsed = set()
    for _path, item in per_path:
        if item.name in dir_assets:
            if item.name in collapsed:
                continue
            collapsed.add(item.name)
            items.append(_collapse_dir_asset(item.name, grouped[item.name]))
        else:
            items.append(item)
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
    if missing:
        items.append(Item("required-checks", "missing",
                          "the ruleset does not require " + " or ".join(missing)))
    elif not facts.strict:
        items.append(Item(
            "required-checks", "outdated",
            "the ruleset lets a pull request merge while its branch is behind main "
            "(strict_required_status_checks_policy is off); a release built from an "
            "older main could then merge (D28)"))
    else:
        items.append(Item("required-checks", "ok", ""))

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


def classify_contracts(repo_root, result, config=None):
    """Project-owned files an installed block depends on but cannot ship.

    The counterpart of an ambiguity: not a question about this repository, but
    a file the standard documents and the project must write (D20). Reported as
    `conflict` rather than `missing` because there is nothing for `apply` to
    install -- only a human can write it -- and because installing the block
    without it does not merely leave a gap, it makes ci.yml invalid so that no
    job in the repository runs at all.
    """
    config = config or {}
    items = []
    if "github-action" in result.ecosystems:
        seam = pathlib.Path(repo_root) / ".github/workflows/action-test.yml"
        if not seam.is_file():
            items.append(Item(
                "action-test", "conflict",
                "ci.yml's action-test job calls .github/workflows/action-test.yml "
                "and this repository has no such file; GitHub rejects the whole "
                "workflow, so every check stops reporting. Write it as the "
                "project's own test (references/conventions.md)."))
    if config.get("ci_local"):
        seam = pathlib.Path(repo_root) / ".github/workflows/ci-local.yml"
        if not seam.is_file():
            items.append(Item(
                "ci-local-workflow", "conflict",
                "ci.yml's ci-local job calls .github/workflows/ci-local.yml "
                "and this repository has no such file; GitHub rejects the whole "
                "workflow, so every check stops reporting. Write it as the "
                "project's own jobs (references/conventions.md), or remove "
                "\"ci_local\" from .github/repo-infra.json."))
    if config.get("release_build"):
        seam = pathlib.Path(repo_root) / ".github/workflows/release-build.yml"
        if not seam.is_file():
            items.append(Item(
                "release-build", "conflict",
                "release_build is set and .github/workflows/release-build.yml does "
                "not exist; the release workflow calls it and GitHub rejects the "
                "whole workflow. Write it (references/release-flow.md)."))
    if "publish-gitea-packages" in config.get("publish", []):
        if not config.get("release_build"):
            items.append(Item(
                "gitea-packages-build", "conflict",
                "publish-gitea-packages uploads the .deb and .rpm files the release "
                "pull request built, and without release_build nothing builds them "
                "before it runs, so it would upload a partial set. Set "
                "\"release_build\": true in .github/repo-infra.json, or remove "
                "publish-gitea-packages from \"publish\"."))
        gitea = config.get("gitea_packages")
        gitea = gitea if isinstance(gitea, dict) else {}
        absent = [k for k in ("url", "owner") if not gitea.get(k)]
        if absent:
            items.append(Item(
                "gitea-packages-config", "conflict",
                "publish-gitea-packages reads \"gitea_packages\" in "
                ".github/repo-infra.json and it lacks " + " and ".join(absent)
                + "; set \"url\" (the Gitea base URL) and \"owner\" "
                "(references/conventions.md)."))
    refused = refused_release_files(config.get("release_files", []),
                                    config.get("version_files", []))
    if refused:
        items.append(Item(
            "release-files", "conflict",
            "release_files in .github/repo-infra.json: "
            + "; ".join(f"{path} {reason}" for path, reason in refused)))
    return items


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
