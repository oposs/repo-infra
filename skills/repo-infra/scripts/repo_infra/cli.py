"""Command line entry point: `python3 -m repo_infra check|apply`."""

import argparse
import pathlib
import sys

from . import callers, migrate, report
from . import check as checking
from .apply import (
    MIGRATE_BODY,
    MIGRATE_SUBJECT,
    ApplyError,
    NeedsMerge,
    apply_admin_item,
    changed,
    commit_paths,
    commit_piece,
    ensure_branch,
    install_piece,
    kept_edits,
    pending,
    plan_piece,
    release_in_progress,
)
from .pieces import ASSETS, PieceError, load_pieces, load_published, upgrade_notes
from .remote import Facts, Gh, GhError

# Administration items write repository settings through `remote.Gh`, and
# each is outward-facing, so apply runs one only when it is named (D30).
ADMIN = {"default-branch", "branch-protection", "required-checks",
         "no-changelog-label", "actions-open-pr", "delete-merged-branches",
         "classic-protection"}

# apply's exit status when it stops for a hand merge. A refusal (ApplyError)
# exits 1; argparse exits 2 on a usage error.
EXIT_NEEDS_MERGE = 3

# Used by the tests to run without a network. Never used at runtime.
CONFORMING_FACTS = Facts(default_branch="main", protected=True,
                         required_contexts={"ci-passed", "changelog-updated"},
                         labels={"no-changelog"}, workflow_permissions="write",
                         can_approve_pr=True, delete_branch_on_merge=True, strict=True)


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


def _files(root, pieces):
    """The pieces apply installs, as the callers of `root` render them (#92)."""
    rendered = checking.rendered(pieces, callers.read_workflows(root))
    return {name: piece for name, piece in rendered.items() if not piece.remote}


def _states(root, pieces, published):
    return {name: checking.piece_state(root, piece, published.get(name, {}))
            for name, piece in pieces.items()}


# Heads the files and jobs the migration removes that repo-infra never
# shipped, in apply's output and in the commit body.
LOST = ("The migration removed these local changes; git keeps them. Port each to a "
        "caller or drop it:")


def _v1_layout(args):
    """True when a bare apply migrates (D33): a consumer that still has a
    file of the v1 layout. --item installs the one piece it names."""
    return (args.item is None and not checking.is_home(args.root)
            and bool(checking.layout_items(args.root, load_pieces(ASSETS))))


def apply_command(args):
    # The arguments are refused before GitHub is asked anything: a typo
    # should not wait for, or fail on, the network.
    if args.item in ADMIN and args.from_file:
        raise ApplyError("--from takes the merged file of a piece, not of "
                         f"the administration item {args.item}")
    if args.from_file and not args.item:
        raise ApplyError("--from needs --item: name the piece the merged file is for")
    if args.item not in ADMIN:
        pieces, published = load_pieces(ASSETS), load_published(ASSETS)
        if args.item is not None and args.item not in pieces:
            raise ApplyError(f"{args.item}: not a piece and not an administration item")
        if args.item is not None and pieces[args.item].remote:
            raise ApplyError(f"{args.item} is called, not installed (D33): add its Call: "
                             "from the catalogue to a caller, as "
                             f"`uses: {pieces[args.item].uses}`")
    repo = args.repo or Gh().current_repo()
    facts = read_facts(repo)
    if args.item in ADMIN:
        print(apply_admin_item(Gh(), repo, args.item, facts, ASSETS, args.root))
        return 0
    # A remote piece is called, never installed (D33); apply writes the
    # byte pieces only.
    files = _files(args.root, pieces)
    states = _states(args.root, files, published)
    names = [args.item] if args.item else _pending(args.root, files, states, published)
    if names or _v1_layout(args):
        blocker = release_in_progress(args.root, facts)
        if blocker:
            raise ApplyError(f"release-in-progress: {blocker}")
        ensure_branch(args.root, facts.default_branch)
        # The branch may carry other versions of the files than the one the
        # first look found, so what to install is decided on this one.
        if _v1_layout(args):
            # Read before the migration removes the files.
            lost = migrate.local_changes(args.root, pieces, ASSETS)
            written = changed(args.root, migrate.migrate(args.root, pieces, ASSETS))
            message = f"{MIGRATE_SUBJECT}\n\n{MIGRATE_BODY}"
            if lost:
                message += f"\n\n{LOST}\n" + "\n".join(f"- {line}" for line in lost)
            if written:
                commit_paths(args.root, written, message)
            print(f"migrated to the v2 layout: {len(written)} files")
            if lost:
                print(f"\n{LOST}")
                for line in lost:
                    print(f"  {line}")
        files = _files(args.root, pieces)
        states = _states(args.root, files, published)
        names = [args.item] if args.item else _pending(args.root, files, states, published)
    notes, kept = [], []
    try:
        for name in names:
            piece, state = files[name], states[name]
            since = plan_piece(args.root, piece, state, published.get(name, {})).since
            written = changed(args.root, install_piece(args.root, piece, state,
                                                       published.get(name, {}),
                                                       merged=args.from_file))
            kept += [f"{path}: carries local edits and {name} v{piece.version} no longer "
                     "ships it; remove it by hand if nothing uses it"
                     for path in kept_edits(piece, state)]
            if not written:
                # An edited shipped file that claims the current version (a
                # finished merge) or a newer one: say what check says, how it
                # gets back to published bytes or that the plugin is old.
                if state.state == "edited" and set(state.edited) & set(piece.files):
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
                callers.validate(docs, pieces, ASSETS, home=checking.is_home(args.root))
                + checking.config_items(args.root, docs)
                if item.state in report.ATTENTION] + kept
    if findings:
        print("\nThe callers, the config and the files left behind need these changes:")
        for line in findings:
            print(f"  {line}")
    print("\nChange the callers and the config from the notes and findings above, "
          "then run check until it exits 0.")
    return 0


def run(argv=None):
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


def main(argv=None):
    """`run`, with apply's two ways of stopping, a failed `gh` call and a
    broken asset store printed as a message and an exit status instead of a
    Python traceback. The upgrade notes of the pieces installed before a
    merge stop are already printed."""
    try:
        return run(argv)
    except NeedsMerge as stop:
        print(f"NeedsMerge: {stop}", file=sys.stderr)
        return EXIT_NEEDS_MERGE
    except ApplyError as refusal:
        print(f"refused: {refusal}", file=sys.stderr)
        return 1
    except GhError as error:
        print(f"gh: {error}", file=sys.stderr)
        return 1
    except PieceError as error:
        print(f"the plugin's asset store is broken (reinstall the plugin): {error}",
              file=sys.stderr)
        return 1
