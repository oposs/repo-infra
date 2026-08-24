import itertools
import pathlib

import pytest

from repo_infra.detect import Detection

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
MINI = HERE / "fixtures/detection-mini.json"
REAL = ROOT / "skills/repo-infra/assets/detection.json"


def mini(tmp_path, files):
    for name, body in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return Detection.load(MINI).detect(tmp_path)


def test_a_repo_with_no_signals_still_gets_the_workflow_library_block(tmp_path):
    result = mini(tmp_path, {})
    assert result.ecosystems == []
    assert result.blocks == ["ci-lib"]


def test_one_signal_selects_one_ecosystem(tmp_path):
    result = mini(tmp_path, {"alpha.toml": 'version = "1.0.0"\n'})
    assert result.ecosystems == ["alpha"]
    assert result.blocks == ["ci-lib", "ci-alpha"]
    assert result.version_files[0]["path"] == "alpha.toml"


def test_a_none_signal_suppresses_a_match(tmp_path):
    result = mini(tmp_path, {"beta.json": "{}\n", "not-beta": ""})
    assert result.ecosystems == []


def test_two_ecosystems_produce_one_sorted_block_list(tmp_path):
    result = mini(tmp_path, {"alpha.toml": "\n", "beta.json": "{}\n"})
    assert result.ecosystems == ["alpha", "beta"]
    assert result.blocks == ["ci-lib", "ci-alpha", "ci-beta"]


def test_a_directory_signal_needs_a_directory(tmp_path):
    (tmp_path / "bin").mkdir()
    result = mini(tmp_path, {})
    assert result.candidates == ["man-pages"]


def test_an_ambiguity_is_reported_and_does_not_stop_detection(tmp_path):
    result = mini(tmp_path, {"alpha.toml": "\n", "beta.json": "{}\n"})
    assert [a["id"] for a in result.ambiguities] == ["alpha-or-beta"]
    assert "authoritative" in result.ambiguities[0]["question"]


def test_detection_is_deterministic(tmp_path):
    files = {"alpha.toml": "\n", "beta.json": "{}\n"}
    assert mini(tmp_path, files).blocks == mini(tmp_path, files).blocks


# --- the real detection file ------------------------------------------------

def test_the_real_file_detects_this_repository_as_a_claude_plugin():
    result = Detection.load(REAL).detect(HERE / "fixtures/repo-claude-plugin")
    assert result.ecosystems == ["claude-plugin"]
    assert result.blocks == ["ci-lib", "ci-claude-plugin"]


def test_the_real_file_detects_a_python_repository():
    result = Detection.load(REAL).detect(HERE / "fixtures/repo-python")
    assert result.ecosystems == ["python"]


def _node_lockfile_combinations():
    """Generate test cases for all 7 lockfile combinations.

    Lockfiles: pnpm, bun, npm. Single lockfile selects its block; any two or
    three select no block and report ambiguity(ies) for each conflicting pair.
    """
    lockfiles = {
        "pnpm": ("pnpm-lock.yaml", "ci-node-pnpm"),
        "bun": ("bun.lock", "ci-node-bun"),
        "npm": ("package-lock.json", None),
    }

    # Fixture name mapping for multi-lockfile combinations (keys sorted for determinism)
    fixture_names = {
        ("bun",): "repo-node-bun",
        ("npm",): "repo-node-npm",
        ("pnpm",): "repo-node-pnpm",
        ("bun", "npm"): "repo-node-bun-npm",
        ("bun", "pnpm"): "repo-node-pnpm-bun",
        ("npm", "pnpm"): "repo-node-pnpm-npm",
        ("bun", "npm", "pnpm"): "repo-node-ambiguous",
    }

    # Ambiguity mapping: which managers conflict (keys sorted for determinism)
    ambiguity_map = {
        ("bun", "npm"): "node-bun-vs-npm",
        ("bun", "pnpm"): "node-pnpm-vs-bun",
        ("npm", "pnpm"): "node-lockfiles",
    }

    cases = []

    # Derive manager names from lockfiles dict (sorted for determinism).
    # Adding a fourth manager extends coverage automatically.
    manager_names = sorted(lockfiles.keys())

    # Generate all non-empty combinations of lockfiles (2^n - 1 cases where n = len(lockfiles))
    for r in range(1, len(lockfiles) + 1):
        for combo in itertools.combinations(manager_names, r):
            # Normalize combo by sorting it for consistent dict lookup
            sorted_combo = tuple(sorted(combo))
            fixture = fixture_names[sorted_combo]

            # Single lockfile: select its block, no ambiguities
            if len(combo) == 1:
                manager = combo[0]
                expected_blocks = ["ci-lib"]
                if lockfiles[manager][1]:
                    expected_blocks.append(lockfiles[manager][1])
                expected_ambiguities = []
            else:
                # Multiple lockfiles: no block, ambiguities for each pair
                expected_blocks = ["ci-lib"]
                expected_ambiguities = []
                for pair in itertools.combinations(combo, 2):
                    sorted_pair = tuple(sorted(pair))
                    expected_ambiguities.append(ambiguity_map[sorted_pair])

            cases.append((fixture, expected_blocks, expected_ambiguities))

    return cases


@pytest.mark.parametrize(
    "fixture_name,expected_blocks,expected_ambiguity_ids",
    _node_lockfile_combinations(),
)
def test_node_lockfile_combinations(fixture_name, expected_blocks, expected_ambiguity_ids):
    """Test that node lockfile combinations produce correct blocks and ambiguities.

    Covers all 7 combinations: 3 single lockfiles (pnpm, bun, npm), 3 pairs, 1 trio.
    Exactly one lockfile selects its block with no ambiguity. Any two or three
    lockfiles select no block and report ambiguities for each conflicting pair.
    """
    result = Detection.load(REAL).detect(HERE / f"fixtures/{fixture_name}")
    assert result.blocks == expected_blocks
    ambiguity_ids = sorted([a["id"] for a in result.ambiguities])
    assert ambiguity_ids == sorted(expected_ambiguity_ids)


def test_the_real_file_detects_both_claude_plugin_and_python():
    result = Detection.load(REAL).detect(HERE / "fixtures/repo-both")
    assert result.ecosystems == ["claude-plugin", "python"]
    assert result.blocks == ["ci-lib", "ci-claude-plugin", "ci-python"]


def test_the_real_file_detects_empty_repository_as_no_ecosystems():
    result = Detection.load(REAL).detect(HERE / "fixtures/repo-empty")
    assert result.ecosystems == []
    assert result.blocks == ["ci-lib"]


def test_the_real_file_detects_a_rust_repository():
    result = Detection.load(REAL).detect(HERE / "fixtures/repo-rust")
    assert result.ecosystems == ["rust"]
    assert result.blocks == ["ci-lib", "ci-rust"]


def test_the_real_file_detects_a_go_repository_with_no_version_file():
    result = Detection.load(REAL).detect(HERE / "fixtures/repo-go")
    assert result.ecosystems == ["go"]
    assert result.version_files == []


def test_detect_does_not_share_mutable_references():
    """Mutations to one result must not affect subsequent detect() calls."""
    detection = Detection.load(REAL)
    result1 = detection.detect(HERE / "fixtures/repo-python")
    result2 = detection.detect(HERE / "fixtures/repo-python")

    # Mutate the first result's version_files and ambiguities
    if result1.version_files:
        result1.version_files[0]["mutated"] = True
    if result1.ambiguities:
        result1.ambiguities[0]["mutated"] = True

    # Second result must be unaffected by the mutation
    assert all("mutated" not in vf for vf in result2.version_files)
    assert all("mutated" not in amb for amb in result2.ambiguities)


def test_detect_does_not_share_mutable_ambiguity_references():
    """The repo-python fixture above has no ambiguities, so it never exercises
    the deepcopy on `ambiguities` -- only the one on `version_files`. This
    fixture matches node-lockfiles, so the ambiguity mutation is live here."""
    detection = Detection.load(REAL)
    result1 = detection.detect(HERE / "fixtures/repo-node-ambiguous")
    result2 = detection.detect(HERE / "fixtures/repo-node-ambiguous")

    assert result1.ambiguities  # the fixture must actually trigger one
    result1.ambiguities[0]["mutated"] = True

    assert all("mutated" not in amb for amb in result2.ambiguities)


def test_an_autotools_perl_repository_gets_the_autotools_block():
    result = Detection.load(REAL).detect(HERE / "fixtures/repo-perl-autotools")
    assert result.blocks == ["ci-lib", "ci-perl-autotools"]


def test_a_makefile_pl_repository_gets_the_makefile_pl_block():
    result = Detection.load(REAL).detect(HERE / "fixtures/repo-perl-mkpl")
    assert result.blocks == ["ci-lib", "ci-perl-mkpl"]


def test_an_autotools_repository_that_also_has_makefile_pl_is_not_both():
    (HERE / "fixtures/repo-perl-autotools/Makefile.PL").write_text("1;\n", encoding="utf-8")
    try:
        result = Detection.load(REAL).detect(HERE / "fixtures/repo-perl-autotools")
        assert result.blocks == ["ci-lib", "ci-perl-autotools"]
    finally:
        (HERE / "fixtures/repo-perl-autotools/Makefile.PL").unlink()


def test_a_checkmk_plugin_gets_the_checkmk_block():
    result = Detection.load(REAL).detect(HERE / "fixtures/repo-checkmk")
    assert result.ecosystems == ["checkmk-plugin"]
    assert result.blocks == ["ci-lib", "ci-checkmk-plugin"]


def test_a_checkmk_plugin_has_no_version_file():
    """mkp-builder takes the version from the release tag, so there is nothing
    in the tree to rewrite. CHANGES.md stays the single source of truth (D5)
    and the publisher has nothing to cross-check -- correct, not a gap."""
    result = Detection.load(REAL).detect(HERE / "fixtures/repo-checkmk")
    assert result.version_files == []


def test_autotools_writes_the_version_file_not_configure_ac():
    import json
    import pathlib
    assets = pathlib.Path(__file__).resolve().parents[1] / "skills/repo-infra/assets"
    detection = json.loads((assets / "detection.json").read_text(encoding="utf-8"))
    eco = [e for e in detection["ecosystems"] if e["id"] == "perl-autotools"][0]
    assert [spec["path"] for spec in eco["version_files"]] == ["VERSION"]


def test_the_version_file_spec_matches_a_real_version_file():
    import json
    import pathlib
    import re
    assets = pathlib.Path(__file__).resolve().parents[1] / "skills/repo-infra/assets"
    detection = json.loads((assets / "detection.json").read_text(encoding="utf-8"))
    eco = [e for e in detection["ecosystems"] if e["id"] == "perl-autotools"][0]
    spec = eco["version_files"][0]
    # The shape SmokePing and every hin-access-suite project ships.
    assert re.search(spec["pattern"], "2.9.0\n", re.M)
    # And the verify template, with the version escaped and the trailing
    # (?![0-9]) appended the way bump.js does it (pattern.replace + append,
    # not "or True" -- this is the guard that stops 2.9.1 from verifying
    # against 2.9.10).
    verify = spec["verify"].replace("$VERSION", re.escape("2.9.1")) + "(?![0-9])"
    assert re.search(verify, "2.9.1\n", re.M)
    assert not re.search(verify, "2.9.10\n", re.M)


def test_the_real_file_detects_a_repository_that_ships_repo_infras_assets():
    # D19: "this repository ships repo-infra's own assets" is a real,
    # file-detectable property. Exactly one repository has it, by the settled
    # four-repo split -- and any repository that vendored those assets would
    # want the self-test too.
    result = Detection.load(REAL).detect(HERE / "fixtures/repo-selfhost")
    assert "repo-infra" in result.ecosystems
    assert "ci-repo-infra-selftest" in result.blocks


def test_an_ordinary_repository_does_not_get_the_selftest():
    # The signal must be the manifest itself, not merely a `skills/` directory.
    result = Detection.load(REAL).detect(HERE / "fixtures/repo-claude-plugin")
    assert "repo-infra" not in result.ecosystems
    assert "ci-repo-infra-selftest" not in result.blocks
