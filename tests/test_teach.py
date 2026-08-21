from repo_infra.report import render_text
from repo_infra.state import Item


class FakeResult:
    def __init__(self, ecosystems):
        self.ecosystems = ecosystems
        self.candidates = []
        self.ambiguities = []


ADMIN_OK = [Item("actions-open-pr", "ok", "")]
FILES_MISSING = [Item("ci", "missing", "not installed")]


def test_an_unrecognised_repository_is_named_as_such():
    text = render_text("oposs/mkp-builder", FakeResult([]), ADMIN_OK + FILES_MISSING)
    assert "the standard does not recognise this repository" in text


def test_an_unrecognised_repository_points_at_the_teach_path_not_apply():
    text = render_text("oposs/mkp-builder", FakeResult([]), ADMIN_OK + FILES_MISSING)
    assert "/repo-infra:apply" not in text


def test_a_recognised_repository_still_points_at_apply():
    text = render_text("oetiker/SmokePing", FakeResult(["perl-autotools"]), FILES_MISSING)
    assert "/repo-infra:apply" in text
    assert "does not recognise" not in text


def test_a_recognised_and_current_repository_is_unchanged():
    text = render_text("oposs/repo-infra", FakeResult(["python"]), ADMIN_OK)
    assert "Up to date with the standard" in text
