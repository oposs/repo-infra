"""Write the standard into a repository.

Everything mechanical is scripted and every write is read back and asserted --
the pattern that exists because `|| true` once swallowed a failed version bump
and shipped a tag whose Cargo.toml and Cargo.lock disagreed.

There is exactly one thing this module refuses to do. A piece whose bytes match no
published version (D30: `edited`) carries local edits, and merging a new version
into those is judgement, not mechanism. It writes the new version, the current
file and the file's git log out and raises NeedsMerge. The model merges; the
script keeps the irreversible half.
"""

import hashlib
import json
import pathlib
import re
import subprocess

from .markers import parse_markers
from .remote import protects_default_branch

# Below the repository's git dir, which is `.git/` in a plain clone and
# `.git/worktrees/<name>/` of the main checkout in a linked worktree.
MERGE_DIR = pathlib.Path("repo-infra/merge")

# Reported as `conflict` by state.py when absent; required here so the ruleset
# is never enabled before the checks it requires can actually report.
REQUIRED_WORKFLOWS = (".github/workflows/ci.yml", ".github/workflows/changelog.yml")

# What the ruleset POST must read back as required -- state.py's
# classify_remote wants the same two contexts, kept here rather than shared
# because that module has no reason to import apply.py's write path.
REQUIRED_CONTEXTS = {"ci-passed", "changelog-updated"}


class ApplyError(Exception):
    """Refused. The message says what a human has to decide."""


class NeedsMerge(Exception):
    def __init__(self, name, new, current, log, target):
        super().__init__(
            f"{name}: {target} matches no published version of the piece. "
            f"Read {current}, {new} and the file's history in {log}, "
            f"merge, then re-run with --item {name} --from <merged file>")
        self.name, self.new, self.current, self.log, self.target = (
            name, new, current, log, target)


def write_asset(repo_root, path, content):
    target = pathlib.Path(repo_root) / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    if target.read_text(encoding="utf-8") != content:
        raise ApplyError(f"{path}: wrote the file and read back something else")
    return path


def git(cwd, *args):
    result = subprocess.run(("git",) + args, cwd=str(cwd), capture_output=True, text=True)
    if result.returncode != 0:
        # `git commit` says "nothing to commit" on stdout and nothing on stderr.
        said = "\n".join(t for t in (result.stderr.strip(), result.stdout.strip()) if t)
        raise ApplyError(f"git {' '.join(args)} failed: {said}")
    return result.stdout


def _git_dir(repo_root):
    """The git dir, read without running git so a bare `.git/` in a test
    still counts. In a linked worktree `.git` is a file saying
    `gitdir: <path>`, and writing below it fails with NotADirectoryError.

    Absolute, because `git` runs with the root as its working directory: a
    relative `--root` would otherwise name the root twice."""
    root = pathlib.Path(repo_root).resolve()
    dot_git = root / ".git"
    if dot_git.is_file():
        line = dot_git.read_text(encoding="utf-8").strip()
        if not line.startswith("gitdir:"):
            raise ApplyError(f"{dot_git}: not a gitdir pointer")
        return (root / line[len("gitdir:"):].strip()).resolve()
    return dot_git


def _read_raw(path):
    """The file with its line endings as they are: a CRLF checkout must be
    compared and snapshotted as CRLF, or the hand-back guard would see an LF
    file that is not on disk."""
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def _scratch_dir(repo_root):
    return _git_dir(repo_root) / MERGE_DIR


def changed(repo_root, paths):
    """The paths among `paths` whose content differs from the last commit.

    A block of an assembled file finds its file already written by the item
    before it; writing the rendering again changes nothing, and `git commit`
    would fail with "nothing to commit".
    """
    if not paths:
        return []
    # -z: a path with a space or a quote is written as is, not quoted.
    entries = iter(git(repo_root, "status", "--porcelain", "-z", "--untracked-files=all",
                       "--", *paths).split("\0"))
    dirty = set()
    for entry in entries:
        if not entry:
            continue
        dirty.add(entry[3:])
        if entry[0] in "RC":
            next(entries, None)  # the path it was renamed or copied from
    return [p for p in paths if p in dirty]


def _prepare_merge(repo_root, name, path, expected, installed):
    scratch = _scratch_dir(repo_root)
    scratch.mkdir(parents=True, exist_ok=True)
    new_path = scratch / f"{name}.new"
    new_path.write_text(expected, encoding="utf-8")
    # The snapshot of what is on disk right now, so a later --from can refuse
    # to overwrite a different edit that lands while the merge is prepared.
    current_path = scratch / f"{name}.current"
    current_path.write_text(installed, encoding="utf-8")
    # Which file the merge is for, so --from writes it back to that file even
    # when the asset ships several.
    (scratch / f"{name}.path").write_text(path + "\n", encoding="utf-8")
    # The history tells an edit from an older generation: a file only apply
    # commits touched has no local edits (commands/apply.md). --git-dir keeps
    # git from walking up out of a repository it cannot read into an enclosing
    # one and answering with the wrong history.
    try:
        log = git(repo_root, f"--git-dir={_git_dir(repo_root)}", "log",
                  "--format=%h %ad %s", "--date=short", "--", path)
        if not log:
            log = f"(no history: no commit touches {path})\n"
    except ApplyError as error:
        log = f"(no history: {error})\n"
    log_path = scratch / f"{name}.log"
    log_path.write_text(log, encoding="utf-8")
    raise NeedsMerge(name, new_path, current_path, log_path, pathlib.Path(repo_root) / path)


def install_piece(repo_root, piece, state, history, merged=None):
    """Write `piece` at its current version; return the paths written or removed.

    A file an older version shipped and this one does not is removed when its
    bytes are a published version; an edited one stays for the human (see
    `kept_edits`). When the piece is edited, the merge is prepared for an
    edited file the new version ships; edited files it dropped cannot be
    merged into anything."""
    if merged is not None:
        return [_hand_back(repo_root, piece, merged)]
    root = pathlib.Path(repo_root)
    shipped = [path for path in state.edited if path in piece.files]
    if shipped:
        _prepare_merge(repo_root, piece.name, shipped[0], piece.files[shipped[0]],
                       _read_raw(root / shipped[0]))
    written = [write_asset(repo_root, path, text) for path, text in sorted(piece.files.items())]
    for path, versions in sorted(history.items()):
        target = root / path
        if path not in piece.files and target.is_file():
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            if digest in versions.values():
                target.unlink()
                written.append(path)
    return written


def kept_edits(piece, state):
    """The edited files the new version no longer ships. install_piece leaves
    them where they are, and the caller says so."""
    return [path for path in state.edited if path not in piece.files]


def _hand_back(repo_root, piece, merged):
    """The merged file from --from, written where the refusal recorded."""
    scratch = _scratch_dir(repo_root)
    recorded = scratch / f"{piece.name}.path"
    snapshot = scratch / f"{piece.name}.current"
    if not recorded.is_file() or not snapshot.is_file():
        raise ApplyError(f"{piece.name}: no merge is in progress; run "
                         f"`apply --item {piece.name}` first to prepare one")
    path = recorded.read_text(encoding="utf-8").strip()
    if path not in piece.files:
        raise ApplyError(f"{piece.name}: the prepared merge names {path}, which this piece "
                         "no longer ships; redo the merge")
    target = pathlib.Path(repo_root) / path
    current = _read_raw(target) if target.is_file() else None
    if current != snapshot.read_text(encoding="utf-8"):
        raise ApplyError(f"{path}: changed since the merge was prepared; redo the merge "
                         "against the current file")
    text = pathlib.Path(merged).read_text(encoding="utf-8")
    got = next((m.version for m in parse_markers(text) if m.asset == piece.name), None)
    if got != piece.version:
        raise ApplyError(f"{piece.name}: the merged file says v{got}, the piece is "
                         f"v{piece.version}")
    write_asset(repo_root, path, text)
    for suffix in ("new", "current", "path", "log"):
        (scratch / f"{piece.name}.{suffix}").unlink(missing_ok=True)
    return path


def commit_piece(repo_root, name, version, paths, merged=False):
    """One commit per piece, so any single piece can be dropped at review. A
    merge with local edits says so: the next NeedsMerge hands the model the
    file's log, and an Install commit there means "no local edits"."""
    subject = (f"Merge {name} v{version} from the repo-infra standard with local edits"
               if merged else f"Install {name} v{version} from the repo-infra standard")
    git(repo_root, "add", "--all", "--", *paths)
    git(repo_root, "commit", "-m", f"{subject}\n\n{TRAILER}")
    return git(repo_root, "rev-parse", "HEAD").strip()


_RELEASE = re.compile(r"^## (\d+\.\d+\.\d+) - \d{4}-\d{2}-\d{2}\s*$")


def latest_release(text):
    for line in text.splitlines():
        match = _RELEASE.match(line)
        if match:
            return match.group(1)
    return None


def release_in_progress(repo_root, facts):
    """Why a piece cannot be installed right now, or None.

    The release flow's pieces call each other, so replacing one while a
    release started by the old copies is under way could leave it with
    neither a draft nor the build record the new copy expects."""
    if facts.release_prs:
        number, branch = facts.release_prs[0]
        return (f"release pull request #{number} ({branch}) is open. Merge or close it and "
                "let its publish finish, then run apply: a new piece cannot finish a "
                "release the old one started.")
    changes = pathlib.Path(repo_root) / "CHANGES.md"
    latest = latest_release(changes.read_text(encoding="utf-8")) if changes.is_file() else None
    if latest and facts.tags is not None and f"v{latest}" not in facts.tags:
        return (f"v{latest} is in CHANGES.md but has no tag: its publish has not finished. "
                "Finish or abandon that release, then run apply.")
    return None


def apply_admin_item(gh, repo, name, facts, assets_root, repo_root):
    """Write one repository-administration setting and read it back.

    Unlike a file item, there is no local copy to compare against -- the only
    evidence a write took is asking GitHub again, which is why every branch
    here ends with a read and an assertion (module docstring).
    """
    if name == "default-branch":
        raise ApplyError(
            f"default-branch: rename '{facts.default_branch}' to 'main' by hand "
            "(repository Settings -> General -> Default branch), then re-run "
            "`check` so it picks up the new default branch. Renaming is "
            "outward-facing -- it breaks links, forks and clones that pin the "
            "old name -- so it is never automatic.")

    if name == "no-changelog-label":
        gh.run(["gh", "api", "--method", "POST", f"repos/{repo}/labels",
                "-f", "name=no-changelog",
                "-f", "description=This pull request deliberately adds no changelog entry",
                "-f", "color=ededed"])
        # `gh label create` prints nothing on success, which looks exactly like
        # a silent failure, and Dependabot ignores a label that does not exist
        # without saying so. Read it back.
        labels = {entry["name"]
                 for entry in json.loads(gh.run(["gh", "api", f"repos/{repo}/labels"]))}
        if "no-changelog" not in labels:
            raise ApplyError(
                f"no-changelog-label: created it but could not read back the "
                f"label list from repos/{repo}/labels; check the label by hand "
                "before retrying.")
        return "created the no-changelog label"

    if name == "actions-open-pr":
        gh.run(["gh", "api", "--method", "PUT",
                f"repos/{repo}/actions/permissions/workflow",
                "-f", "default_workflow_permissions=write",
                "-F", "can_approve_pull_request_reviews=true"])
        after = json.loads(
            gh.run(["gh", "api", f"repos/{repo}/actions/permissions/workflow"]))
        if not (after["can_approve_pull_request_reviews"]
                and after["default_workflow_permissions"] == "write"):
            raise ApplyError(
                f"actions-open-pr: wrote the setting and read back {after!r}. "
                "An organisation policy may be overriding it -- check "
                "Settings -> Actions -> General at the organisation level, "
                "then retry.")
        return "allowed Actions to create and approve pull requests"

    if name in ("required-checks", "branch-protection"):
        # Both names describe facts about the same ruleset -- an unprotected
        # default branch always reads as both missing at once -- so they share
        # one refusal and one write.
        if facts.default_branch != "main":
            raise ApplyError(
                f"{name}: the default branch is '{facts.default_branch}'. The "
                "ruleset targets the default branch while the shipped "
                "workflows filter on 'main', so enabling it now would leave "
                "every required check pending forever. Rename the default "
                "branch to 'main' by hand first (see the default-branch "
                "item), re-run `check` to confirm, then apply this item "
                "again.")
        # Asked of GitHub, on the default branch itself -- never the local
        # checkout. A file item lands in `repo_root` the moment it is
        # committed, whether or not that commit has been pushed or merged;
        # checking the working tree here would let this precondition pass
        # while `main` still has neither workflow, which is exactly the
        # "required check that can never report" failure this item exists
        # to prevent.
        missing, unverified = [], []
        for workflow in REQUIRED_WORKFLOWS:
            exists = gh.path_exists_on_branch(repo, facts.default_branch, workflow)
            if exists is False:
                missing.append(workflow)
            elif exists is None:
                unverified.append(workflow)
        if unverified:
            raise ApplyError(
                f"{name}: could not confirm whether {', '.join(unverified)} "
                f"{'is' if len(unverified) == 1 else 'are'} on "
                f"'{facts.default_branch}' -- the existence check itself "
                "failed (network error, permissions, or something else on "
                f"the repos/{repo}/contents endpoint), not a clean 404. "
                "Refusing rather than guessing either way; check by hand "
                "and retry.")
        if missing:
            raise ApplyError(
                f"{name}: {', '.join(missing)} not on main yet. A required "
                "status check whose workflow does not exist blocks every "
                "pull request in the repository -- including the one that "
                "would install the workflow. Run `apply` with no --item to "
                "install the missing file items first, merge that to main, "
                "then apply this item again.")
        payload = (pathlib.Path(assets_root) / "gh/ruleset-main.json").read_text(
            encoding="utf-8")
        staged = _stage_ruleset_payload(repo_root, payload)
        # POST creates; it cannot adopt. A repository that already had a
        # ruleset of this name -- every repository whose `branch-protection`
        # reads `ok` before conversion -- got `422 Validation Failed` and no
        # required checks. Updating the one that is there is the same write,
        # aimed at the object that exists.
        existing = gh.ruleset_id(repo, json.loads(payload)["name"])
        if existing is None:
            output = gh.run(["gh", "api", "--method", "POST",
                             f"repos/{repo}/rulesets", "--input", staged])
        else:
            output = gh.run(["gh", "api", "--method", "PUT",
                             f"repos/{repo}/rulesets/{existing}", "--input", staged])
        # A ruleset POST replaces the whole object -- the server can reject,
        # rewrite or partially apply it, so "the call did not error" is not
        # evidence the branch is actually guarded. Read back what was created
        # and check it says what we asked for, not just that something exists.
        created = json.loads(output)
        if created.get("enforcement") != "active":
            raise ApplyError(
                f"{name}: created the ruleset but it read back enforcement="
                f"{created.get('enforcement')!r}, not 'active'. Check it in "
                f"Settings -> Rules -> Rulesets on repos/{repo} by hand.")
        if not protects_default_branch(created, facts.default_branch):
            raise ApplyError(
                f"{name}: created the ruleset but it read back not covering "
                f"the default branch '{facts.default_branch}' -- conditions "
                f"were {created.get('conditions')!r}. Check it in Settings -> "
                f"Rules -> Rulesets on repos/{repo} by hand.")
        contexts = {check["context"] for rule in created.get("rules", [])
                   if rule.get("type") == "required_status_checks"
                   for check in rule["parameters"]["required_status_checks"]}
        absent = REQUIRED_CONTEXTS - contexts
        if absent:
            raise ApplyError(
                f"{name}: created the ruleset but it read back without "
                f"{', '.join(sorted(absent))} in required_status_checks. The "
                f"server may have rejected or altered part of the payload -- "
                f"check it in Settings -> Rules -> Rulesets on repos/{repo} "
                "by hand.")
        strict = any(rule.get("parameters", {}).get("strict_required_status_checks_policy")
                     is True for rule in created.get("rules", [])
                     if rule.get("type") == "required_status_checks")
        if not strict:
            raise ApplyError(
                f"{name}: wrote the ruleset but it read back with "
                "strict_required_status_checks_policy off, so a pull request whose "
                "branch is behind main can still merge. Check it in Settings -> Rules "
                f"-> Rulesets on repos/{repo} by hand.")
        if created.get("bypass_actors"):
            raise ApplyError(
                f"{name}: created the ruleset but it read back with "
                f"bypass_actors={created['bypass_actors']!r}, not empty. A "
                "ruleset that grants a bypass is not the one we shipped -- "
                f"check it in Settings -> Rules -> Rulesets on repos/{repo} "
                "by hand.")
        return "enabled the branch ruleset with both required checks and up-to-date branches"

    raise ApplyError(f"{name}: not an administration item")


def _stage_ruleset_payload(repo_root, payload):
    """`gh api --input` takes a path, not a string, so the payload is staged
    under the git dir, like every other scratch file."""
    scratch = _scratch_dir(repo_root)
    scratch.mkdir(parents=True, exist_ok=True)
    target = scratch / "ruleset.json"
    target.write_text(payload, encoding="utf-8")
    return str(target)


BRANCH = "repo-infra/apply"

# Ends every commit apply makes in the target repository, one item or the
# D28 migration.
TRAILER = "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"


def ensure_branch(repo_root):
    current = git(repo_root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    if current == BRANCH:
        return BRANCH
    existing = git(repo_root, "branch", "--list", BRANCH).strip()
    git(repo_root, "checkout", BRANCH) if existing else git(repo_root, "checkout", "-b", BRANCH)
    return BRANCH


def commit_item(repo_root, name, paths, merged=False):
    """One commit per item, so any single item can be dropped at review.

    A hand merge with local edits gets its own subject: the next NeedsMerge
    hands the LLM the file's log, and an Install commit there means "no local
    edits" (D29). A merge handed back unchanged is an install.
    """
    if not paths:
        return None
    subject = (f"Merge {name} from the repo-infra standard with local edits" if merged
               else f"Install {name} from the repo-infra standard")
    git(repo_root, "add", *paths)
    git(repo_root, "commit", "-m", f"{subject}\n\n{TRAILER}")
    return git(repo_root, "rev-parse", "HEAD").strip()


CONFIG = ".github/repo-infra.json"

WIDTH = 80


def _compact(value, indent, level, prefix=0):
    unit = indent if isinstance(indent, str) else " " * indent
    if isinstance(value, (dict, list)) and value:
        items = list(value.values()) if isinstance(value, dict) else value
        one_line = json.dumps(value, separators=(", ", ": "))
        # A tab counts as the 8 columns an editor shows it as.
        if (not any(isinstance(v, (dict, list)) for v in items)
                and len(unit.expandtabs()) * level + prefix + len(one_line) + 1 <= WIDTH):
            return one_line
        inner = unit * (level + 1)
        if isinstance(value, dict):
            parts = []
            for key, item in value.items():
                head = json.dumps(key) + ": "
                parts.append(inner + head + _compact(item, indent, level + 1, len(head)))
            return "{\n" + ",\n".join(parts) + "\n" + unit * level + "}"
        parts = [inner + _compact(item, indent, level + 1) for item in value]
        return "[\n" + ",\n".join(parts) + "\n" + unit * level + "]"
    return json.dumps(value)


def config_text(data, original=None):
    """`data` as JSON in the layout of `original`, the file it replaces.

    A plain json.dumps(indent=2) rewrote every line of a repo-infra.json that
    was indented by four spaces, so the migration's one-key change showed up
    as a diff of the whole file. The indent and the final newline are read
    from the file; key order is the order of `data`.

    An array or object of scalars stays on one line when it fits in 80 columns;
    oetiker/mdmost#30 showed `"ci": ["ci-man", "ci-rust-musl"]` turned into
    four lines.
    """
    indent, newline = 2, "\n"
    if original is not None:
        newline = "\n" if original.endswith("\n") else ""
        for line in original.splitlines()[1:]:
            stripped = line.lstrip(" \t")
            if stripped and stripped != line:
                lead = line[:len(line) - len(stripped)]
                indent = lead if "\t" in lead else len(lead)
                break
    return _compact(data, indent, 0) + newline


def write_config(repo_root, result, answers=None):
    """Write .github/repo-infra.json, preserving anything already answered.

    An existing file wins on every key it sets: it records answers to
    ambiguities and deliberate `skip` decisions, and re-detecting must not
    discard them. That file is the only way to record a considered "no", and
    without it the checker nags about the same item forever.
    """
    existing = {}
    original = None
    target = pathlib.Path(repo_root) / CONFIG
    if target.is_file():
        original = target.read_text(encoding="utf-8")
        existing = json.loads(original)

    if result.ambiguities:
        answered = (answers or {}).keys() | existing.get("answers", {}).keys()
        unanswered = [a for a in result.ambiguities if a["id"] not in answered]
        if unanswered:
            raise ApplyError(f"{unanswered[0]['id']}: unresolved -- {unanswered[0]['question']}")

    config = {
        "ecosystems": result.ecosystems,
        "moving_major_tag": existing.get("moving_major_tag", False),
        "version_files": existing.get("version_files") or result.version_files,
        "publish": existing.get("publish", []),
        "build": existing.get("build", []),
    }
    # Every other key is a decision this function does not compute -- `ci`,
    # `publish_local`, `skip`, `answers`, a `_comment` -- so it is kept as
    # written. A fixed list of keys to keep dropped each new one as it was added.
    for key, value in existing.items():
        config.setdefault(key, value)
    if answers:
        config.setdefault("answers", {}).update(answers)

    return write_asset(repo_root, CONFIG, config_text(config, original))
