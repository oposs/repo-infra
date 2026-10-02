# tests/conftest.py
import os
import shutil

import pytest


@pytest.fixture(autouse=True)
def git_identity(monkeypatch):
    """Give every git commit an author, including the ones apply makes.

    A GitHub runner has no git identity and no host name git can build one
    from, so "git commit" fails there with "Author identity unknown". A
    developer machine guesses one, which hid six such tests until the
    PR #44 run.
    """
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.com")


@pytest.fixture
def require():
    """Skip a test whose tool is missing, or fail it when CI is set.

    Locally a missing pandoc is a reason to skip. On a CI runner the job that
    runs these tests exists to install the tools, so a missing one means the
    gate would pass by testing nothing (owner ruling, 2026-09-23).
    """
    def check(*tools):
        missing = [tool for tool in tools if shutil.which(tool) is None]
        if not missing:
            return
        message = "not on the PATH: " + ", ".join(missing)
        if os.environ.get("CI"):
            pytest.fail(message + " (CI is set, so this test must run, not skip)")
        pytest.skip(message)
    return check
