"""ri-ci-node-pnpm: the Node version comes from the project.

The piece ran every project on Node 22, the LTS when it was written, and a
project that wanted Node 26 could not say so. Now package.json names the
version where actions/setup-node reads it; without one the piece takes the
current LTS, because setup-node would otherwise keep whatever Node the runner
image carries.
"""

import json
import os
import pathlib
import subprocess

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIECE = ROOT / ".github/workflows/ri-ci-node-pnpm.yml"
STEP_NAME = "Choose the Node version"


def steps():
    jobs = yaml.safe_load(PIECE.read_text(encoding="utf-8"))["jobs"]
    return jobs["node-pnpm-check"]["steps"]


def choose_step():
    return next(s for s in steps() if s.get("name") == STEP_NAME)


def choose(tmp_path, manifest, directory="."):
    """Run the step in a tree whose <directory>/package.json is `manifest`."""
    where = tmp_path / directory
    where.mkdir(parents=True, exist_ok=True)
    (where / "package.json").write_text(
        manifest if isinstance(manifest, str) else json.dumps(manifest), encoding="utf-8")
    out = tmp_path / "github_output"
    out.write_text("", encoding="utf-8")
    env = dict(os.environ, GITHUB_OUTPUT=str(out), **choose_step()["env"])
    env["DIRECTORY"] = directory
    done = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", choose_step()["run"]],
                          cwd=where, env=env, capture_output=True, text=True, timeout=60)
    done.outputs = dict(line.split("=", 1) for line in out.read_text().splitlines() if line)
    return done


def test_no_node_version_is_hard_coded():
    setup = next(s for s in steps() if s.get("uses", "").startswith("actions/setup-node@"))
    assert setup["with"]["node-version"] == "${{ steps.node.outputs.version }}"
    assert setup["with"]["node-version-file"] == "${{ steps.node.outputs.file }}"


def test_the_choice_comes_before_setup_node():
    names = [s.get("name") or s.get("uses") or s.get("run") for s in steps()]
    setup = next(i for i, s in enumerate(steps()) if s.get("uses", "").startswith("actions/setup-node@"))
    assert names.index(STEP_NAME) < setup


def test_engines_node_hands_package_json_to_setup_node(tmp_path):
    done = choose(tmp_path, {"engines": {"node": ">=26"}})
    assert done.returncode == 0, done.stderr
    assert done.outputs == {"file": "./package.json"}


def test_volta_and_dev_engines_count_as_setup_node_reads_them(tmp_path):
    for manifest in ({"volta": {"node": "26.1.0"}},
                     {"volta": {"extends": "../package.json"}},
                     {"devEngines": {"runtime": {"name": "node", "version": "^26"}}},
                     {"devEngines": {"runtime": [{"name": "bun"}, {"name": "Node", "version": "26"}]}}):
        done = choose(tmp_path, manifest)
        assert done.returncode == 0, done.stderr
        assert done.outputs == {"file": "./package.json"}, manifest


def test_without_a_version_the_current_lts(tmp_path):
    for manifest in ({"name": "x"},
                     {"engines": {"pnpm": ">=10"}},
                     {"devEngines": {"runtime": {"name": "bun", "version": "1"}}},
                     {"devEngines": {"runtime": {"name": "node"}}}):
        done = choose(tmp_path, manifest)
        assert done.returncode == 0, done.stderr
        assert done.outputs == {"version": "lts/*"}, manifest


def test_the_file_is_named_from_the_repository_root(tmp_path):
    # setup-node resolves node-version-file against the workspace, not against
    # the job's working directory.
    done = choose(tmp_path, {"engines": {"node": "26"}}, directory="player")
    assert done.returncode == 0, done.stderr
    assert done.outputs == {"file": "player/package.json"}


def test_a_package_json_that_is_not_json_fails_the_step(tmp_path):
    done = choose(tmp_path, "{ not json")
    assert done.returncode != 0
