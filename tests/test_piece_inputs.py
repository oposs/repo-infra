"""Optional inputs that let a piece serve a project shape it refused before:
git submodules in the Rust and Go pieces (#147, #148) and a node project in a
subdirectory (#151)."""

import pathlib

import pytest

from repo_infra import workflow

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUBMODULE_PIECES = ("ri-ci-rust", "ri-ci-rust-musl", "ri-release-rust-binaries",
                    "ri-publish-crates-io", "ri-ci-go", "ri-release-go-binaries")


def load(name):
    return workflow.load((ROOT / ".github/workflows" / f"{name}.yml").read_text(
        encoding="utf-8"))


def caller_checkouts(doc):
    """Each actions/checkout step that checks out the calling repository, not
    repo-infra's own scripts at .repo-infra."""
    found = []
    for job in doc["jobs"].values():
        for step in job.get("steps", []):
            if step.get("uses", "").startswith("actions/checkout@") and \
                    step.get("with", {}).get("path") != ".repo-infra":
                found.append(step)
    return found


@pytest.mark.parametrize("name", SUBMODULE_PIECES)
def test_the_rust_piece_takes_an_optional_submodules_input(name):
    spec = load(name)["on"]["workflow_call"]["inputs"]["submodules"]
    assert spec["type"] == "string"
    assert spec["required"] == "false"
    assert spec["default"] == "false"


@pytest.mark.parametrize("name", SUBMODULE_PIECES)
def test_every_checkout_of_the_caller_passes_submodules_on(name):
    steps = caller_checkouts(load(name))
    assert steps
    assert all(step["with"].get("submodules") == "${{ inputs.submodules }}"
               for step in steps), name


def test_the_pnpm_piece_takes_an_optional_directory_input():
    spec = load("ri-ci-node-pnpm")["on"]["workflow_call"]["inputs"]["directory"]
    assert spec["type"] == "string"
    assert spec["required"] == "false"
    assert spec["default"] == "."


def test_the_pnpm_piece_runs_every_command_in_the_directory():
    doc = load("ri-ci-node-pnpm")
    (job,) = doc["jobs"].values()
    assert job["defaults"]["run"]["working-directory"] == "${{ inputs.directory }}"
    setup = next(s for s in job["steps"] if s.get("uses", "").startswith("actions/setup-node@"))
    assert setup["with"]["cache-dependency-path"] == "${{ inputs.directory }}/pnpm-lock.yaml"
    # corepack reads packageManager from the package.json of the directory it runs in.
    assert [s["run"] for s in job["steps"] if "run" in s][0] == "corepack enable"
