import json
import pathlib

from repo_infra.assemble import render_all
from repo_infra.detect import Detection

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"


def test_this_repository_is_what_the_assembler_would_install():
    """The shipped asset and the file that releases this repo cannot drift apart.

    repo-infra gets no exemption from its own standard, so its .github/ is the
    assembler's output rather than a hand-maintained copy. If this test fails,
    somebody edited an installed file instead of its asset.
    """
    manifest = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
    result = Detection.load(ASSETS / "detection.json").detect(ROOT)
    # D19: repo-infra ships its own assets, so it detects its own self-test
    # ecosystem. This list changing is the proof the wiring is real.
    assert result.ecosystems == ["claude-plugin", "python", "repo-infra"]

    for path, expected in sorted(render_all(ASSETS, result, manifest).items()):
        installed = ROOT / path
        assert installed.is_file(), "%s is missing from this repository" % path
        assert installed.read_text(encoding="utf-8") == expected, (
            "%s differs from its asset -- edit the asset, then re-render" % path)


def test_repo_infra_json_ecosystems_matches_detection():
    """.github/repo-infra.json's "ecosystems" is the detected list, recorded so a
    later run can tell "still this" from "detection changed underneath me"
    (skills/repo-infra/references/conventions.md). It is not assembler output, so
    nothing else re-renders it if detection moves on -- this is the guard.
    """
    config = json.loads((ROOT / ".github/repo-infra.json").read_text(encoding="utf-8"))
    result = Detection.load(ASSETS / "detection.json").detect(ROOT)
    assert config["ecosystems"] == result.ecosystems
