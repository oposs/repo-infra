import json
import pathlib

import pytest

from repo_infra import fragments

CASES = json.loads((pathlib.Path(__file__).resolve().parent / "fixtures"
                    / "changelog-fragments" / "cases.json").read_text(encoding="utf-8"))


def of(kind):
    return [c for c in CASES if c["kind"] == kind]


@pytest.mark.parametrize("case", of("note"), ids=lambda c: repr(c["input"]))
def test_note_dir_reads_the_directory_of_the_note_or_refuses_it(case):
    if case["ok"]:
        assert fragments.note_dir(case["input"]) == case["value"]
    else:
        with pytest.raises(ValueError, match="Changelog fragments directory"):
            fragments.note_dir(case["input"])


@pytest.mark.parametrize("case", of("name"), ids=lambda c: c["input"])
def test_fragment_names_follow_the_pattern(case):
    kind, _ = fragments.classify_path("CHANGES.d", f"CHANGES.d/fixed/{case['input']}")
    assert (kind == "fragment") == case["ok"]


@pytest.mark.parametrize("case", of("body"), ids=lambda c: repr(c["input"]))
def test_fragment_bodies_follow_the_entry_rules(case):
    assert (fragments.fragment_problem(case["input"]) is None) == case["ok"]
    if case["ok"]:
        assert "|".join(fragments.entries(case["input"])) == case["value"]


def test_classify_path_tells_outside_root_refused_and_fragment():
    name = "20261126-0921-a3f9-x.md"
    assert fragments.classify_path("CHANGES.d", "src/a.rs")[0] == "outside"
    assert fragments.classify_path("CHANGES.d", "CHANGES.dx/new/" + name)[0] == "outside"
    assert fragments.classify_path("CHANGES.d", "CHANGES.d/README.md") == ("root", None)
    assert fragments.classify_path("CHANGES.d", f"CHANGES.d/other/{name}")[0] == "refused"
    assert fragments.classify_path("CHANGES.d", f"CHANGES.d/new/sub/{name}")[0] == "refused"
    assert fragments.classify_path("CHANGES.d", f"CHANGES.d/new/{name}") == ("fragment", "new")
