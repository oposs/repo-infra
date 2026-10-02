"""check (D30): the state of every piece, the callers, the config and the
administration items.

It reports and never writes, and it never refuses a repository because
nothing matched it: choosing pieces is the AI's judgement. A piece is
identified by its bytes against every published version, never by its
marker: the marker says which version a file claims to be, the bytes say
whether it is one.
"""

import hashlib
import json
import pathlib
import posixpath
import re
from collections import namedtuple

from . import callers
from .markers import parse_markers
from .pieces import ASSETS, load_pieces, load_published
from .report import Item

PieceState = namedtuple("PieceState", "state installed edited")

CONFIG = ".github/repo-infra.json"
# What the borrowed release machinery reads (release-pr.yml, lib/*.js).
KEYS = ("version_files", "release_assets", "release_files", "gitea_packages",
        "moving_major_tag", "rust")
OBSOLETE = ("ecosystems", "ci", "ci_local", "publish", "build", "publish_local",
            "release_build", "release_build_local", "skip", "answers")
SCANNED = (".github", "build", "m4")
REQUIRED_WORKFLOWS = ("ci.yml", "changelog.yml")


def _digest(data):
    return hashlib.sha256(data).hexdigest()


# Files installed by repo-infra v0.3.1 carry ` sha256=<hex>` on the first line
# that is a marker (line 2 when the file starts with `name:`). The bytes of the
# published version have no such suffix. The marker pattern mirrors markers.py.
_MARKER_LINE = re.compile(
    rb"^\s*(?:#|//|--|dnl\b)\s*repo-infra:\s+[a-z0-9][a-z0-9-]*\s+v\d+(?:\s.*)?$")
_STAMP = re.compile(rb" sha256=[0-9a-f]+(?=\r?$)")


def _unstamped(data):
    lines = data.split(b"\n")
    for i, line in enumerate(lines):
        if _MARKER_LINE.match(line.rstrip(b"\r")):
            lines[i] = _STAMP.sub(b"", line, count=1)
            break
    return b"\n".join(lines)


def piece_state(repo_root, piece, history):
    root = pathlib.Path(repo_root)
    paths = sorted(set(history) | set(piece.files))
    installed = {p: _unstamped((root / p).read_bytes()) for p in paths if (root / p).is_file()}
    if not installed:
        return PieceState("absent", None, [])
    versions, edited = {}, []
    for path, data in installed.items():
        matches = [v for v, d in history.get(path, {}).items() if d == _digest(data)]
        if matches:
            versions[path] = max(matches)
        else:
            edited.append(path)
    if edited:
        markers = parse_markers(installed[edited[0]].decode("utf-8", errors="replace"))
        claimed = next((m.version for m in markers if m.asset == piece.name), None)
        return PieceState("edited", claimed, edited)
    current = (set(installed) == set(piece.files)
               and all(versions[p] == piece.version for p in piece.files))
    return PieceState("current" if current else "outdated", min(versions.values()), [])


def missing_dependencies(pieces, states):
    found = {}
    for name, state in sorted(states.items()):
        if state.state == "absent":
            continue
        for dep in pieces[name].needs:
            if dep in states and states[dep].state == "absent":
                found.setdefault(dep, name)
    return sorted(found.items())


def _edited(piece, state):
    files = ", ".join(state.edited)
    if state.installed and state.installed > piece.version:
        return (f"{files} says v{state.installed}, newer than this plugin's "
                f"v{piece.version}; update the plugin")
    return (f"{files} matches no published version of {piece.name}. Pieces are used as "
            "published: move the change into a caller. apply stops here with the files "
            "for a hand merge")


def unknown_items(repo_root, pieces):
    root = pathlib.Path(repo_root)
    items = []
    for top in SCANNED:
        base = root / top
        if not base.is_dir():
            continue
        for path in sorted(p for p in base.rglob("*") if p.is_file()):
            try:
                markers = parse_markers(path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, OSError):
                continue
            if markers and markers[0].asset not in pieces:
                first = markers[0]
                items.append(Item(
                    "pieces", first.asset, "unknown",
                    f"{path.relative_to(root).as_posix()} carries `repo-infra: {first.asset} "
                    f"v{first.version}` and repo-infra ships no such piece. A file of the "
                    "assembled standard (ci, release-build, release-publish) is a caller "
                    "now: rewrite it from references/onboarding.md"))
    return items


def piece_items(repo_root, pieces, published):
    states = {name: piece_state(repo_root, piece, published.get(name, {}))
              for name, piece in pieces.items()}
    items = []
    for name, state in sorted(states.items()):
        piece = pieces[name]
        if state.state == "absent":
            if piece.core:
                items.append(Item("pieces", name, "missing",
                                  "not installed; every repository carries it"))
        elif state.state == "current":
            items.append(Item("pieces", name, "current", f"v{piece.version}"))
        elif state.state == "outdated":
            gone = [f for f in piece.files if not (pathlib.Path(repo_root) / f).is_file()]
            if gone and state.installed == piece.version:
                detail = f"{', '.join(gone)} is missing; apply restores it"
            else:
                detail = (f"v{state.installed} installed, v{piece.version} available; "
                          "apply replaces it")
            items.append(Item("pieces", name, "outdated", detail))
        else:
            items.append(Item("pieces", name, "edited", _edited(piece, state)))
    reported = {i.name for i in items if i.state == "missing"}
    items += [Item("pieces", dep, "missing", f"{user} needs it")
              for dep, user in missing_dependencies(pieces, states) if dep not in reported]
    return items + unknown_items(repo_root, pieces)


# The JS `refusedReleaseFiles` in workflows/lib/release.js enforces the same rule; change both.
def refused_release_files(entries, version_files):
    """release_files entries that would reopen the channel D26 closes.

    The read-only build writes the repository only through the files `finish`
    commits. A path that is, after normalising, CHANGES.md, a version file or
    anything under .github/ would let it rewrite the changelog, a version or a
    workflow. `finish` checks the same rule at run time (release.js).
    """
    versions = {posixpath.normpath(f["path"]) for f in version_files or []
                if isinstance(f, dict) and isinstance(f.get("path"), str)}
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


def config_items(repo_root, docs):
    path = pathlib.Path(repo_root) / CONFIG
    if not path.is_file():
        return [Item("config", "repo-infra.json", "missing",
                     f"{CONFIG} does not exist; Create release PR reads version_files "
                     "from it")]
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return [Item("config", "repo-infra.json", "problem", f"{CONFIG} is not JSON: {error}")]
    if not isinstance(config, dict):
        return [Item("config", "repo-infra.json", "problem", f"{CONFIG} is not a JSON object")]
    items = []
    old = [key for key in config if key in OBSOLETE]
    if old:
        items.append(Item("config", "repo-infra.json", "problem",
                          f"{', '.join(old)}: no longer read; the callers state this now "
                          "(D30). Remove them"))
    strange = [key for key in config
               if key not in KEYS and key not in OBSOLETE and not key.startswith("_")]
    if strange:
        items.append(Item("config", "repo-infra.json", "problem",
                          f"{', '.join(strange)}: not a key repo-infra reads"))
    if not config.get("version_files"):
        items.append(Item("config", "version_files", "problem",
                          "version_files is empty; Create release PR would bump no file"))
    version_files = config.get("version_files", [])
    if version_files and not (isinstance(version_files, list) and all(
            isinstance(f, dict) and isinstance(f.get("path"), str) for f in version_files)):
        items.append(Item("config", "version_files", "problem",
                          "version_files must be a list of objects, each with a \"path\""))
        version_files = []
    release_files = config.get("release_files", [])
    if not isinstance(release_files, list):
        items.append(Item("config", "release_files", "problem",
                          "release_files must be a list of paths"))
        release_files = []
    refused = refused_release_files(release_files, version_files)
    if refused:
        items.append(Item("config", "release_files", "problem",
                          "; ".join(f"{entry} {reason}" for entry, reason in refused)))
    if callers.calls(docs, "ri-publish-gitea.yml"):
        gitea = config.get("gitea_packages")
        gitea = gitea if isinstance(gitea, dict) else {}
        absent = [key for key in ("url", "owner") if not gitea.get(key)]
        if absent:
            items.append(Item("config", "gitea_packages", "problem",
                              "ri-publish-gitea reads \"gitea_packages\" in "
                              f"{CONFIG} and it lacks {' and '.join(absent)}; set \"url\" "
                              "(the Gitea base URL) and \"owner\""))
    return items


def path_filter_items(docs):
    items = []
    for name in REQUIRED_WORKFLOWS:
        doc = docs.get(name)
        on = doc.get("on") if isinstance(doc, dict) else None
        if not isinstance(on, dict):
            continue
        if any(isinstance(spec, dict) and {"paths", "paths-ignore"} & set(spec)
               for spec in on.values()):
            items.append(Item("callers", name, "conflict",
                              f"{name} filters on paths; a required check would leave every "
                              "unmatched pull request pending forever. Move the condition "
                              "into the job (D13)"))
    return items


def classify_remote(facts):
    items = []

    if facts.default_branch == "main":
        items.append(Item("administration", "default-branch", "ok", "main"))
    else:
        items.append(Item("administration", "default-branch", "conflict",
            f"'{facts.default_branch}' -- the standard is 'main'. Rename before anything "
            "else is applied: the ruleset targets the default branch while the workflows "
            f"run on main, so on '{facts.default_branch}' every required check stays "
            "pending forever. Renaming breaks links, forks and clones that pin it."))

    items.append(Item("administration", "branch-protection", "ok" if facts.protected else "missing",
                      "" if facts.protected else "the default branch is unprotected"))

    wanted = {"ci-passed", "changelog-updated"}
    missing = sorted(wanted - facts.required_contexts)
    if missing:
        items.append(Item("administration", "required-checks", "missing",
                          "the ruleset does not require " + " or ".join(missing)))
    elif not facts.strict:
        items.append(Item("administration", "required-checks", "outdated",
            "the ruleset lets a pull request merge while its branch is behind main "
            "(strict_required_status_checks_policy is off); a release built from an "
            "older main could then merge (D28)"))
    else:
        items.append(Item("administration", "required-checks", "ok", ""))

    has_label = "no-changelog" in facts.labels
    items.append(Item("administration", "no-changelog-label", "ok" if has_label else "missing",
                      "" if has_label else "dependabot requests it; it does not exist"))

    ok = facts.can_approve_pr and facts.workflow_permissions == "write"
    items.append(Item("administration", "actions-open-pr", "ok" if ok else "missing",
        "" if ok else f"can_approve_pull_request_reviews = {facts.can_approve_pr}, "
                      f"default_workflow_permissions = {facts.workflow_permissions}"))
    return items


def run(repo_root, facts, assets=ASSETS):
    pieces = load_pieces(assets)
    docs = callers.read_workflows(repo_root)
    return (piece_items(repo_root, pieces, load_published(assets))
            + callers.validate(docs, pieces, assets)
            + config_items(repo_root, docs)
            + path_filter_items(docs)
            + classify_remote(facts))
