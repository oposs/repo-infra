# container-make Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `container-make` (`build/container-make.mk`) and `ri-ci-container`, so a non-autotools project runs `make check` in its `Containerfile` image on a developer machine and in CI, and teach `check` to report the ways the pair goes wrong.

**Architecture:** A GNU Make fragment decides from `REPO_INFRA_USE_CONTAINER` whether it is the driver; as the driver its `check` recipe builds the image, picks engine, devices, mounts and the cache volume, and runs a small `sh` wrapper in the container that hands files back, trusts the mounted git repository, forwards signals and runs the project's own `check`. A remote workflow piece runs `make -C <directory> check` with docker. `check.py` learns which remote pieces the callers call, so a called piece's `Pieces:` and a remote alternative are judged instead of assumed met.

**Tech Stack:** GNU Make 4.x, POSIX `sh` (dash, busybox ash, bash), podman 4.9 / docker, GitHub Actions reusable workflows, Python 3.11 (`tomllib`), pytest.

**Spec:** [docs/superpowers/specs/2026-10-19-container-make-design.md](file:///home/oetiker/checkouts/repo-infra/docs/superpowers/specs/2026-10-19-container-make-design.md). Read it before each task; this plan cites it as "spec, <section>".

## Global Constraints

- The repository is public: no internal host names in any file.
- No em dash (U+2014) anywhere shipped (`tests/test_no_em_dash.py`), and none in this plan's outputs.
- v2 interface frozen: no existing piece changes its inputs, secrets or permissions. New pieces only.
- Names (`tests/test_naming.py`): workflow inputs snake_case, job and file names kebab-case.
- Prose (fragment header and comments, workflow comments, `CHANGES.md`, `conventions.md`, `teaching-the-standard.md`, piece `CHANGES.md`): load the `repo-infra:writing-style` skill first.
- Fragment: GNU Make only; recipes in POSIX `sh`; the in-container wrapper must run under busybox `sh`, `find`, `stat`, `chown`.
- Variable names, verbatim: `REPO_INFRA_USE_CONTAINER` (values `yes`, `no`, unset = `yes`), `CONTAINER_DRIVER` (`yes`/`no`), `CONTAINER_ENGINE`, `CONTAINER_TAG`, `CONTAINER_DEVICES`, `CONTAINER_OPTS`; pass-through `CARGO_BUILD_JOBS`, `RUST_TEST_THREADS`.
- Defaults, verbatim: tag `<clean top-level dir name>-ci:local`; volume `<project>-ci-home` at `/root`; mount top level at `/src`; `-w /src/<path>`; `--init`; `--security-opt label=disable`; podman build `--pull=newer`, docker build `--pull`; `timeout-minutes` 60; workflow permissions `contents: read`.
- Never `--privileged`, never `--userns=keep-id`.
- The fast suite (`make test`, `make lint`) needs no container engine and pulls no image.
- Machine rule for every command below: at most 4 cores; tests that start containers run under a memory cap: `systemd-run --user --scope -p MemoryMax=4G -- make test-container`. podman is the local engine. Locally `docker` is the docker CLI talking to the podman socket (Server Version 4.9.3), not a real dockerd.
- Not in this plan: moving fat32expander; #100 (autotools side to `make check`).

## Decisions this plan takes where the spec left room

Each is marked **[owner]** where the owner should confirm before merge.

- **D-a, check rule for an unrun `container-make`.** `Pieces: ri-ci-container` on the fragment does not yield a report today: `missing_dependencies` counts a remote alternative as met, and it never looks at the `Pieces:` of a *called* remote piece either, so the spec's claim that "the existing dependency report covers a call without the fragment" does not hold against `check.py`. Decision: `check` computes the set of remote pieces the callers call (`called_pieces`), and `missing_dependencies` takes it: a called remote piece's requirements are checked like an installed piece's, and a remote alternative is met only when called. One rule covers both directions. Side effect **[owner]**: existing consumers now see real findings they did not see before, for example `man missing / ri-release-rust-binaries needs it` for a repository that calls `ri-release-rust-binaries` without `build/man.mk`. That gets its own `### Changed` entry.
- **D-a2.** A call that passes `repository` (already excluded for dependabot) or a `directory` other than `""`/`"."` does not count as called: `check` reads only the top level, and the fragment of such a call lives below it. repo-infra's own `container` job therefore does not make its self-check demand `build/container-make.mk` at the top.
- **D-b, offline image builds.** podman `--pull=newer` suppresses a pull error when a local image exists (podman-build(1)); docker `--pull` fails without the registry. The fragment therefore builds with docker as `docker build --pull ... || { notice; docker build ... ; }`. Proof: a container test builds `FROM localhost:1/ri-offline-base:1` (a local tag at a registry port that refuses connections) with each available engine; on the GitHub runner the docker case runs against a real dockerd.
- **D-c, signals.** The wrapper runs `make check` in the background and `wait`s, because a shell defers a trap until a foreground child exits. A background job of a non-interactive shell has SIGINT ignored, so the trap sends **SIGTERM** to the process group (`kill -s TERM 0`), not SIGINT as the spec words it. Ctrl-C on a terminal and SIGINT without one are automated as container tests (a pty for the terminal case), run with docker on the runner. The terminal case on real docker cannot be checked on this machine; Task 7 names the CI evidence and a manual fallback.
- **D-c2, missing init.** A podman without catatonit fails `--init`. The fragment cannot read the engine's stderr while it streams test output, so after a run that exits 125, 126 or 127 it prints one hint naming the `catatonit` package and `REPO_INFRA_USE_CONTAINER=no`.
- **D-d, toolchain pin.** `check` reads `channel` from `[toolchain]` in the top-level `rust-toolchain.toml` and requires the top-level `Containerfile` to name it in a `RUN` line that calls `rustup`, or as the tag of a `rust:` base image (`FROM rust:1.85.0-trixie`). `components` and `targets` are not compared **[owner]**: rustup also downloads a missing component on every run.
- **D-e.** The spec names the workflow input `timeout-minutes`; `tests/test_naming.py` requires snake_case inputs. The input is `timeout_minutes`.
- **D-f.** Command-line overrides reach the inner make through the container's `MAKEFLAGS` environment variable, set to `-- <overrides>`, because make re-reads its own escaping (`TEST='a b'` arrives as `a b`), and the shell never sees the values. `REPO_INFRA_USE_CONTAINER=...` is filtered out of the overrides. No `MAKEFLAGS` is passed when there are none.
- **D-g.** `CONTAINER_OPTS` containing `--group-add` is refused always (the spec says it must not hold it), in the recipe.
- **D-h.** Device mode and group are printed with `ls -ld` (portable to a Mac host, unlike `stat -c`).
- **D-i.** `container-clean` removes the volume only after `<engine> volume inspect` finds it, and says so when there is none.
- **D-j.** The fixture's fragment is a symlink `tests/fixtures/container-make/build/container-make.mk -> ../../../../skills/repo-infra/assets/pieces/container-make/container-make.mk`; the top-level mount makes it resolve in the container, which is the spec's own subdirectory case.
- **D-k.** Until the first release, `container-make` v1's recorded hash may change: a task that edits the fragment deletes the `pieces/container-make/container-make.mk` entry from `skills/repo-infra/assets/generations.json` and reruns `make generations`. Never do this to a released version.

## Review Focus

1. A checkout path with a space (`~/My Project`): the mount must stay one argument and the tag clean (`my-project-ci:local`). Test in Task 1.
2. A project that sets `CONTAINER_DEVICES` or `CONTAINER_OPTS` after the include: the recipe must still see them (lazy expansion). Test in Task 1.
3. `make check REPO_INFRA_USE_CONTAINER=yes` typed by hand: the override must not reach the inner make, or the container would try to drive itself. Test in Task 1.
4. Override values with spaces and quotes (`TEST='a b'`, `TEST="it's"`): the project's `check` must see them unchanged. Test in Task 2.
5. A `make check` outside git (an unpacked tarball): top level is make's directory, no common-dir mount, volume from the directory name. Test in Task 1.

---

### File map

| File | Responsibility | Task |
|---|---|---|
| `skills/repo-infra/assets/pieces/container-make/container-make.mk` | the fragment | 1, 2, 4 |
| `skills/repo-infra/assets/pieces/container-make/CHANGES.md` | upgrade notes, `## v1` | 1 |
| `skills/repo-infra/assets/manifest.json` | entries `container-make`, `ri-ci-container` | 1, 4 |
| `skills/repo-infra/assets/generations.json` | v1 hash (`make generations`) | 1, 2, 4 |
| `tests/fakeengine.py` | fake `podman`/`docker` used by the fast tests | 1 |
| `tests/test_container_make.py` | fast suite, fake engine | 1, 2 |
| `tests/fixtures/container-make/{Containerfile,Makefile,build/container-make.mk}` | fixture project | 3 |
| `tests/test_container_make_engine.py` | `-m container`, real engines | 3 |
| `.github/workflows/ri-ci-container.yml` | workflow piece | 4 |
| `tests/test_ci_container.py` | workflow piece test | 4 |
| `.github/workflows/ci.yml`, `skills/repo-infra/references/examples/repo-infra/ci.yml` | `container` job | 4 |
| `skills/repo-infra/scripts/repo_infra/check.py` | called pieces, conflicts, guard scan, toolchain | 5 |
| `tests/test_check_container.py` | check rules | 5 |
| `skills/repo-infra/references/{conventions,teaching-the-standard,catalogue}.md`, `CHANGES.md`, `tests/test_skill.py`, `tests/test_ci_pieces.py` | docs | 6 |

---

### Task 1: The fragment's host side

**Files:**
- Create: `skills/repo-infra/assets/pieces/container-make/container-make.mk`, `skills/repo-infra/assets/pieces/container-make/CHANGES.md`, `tests/fakeengine.py`, `tests/test_container_make.py`
- Modify: `skills/repo-infra/assets/manifest.json`, `skills/repo-infra/assets/generations.json`, `skills/repo-infra/references/catalogue.md` (regenerated)

**Interfaces:**
- Produces: make variables `CONTAINER_DRIVER` (`yes`/`no`), targets `check` and `container-clean` (driver only); env var `REPO_INFRA_WRAPPER` exported to the `check` recipe only (filled in Task 2; in this task a placeholder `make check`); `tests/fakeengine.py` with `install_fake(bin_dir: pathlib.Path) -> None` writing executable `podman` and `docker`, and `calls(log: pathlib.Path) -> list[dict]` reading its log; `tests/test_container_make.py` helpers `project(root: pathlib.Path, makefile: str = GUARDED, git: bool = True) -> pathlib.Path` and `make(root, *args, engines=("podman", "docker"), env=None, stdin=subprocess.DEVNULL) -> subprocess.CompletedProcess`.

Header (marker and fields exactly; body comments per writing-style):

```make
# repo-infra: container-make v1
#
# Purpose: Run `make check` in the image the project's Containerfile builds, for a project without autotools (#94).
# Choose: The tests need tools or root beyond the runner image (D16) and the build is not autotools.
# Supplies: A Containerfile (contract in references/conventions.md) and a Makefile that includes this file first and guards its own `check:` with `ifeq ($(CONTAINER_DRIVER),no)`.
```

(`Pieces: ri-ci-container` is added in Task 4, when that piece exists.)

Manifest entry: `"container-make": {"target": "build/container-make.mk", "group": "build"}`. Piece `CHANGES.md`: `# container-make`, the two standard intro lines from `pieces/container/CHANGES.md`, `## v1` "First version."

Fake engine (`tests/fakeengine.py`): a Python script installed as both `podman` and `docker`, appending one JSON line `{"engine": <basename argv0>, "argv": argv[1:], "stdin": <text read for `build`>}` to `$FAKE_ENGINE_LOG`. Behaviour by subcommand: `build` reads stdin, exits `1` when `FAKE_BUILD_FAIL_PULL=1` and a `--pull*` argument is present, else `0`; `info` prints `$FAKE_PODMAN_INFO` (default `false crun`); `volume inspect` exits `0` when `FAKE_VOLUME=1`, else `1`; `volume rm` exits 0; `run` exits `$FAKE_RUN_STATUS` (default 0), or with `FAKE_EXEC=1` emulates (Task 2). `make()` runs `make` with `PATH=<fake bin with only the requested engines>:<dir holding only symlinks to make, sh, git, find, ls, tr, sed, awk, basename, dirname, cat, head, wc, printf>` so a real podman never answers, and strips `MAKEFLAGS`, `MAKELEVEL`, `MFLAGS` as `tests/test_man_build.py::make_env` does; `LC_ALL=C`.

`GUARDED` Makefile:

```make
CONTAINER_DEVICES =
include build/container-make.mk

.PHONY: all
all:
	@echo PROJECT_ALL

ifeq ($(CONTAINER_DRIVER),no)
check:
	@echo PROJECT_CHECK TEST=[$(TEST)]
endif
```

- [ ] **Step 1: Write the failing tests** in `tests/test_container_make.py`. Helper `argv_of(calls, sub)` returns the argv of the single call whose first argument is `sub`; `pairs(argv, a, b)` is true when `b` follows `a`. Assertions:

```python
def test_including_the_fragment_keeps_the_projects_default_goal(tmp_path):
    # include first and include last; bare `make` prints PROJECT_ALL, logs no engine call
def test_make_all_works_with_no_engine_on_path(tmp_path):
    done = make(project(tmp_path / "p"), "all", engines=())
    assert done.returncode == 0 and "PROJECT_ALL" in done.stdout
def test_check_without_an_engine_names_the_escape(tmp_path):
    done = make(project(tmp_path / "p"), "check", engines=())
    assert done.returncode != 0
    assert "REPO_INFRA_USE_CONTAINER=no" in done.stderr
def test_use_container_no_runs_the_projects_check_here(tmp_path):
    done = make(root, "check", engines=(), env={"REPO_INFRA_USE_CONTAINER": "no"})
    assert "PROJECT_CHECK" in done.stdout
@pytest.mark.parametrize("value", ["", "yes"])
def test_use_container_unset_or_yes_drives(tmp_path, value):  # a `run` call is logged
def test_any_other_value_is_an_error_naming_yes_and_no(tmp_path):
    # REPO_INFRA_USE_CONTAINER=maybe -> rc != 0, stderr names "yes" and "no", no engine call
def test_podman_wins_when_both_exist / test_docker_when_only_docker / test_container_engine_picks_docker
def test_container_engine_other_than_podman_or_docker_is_refused(tmp_path)
def test_the_image_is_built_from_the_containerfile_on_stdin(tmp_path):
    # build argv == ["build", "--pull=newer", "-t", "p-ci:local", "-"] for podman,
    # ["build", "--pull", "-t", "p-ci:local", "-"] for docker; stdin == Containerfile text
def test_a_failed_docker_pull_builds_again_on_the_local_copy(tmp_path):
    # FAKE_BUILD_FAIL_PULL=1, docker: two build calls, second without --pull, a notice on stderr, run follows
def test_a_missing_containerfile_is_named_and_nothing_runs(tmp_path)
def test_the_run_carries_the_fixed_options(tmp_path):
    # run argv contains "--rm", "--init", "--security-opt", "label=disable",
    # "-e", "REPO_INFRA_USE_CONTAINER=no", ["-v", f"{top}:/src"], ["-v", "p-ci-home:/root"],
    # ["-w", "/src"]; no "--privileged", no "--userns=keep-id"; no "-i"/"-t" with stdin DEVNULL
def test_a_terminal_adds_i_and_t_together(tmp_path):
    # stdin = slave end of pty.openpty(): "-i" and "-t" both present
@pytest.mark.parametrize("name, tag", [
    ("My Project", "my-project-ci:local"), ("Foo__Bar", "foo-bar-ci:local"),
    ("--x--", "x-ci:local"), ("über", "ber-ci:local"), ("...", "project-ci:local")])
def test_the_tag_is_the_cleaned_top_level_name(tmp_path, name, tag)
    # also: the "-v" mount value for "My Project" is one argv element
def test_container_tag_set_by_the_project_names_tag_and_volume(tmp_path):
    # CONTAINER_TAG = Reg/x:1 before include -> tag "Reg/x:1", volume "Reg-x-1-ci-home"
def test_a_subdirectory_mounts_the_top_level_and_works_below_it(tmp_path):
    # project in top/sub, make -C sub check: ["-v", f"{top}:/src"], ["-w", "/src/sub"], build stdin == sub/Containerfile
def test_a_worktree_mounts_the_common_dir_and_shares_the_main_volume(tmp_path):
    # main checkout "main", `git worktree add ../Feature X`: tag "feature-x-ci:local",
    # volume "main-ci-home", ["-v", f"{common}:{common}"] with common = main/.git
def test_outside_git_the_top_level_is_makes_directory(tmp_path):
    # git=False: ["-v", f"{root}:/src"], ["-w", "/src"], no second -v besides the volume
def test_a_present_device_is_passed_with_its_mode_and_an_absent_one_skipped(tmp_path):
    # CONTAINER_DEVICES = <tmp>/fake-kvm <tmp>/none: ["--device", ".../fake-kvm"], stdout/stderr
    # shows the ls -ld mode of fake-kvm, a notice names .../none as skipped
def test_podman_with_a_device_keeps_groups(tmp_path)          # "--group-add", "keep-groups"
def test_docker_with_a_device_adds_no_group(tmp_path)
@pytest.mark.parametrize("info", ["true crun", "false runc"])
def test_podman_remote_or_without_crun_leaves_keep_groups_out_with_a_notice(tmp_path, info)
def test_no_device_no_keep_groups(tmp_path)
def test_devices_and_opts_set_after_the_include_still_count(tmp_path)   # Review Focus 2
def test_container_opts_are_split_into_words(tmp_path):        # "--cpus=4", "--memory=6g"
def test_container_opts_with_group_add_is_refused(tmp_path)
@pytest.mark.parametrize("var", ["CARGO_BUILD_JOBS", "RUST_TEST_THREADS"])
def test_cargo_variables_pass_only_when_set(tmp_path, var):   # ["-e", var] present iff set
def test_overrides_reach_the_inner_make_through_makeflags(tmp_path):
    # make check TEST=foo -> ["-e", "MAKEFLAGS=-- TEST=foo"]; no override -> no MAKEFLAGS
    # make -j3 check -> no "--jobserver" and no "-j" anywhere in the run argv
def test_use_container_on_the_command_line_does_not_reach_the_inner_make(tmp_path):  # Review Focus 3
    # make check REPO_INFRA_USE_CONTAINER=yes TEST=a -> ["-e", "MAKEFLAGS=-- TEST=a"]
def test_the_runs_exit_status_is_makes(tmp_path):              # FAKE_RUN_STATUS=3 -> rc != 0
@pytest.mark.parametrize("status", [125, 126, 127])
def test_an_engine_failure_names_catatonit(tmp_path, status)   # stderr names "catatonit"
def test_container_clean_removes_the_volume(tmp_path):
    # FAKE_VOLUME=1: a ["volume", "rm", "p-ci-home"] call; FAKE_VOLUME unset: no rm, a notice
def test_container_clean_is_not_defined_inside(tmp_path):
    # REPO_INFRA_USE_CONTAINER=no make container-clean -> "No rule to make target"
def test_the_fragment_carries_its_marker_and_no_em_dash()
```

- [ ] **Step 2: Run them, expect failures**

Run: `python3 -m pytest -q tests/test_container_make.py`
Expected: errors, `build/container-make.mk` missing.

- [ ] **Step 3: Write the fragment's host side**

Structure (top to bottom):
1. Header and comments (writing-style).
2. `REPO_INFRA_USE_CONTAINER` check: empty or `yes` -> `CONTAINER_DRIVER := yes`; `no` -> `CONTAINER_DRIVER := no`; else `$(error ...)` naming `yes` and `no`.
3. `ifeq ($(CONTAINER_DRIVER),yes)`: save `_repo_infra_cm_goal := $(.DEFAULT_GOAL)`; defaults with `?=` (`CONTAINER_ENGINE`, `CONTAINER_DEVICES`, `CONTAINER_OPTS`); record `_repo_infra_cm_tag_given` from `$(origin CONTAINER_TAG)` *before* the tag default; `.PHONY: check container-clean`; the two recipes; restore `.DEFAULT_GOAL`; `endif`.
4. Every value that runs a command (git, engine lookup, name cleaning) is computed inside the recipe shell, never with `:=` or `$(shell)` at parse time.

The `check` recipe, one `sh` script (`set -eu`), in this order:
1. Engine: `$(CONTAINER_ENGINE)` if set (must be `podman` or `docker`), else `podman` if `command -v podman`, else `docker`, else the error naming `REPO_INFRA_USE_CONTAINER=no`.
2. Refuse `CONTAINER_OPTS` holding `--group-add`.
3. `top=$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)`; `rel` = `$(CURDIR)` relative to `top` (empty at top, `case` on `"$top"/*`); `common=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || :)`; the common mount when `common` is set and not under `top`.
4. `Containerfile` in `$(CURDIR)` or stop with its path named.
5. Tag: `$(CONTAINER_TAG)` when given, else `$(clean "$(basename "$top")")-ci:local`. Volume: when the tag was given, the tag with `:` and `/` replaced by `-`; else `clean` of the basename of `dirname "$common"` in git, of `$top` outside; then `-ci-home`.
6. Build (podman `--pull=newer`; docker `--pull` with the fallback of D-b).
7. Devices: for each word of `CONTAINER_DEVICES`, `[ -e ]` -> `--device <d>` and print `ls -ld` mode and owner:group; else a notice that it is skipped.
8. keep-groups: podman and at least one device: `podman info --format '{{.Host.ServiceIsRemote}} {{.Host.OCIRuntime.Name}}'`; `false crun` -> `--group-add keep-groups`, otherwise a notice.
9. `[ -t 0 ]` -> `-i -t`.
10. Run, argv in this order: `run --rm --init --security-opt label=disable [-i -t] [--device ...] [--group-add keep-groups] $(CONTAINER_OPTS) -e REPO_INFRA_USE_CONTAINER=no [-e MAKEFLAGS=-- <overrides>] [-e CARGO_BUILD_JOBS] [-e RUST_TEST_THREADS] -v <top>:/src [-v <common>:<common>] -v <volume>:/root -w /src[/<rel>] <tag> sh -c "$REPO_INFRA_WRAPPER" sh /src [<common>]`; on status 125, 126 or 127 print the catatonit hint; exit with the run's status.

Overrides: `$(filter-out REPO_INFRA_USE_CONTAINER=%,$(MAKEOVERRIDES))`, single-quoted for the recipe with `$(subst ','\'',...)`.

The name cleaning, exact (the spec fixes the rule, the separator choice is this plan's: a run becomes `-`):

```sh
clean() {
	printf '%s' "$1" | LC_ALL=C tr '[:upper:]' '[:lower:]' \
	  | LC_ALL=C sed -e 's/[^a-z0-9._-]/-/g' -e 's/[._-]\{2,\}/-/g' -e 's/^[._-]*//' -e 's/[._-]*$//' \
	  | { read -r n || :; echo "${n:-project}"; }
}
```

`container-clean`: same engine lookup and volume name; `volume inspect` then `volume rm`, or a notice (D-i).

In this task `REPO_INFRA_WRAPPER` is `check: export REPO_INFRA_WRAPPER = make check` (Task 2 replaces it).

- [ ] **Step 4: Register the piece:** manifest entry, `CHANGES.md`, `make generations`, `make catalogue`.

- [ ] **Step 5: Run the tests**

Run: `python3 -m pytest -q tests/test_container_make.py && make lint test`
Expected: all pass; `make test` count grows by exactly the number of tests added here.

- [ ] **Step 6: Commit**

```bash
git add skills/repo-infra/assets/pieces/container-make skills/repo-infra/assets/manifest.json \
  skills/repo-infra/assets/generations.json skills/repo-infra/references/catalogue.md \
  tests/fakeengine.py tests/test_container_make.py
git commit -m "Add container-make, the host side of the make container driver (#94)"
```

---

### Task 2: The in-container wrapper

**Files:**
- Modify: `skills/repo-infra/assets/pieces/container-make/container-make.mk`, `skills/repo-infra/assets/generations.json` (D-k), `tests/fakeengine.py`, `tests/test_container_make.py`

**Interfaces:**
- Consumes: Task 1's run argv layout (`... <tag> sh -c "$REPO_INFRA_WRAPPER" sh /src [<common>]`), `fakeengine` log.
- Produces: `REPO_INFRA_WRAPPER`, defined with `define` and exported only to `check`; positional parameters are the paths to hand back, `$1` is `/src`.

Fake `run` emulation (`FAKE_EXEC=1`): map each `-v host:ctr` whose `ctr` is `/src` (and identical common-dir mounts); `cwd` = the `-w` path with `/src` replaced by the host top; environment = only the `-e` pairs (`-e NAME` takes the fake's own environment value) plus `PATH`, `HOME=<tmp>`; argv after the tag with every `/src` argument mapped, and `/etc/gitconfig` in the `-c` text replaced by `$FAKE_ETC/gitconfig`; run it, exit with its status.

The wrapper, exact (the signal and stdin handling is not determined by the spec; see D-c):

```sh
set -u
owner=$(stat -c %u "$1") && group=$(stat -c %g "$1") || exit 125
handback() {
	find "$@" ! -user "$owner" -exec chown -h "$owner:$group" {} + 2>/dev/null || :
	count=$(find "$@" ! -user "$owner" -print 2>/dev/null | wc -l)
	if [ "$count" -gt 0 ]; then
		echo "build/container-make.mk: $count files in the checkout belong to another user and could not be handed back; fix them on the host. The first ones:" >&2
		find "$@" ! -user "$owner" -print 2>/dev/null | head -n 5 | sed 's/^/  /' >&2
	fi
}
printf '[safe]\n\tdirectory = *\n' >> /etc/gitconfig 2>/dev/null || :
handback "$@"
stop() { trap '' INT TERM; kill -s TERM 0 2>/dev/null; wait; exit "$1"; }
trap 'stop 130' INT
trap 'stop 143' TERM
exec 3<&0
make check 0<&3 3<&- &
wait "$!"
status=$?
trap - INT TERM
handback "$@"
exit "$status"
```

(In the `.mk` every `$` is `$$`. `exec 3<&0` keeps the terminal on make's stdin: a non-interactive shell gives a background job `/dev/null`.)

- [ ] **Step 1: Write the failing tests** (all `FAKE_EXEC=1`, `REPO_INFRA_USE_CONTAINER` unset):

```python
def test_the_inner_make_runs_the_projects_guarded_check(tmp_path):
    # stdout has "PROJECT_CHECK TEST=[]", rc == 0
@pytest.mark.parametrize("value", ["foo", "a b", "it's", "x$y"])
def test_an_override_reaches_the_projects_check_unchanged(tmp_path, value):   # Review Focus 4
    # make check TEST=<value> -> stdout has f"PROJECT_CHECK TEST=[{value}]"
def test_the_projects_exit_status_survives_the_handback(tmp_path):
    # check: exit 3 inside the guard -> host make rc != 0 and "Error 3" in stderr
def test_the_wrapper_trusts_every_repository_for_git(tmp_path):
    # $FAKE_ETC/gitconfig ends with "[safe]\n\tdirectory = *\n"
def test_an_unguarded_check_runs_on_the_host_and_make_warns(tmp_path):
    # documents the hazard Task 5 reports: `check:` outside the guard after the include ->
    # "overriding recipe" in stderr and no engine `run` call
def test_the_wrapper_is_posix_sh(tmp_path):
    # `sh -n` (and `busybox sh -n` when busybox is on PATH) accepts the expanded REPO_INFRA_WRAPPER,
    # read via `make -p` or by running the fake with FAKE_DUMP_WRAPPER=1
```

- [ ] **Step 2: Run them, expect failures** (`PROJECT_CHECK` absent: the Task 1 placeholder recurses into the driver or fails).

- [ ] **Step 3: Replace the placeholder with the wrapper; re-record generations (D-k).**

- [ ] **Step 4: Run** `python3 -m pytest -q tests/test_container_make.py && make lint test`. Expected: pass.

- [ ] **Step 5: Commit** `git commit -m "container-make: hand files back, trust the mount for git, forward signals"`

---

### Task 3: Fixture and real-engine tests

**Files:**
- Create: `tests/fixtures/container-make/Containerfile`, `tests/fixtures/container-make/Makefile`, `tests/fixtures/container-make/build/container-make.mk` (symlink, D-j), `tests/test_container_make_engine.py`

**Interfaces:**
- Consumes: the fragment (Tasks 1, 2).
- Produces: the fixture `ci.yml` calls in Task 4 (`directory: tests/fixtures/container-make`); fixture knobs `TEST`, `SLEEP`, `FAIL`, `CACHE` (`write` puts `/root/marker`, `read` fails without it); fixture output lines `fixture: check ran as root`, `fixture: sleeping`, `fixture: /dev/kvm opens` or `fixture: no /dev/kvm`.

Containerfile: `FROM docker.io/library/alpine@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b` (the autotools fixture's pin, so the cache is shared), `RUN apk add --no-cache make git`, a comment naming alpine 3.24.1, no `USER`, no `COPY`.

Makefile: `CONTAINER_DEVICES = /dev/kvm`, the include, an `all` that prints, and guarded `check` that: fails unless `id -u` is 0; writes `check-ran.txt` holding `$(TEST)`; opens `/dev/kvm` read-write when it exists (`sh -c 'exec 3<> /dev/kvm'`) and prints which; runs `git status --short >/dev/null`; prints `fixture: check ran as root`; with `SLEEP` prints `fixture: sleeping` and sleeps; with `CACHE=write` writes `/root/marker`, with `CACHE=read` fails unless it exists; with `FAIL` exits 3.

`tests/test_container_make_engine.py`: `pytestmark = pytest.mark.container`; engines parametrized from `RI_TEST_ENGINES` (default `podman docker`), each skipped when `<engine> info` fails, failed instead when `CI` is set (the `require` pattern of `tests/conftest.py`); a session fixture copies the fixture into a tmp git repository (copytree resolves the symlink), commits it; every run sets `CONTAINER_ENGINE` and `CONTAINER_OPTS=--cpus=4 --memory=2g`; teardown runs `make container-clean` and `<engine> rmi <tag>`.

- [ ] **Step 1: Write the tests**

```python
def test_check_runs_as_root_and_leaves_files_to_the_caller(engine, tree):
    # rc 0, "fixture: check ran as root"; check-ran.txt exists, st_uid == os.getuid()
    # a file the check created under a new directory too
def test_a_failing_check_fails_make_and_still_hands_back(engine, tree):    # FAIL=1 -> rc != 0
def test_an_override_reaches_the_fixture(engine, tree):                     # TEST='a b' -> file "a b"
def test_a_worktree_runs_git_in_the_container(engine, tree):
    # git worktree add; make check there; rc 0; main checkout's .git has no file with another uid
def test_a_subdirectory_project_sees_the_whole_repository(engine, tree):    # make -C sub check
def test_a_second_run_reuses_the_cache_volume(engine, tree):
    # make check CACHE=write, then make check CACHE=read: rc 0 (the volume kept /root/marker)
def test_an_offline_build_uses_the_local_base_image(engine, tmp_path):     # D-b
    # tag the alpine digest as localhost:1/ri-offline-base:1; Containerfile FROM it; make check rc 0;
    # docker: stderr carries the fallback notice
def test_sigint_without_a_terminal_stops_the_container(engine, tree):      # D-c
    # Popen(start_new_session=True, stdin=DEVNULL), SLEEP=120; after "fixture: sleeping"
    # os.killpg(SIGINT); exits within 30 s; `<engine> ps -q --filter ancestor=<tag>` empty
def test_ctrl_c_on_a_terminal_stops_the_container(engine, tree):           # D-c
    # same, stdin/stdout on a pty slave made the controlling terminal; write b"\x03" to the master
def test_a_missing_init_names_catatonit(tree):                             # podman only, D-c2
    # CONTAINER_OPTS=--init-path=/nonexistent -> rc != 0 and "catatonit" in output
def test_kvm_opens_when_the_host_has_it(engine, tree):
    # skip unless /dev/kvm is readable and writable by this user; "fixture: /dev/kvm opens"
```

- [ ] **Step 2: Run them, capped**

Run: `systemd-run --user --scope -p MemoryMax=4G -- make test-container`
Expected: the new tests pass for podman; docker passes or is explained (local docker is the podman socket; a docker-only failure here is recorded in the task report, not worked around). The existing autotools container tests still pass.

- [ ] **Step 3: Time it.** If `make test-container` takes longer than 12 minutes locally, raise `timeout-minutes` of the `repo-infra-selftest` job in `.github/workflows/ri-ci-repo-infra-selftest.yml` from 20 to 40.

- [ ] **Step 4: Fast gates** `make lint test` (the engine tests are deselected; no image pulled).

- [ ] **Step 5: Commit** `git commit -m "container-make: fixture and real-engine tests"`

---

### Task 4: The workflow piece `ri-ci-container`

**Files:**
- Create: `.github/workflows/ri-ci-container.yml`, `tests/test_ci_container.py`
- Modify: `skills/repo-infra/assets/manifest.json`, `skills/repo-infra/assets/pieces/container-make/container-make.mk` (add `# Pieces: ri-ci-container` after `Supplies:`), `skills/repo-infra/assets/generations.json` (D-k), `skills/repo-infra/references/catalogue.md`, `.github/workflows/ci.yml`, `skills/repo-infra/references/examples/repo-infra/ci.yml`

**Interfaces:**
- Consumes: the fixture (Task 3).
- Produces: inputs `ref` (string, default `''`), `repository` (string, default `${{ github.repository }}`), `directory` (string, default `.`), `timeout_minutes` (number, default 60); job id `container`; manifest `"ri-ci-container": {"kind": "remote", "group": "ci"}`.

Header, exact fields:

```yaml
# repo-infra: ri-ci-container v2
#
# Purpose: Run `make check` in the image the project's Containerfile builds (#94).
# Choose: The project includes build/container-make.mk.
# Supplies: A Containerfile and a Makefile that includes build/container-make.mk; `directory` when it is not at the top level.
# Pieces: container-make
# Call:
#   container:
#     uses: oposs/repo-infra/.github/workflows/ri-ci-container.yml@v2
#     with:
#       ref: ${{ inputs.ref }}
```

Body: `inputs.ref`/`repository` descriptions copied from `ri-ci-man.yml`; `permissions: contents: read`; one job `container`, `name: make check in the container`, `runs-on: ubuntu-latest`, `timeout-minutes: ${{ inputs.timeout_minutes }}`, steps: checkout with `repository`/`ref`; `run: make -C "$DIRECTORY" check` with `env: DIRECTORY: ${{ inputs.directory }}`, `CONTAINER_ENGINE: docker`, and a comment saying why docker (spec, "ri-ci-container").

`ci.yml` job (and the identical example copy), with the skip `if:` every other job carries, and `container` added to `ci-passed`'s `needs:`:

```yaml
  container:
    if: <the same skip expression as the other jobs>
    uses: ./.github/workflows/ri-ci-container.yml
    with:
      ref: ${{ inputs.ref }}
      directory: tests/fixtures/container-make
```

- [ ] **Step 1: Write the failing tests** in `tests/test_ci_container.py`:

```python
def test_the_piece_declares_exactly_its_one_job():          # list(doc["jobs"]) == ["container"]
def test_the_inputs_and_their_defaults():                    # directory ".", timeout_minutes 60, type number
def test_the_job_timeout_comes_from_the_input():             # "${{ inputs.timeout_minutes }}"
def test_it_runs_make_check_in_the_directory_with_docker():
    # the run step's text == 'make -C "$DIRECTORY" check'; env CONTAINER_ENGINE == "docker",
    # DIRECTORY == "${{ inputs.directory }}"
def test_it_needs_only_contents_read():                      # doc["permissions"] == {"contents": "read"}
def test_the_step_runs_the_fixture_through_the_fake_engine(tmp_path):
    # run the step's shell (bash -e -c) with DIRECTORY=tests/fixtures/container-make on a copy
    # of the repository's fixture and the fake docker on PATH: one docker build and one docker run
def test_repo_infra_ci_runs_the_fixture_through_the_piece():
    # ci.yml job "container" uses ./.github/workflows/ri-ci-container.yml with that directory,
    # and "container" is in ci-passed needs
```

- [ ] **Step 2: Run, expect failures.** `python3 -m pytest -q tests/test_ci_container.py`

- [ ] **Step 3: Write the workflow, manifest entry, fragment `Pieces:` line, `ci.yml` job and example copy; `make generations` (D-k); `make catalogue`.**

- [ ] **Step 4: Run** `python3 -m pytest -q tests/test_ci_container.py tests/test_pieces.py tests/test_naming.py tests/test_self_check.py tests/test_catalogue.py tests/test_v2_compat.py && make lint test`. Expected: pass, including `test_this_repository_passes_its_own_check` (the `directory` call is not counted, D-a2; until Task 5 nothing counts calls at all).

- [ ] **Step 5: Commit** `git commit -m "Add ri-ci-container and run the fixture through it in CI (#94)"`

---

### Task 5: What `check` reports

**Files:**
- Modify: `skills/repo-infra/scripts/repo_infra/check.py`
- Create: `tests/test_check_container.py`
- Modify (if a case breaks): `tests/test_check.py`, `tests/test_dependabot.py`

**Interfaces:**
- Consumes: `callers.jobs`, `callers.normal_uses`, `load_pieces`, `piece_state`, `report.Item`.
- Produces (all in `check.py`):
  - `called_pieces(docs: dict, pieces: dict) -> set[str]`: remote pieces a job calls, without `with.repository` and with `with.directory` absent, `""` or `"."` (D-a2). `rendered()` uses it instead of its own set.
  - `missing_dependencies(pieces, states, called=None) -> list[tuple[str, str]]`: `called=None` keeps today's behaviour (cli's `_pending` passes nothing, so `apply` never tries to install a remote piece). With a set: users are the present local pieces plus the called remote pieces; a remote alternative is met only when it is in `called`.
  - `piece_items(repo_root, pieces, published, called=None)`: passes `called` on; a missing remote dependency reads `f"{user} needs it; no caller job calls {piece.uses} (see its Call: in the catalogue)"`, a local one keeps `f"{user} needs it"`.
  - `unguarded_check_lines(text: str) -> list[int]`
  - `toolchain_pin_missing(toolchain: str, containerfile: str) -> str | None`
  - `container_make_items(repo_root, pieces, published, called) -> list[Item]`, all `Item("pieces", "container-make", state, detail)`, only when `container-make` is not absent:
    - `conflict` when `container` or `container-m4` is not absent (detail names both files and says an autotools project keeps `container` + `container-m4`, any other keeps `container-make`);
    - `conflict` when `ri-ci-perl-mkpl` or `ri-ci-perl-autotools` is in `called` (detail: a generated Perl `Makefile` runs its tests on the runner);
    - `problem` per top-level make file (first of `GNUmakefile`, `makefile`, `Makefile`) that includes `container-make.mk` and has unguarded `check:` lines, naming the lines and `ifeq ($(CONTAINER_DRIVER),no)`;
    - `problem` when `toolchain_pin_missing` returns a channel, naming it and `RUN rustup toolchain install <channel>`.
  - `run()` computes `called = called_pieces(docs, pieces)` once and passes it to `piece_items` and `container_make_items`.

The guard scan, exact (the spec says "a plain text scan"; the conditional tracking is this plan's):

```python
_INCLUDE = re.compile(r"^\s*-?s?include\s+\S*container-make\.mk\b", re.MULTILINE)
_GUARD = re.compile(r"^ifeq\s*\(\s*\$[({]CONTAINER_DRIVER[)}]\s*,\s*no\s*\)$")
_OPEN = re.compile(r"^(ifeq|ifneq|ifdef|ifndef)\b")
_RULE = re.compile(r"^([^:=#\t][^:=#]*?)::?(?!=)")


def unguarded_check_lines(text):
    """Line numbers of `check:` rules outside `ifeq ($(CONTAINER_DRIVER),no)`."""
    if not _INCLUDE.search(text):
        return []
    stack, found = [], []
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith("\t"):
            continue
        code = line.split("#", 1)[0].strip()
        if _OPEN.match(code):
            stack.append(bool(_GUARD.match(code)))
        elif code.startswith("else") and stack:
            stack[-1] = bool(_GUARD.match(code[4:].strip()))
        elif code == "endif" and stack:
            stack.pop()
        else:
            rule = _RULE.match(code)
            if (rule and "check" in rule[1].split() and "=" not in code[rule.end():]
                    and not any(stack)):
                found.append(number)
    return found
```

`toolchain_pin_missing`: `channel` = `tomllib.loads(toolchain)["toolchain"]["channel"]` (None on a parse error or no string); join backslash continuations; skip comment lines; met when a line whose first word is `RUN` contains `rustup` and the channel as a token (`(?<![\w.-])<channel>(?![\w.])`), or a `FROM` line matches `\brust:<channel>(?![\w.])`.

- [ ] **Step 1: Write the failing tests** in `tests/test_check_container.py` (real `load_pieces()`/`load_published()`, repositories under `tmp_path`, the fragment installed from the asset, callers written as YAML calling `oposs/repo-infra/.github/workflows/<piece>.yml@v2`):

```python
def test_a_call_of_ri_ci_container_without_the_fragment_is_reported():
    # ("container-make", "missing", "ri-ci-container needs it")
def test_the_fragment_without_a_call_is_reported():
    # ("ri-ci-container", "missing", detail starts "container-make needs it; no caller job calls")
def test_the_pair_together_reports_nothing_missing():
def test_a_call_with_directory_or_repository_is_not_counted():          # D-a2, both directions
def test_a_called_piece_needs_its_build_files():
    # calling ri-release-rust-binaries without build/man.mk -> ("man", "missing", "ri-release-rust-binaries needs it")
def test_a_remote_alternative_is_met_only_when_called():
    # calling ri-release-nfpm alone -> ri-release-rust-binaries missing; with ri-release-go-binaries -> nothing
def test_cli_pending_never_lists_a_remote_piece(tmp_path):               # cli._pending with the fragment only
def test_container_make_with_the_autotools_driver_is_a_conflict():      # container and/or container-m4
@pytest.mark.parametrize("perl", ["ri-ci-perl-mkpl", "ri-ci-perl-autotools"])
def test_container_make_with_a_perl_ci_piece_is_a_conflict(perl):
@pytest.mark.parametrize("text, lines", [
    (GUARDED, []),
    ("include build/container-make.mk\ncheck:\n\tx\n", [2]),
    ("include build/container-make.mk\nifeq ($(CONTAINER_DRIVER),no)\ncheck: a\nelse\ncheck:\n\tx\nendif\n", [5]),
    ("include build/container-make.mk\nifeq (${CONTAINER_DRIVER}, no)\nifdef X\ncheck:\nendif\nendif\n", []),
    ("include build/container-make.mk\n.PHONY: check\n", []),
    ("include build/container-make.mk\ncheck: TEST = x\n", []),
    ("check:\n\tx\n", []),                      # no include, no rule applies
    ("include build/container-make.mk\nall check:\n", [2]),
])
def test_unguarded_check_lines(text, lines):
@pytest.mark.parametrize("containerfile, missing", [
    ("FROM rust:1-trixie\nRUN rustup toolchain install 1.85.0\n", None),
    ("FROM docker.io/library/rust:1.85.0-trixie\n", None),
    ("FROM rust:1-trixie\nRUN apt-get update && \\\n    rustup toolchain install 1.85.0\n", None),
    ("FROM rust:1-trixie\n# RUN rustup toolchain install 1.85.0\n", "1.85.0"),
    ("FROM rust:1.85-trixie\n", "1.85.0"),
    ("FROM rust:1-trixie\nRUN rustup toolchain install 1.85.01\n", "1.85.0"),
])
def test_toolchain_pin_missing(containerfile, missing):
    # toolchain = '[toolchain]\nchannel = "1.85.0"\n'; also: no channel -> None, bad TOML -> None
def test_the_items_appear_in_check_run():
    # check.run on a repo with the fragment, an unguarded Makefile, a pin missing, no ci call:
    # rows for ri-ci-container missing, container-make problem (Makefile), container-make problem (toolchain)
```

- [ ] **Step 2: Run, expect failures.** `python3 -m pytest -q tests/test_check_container.py`

- [ ] **Step 3: Implement** the functions above; update the comment in `missing_dependencies` (it currently says a remote alternative "counts as met").

- [ ] **Step 4: Run** `make lint test`. Expected: pass, with `test_this_repository_passes_its_own_check` still green. If an existing test in `tests/test_check.py` or `tests/test_dependabot.py` changes result, the new behaviour is the cause: adapt the test only when D-a says the new result is right, and list it in the task report.

- [ ] **Step 5: Commit** `git commit -m "check: judge called pieces' needs, report container-make misuse (#94)"` with a body explaining D-a (the report existed only for installed pieces).

---

### Task 6: Documentation and changelog

Load `repo-infra:writing-style` before writing.

**Files:**
- Modify: `skills/repo-infra/references/conventions.md`, `skills/repo-infra/references/teaching-the-standard.md`, `skills/repo-infra/references/catalogue.md` (`make catalogue`), `CHANGES.md`, `tests/test_skill.py`, `tests/test_ci_pieces.py` (comment listing which test file covers `.mk`: add `tests/test_container_make.py`)

- [ ] **Step 1: Failing tests** in `tests/test_skill.py`:

```python
def test_conventions_states_the_second_containerfile_contract():
    # text has "container-make", "REPO_INFRA_USE_CONTAINER", "CONTAINER_DRIVER", "/root",
    # "CARGO_TARGET_DIR=/src/target/container", "CARGO_HOME=/root/.cargo", "GOPATH=/root/go",
    # "rustup toolchain install"
def test_the_threshold_names_both_drivers():
    # teaching-the-standard.md "The threshold you will hit most often" section names
    # "container-m4", "container", "container-make" and "ri-ci-container"
```

- [ ] **Step 2: Write** in `conventions.md`, after the D18 contract, a section "The Containerfile contract for container-make (#94)": the seven points of spec, "The Containerfile contract, second variant", verbatim in substance; the detection rule (spec, "Detecting the container"); the guarded `check` example; the variables `CONTAINER_TAG`, `CONTAINER_DEVICES`, `CONTAINER_OPTS`, `CONTAINER_ENGINE`; `make container-clean`. In `teaching-the-standard.md` the threshold paragraph names both answers (spec, "Documentation").

- [ ] **Step 3: `CHANGES.md`** under `## [Unreleased]`:
  - `### New`: one entry, at most three sentences, leading with what the reader does: a project without autotools runs `make check` in its `Containerfile` image on a developer machine (podman or docker) and in CI, through `build/container-make.mk` (`container-make`) and `ri-ci-container`; `REPO_INFRA_USE_CONTAINER=no` runs the tests natively; `check` reports either piece alone, `container-make` with `container`/`container-m4` or a `ri-ci-perl-*` piece, a `check:` outside `ifeq ($(CONTAINER_DRIVER),no)`, and a `rust-toolchain.toml` pin the `Containerfile` does not install. Ends `(#94)`.
  - `### Changed`: `check` now reports a build file that a called workflow piece needs, for example `man missing` with "ri-release-rust-binaries needs it", and a remote alternative counts only when a caller calls it. Ends `(#94)`.

- [ ] **Step 4: Run** `make catalogue && make lint test`. Expected: pass, no em dash.

- [ ] **Step 5: Commit** `git commit -m "Document container-make and its Containerfile contract (#94)"`

---

### Task 7: Proof on GitHub (owner, after the pull request opens)

No files. This task is a checklist for the pull request description; nothing here may be marked done from a local run.

- [ ] `CI / container / make check in the container` is green; its log shows the `/dev/kvm` line with mode and group and `fixture: /dev/kvm opens` (spec, "Left to the builder": the `/dev/kvm` handling proven on a real run). If the hosted runner has no `/dev/kvm`, the log says `fixture: no /dev/kvm`; record that, the run is still valid.
- [ ] `CI / selftest / Container self-test` ran `tests/test_container_make_engine.py` for **docker** without skips: that is the real-dockerd proof of D-b (offline fallback) and D-c (Ctrl-C on a terminal, SIGINT without one).
- [ ] If the docker pty test cannot run on the runner, verify by hand on a host with a real dockerd: `CONTAINER_ENGINE=docker make -C tests/fixtures/container-make check SLEEP=120`, press Ctrl-C after `fixture: sleeping`, then `docker ps` lists no container from `container-make-ci:local`. Record the result in the pull request.

---

## Gates for every task

```bash
make lint test                                                   # fast, no engine, one core
systemd-run --user --scope -p MemoryMax=4G -- make test-container  # Tasks 3 and later, before the PR
```

Re-derive results after each task: report the test count before and after and what accounts for the difference.
