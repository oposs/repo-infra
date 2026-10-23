"""ri-ci-container: the piece that runs `make check` in the project's container (#94)."""

import os
import pathlib
import shutil
import subprocess
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fakeengine import calls, install_fake  # noqa: E402
from test_container_make import TOOLS  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIECE = ROOT / ".github/workflows/ri-ci-container.yml"
FIXTURE = "tests/fixtures/container-make"


def piece():
    return yaml.safe_load(PIECE.read_text(encoding="utf-8"))


def run_step():
    steps = piece()["jobs"]["container"]["steps"]
    found = [s for s in steps if "run" in s]
    assert len(found) == 1
    return found[0]


def test_the_piece_declares_exactly_its_one_job():
    assert list(piece()["jobs"]) == ["container"]


def test_the_inputs_and_their_defaults():
    # PyYAML reads the key `on` as True.
    inputs = piece()[True]["workflow_call"]["inputs"]
    assert inputs["directory"]["default"] == "."
    assert inputs["timeout_minutes"]["default"] == 60
    assert inputs["timeout_minutes"]["type"] == "number"
    assert inputs["ref"]["default"] == ""
    assert inputs["repository"]["default"] == "${{ github.repository }}"


def test_the_job_timeout_comes_from_the_input():
    assert piece()["jobs"]["container"]["timeout-minutes"] == "${{ inputs.timeout_minutes }}"


def test_it_runs_make_check_in_the_directory_with_docker():
    step = run_step()
    assert step["run"].strip() == 'make -C "$DIRECTORY" check'
    assert step["env"]["CONTAINER_ENGINE"] == "docker"
    assert step["env"]["DIRECTORY"] == "${{ inputs.directory }}"


def test_it_needs_only_contents_read():
    assert piece()["permissions"] == {"contents": "read"}


def test_the_step_runs_the_fixture_through_the_fake_engine(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(ROOT / FIXTURE, repo / FIXTURE)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    tools = tmp_path / "tools"
    tools.mkdir()
    for tool in (*TOOLS, "bash"):
        real = shutil.which(tool)
        assert real, f"{tool} is not on the PATH of the test run"
        (tools / tool).symlink_to(real)
    fake = tmp_path / "fake"
    fake.mkdir()
    install_fake(fake)
    (fake / "podman").unlink()
    log = tmp_path / "engine.log"
    env = {k: v for k, v in os.environ.items()
           if k not in ("MAKEFLAGS", "MAKELEVEL", "MFLAGS", "REPO_INFRA_USE_CONTAINER",
                        "CONTAINER_TAG")}
    step = run_step()
    env.update({"PATH": f"{fake}:{tools}", "LC_ALL": "C", "FAKE_ENGINE_LOG": str(log),
                "GIT_CEILING_DIRECTORIES": str(tmp_path), "DIRECTORY": FIXTURE,
                "CONTAINER_ENGINE": step["env"]["CONTAINER_ENGINE"]})
    done = subprocess.run(["bash", "-e", "-c", step["run"]], cwd=repo, env=env,
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    recorded = calls(log)
    subs = [c["argv"][0] for c in recorded if c["argv"]]
    assert subs.count("build") == 1 and subs.count("run") == 1, recorded
    assert all(c["engine"] == "docker" for c in recorded)


def test_repo_infra_ci_runs_the_fixture_through_the_piece():
    doc = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    job = doc["jobs"]["container"]
    assert job["uses"] == "./.github/workflows/ri-ci-container.yml"
    assert job["with"]["directory"] == FIXTURE
    assert "container" in doc["jobs"]["ci-passed"]["needs"]
