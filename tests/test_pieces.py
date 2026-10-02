# tests/test_pieces.py
"""Invariants every shipped piece holds (D30). Parametrized over the real
store, so a piece added later is checked the day it lands."""

import json
import pathlib
import re

import pytest

from repo_infra import callers, workflow
from repo_infra.pieces import ASSETS, load_pieces

PIECES = load_pieces()
WORKFLOW_PIECES = sorted((p for p in PIECES.values() if p.workflow), key=lambda p: p.name)
# changelog and release-pr start runs of their own; every other workflow piece is called.
CALLED = [p for p in WORKFLOW_PIECES if p.group != "release"]
ALL = sorted(PIECES.values(), key=lambda p: p.name)
ACTIONS = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))["actions"]
GROUPS = {"ci", "release-build", "publish", "release", "build"}
_PINNED = re.compile(r"^([\w.-]+/[\w.-]+)@(v\d+)$")


def ids(piece):
    return piece.name


def doc_of(piece):
    return workflow.load(piece.files[piece.target])


@pytest.mark.parametrize("piece", ALL, ids=ids)
def test_a_piece_names_a_known_group_and_existing_pieces(piece):
    assert piece.group in GROUPS
    assert [n for n in piece.needs if n not in PIECES] == []


@pytest.mark.parametrize("piece", ALL, ids=ids)
def test_changes_has_a_section_for_the_current_version(piece):
    text = (ASSETS / "pieces" / piece.name / "CHANGES.md").read_text(encoding="utf-8")
    versions = [int(v) for v in re.findall(r"^## v(\d+)\s*$", text, re.MULTILINE)]
    assert piece.version in versions
    assert max(versions) == piece.version


@pytest.mark.parametrize("piece", CALLED, ids=ids)
def test_a_workflow_piece_is_a_described_reusable_workflow(piece):
    doc = doc_of(piece)
    face = workflow.interface(doc)
    assert face is not None, "no on: workflow_call"
    undescribed = [n for n, s in {**face.inputs, **face.secrets}.items()
                   if not s["description"].strip()]
    assert undescribed == []
    assert "permissions" in doc, "declare the workflow-level permissions"
    assert set(doc["on"]) == {"workflow_call"}, "a piece is only ever called"


@pytest.mark.parametrize("piece", WORKFLOW_PIECES, ids=ids)
def test_every_inline_job_has_a_timeout(piece):
    jobs = doc_of(piece)["jobs"]
    assert [j for j, job in jobs.items() if "uses" not in job
            and "timeout-minutes" not in job] == []


@pytest.mark.parametrize("piece", WORKFLOW_PIECES, ids=ids)
def test_actions_are_pinned_to_the_manifest(piece):
    wrong = []
    for job in doc_of(piece)["jobs"].values():
        for step in job.get("steps", []):
            match = _PINNED.match(step.get("uses", ""))
            if match and ACTIONS.get(match[1]) != match[2]:
                wrong.append(step["uses"])
    assert wrong == []


@pytest.mark.parametrize("piece", CALLED, ids=ids)
def test_the_call_snippet_calls_this_piece_correctly(piece):
    snippet = workflow.load(piece.header["Call"])
    assert len(snippet) == 1, "Call: holds exactly one job"
    (job_id, job), = snippet.items()
    file = pathlib.PurePosixPath(piece.target).name
    assert job["uses"] == f"./.github/workflows/{file}"
    assert callers.call_problems(job_id, job, {file: doc_of(piece)}) == []


@pytest.mark.parametrize("piece", [p for p in CALLED
                                   if p.group in ("ci", "release-build")], ids=ids)
def test_a_ci_or_build_piece_keeps_the_ref_contract(piece):
    assert callers.ref_problems(doc_of(piece), reserved=piece.group == "ci") == []
