# tests/conftest.py
import subprocess

import pytest

OLD = "name: CI\n# repo-infra: ci v1\njobs:\n  fmt:\n"
NEW = "name: CI\n# repo-infra: ci v3\njobs:\n  fmt:\n"


@pytest.fixture
def plugin_checkout(tmp_path_factory):
    """A git checkout of the plugin whose history contains the v1 asset.

    This is how apply recovers the base for a three-way merge: the marker says
    which generation is installed, and the plugin's own history has that
    generation's asset.
    """
    root = tmp_path_factory.mktemp("plugin")
    assets = root / "assets/ci"
    assets.mkdir(parents=True)

    def run(*args):
        return subprocess.run(args, cwd=root, check=True, capture_output=True)

    run("git", "init", "-q")
    run("git", "config", "user.email", "test@example.com")
    run("git", "config", "user.name", "Test")
    (assets / "ci-frame.yml").write_text(OLD, encoding="utf-8")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "v1")
    (assets / "ci-frame.yml").write_text(NEW, encoding="utf-8")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "v3")
    return root
