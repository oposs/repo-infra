"""Write the standard into a repository.

Everything mechanical is scripted and every write is read back and asserted --
the pattern that exists because `|| true` once swallowed a failed version bump
and shipped a tag whose Cargo.toml and Cargo.lock disagreed.

There is exactly one thing this module refuses to do. Merging a new asset
generation into a file that carries local edits is judgement, not mechanism, so
it writes the three versions out and raises NeedsMerge. The model merges; the
script keeps the irreversible half.
"""

import json
import pathlib
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
    def __init__(self, name, base, new, current):
        super().__init__(
            f"{name}: local edits present; merge {base} and {new} over {current}, "
            "then re-run with --from")
        self.name, self.base, self.new, self.current = name, base, new, current


def write_asset(repo_root, path, content):
    target = pathlib.Path(repo_root) / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    if target.read_text(encoding="utf-8") != content:
        raise ApplyError(f"{path}: wrote the file and read back something else")
    return path


def _git(cwd, *args):
    result = subprocess.run(("git",) + args, cwd=str(cwd), capture_output=True, text=True)
    if result.returncode != 0:
        raise ApplyError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _asset_source(plugin_root, name):
    """Where `name` lives inside the plugin checkout, found by its own marker.

    Deriving this from the marker rather than from the manifest keeps the
    lookup correct for the assembled ci.yml, whose frame lives in
    assets/ci/ci-frame.yml and has no target of its own.
    """
    assets = pathlib.Path(plugin_root) / "assets"
    if not assets.is_dir():
        return None
    for path in sorted(assets.rglob("*")):
        if not path.is_file():
            continue
        found = parse_markers(path.read_text(encoding="utf-8", errors="ignore"))
        if found and found[0].asset == name:
            return str(path.relative_to(plugin_root))
    return None


def base_version_of(plugin_root, asset_path, version):
    """The asset as it was at `version`, from the plugin's own git history.

    Returns None when the plugin is not a git checkout, or when that generation
    is not in the history -- in which case the merge proceeds without a base
    rather than failing.
    """
    try:
        revisions = _git(plugin_root, "log", "--format=%H", "--", asset_path).split()
    except ApplyError:
        return None
    for revision in revisions:
        try:
            # `git show rev:path` resolves `path` from the repository root, not
            # from cwd -- the leading `./` is what tells git to resolve it
            # relative to `plugin_root` instead, which is a subdirectory of the
            # real plugin checkout (`skills/repo-infra`), never its root.
            text = _git(plugin_root, "show", f"{revision}:./{asset_path}")
        except ApplyError:
            continue
        found = parse_markers(text)
        if found and found[0].version == version:
            return text
    return None


def _targets_for(name, rendered):
    """Every rendered path carrying this asset's marker, not just the first.

    A directory asset ships one marker copied into each of its files, so
    `workflow-lib` names nine paths under one item. Returning the first is how
    `apply --item workflow-lib` came to install `bump.js` alone and leave the
    next `check` reporting `files disagree` on a conversion that had just
    succeeded -- silently, because one written file is indistinguishable from
    nine at the moment of writing.
    """
    targets = sorted((path, text) for path, text in rendered.items()
                     if any(m.asset == name for m in parse_markers(text)))
    if not targets:
        raise ApplyError(f"{name}: no rendered file carries that asset")
    return targets


def _git_dir(repo_root):
    """The git dir, read without running git so a bare `.git/` in a test
    still counts. In a linked worktree `.git` is a file saying
    `gitdir: <path>`, and writing below it fails with NotADirectoryError."""
    dot_git = pathlib.Path(repo_root) / ".git"
    if dot_git.is_file():
        line = dot_git.read_text(encoding="utf-8").strip()
        if not line.startswith("gitdir:"):
            raise ApplyError(f"{dot_git}: not a gitdir pointer")
        return (pathlib.Path(repo_root) / line[len("gitdir:"):].strip()).resolve()
    return dot_git


def _scratch_dir(repo_root):
    return _git_dir(repo_root) / MERGE_DIR


def apply_file_item(repo_root, name, rendered, items, plugin_root, merged=None):
    state = next((i.state for i in items if i.name == name), None)
    if state is None:
        raise ApplyError(f"{name}: not in the report")
    if state == "ok":
        return []
    if state == "conflict":
        detail = next(i.detail for i in items if i.name == name)
        raise ApplyError(f"{name}: conflict: {detail}. This is a migration, not an upgrade.")

    targets = _targets_for(name, rendered)
    path, expected = targets[0]
    wanted = next(m.version for m in parse_markers(expected) if m.asset == name)

    if merged is not None:
        # A directory asset merges one file at a time; the refusal recorded
        # which one (`{name}.path`). A single-file asset has only one choice.
        recorded = _scratch_dir(repo_root) / f"{name}.path"
        if recorded.is_file():
            path = recorded.read_text(encoding="utf-8").strip()
            if path not in dict(targets):
                raise ApplyError(f"{name}: the prepared merge names {path}, which "
                                 "this asset no longer ships; redo the merge")
        elif len(targets) > 1:
            raise ApplyError(f"{name}: no merge is in progress; run "
                             f"`apply --item {name}` first to prepare one")
        # The refusal that raised NeedsMerge recorded what was on disk at the
        # time (`{name}.current`). Requiring that snapshot to still match
        # before writing is what stops a merge prepared against one version
        # of the file from being replayed over a different, newer edit --
        # the two guard different mistakes, not the same one twice: this one
        # catches staleness, the version check below catches a wrong merge.
        snapshot_path = _scratch_dir(repo_root) / f"{name}.current"
        if not snapshot_path.is_file():
            raise ApplyError(f"{name}: no merge is in progress; run "
                             f"`apply --item {name}` first to prepare one")
        snapshot = snapshot_path.read_text(encoding="utf-8")
        target = pathlib.Path(repo_root) / path
        current = target.read_text(encoding="utf-8") if target.is_file() else None
        if current != snapshot:
            raise ApplyError(f"{path}: changed since the merge was prepared; "
                             "redo the merge against the current file")

        text = pathlib.Path(merged).read_text(encoding="utf-8")
        got = next((m.version for m in parse_markers(text) if m.asset == name), None)
        if got != wanted:
            raise ApplyError(f"{name}: the merged file says v{got}, the asset is v{wanted}")
        written = [write_asset(repo_root, path, text)]
        # The staleness guard above fails closed even on a stale snapshot, so
        # leaving these behind is untidy rather than unsafe -- but a finished
        # merge has nothing left to guard, so clear this item's own scratch
        # files. Other items may still have a merge in progress, so only
        # `name`'s own files go, never the whole directory.
        for suffix in ("base", "new", "current", "path"):
            (_scratch_dir(repo_root) / f"{name}.{suffix}").unlink(missing_ok=True)
        return written

    if len(targets) > 1:
        return _apply_dir_asset(repo_root, name, targets, wanted, plugin_root)

    if state == "missing":
        return [write_asset(repo_root, path, expected)]

    # outdated
    installed = (pathlib.Path(repo_root) / path).read_text(encoding="utf-8")
    found = parse_markers(installed)
    source = _asset_source(plugin_root, found[0].asset)
    base = base_version_of(plugin_root, source, found[0].version) if source else None
    if base is not None and base == installed:
        return [write_asset(repo_root, path, expected)]

    _prepare_merge(repo_root, name, path, base, expected, installed)


def _prepare_merge(repo_root, name, path, base, expected, installed):
    scratch = _scratch_dir(repo_root)
    scratch.mkdir(parents=True, exist_ok=True)
    new_path = scratch / f"{name}.new"
    new_path.write_text(expected, encoding="utf-8")
    base_path = scratch / f"{name}.base"
    base_path.write_text(base if base is not None else "", encoding="utf-8")
    # The snapshot of what is on disk right now, so a later --from can refuse
    # to overwrite a different edit that lands while the merge is prepared.
    (scratch / f"{name}.current").write_text(installed, encoding="utf-8")
    # Which file the merge is for, so --from writes it back to that file even
    # when the asset ships several.
    (scratch / f"{name}.path").write_text(path + "\n", encoding="utf-8")
    raise NeedsMerge(name, base_path, new_path, pathlib.Path(repo_root) / path)


def _dir_sources(plugin_root, name, targets):
    """Each target's source inside the plugin, by its path below the asset root.

    The manifest versions a directory asset as one unit, but every file has a
    history of its own. Looking a file's base up under a sibling's path (the
    first file carrying the marker) compares it against the wrong history.
    """
    assets = pathlib.Path(plugin_root) / "assets"
    sources = []
    if assets.is_dir():
        sources = sorted(
            p for p in assets.rglob("*") if p.is_file()
            and any(m.asset == name for m in parse_markers(
                p.read_text(encoding="utf-8", errors="ignore"))))
    if not sources:
        return {}
    source_root = pathlib.Path(*_common_parts([p.parts for p in sources]))
    target_root = pathlib.PurePosixPath(
        *_common_parts([pathlib.PurePosixPath(t).parts for t, _ in targets]))
    return {target: str((source_root / pathlib.PurePosixPath(target).relative_to(target_root))
                        .relative_to(plugin_root))
            for target, _ in targets}


def _common_parts(all_parts):
    common = []
    # Paths of different depth are expected; the common prefix is the shorter.
    for parts in zip(*[p[:-1] for p in all_parts], strict=False):
        if len(set(parts)) != 1:
            break
        common.append(parts[0])
    return common


def _apply_dir_asset(repo_root, name, targets, wanted, plugin_root):
    """Install or upgrade a directory asset one file at a time.

    A missing file is written. A file at the current generation is left alone,
    local edits included. A file at an older generation is overwritten only
    when it is byte for byte that generation from the plugin's own history.
    One edited file stops the whole run before anything is written, so a
    refusal never leaves a half-upgraded directory behind it.
    """
    sources = _dir_sources(plugin_root, name, targets)
    to_write = []
    for path, expected in targets:
        target = pathlib.Path(repo_root) / path
        if not target.is_file():
            to_write.append((path, expected))
            continue
        installed = target.read_text(encoding="utf-8")
        have = next((m.version for m in parse_markers(installed) if m.asset == name), None)
        if have == wanted:
            continue
        source = sources.get(path)
        base = base_version_of(plugin_root, source, have) if source and have else None
        if base is not None and base == installed:
            to_write.append((path, expected))
            continue
        _prepare_merge(repo_root, name, path, base, expected, installed)
    return [write_asset(repo_root, path, text) for path, text in to_write]


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


def ensure_branch(repo_root):
    current = _git(repo_root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    if current == BRANCH:
        return BRANCH
    existing = _git(repo_root, "branch", "--list", BRANCH).strip()
    _git(repo_root, "checkout", BRANCH) if existing else _git(repo_root, "checkout", "-b", BRANCH)
    return BRANCH


def commit_item(repo_root, name, paths):
    """One commit per item, so any single item can be dropped at review."""
    if not paths:
        return None
    _git(repo_root, "add", *paths)
    _git(repo_root, "commit", "-m",
         f"Install {name} from the repo-infra standard\n\n"
         "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>")
    return _git(repo_root, "rev-parse", "HEAD").strip()


CONFIG = ".github/repo-infra.json"


def write_config(repo_root, result, answers=None):
    """Write .github/repo-infra.json, preserving anything already answered.

    An existing file wins on every key it sets: it records answers to
    ambiguities and deliberate `skip` decisions, and re-detecting must not
    discard them. That file is the only way to record a considered "no", and
    without it the checker nags about the same item forever.
    """
    existing = {}
    target = pathlib.Path(repo_root) / CONFIG
    if target.is_file():
        existing = json.loads(target.read_text(encoding="utf-8"))

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

    body = json.dumps(config, indent=2) + "\n"
    return write_asset(repo_root, CONFIG, body)
