"""Command line entry point: `python3 -m repo_infra check|apply`."""

import argparse
import json
import pathlib

from . import report
from .apply import apply_admin_item, apply_file_item, commit_item, ensure_branch
from .assemble import render_all
from .detect import Detection
from .remote import Facts, Gh
from .state import NEEDS_ATTENTION_STATES, classify, classify_ambiguities

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
                         can_approve_pr=True)


def read_facts(repo):
    return Gh().facts(repo)


def _load(root):
    manifest = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
    result = Detection.load(ASSETS / "detection.json").detect(root)
    return manifest, result, render_all(ASSETS, result, manifest)


def check(args):
    manifest, result, rendered = _load(args.root)
    repo = args.repo or Gh().current_repo()
    items = classify(args.root, rendered, manifest, read_facts(repo))
    items += classify_ambiguities(result)
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
    manifest, result, rendered = _load(args.root)
    repo = args.repo or Gh().current_repo()
    facts = read_facts(repo)
    items = classify(args.root, rendered, manifest, facts)
    plugin_root = ASSETS.parent

    names = [args.item] if args.item else _ordered_names(items)
    ensure_branch(args.root)
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
