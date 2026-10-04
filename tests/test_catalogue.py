import pathlib

import pytest
from piecekit import make_assets, workflow_piece

from repo_infra import catalogue
from repo_infra.pieces import load_pieces

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOGUE = ROOT / "skills/repo-infra/references/catalogue.md"


def test_the_committed_catalogue_is_what_the_pieces_say():
    assert CATALOGUE.read_text(encoding="utf-8") == catalogue.render(load_pieces()), (
        "run make catalogue")


def test_an_entry_shows_header_inputs_permissions_and_the_call(tmp_path):
    extra = ("      target:\n        description: The make target.\n"
             "        type: string\n        required: true\n")
    store = make_assets(tmp_path, {"ri-x": workflow_piece("ri-x", 2, inputs=extra)})
    text = catalogue.entry(load_pieces(store)["ri-x"])
    assert text.startswith("### ri-x v2\n\nInstalled at `.github/workflows/ri-x.yml`.")
    assert "**Purpose:** Test piece ri-x." in text
    assert "| `ref` | string | no | `''` | The commit to test. |" in text
    assert "| `target` | string | yes |  | The make target. |" in text
    assert "**Permissions it needs:** contents: read" in text
    assert "```yaml\nx:\n  uses: ./.github/workflows/ri-x.yml\n" in text


def test_a_piece_in_an_unknown_group_is_an_error_not_a_gap(tmp_path):
    store = make_assets(tmp_path, {"ri-x": workflow_piece("ri-x", 1)})
    pieces = load_pieces(store)
    pieces["ri-x"].group = "nowhere"
    with pytest.raises(ValueError, match="ri-x.*nowhere"):
        catalogue.render(pieces)


# --- deferred Task 6 minors -------------------------------------------------

SECRETS = """    secrets:
      TOKEN:
        description: The registry token | write scope.
        required: true
    outputs:
      tag:
        description: The tag.
        value: ${{ jobs.x.outputs.tag }}
"""


def test_an_entry_shows_secrets_and_outputs(tmp_path):
    piece = workflow_piece("ri-x", 1).replace("permissions:\n", SECRETS + "permissions:\n", 1)
    store = make_assets(tmp_path, {"ri-x": piece})
    text = catalogue.entry(load_pieces(store)["ri-x"])
    assert "| `TOKEN` | yes | The registry token \\| write scope. |" in text
    assert "**Outputs:** `tag`" in text


def test_a_pipe_in_the_type_or_the_default_does_not_split_the_row(tmp_path):
    odd = ("      mode:\n        description: The mode.\n        type: string|number\n"
           "        required: false\n        default: a|b\n")
    store = make_assets(tmp_path, {"ri-x": workflow_piece("ri-x", 1, inputs=odd)})
    text = catalogue.entry(load_pieces(store)["ri-x"])
    assert "| `mode` | string\\|number | no | `a\\|b` | The mode. |" in text


def test_a_multi_line_call_is_shown_whole(tmp_path):
    store = make_assets(tmp_path, {"ri-x": workflow_piece("ri-x", 1)})
    text = catalogue.entry(load_pieces(store)["ri-x"])
    assert ("```yaml\nx:\n  uses: ./.github/workflows/ri-x.yml\n  with:\n"
            "    ref: ${{ inputs.ref }}\n```") in text


def test_a_piece_that_is_no_workflow_has_no_tables(tmp_path):
    from piecekit import lib_file
    store = make_assets(tmp_path, {"lib-x": {"a.js": lib_file("lib-x", 1, "a")}})
    text = catalogue.entry(load_pieces(store)["lib-x"])
    assert text == ("### lib-x v1\n\nInstalled at `.github/workflows/lib-x`.\n\n"
                    "**Purpose:** Test library.\n\n**Choose it when:** In tests.\n\n"
                    "**The repository supplies:** Nothing.\n")


def test_main_without_a_target_says_how_to_call_it(capsys):
    """It raised IndexError."""
    assert catalogue.main([]) == 2
    assert capsys.readouterr().err == (
        "usage: python3 -m repo_infra.catalogue <catalogue.md to write>\n")
