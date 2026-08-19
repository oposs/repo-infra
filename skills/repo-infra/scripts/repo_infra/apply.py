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

MERGE_DIR = pathlib.Path(".git/repo-infra/merge")


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
            text = _git(plugin_root, "show", f"{revision}:{asset_path}")
        except ApplyError:
            continue
        found = parse_markers(text)
        if found and found[0].version == version:
            return text
    return None


def _target_for(name, rendered):
    for path, text in rendered.items():
        if any(m.asset == name for m in parse_markers(text)):
            return path, text
    raise ApplyError(f"{name}: no rendered file carries that asset")


def _scratch_dir(repo_root):
    return pathlib.Path(repo_root) / MERGE_DIR


def apply_file_item(repo_root, name, rendered, items, plugin_root, merged=None):
    state = next((i.state for i in items if i.name == name), None)
    if state is None:
        raise ApplyError(f"{name}: not in the report")
    if state == "ok":
        return []
    if state == "conflict":
        detail = next(i.detail for i in items if i.name == name)
        raise ApplyError(f"{name}: conflict — {detail}. This is a migration, not an upgrade.")

    path, expected = _target_for(name, rendered)
    wanted = next(m.version for m in parse_markers(expected) if m.asset == name)

    if merged is not None:
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
        return [write_asset(repo_root, path, text)]

    if state == "missing":
        return [write_asset(repo_root, path, expected)]

    # outdated
    installed = (pathlib.Path(repo_root) / path).read_text(encoding="utf-8")
    have = next(m.version for m in parse_markers(installed) if m.asset == name)
    source = _asset_source(plugin_root, name)
    base = base_version_of(plugin_root, source, have) if source else None
    if base is not None and base == installed:
        return [write_asset(repo_root, path, expected)]

    scratch = _scratch_dir(repo_root)
    scratch.mkdir(parents=True, exist_ok=True)
    new_path = scratch / f"{name}.new"
    new_path.write_text(expected, encoding="utf-8")
    base_path = scratch / f"{name}.base"
    base_path.write_text(base if base is not None else "", encoding="utf-8")
    # The snapshot of what is on disk right now, so a later --from can refuse
    # to overwrite a different edit that lands while the merge is prepared.
    (scratch / f"{name}.current").write_text(installed, encoding="utf-8")
    raise NeedsMerge(name, base_path, new_path, pathlib.Path(repo_root) / path)


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
    }
    for key in ("skip", "answers"):
        if key in existing:
            config[key] = existing[key]
    if answers:
        config.setdefault("answers", {}).update(answers)

    body = json.dumps(config, indent=2) + "\n"
    return write_asset(repo_root, CONFIG, body)
