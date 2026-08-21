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


def test_a_repository_with_no_ecosystem_but_an_open_ambiguity_is_not_called_unrecognised():
    """No ecosystem matched *and* an ambiguity is open -- unresolved is not the
    same as unrecognised, so this must fall through to the ordinary
    "/repo-infra:apply" message, not the teach-path one. The only thing
    pinning `report.render_text`'s `and not has_ambiguous` guard today is
    `test_an_unresolved_ambiguity_keeps_the_count_honest` in test_report.py,
    which never mentions the teach path -- a future simplification that drops
    the guard would keep that test green and silently revert this."""
    ambiguous = [Item("node-lockfiles", "ambiguous", "pnpm-lock.yaml or package-lock.json?")]
    text = render_text("oetiker/mdmost", FakeResult([]), ambiguous)
    assert "does not recognise" not in text
    assert "/repo-infra:apply" in text


def test_a_recognised_and_current_repository_is_unchanged():
    text = render_text("oposs/repo-infra", FakeResult(["python"]), ADMIN_OK)
    assert "Up to date with the standard" in text
