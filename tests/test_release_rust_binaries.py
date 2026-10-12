"""ri-release-rust-binaries (D32): the seven archives of a Rust program. The
build and the packing step run here on a fake target tree."""

import os
import pathlib
import subprocess
import tarfile

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIECE = (ROOT / "skills/repo-infra/assets/pieces/ri-release-rust-binaries/"
         "ri-release-rust-binaries.yml")
SHAPE = ROOT / "skills/repo-infra/references/project-shape.md"
TARGETS = ["x86_64-unknown-linux-musl", "aarch64-unknown-linux-musl", "x86_64-apple-darwin",
           "aarch64-apple-darwin", "x86_64-pc-windows-msvc", "aarch64-pc-windows-msvc",
           "x86_64-unknown-illumos"]


def doc():
    return yaml.safe_load(PIECE.read_text(encoding="utf-8"))


def step(job, name):
    return next(s for s in doc()["jobs"][job]["steps"] if s.get("name") == name)


def legs():
    return doc()["jobs"]["binaries"]["strategy"]["matrix"]["include"]


def test_the_matrix_builds_the_seven_native_targets_of_the_shape():
    assert sorted(leg["target"] for leg in legs()) == sorted(TARGETS)
    shape = SHAPE.read_text(encoding="utf-8")
    assert all(f"`{target}`" in shape for target in TARGETS)


def test_the_mac_legs_run_on_the_current_image():
    # A fixed label stops being served when GitHub retires it, and the leg
    # then waits in `queued` until the run is cancelled.
    assert {leg["target"]: leg["os"] for leg in legs() if "apple" in leg["target"]} == {
        "x86_64-apple-darwin": "macos-latest", "aarch64-apple-darwin": "macos-latest"}


def test_one_target_failing_does_not_cancel_the_others():
    assert doc()["jobs"]["binaries"]["strategy"]["fail-fast"] is False


def test_only_the_musl_legs_ask_for_a_static_crt():
    assert sorted(leg["target"] for leg in legs() if leg.get("static")) == [
        "aarch64-unknown-linux-musl", "x86_64-unknown-linux-musl"]


def test_linux_and_illumos_build_with_cross_pinned_by_version():
    assert sorted(leg["target"] for leg in legs() if leg.get("cross")) == [
        "aarch64-unknown-linux-musl", "x86_64-unknown-illumos", "x86_64-unknown-linux-musl"]
    assert step("binaries", "Install cross")["run"].strip() == (
        "cargo install cross --version 0.2.5 --locked")


def test_the_man_pages_are_built_once_on_linux_and_fetched_by_every_leg_but_windows():
    jobs = doc()["jobs"]
    assert jobs["binaries"]["needs"] == "man"
    assert jobs["man"]["runs-on"] == "ubuntu-latest"
    runs = [s.get("run", "") for s in jobs["man"]["steps"]]
    assert any("apt-get install -y pandoc" in r for r in runs)
    assert "make man" in [r.strip() for r in runs]
    assert jobs["man"]["steps"][-1]["with"]["name"] == "man-pages"
    fetch = step("binaries", "Fetch the man pages")
    assert fetch["with"] == {"name": "man-pages", "path": "man"}
    assert fetch["if"] == "${{ !matrix.windows }}"
    every_run = [s.get("run", "") for job in jobs.values() for s in job["steps"]]
    assert not any("brew install pandoc" in r for r in every_run)


def _stub(directory, name):
    path = directory / name
    path.write_text('#!/bin/sh\necho "%s $* RUSTFLAGS=${RUSTFLAGS-unset}"\n' % name)
    path.chmod(0o755)


@pytest.mark.parametrize("leg", legs(), ids=lambda leg: leg["target"])
def test_the_build_names_the_binary_and_sets_crt_static_only_on_a_static_leg(tmp_path, leg):
    stubs = tmp_path / "bin"
    stubs.mkdir()
    _stub(stubs, "cargo")
    _stub(stubs, "cross")
    env = {"PATH": f"{stubs}:/usr/bin:/bin", "BIN": "tool", "TARGET": leg["target"],
           "CROSS": "true" if leg.get("cross") else "",
           "STATIC": "true" if leg.get("static") else ""}
    done = subprocess.run(["bash", "-c", step("binaries", "Build")["run"]], env=env,
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    tool = "cross" if leg.get("cross") else "cargo"
    flags = "-C target-feature=+crt-static" if leg.get("static") else "unset"
    assert done.stdout.strip() == (
        f"{tool} build --release --bin tool --target {leg['target']} RUSTFLAGS={flags}")


def pack(tmp_path, pages):
    work = tmp_path / "src"
    release = work / "target/x86_64-unknown-linux-musl/release"
    release.mkdir(parents=True)
    (release / "tool").write_text("#!/bin/sh\n")
    (release / "tool").chmod(0o755)
    (work / "README.md").write_text("readme\n")
    (work / "LICENSE").write_text("license\n")
    (work / "man").mkdir()
    for page in pages:
        (work / "man" / page).write_text(".TH X\n")
    env = {"PATH": "/usr/bin:/bin", "BIN": "tool", "VERSION": "1.2.3",
           "TARGET": "x86_64-unknown-linux-musl"}
    return work, subprocess.run(["bash", "-c", step("binaries", "Pack the archive")["run"]],
                                cwd=work, env=env, capture_output=True, text=True)


def test_the_archive_holds_the_binary_every_man_page_the_readme_and_the_license(tmp_path):
    work, done = pack(tmp_path, ["tool.1", "toold.8"])
    assert done.returncode == 0, done.stdout + done.stderr
    archive = work / "dist/tool-1.2.3-x86_64-unknown-linux-musl.tar.gz"
    assert sorted(p.name for p in (work / "dist").iterdir()) == [archive.name]
    with tarfile.open(archive) as tar:
        members = {m.name: m for m in tar.getmembers()}
    assert sorted(n for n, m in members.items() if m.isfile()) == [
        "tool/LICENSE", "tool/README.md", "tool/man/tool.1", "tool/man/toold.8", "tool/tool"]
    assert members["tool/tool"].mode & 0o111


def test_the_mac_tar_adds_no_appledouble_files():
    assert step("binaries", "Pack the archive")["env"]["COPYFILE_DISABLE"] == 1


def test_an_archive_without_a_man_page_fails(tmp_path):
    _, done = pack(tmp_path, [])
    assert done.returncode == 1
    assert "no man page under man/" in done.stdout


def test_the_windows_zip_has_the_same_layout_without_man():
    zip_step = step("binaries", "Pack the zip")
    assert zip_step["shell"] == "pwsh" and zip_step["if"] == "${{ matrix.windows }}"
    run = zip_step["run"]
    assert "target/${env:TARGET}/release/${env:BIN}.exe" in run
    assert "Copy-Item README.md, LICENSE" in run
    assert "man/" not in run
    assert "dist/${env:BIN}-${env:VERSION}-${env:TARGET}.zip" in run


def test_every_leg_uploads_its_archive_as_a_release_asset():
    upload = doc()["jobs"]["binaries"]["steps"][-1]
    assert upload["with"] == {"name": "release-asset-${{ matrix.target }}", "path": "dist/*",
                              "if-no-files-found": "error"}


GUARD = "Refuse a package with a second binary"


def crate(root, name, extra=""):
    """A package named `name` with src/main.rs, plus `extra` appended to its
    Cargo.toml; cargo metadata --no-deps reads it without network."""
    (root / "src").mkdir(parents=True)
    (root / "src/main.rs").write_text("fn main() {}\n")
    (root / "Cargo.toml").write_text(
        f'[package]\nname = "{name}"\nversion = "0.0.0"\nedition = "2021"\n{extra}')


def guard(root):
    return subprocess.run(["bash", "-c", step("binaries", GUARD)["run"]], cwd=root,
                          env={**os.environ, "BIN": "tool"}, capture_output=True, text=True)


def test_the_guard_passes_a_package_with_the_one_binary(tmp_path):
    crate(tmp_path, "tool")
    done = guard(tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_guard_ignores_the_binaries_of_other_workspace_members(tmp_path):
    crate(tmp_path, "tool", '\n[workspace]\nmembers = ["xtask"]\n')
    crate(tmp_path / "xtask", "xtask")
    done = guard(tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.parametrize("extra, src_bin", [
    ('\n[[bin]]\nname = "tool"\npath = "src/main.rs"\n\n'
     '[[bin]]\nname = "tool-admin"\npath = "src/admin.rs"\n', None),
    ("", "tool-admin"),
], ids=["declared", "src-bin"])
def test_the_guard_refuses_a_second_binary_in_the_package(tmp_path, extra, src_bin):
    crate(tmp_path, "tool", extra)
    (tmp_path / "src/admin.rs").write_text("fn main() {}\n")
    if src_bin:
        (tmp_path / "src/bin").mkdir()
        (tmp_path / f"src/bin/{src_bin}.rs").write_text("fn main() {}\n")
    done = guard(tmp_path)
    assert done.returncode == 1
    assert done.stdout.splitlines() == [
        "::error::the package of tool also builds tool-admin; the archives, packages and "
        "formula carry tool alone, so move tool-admin into another package"]


def test_the_guard_runs_on_every_leg_before_the_build():
    names = [s.get("name") for s in doc()["jobs"]["binaries"]["steps"]]
    assert names.index(GUARD) == names.index("Build") - 1
    assert "if" not in step("binaries", GUARD)
