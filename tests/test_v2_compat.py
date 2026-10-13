"""D33: within v2 a piece keeps its interface and its permissions."""

import json
import os
import pathlib
import subprocess

import pytest
import v2compat
from v2compat import problems

from repo_infra import workflow
from repo_infra.pieces import load_pieces

ROOT = pathlib.Path(__file__).resolve().parents[1]

BASE = """on:
  workflow_call:
    inputs:
      ref:
        description: x
        type: string
        required: false
        default: ''
    secrets:
      token:
        description: x
        required: false
    outputs:
      out:
        description: x
        value: ${{ jobs.a.outputs.out }}
permissions:
  contents: read
jobs:
  a:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - run: 'true'
"""


def cmp(new, old=BASE):
    return problems({"ri-x": workflow.load(old)}, {"ri-x": workflow.load(new)})


def test_the_same_piece_has_no_problem():
    assert cmp(BASE) == []


def test_a_removed_piece_is_a_problem():
    assert problems({"ri-x": workflow.load(BASE)}, {}) == ["ri-x: removed within v2"]


@pytest.mark.parametrize("edit, problem", [
    (lambda t: t.replace("      ref:\n        description: x\n        type: string\n"
                         "        required: false\n        default: ''\n", ""),
     "ri-x: input ref removed"),
    (lambda t: t.replace("type: string", "type: boolean"),
     "ri-x: input ref changed its type from string to boolean"),
    (lambda t: t.replace("        required: false\n        default: ''\n",
                         "        required: true\n"),
     "ri-x: input ref became required"),
    (lambda t: t.replace("      token:\n        description: x\n        required: false\n",
                         "      token:\n        description: x\n        required: true\n"),
     "ri-x: secret token became required"),
    (lambda t: t.replace("    secrets:\n      token:\n        description: x\n"
                         "        required: false\n", ""),
     "ri-x: secret token removed"),
    (lambda t: t.replace("    outputs:\n      out:\n        description: x\n"
                         "        value: ${{ jobs.a.outputs.out }}\n", ""),
     "ri-x: output out removed"),
    (lambda t: t.replace("    inputs:\n", "    inputs:\n      new:\n        description: x\n"
                         "        type: string\n        required: true\n"),
     "ri-x: new input new must be optional with a default"),
    (lambda t: t.replace("    inputs:\n", "    inputs:\n      new:\n        description: x\n"
                         "        type: string\n        required: false\n"),
     "ri-x: new input new must be optional with a default"),
    (lambda t: t.replace("    secrets:\n", "    secrets:\n      key:\n        description: x\n"
                         "        required: true\n"),
     "ri-x: new secret key must be optional"),
    (lambda t: t.replace("permissions:\n  contents: read\njobs:",
                         "permissions:\n  contents: write\njobs:"),
     "ri-x: the workflow-level permissions grant contents: write, above contents: read"),
    (lambda t: t.replace("    permissions:\n      contents: read\n",
                         "    permissions:\n      contents: read\n      checks: write\n"),
     "ri-x: job a asks for checks: write, above what it asked for in v2"),
    (lambda t: t + "  b:\n    runs-on: ubuntu-latest\n    permissions:\n"
                   "      pull-requests: write\n    steps:\n      - run: 'true'\n",
     "ri-x: new job b asks for pull-requests: write, beyond what the piece asked for in v2"),
])
def test_a_change_v2_consumers_would_notice_is_a_problem(edit, problem):
    assert problem in cmp(edit(BASE))


@pytest.mark.parametrize("edit", [
    lambda t: t.replace("    inputs:\n", "    inputs:\n      new:\n        description: x\n"
                        "        type: string\n        required: false\n        default: ''\n"),
    lambda t: t.replace("    secrets:\n", "    secrets:\n      key:\n        description: x\n"
                        "        required: false\n"),
    lambda t: t.replace("    outputs:\n", "    outputs:\n      more:\n        description: x\n"
                        "        value: ${{ jobs.a.outputs.more }}\n"),
    lambda t: t.replace("    permissions:\n      contents: read\n", "    permissions:\n"
                        "      contents: none\n"),
])
def test_a_change_v2_allows_is_fine(edit):
    assert cmp(edit(BASE)) == []


def _repo(path, tags):
    def run(*args):
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)

    run("init", "-q")
    run("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q",
        "--allow-empty", "-m", "x")
    for tag in tags:
        run("tag", tag)
    return path


@pytest.mark.parametrize("tags, required, action", [
    (["v2.0.0"], True, "fail"),
    (["v2.0.0"], False, "skip"),
    ([], True, "skip"),
    (["v1.4.2", "v3.0.0", "v2.x", "v20.0.0"], True, "skip"),
    (["v2.0.0", "v2"], True, "compare"),
    (["v2"], False, "compare"),
])
def test_what_the_comparison_does_in_a_checkout(tmp_path, tags, required, action):
    repo = _repo(tmp_path, tags)
    got, detail = v2compat.v2_source(repo, required)
    assert got == action
    if action == "compare":
        assert detail == subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                                        capture_output=True, text=True).stdout.strip()


@pytest.fixture
def v2():
    action, detail = v2compat.v2_source(ROOT, os.environ.get("RI_V2_COMPAT") == "required")
    if action == "fail":
        pytest.fail(detail)
    if action == "skip":
        pytest.skip(detail)
    return detail


def _git(*args):
    return v2compat.git(ROOT, *args)


def test_the_pieces_keep_what_v2_consumers_call(v2):
    manifest = json.loads(_git("show", f"{v2}:skills/repo-infra/assets/manifest.json").stdout)
    old = {}
    for name, spec in manifest["pieces"].items():
        if spec.get("kind") == "remote":
            old[name] = workflow.load(_git("show", f"{v2}:.github/workflows/{name}.yml").stdout)
    new = {name: workflow.load(p.files[p.target]) for name, p in load_pieces().items()
           if p.remote}
    assert problems(old, new) == []
