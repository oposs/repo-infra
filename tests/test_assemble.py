import json
import pathlib

import pytest

from repo_infra.assemble import AssemblyError, assemble_ci, block_job_ids

HERE = pathlib.Path(__file__).resolve().parent
MINI = HERE / "fixtures/assets-mini"


def manifest():
    return json.loads((MINI / "manifest.json").read_text(encoding="utf-8"))


def test_one_block_lands_between_the_frame_and_the_aggregator():
    text = assemble_ci(MINI, ["ci-alpha"], manifest())
    assert text.startswith("name: CI\n# repo-infra: ci v1\n")
    assert "  # repo-infra: ci-alpha v1\n  a-one:\n" in text
    assert text.rstrip("\n").endswith("run: exit 1")


def test_the_needs_list_is_the_union_of_the_blocks_in_order():
    text = assemble_ci(MINI, ["ci-alpha", "ci-beta"], manifest())
    assert "    needs: [a-one, b-one, b-two]" in text
    assert "needs: []" not in text


def test_every_block_carries_its_own_marker():
    text = assemble_ci(MINI, ["ci-alpha", "ci-beta"], manifest())
    assert "  # repo-infra: ci-alpha v1" in text
    assert "  # repo-infra: ci-beta v2" in text


def test_assembly_is_byte_identical_on_a_re_run():
    assert assemble_ci(MINI, ["ci-beta"], manifest()) == assemble_ci(MINI, ["ci-beta"], manifest())


def test_a_missing_block_file_is_an_error_not_a_skip():
    with pytest.raises(AssemblyError, match="ci-missing"):
        assemble_ci(MINI, ["ci-missing"], manifest())


def test_a_block_absent_from_the_manifest_is_an_error():
    (MINI / "ci/ci-orphan.yml").write_text("  orphan:\n", encoding="utf-8")
    try:
        with pytest.raises(AssemblyError, match="ci-orphan"):
            assemble_ci(MINI, ["ci-orphan"], manifest())
    finally:
        (MINI / "ci/ci-orphan.yml").unlink()


def test_an_aggregator_without_the_needs_placeholder_is_an_error(tmp_path):
    broken = tmp_path / "ci"
    broken.mkdir()
    for name in ("ci-frame", "ci-alpha"):
        (broken / (name + ".yml")).write_text((MINI / "ci" / (name + ".yml")).read_text(), encoding="utf-8")
    (broken / "ci-aggregator.yml").write_text("  ci-passed:\n    needs: [already-filled]\n", encoding="utf-8")
    with pytest.raises(AssemblyError, match="needs"):
        assemble_ci(tmp_path, ["ci-alpha"], manifest())


def test_block_job_ids_reads_only_top_level_job_keys():
    text = (MINI / "ci/ci-beta.yml").read_text(encoding="utf-8")
    assert block_job_ids(text) == ["b-one", "b-two"]
