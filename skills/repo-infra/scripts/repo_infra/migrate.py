"""Migration of a repository to the one release flow (D28).

D24 to D27 never shipped, so a repository on them was converted from the
branch. `check` reports what moves and `apply` moves it: the
.github/repo-infra.json keys D28 replaced, the Cargo.lock entries detection
proposes, D26's project-owned release-build.yml, which becomes
release-build-local.yml unchanged, and D26's release-pr.yml (marker
`release-pr-build v1`), which is replaced whole by the release-pr asset.
Everything is rendered from the migrated
config, so `check` shows the files as they will be after the move.
"""

import copy
import json
import pathlib
import re

from .apply import CONFIG, TRAILER, ApplyError, config_text, git, write_asset
from .markers import parse_markers
from .state import Item, unmanaged

D26_BUILD = ".github/workflows/release-build.yml"
LOCAL_BUILD = ".github/workflows/release-build-local.yml"
RELEASE_PR = ".github/workflows/release-pr.yml"
NAMES = ("release-build-rename", "release-build-config", "publish-source-tarball",
         "release-assets", "cargo-lock-version-files", "release-pr-replace")
# The files whose change alters how a release in flight would finish. An item
# belongs to the release flow when it writes one of them: a CI block writes
# the whole ci.yml, frame included. The ruleset's up-to-date rule is not in
# it: turning it on while an old-flow release pull request is open only asks
# that pull request to be up to date before it merges.
RELEASE_FLOW_FILES = frozenset({
    RELEASE_PR, ".github/workflows/changelog.yml", ".github/workflows/ci.yml",
    ".github/workflows/release-publish.yml", D26_BUILD})
_LIB = ".github/workflows/lib/"
_LOCK_NAME = re.compile(r'name = "([^"]+)"')
_RELEASE = re.compile(r"^## (\d+\.\d+\.\d+) - \d{4}-\d{2}-\d{2}\s*$")


def _is_d26_build(repo_root):
    path = pathlib.Path(repo_root) / D26_BUILD
    return path.is_file() and not parse_markers(path.read_text(encoding="utf-8"))


def _is_d26_release_pr(repo_root):
    """Exactly the marker D26 shipped. Any other unknown marker stays a conflict:
    `release-pr-build` is not an alias of `release-pr`."""
    path = pathlib.Path(repo_root) / RELEASE_PR
    if not path.is_file():
        return False
    found = parse_markers(path.read_text(encoding="utf-8"))
    return [(m.asset, m.version) for m in found] == [("release-pr-build", 1)]


def _lock_crate(entry):
    if entry.get("path") != "Cargo.lock":
        return None
    match = _LOCK_NAME.search(entry.get("pattern", ""))
    return match.group(1) if match else None


def migrated_config(repo_root, config, result, manifest):
    """The config after D28's migration, and one Item per change it makes."""
    new = copy.deepcopy(config)
    items = []

    build = new.get("release_build")
    if isinstance(build, bool):
        if build and _is_d26_build(repo_root):
            new["release_build_local"] = True
            items.append(Item(
                "release-build-rename", "outdated",
                f"{D26_BUILD} is D26's project-owned build. apply renames it to "
                f"{LOCAL_BUILD} with git mv, unchanged, sets \"release_build_local\": true "
                "and installs the assembled release-build.yml."))
        new["release_build"] = []
        items.append(Item(
            "release-build-config", "outdated",
            f"\"release_build\": {json.dumps(build)} becomes \"release_build\": [], the "
            "list of build add-ons."))

    publish = new.get("publish", [])
    if "publish-source-tarball" in publish:
        new["publish"] = [p for p in publish if p != "publish-source-tarball"]
        builds = list(new.get("release_build") or [])
        if "release-source-tarball" not in builds:
            builds.append("release-source-tarball")
        new["release_build"] = builds
        items.append(Item(
            "publish-source-tarball", "outdated",
            "the tarball is built before the merge now: apply moves "
            "\"publish-source-tarball\" from \"publish\" to \"release_build\": "
            "[\"release-source-tarball\"]."))

    blocks = manifest.get("release_build_blocks", {})
    builds = new.get("release_build") if isinstance(new.get("release_build"), list) else []
    declared = list(new.get("release_assets", []))
    wanted = [p for name in builds for p in blocks.get(name, {}).get("assets", [])]
    absent = [p for p in dict.fromkeys(wanted) if p not in declared]
    if absent:
        new["release_assets"] = declared + absent
        items.append(Item(
            "release-assets", "conflict",
            "release_assets in .github/repo-infra.json lacks " + ", ".join(absent)
            + ", which an installed release_build add-on builds; finish would accept a "
            "build that drops it. apply adds it."))

    if "version_files" in new:
        have = {_lock_crate(e) for e in new["version_files"]}
        lock = [e for e in result.version_files
                if _lock_crate(e) and _lock_crate(e) not in have]
        if lock:
            new["version_files"] = list(new["version_files"]) + lock
            items.append(Item(
                "cargo-lock-version-files", "missing",
                "version_files has no Cargo.lock entry for "
                + ", ".join(_lock_crate(e) for e in lock)
                + "; the release pull request would leave Cargo.lock at the old version. "
                "apply adds them."))

    if _is_d26_release_pr(repo_root):
        version = manifest["assets"]["release-pr"]["version"]
        items.append(Item(
            "release-pr-replace", "outdated",
            f"{RELEASE_PR} carries release-pr-build v1, D26's release workflow, which "
            "calls workflow library functions D28 removed. apply replaces it whole with "
            f"release-pr v{version}."))
    return new, items


def renaming(migrations):
    return any(i.name == "release-build-rename" for i in migrations)


def without_superseded(items, migrations):
    """D26's files read as unmanaged until their migration acts on them.

    The D26 build is reported by every block of the assembled release-build.yml,
    the frame and each add-on, and D26's release-pr.yml by the release-pr item;
    each of those is the migration's to resolve.
    """
    superseded = set()
    if renaming(migrations):
        superseded.add(unmanaged(D26_BUILD))
    if any(i.name == "release-pr-replace" for i in migrations):
        superseded.add(unmanaged(RELEASE_PR))
    return [i for i in items if not (i.state == "conflict" and i.detail in superseded)]


def apply_migrations(repo_root, config, effective, rendered):
    """Perform the migration and stage it; returns the paths to commit.

    `rendered` is the rendering of the migrated config; D26's release-pr.yml
    is replaced by its release-pr.yml.
    """
    root = pathlib.Path(repo_root)
    written = []
    if _is_d26_release_pr(root):
        written.append(write_asset(root, RELEASE_PR, rendered[RELEASE_PR]))
    if effective.get("release_build_local") and not config.get("release_build_local") \
            and _is_d26_build(root):
        git(root, "mv", D26_BUILD, LOCAL_BUILD)
        written.append(LOCAL_BUILD)
    if effective != config:
        target = root / CONFIG
        original = target.read_text(encoding="utf-8") if target.is_file() else None
        target.write_text(config_text(effective, original), encoding="utf-8")
        if json.loads(target.read_text(encoding="utf-8")) != effective:
            raise ApplyError(f"{CONFIG}: wrote the migrated config and read back something else")
        written.append(CONFIG)
    return written


def commit_migration(repo_root, written):
    if not written:
        return None
    git(repo_root, "add", *written)
    git(repo_root, "commit", "-m",
         f"Migrate to the one release flow (repo-infra D28)\n\n{TRAILER}")
    return git(repo_root, "rev-parse", "HEAD").strip()


def latest_release(text):
    for line in text.splitlines():
        match = _RELEASE.match(line)
        if match:
            return match.group(1)
    return None


def release_in_progress(repo_root, facts):
    """Why this repository cannot migrate right now, or None.

    The new publish expects a draft with release-build.json and the new
    release mode expects release-built; a release started by the old flow
    has neither.
    """
    if facts.release_prs:
        number, branch = facts.release_prs[0]
        return Item(
            "release-in-progress", "conflict",
            f"release pull request #{number} ({branch}) is open. Merge or close it and "
            "let its publish finish, then migrate: the new flow cannot finish a release "
            "the old one started.")
    changes = pathlib.Path(repo_root) / "CHANGES.md"
    latest = latest_release(changes.read_text(encoding="utf-8")) if changes.is_file() else None
    if latest and facts.tags is not None and f"v{latest}" not in facts.tags:
        return Item(
            "release-in-progress", "conflict",
            f"v{latest} is in CHANGES.md but has no tag: its publish has not finished. "
            "Finish or abandon that release, then migrate.")
    return None


def in_release_flow(name, rendered):
    if name in NAMES:
        return True
    return any(path in RELEASE_FLOW_FILES or path.startswith(_LIB)
               for path, text in rendered.items()
               if any(m.asset == name for m in parse_markers(text)))


def touches_release_flow(items, rendered):
    return any(i.state not in ("ok", "skipped") and in_release_flow(i.name, rendered)
               for i in items)
