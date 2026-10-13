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
# The release pieces are tested by their own files; every other workflow piece is
# reviewed here as one a caller calls.
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


BYTE = [p for p in ALL if not p.remote]
REMOTE = [p for p in ALL if p.remote]


@pytest.mark.parametrize("piece", BYTE, ids=ids)
def test_changes_has_a_section_for_the_current_version(piece):
    text = (ASSETS / "pieces" / piece.name / "CHANGES.md").read_text(encoding="utf-8")
    versions = [int(v) for v in re.findall(r"^## v(\d+)\s*$", text, re.MULTILINE)]
    assert piece.version in versions
    assert max(versions) == piece.version


@pytest.mark.parametrize("piece", REMOTE, ids=ids)
def test_a_remote_piece_has_no_copy_and_no_upgrade_notes(piece):
    assert not (ASSETS / "pieces" / piece.name).exists()


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
    assert job["uses"] == piece.uses
    file = pathlib.PurePosixPath(piece.target).name
    local = dict(job, uses=f"./.github/workflows/{file}")
    assert callers.call_problems(job_id, local, {file: doc_of(piece)}) == []


def test_every_ri_workflow_of_repo_infra_is_a_piece_or_home_only():
    root = ASSETS.parents[2]
    files = {p.name for p in (root / ".github/workflows").glob("ri-*.yml")}
    assert files == {f"{p.name}.yml" for p in REMOTE} | {"ri-ci-lib.yml"}


@pytest.mark.parametrize("piece", [p for p in CALLED
                                   if p.group in ("ci", "release-build")], ids=ids)
def test_a_ci_or_build_piece_keeps_the_ref_contract(piece):
    assert callers.ref_problems(doc_of(piece), reserved=piece.group == "ci") == []


LIB_CHECKOUT = {
    "uses": "actions/checkout@v7",
    "with": {"repository": "${{ job.workflow_repository }}",
             "ref": "${{ job.workflow_sha }}",
             "path": ".repo-infra",
             "sparse-checkout": ".github/workflows/lib"}}
LIB_PATH = ".repo-infra/.github/workflows/lib"


def _library_jobs(piece):
    return {job_id: job for job_id, job in doc_of(piece)["jobs"].items()
            if ".github/workflows/lib" in str(job.get("steps", ""))}


@pytest.mark.parametrize("piece", REMOTE, ids=ids)
def test_a_piece_requires_the_library_only_from_its_own_commit(piece):
    text = piece.files[piece.target]
    for line in text.splitlines():
        if ".github/workflows/lib" in line and not line.lstrip().startswith("#"):
            assert (LIB_PATH in line or "sparse-checkout: .github/workflows/lib" in line), line


@pytest.mark.parametrize("piece", REMOTE, ids=ids)
def test_the_library_checkout_follows_every_source_checkout(piece):
    """actions/checkout cleans the workspace, so a source checkout after the
    library checkout would delete .repo-infra (D33)."""
    for job_id, job in _library_jobs(piece).items():
        steps = job["steps"]
        libs = [i for i, s in enumerate(steps) if s == LIB_CHECKOUT]
        assert len(libs) == 1, f"{job_id}: one library checkout"
        sources = [i for i, s in enumerate(steps)
                   if str(s.get("uses", "")).startswith("actions/checkout@") and s != LIB_CHECKOUT]
        scripts = [i for i, s in enumerate(steps)
                   if str(s.get("uses", "")).startswith("actions/github-script@")]
        assert all(i < libs[0] for i in sources), f"{job_id}: source checkout after the library"
        assert all(libs[0] < i for i in scripts), f"{job_id}: script before the library"


@pytest.mark.parametrize("piece", REMOTE, ids=ids)
def test_a_remote_piece_needs_no_workflow_lib_piece(piece):
    assert "workflow-lib" not in piece.needs


def test_the_library_is_one_copy_and_no_piece():
    root = ASSETS.parents[2]
    assert not (ASSETS / "pieces/workflow-lib").exists()
    for path in (root / ".github/workflows/lib").glob("*.js"):
        assert "repo-infra: workflow-lib" not in path.read_text(encoding="utf-8"), path.name
