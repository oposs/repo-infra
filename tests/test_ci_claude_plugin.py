"""The ri-ci-claude-plugin piece (#82): its shipped step, run under node.

The rules themselves are tested in .github/workflows/lib/plugin.test.js.
These tests run the step's own `script:` text against a real git
repository with the library in .repo-infra, as CI lays them out, so the
wiring (git ls-files, the library path, the repository input) is what is
tested, not a copy of it.
"""

import json
import os
import pathlib
import shutil
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIECE = ROOT / ".github/workflows/ri-ci-claude-plugin.yml"
GOOD = {"name": "demo", "description": "A demo", "version": "1.2.3"}

PRELUDE = """
const failures = []; const notices = [];
const core = { setFailed: (m) => failures.push(m), notice: (m) => notices.push(m) };
"""


def step():
    steps = yaml.safe_load(PIECE.read_text(encoding="utf-8"))["jobs"]["plugin-manifest"]["steps"]
    (found,) = [s for s in steps if s.get("name") == "Check every .claude-plugin/plugin.json"]
    assert found["env"] == {"REPOSITORY": "${{ inputs.repository }}"}
    return found["with"]["script"]


def workspace(tmp_path, tree):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    ws = tmp_path / "ws"
    ws.mkdir()
    for path, content in tree.items():
        target = ws / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content if isinstance(content, str) else json.dumps(content),
                          encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=ws, check=True)
    subprocess.run(["git", "add", "-A"], cwd=ws, check=True)
    # Untracked, as the library checkout is in CI: it must not count.
    shutil.copytree(ROOT / ".github/workflows/lib", ws / ".repo-infra/.github/workflows/lib")
    (ws / ".repo-infra/.claude-plugin").mkdir()
    (ws / ".repo-infra/.claude-plugin/plugin.json").write_text("{", encoding="utf-8")
    return node, ws


def run(tmp_path, tree, repository="oetiker/shadcn-egui"):
    node, ws = workspace(tmp_path, tree)
    harness = PRELUDE + "\n(async () => {\n" + step() + \
        "\n})().then(() => console.log(JSON.stringify({ failures, notices })));\n"
    path = tmp_path / "harness.js"
    path.write_text(harness, encoding="utf-8")
    proc = subprocess.run([node, str(path)], capture_output=True, text=True, cwd=ws,
                          env={"GITHUB_WORKSPACE": str(ws), "REPOSITORY": repository,
                               "PATH": os.environ["PATH"]})
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_a_root_plugin_passes_as_before(tmp_path):
    assert run(tmp_path, {".claude-plugin/plugin.json": GOOD}) == {
        "failures": [], "notices": ["checked .claude-plugin/plugin.json"]}


def test_a_plugin_in_a_subdirectory_with_its_marketplace_passes(tmp_path):
    marketplace = {"name": "m", "owner": {"name": "o"}, "plugins": [
        {"name": "shadcn-egui", "source": {
            "source": "git-subdir", "url": "https://github.com/oetiker/shadcn-egui.git",
            "path": "plugin"}},
        {"name": "other", "source": {
            "source": "git-subdir", "url": "oposs/repo-infra", "path": "nowhere"}}]}
    assert run(tmp_path, {"plugin/.claude-plugin/plugin.json": GOOD,
                          ".claude-plugin/marketplace.json": marketplace}) == {
        "failures": [], "notices": ["checked plugin/.claude-plugin/plugin.json"]}


def test_no_plugin_fails(tmp_path):
    out = run(tmp_path, {"README.md": "hi"})
    assert len(out["failures"]) == 1
    assert "no tracked .claude-plugin/plugin.json" in out["failures"][0]


def test_a_bad_nested_version_and_a_dangling_entry_both_fail(tmp_path):
    marketplace = {"name": "m", "owner": {"name": "o"}, "plugins": [
        {"name": "egui", "source": {
            "source": "git-subdir", "url": "Oetiker/Shadcn-Egui", "path": "plugins/egui"}}]}
    out = run(tmp_path, {"plugin/.claude-plugin/plugin.json": dict(GOOD, version="v1"),
                         ".claude-plugin/marketplace.json": marketplace})
    assert out["failures"] == [
        'plugin/.claude-plugin/plugin.json: version "v1" is not X.Y.Z\n'
        '.claude-plugin/marketplace.json: plugin "egui" points at plugins/egui, '
        "which has no tracked plugins/egui/.claude-plugin/plugin.json"]
