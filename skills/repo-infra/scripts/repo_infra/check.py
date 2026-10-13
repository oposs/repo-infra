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
# What the borrowed release machinery reads (release-pr.yml, lib/*.js), and
# the exceptions the shape review reads (D32).
KEYS = ("version_files", "release_assets", "release_files", "gitea_packages",
        "moving_major_tag", "rust", "exceptions")
OBSOLETE = ("ecosystems", "ci", "ci_local", "publish", "build", "publish_local",
            "release_build", "release_build_local", "answers")
# D30 removed `skip`; D32 gave its purpose to `exceptions`, keyed by rule id.
RENAMED = {"skip": "exceptions"}
SCANNED = (".github", "build", "m4")
REQUIRED_WORKFLOWS = ("ci.yml", "changelog.yml")
# D33: pieces that left the store, and how a consumer's copy of each is found.
RETIRED = {"changelog": ".github/workflows/changelog.yml",
           "release-pr": ".github/workflows/release-pr.yml",
           "ri-ci-lib": ".github/workflows/ri-ci-lib.yml"}
LIBRARY = "workflow-lib"


def _digest(data):
    return hashlib.sha256(data).hexdigest()


# Files installed by repo-infra v0.3.1 carry ` sha256=<hex>` on the first line
# that is a marker (line 2 when the file starts with `name:`). The bytes of the
# published version have no such suffix. The marker pattern mirrors markers.py.
_MARKER_LINE = re.compile(
    rb"^\s*(?:#|//|--|dnl\b)\s*repo-infra:\s+[a-z0-9][a-z0-9-]*\s+v\d+(?:\s.*)?$")
_STAMP = re.compile(rb" sha256=[0-9a-f]+(?=\r?$)")


def unstamped(data):
    lines = data.split(b"\n")
    for i, line in enumerate(lines):
        if _MARKER_LINE.match(line.rstrip(b"\r")):
            lines[i] = _STAMP.sub(b"", line, count=1)
            break
    return b"\n".join(lines)


def piece_state(repo_root, piece, history):
    root = pathlib.Path(repo_root)
    paths = sorted(set(history) | set(piece.files))
    installed = {p: unstamped((root / p).read_bytes()) for p in paths if (root / p).is_file()}
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


def is_home(repo_root):
    """True in repo-infra itself, the repository that ships the pieces (D33):
    its pieces are local and called through ./, and its library is the
    library."""
    return (pathlib.Path(repo_root) / "skills/repo-infra/assets/manifest.json").is_file()


def missing_dependencies(pieces, states):
    found = {}
    for name, state in sorted(states.items()):
        if state.state == "absent":
            continue
        for dep in pieces[name].needs:
            if dep in states and states[dep].state == "absent":
                found.setdefault(dep, name)
    return sorted(found.items())


def edited_detail(piece, state):
    files = ", ".join(state.edited)
    if state.installed and state.installed > piece.version:
        return (f"{files} says v{state.installed}, newer than this plugin's "
                f"v{piece.version}; update the plugin")
    if state.installed == piece.version:
        # A finished --from merge ends here. apply writes no file that claims
        # the current version, so the way back to published bytes is to
        # remove the file and install the piece again.
        return (f"{files} claims v{piece.version}, the current version, but matches no "
                f"published version of {piece.name}. Pieces are used as published: move "
                f"the change into a caller, then delete {files} and run "
                f"`apply --item {piece.name}` to restore it")
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
            # A retired piece is the v1 layout, layout_items' to report (D33).
            if (markers and markers[0].asset not in pieces
                    and markers[0].asset not in RETIRED and markers[0].asset != LIBRARY):
                first = markers[0]
                items.append(Item(
                    "pieces", first.asset, "unknown",
                    f"{path.relative_to(root).as_posix()} carries `repo-infra: {first.asset} "
                    f"v{first.version}` and repo-infra ships no such piece. A file of the "
                    "assembled standard (ci, release-build, release-publish) is a caller "
                    "now: rewrite it from references/onboarding.md"))
    return items


def layout_items(repo_root, pieces):
    """The files of the v1 layout (D30) in a consumer (D33): copies of the
    pieces it now calls, the library they load from repo-infra, and the
    retired pieces."""
    root = pathlib.Path(repo_root)
    items = []
    for name, piece in sorted(pieces.items()):
        if piece.remote and (root / piece.target).is_file():
            items.append(Item("pieces", name, "outdated",
                              f"{piece.target} is a copy (v1 layout); repositories call "
                              f"{piece.uses}. Run apply to migrate (D33)"))
    if (root / ".github/workflows/lib").is_dir():
        items.append(Item("pieces", LIBRARY, "outdated",
                          ".github/workflows/lib/ is a copy of the library (v1 layout); the "
                          "pieces load it from repo-infra. Run apply to migrate (D33)"))
    for name, path in RETIRED.items():
        target = root / path
        if not target.is_file():
            continue
        markers = parse_markers(target.read_text(encoding="utf-8", errors="replace"))
        # changelog.yml and release-pr.yml are callers in v2 and carry no
        # marker; ri-ci-lib.yml has no v2 form at all.
        if name == "ri-ci-lib" or (markers and markers[0].asset == name):
            fate = ("repositories no longer test a library of their own"
                    if name == "ri-ci-lib" else "it is a caller now")
            items.append(Item("pieces", name, "outdated",
                              f"{path} is the v1 {name} piece; {fate}. Run apply to "
                              "migrate (D33)"))
    return items


def core_call_items(docs, pieces):
    """A core remote piece is used by calling it (D33). Before D33 an absent
    core piece read missing and apply installed it."""
    return [Item("pieces", name, "missing",
                 f"no workflow calls it; every repository calls {piece.uses} "
                 "(see its Call: in the catalogue)")
            for name, piece in sorted(pieces.items())
            if piece.remote and piece.core
            and not callers.calls(docs, pathlib.PurePosixPath(piece.target).name)]


def piece_items(repo_root, pieces, published):
    states = {name: piece_state(repo_root, piece, published.get(name, {}))
              for name, piece in pieces.items() if not piece.remote}
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
            items.append(Item("pieces", name, "edited", edited_detail(piece, state)))
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


def _reasons(value):
    """True for an object whose every value is a non-empty reason (D32)."""
    return isinstance(value, dict) and all(
        isinstance(reason, str) and reason.strip() for reason in value.values())


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
               if key not in KEYS and key not in OBSOLETE and key not in RENAMED
               and not key.startswith("_")]
    if strange:
        items.append(Item("config", "repo-infra.json", "problem",
                          f"{', '.join(strange)}: not a key repo-infra reads"))
    if "skip" in config:
        items.append(Item("config", "skip", "problem",
                          "skip is now exceptions (D32): rename the key, and rewrite each "
                          "of its keys as a rule id of references/project-shape.md with "
                          "the reason the rule does not apply"))
    if "exceptions" in config and not _reasons(config["exceptions"]):
        items.append(Item("config", "exceptions", "problem",
                          "exceptions must be an object that maps each rule id of "
                          "references/project-shape.md to a non-empty reason"))
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


# A step's `uses:` on a line of its own; a commented-out line does not match.
_ACTION = re.compile(r"^[ \t]*(?:-[ \t]+)?uses:[ \t]*['\"]?([^\s'\"#]+)", re.MULTILINE)
# A major tag or version: v4, v4.2, v4.2.1. A SHA or a branch is no major.
_MAJOR = re.compile(r"^v(\d+)(?:\.\d+){0,2}$")


def action_pins(text):
    """[(owner/repo in lower case, as written, major)] for each action the
    workflow `text` pins at a major. Local actions, docker:// images and
    reusable workflow calls are no action pins."""
    found = []
    for uses in _ACTION.findall(text):
        name, at, ref = uses.rpartition("@")
        major = _MAJOR.match(ref)
        if (not at or not major or name.startswith(("./", "docker://"))
                or "/.github/workflows/" in f"/{name}"):
            continue
        action = "/".join(name.split("/")[:2])
        found.append((action.lower(), action, int(major[1])))
    return found


def action_pin_items(repo_root, pieces):
    """A repository-owned workflow that pins an action at an older major than
    the pieces or another workflow of the repository do (#59). Dependabot
    updates one action to one version in every workflow, and the update it
    opens for the old pin downgrades the files already past that version. In
    v2 dependabot never sees the pieces, so the downgrade happens between the
    repository's own files; the pieces' pins are a floor besides."""
    piece_files = {path for piece in pieces.values() for path in piece.files}
    # {action: (major, where)}; the pieces win a tie, then the first file.
    newest = {}
    for path, text in (item for piece in pieces.values() for item in piece.files.items()):
        if path.startswith(f"{callers.WORKFLOWS}/") and path.endswith((".yml", ".yaml")):
            for key, _, major in action_pins(text):
                if major > newest.get(key, (0,))[0]:
                    newest[key] = (major, "repo-infra's workflows pin")
    folder = pathlib.Path(repo_root) / callers.WORKFLOWS
    if not folder.is_dir():
        return []
    owned = [(path.name, action_pins(path.read_text(encoding="utf-8", errors="replace")))
             for path in sorted(folder.iterdir())
             if path.is_file() and path.suffix in (".yml", ".yaml")
             and f"{callers.WORKFLOWS}/{path.name}" not in piece_files]
    for name, found in owned:
        for key, _, major in found:
            if major > newest.get(key, (0,))[0]:
                newest[key] = (major, f"{name} pins")
    items = []
    for name, found in owned:
        oldest = {}
        for key, action, major in found:
            if major < newest[key][0] and major < oldest.get(key, (None, major + 1))[1]:
                oldest[key] = (action, major)
        for key, (action, major) in sorted(oldest.items()):
            want, where = newest[key]
            items.append(Item(
                "callers", name, "outdated",
                f"{name} pins {action}@v{major} and {where} v{want}. Dependabot moves an "
                "action to one version in every workflow, so its update from "
                f"v{major} can downgrade the files already past it. Pin v{want}"))
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
    home = is_home(repo_root)
    return (piece_items(repo_root, pieces, load_published(assets))
            + ([] if home else layout_items(repo_root, pieces))
            + core_call_items(docs, pieces)
            + callers.validate(docs, pieces, assets, home=home)
            + config_items(repo_root, docs)
            + path_filter_items(docs)
            + action_pin_items(repo_root, pieces)
            + classify_remote(facts))
