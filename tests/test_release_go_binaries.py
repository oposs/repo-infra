"""ri-release-go-binaries (D35): the seven archives of a Go program under the
target names of ri-release-rust-binaries, or the ones `targets` chooses (D34).
The target choice, the build and the packing step run here; the build runs
the local go on a tiny module when there is one."""

import json
import os
import pathlib
import shutil
import subprocess
import tarfile
import zipfile

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIECE = ROOT / ".github/workflows/ri-release-go-binaries.yml"
RUST = ROOT / ".github/workflows/ri-release-rust-binaries.yml"
SHAPE = ROOT / "skills/repo-infra/references/project-shape.md"
PLATFORMS = {
    "x86_64-unknown-linux-musl": ("linux", "amd64"),
    "aarch64-unknown-linux-musl": ("linux", "arm64"),
    "x86_64-unknown-illumos": ("illumos", "amd64"),
    "x86_64-apple-darwin": ("darwin", "amd64"),
    "aarch64-apple-darwin": ("darwin", "arm64"),
    "x86_64-pc-windows-msvc": ("windows", "amd64"),
    "aarch64-pc-windows-msvc": ("windows", "arm64"),
}


def doc(path=PIECE):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def inputs(path=PIECE):
    # PyYAML reads the key `on` as the boolean true.
    return doc(path)[True]["workflow_call"]["inputs"]


def step(job, name, path=PIECE):
    return next(s for s in doc(path)["jobs"][job]["steps"] if s.get("name") == name)


def plan(targets, path=PIECE):
    """Runs the plan step with `targets`; its output file is stdout."""
    return subprocess.run(["bash", "-c", step("plan", "Choose the targets", path)["run"]],
                          env={"PATH": "/usr/bin:/bin", "TARGETS": targets,
                               "GITHUB_OUTPUT": "/dev/stdout"},
                          capture_output=True, text=True)


def chosen(targets):
    done = plan(targets)
    assert done.returncode == 0, done.stdout + done.stderr
    lines = done.stdout.splitlines()
    assert len(lines) == 1 and lines[0].startswith("matrix=")
    return json.loads(lines[0].removeprefix("matrix="))["include"]


def legs():
    """The legs a caller gets without `targets`."""
    return chosen(inputs()["targets"]["default"])


def test_the_matrix_builds_the_seven_native_targets_of_the_shape():
    assert sorted(leg["target"] for leg in legs()) == sorted(PLATFORMS)
    shape = SHAPE.read_text(encoding="utf-8")
    assert all(f"`{target}`" in shape for target in PLATFORMS)


def test_each_target_maps_to_its_goos_and_goarch():
    assert {leg["target"]: (leg["goos"], leg["goarch"]) for leg in legs()} == PLATFORMS


def test_only_the_windows_legs_are_marked_windows():
    assert sorted(leg["target"] for leg in legs() if leg.get("windows")) == [
        "aarch64-pc-windows-msvc", "x86_64-pc-windows-msvc"]


def test_the_interface_is_the_rust_piece_plus_package_and_version_var():
    go, rust = inputs(), inputs(RUST)
    assert set(go) == set(rust) | {"package", "version_var"}
    assert all(go[name] == rust[name] for name in rust)
    assert (go["package"]["required"], go["package"]["default"]) == (False, ".")
    assert (go["version_var"]["required"], go["version_var"]["default"]) == (False, "")


def test_the_matrix_comes_from_the_plan_job_and_every_leg_runs_on_linux():
    binaries = doc()["jobs"]["binaries"]
    assert binaries["strategy"]["matrix"] == "${{ fromJSON(needs.plan.outputs.matrix) }}"
    assert binaries["strategy"]["fail-fast"] is False
    assert binaries["runs-on"] == "ubuntu-latest"
    assert binaries["needs"] == ["plan", "man"]
    assert doc()["jobs"]["plan"]["outputs"] == {"matrix": "${{ steps.plan.outputs.matrix }}"}


def test_the_toolchain_is_the_one_go_mod_names_as_in_ri_ci_go():
    setup = next(s for s in doc()["jobs"]["binaries"]["steps"]
                 if s.get("uses", "").startswith("actions/setup-go@"))
    ci = doc(ROOT / ".github/workflows/ri-ci-go.yml")["jobs"]["go-test"]["steps"]
    assert setup == next(s for s in ci if s.get("uses", "").startswith("actions/setup-go@"))
    assert setup["with"] == {"go-version-file": "go.mod"}


@pytest.mark.parametrize("targets", [
    "x86_64-unknown-linux-musl aarch64-unknown-linux-musl x86_64-apple-darwin "
    "aarch64-apple-darwin x86_64-unknown-illumos",
    "aarch64-apple-darwin",
    "  x86_64-pc-windows-msvc\n x86_64-unknown-linux-musl  x86_64-pc-windows-msvc ",
], ids=["no-windows", "one", "blanks-newlines-repeats"])
def test_targets_keeps_exactly_the_named_legs_unchanged(targets):
    full = {leg["target"]: leg for leg in legs()}
    picked = chosen(targets)
    assert [leg["target"] for leg in picked] == [t for t in full if t in targets.split()]
    assert all(leg == full[leg["target"]] for leg in picked)


@pytest.mark.parametrize("targets", [
    "x86_64-unknown-linux-musl i686-pc-windows-gnu",
    "x86_64-unknown-linux-gnu riscv64gc-unknown-linux-musl",
    "*", "", "  \n ",
], ids=["one-unknown", "two-unknown", "glob", "empty", "blank"])
def test_a_wrong_targets_fails_with_the_message_of_the_rust_piece(targets):
    go, rust = plan(targets), plan(targets, RUST)
    assert go.returncode == rust.returncode == 1
    assert go.stdout == rust.stdout
    assert go.stdout.startswith("::error::targets names ")


def test_the_man_pages_are_built_once_and_fetched_by_every_leg_but_windows():
    jobs = doc()["jobs"]
    assert [s.get("run", "").strip() for s in jobs["man"]["steps"]] == [
        s.get("run", "").strip() for s in doc(RUST)["jobs"]["man"]["steps"]]
    assert jobs["man"]["steps"][-1]["with"]["name"] == "man-pages"
    fetch = step("binaries", "Fetch the man pages")
    assert fetch["with"] == {"name": "man-pages", "path": "man"}
    assert fetch["if"] == "${{ !matrix.windows }}"


def test_every_leg_uploads_its_archive_as_a_release_asset():
    upload = doc()["jobs"]["binaries"]["steps"][-1]
    assert upload["with"] == {"name": "release-asset-${{ matrix.target }}", "path": "dist/*",
                              "if-no-files-found": "error"}


def leg_env(leg):
    """The env of a step as GitHub fills it for `leg`: a key the leg lacks is
    the empty string."""
    return {"TARGET": leg["target"], "GOOS": leg["goos"], "GOARCH": leg["goarch"],
            "WINDOWS": "true" if leg.get("windows") else ""}


def build(cwd, leg, path, version_var="", package="."):
    env = {"PATH": path, "BIN": "tool", "PACKAGE": package, "VERSION": "1.2.3",
           "VERSION_VAR": version_var, **leg_env(leg)}
    if "HOME" in os.environ:
        env["HOME"] = os.environ["HOME"]
    # Go reads these from the environment; the step does not set them.
    env.update(GOTOOLCHAIN="local", GOFLAGS="-p=4", GOMAXPROCS="4")
    return subprocess.run(["bash", "-c", step("binaries", "Build")["run"]], cwd=cwd, env=env,
                          capture_output=True, text=True)


@pytest.mark.parametrize("version_var, flags", [
    ("", ""),
    ("main.version", " -ldflags -X main.version=1.2.3"),
], ids=["no-version-var", "version-var"])
@pytest.mark.parametrize("leg", legs(), ids=lambda leg: leg["target"])
def test_the_build_command_of_every_leg(tmp_path, leg, version_var, flags):
    stubs = tmp_path / "bin"
    stubs.mkdir()
    (stubs / "go").write_text('#!/bin/sh\necho "CGO_ENABLED=$CGO_ENABLED GOOS=$GOOS '
                              'GOARCH=$GOARCH go $*"\n')
    (stubs / "go").chmod(0o755)
    done = build(tmp_path, leg, f"{stubs}:/usr/bin:/bin", version_var, "./cmd")
    assert done.returncode == 0, done.stderr
    exe = ".exe" if leg.get("windows") else ""
    assert done.stdout.strip() == (
        f"CGO_ENABLED=0 GOOS={leg['goos']} GOARCH={leg['goarch']} go build -trimpath "
        f"-buildvcs=false{flags} -o release-bin/{leg['target']}/tool{exe} ./cmd")


GO = shutil.which("go")
MAGIC = {"linux": b"\x7fELF", "illumos": b"\x7fELF", "darwin": b"\xcf\xfa\xed\xfe",
         "windows": b"MZ"}


@pytest.fixture(scope="module")
def module(tmp_path_factory):
    """A Go module whose main package lives in cmd/, as unspammer's does."""
    root = tmp_path_factory.mktemp("gomod")
    (root / "go.mod").write_text("module example.com/tool\n\ngo 1.22\n")
    (root / "cmd").mkdir()
    (root / "cmd/main.go").write_text(
        'package main\n\nimport "fmt"\n\nvar version = "dev"\n\n'
        'func main() { fmt.Println(version) }\n')
    return root


@pytest.mark.skipif(GO is None, reason="no go on PATH")
@pytest.mark.parametrize("leg", legs(), ids=lambda leg: leg["target"])
def test_go_builds_a_static_binary_for_every_leg(module, leg):
    done = build(module, leg, f"{pathlib.Path(GO).parent}:/usr/bin:/bin", "main.version",
                 "./cmd")
    assert done.returncode == 0, done.stdout + done.stderr
    exe = ".exe" if leg.get("windows") else ""
    binary = module / f"release-bin/{leg['target']}/tool{exe}"
    assert binary.read_bytes().startswith(MAGIC[leg["goos"]])
    info = subprocess.run([GO, "version", "-m", str(binary)], capture_output=True, text=True,
                          env={**os.environ, "GOTOOLCHAIN": "local"}, check=True).stdout
    settings = dict(line.split("\t")[2].split("=", 1) for line in info.splitlines()
                    if line.startswith("\tbuild\t") and "=" in line.split("\t")[2])
    assert settings["GOOS"] == leg["goos"] and settings["GOARCH"] == leg["goarch"]
    assert settings["CGO_ENABLED"] == "0" and settings["-trimpath"] == "true"
    # -trimpath leaves -ldflags out of the build settings; the string is in
    # the binary, and the host leg below prints it.
    assert b"1.2.3" in binary.read_bytes()
    assert not any(key.startswith("vcs") for key in settings)
    if (leg["goos"], leg["goarch"]) == ("linux", "amd64"):
        ran = subprocess.run([str(binary)], capture_output=True, text=True, check=True)
        assert ran.stdout == "1.2.3\n"


def pack(tmp_path, leg, pages):
    work = tmp_path / "src"
    exe = ".exe" if leg.get("windows") else ""
    out = work / f"release-bin/{leg['target']}"
    out.mkdir(parents=True)
    (out / f"tool{exe}").write_text("#!/bin/sh\n")
    (out / f"tool{exe}").chmod(0o755)
    (work / "README.md").write_text("readme\n")
    (work / "LICENSE").write_text("license\n")
    if pages is not None:
        (work / "man").mkdir()
        for page in pages:
            (work / "man" / page).write_text(".TH X\n")
    env = {"PATH": "/usr/bin:/bin", "BIN": "tool", "VERSION": "1.2.3", **leg_env(leg)}
    return work, subprocess.run(["bash", "-c", step("binaries", "Pack the archive")["run"]],
                                cwd=work, env=env, capture_output=True, text=True)


UNIX = [leg for leg in legs() if not leg.get("windows")]
WINDOWS = [leg for leg in legs() if leg.get("windows")]


@pytest.mark.parametrize("leg", UNIX, ids=lambda leg: leg["target"])
def test_the_archive_holds_the_binary_every_man_page_the_readme_and_the_license(
        tmp_path, leg):
    work, done = pack(tmp_path, leg, ["tool.1", "toold.8"])
    assert done.returncode == 0, done.stdout + done.stderr
    archive = work / f"dist/tool-1.2.3-{leg['target']}.tar.gz"
    assert sorted(p.name for p in (work / "dist").iterdir()) == [archive.name]
    with tarfile.open(archive) as tar:
        members = {m.name: m for m in tar.getmembers()}
    assert sorted(n for n, m in members.items() if m.isfile()) == [
        "tool/LICENSE", "tool/README.md", "tool/man/tool.1", "tool/man/toold.8", "tool/tool"]
    assert members["tool/tool"].mode & 0o111


def test_an_archive_without_a_man_page_fails(tmp_path):
    _, done = pack(tmp_path, UNIX[0], [])
    assert done.returncode == 1
    assert "no man page under man/" in done.stdout


@pytest.mark.parametrize("leg", WINDOWS, ids=lambda leg: leg["target"])
def test_the_windows_zip_has_the_same_layout_without_man(tmp_path, leg):
    # No man/ at all: the Windows legs do not fetch the man pages.
    work, done = pack(tmp_path, leg, None)
    assert done.returncode == 0, done.stdout + done.stderr
    archive = work / f"dist/tool-1.2.3-{leg['target']}.zip"
    assert sorted(p.name for p in (work / "dist").iterdir()) == [archive.name]
    with zipfile.ZipFile(archive) as zipped:
        files = sorted(n for n in zipped.namelist() if not n.endswith("/"))
    assert files == ["tool/LICENSE", "tool/README.md", "tool/tool.exe"]
