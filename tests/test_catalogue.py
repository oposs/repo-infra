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
