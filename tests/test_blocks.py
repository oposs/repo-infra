import json
import pathlib
import re

import pytest

from repo_infra.assemble import block_job_ids
from repo_infra.state import carries_a_path_filter

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
USES = re.compile(r"uses:\s*([\w.-]+/[\w.-]+)@(v\d+|\w+)")


def every_asset_file():
    for path in sorted(ASSETS.rglob("*")):
        if path.is_file() and path.suffix in (".yml", ".yaml"):
            yield path


def required_workflow_files():
    """Only the assets that end up behind a required check.

    The publish assets legitimately carry `paths: ['CHANGES.md']`: that is a
    push trigger and none of their jobs is a required context. Applying D13's
    rule to them would be wrong.
    """
    yield from sorted((ASSETS / "ci").glob("*.yml"))
    yield ASSETS / "workflows/changelog.yml"


@pytest.mark.parametrize("block", sorted(MANIFEST["ci_blocks"]))
def test_a_block_declares_exactly_the_jobs_it_contains(block):
    text = (ASSETS / "ci" / (block + ".yml")).read_text(encoding="utf-8")
    assert block_job_ids(text) == MANIFEST["ci_blocks"][block]["jobs"]


@pytest.mark.parametrize("path", list(required_workflow_files()), ids=lambda p: p.name)
def test_no_required_workflow_carries_a_path_filter(path):
    # D13: a workflow skipped by paths/branches filtering stays Pending forever
    # and blocks the pull request. A job skipped by a job-level `if:` reports
    # Success. Only the second is safe for a required check.
    text = path.read_text(encoding="utf-8")
    assert not carries_a_path_filter(text), "%s carries a paths filter" % path


def test_the_path_filter_check_catches_a_real_filter():
    text = "on:\n  push:\n    paths: ['src/**']\n"
    assert carries_a_path_filter(text)


def test_the_path_filter_check_ignores_a_comment_that_only_mentions_paths():
    text = "# Never add paths: or paths-ignore: to this workflow (spec D13).\n"
    assert not carries_a_path_filter(text)


def test_the_aggregator_fails_open_nowhere():
    text = (ASSETS / "ci/ci-aggregator.yml").read_text(encoding="utf-8")
    assert "if: always()" in text
    assert "needs: []" in text


def test_the_aggregator_has_no_name_so_its_context_is_its_job_id():
    # D14: renaming a required job silently un-requires the check.
    text = (ASSETS / "ci/ci-aggregator.yml").read_text(encoding="utf-8")
    body = text.split("ci-passed:", 1)[1]
    assert "\n    name:" not in body


def test_every_ci_block_named_by_detection_exists():
    detection = json.loads((ASSETS / "detection.json").read_text(encoding="utf-8"))
    for entry in detection["ecosystems"]:
        block = entry["ci_block"]
        assert block in MANIFEST["ci_blocks"], "%s: %s is not in the manifest" % (entry["id"], block)
        assert (ASSETS / "ci" / (block + ".yml")).is_file(), "%s: no such block file" % block


def test_no_two_blocks_declare_the_same_job_id():
    seen = {}
    for block, meta in MANIFEST["ci_blocks"].items():
        for job in meta["jobs"]:
            assert job not in seen, "%s and %s both declare job %r" % (seen[job], block, job)
            seen[job] = block


@pytest.mark.parametrize("path", list(every_asset_file()), ids=lambda p: p.name)
def test_every_asset_uses_a_manifest_pinned_major(path):
    for action, ref in USES.findall(path.read_text(encoding="utf-8")):
        if not ref.startswith("v"):
            continue  # dtolnay/rust-toolchain@stable is a branch, and correct
        assert action in MANIFEST["actions"], "%s uses %s, not in the manifest" % (path.name, action)
        assert MANIFEST["actions"][action] == ref, "%s uses %s@%s, manifest pins %s" % (
            path.name, action, ref, MANIFEST["actions"][action])


def test_every_non_yaml_asset_is_covered_by_a_test():
    # every_asset_file() only walks YAML. Anything else under assets/ needs its
    # own test file, or it ships unchecked.
    #   .mk -> tests/test_build_assets.py
    #   .m4 -> tests/test_container_m4.py
    others = {p.suffix for p in ASSETS.rglob("*") if p.is_file()} - {".yml", ".yaml", ".json", ".js"}
    assert others == {".mk", ".m4"}, "a new asset kind arrived with no test: %s" % others


def test_the_autotools_block_installs_only_the_fixed_host_toolchain():
    text = (ASSETS / "ci/ci-perl-autotools.yml").read_text(encoding="utf-8")
    assert "autoconf automake gettext podman" in text
    # D16: no per-repo package list, in any shape.
    assert "apt-packages" not in text
    assert "system_packages" not in text


def test_the_autotools_block_runs_make_test():
    text = (ASSETS / "ci/ci-perl-autotools.yml").read_text(encoding="utf-8")
    assert "make test" in text
    assert "make check" not in text


def test_the_autotools_block_no_longer_documents_a_bare_configure_limit():
    # D18 closed it: plain ./configure is driver mode, so the runner never
    # probes the project's system dependencies.
    text = (ASSETS / "ci/ci-perl-autotools.yml").read_text(encoding="utf-8")
    assert "Known limit" not in text
    assert "enable-pkgonly" not in text


def test_the_selftest_block_declares_exactly_its_one_job():
    text = (ASSETS / "ci/ci-repo-infra-selftest.yml").read_text(encoding="utf-8")
    assert block_job_ids(text) == MANIFEST["ci_blocks"]["ci-repo-infra-selftest"]["jobs"]
    assert block_job_ids(text) == ["repo-infra-selftest"]


def test_the_selftest_block_runs_only_the_container_marked_tests():
    # The marker is what keeps the ordinary pytest job sub-second. A selftest
    # job that ran the whole suite would duplicate it and hide its own cost.
    text = (ASSETS / "ci/ci-repo-infra-selftest.yml").read_text(encoding="utf-8")
    assert "-m container" in text


def test_both_blocks_install_a_byte_identical_host_toolchain():
    # D19: podman on an Ubuntu runner is the link the self-test exists to
    # exercise. If the two blocks drift, the self-test keeps passing against a
    # toolchain the autotools block no longer ships -- green and worthless.
    # This check uses full-line equality, not substring containment, to catch
    # indentation changes and appended packages.
    toolchain_lines = {}
    for name in ("ci/ci-perl-autotools.yml", "ci/ci-repo-infra-selftest.yml"):
        text = (ASSETS / name).read_text(encoding="utf-8")
        lines = [line for line in text.split('\n') if "apt-get install" in line]
        assert len(lines) == 1, f"{name}: expected 1 apt-get install line, found {len(lines)}"
        toolchain_lines[name] = lines[0]

    # Both files must have the exact same toolchain line, byte for byte.
    assert toolchain_lines["ci/ci-perl-autotools.yml"] == toolchain_lines["ci/ci-repo-infra-selftest.yml"]
