"""Command line entry point: `python3 -m repo_infra check|apply`."""

import argparse
import json
import pathlib

from . import migrate, report
from .apply import ApplyError, apply_admin_item, apply_file_item, commit_item, ensure_branch
from .assemble import render_all
from .detect import Detection
from .remote import Facts, Gh
from .state import (
    NEEDS_ATTENTION_STATES,
    classify,
    classify_ambiguities,
    classify_contracts,
)

ASSETS = pathlib.Path(__file__).resolve().parents[2] / "assets"

# Administration items write repository settings through `remote.Gh` rather
# than files, so they route to apply_admin_item instead of apply_file_item.
ADMIN = {"default-branch", "branch-protection", "required-checks",
         "no-changelog-label", "actions-open-pr"}

# branch-protection and required-checks are two facts read off the *same*
# ruleset (remote.py derives both from whichever ruleset protects the default
# branch), so on a totally unconfigured repository both come back "missing"
# together. Installing the ruleset once satisfies both -- collapsing them here
# is what stops the default (--item-less) run from POSTing it twice.
_RULESET_ALIASES = {"branch-protection", "required-checks"}
_ADMIN_ORDER = {"no-changelog-label": 0, "actions-open-pr": 1}

# Used by the tests to run `check` without a network. Never used at runtime.
CONFORMING_FACTS = Facts(default_branch="main", protected=True,
                         required_contexts={"ci-passed", "changelog-updated"},
                         labels={"no-changelog"}, workflow_permissions="write",
                         can_approve_pr=True, strict=True)


def read_facts(repo):
    return Gh().facts(repo)


def _config(root):
    """The repository's recorded decisions, or {} for an unconverted one."""
    config = pathlib.Path(root) / ".github/repo-infra.json"
    if not config.is_file():
        return {}
    return json.loads(config.read_text(encoding="utf-8"))


def _prepare(root):
    """Everything `check` and `apply` read, rendered from the migrated config (D28).

    Detection cannot answer what a repository publishes, builds or runs of its
    own; those are decisions it recorded in its config (D12, D16, D22, A1). An
    unconverted repository has no config file and has chosen nothing.
    """
    manifest = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
    detection = Detection.load(ASSETS / "detection.json")
    result = detection.detect(root)
    config, migrations = migrate.migrated_config(root, _config(root), result, manifest)
    ci = config.get("ci", [])
    rendered = render_all(ASSETS, result, manifest,
                          config.get("publish", []), config.get("build", []),
                          ci, config.get("publish_local", []),
                          ci_local=bool(config.get("ci_local")),
                          release_build=config.get("release_build", []),
                          release_build_local=bool(config.get("release_build_local")))
    result.candidates = detection.open_candidates(result.candidates, ci)
    return manifest, result, rendered, config, migrations


def _load(root):
    return _prepare(root)[:3]


def _blocker(root, facts, items):
    blocker = migrate.release_in_progress(root, facts)
    return blocker if blocker and migrate.touches_release_flow(items) else None


def check(args):
    manifest, result, rendered, config, migrations = _prepare(args.root)
    repo = args.repo or Gh().current_repo()
    facts = read_facts(repo)
    items = migrate.without_superseded(classify(args.root, rendered, manifest, facts),
                                       migrations) + migrations
    items += classify_ambiguities(result)
    items += classify_contracts(args.root, result, config,
                                pending_rename=migrate.renaming(migrations))
    blocker = _blocker(args.root, facts, items)
    if blocker:
        items.append(blocker)
    renderer = report.render_json if args.json else report.render_text
    print(renderer(repo, result, items))
    return 1 if any(i.state in NEEDS_ATTENTION_STATES for i in items) else 0


def _ordered_names(items):
    """Files first, then the label, then the permissions, then the ruleset.

    A required status check whose workflow does not exist blocks every pull
    request in the repository, including the one that would install the
    workflow -- so administration runs last, after the file items that put
    ci.yml and changelog.yml on the default branch. apply_admin_item refuses
    the ruleset anyway if they are not there yet, but this ordering makes
    that refusal rare rather than routine.

    default-branch never appears here: classify_remote reports it as `ok` or
    `conflict`, never `missing`/`outdated`, and apply_admin_item refuses it
    unconditionally besides (renaming is outward-facing, so it is never
    automatic) -- excluded here too, so that stays true even if that contract
    ever drifts.
    """
    names = [i.name for i in items if i.state in ("missing", "outdated")]
    files = [n for n in names if n not in ADMIN]
    admin = [n for n in names
            if n in ADMIN and n not in _RULESET_ALIASES and n != "default-branch"]
    admin.sort(key=lambda n: _ADMIN_ORDER.get(n, 2))
    if any(n in _RULESET_ALIASES for n in names):
        admin.append("required-checks")
    return files + admin


def apply_command(args):
    manifest, result, rendered, config, migrations = _prepare(args.root)
    if migrations and args.item and args.item not in migrate.NAMES:
        # Every file is rendered from the migrated config; an item committed
        # on top of the old one would ship a release flow that config does not
        # describe.
        pending = ", ".join(i.name for i in migrations)
        raise ApplyError(
            f"{args.item}: the migration to the one release flow is pending ({pending}). "
            f"Run `apply --item {migrations[0].name}` first; it applies all of them in "
            "one commit.")
    repo = args.repo or Gh().current_repo()
    facts = read_facts(repo)
    items = migrate.without_superseded(classify(args.root, rendered, manifest, facts),
                                       migrations) + migrations
    blocker = _blocker(args.root, facts, items)
    if blocker:
        raise ApplyError(f"release-in-progress: {blocker.detail}")
    plugin_root = ASSETS.parent

    ensure_branch(args.root)
    if migrations and (args.item is None or args.item in migrate.NAMES):
        # One config edit, one commit: the items are views of the same file.
        written = migrate.apply_migrations(args.root, _config(args.root), config)
        migrate.commit_migration(args.root, written)
        print("applied " + ", ".join(i.name for i in migrations))
        if args.item:
            return 0
        manifest, result, rendered, config, migrations = _prepare(args.root)
        items = classify(args.root, rendered, manifest, facts)

    names = [args.item] if args.item else _ordered_names(items)
    for name in names:
        if name in ADMIN:
            print(apply_admin_item(Gh(), repo, name, facts, ASSETS, args.root))
            continue
        written = apply_file_item(args.root, name, rendered, items, plugin_root,
                                  merged=args.from_file)
        commit_item(args.root, name, written)
        print(f"applied {name}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="repo-infra")
    sub = parser.add_subparsers(dest="command", required=True)

    checker = sub.add_parser("check", help="report drift; never writes")
    checker.add_argument("--repo", help="owner/name; defaults to the current checkout")
    checker.add_argument("--root", default=".", help="repository root")
    checker.add_argument("--json", action="store_true")
    checker.set_defaults(run=check)

    applier = sub.add_parser("apply", help="install the standard; writes on a branch")
    applier.add_argument("--repo")
    applier.add_argument("--root", default=".")
    applier.add_argument("--item", help="apply one item; default is every actionable file item")
    applier.add_argument("--from", dest="from_file", help="take the merged file from here")
    applier.set_defaults(run=apply_command)

    args = parser.parse_args(argv)
    return args.run(args)
