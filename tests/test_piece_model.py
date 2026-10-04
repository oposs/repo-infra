# tests/test_piece_model.py
import pytest
from piecekit import lib_file, make_assets, workflow_piece

from repo_infra import pieces


def test_loads_a_file_piece_with_its_header(tmp_path):
    assets = make_assets(tmp_path, {"ri-x": workflow_piece("ri-x", 2)})
    piece = pieces.load_pieces(assets)["ri-x"]
    assert piece.version == 2
    assert piece.target == ".github/workflows/ri-x.yml"
    assert piece.workflow
    assert piece.header["Purpose"] == "Test piece ri-x."
    assert piece.header["Call"].splitlines()[0] == "x:"
    assert piece.header["Call"].splitlines()[1] == "  uses: ./.github/workflows/ri-x.yml"


def test_loads_a_directory_piece(tmp_path):
    assets = make_assets(tmp_path, {"lib-x": {"a.js": lib_file("lib-x", 3, "a"),
                                              "b.js": lib_file("lib-x", 3, "b")}})
    piece = pieces.load_pieces(assets)["lib-x"]
    assert piece.kind == "dir"
    assert sorted(piece.files) == [".github/workflows/lib-x/a.js",
                                   ".github/workflows/lib-x/b.js"]
    assert not piece.workflow
    assert piece.version == 3


def test_files_of_a_directory_piece_must_agree_on_the_version(tmp_path):
    assets = make_assets(tmp_path, {"lib-x": {"a.js": lib_file("lib-x", 3, "a"),
                                              "b.js": lib_file("lib-x", 2, "b")}})
    with pytest.raises(pieces.PieceError, match="b.js"):
        pieces.load_pieces(assets)


def test_the_marker_must_name_the_piece(tmp_path):
    assets = make_assets(tmp_path, {"ri-x": workflow_piece("ri-y", 1)})
    with pytest.raises(pieces.PieceError, match="repo-infra: ri-x vN"):
        pieces.load_pieces(assets)


@pytest.mark.parametrize("text, problem", [
    ("# repo-infra: p v1\n#\n# Choose: x\n# Supplies: y\nname: p\n", "Purpose"),
    ("# repo-infra: p v1\n#\n# Purpose: x\n# Colour: y\n", "Colour"),
    ("# repo-infra: p v1\n#\n# Purpose: x\n# Purpose: y\n", "twice"),
    ("name: p\n# repo-infra: p v1\n# Purpose: x\n", "Choose"),
    ("# other comment\n# repo-infra: p v1\n", "first comment line"),
])
def test_header_problems_are_named(text, problem):
    with pytest.raises(pieces.PieceError, match=problem):
        pieces.parse_header(text, "#")


def test_a_field_continues_on_indented_lines_and_ends_at_an_empty_comment():
    text = ("dnl repo-infra: p v1\ndnl\ndnl Purpose: one\ndnl   two\ndnl Choose: c\n"
            "dnl Supplies: s\ndnl\ndnl Prose that is not a field.\n")
    assert pieces.parse_header(text, "dnl") == {"Purpose": "one\ntwo", "Choose": "c",
                                                 "Supplies": "s"}


def test_published_maps_every_recorded_version_to_its_repository_path(tmp_path):
    old = workflow_piece("ri-x", 1, body="old")
    assets = make_assets(tmp_path, {"ri-x": workflow_piece("ri-x", 2)},
                         history=[("ri-x", None, old)])
    published = pieces.load_published(assets)["ri-x"][".github/workflows/ri-x.yml"]
    assert sorted(published) == [1, 2]


def test_upgrade_notes_cover_every_version_crossed(tmp_path):
    assets = make_assets(tmp_path, {"ri-x": workflow_piece("ri-x", 3)},
                         history=[("ri-x", None, workflow_piece("ri-x", 2, body="b")),
                                  ("ri-x", None, workflow_piece("ri-x", 1, body="a"))])
    assert pieces.upgrade_notes("ri-x", 1, 3, assets) == [
        (2, "Notes for ri-x v2."), (3, "Notes for ri-x v3.")]


def test_a_missing_section_says_so(tmp_path):
    assets = make_assets(tmp_path, {"ri-x": workflow_piece("ri-x", 2)})
    assert pieces.upgrade_notes("ri-x", 0, 2, assets)[0] == (
        1, "(no upgrade notes for this version)")


# --- deferred Task 2 minors --------------------------------------------------

def _manifest(assets):
    import json
    return json.loads((assets / "manifest.json").read_text(encoding="utf-8"))


def _write_manifest(assets, manifest):
    import json
    (assets / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_a_piece_whose_file_is_missing_is_a_piece_error(tmp_path):
    """It raised FileNotFoundError, which reads as a crash, not a store defect."""
    assets = make_assets(tmp_path, {"ri-x": workflow_piece("ri-x", 1)})
    (assets / "pieces/ri-x/ri-x.yml").unlink()
    with pytest.raises(pieces.PieceError, match="ri-x: pieces/ri-x/ri-x.yml is missing"):
        pieces.load_pieces(assets)


def test_a_directory_piece_whose_folder_is_missing_is_a_piece_error(tmp_path):
    assets = make_assets(tmp_path, {"lib-x": {"a.js": lib_file("lib-x", 1, "a")}})
    (assets / "pieces/lib-x/lib-x/a.js").unlink()
    (assets / "pieces/lib-x/lib-x").rmdir()
    with pytest.raises(pieces.PieceError, match="lib-x: pieces/lib-x/lib-x is missing"):
        pieces.load_pieces(assets)


@pytest.mark.parametrize("key", ["header", "target"])
def test_a_manifest_entry_without_a_key_it_needs_is_a_piece_error(tmp_path, key):
    """It raised KeyError."""
    assets = make_assets(tmp_path, {"lib-x": {"a.js": lib_file("lib-x", 1, "a")}})
    manifest = _manifest(assets)
    del manifest["pieces"]["lib-x"][key]
    _write_manifest(assets, manifest)
    with pytest.raises(pieces.PieceError, match=f"lib-x: the manifest entry lacks {key}"):
        pieces.load_pieces(assets)


def test_a_word_that_starts_with_the_comment_token_is_no_comment():
    """`dnlPurpose:` is an m4 word, not `dnl` followed by a field."""
    text = "dnl repo-infra: p v1\ndnl\ndnlPurpose: x\ndnl Choose: c\ndnl Supplies: s\n"
    with pytest.raises(pieces.PieceError, match="Purpose"):
        pieces.parse_header(text, "dnl")


def test_a_hash_comment_needs_no_space():
    text = "#repo-infra: p v1\n#\n#Purpose: x\n#Choose: c\n#Supplies: s\n"
    assert pieces.parse_header(text, "#") == {"Purpose": "x", "Choose": "c", "Supplies": "s"}


def test_needs_and_core_come_from_the_header_and_the_manifest(tmp_path):
    header = "# Pieces: lib-x, ri-y\n"
    assets = make_assets(tmp_path, {"ri-x": workflow_piece("ri-x", 1, header=header),
                                    "lib-x": {"a.js": lib_file("lib-x", 1, "a")}},
                         core=("lib-x",))
    loaded = pieces.load_pieces(assets)
    assert loaded["ri-x"].needs == ["lib-x", "ri-y"]
    assert loaded["lib-x"].needs == []
    assert (loaded["ri-x"].core, loaded["lib-x"].core) == (False, True)


def test_published_maps_the_files_of_a_directory_piece(tmp_path):
    assets = make_assets(tmp_path, {"lib-x": {"a.js": lib_file("lib-x", 2, "a2")}},
                         history=[("lib-x", "a.js", lib_file("lib-x", 1, "a1")),
                                  ("lib-x", "gone.js", lib_file("lib-x", 1, "g1"))])
    published = pieces.load_published(assets)["lib-x"]
    assert {path: sorted(v) for path, v in published.items()} == {
        ".github/workflows/lib-x/a.js": [1, 2],
        ".github/workflows/lib-x/gone.js": [1]}


def test_changes_sections_split_on_version_headings():
    text = "# p\n\n## v3\n\nThree.\n\n## v2\n\nTwo.\nMore.\n\n## v1\n"
    assert pieces.changes_sections(text) == {3: "Three.", 2: "Two.\nMore.", 1: ""}


def test_upgrade_notes_of_a_directory_piece(tmp_path):
    assets = make_assets(tmp_path, {"lib-x": {"a.js": lib_file("lib-x", 2, "a2")}},
                         history=[("lib-x", "a.js", lib_file("lib-x", 1, "a1"))])
    assert pieces.upgrade_notes("lib-x", 1, 2, assets) == [(2, "Notes for lib-x v2.")]


def test_upgrade_notes_without_a_changes_file(tmp_path):
    assets = make_assets(tmp_path, {"ri-x": workflow_piece("ri-x", 2)})
    (assets / "pieces/ri-x/CHANGES.md").unlink()
    assert pieces.upgrade_notes("ri-x", 1, 2, assets) == [
        (2, "(no upgrade notes for this version)")]


def test_a_directory_piece_whose_header_file_is_missing_is_a_piece_error(tmp_path):
    assets = make_assets(tmp_path, {"lib-x": {"a.js": lib_file("lib-x", 1, "a")}})
    manifest = _manifest(assets)
    manifest["pieces"]["lib-x"]["header"] = "nothere.js"
    _write_manifest(assets, manifest)
    with pytest.raises(pieces.PieceError, match="lib-x: the header file nothere.js"):
        pieces.load_pieces(assets)
