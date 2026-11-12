# Linux packages built per distribution

Date: 2026-11-12
Status: design, not built
Decision: D38 (a release piece that builds, tests and packages a program once
per distribution, inside that distribution; closes #148 and #149, prepares
#150)

## Why

The standard Linux build is a static binary: musl for Rust (D32), no cgo for Go
(D35). `ri-release-nfpm` packs that one binary into one `.deb` and one `.rpm`
that run on every distribution. A program that links system libraries cannot
take that path:

- lectover (oetiker/lectover, onboarded in oetiker/lectover#1) has a Vulkan
  backend. It loads the system's GPU driver through `libvulkan.so.1`, which a
  static musl binary cannot do, and its build needs the Vulkan headers,
  `glslc` and SPIRV-Headers. It builds glibc archives in its own
  `release-build-local.yml` inside `pkg/linux/Containerfile` (ubuntu:24.04),
  and `ri-release-nfpm` refuses them (#149).
- wg-wrangler (oposs/wg-wrangler) compiles Perl XS modules. An XS module is
  tied to the Perl version of the distribution it was built on. It builds one
  `.deb` per distribution with `dpkg-buildpackage` in its own
  `release-build-local.yml`, five images, version
  `<version>~<codename>`, and sends each file to its own apt distribution
  through `ri-publish-gitea`.

One build in one image works only for a program that links glibc and nothing
else; it fixes the oldest glibc the package runs on, and an XS module or a
library soname that differs between releases breaks it (owner, 2026-11-12). So
the general shape is one build per distribution. Two repositories already
carry their own copy of it, which is the per-repository machinery D17 forbids.

## Decision

D38: a program that links system libraries is built, tested and packaged once
per distribution release, inside an image of that release, by the new piece
`ri-release-distro-packages`. A static program keeps the current path
(`ri-release-rust-binaries` or `ri-release-go-binaries`, then
`ri-release-nfpm`).

The split follows D17. repo-infra owns the shape: the list of releases, the
matrix, the container run, dependency detection, packing with nfpm, version
and file names, the read-back and the install test. The project owns the
content: which packages its build image needs, how `make` builds and installs
it, and its `nfpm.yaml`.

## The standard list

The piece carries one list of releases. A caller builds all of them unless it
narrows the list (see "Narrowing the list"). The owner chose the list on
2026-11-12.

| Family | Releases | Package |
|---|---|---|
| deb | Debian 12, Debian 13, Ubuntu 22.04, Ubuntu 24.04, Ubuntu 26.04 | `.deb` |
| rpm | AlmaLinux 9, AlmaLinux 10, the newest released Fedora | `.rpm` |
| apk | the two newest stable Alpine releases | `.apk` |

Every release is built for amd64 on `ubuntu-24.04` and for arm64 on
`ubuntu-24.04-arm`, natively, with no cross compile: 20 legs.

Keeping the list current is repo-infra's work: when Fedora or Alpine releases,
or a release reaches its end of life, the list changes in one commit and one
repo-infra release, and every caller picks it up through `@v2`. Adding a
release to the list is not an interface change.

## What the project supplies

### The Containerfile

The project's `Containerfile` at the top level is the build image for every
release. It is the second contract of `conventions.md` (tools only, no `COPY`
of the tree, the checkout mounted at `/src`, no `USER`), so one file serves
`container-make` and this piece. Two points are added:

1. The base image is an argument with a default, and the stage that holds the
   tools is named `build-deps`:

   ```dockerfile
   ARG BASE=docker.io/library/debian:13
   FROM ${BASE} AS build-deps
   ```

   `container-make` builds it with the default. This piece builds it with
   `--build-arg BASE=<image of the release> --target build-deps`.

2. One `RUN` installs the build dependencies of every family. It reads `ID`
   and `ID_LIKE` from `/etc/os-release` and runs `apt-get`, `dnf` or `apk` with
   that family's package names. The image is built with no build context
   (`container-make` does the same), so the list lives in the `Containerfile`
   itself and not in a script beside it.

A D18 project (autotools, `COPY` of the tree and a build in the image, as
wg-wrangler has it) keeps its later stages and puts the tools in a first stage
named `build-deps`. With `--target build-deps` the later stages, and their
`COPY`, are not built.

The toolchain the build needs (rustup for lectover, node for wg-wrangler's
frontend) is the project's to install in this stage, as today.

### The build

The piece runs, inside the container with `/src` as the working directory:

1. for an autotools project (`configure.ac` exists): `./bootstrap` and
   `./configure --disable-container`. The project sets its prefix with
   `AC_PREFIX_DEFAULT` in `configure.ac`; the piece passes no options.
2. `make`
3. `make check`. A test that fails on one release fails that leg, which is the
   point: the XS module or library that behaves differently there is found
   before the release (owner, 2026-11-12).
4. `make install DESTDIR=/stage`

The project's `Makefile` decides how its program is built for a package. For
lectover that is `cargo build --release --locked --features vulkan`, so the
Vulkan feature lives in its `Makefile` and not in a piece input.

### nfpm.yaml

The same nfpm config `ri-release-nfpm` reads, with its contents taken from
`${STAGE}`, which here is the `DESTDIR` tree rather than an archive layout.
The piece sets the variables `ri-release-nfpm` sets today (`VERSION`,
`SOURCE_DATE_EPOCH`, `MTIME`, `PACKAGER`, `STAGE`, `ARCH`) and `packagers`
works as there, keyed by packager (`deb`, `rpm`, now `apk`). For a value that
differs per release, the piece also sets `RELEASE` (its own name, for example
`debian-12`), `ID` and `VERSION_ID` from `/etc/os-release`, and `CODENAME`
(empty where the release has none); the config uses them through `${...}`
like the others. A release a program cannot serve at all, for example Alpine
for a program that needs systemd, is left out by narrowing the list. The config lists no dependency on a shared library: the piece
finds those (next section). Dependencies the piece cannot see, such as a
program the package runs, stay in the config.

## Dependencies found by the piece

The project declares no shared-library dependencies (owner, 2026-11-12). After
`make install`, the piece runs a detector in the same build image, on every
ELF file under `/stage`:

- deb: `dpkg-shlibdeps`, which writes `Depends` with the versions of that
  release, for example `libc6 (>= 2.36), libvulkan1 (>= 1.3.239)`.
- rpm: `/usr/lib/rpm/rpmdeps --requires`, from `rpm-build`.
- apk: the needed sonames from `scanelf --needed` (`pax-utils`), written as
  `so:<soname>` dependencies, which apk resolves against the repository index.
- Perl: when `/stage` holds a shared object under a Perl library path, the
  piece adds the Perl API of the image: `perlapi-<version>` on deb, as
  `dh_perl` does in wg-wrangler's build today, and the equivalent on rpm and
  apk.

The piece installs the detector's package in the build container itself
(`dpkg-dev`, `rpm-build`, `pax-utils`), so the project's `Containerfile` does
not list it. It merges the result into the expanded nfpm config as the
`depends` of each packager, after the entries the project wrote.

## Versions and file names

| Family | Version in the package | Example file |
|---|---|---|
| deb | `<version>~<codename>` | `wg-wrangler_1.4.0~trixie_amd64.deb` |
| rpm | release field `1.<dist>`: `el9`, `el10`, `fc<N>` | `lectover-0.2.0-1.el10.x86_64.rpm` |
| apk | `<version>-r0`, the release in the file name | `lectover-0.2.0-r0.alpine3.23.x86_64.apk` (builder settles the form) |

A file name carries the release, so the 20 files differ in name. GitHub's
renaming of `~` (#129) is handled by `lib/assets.js` and `lib/gitea.js`
already.

The artifacts are `release-asset-packages-<release>-<arch>`, for example
`release-asset-packages-debian-13-arm64`. The caller lists
`release_assets` by glob per family.

## Proof in every leg

1. Read the package back, as `ri-release-nfpm` does: name, version, and for a
   package with an ELF file, a non-empty dependency list.
2. Install it in a clean container of the same release, built from the base
   image alone, without the build dependencies: `apt-get install ./x.deb`,
   `dnf install ./x.rpm`, `apk add --allow-untrusted ./x.apk`. This proves the
   detected dependencies resolve on that release.

On AlmaLinux, many libraries and Perl modules are only in EPEL and CRB. The
piece turns on both in the build image and in the install-test image, before
the project's `RUN` (owner, 2026-11-12). The rpm install snippet for AlmaLinux
tells users to turn them on too (`dnf install epel-release` and
`dnf config-manager --set-enabled crb`).

## Narrowing the list

An input `distributions` names the releases to build, in the piece's own
names (`debian-12`, `ubuntu-24.04`, `almalinux-10`, `fedora`, `alpine` and so
on); unset builds all. As with `targets` (D34), a call that sets it needs an
exception, here `linux-packages`, whose text gives the reason. A name the
piece does not know fails the run. `check` reports a call that sets
`distributions` without the exception.

A call of this piece without `distributions` meets `linux-packages`. The row
of the exceptions table in `project-shape.md` that asks for `linux-packages`
when a musl target is left out applies only to a repository that does not call
this piece. Leaving out the musl targets still needs `native-targets`, as
today; lectover has it.

The piece checks that every leg of the chosen releases produced its package
before it ends, because a `release_assets` glob such as `*.deb` fails only when
nothing matches.

## Publishing

`linux-packages` requires the packages in the Gitea registry.
`ri-publish-gitea` learns to route the files this piece writes from their
names (owner, 2026-11-12):

| File | Upload path under `<gitea-url>/api/packages/<owner>/` | User adds |
|---|---|---|
| `.deb` | `debian/pool/<codename>/<component>/upload` | the snippet with `$VERSION_CODENAME`, as today |
| `.rpm` | `rpm/<dist>/upload`, or `rpm/<group>/<dist>/upload` with `rpm.group` set | `rpm/<dist>.repo` |
| `.apk` | `alpine/<branch>/main` (branch `v3.23`) | that URL in `/etc/apk/repositories`, key from `alpine/key` |

Gitea's documentation allows a slash in an rpm group (its examples are
`rocky/el9` and `test/fc38`), and documents the Alpine path with `main` as the
repository. The current paths stay as they are: every repository publishing
rpms today (unspammer, edaptor, mtuspy and others) has an empty `rpm.group`
and static packages, which keep going to `rpm/upload` and `rpm.repo`. The
`debian.distributions` map stays and wins for a file it matches, so current
callers see no change. Uploading `.apk` to Gitea's Alpine registry is new. The
install snippets in `project-shape.md` get the rpm and Alpine forms above for
a project on this piece.

## Running the legs before a release

`container-make` builds only the default `BASE`, so without more the package
names of 19 releases and `make check` on them would run first in a release.
The project therefore also calls the piece's CI form from a dispatch-only
workflow, in the way `gate-mtuspy` works in repo-infra (owner, 2026-11-12):

- `workflow_dispatch`, by hand, on any branch: all chosen legs, with build,
  `make check`, packing, read-back and install test, and no upload to a
  release.
- Create release PR runs the same legs anyway, since the release build is
  this piece.
- Pull request CI does not run it; normal pull requests stay at their
  current speed.

Whether the CI form is a second workflow file or the same piece with an input
that skips the release artifacts is left to the builder.

## Changes to the other pieces and references

- `ri-release-rust-binaries`: no glibc targets, no `features` input. #148
  points 2 to 4 are answered by this piece. For a target-specific feature on
  macOS (lectover's Metal), the crate uses Cargo's
  `[target.'cfg(target_os = "macos")'.dependencies]`; Metal is part of the
  macOS SDK, so `ri-ci-rust` on the mac runner builds it as it is. Linux GPU
  features stay out of the Cargo manifest's target table, because they would
  make `ri-ci-rust` on the Linux runner need the Vulkan headers.
- `ri-release-nfpm`: unchanged. It keeps building from the musl archives only;
  #149 closes with a pointer to this piece.
- `ri-release-homebrew`: #150 (a formula from the archives that exist) stays
  its own change, after this one. Until then lectover keeps its `homebrew`
  exception.
- `project-shape.md`, `linux-packages`, "Met by": a program that links system
  libraries, Rust, Go or interpreted with native modules, uses
  `ri-release-distro-packages`. This replaces the line that says no piece
  builds packages per architecture for an interpreted program with native
  modules.
- `conventions.md`: the two Containerfile points above.
- `catalogue.md` and the generations, from the new piece's header.
- D16 text: a release build over the threshold has this piece now.

## Migration of the two repositories

Both are follow-up pull requests in those repositories, made with `apply`.

- lectover: Linux ships as packages only, with no glibc archive.
  `ri-release-rust-binaries` builds `aarch64-apple-darwin` with
  `targets`. The Metal feature moves to a `cfg(target_os = "macos")`
  dependency. Its `Makefile` builds with `--features vulkan`. Its
  `pkg/linux/Containerfile` becomes the top-level `Containerfile` with
  `ARG BASE` and the three families. `release-build-local.yml` goes away.
  The owner accepts current releases only for lectover, so it narrows
  `distributions` with a `linux-packages` exception; which releases count as
  current is settled in that pull request.
- wg-wrangler: `debian/` and `make-deb.sh` become `nfpm.yaml` (systemd unit,
  postinst and postrm as nfpm `contents` and `scripts`) and the build
  contract above. It gains rpm and apk packages. `release-build-local.yml`
  goes away.

## Non-goals

- A single build for several distributions with a fixed glibc floor.
- openSUSE, i386, armhf, RISC-V.
- rpm and apk repositories other than Gitea's.
- Image caching or a registry. The image is built on every leg, as in
  `container-make`.
- `.apk` for static programs from `ri-release-nfpm`. Possible later with the
  same config; not part of this change.

## Left to the builder

- The image names and tags of each release, and the codenames (Ubuntu 26.04
  among them).
- How `ri-publish-gitea` reads the release from an `.apk` file name, and the
  exact `.apk` file name form.
- `lib/gitea.js` builds the rpm path with `encodeURIComponent` on the whole
  group, which turns `<group>/el9` into `<group>%2Fel9`. The path must be
  encoded per segment.
- Whether `rpmdeps` is the right entry point on AlmaLinux 9 and 10 and on
  Fedora, or `find-requires`.
- How the man pages reach `/src/man` for a project with the `man` piece:
  the same `man` job as `ri-release-rust-binaries`, downloaded into the
  checkout before the container run, with `make` not rebuilding them inside
  an image without pandoc.
- That `--target build-deps` skips the later stages under both docker and
  podman when the build has no context.
- Whether the piece runs in a job container or starts the container itself.
  `container-make` starts it itself; the piece builds the image from the
  project's file, so it does too.
- Tests: the piece's JavaScript in `lib/` with `make test-js`, the header in
  `make test`, and a proof run against a test repository with a C program that
  links a library whose soname differs between releases.

## Calls made in this design without the owner

- The piece name `ri-release-distro-packages` and the artifact names.
- `make`, `make check`, `make install DESTDIR=/stage` as the build contract,
  and `AC_PREFIX_DEFAULT` instead of configure options.
- One `Containerfile` with `ARG BASE` and a `build-deps` stage, shared with
  `container-make`, rather than one file per family.
- The detected dependencies are merged into the nfpm config by the piece.
- `linux-packages` as the exception that pairs with `distributions`.
- `ri-publish-gitea` routes by file name.
- Linux GPU features in the project's `Makefile`, not in Cargo's target table.
- Two Alpine releases.
- Per-release values in `nfpm.yaml` through the variables `RELEASE`, `ID`,
  `VERSION_ID` and `CODENAME`, with `packagers` still keyed by packager.
- A call without `distributions` meets `linux-packages`; leaving out musl then
  needs only `native-targets`.
