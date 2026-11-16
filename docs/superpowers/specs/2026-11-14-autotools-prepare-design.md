# Preparing an autotools tree before make (D39)

Decision: D39 (one preparation step for every piece that runs `make` on the
runner, with autotools as its first user; keeps
D15's `make check` seam, D18's container driver and D23's man page build)

## Intent

A repository with `configure.ac` has no `Makefile` until `./bootstrap` and
`./configure` have run. Each piece finds this out on its own today:

- `ri-ci-perl-autotools` and `ri-release-source-tarball` run `./bootstrap` and
  `./configure` themselves, with different arguments.
- `ri-ci-man` runs `make man` on the bare checkout. On isam-alarm-collector
  (the first native autotools repository with a manual) it fails: there is no
  `Makefile`.
- The `man` job of `ri-release-distro-packages` runs `make -C <directory> man`
  on the runner the same way, although the piece says it supports autotools
  ("autotools only when configure.ac exists"). SmokePing, the project D38
  names, has `configure.ac`.

The owner wants the standard to know this once, as a general concept, and not
per piece.

The include side has the same root. `build/man.mk` v4 uses GNU make
`ifeq`/`else`/`endif`. automake reads `include` in `Makefile.am` itself and
stops: `build/man.mk:40: error: endif without if`. isam-alarm-collector works
around it with `-include`, which hides the targets from automake.

## Goals

- One rule: a piece that runs `make` on the runner prepares the tree first.
  The project names its preparation in the `prepare` key; a tree with
  `configure.ac` and no `prepare` key gets the autotools preparation.
- The same preparation in every such piece, pinned identical by a test, as the
  host toolchain line and the pandoc step are today.
- A project whose tree needs a preparation, autotools or any other (CMake,
  Meson, a generated Makefile), names it once, in `.github/repo-infra.json`.
- `build/man.mk` works when automake includes it with a plain `include`.

## Non-goals

- No special path that builds the man page without the project's `Makefile`.
  Considered and dropped (see Approaches).
- No change for repositories without `configure.ac` and without `prepare`: the
  step does nothing there.
- The container legs of `ri-release-distro-packages` are not changed: they run
  `make` inside their image, where the Containerfile prepares the tree.

## Anti-goals

- A new required input, a removed input or a wider permission. The change
  stays within `v2` (D33): CI refuses an interface change.
- A piece that silently skips its `make` when preparation fails. A failed
  preparation fails the job and names the command.

## Constraints

- `./configure` of a native project checks the project's dependencies on the
  runner. A man job then fails when the runner lacks a library the man page
  does not need. Accepted: the project's main CI job (`ri-ci-perl-autotools`)
  runs the same `configure` and must pass anyway, and the `prepare` key is the
  way out for a project that needs something else.
- In driver mode (D18) `configure` checks no project dependency, so the step
  is cheap there.
- pandoc is installed by the pieces that build man pages; `configure` must not
  need it.

## Approaches

1. **General rule (picked).** Every piece that runs `make` on the runner runs
   one shared preparation step first when `configure.ac` exists. Cost: the man
   job inherits `configure`'s dependency checks.
2. **Man build without preparation.** `make -f build/man.mk man` without the
   project's `Makefile`. Dropped by the owner: it is a second way to build, it
   needs `MAN_NAME` from a second place (front matter or a piece input), and it
   hides a `configure` that fails on the runner, which the main CI job hits
   anyway.
3. **Both.** Dropped with 2.

## The design

### The rule

A piece that runs `make` on the runner runs the preparation step before its
first `make`, in the directory it runs `make` in (the checkout root, or
`directory` for `ri-release-distro-packages` and `ri-ci-container`). The step
decides what to run:

| `prepare` key | `configure.ac` | The step runs |
|---|---|---|
| set | either | the toolchain line if `configure.ac` exists, then `prepare` |
| absent | present | the toolchain line, then `./bootstrap && ./configure` |
| absent | absent | nothing |

Autotools is the first user of `prepare`: its default is the second row.
(Builder's call: a project with `configure.ac` and its own `prepare` still
gets the autotools toolchain, so its command can call `./bootstrap`.)

### The step

One step, the same text in every piece that carries it, pinned by a test with
full-line equality like `test_the_three_pieces_install_a_byte_identical_host_toolchain`:

1. Read `prepare` from `.github/repo-infra.json` at the checkout root with
   `jq` (on the runner image).
2. When `configure.ac` exists, install the fixed host toolchain, the existing
   line `sudo apt-get install -y autoconf automake gettext podman`.
3. Run `prepare` with `bash -e -c` when set; otherwise
   `./bootstrap && ./configure` when `configure.ac` exists; otherwise nothing.

`ri-ci-perl-autotools` and `ri-release-source-tarball` replace their own
toolchain, `./bootstrap` and `./configure` steps with this step. The
`--prefix=$HOME/test-install` of `ri-ci-perl-autotools` goes: the piece never
runs `make install`.

Pieces that carry the step: every piece that runs `make` on the runner, so
the test needs no exemption list (builder's call). Today that is
`ri-ci-perl-autotools`, `ri-release-source-tarball`, `ri-ci-man`, the `man`
job of `ri-release-distro-packages`, the man steps of `ri-release-rust-binaries`
and `ri-release-go-binaries`, `ri-ci-container` and `ri-ci-perl-mkpl`. In the
last four the step does nothing today unless the project sets `prepare`.

### The `prepare` key

`.github/repo-infra.json` may set `"prepare": "<shell command>"`, run from the
directory the piece runs `make` in. `check` accepts the key and reports a
value that is not a non-empty string. The key is general: it works without
`configure.ac`. The catalogue's "Supplies" line of each
piece with the step names `configure.ac` and the key.

### build/man.mk v5

v5 has no GNU make conditional: `MAN_NAME` and the section are checked with
`$(if ...)` and `$(error ...)` in expressions and recipes, so automake's
`include` copies the file without parsing errors and `make man` behaves as v4:

- `MAN_NAME` unset stops make with the v4 message.
- A manual without a usable `section:` stops `make man` and nothing else,
  with the v4 message.
- `.DEFAULT_GOAL` is saved and restored as in v4.

Scope (builder's calls):

- v5 works with a plain `include` under any automake strictness without
  `-Werror`. `:=`, `$(shell)` and `$(if)` are GNU make features that
  `-Wportability` warns about; a project with `-Werror` adds
  `-Wno-portability`, and the `man-pages` skill says so.
- v5 keeps the v4 paths. It is included from the top-level `Makefile.am` and
  built in-tree; VPATH builds and subdirectory includes are not supported, and
  the skill says so. A plain-Makefile repository sees no difference.

The `man-pages` skill and the comment in `man.mk` say that an autotools
project includes it from `Makefile.am` with
`include $(top_srcdir)/build/man.mk` and lists `build/man.mk` and
`build/man-deflist.lua` in `EXTRA_DIST`.

### Docs

- This document as D39.
- `references/conventions.md`: a section "Preparing an autotools tree" with the
  rule and the `prepare` key.
- `references/onboarding.md`, Known traps: the automake include.
- `CHANGES.md` `[Unreleased]`: one entry per visible effect.
- `make catalogue`, `make generations`.

### Tests

- The step is byte-identical in every listed piece, and every piece that runs
  `make` on the runner carries it before its first `make`.
- The step script, run against fixtures: no `configure.ac` does nothing;
  `configure.ac` without `prepare` runs `./bootstrap && ./configure`; with
  `prepare` runs that command; a failing command fails the step.
- `man.mk` v5: the v4 tests still pass; a fixture automake project with
  `include $(top_srcdir)/build/man.mk` survives `autoreconf` and `make man`
  produces the page. It is marked `pandoc`, and the self-test job that runs
  the `pandoc` tests also installs the autotools toolchain (builder's call).
- `check`: `prepare` accepted as a non-empty string, refused otherwise.

### Proof

isam-alarm-collector's onboarding branch points `ri-ci-man`,
`ri-ci-perl-autotools` and `ri-release-source-tarball` at
`@feat/autotools-prepare`, installs `man.mk` v5 from the branch's scripts and
goes back to a plain `include`. Green CI there proves the rule; then the
pointers return to `@v2` after the release.

## Left to the builder

- The exact shell of the step and of the `$(if ...)` rewrite.
- Whether the step test runs the script extracted from the YAML or a copy.
- The wording of the docs, in the `writing-style` voice.
