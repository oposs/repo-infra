import json

from repo_infra.detect import DetectResult
from repo_infra.report import render_json, render_text
from repo_infra.state import Item

RESULT = DetectResult(ecosystems=["rust"], blocks=["ci-lib", "ci-rust"],
                      version_files=[], candidates=["man-pages"], ambiguities=[])
ITEMS = [
    Item("default-branch", "ok", "main"),
    Item("changelog", "missing", "not installed"),
    Item("ci-rust", "outdated", "v1 installed, v2 available"),
    Item("release-pr", "ok", ""),
]


def test_the_report_names_the_repository_and_what_was_detected():
    text = render_text("oetiker/mdmost", RESULT, ITEMS)
    assert text.startswith("repo-infra check")
    assert "oetiker/mdmost" in text
    assert "rust" in text


def test_every_item_appears_with_its_state_and_detail():
    text = render_text("oetiker/mdmost", RESULT, ITEMS)
    assert "changelog" in text and "missing" in text
    assert "v1 installed, v2 available" in text


def test_the_count_excludes_items_that_are_already_ok():
    assert "2 items need attention" in render_text("oetiker/mdmost", RESULT, ITEMS)


def test_a_clean_repository_says_so_and_names_no_next_command():
    text = render_text("oposs/repo-infra", RESULT, [Item("changelog", "ok", "")])
    assert "nothing to do" in text
    assert "/repo-infra:apply" not in text


def test_candidates_are_listed_but_not_counted():
    text = render_text("oetiker/mdmost", RESULT, ITEMS)
    assert "man-pages" in text
    assert "2 items need attention" in text


def test_json_carries_the_same_structure_for_apply_to_consume():
    data = json.loads(render_json("oetiker/mdmost", RESULT, ITEMS))
    assert data["repo"] == "oetiker/mdmost"
    assert data["ecosystems"] == ["rust"]
    assert data["candidates"] == ["man-pages"]
    assert {"name": "ci-rust", "state": "outdated",
            "detail": "v1 installed, v2 available"} in data["items"]


def test_an_unresolved_ambiguity_keeps_the_count_honest():
    """A `?` question in the text is not enough -- the count a person reads
    first must not say 'nothing to do' while an item still needs a decision."""
    result = DetectResult(ecosystems=[], blocks=["ci-lib"], version_files=[],
                          candidates=[], ambiguities=[{
                              "id": "node-lockfiles",
                              "question": "pnpm-lock.yaml and package-lock.json both exist.",
                          }])
    items = [Item("node-lockfiles", "ambiguous",
                  "pnpm-lock.yaml and package-lock.json both exist.")]
    text = render_text("oetiker/mdmost", result, items)
    assert "1 item needs attention" in text
    assert "nothing to do" not in text
