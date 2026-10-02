"""The static musl CI add-on and the opt-in CI seam it arrives with (D22)."""

import json
import os
import pathlib
import re
import stat
import subprocess

import pytest
import yaml

from repo_infra.assemble import (
    AssemblyError,
    assemble_ci,
    block_job_ids,
    ci_addon_blocks,
    render_all,
)
from repo_infra.detect import Detection, DetectResult
from repo_infra.markers import parse_markers

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
BLOCK = ASSETS / "ci/ci-rust-musl.yml"

CI_YML = ".github/workflows/ci.yml"


def rust_result():
    """What detection makes of a repository whose only signal is Cargo.toml."""
    return Detection.load(ASSETS / "detection.json").detect(
        ROOT / "tests/fixtures/repo-rust")


def musl_job(ci=("ci-rust-musl",)):
    result = rust_result()
    rendered = render_all(ASSETS, result, MANIFEST, ci=list(ci))
    return yaml.safe_load(rendered[CI_YML])


def piece_job():
    """The rust-musl job as the piece ships it."""
    path = ASSETS / "pieces/ri-ci-rust-musl/ri-ci-rust-musl.yml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"]["rust-musl"]


def verify_script():
    """The `run:` body of the linkage assertion, as the runner would see it."""
    job = piece_job()
    step = next(s for s in job["steps"] if s.get("name", "").startswith("Verify"))
    # The runner expands workflow expressions before bash ever sees them.
    return re.sub(r"\$\{\{[^}]*\}\}", "x86_64-unknown-linux-musl", step["run"])


# --- the seam: an opt-in CI block -------------------------------------------


def test_the_addon_is_absent_unless_the_repository_asks_for_it():
    """D22: a library crate has no binary to link statically, and an aarch64
    cross-build costs real CI minutes. Detection sees Cargo.toml, not intent."""
    doc = musl_job(ci=())
    assert "rust-musl" not in doc["jobs"]
    assert set(doc["jobs"]) == {"lib", "rust-plan", "rust-check", "rust-test", "ci-passed", "release-pr-current"}


def test_naming_the_addon_installs_it_and_makes_it_required():
    # The user's ruling: this is a required check, not advisory. Membership in
    # ci-passed's generated `needs:` list is the whole of that guarantee -- the
    # ruleset requires exactly one context (D2) and this is how a job reaches it.
    doc = musl_job()
    assert "rust-musl" in doc["jobs"]
    assert "rust-musl" in doc["jobs"]["ci-passed"]["needs"]


def test_the_addon_lands_after_the_detected_blocks():
    # Adding an add-on must not reorder the jobs a repository already has, or
    # every converted Rust repository shows a spurious diff on its next apply.
    text = assemble_ci(ASSETS, rust_result().blocks + ["ci-rust-musl"], MANIFEST)
    assert text.index("  rust-check:") < text.index("  rust-musl:")
    assert text.index("  rust-musl:") < text.index("  ci-passed:")


def test_the_addon_carries_its_own_marker_at_the_declared_version():
    # D11: one marker per block, so upgrading ci-rust never touches this one.
    text = assemble_ci(ASSETS, ["ci-rust", "ci-rust-musl"], MANIFEST)
    assert ("ci-rust-musl", MANIFEST["ci_blocks"]["ci-rust-musl"]["version"]) in [
        (m.asset, m.version) for m in parse_markers(text)]


def test_the_block_declares_exactly_the_jobs_it_contains():
    text = BLOCK.read_text(encoding="utf-8")
    assert block_job_ids(text) == MANIFEST["ci_blocks"]["ci-rust-musl"]["jobs"]
    assert block_job_ids(text) == ["rust-musl"]


def test_the_assembled_workflow_is_loadable_yaml():
    # The block is pasted into a frame at a fixed indent, and it carries a
    # multi-line shell script. A block that is valid alone but wrong by one
    # space produces a file GitHub silently refuses to run, while every string
    # assertion in this file still passes.
    doc = musl_job()
    assert set(doc["jobs"]) == {
        "lib", "rust-plan", "rust-check", "rust-test", "rust-musl", "ci-passed", "release-pr-current"}


def test_an_addon_for_an_ecosystem_this_repository_does_not_have_is_refused():
    # Rendered, it would install a job that cannot pass, and a required check
    # that cannot pass blocks every pull request in the repository.
    python_result = Detection.load(ASSETS / "detection.json").detect(
        ROOT / "tests/fixtures/repo-python")
    with pytest.raises(AssemblyError, match="requires the rust ecosystem"):
        render_all(ASSETS, python_result, MANIFEST, ci=["ci-rust-musl"])


def test_an_addon_that_detection_already_installs_is_refused():
    # Two blocks declaring `rust-check:` make ci.yml invalid YAML, so *no* job
    # runs and the required check never reports at all -- louder than a failure
    # and much harder to read.
    with pytest.raises(AssemblyError, match="is not an opt-in block"):
        ci_addon_blocks(rust_result(), ["ci-rust"], MANIFEST)


def test_naming_the_same_addon_twice_is_refused():
    result = DetectResult(ecosystems=["rust"], blocks=["ci-lib", "ci-rust"])
    with pytest.raises(AssemblyError, match="already installed"):
        ci_addon_blocks(result, ["ci-rust-musl", "ci-rust-musl"], MANIFEST)


def test_an_addon_absent_from_the_manifest_is_refused():
    with pytest.raises(AssemblyError, match="ci-nonexistent"):
        ci_addon_blocks(rust_result(), ["ci-nonexistent"], MANIFEST)




def test_every_ci_block_is_either_detected_or_declared_optional():
    """An orphan block ships unreachable: nothing detects it and nothing may
    name it, so it is tested forever and installed never."""
    detection = json.loads((ASSETS / "detection.json").read_text(encoding="utf-8"))
    detected = {e["ci_block"] for e in detection["ecosystems"]} | {"ci-lib"}
    for name, meta in MANIFEST["ci_blocks"].items():
        assert name in detected or meta.get("optional"), (
            "%s is neither named by detection nor marked optional" % name)


def test_an_optional_block_names_its_ecosystem_or_none():
    """D23 widened D22's rule. A man page has no ecosystem, so an optional
    block may omit `requires` and then fits any. When it does name one, the
    name must be an ecosystem detection knows, or the refusal in
    ci_addon_blocks would fire on every repository that names the block."""
    detection = json.loads((ASSETS / "detection.json").read_text(encoding="utf-8"))
    known = {e["id"] for e in detection["ecosystems"]}
    for name, meta in MANIFEST["ci_blocks"].items():
        if not meta.get("optional") or "requires" not in meta:
            continue
        assert meta["requires"] in known, "%s requires unknown ecosystem %r" % (
            name, meta["requires"])


# --- the block itself --------------------------------------------------------


def test_the_matrix_is_both_linux_musl_targets():
    job = piece_job()
    assert job["strategy"]["matrix"]["target"] == [
        "x86_64-unknown-linux-musl", "aarch64-unknown-linux-musl"]


def test_one_target_failing_does_not_cancel_the_other():
    # Which of the two broke is the whole answer; fail-fast discards half of it.
    assert piece_job()["strategy"]["fail-fast"] is False


def test_the_build_goes_through_cross_not_a_bare_cargo_target_build():
    # `ring` needs the right assembler for the target and `zstd-sys` needs a C
    # compiler for it. cross's images carry both; the runner carries neither.
    runs = [s.get("run", "") for s in piece_job()["steps"]]
    build = next(r for r in runs if "--release" in r and "--target" in r)
    assert "cross build" in build
    assert "cargo build" not in build


def test_the_build_asks_for_a_static_crt():
    runs = [s.get("run", "") for s in piece_job()["steps"]]
    build = next(r for r in runs if "cross build" in r)
    assert 'RUSTFLAGS="-C target-feature=+crt-static"' in build


def test_cross_is_pinned_to_an_exact_version():
    # A cross-compile is the thing least likely to be rehearsed locally, so a
    # break arrives in a pull request innocent of it. `main` would do exactly
    # that.
    runs = [s.get("run", "") for s in piece_job()["steps"]]
    install = next(r for r in runs if "cargo install cross" in r)
    assert "--version 0.2.5" in install
    assert "--locked" in install


def test_the_toolchain_stays_a_channel_reference():
    # references/conventions.md: `@stable` tracks the toolchain channel, not a
    # tagged release of the action, and dependabot correctly leaves branch
    # references alone. Pinning it freezes Rust to the day of the pin.
    uses = [s.get("uses", "") for s in piece_job()["steps"]]
    assert "dtolnay/rust-toolchain@stable" in uses


def test_the_block_names_no_project_specific_binary():
    # oxutrm's proven job passes `--bin oxutrm`. The standard cannot know a
    # name, so it must derive the list instead of carrying one.
    text = BLOCK.read_text(encoding="utf-8")
    assert "--bin " not in text
    assert "cargo metadata" in text


def test_the_objdump_half_is_guarded_so_it_skips_where_the_tool_is_absent():
    # This guard is why the check is portable across runner images: without it
    # the job errors on an image with no llvm-objdump rather than falling back
    # to the `file` assertion alone.
    script = verify_script()
    objdump = next(line for line in script.splitlines() if "llvm-objdump" in line
                   and not line.strip().startswith("#"))
    assert "command -v llvm-objdump" in objdump


# --- the linkage assertion, run for real -------------------------------------
#
# Substring assertions cannot check this step: its requirement is behavioural
# (a dynamically linked binary must fail the job, a library-only workspace must
# not) and the script contains every word either way. So the step's own shell
# runs against a throwaway tree with stand-in `cargo`, `jq` and `file` on PATH.


def _stub(directory, name, body):
    path = directory / name
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def run_verify(tmp_path, bin_names, built, file_says="statically linked"):
    """Run the verify step against a fake build tree.

    `bin_names` is what `cargo metadata` reports; `built` is which of those
    actually landed in target/<triple>/release; `file_says` is what `file`
    reports about each one.
    """
    tree = tmp_path / "tree"
    release = tree / "target/x86_64-unknown-linux-musl/release"
    release.mkdir(parents=True)
    for name in built:
        (release / name).write_bytes(b"\x7fELF")

    stubs = tmp_path / "bin"
    stubs.mkdir()
    # `cargo metadata` emits the JSON; the real jq then does the filtering, so
    # the jq filter in the block is exercised rather than stubbed out.
    packages = {"packages": [{"targets": [
        {"name": n, "kind": ["bin"]} for n in bin_names] + [
        {"name": "thelib", "kind": ["lib"]}]}]}
    _stub(stubs, "cargo", "cat <<'EOF'\n%s\nEOF\n" % json.dumps(packages))
    _stub(stubs, "file", 'echo "$1: ELF 64-bit LSB executable, %s"\n' % file_says)
    # llvm-objdump deliberately absent: the guarded half must skip, not error.

    env = dict(os.environ, PATH="%s:%s" % (stubs, os.environ["PATH"]))
    return subprocess.run(["bash", "-c", verify_script()], cwd=tree, env=env,
                          capture_output=True, text=True)


def test_a_statically_linked_binary_passes(tmp_path):
    done = run_verify(tmp_path, ["app"], ["app"])
    assert done.returncode == 0, done.stderr + done.stdout
    assert "verified 1 of 1" in done.stdout


def test_a_dynamically_linked_binary_fails_the_job(tmp_path):
    # The reason the step exists: `crt-static` is a hint the linker may ignore,
    # and a binary that only runs on the machine that built it fails at the far
    # end, on a host nobody is watching.
    done = run_verify(tmp_path, ["app"], ["app"],
                      file_says="dynamically linked, interpreter /lib/ld.so")
    assert done.returncode == 1
    assert "is not statically linked" in done.stdout


def test_a_library_only_workspace_passes_without_a_linkage_check(tmp_path):
    # A crate with no binary has nothing to link statically. The build still
    # proved it compiles for musl, so this is a pass, not a failure -- which is
    # what lets the add-on be named by a workspace that mixes libs and bins.
    done = run_verify(tmp_path, [], [])
    assert done.returncode == 0, done.stderr + done.stdout
    assert "no binary targets" in done.stdout


def test_declared_binaries_that_were_all_missing_fail_the_job(tmp_path):
    # Otherwise a build that silently produced nothing reports success by
    # saying nothing at all -- green, and testing exactly zero binaries.
    done = run_verify(tmp_path, ["app", "helper"], [])
    assert done.returncode == 1
    assert "produced none of them" in done.stdout


def test_a_binary_behind_required_features_is_skipped_not_failed(tmp_path):
    # `required-features` bins are not produced by a plain --workspace build.
    done = run_verify(tmp_path, ["app", "extra"], ["app"])
    assert done.returncode == 0, done.stderr + done.stdout
    assert "verified 1 of 2" in done.stdout
