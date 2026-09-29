"""ci-rust v2 (D24): a planned matrix instead of one workspace-wide run."""

import json
import pathlib

import yaml

from repo_infra.assemble import assemble_ci

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))


def jobs():
    return yaml.safe_load(assemble_ci(ASSETS, ["ci-rust"], MANIFEST))["jobs"]


def run_lines(job):
    return "\n".join(step.get("run", "") for step in job["steps"])


def test_the_plan_is_a_required_job():
    # If rust-plan fails, both matrix jobs are skipped, and ci-passed counts a
    # skipped need as green. rust-plan in ci-passed's needs is what stops a
    # run whose Rust checks never ran from going green.
    assert jobs()["ci-passed"]["needs"] == ["rust-plan", "rust-check", "rust-test"]


def test_the_matrix_jobs_wait_for_the_plan_and_read_its_lists():
    j = jobs()
    for name, output in (("rust-check", "lint"), ("rust-test", "test")):
        assert j[name]["needs"] == "rust-plan"
        assert j[name]["strategy"]["matrix"]["package"] == (
            "${{ fromJSON(needs.rust-plan.outputs.%s) }}" % output)
        assert j[name]["strategy"]["fail-fast"] is False


def test_the_plan_reads_cargo_metadata_without_resolving_dependencies():
    assert "cargo metadata --no-deps --format-version 1" in run_lines(jobs()["rust-plan"])


def test_the_plan_calls_the_library_function():
    script = next(s["with"]["script"] for s in jobs()["rust-plan"]["steps"]
                  if s.get("id") == "plan")
    assert "rust-plan.js" in script
    assert "core.setFailed" in script


def test_clippy_on_a_named_package_skips_the_other_members():
    # clippy-driver replaces rustc for every workspace member regardless of
    # -p, so without --no-deps the vendored crates are linted anyway.
    run = run_lines(jobs()["rust-check"])
    assert 'cargo clippy --all-targets -p "$PACKAGE" --no-deps -- -D warnings' in run
    assert "cargo clippy --all-targets -- -D warnings" in run


def test_fmt_and_test_take_the_package_only_when_one_is_named():
    assert 'cargo fmt --check ${PACKAGE:+-p "$PACKAGE"}' in run_lines(jobs()["rust-check"])
    assert 'cargo test ${PACKAGE:+-p "$PACKAGE"}' in run_lines(jobs()["rust-test"])


def test_the_package_reaches_the_shell_through_env_not_interpolation():
    # A crate name interpolated into `run:` would be shell code from a config
    # file; env keeps it a value.
    for name in ("rust-check", "rust-test"):
        assert "${{ matrix.package }}" not in run_lines(jobs()[name])
        assert jobs()[name]["env"]["PACKAGE"] == "${{ matrix.package }}"


def test_every_job_has_a_timeout():
    for name in ("rust-plan", "rust-check", "rust-test"):
        assert isinstance(jobs()[name]["timeout-minutes"], int)
