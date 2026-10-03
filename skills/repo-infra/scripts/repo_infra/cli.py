"""Command line entry point: `python3 -m repo_infra check|apply`."""

import argparse
import pathlib

from . import callers, report
from . import check as checking
from .apply import (
    ApplyError,
    apply_admin_item,
    changed,
    commit_piece,
    ensure_branch,
    install_piece,
    kept_edits,
    pending,
    plan_piece,
    release_in_progress,
)
from .pieces import ASSETS, load_pieces, load_published, upgrade_notes
from .remote import Facts, Gh

# Administration items write repository settings through `remote.Gh`, and
# each is outward-facing, so apply runs one only when it is named (D30).
ADMIN = {"default-branch", "branch-protection", "required-checks",
         "no-changelog-label", "actions-open-pr"}

# Used by the tests to run without a network. Never used at runtime.
CONFORMING_FACTS = Facts(default_branch="main", protected=True,
                         required_contexts={"ci-passed", "changelog-updated"},
                         labels={"no-changelog"}, workflow_permissions="write",
                         can_approve_pr=True, strict=True)


def read_facts(repo):
    return Gh().facts(repo)


def check(args):
    repo = args.repo or Gh().current_repo()
    items = checking.run(args.root, read_facts(repo), ASSETS)
    renderer = report.render_json if args.json else report.render_text
    print(renderer(repo, items))
    return 1 if any(item.state in report.ATTENTION for item in items) else 0


def _pending(root, pieces, states, published):
    """The pieces a bare apply installs: those with a file to write, a file to
    remove or a merge (merges last, so the merge stop leaves the rest
    installed), absent core pieces, and pieces an installed piece needs."""
    plans = {name: plan_piece(root, pieces[name], state, published.get(name, {}))
             for name, state in sorted(states.items()) if state.state != "absent"}
    names = [name for name, plan in plans.items() if pending(plan) and not plan.candidates]
    names += [name for name, state in sorted(states.items())
              if state.state == "absent" and pieces[name].core]
    names += [dep for dep, _ in checking.missing_dependencies(pieces, states)
              if dep not in names]
    return names + [name for name, plan in plans.items() if plan.candidates]


def _states(root, pieces, published):
    return {name: checking.piece_state(root, piece, published.get(name, {}))
            for name, piece in pieces.items()}


def apply_command(args):
    repo = args.repo or Gh().current_repo()
    facts = read_facts(repo)
    if args.item in ADMIN:
        if args.from_file:
            raise ApplyError("--from takes the merged file of a piece, not of "
                             f"the administration item {args.item}")
        print(apply_admin_item(Gh(), repo, args.item, facts, ASSETS, args.root))
        return 0
    if args.from_file and not args.item:
        raise ApplyError("--from needs --item: name the piece the merged file is for")
    pieces, published = load_pieces(ASSETS), load_published(ASSETS)
    if args.item is not None and args.item not in pieces:
        raise ApplyError(f"{args.item}: not a piece and not an administration item")
    states = _states(args.root, pieces, published)
    names = [args.item] if args.item else _pending(args.root, pieces, states, published)
    if names:
        blocker = release_in_progress(args.root, facts)
        if blocker:
            raise ApplyError(f"release-in-progress: {blocker}")
        ensure_branch(args.root)
        # The branch may carry other versions of the files than the one the
        # first look found, so what to install is decided on this one.
        states = _states(args.root, pieces, published)
        names = [args.item] if args.item else _pending(args.root, pieces, states, published)
    notes, kept = [], []
    try:
        for name in names:
            piece, state = pieces[name], states[name]
            since = plan_piece(args.root, piece, state, published.get(name, {})).since
            written = changed(args.root, install_piece(args.root, piece, state,
                                                       published.get(name, {}),
                                                       merged=args.from_file))
            kept += [f"{path}: carries local edits and {name} v{piece.version} no longer "
                     "ships it; remove it by hand if nothing uses it"
                     for path in kept_edits(piece, state)]
            if not written:
                # A merged piece: say how it gets back to published bytes.
                if state.state == "edited" and state.installed == piece.version:
                    print(f"{name}: {checking.edited_detail(piece, state)}")
                else:
                    print(f"{name}: already v{piece.version}")
                continue
            merged = args.from_file is not None and any(
                (pathlib.Path(args.root) / path).is_file()
                and (pathlib.Path(args.root) / path).read_text(encoding="utf-8")
                != piece.files.get(path) for path in written)
            commit_piece(args.root, name, piece.version, written, merged=merged)
            print(f"installed {name} v{piece.version}")
            if since:
                notes += [(name, v, text) for v, text in
                          upgrade_notes(name, since, piece.version, ASSETS)]
    finally:
        # A merge stop must not swallow the notes of the pieces installed before it.
        for name, version, text in notes:
            print(f"\n{name} v{version}\n{text}")
    docs = callers.read_workflows(args.root)
    findings = [f"{item.name}: {item.detail}" for item in
                callers.validate(docs, pieces, ASSETS) + checking.config_items(args.root, docs)
                if item.state in report.ATTENTION] + kept
    if findings:
        print("\nThe callers, the config and the files left behind need these changes:")
        for line in findings:
            print(f"  {line}")
    print("\nChange the callers and the config from the notes and findings above, "
          "then run check until it exits 0.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="repo-infra")
    sub = parser.add_subparsers(dest="command", required=True)

    checker = sub.add_parser("check", help="report the state of the pieces, callers and "
                                           "settings; never writes")
    checker.add_argument("--repo", help="owner/name; defaults to the current checkout")
    checker.add_argument("--root", default=".", help="repository root")
    checker.add_argument("--json", action="store_true")
    checker.set_defaults(run=check)

    applier = sub.add_parser("apply", help="install or replace pieces on a branch; "
                                           "with --item, one piece or one setting")
    applier.add_argument("--repo")
    applier.add_argument("--root", default=".")
    applier.add_argument("--item", help="one piece or administration item")
    applier.add_argument("--from", dest="from_file", help="take the merged file from here")
    applier.set_defaults(run=apply_command)

    args = parser.parse_args(argv)
    return args.run(args)
