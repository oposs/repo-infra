"""build/container-make.mk: the host side of the make container driver (#94).

The engine is a fake (tests/fakeengine.py) and the PATH make sees holds only
the tools the recipe needs, so no test reaches a real podman or docker.
"""

import os
import pathlib
import pty
import re
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fakeengine import calls, install_fake  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
MK = ROOT / "skills/repo-infra/assets/pieces/container-make/container-make.mk"

GUARDED = """\
CONTAINER_DEVICES =
include build/container-make.mk

.PHONY: all
all:
\t@echo PROJECT_ALL

ifeq ($(CONTAINER_DRIVER),no)
check:
\t@echo PROJECT_CHECK TEST=[$(TEST)]
endif
"""

CONTAINERFILE = "FROM scratch\nRUN true\n"

TOOLS = ("make", "sh", "git", "find", "ls", "tr", "sed", "awk", "basename",
         "dirname", "cat", "head", "wc", "printf", "stat", "chown", "id", "sleep",
         "echo")


def project(root, makefile=GUARDED, git=True):
    """A project that includes the fragment the way the manual says."""
    (root / "build").mkdir(parents=True)
    shutil.copy(MK, root / "build/container-make.mk")
    (root / "Makefile").write_text(makefile, encoding="utf-8")
    (root / "Containerfile").write_text(CONTAINERFILE, encoding="utf-8")
    if git:
        subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def log_of(root):
    return root.parent / f"{root.name}.engine.log"


def engine_calls(root):
    return calls(log_of(root))


def make(root, *args, engines=("podman", "docker"), env=None,
         stdin=subprocess.DEVNULL):
    """Run make in root with a PATH of fake engines and a few real tools."""
    side = root.parent / f".{root.name}.path"
    tools = side / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    for tool in TOOLS:
        real = shutil.which(tool)
        assert real, f"{tool} is not on the PATH of the test run"
        link = tools / tool
        if not link.exists():
            link.symlink_to(real)
    fake = side / ("fake-" + ("-".join(engines) or "none"))
    fake.mkdir(exist_ok=True)
    install_fake(fake)
    for name in {"podman", "docker"} - set(engines):
        (fake / name).unlink()
    # `make test` runs pytest, so MAKEFLAGS and MAKELEVEL arrive set (as in
    # tests/test_man_build.py::make_env).
    full = {k: v for k, v in os.environ.items()
            if k not in ("MAKEFLAGS", "MAKELEVEL", "MFLAGS")}
    for key in ("REPO_INFRA_USE_CONTAINER", "CONTAINER_ENGINE", "CONTAINER_TAG",
                "CARGO_BUILD_JOBS", "RUST_TEST_THREADS"):
        full.pop(key, None)
    full.update({"PATH": f"{fake}:{tools}", "LC_ALL": "C",
                 "FAKE_ENGINE_LOG": str(log_of(root)),
                 "GIT_CEILING_DIRECTORIES": str(root.parent)})
    full.update(env or {})
    if "PATH_PREFIX" in full:
        full["PATH"] = f"{full.pop('PATH_PREFIX')}:{full['PATH']}"
    return subprocess.run(["make", *args], cwd=root, env=full, stdin=stdin,
                          capture_output=True, text=True, timeout=120)


def argv_of(recorded, sub):
    found = [c["argv"] for c in recorded if c["argv"][:1] == [sub]]
    assert len(found) == 1, f"expected one {sub} call, got {recorded}"
    return found[0]


def pairs(argv, a, b):
    return any(x == a and y == b for x, y in zip(argv, argv[1:], strict=False))


def run_argv(root, *args, **kw):
    done = make(root, *args, **kw)
    assert done.returncode == 0, done.stderr
    return argv_of(engine_calls(root), "run")


def git_commit(root):
    (root / "f").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "x"], check=True)


# --- the fragment as a make include -------------------------------------------


@pytest.mark.parametrize("position", ["first", "last"])
def test_including_the_fragment_keeps_the_projects_default_goal(tmp_path, position):
    body = GUARDED.split("\n", 2)[2]
    if position == "last":
        text = "CONTAINER_DEVICES =\n" + body.replace(
            "ifeq", "include build/container-make.mk\nifeq", 1)
    else:
        text = GUARDED
    root = project(tmp_path / "p", makefile=text)
    done = make(root, engines=())
    assert done.returncode == 0, done.stderr
    assert "PROJECT_ALL" in done.stdout
    assert engine_calls(root) == []


def test_make_all_works_with_no_engine_on_path(tmp_path):
    done = make(project(tmp_path / "p"), "all", engines=())
    assert done.returncode == 0 and "PROJECT_ALL" in done.stdout


def test_check_without_an_engine_names_the_escape(tmp_path):
    done = make(project(tmp_path / "p"), "check", engines=())
    assert done.returncode != 0
    assert "REPO_INFRA_USE_CONTAINER=no" in done.stderr


def test_use_container_no_runs_the_projects_check_here(tmp_path):
    root = project(tmp_path / "p")
    done = make(root, "check", engines=(), env={"REPO_INFRA_USE_CONTAINER": "no"})
    assert done.returncode == 0, done.stderr
    assert "PROJECT_CHECK" in done.stdout


@pytest.mark.parametrize("value", ["", "yes"])
def test_use_container_unset_or_yes_drives(tmp_path, value):
    root = project(tmp_path / "p")
    run_argv(root, "check", env={"REPO_INFRA_USE_CONTAINER": value})


def test_any_other_value_is_an_error_naming_yes_and_no(tmp_path):
    root = project(tmp_path / "p")
    done = make(root, "check", env={"REPO_INFRA_USE_CONTAINER": "maybe"})
    assert done.returncode != 0
    assert "yes" in done.stderr and "no" in done.stderr
    assert engine_calls(root) == []


# --- the engine ---------------------------------------------------------------


def test_podman_wins_when_both_exist(tmp_path):
    root = project(tmp_path / "p")
    assert make(root, "check").returncode == 0
    assert {c["engine"] for c in engine_calls(root)} == {"podman"}


def test_docker_when_only_docker(tmp_path):
    root = project(tmp_path / "p")
    assert make(root, "check", engines=("docker",)).returncode == 0
    assert {c["engine"] for c in engine_calls(root)} == {"docker"}


def test_container_engine_picks_docker(tmp_path):
    root = project(tmp_path / "p")
    assert make(root, "check", env={"CONTAINER_ENGINE": "docker"}).returncode == 0
    assert {c["engine"] for c in engine_calls(root)} == {"docker"}


def test_container_engine_other_than_podman_or_docker_is_refused(tmp_path):
    root = project(tmp_path / "p")
    done = make(root, "check", env={"CONTAINER_ENGINE": "nerdctl"})
    assert done.returncode != 0
    assert "podman" in done.stderr and "docker" in done.stderr
    assert engine_calls(root) == []


# --- the image ----------------------------------------------------------------


def test_the_image_is_built_from_the_containerfile_on_stdin(tmp_path):
    root = project(tmp_path / "p")
    assert make(root, "check").returncode == 0
    build = [c for c in engine_calls(root) if c["argv"][0] == "build"]
    assert len(build) == 1
    assert build[0]["argv"] == ["build", "--pull=newer", "-t", "p-ci:local", "-"]
    assert build[0]["stdin"] == CONTAINERFILE

    root = project(tmp_path / "q")
    assert make(root, "check", engines=("docker",)).returncode == 0
    build = [c for c in engine_calls(root) if c["argv"][0] == "build"]
    assert build[0]["argv"] == ["build", "--pull", "-t", "q-ci:local", "-"]
    assert build[0]["stdin"] == CONTAINERFILE


def test_a_failed_docker_pull_builds_again_on_the_local_copy(tmp_path):
    root = project(tmp_path / "p")
    done = make(root, "check", engines=("docker",),
                env={"FAKE_BUILD_FAIL_PULL": "1"})
    assert done.returncode == 0, done.stderr
    recorded = engine_calls(root)
    builds = [c["argv"] for c in recorded if c["argv"][0] == "build"]
    assert len(builds) == 2
    assert "--pull" in builds[0] and not any(a.startswith("--pull") for a in builds[1])
    assert "building again without it" in done.stderr
    assert [c["argv"][0] for c in recorded][-1] == "run"


def test_a_missing_containerfile_is_named_and_nothing_runs(tmp_path):
    root = project(tmp_path / "p")
    (root / "Containerfile").unlink()
    done = make(root, "check")
    assert done.returncode != 0
    assert str(root / "Containerfile") in done.stderr
    assert engine_calls(root) == []


# --- the run ------------------------------------------------------------------


def test_the_run_carries_the_fixed_options(tmp_path):
    root = project(tmp_path / "p")
    argv = run_argv(root, "check")
    top = str(root.resolve())
    for word in ("--rm", "--init"):
        assert word in argv
    assert pairs(argv, "--security-opt", "label=disable")
    assert pairs(argv, "-e", "REPO_INFRA_USE_CONTAINER=no")
    assert pairs(argv, "-v", f"{top}:/src")
    assert pairs(argv, "-v", "p-ci-home:/root")
    assert pairs(argv, "-w", "/src")
    assert "p-ci:local" in argv
    assert not any("privileged" in a or "keep-id" in a for a in argv)
    assert "-i" not in argv and "-t" not in argv


def test_a_terminal_adds_i_and_t_together(tmp_path):
    root = project(tmp_path / "p")
    master, slave = pty.openpty()
    try:
        done = make(root, "check", stdin=slave)
    finally:
        os.close(master)
        os.close(slave)
    assert done.returncode == 0, done.stderr
    argv = argv_of(engine_calls(root), "run")
    assert "-i" in argv and "-t" in argv


@pytest.mark.parametrize("name, tag", [
    ("My Project", "my-project-ci:local"), ("Foo__Bar", "foo-bar-ci:local"),
    ("--x--", "x-ci:local"), ("über", "ber-ci:local"),
    ("...", "project-ci:local")])
def test_the_tag_is_the_cleaned_top_level_name(tmp_path, name, tag):
    root = project(tmp_path / name)
    argv = run_argv(root, "check")
    assert tag in argv
    assert pairs(argv, "-v", f"{root.resolve()}:/src")


def test_container_tag_set_by_the_project_names_tag_and_volume(tmp_path):
    text = "CONTAINER_TAG = Reg/x:1\n" + GUARDED
    root = project(tmp_path / "p", makefile=text)
    argv = run_argv(root, "check")
    assert "Reg/x:1" in argv
    assert pairs(argv, "-v", "Reg-x-1-ci-home:/root")


def test_a_subdirectory_mounts_the_top_level_and_works_below_it(tmp_path):
    top = project(tmp_path / "top")
    sub = top / "sub"
    sub.mkdir()
    for name in ("Makefile", "Containerfile"):
        (sub / name).write_text("# sub\n" + (top / name).read_text(), encoding="utf-8")
    (sub / "Containerfile").write_text("FROM scratch\n# sub\n", encoding="utf-8")
    (sub / "build").symlink_to(top / "build")
    done = make(top, "-C", "sub", "check")
    assert done.returncode == 0, done.stderr
    recorded = engine_calls(top)
    argv = argv_of(recorded, "run")
    assert pairs(argv, "-v", f"{top.resolve()}:/src")
    assert pairs(argv, "-w", "/src/sub")
    build = [c for c in recorded if c["argv"][0] == "build"][0]
    assert build["stdin"] == "FROM scratch\n# sub\n"


def test_a_worktree_mounts_the_common_dir_and_shares_the_main_volume(tmp_path):
    main = project(tmp_path / "main")
    git_commit(main)
    subprocess.run(["git", "-C", str(main), "worktree", "add", "-q",
                    str(tmp_path / "Feature X"), "-b", "feat"], check=True)
    feature = tmp_path / "Feature X"
    done = make(feature, "check")
    assert done.returncode == 0, done.stderr
    argv = argv_of(engine_calls(feature), "run")
    common = str((main / ".git").resolve())
    assert "feature-x-ci:local" in argv
    assert pairs(argv, "-v", "main-ci-home:/root")
    assert pairs(argv, "-v", f"{common}:{common}")
    assert pairs(argv, "-v", f"{feature.resolve()}:/src")


def old_git(tmp_path):
    """A directory with a git that, like git before 2.31, prints an unknown
    --path-format flag back and exits 0."""
    old = tmp_path / "oldgit"
    old.mkdir()
    wrapper = old / "git"
    wrapper.write_text(
        '#!/bin/sh\n'
        'for a in "$@"; do\n'
        '  case $a in --path-format*) echo "$@"; exit 0 ;; esac\n'
        'done\n'
        f'exec {shutil.which("git")} "$@"\n', encoding="utf-8")
    wrapper.chmod(0o755)
    return str(old)


def test_a_worktree_needs_no_path_format_support_from_git(tmp_path):
    main = project(tmp_path / "main")
    git_commit(main)
    subprocess.run(["git", "-C", str(main), "worktree", "add", "-q",
                    str(tmp_path / "feature"), "-b", "feat"], check=True)
    feature = tmp_path / "feature"
    done = make(feature, "check", env={"PATH_PREFIX": old_git(tmp_path)})
    assert done.returncode == 0, done.stderr
    argv = argv_of(engine_calls(feature), "run")
    common = str((main / ".git").resolve())
    assert pairs(argv, "-v", f"{common}:{common}")
    assert not any("--path-format" in a for a in argv)


def test_a_subdirectory_needs_no_path_format_support_from_git(tmp_path):
    top = project(tmp_path / "top")
    git_commit(top)
    sub = top / "sub"
    sub.mkdir()
    for name in ("Makefile", "Containerfile"):
        (sub / name).write_text((top / name).read_text(), encoding="utf-8")
    (sub / "build").symlink_to(top / "build")
    done = make(top, "-C", "sub", "check", env={"PATH_PREFIX": old_git(tmp_path)})
    assert done.returncode == 0, done.stderr
    argv = argv_of(engine_calls(top), "run")
    assert pairs(argv, "-v", f"{top.resolve()}:/src")
    assert pairs(argv, "-w", "/src/sub")
    assert not any("--path-format" in a for a in argv)


def test_outside_git_the_top_level_is_makes_directory(tmp_path):
    root = project(tmp_path / "p", git=False)
    argv = run_argv(root, "check")
    mounts = [b for a, b in zip(argv, argv[1:], strict=False) if a == "-v"]
    assert mounts == [f"{root.resolve()}:/src", "p-ci-home:/root"]
    assert pairs(argv, "-w", "/src")


# --- devices and options ------------------------------------------------------


def device_project(tmp_path, extra=""):
    kvm = tmp_path / "fake-kvm"
    kvm.write_text("", encoding="utf-8")
    none = tmp_path / "none"
    text = GUARDED.replace("CONTAINER_DEVICES =\n", "") + extra
    text = f"CONTAINER_DEVICES = {kvm} {none}\n" + text
    return project(tmp_path / "p", makefile=text), kvm, none


def test_a_present_device_is_passed_with_its_mode_and_an_absent_one_skipped(tmp_path):
    root, kvm, none = device_project(tmp_path)
    kvm.chmod(0o640)
    done = make(root, "check")
    assert done.returncode == 0, done.stderr
    argv = argv_of(engine_calls(root), "run")
    assert pairs(argv, "--device", str(kvm))
    assert str(none) not in argv
    out = done.stdout + done.stderr
    assert "-rw-r-----" in out
    assert re.search(rf"{re.escape(str(none))}.*skipped|skipped.*{re.escape(str(none))}", out)


def test_podman_with_a_device_keeps_groups(tmp_path):
    root, _, _ = device_project(tmp_path)
    argv = run_argv(root, "check")
    assert pairs(argv, "--group-add", "keep-groups")


def test_docker_with_a_device_adds_no_group(tmp_path):
    root, _, _ = device_project(tmp_path)
    argv = run_argv(root, "check", engines=("docker",))
    assert "--group-add" not in argv


@pytest.mark.parametrize("info", ["true crun", "false runc"])
def test_podman_remote_or_without_crun_leaves_keep_groups_out_with_a_notice(
        tmp_path, info):
    root, _, _ = device_project(tmp_path)
    done = make(root, "check", env={"FAKE_PODMAN_INFO": info})
    assert done.returncode == 0, done.stderr
    assert "--group-add" not in argv_of(engine_calls(root), "run")
    assert "keep-groups" in done.stderr


def test_a_failing_podman_info_takes_the_notice_path(tmp_path):
    root, _, _ = device_project(tmp_path)
    done = make(root, "check", env={"FAKE_PODMAN_INFO_FAIL": "1"})
    assert done.returncode == 0, done.stderr
    assert "--group-add" not in argv_of(engine_calls(root), "run")
    assert "keep-groups" in done.stderr
    assert engine_calls(root)[-1]["argv"][0] == "run"


def test_no_device_no_keep_groups(tmp_path):
    root = project(tmp_path / "p")
    argv = run_argv(root, "check")
    assert "--group-add" not in argv
    assert not any(c["argv"][0] == "info" for c in engine_calls(root))


def test_devices_and_opts_set_after_the_include_still_count(tmp_path):
    kvm = tmp_path / "fake-kvm"
    kvm.write_text("", encoding="utf-8")
    text = GUARDED + f"CONTAINER_DEVICES = {kvm}\nCONTAINER_OPTS = --cpus=2\n"
    root = project(tmp_path / "p", makefile=text)
    argv = run_argv(root, "check")
    assert pairs(argv, "--device", str(kvm))
    assert "--cpus=2" in argv


def test_container_opts_are_split_into_words(tmp_path):
    root = project(tmp_path / "p")
    argv = run_argv(root, "check", env={"CONTAINER_OPTS": "--cpus=4 --memory=6g"})
    assert "--cpus=4" in argv and "--memory=6g" in argv


def test_container_opts_with_group_add_is_refused(tmp_path):
    root = project(tmp_path / "p")
    done = make(root, "check", env={"CONTAINER_OPTS": "--group-add=audio"})
    assert done.returncode != 0
    assert "--group-add" in done.stderr
    assert not any(c["argv"][0] == "run" for c in engine_calls(root))


@pytest.mark.parametrize("var", ["CARGO_BUILD_JOBS", "RUST_TEST_THREADS"])
def test_cargo_variables_pass_only_when_set(tmp_path, var):
    root = project(tmp_path / "p")
    assert pairs(run_argv(root, "check", env={var: "2"}), "-e", var)
    root = project(tmp_path / "q")
    assert var not in run_argv(root, "check")


def test_overrides_reach_the_inner_make_through_makeflags(tmp_path):
    root = project(tmp_path / "p")
    argv = run_argv(root, "check", "TEST=foo")
    assert pairs(argv, "-e", "MAKEFLAGS=-- TEST=foo")

    root = project(tmp_path / "q")
    argv = run_argv(root, "check")
    assert not any(a.startswith("MAKEFLAGS") for a in argv)

    root = project(tmp_path / "r")
    argv = run_argv(root, "-j3", "check")
    assert not any("jobserver" in a or a.startswith("-j") for a in argv)


def test_use_container_on_the_command_line_does_not_reach_the_inner_make(tmp_path):
    root = project(tmp_path / "p")
    argv = run_argv(root, "check", "REPO_INFRA_USE_CONTAINER=yes", "TEST=a")
    assert pairs(argv, "-e", "MAKEFLAGS=-- TEST=a")

    root = project(tmp_path / "q")
    argv = run_argv(root, "check", "REPO_INFRA_USE_CONTAINER:=yes", "TEST=a")
    assert pairs(argv, "-e", "MAKEFLAGS=-- TEST=a")


# --- status and cleanup -------------------------------------------------------


def test_the_runs_exit_status_is_makes(tmp_path):
    root = project(tmp_path / "p")
    done = make(root, "check", env={"FAKE_RUN_STATUS": "3"})
    assert done.returncode != 0
    assert "catatonit" not in done.stderr


@pytest.mark.parametrize("status", [125, 126, 127])
def test_an_engine_failure_names_catatonit(tmp_path, status):
    root = project(tmp_path / "p")
    done = make(root, "check", env={"FAKE_RUN_STATUS": str(status)})
    assert done.returncode != 0
    assert "catatonit" in done.stderr
    assert "REPO_INFRA_USE_CONTAINER=no" in done.stderr


def test_container_clean_removes_the_volume(tmp_path):
    root = project(tmp_path / "p")
    done = make(root, "container-clean", env={"FAKE_VOLUME": "1"})
    assert done.returncode == 0, done.stderr
    assert ["volume", "rm", "p-ci-home"] in [c["argv"] for c in engine_calls(root)]

    root = project(tmp_path / "q")
    done = make(root, "container-clean")
    assert done.returncode == 0, done.stderr
    assert not any(c["argv"][:2] == ["volume", "rm"] for c in engine_calls(root))
    assert "q-ci-home" in done.stdout + done.stderr


def test_container_clean_is_not_defined_inside(tmp_path):
    root = project(tmp_path / "p")
    done = make(root, "container-clean", engines=(),
                env={"REPO_INFRA_USE_CONTAINER": "no"})
    assert done.returncode != 0
    assert "No rule to make target" in done.stderr


def test_the_fragment_carries_its_marker_and_no_em_dash():
    text = MK.read_text(encoding="utf-8")
    assert text.startswith("# repo-infra: container-make v1\n")
    assert chr(0x2014) not in text


# --- the wrapper inside the container -----------------------------------------


def exec_env(tmp_path, **extra):
    """Environment that makes the fake engine run the container command."""
    etc = tmp_path / "etc"
    etc.mkdir(exist_ok=True)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {"FAKE_EXEC": "1", "FAKE_ETC": str(etc), "FAKE_HOME": str(home), **extra}


def test_the_inner_make_runs_the_projects_guarded_check(tmp_path):
    root = project(tmp_path / "p")
    done = make(root, "check", env=exec_env(tmp_path))
    assert done.returncode == 0, done.stderr
    assert "PROJECT_CHECK TEST=[]" in done.stdout


@pytest.mark.parametrize("value", ["foo", "a b", "it's", "x$y"])
def test_an_override_reaches_the_projects_check_unchanged(tmp_path, value):
    text = GUARDED.replace("@echo PROJECT_CHECK TEST=[$(TEST)]",
                           "@:\n\t$(info PROJECT_CHECK TEST=[$(TEST)])")
    root = project(tmp_path / "p", makefile=text)
    done = make(root, "check", "TEST=" + value.replace("$", "$$"),
                env=exec_env(tmp_path))
    assert done.returncode == 0, done.stderr
    assert f"PROJECT_CHECK TEST=[{value}]" in done.stdout


def test_the_projects_exit_status_survives_the_handback(tmp_path):
    text = GUARDED.replace("@echo PROJECT_CHECK TEST=[$(TEST)]", "@exit 3")
    root = project(tmp_path / "p", makefile=text)
    done = make(root, "check", env=exec_env(tmp_path))
    assert done.returncode != 0
    assert "Error 3" in done.stderr


def test_the_projects_check_reads_the_runs_stdin(tmp_path):
    # The check runs as a background job, which a non-interactive shell gives
    # /dev/null as stdin; the wrapper hands it the run's stdin through fd 3.
    text = GUARDED.replace("@echo PROJECT_CHECK TEST=[$(TEST)]",
                           "@read x; echo GOT=$$x")
    root = project(tmp_path / "p", makefile=text)
    given = tmp_path / "stdin"
    given.write_text("hello\n", encoding="utf-8")
    with given.open() as stdin:
        done = make(root, "check", env=exec_env(tmp_path), stdin=stdin)
    assert done.returncode == 0, done.stderr
    assert "GOT=hello" in done.stdout


def test_the_wrapper_trusts_every_repository_for_git(tmp_path):
    root = project(tmp_path / "p")
    env = exec_env(tmp_path)
    assert make(root, "check", env=env).returncode == 0
    config = pathlib.Path(env["FAKE_ETC"]) / "gitconfig"
    assert config.read_text(encoding="utf-8").endswith("[safe]\n\tdirectory = *\n")


def test_an_unguarded_check_runs_on_the_host_and_make_warns(tmp_path):
    text = GUARDED.replace("ifeq ($(CONTAINER_DRIVER),no)\n", "").replace(
        "endif\n", "")
    root = project(tmp_path / "p", makefile=text)
    done = make(root, "check")
    assert "overriding recipe" in done.stderr
    assert "PROJECT_CHECK" in done.stdout
    assert not any(c["argv"][0] == "run" for c in engine_calls(root))


@pytest.mark.parametrize("shell", ["sh", "busybox"])
def test_the_wrapper_is_posix_sh(tmp_path, shell):
    argv0 = shutil.which(shell)
    if argv0 is None:
        pytest.skip(f"{shell} is not installed")
    root = project(tmp_path / "p")
    argv = run_argv(root, "check")
    script = argv[argv.index("-c") + 1]
    cmd = [argv0, "sh", "-n"] if shell == "busybox" else [argv0, "-n"]
    done = subprocess.run(cmd, input=script, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
