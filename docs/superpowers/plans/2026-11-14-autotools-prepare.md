# One preparation step before make (D39) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every piece that runs `make` on the runner first runs one shared preparation step (the `prepare` key, or `./bootstrap && ./configure` for a tree with `configure.ac`), and `build/man.mk` v5 survives automake's `include`.

**Architecture:** The step is inline YAML, byte-identical in every piece that carries it, pinned by a test (the precedent is the host toolchain line and the pandoc step). `check` learns the `prepare` key. `man.mk` v5 replaces `ifeq` blocks with `$(if ...)`/`$(error ...)`.

**Tech Stack:** GitHub Actions reusable workflows, bash, jq, GNU make, autoconf/automake, pytest.

**Spec:** `docs/superpowers/specs/2026-11-14-autotools-prepare-design.md` (D39). Read it first.

## Global Constraints

- Interface stays within `v2` (D33): no new, removed or renamed input, secret or output; no wider permission.
- Toolchain line, verbatim: `          sudo apt-get install -y autoconf automake gettext podman`
- Default preparation, verbatim: `./bootstrap && ./configure`
- The custom command runs as `bash -e -c "$PREPARE"`, from the directory the piece runs `make` in. `prepare` is read from `.github/repo-infra.json` at the checkout root.
- The step runs before the first `make` of its job; a failing command fails the job.
- Prose follows the `writing-style` skill (no em dashes; `tests/test_no_em_dash.py` enforces it).
- Gates: `make check` (lint, test, test-js) green; `make test-container` after touching the selftest workflow; never more than 4 cores.
- Every change gets a `CHANGES.md` `[Unreleased]` entry for users (see Task 5).

## Review Focus

1. `.github/repo-infra.json` absent: the step must treat `prepare` as unset, not fail on `jq`. Test in Task 1.
2. `prepare` set to an empty string or a non-string: `check` reports it; the step must not run an empty command as "success". Tests in Tasks 1 and 3.
3. `directory` input set (`ri-release-distro-packages`, `ri-ci-container`): the step looks for `configure.ac` and runs the command in that directory. Test in Task 1.
4. A `prepare` command that exits non-zero halfway (`false; true`): `bash -e` must fail the step. Test in Task 1.
5. `man.mk` v5 in a plain-Makefile repository: every v4 behaviour (MAN_NAME error, missing `section:` stops only `make man`, `.DEFAULT_GOAL` kept) is unchanged. Existing tests in `tests/test_man_build.py` stay green unchanged.

---

### Task 1: The preparation step and its tests

**Files:**
- Create: `tests/test_prepare_step.py`
- Modify: `.github/workflows/ri-ci-man.yml` (insert the step before `make man`)

**Interfaces:**
- Produces: the step text, a YAML step named `Prepare the tree (D39)` with `env: DIRECTORY` (the directory `make` runs in; `.` where the piece has no `directory` input). Later tasks copy it byte for byte. Helper in the test file: `prepare_step(workflow_path) -> str` returns the step's `run:` script from a piece; `run_prepare(tmp_path, script, files: dict[str, str], directory=".") -> subprocess.CompletedProcess` runs the script with `sudo` and `apt-get` stubbed on PATH.

- [ ] **Step 1: Write the failing tests** in `tests/test_prepare_step.py`, all using `run_prepare` on the script from `ri-ci-man.yml`:
  - `test_no_configure_ac_and_no_prepare_does_nothing`: returncode 0, `apt-get` stub not called, no command run.
  - `test_configure_ac_runs_toolchain_then_bootstrap_and_configure`: fixture with executable `bootstrap` and `configure` stubs that append their name to a log; log reads `bootstrap\nconfigure\n`; `apt-get` stub got `install -y autoconf automake gettext podman`.
  - `test_prepare_key_runs_instead_of_the_default`: `.github/repo-infra.json` = `{"prepare": "echo custom > out"}`, with `configure.ac`; `out` holds `custom`, `bootstrap` stub not called, toolchain installed.
  - `test_prepare_key_runs_without_configure_ac`: same key, no `configure.ac`; `out` written, toolchain not installed.
  - `test_a_failing_prepare_fails_the_step`: `{"prepare": "false; touch reached"}`; returncode != 0, `reached` absent.
  - `test_missing_config_file_counts_as_no_prepare`: no `.github/repo-infra.json`, `configure.ac` present; default runs.
  - `test_the_step_runs_in_directory`: `directory="sub"`, `sub/configure.ac` and stubs in `sub/`; default runs there, root untouched.
  - `test_the_step_comes_before_make_man`: in `ri-ci-man.yml` the step's index is lower than the index of the step that runs `make man`.

- [ ] **Step 2: Run them, expect FAIL** (`prepare_step` finds no step)

Run: `python3 -m pytest -q tests/test_prepare_step.py`

- [ ] **Step 3: Write the step into `ri-ci-man.yml`** after checkout and before pandoc. Script order per the spec's three steps; read the key with `jq -r '.prepare // empty'` when the file exists; `cd "$DIRECTORY"` before looking for `configure.ac`. Comment above it in the house style: names D39 and the isam-alarm-collector failure (`make: *** No rule to make target 'man'` on a tree with only `Makefile.am`). Note: an empty-string `prepare` behaves as unset in the step; `check` (Task 3) reports it.

- [ ] **Step 4: Run, expect PASS**; then `make check`.

- [ ] **Step 5: Commit** `ri-ci-man prepares the tree before make man (D39)`

### Task 2: The step in every other piece that runs make

**Files:**
- Modify: `.github/workflows/ri-ci-perl-autotools.yml` (replace its toolchain, `./bootstrap`, `./configure --prefix=$HOME/test-install` steps), `ri-release-source-tarball.yml` (replace toolchain, `./bootstrap`, `./configure`), `ri-release-distro-packages.yml` (`man` job, before `make -C "$DIRECTORY" man`, `DIRECTORY: ${{ inputs.directory }}`), `ri-ci-container.yml` (before `make -C "$DIRECTORY" check`), `ri-ci-perl-mkpl.yml` (before `make thirdparty`), `ri-release-rust-binaries.yml` and `ri-release-go-binaries.yml` (before `make man`)
- Modify: `tests/test_ci_pieces.py` (`test_the_three_pieces_install_a_byte_identical_host_toolchain` now reads the toolchain line from the step, see below), `tests/test_prepare_step.py`

**Interfaces:**
- Consumes: the step text from Task 1, `prepare_step()`.

- [ ] **Step 1: Write the failing tests** in `tests/test_prepare_step.py`:
  - `test_every_piece_that_runs_make_carries_the_identical_step`: for every `ri-*.yml` whose `run:` text matches `\bmake\b` outside comments, `prepare_step()` exists and equals the one in `ri-ci-man.yml`, apart from the `DIRECTORY` env value.
  - `test_the_step_precedes_the_first_make_in_its_job`: per job, the step index is lower than the first step running `make`.
  - `test_the_autotools_pieces_no_longer_configure_by_hand`: `ri-ci-perl-autotools.yml` and `ri-release-source-tarball.yml` have no step whose `run` is `./bootstrap` or starts with `./configure`.

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Insert the step** in each listed piece. In `ri-ci-perl-autotools` and `ri-release-source-tarball` the existing D15/D18 comments move above the step. Adjust `test_the_three_pieces_install_a_byte_identical_host_toolchain` so it accepts the toolchain line inside the step (still full-line equality) in all three files; keep `tests/test_ci_pieces.py::test_the_autotools_piece_installs_only_the_fixed_host_toolchain` and `test_the_autotools_piece_runs_make_check` green.

- [ ] **Step 4: Run, expect PASS**; `make check`.

- [ ] **Step 5: Commit** `Every piece that runs make prepares the tree first (D39)`

### Task 3: check learns the prepare key

**Files:**
- Modify: `skills/repo-infra/scripts/repo_infra/check.py` (`KEYS`, add the problem item next to the `exceptions` check near line 550)
- Test: `tests/test_check.py`

- [ ] **Step 1: Failing tests:**
  - `test_a_prepare_string_is_accepted`: config with `"prepare": "cmake -B build"` gives no `config` item for `prepare`.
  - `test_an_empty_or_non_string_prepare_is_a_problem` (parametrized `""`, `"  "`, `3`, `["a"]`): one `Item("config", "prepare", "problem", ...)` whose text says `prepare must be a non-empty shell command`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Add `"prepare"` to `KEYS`; add the item.**
- [ ] **Step 4: Run, expect PASS**; `make check`.
- [ ] **Step 5: Commit** `check accepts the prepare key (D39)`

### Task 4: man.mk v5 without GNU make conditionals

**Files:**
- Modify: `skills/repo-infra/assets/pieces/man/man.mk` (marker `# repo-infra: man v5`), `skills/repo-infra/assets/pieces/man/CHANGES.md` (`## v5`)
- Modify: `.github/workflows/ri-ci-repo-infra-selftest.yml` (`repo-infra-man` job installs the toolchain line before its pytest step)
- Modify: `tests/test_ci_pieces.py` (the toolchain-line test now expects one line per job in the selftest file, two in total)
- Test: `tests/test_man_build.py`

- [ ] **Step 1: Failing tests** in `tests/test_man_build.py`:
  - `test_man_mk_has_no_make_conditionals`: no line of `man.mk` matches `^\s*(ifeq|ifneq|ifdef|ifndef|else|endif)\b`.
  - `test_automake_includes_man_mk` (marked `pandoc`; skip when `autoreconf` is missing): fixture project with `configure.ac` (`AC_INIT([fixture],[1.0])`, `AM_INIT_AUTOMAKE([foreign])`, `AC_CONFIG_FILES([Makefile])`, `AC_OUTPUT`), `Makefile.am` with `MAN_NAME = fixture`, `include $(top_srcdir)/build/man.mk` and `EXTRA_DIST = docs/manual.md build/man.mk build/man-deflist.lua`, plus `FIXTURE_MANUAL`; `autoreconf -fi && ./configure && make man` exits 0 and writes `man/fixture.1`.
  - The existing v4 tests stay unchanged and green.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Rewrite `man.mk`.** MAN_NAME check as a top-level `$(if $(strip $(MAN_NAME)),,$(error ...))` with the v4 message; the `man` target always defined, its recipe prints the v4 section message and exits 1 when `_repo_infra_man_section` is empty, else depends on the page; page rule defined unconditionally with the section variable. Header comment: Makefile.am use with `include $(top_srcdir)/build/man.mk`, top-level only, in-tree builds, `-Wno-portability` under `-Werror`.
- [ ] **Step 4: Selftest workflow** gets the toolchain line in `repo-infra-man`; update the toolchain-line test.
- [ ] **Step 5: Run** `make test` (pandoc tests run locally) and `make test-container`; then `make generations` and `make catalogue`.
- [ ] **Step 6: Commit** `man.mk v5 survives automake's include (D39)`

### Task 5: Docs, catalogue, changelog

**Files:**
- Modify: `skills/repo-infra/references/conventions.md` (new section "Preparing a tree before make": the table from the spec, the `prepare` key), `skills/repo-infra/references/onboarding.md` (Known traps: automake include of `man.mk`; the "Supplies" note), `skills/man-pages/SKILL.md` (setup step 1: Makefile.am variant, `EXTRA_DIST`, `-Wno-portability`, top-level only), piece header `# Supplies:` lines of every piece from Task 2 (mention `configure.ac` or the `prepare` key), `CHANGES.md`
- Regenerate: `make catalogue`

- [ ] **Step 1: Write the docs** in the `writing-style` voice.
- [ ] **Step 2: `CHANGES.md` `[Unreleased]`:**
  - `### New`: the `prepare` key, one entry: what it runs and where.
  - `### Fixed`: `ri-ci-man` and the man job of `ri-release-distro-packages` stopped with "No rule to make target 'man'" on a tree with `configure.ac`; they now run `./bootstrap && ./configure` first.
  - `### Fixed`: `man` v5: automake stopped on `build/man.mk` with `endif without if`; v5 can be included from `Makefile.am`.
  - `### Changed`: `ri-ci-perl-autotools` no longer passes `--prefix=$HOME/test-install` to `configure`.
- [ ] **Step 3: `make catalogue`; `make check`.**
- [ ] **Step 4: Commit** `Document the preparation step and the prepare key (D39)`

### Task 6: Proof on isam-alarm-collector, then the pull request

Work in `/home/oetiker/checkouts/isam-alarm-collector` on branch `repo-infra/apply` (not pushed yet; see the handoff for the order of administration steps, each confirmed with the owner).

- [ ] **Step 1: Push `feat/autotools-prepare`** to `oposs/repo-infra` (ask the owner first).
- [ ] **Step 2:** In isam-alarm-collector point `ri-ci-man`, `ri-ci-perl-autotools` and `ri-release-source-tarball` at `@feat/autotools-prepare`; install `man.mk` v5 with `PYTHONPATH=/scratch/oetiker/claude-worktrees/repo-infra-autotools-prepare/skills/repo-infra/scripts python3 -m repo_infra apply --item man`; change `-include $(top_srcdir)/build/man.mk` back to `include $(top_srcdir)/build/man.mk`.
- [ ] **Step 3:** After the owner renamed `master` to `main` and the `no-changelog` label exists: push `repo-infra/apply`, open the onboarding PR with `--label no-changelog`. Expected: `ci-passed` green with jobs `perl`, `man`, `local`, `release-pr-current`.
- [ ] **Step 4:** Open the repo-infra PR (`--label` per that repo's rules), body names the proof run URL.
- [ ] **Step 5:** After the repo-infra release, point isam-alarm-collector back at `@v2` and reinstall `man` from the published plugin.
