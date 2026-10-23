# A container driver for projects without autotools (#94)

Extends: D16 (the containerization threshold), D17 (repo-infra owns the shape
of the build environment), D18 (the autotools container driver).

## Intent

D16 sends a project that needs a system package beyond the runner image into a
container. D17 says repo-infra ships the machinery for that, so the estate does
not grow one container script per repository. D18 shipped that machinery for
autotools only: `container` (`build/container.mk`) and `container-m4` assume
`configure.ac`, `./bootstrap && ./configure --disable-container` and
`make dist`.

A Cargo, Go, Node or plain-Makefile project that crosses the threshold has no
piece today. fat32expander (oetiker/fat32expander#4) is the first case: its
heavy tests need `dosfstools`, `mtools`, `musl-tools`, `qemu-system-x86`,
`cpio`, `curl` and `/dev/kvm`. It solved this on its own with a
`Containerfile`, `scripts/ci-container.sh` (about 80 lines of engine, user and
KVM handling), Makefile targets `ci-heavy` and `ci-container`, and a
`ci-local.yml` job. That script is exactly the per-repository machinery D17
forbids. This design turns it into two pieces.

Two needs send a project's tests into a container (owner's statement):

- **Tools a developer does not have.** `mkfs.fat`, `dosfsck`, `mtools`,
  `cpio`, `qemu-system-x86` are not on a normal developer machine and would
  need `apt install` there. In the image they are one line of the
  `Containerfile`.
- **Root.** Tests that need root run as root in the container. This is root
  as a user (owning files, `chown`, permission checks that skip as non-root),
  which rootless podman and docker both give without `--privileged`. A test
  that needs root in the kernel (block devices, `mount`) runs inside a QEMU
  guest started from the container, as fat32expander does: its scripts boot an
  Alpine guest and grow the filesystem there. `/dev/kvm` makes that guest fast;
  without it QEMU falls back to TCG and the tests still run.

## What the developer sees

The developer types `make check`. Nothing else.

- On the host, `make check` builds the image from the project's `Containerfile`
  and runs `make check` inside it, with the checkout mounted at `/src`.
- Inside the container, `make check` runs the project's own `check` target.
- CI runs the same `make check`, so a local run and a CI run are the same
  commands with the same result.

## Goals

- One `make check` that works on a developer machine (podman or docker) and on a
  GitHub runner.
- The fragment decides by itself whether it runs inside the container. No
  switch has to be passed for the normal case.
- `/dev/kvm` and other devices reach the container when the host has them.
- The tests run as root in the container, under both engines.
- Files the tests write into the mounted checkout belong to the calling user
  afterwards.
- No `--privileged`. Kernel root is reached through a QEMU guest.
- A second local `make check` downloads nothing again, and host and container
  builds do not rebuild over each other.
- A second Containerfile contract, without the autotools points.

## Non-goals

- `ri-ci-rust` (and the other native CI pieces) stay native and unchanged. They
  keep running fmt, clippy and the plain tests on the runner. The container
  piece runs only what needs the image. Owner's decision.
- No image caching and no registry. The image is rebuilt on every CI run (about
  two minutes for fat32expander). The workflow piece needs only
  `contents: read`. Caching can come later as its own change.
- No way to declare system packages anywhere but the project's own
  `Containerfile` (D16).
- No `dist`, `install` or release targets. This driver is for tests. A project
  of this kind builds its release artifacts with its ecosystem's release pieces
  (`ri-release-rust-binaries` and so on).
- No `test-dev` single-file loop like the autotools driver has. The tree is
  mounted, so an edit is visible at once. To narrow a run, the project's
  `check` reads a variable of its own (`make check TEST=foo`, see "The test
  target is `check`").

## Anti-goals

- A developer must never have to know about podman, docker or `/dev/kvm` to run
  the tests.
- The fragment must never run the tests natively on a host that lacks the
  packages and report a confusing failure. If it cannot start a container, it
  says so and names the escape.

## Decisions taken with the owner

### Detecting the container

The owner asked that `make` detect by itself whether it runs inside the
container, with an environment variable as the escape. Proposed first: the
engines' marker files (`/run/.containerenv`, `/.dockerenv`) plus a TTY test.
The builder check found the gap in that: a container-based CI runner (a Gitea
act_runner runs every job in docker and leaves `/.dockerenv`) has a marker and
no TTY, so the tests would run there natively, without the packages.

Decided: "inside" means that the driver started this run, and nothing
else.

- The driver starts the container with `REPO_INFRA_USE_CONTAINER=no` in its
  environment. In there, `make check` runs the project's own target.
- Everywhere else, a developer machine, a toolbox, a devcontainer, a GitHub
  runner or a container-based runner, counts as the host: `make check` builds
  the image and runs the tests in it.
- The same variable is the manual escape: `REPO_INFRA_USE_CONTAINER=no` runs the
  tests here, natively. `REPO_INFRA_USE_CONTAINER=yes` (or unset) goes
  through the image. Any other value is an error naming the two. The name is not
  `REPO_INFRA_CONTAINER`: that is the m4 macro of `container-m4`, and m4
  would expand it inside a `configure.ac` that mentions the variable.
- If the host path needs a container engine and none is found (a toolbox
  without podman, a shell opened by hand in the project image), the fragment
  fails with a message that names `REPO_INFRA_USE_CONTAINER=no`. The lookup
  and that error run inside the recipes of `check` and `container-clean`
  only, never while make reads the `Makefile`, so every other target works
  on a host without an engine (a Mac, a toolbox). The fake-engine test runs
  `make all` with no engine on `PATH`.

### The test target is `check`

The owner's point: whatever the project's test command is, it must run in the
defined environment, so it never fails on a missing tool and never asks for
one to be installed. No new target name is introduced for that.

The test target is `check`, as the GNU coding standards name it. That is a
standard-wide rule, decided here: a Makefile that a project writes, or that
autotools generates, runs its tests with `make check`. A Perl `Makefile.PL`
project keeps `make test`, because ExtUtils::MakeMaker generates `test` and
never `check`. Moving the autotools side (`ri-ci-perl-autotools`,
`container` v4) is #100, not part of this change.

The fragment works like the autotools driver: outside the container it
forwards `check` into it; inside, it defines nothing, and the project's own
`check` runs. The project guards its own target with the variable the
fragment sets:

    include build/container-make.mk

    ifeq ($(CONTAINER_DRIVER),no)
    check: fmt-check lint test-unit
    endif

- Host: `make check` builds the image and runs `make check` in it, with
  `REPO_INFRA_USE_CONTAINER=no` set. The inner `make` gets the variable
  assignments of the outer command line (`$(MAKEOVERRIDES)`), so
  `make check TEST=foo` reaches the project's `check`. `-j` and the
  jobserver are not passed on: its file descriptors do not cross into the
  container. A project that wants parallel jobs sets them in its own `check`.
- `REPO_INFRA_USE_CONTAINER=no` (in the container, or by hand on the host):
  `CONTAINER_DRIVER` is `no`, the fragment defines nothing, and the
  project's `check` runs.
- What `check` covers is the project's own decision, as it is today. Other
  targets of the project (`fmt-check`, `lint`, `test-unit`) are not forwarded
  and run where they are called.

### Engine, user and devices

This takes over what fat32expander's script learned:

- Engine: `CONTAINER_ENGINE` picks `podman` or `docker`; unset, podman wins
  when both exist.
- User: the tests run as root in the container under both engines. Under
  rootless podman that root is the calling user on the host. Under rootful
  docker it is real root, so files the tests create in the checkout would
  belong to root. The run therefore starts and ends, whatever the tests' exit
  status, with
  `find /src ! -user <owner> -exec chown -h <owner>:<group> {} +` (and the
  same over the git common dir when it is mounted, see "The image"; `-h`: a
  symlink a test made gets its own owner fixed, and its target is left
  alone), where owner
  and group are what `/src` shows inside the container: the developer's uid
  under rootful docker, root (that is, the developer) under rootless podman,
  where it changes nothing. Only files with the wrong owner are touched, so a
  large `target/` costs a scan, not a rewrite. The pass at the start repairs
  what an interrupted run (Ctrl-C, SIGKILL, OOM kill) left behind. One rule,
  no engine detection. The tests' exit status is kept.
  A file the pass cannot change does not stop the run and does not change
  the exit status. Under rootless podman a file of another host user, or of
  host root after a `sudo make install` in the tree, shows as `nobody`, and
  `chown` fails with "Operation not permitted". The wrapper prints one notice
  with the number of such files and the first few paths, to be fixed on the
  host.
- Signals: the run always gets `--init`, so a small init is PID 1 and passes
  SIGINT and SIGTERM on. Without it the wrapper shell is PID 1, which ignores
  both, and Ctrl-C in a run without a TTY stops nothing. When stdin is a
  terminal, `-i -t` are added together: the terminal goes raw and Ctrl-C
  reaches the container's foreground processes. `-t` alone would not do:
  docker proxies signals in non-TTY mode only, so Ctrl-C would stop the
  client and leave the container running beside the next `make check`. The
  plan confirms this on docker. Without a terminal (CI, scripts) neither flag
  is set and `--init` with the signal proxy does the work. An interrupted run
  skips its closing chown pass; the opening pass of the next run repairs that.
  The init (catatonit under podman, docker-init under docker) signals only
  its direct child, the wrapper. A wrapper shell that is bash waits for
  `make` and passes nothing on, so the wrapper sets a `trap` that sends the
  signal to its whole process group (`kill -s INT 0`); that works with any
  shell and either init. On Ubuntu, podman only recommends catatonit; when
  `--init` fails for want of an init binary, the driver says so and names
  the package.
- git: under rootful docker, root in the container runs git on a `/src`
  that belongs to the runner user, and git (2.35.2 and later) refuses with
  "detected dubious ownership in repository at '/src'". Before it runs make,
  the wrapper therefore appends `[safe]` `directory = *` to `/etc/gitconfig`.
  That file lives in the container's own layer and goes with `--rm`; the
  host is not touched. git, libgit2 (the `git2` crate behind many `build.rs`
  version stamps) and gix all read the system config, and a test that sets
  its own `GIT_CONFIG_COUNT` cannot displace it, which environment pairs
  could not promise. `*` rather than `/src`, because in a worktree git also
  checks the git dir in the common dir mount; the container sees nothing but
  the developer's own checkout. Under rootless podman `/src` belongs to root
  in the container and this changes nothing.
- SELinux: the run always gets `--security-opt label=disable`. On an
  enforcing host (Fedora, RHEL) a bind mount without a label option gives
  "Permission denied" on every file in `/src`. Relabelling with `:z` would
  change the checkout's labels on the host for good; `label=disable` lifts
  the confinement for this one container and leaves the host as it is. On a
  host without SELinux it does nothing.
- `--userns=keep-id` is not used: podman 4.9.3 with `fuse-overlayfs` as
  `mount_program` refuses it with "make .../merged private: Permission
  denied". Root in the container does not need it.
- Devices: the project lists them in `CONTAINER_DEVICES` (for example
  `/dev/kvm`). Each device that exists on the host is passed in with
  `--device`; one that does not exist is skipped with a notice, so a laptop
  without KVM still runs the suite. The driver prints the mode and group of
  each device it passes in, so a device the container cannot open is visible
  before QEMU quietly falls back to TCG.
  - Under rootful docker, root in the container is real root and opens a
    device such as `/dev/kvm` (`crw-rw---- root kvm`) without any group.
  - Under rootless podman, root in the container is the calling user, and
    podman drops that user's supplementary groups. When at least one device
    is passed in, the driver therefore adds `--group-add keep-groups`, so a
    user in `kvm` keeps access (fat32expander's script does the same). A
    device the user cannot open on the host stays closed in the container.
    `keep-groups` needs the `crun` runtime and does not work with podman
    remote (podman machine on macOS and Windows); there the driver leaves
    it out and prints a notice.
- `CONTAINER_OPTS` adds options to the run (for example
  `--cpus=4 --memory=6g` on a shared machine). It must not hold
  `--group-add`, which podman refuses next to `keep-groups`.
  `CARGO_BUILD_JOBS` and
  `RUST_TEST_THREADS` pass through when set.

### The image

- Built from the project's `Containerfile` with no build context
  (`<engine> build -t <tag> - < Containerfile`). The image holds tools only;
  it copies nothing from the tree.
- The build checks the registry for a newer base image, so a floating tag
  such as `rust:1-trixie` does not freeze on a developer machine while CI
  moves on: podman with `--pull=newer`, docker with `--pull` (its layer
  cache keeps an unchanged base from being downloaded again). How each
  behaves offline is for the plan to verify; an offline build must still
  run on the local copy.
- The tag defaults to the directory name of the checkout's top level (see
  the mount below) plus `-ci:local`; the
  project may set `CONTAINER_TAG` before the include. The name is lowercased
  and every character outside `[a-z0-9._-]` becomes `-`; runs of separators
  become one, separators at the start and end are dropped, and an empty
  result becomes `project`. Both engines refuse uppercase in a tag
  ("repository name must be lowercase"). Two
  projects checked out under the same directory name share the tag and the
  cache volume; `CONTAINER_TAG` separates them.
- The checkout's top level is mounted read-write at `/src`: the output of
  `git rev-parse --show-toplevel`, or make's current directory outside git.
  The run starts with `-w /src/<path>`, where `<path>` is make's current
  directory relative to the top level (empty at the top). So a project in a
  subdirectory (`make -C sub check`, the `directory` input) still sees the
  whole repository: a symlinked fragment, a Cargo workspace or a `path =`
  dependency above it, and the git repository itself. The `Containerfile`
  is the one in make's current directory, the project's own.
- In a git worktree, `.git` is a file that points into the main checkout's
  `.git/worktrees/<name>`. The driver therefore also mounts
  `git rev-parse --path-format=absolute --git-common-dir` read-write at the
  same absolute path when it lies outside the top level, so git works in the
  container. The chown pass covers this mount too, or a `git status` under
  rootful docker would leave root-owned files in the main checkout's `.git`.
- A named volume `<project>-ci-home` is mounted at the container's `HOME`,
  `/root`. `<project>` is the main checkout's directory name (the parent of
  the git common dir), cleaned as the tag is; with `CONTAINER_TAG` set, the
  tag with `:` and `/` replaced by `-`. So all worktrees of one project share
  one warm cache, while the image tag stays per worktree, because a branch
  may change its `Containerfile`. Cargo and Go lock their caches, so runs in
  two worktrees at once are safe. The `Containerfile` puts every
  download cache under `/root` (contract point 6), so one mount serves every
  ecosystem and the driver needs no knowledge of which one it runs. The engine
  creates the volume on first use and copies the image's `/root` into it
  once; later changes to `/root` in the image stay hidden until
  `container-clean`, which is why the image installs nothing there. On a CI
  runner it is new on every run, so CI behaves as without it; this is not
  the image cache the non-goals rule out.
- `make container-clean` removes the volume, for a cold run. It is defined on
  the host only.

## The pieces

### `container-make`: the build file

`build/container-make.mk`, a GNU Make fragment the project includes from its
`Makefile`:

    include build/container-make.mk

    ifeq ($(CONTAINER_DRIVER),no)
    check:
    	cargo test -- --ignored
    	./tests/qemu-suite.sh
    endif

It carries the standard marker header (Purpose, Choose, Supplies) and is
drift-checked like `container`. It must work with GNU Make only; the project's
`Makefile` is GNU Make already.

Including it never changes what a bare `make` builds. Like `man.mk`, it saves
`.DEFAULT_GOAL` before its own targets and restores it after them, so the
include may come first and the project's first target stays the default. The
fake-engine test checks this.

It is the alternative to `container` + `container-m4`, never in addition to
them. `check` reports a repository that installs both kinds.

The two new pieces go together, and `check` reports either one alone.
`ri-ci-container` carries `Pieces: container-make`, so the existing
dependency report covers a call without the fragment, which would run
`make check` on the runner without the image. A `container-make` that no
caller job runs through `ri-ci-container` is reported too, because CI would
never run its suite. Whether `Pieces: ri-ci-container` on the fragment
already yields that report, or `check` needs a rule of its own, is for the
plan to find out.

The project's own `check:` must sit inside `ifeq ($(CONTAINER_DRIVER),no)`.
Unguarded, GNU Make keeps the later recipe: with the include first, the
project's recipe wins on the host and the tests run there without the image,
which the anti-goals forbid, and the only sign is the warning "overriding
recipe". `check` therefore reports a `check:` rule outside that block in a
`Makefile` that includes `container-make.mk`, by a plain text scan of the
`Makefile`. `container-make` is for a hand-written `Makefile`. A Perl
project's `Makefile` is generated by `Makefile.PL`, and `ri-ci-perl-mkpl` and
`ri-ci-perl-autotools` run their tests on the runner, so `check` reports
`container-make` together with either of them.

### `ri-ci-container`: the workflow piece

A called workflow (`oposs/repo-infra/.github/workflows/ri-ci-container.yml@v2`),
like `ri-ci-man`:

- Inputs: `ref` (the commit to test) and `repository` (the repository to
  check out, default the caller's), as every `ri-ci-*` piece has (D33).
  Optional `directory` (default `.`): the directory that holds the
  `Makefile`, for a repository whose project sits below the top level, and
  for repo-infra's own fixture.
- Steps: checkout `ref`, then `make -C <directory> check` with
  `CONTAINER_ENGINE=docker`.
  Docker on the runner, because the runner user is not in the `kvm` group,
  and under docker the container's root is real root, which opens
  `/dev/kvm` without the group. No udev rule and no `chmod` are needed;
  fat32expander's run is the reference.
- Permissions: `contents: read`.
- `timeout-minutes: 60`, changeable through the optional input
  `timeout-minutes`, so a hung QEMU guest does not hold a runner for
  GitHub's default of six hours.

The caller adds it in `ci.yml` beside its native CI pieces and lists it in the
`needs:` of `ci-passed`.

An autotools project has no such second piece: its ecosystem piece runs
`make check`, and that is the container job. Here the native pieces stay
native (see "Non-goals"), so the container job needs a piece of its own.
After #100 both sides run the same `make check`; they differ only in which
workflow calls it.

## The Containerfile contract, second variant

`conventions.md` gets a second contract under the D18 one, for `container-make`:

1. Hold the tools only. No `COPY` of the tree; the checkout is mounted at
   `/src` at run time.
2. Carry `make` and everything the project's `check` needs, including the
   ecosystem toolchain (for example `FROM rust:1-trixie`). The driver
   itself needs `sh`, `find`, `stat` and `chown`; every common base image
   and busybox have them.
3. Do not set `USER`. The tests run as root, and the driver hands the
   checkout back to its owner.
4. Install the tools the runner image had that the tests used without saying
   so. fat32expander met this with `cpio`: the move into a minimal image
   surfaces hidden dependencies, and the fix belongs in the `Containerfile`.
5. Keep the container's build output apart from the host's when both use the
   same directory in the tree. For Rust:
   `ENV CARGO_TARGET_DIR=/src/target/container`.
   Otherwise the container's `rustc` and the host's overwrite each other's
   artifacts in `/src/target` and each build starts from scratch.
   With the default target directory, `cargo clean` on the host removes it
   too.
6. Keep the ecosystem's download caches under `/root`, and install nothing
   into `/root`. The official images move them elsewhere: `rust` sets
   `CARGO_HOME=/usr/local/cargo`, `golang` sets `GOPATH=/go`. So after the
   toolchain setup a Rust `Containerfile` sets `ENV CARGO_HOME=/root/.cargo`,
   a Go one `ENV GOPATH=/root/go`. The tools stay where the base image put
   them and are found through `PATH`.
7. Install a pinned toolchain in the image. A Rust project with a
   `rust-toolchain.toml` names the same version in the `Containerfile`
   (`RUN rustup toolchain install <version>`); otherwise rustup downloads it
   into `/usr/local/rustup`, outside the cache volume, on every run. How
   `check` compares the two versions is for the plan.

The autotools points (bootstrap, `--disable-container`, `EXTRA_DIST`, GNU tar)
do not apply to this variant.

## Documentation

- `teaching-the-standard.md`, "The threshold you will hit most often": name
  both answers, autotools (`container` + `container-m4`) and everything else
  (`container-make` + `ri-ci-container`).
- `conventions.md`: the second contract and the detection rules.
- The catalogue, regenerated.
- `CHANGES.md`: one entry under `### New`, ending `(#94)`.

## Migration of fat32expander

Not part of this change, but the design must make it possible:
`scripts/ci-container.sh`, the `ci-heavy` and `ci-container` targets and the
`heavy` job of `ci-local.yml` go away. `ci-heavy` moves into its guarded
`check`, the `Containerfile` stays, and `ci.yml` calls `ri-ci-container`. The
macOS job stays in `ci-local.yml`. The container `check` holds only the root
and QEMU suite; the plain tests stay in the native `ri-ci-rust`, because they
skip themselves when run as root and would pass there without running.

## Further decisions

- No `test-dev` target: the tree is mounted, so an edit is visible at once.
- "Inside" is the variable the driver sets, not marker files and a TTY (see
  "Detecting the container").
- `check` reports `container-make` together with `container`/`container-m4`
  or with `ri-ci-perl-*`.
- No Dependabot `docker` entry for the `Containerfile`: the image is rebuilt
  on every run from a floating tag such as `rust:1-trixie`.
- Proof: repo-infra gets a small fixture project (a `Containerfile`, a
  `Makefile` with the include, a `check` that writes a file, checks it runs as
  root and touches `/dev/kvm` when present) under
  `tests/fixtures/container-make/`, and its own CI calls the real
  `ri-ci-container` on it with `directory: tests/fixtures/container-make`,
  next to the existing container self-test. A fake-engine test covers the
  Make logic in the fast suite.
- Moving fat32expander onto the pieces is a separate step after the release.

## Left to the builder

- The exact Make code of the detection and the error texts, within the rules
  above.
- How tests run the fragment (a fake engine on `PATH` that records its
  arguments, as other piece tests fake `gh` and `cargo`, is the expected
  pattern).
- The test of the workflow piece, following the existing `ri-ci-*` piece tests.
- The `/dev/kvm` handling on the hosted runner, proven on a real run.
