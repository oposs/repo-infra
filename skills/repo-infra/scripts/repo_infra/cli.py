"""Command line entry point: `python3 -m repo_infra check|apply`."""

import argparse
import json
import pathlib

from . import report
from .assemble import render_all
from .detect import Detection
from .remote import Facts, Gh
from .state import NEEDS_ATTENTION_STATES, classify, classify_ambiguities

ASSETS = pathlib.Path(__file__).resolve().parents[2] / "assets"

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


def main(argv=None):
    parser = argparse.ArgumentParser(prog="repo-infra")
    sub = parser.add_subparsers(dest="command", required=True)

    checker = sub.add_parser("check", help="report drift; never writes")
    checker.add_argument("--repo", help="owner/name; defaults to the current checkout")
    checker.add_argument("--root", default=".", help="repository root")
    checker.add_argument("--json", action="store_true")
    checker.set_defaults(run=check)

    args = parser.parse_args(argv)
    return args.run(args)
