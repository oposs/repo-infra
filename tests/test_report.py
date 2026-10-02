import json

from repo_infra.report import Item, render_json, render_text

ITEMS = [Item("pieces", "ri-ci-rust", "outdated", "v1 installed, v2 available"),
         Item("pieces", "changelog", "current", "v5"),
         Item("callers", "ci.yml", "problem", "job a calls ri-zz.yml, which does not exist"),
         Item("administration", "default-branch", "ok", "main")]


def test_text_groups_rows_by_section_and_counts_what_needs_attention():
    text = render_text("o/r", ITEMS)
    assert text.startswith("repo-infra check: o/r\n\npieces\n  ri-ci-rust")
    assert "\ncallers\n  ci.yml" in text
    assert "\nadministration\n  default-branch" in text
    assert "config" not in text
    assert text.endswith("2 items need attention.\n")


def test_text_says_so_when_nothing_needs_attention():
    assert render_text("o/r", ITEMS[1:2]).endswith(
        "Up to date with the standard; nothing to do.\n")


def test_json_carries_the_section():
    data = json.loads(render_json("o/r", ITEMS))
    assert data["repo"] == "o/r"
    assert data["items"][2] == {"section": "callers", "name": "ci.yml", "state": "problem",
                                "detail": "job a calls ri-zz.yml, which does not exist"}
