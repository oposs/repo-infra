"""Migration of a repository to the one release flow (D28).

D24 to D27 never shipped, so a repository on them was converted from the
branch. `check` reports what moves and `apply` moves it: the
.github/repo-infra.json keys D28 replaced, the Cargo.lock entries detection
proposes, and D26's project-owned release-build.yml, which becomes
release-build-local.yml unchanged. Everything is rendered from the migrated
config, so `check` shows the files as they will be after the move.
"""

import copy
import json
import pathlib
import re

from .apply import CONFIG, TRAILER, ApplyError, _git
from .markers import parse_markers
from .state import Item, unmanaged

D26_BUILD = ".github/workflows/release-build.yml"
LOCAL_BUILD = ".github/workflows/release-build-local.yml"
NAMES = ("release-build-rename", "release-build-config", "publish-source-tarball",
         "release-assets", "cargo-lock-version-files")
# Items whose change alters how a release in flight would finish.
RELEASE_FLOW = frozenset({"release-pr", "changelog", "ci", "release-publish",
                          "release-build", "workflow-lib", *NAMES})
_LOCK_NAME = re.compile(r'name = "([^"]+)"')
_RELEASE = re.compile(r"^## (\d+\.\d+\.\d+) - \d{4}-\d{2}-\d{2}\s*$")


def _is_d26_build(repo_root):
    path = pathlib.Path(repo_root) / D26_BUILD
    return path.is_file() and not parse_markers(path.read_text(encoding="utf-8"))


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
    return new, items


def renaming(migrations):
    return any(i.name == "release-build-rename" for i in migrations)


def without_superseded(items, migrations):
    """The D26 build reads as an unmanaged release-build.yml until it is renamed.

    Every block of the assembled file says so, the frame and each add-on, and
    each one is the rename's to resolve.
    """
    if not renaming(migrations):
        return items
    return [i for i in items if not (i.state == "conflict" and i.detail == unmanaged(D26_BUILD))]


def apply_migrations(repo_root, config, effective):
    """Perform the migration and stage it; returns the paths to commit."""
    root = pathlib.Path(repo_root)
    written = []
    if effective.get("release_build_local") and not config.get("release_build_local") \
            and _is_d26_build(root):
        _git(root, "mv", D26_BUILD, LOCAL_BUILD)
        written.append(LOCAL_BUILD)
    if effective != config:
        target = root / CONFIG
        target.write_text(json.dumps(effective, indent=2) + "\n", encoding="utf-8")
        if json.loads(target.read_text(encoding="utf-8")) != effective:
            raise ApplyError(f"{CONFIG}: wrote the migrated config and read back something else")
        written.append(CONFIG)
    return written


def commit_migration(repo_root, written):
    if not written:
        return None
    _git(repo_root, "add", *written)
    _git(repo_root, "commit", "-m",
         f"Migrate to the one release flow (repo-infra D28)\n\n{TRAILER}")
    return _git(repo_root, "rev-parse", "HEAD").strip()


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


def touches_release_flow(items):
    return any(i.name in RELEASE_FLOW and i.state not in ("ok", "skipped") for i in items)
