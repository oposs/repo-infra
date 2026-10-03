# Conventions

House rules that are not derivable from the repository you are standing in.
Facts with values (action majors, the ruleset payload) live in
`assets/manifest.json` and `assets/gh/ruleset-main.json`. This file carries only
the reasoning that made those values the way they are, and the traps a model
reaches for by default instead.

## `### New`, never `### Added`

Keep a Changelog calls the section `### Added`. This project's roller matches
literally on `### New`. A model told only "use Keep a Changelog" writes
`### Added` with full confidence, and the roller finds nothing under
`[Unreleased]` to move. There is no error, just an empty release notes section, on
a release that has content. Nothing fails; the section is just gone.

## `actions/github-script` injects ten names into every `script:` block

`context`, `core`, `github`, `octokit`, `getOctokit`, `exec`, `glob`, `io`,
`require`, `__original_require__`. Declaring a variable with any of these names
shadows the injected one at best, and at worst collides at parse time before a
single line of your script runs.

`io` is the one that actually happened here: the release workflows named their
file-access object `io`, and the step died with
`SyntaxError: Identifier 'io' has already been declared` before executing
anything: an entire release attempt, gone with no useful log. It is `fileIO`
now, in every workflow that touches files through github-script.

## A required job carries no `name:`

A workflow's `name:` is what a human reads in the Actions UI. A job's **check
context** (what the ruleset actually matches against) is its job id, unless
the job also sets `name:`, in which case the context becomes that name instead.
`changelog-updated` and `ci-passed` are job ids with no `name:` for exactly this
reason: give either one a friendly `name:` later and the check context changes
with it, silently un-requiring the check the ruleset was written against. Every
*other* job in a caller or a piece is free to carry a `name:`; only the two the
ruleset names by id are not.

## Never add `paths` or `paths-ignore` to a required workflow

Two different things can skip work, and GitHub reports them differently:

| What is skipped | Reported as | Effect on a required check |
|---|---|---|
| a **job**, by a job-level `if:` | Success | merges fine |
| a **workflow**, by `paths`/`paths-ignore`/`branches` filtering | stays Pending | blocks the pull request forever |

`ci.yml` and `changelog.yml` are required by the ruleset, so neither carries a
workflow-level `paths` or `paths-ignore` filter, ever. Conditional work moves
inside a job instead. A `branches: [main]` filter is fine on `pull_request`
because it matches the PR's base, which is what the ruleset gates; it is not a
license to add a `paths` filter alongside it.

## `dtolnay/rust-toolchain@stable` is meant to stay a branch reference

It looks like a version that dependabot forgot to bump. It is not a version at
all: `@stable` tracks the toolchain channel, not a tagged release of the
action, and dependabot correctly leaves branch references alone. Do not "fix"
it to a SHA or a version tag; that pins the Rust toolchain to whatever was
current on the day of the pin, which is the opposite of what this line is for.

## The workflow library is CommonJS, not ESM

`.github/workflows/lib/*.js` uses `require()` and `module.exports`, because
that is what `actions/github-script` provides to a `script:` block, and there is
no way to `import` an ES module into one. An editor with type-aware completion
will suggest `import`/`export` the moment it sees a `.js` file; the suggestion
is wrong for this directory specifically, not a style preference to override.

## `.github/repo-infra.json` holds what a caller cannot say

The file keeps only what the release machinery (`release-pr.yml`, `lib/*.js`)
reads and what cannot be seen in a caller. Nothing writes it: it is hand-edited,
and `check` and `apply` only read it. `check` reports a key it does not read as
a `problem`, and the keys of the old assembler (`ecosystems`, `ci`, `publish`, `build`,
`release_build`, `skip`, `answers` and the three that ended in `_local`) as
`problem` too, so a migrated repository is told to remove
them (D30). The callers state the same facts directly.

- `version_files`: where the release writes the version, and what it reads back
  to confirm the write took (D5, D6). `references/onboarding.md` has the entries
  per build file, including one `Cargo.lock` entry per released crate.
- `release_assets`, `release_files`: every file the release must carry, as name
  patterns, and the repository paths the build may rewrite (D26). `check`
  refuses a `release_files` entry that is `CHANGES.md`, a version file or under
  `.github/`.
- `gitea_packages`: the Gitea server (`url`), the owner and the channels
  `ri-publish-gitea` uploads to. `references/release-flow.md` has the shape.
- `moving_major_tag`: whether publishing also moves a floating `vN` tag
  alongside the exact `vN.N.N` one. Off by default; most consumers pin exact
  tags, and a floating major tag is a promise to keep it working forever.
- `rust`: the crates `ri-ci-rust` lints and tests (D24, below). It stays because
  `lib/rust-plan.js` reads it at run time (Decision G of D30).

`ri-publish-crates-io` carries a prerequisite that lives outside the repository:
crates.io pins a Trusted Publisher to a *(repository, workflow filename)* pair,
and the filename is the caller's `.github/workflows/release-publish.yml`. A crate
that published before it was converted has its publisher registered against its
old workflow name, and that pin does not follow the rename. Register a new
Trusted Publisher per publishable crate before the first converted release, or
the release stays a draft and the crate never ships. `check` queries GitHub, not
crates.io, and cannot see this.

## The Containerfile contract (D18)

repo-infra owns the *shape* of the build environment; the project owns its
*content*. The `Containerfile` is therefore the project's own file and is not
shipped, versioned or drift-checked -- every project must edit it to name its
own packages, and a checker could not tell an intended edit from a stale copy.

The pieces are `container-m4` (`m4/repo-infra-container.m4`) and `container`
(`build/container.mk`), which together make the tree a container driver.
Nothing installs them automatically; it is a decision, made with
`apply --item container-m4` and `apply --item container`.

What it must do, so the driver targets can reach it:

1. **Carry the autotools toolchain** -- `autoconf`, `automake` and `make` are in
   the image, because the image's build phase runs them.
2. **Run the real build in its build phase** --
   `./bootstrap && ./configure --disable-container && make && make install`.
   `configure` does not exist in a fresh checkout, so the image must bootstrap
   first. `--disable-container` names the semantics, not the location: it means
   "do the real build in this tree", which is also what a distro packager on a
   bare build host wants.
3. **Leave the build tree at `/src`** -- `make dist` and `make test` are run
   against that path from outside.
4. **List itself in `EXTRA_DIST`** -- `build/container.mk` and
   `m4/repo-infra-container.m4` are distributed automatically (an included
   fragment and a macro directory), but the project's own `Containerfile` is
   not, so without this a released tarball extracts to a tree `configure`
   refuses in its default mode: `no Containerfile in . -- write one, or pass
   --disable-container to build in this tree.`
5. **Provide GNU tar** -- automake 1.17+ defaults `AM_INIT_AUTOMAKE`'s archive
   format to `ustar`, and busybox tar cannot write that format, so on an image
   whose default `tar` is busybox (Alpine's, for example) automake's probe
   fails and it silently falls back to `am__tar=false`: `make dist` then exits
   0 having archived nothing.

`configure.ac` calls `REPO_INFRA_CONTAINER` and wraps its own dependency checks.
The macro installs to `m4/repo-infra-container.m4`, so the project must also
declare its macro directory -- without it, `aclocal` never sees the file, and
`autoreconf` fails with `CONTAINER_DRIVER does not appear in AM_CONDITIONAL`,
an error that points at this fragment for a line the project never wrote:

    AC_CONFIG_MACRO_DIRS([m4])

    REPO_INFRA_CONTAINER
    AS_IF([test "x$enable_container" = xno], [
      dnl librrd, RRDs, everything real -- probed here and nowhere else
    ])

and in `Makefile.am`, so a bare `aclocal` run finds it too:

    ACLOCAL_AMFLAGS = -I m4

**Single-file test runs.** `make test-dev TARGET=t/foo.t` reaches one file
through `make test TESTS=<file>`. Automake honours a command-line `TESTS=`
override for free, so a project whose `test` target is `test: check` needs to do
nothing. A project that drives `prove` itself must honour `TESTS` the same way.

**`test-dev` needs `TEST_DEV_MOUNTS`.** The project declares, in its own
`Makefile.am` before the include, which directories hold the interpreted source
it wants to edit and re-run against without rebuilding the image:

    TEST_DEV_MOUNTS = lib t bin/plugins

There is no way for the fragment to guess this list -- a blanket mount of the
whole tree would hide everything `configure` generated inside the image -- so
`test-dev` refuses with a usage message when it is unset, the same way it
refuses a missing `TARGET`, rather than silently testing the image's baked-in
copy instead of the file just edited.

**What `Makefile.am` must look like.** A project already defines its own
`test:` for the native case (`test: check`) and now also includes
`build/container.mk`. Both definitions are unconditional, so automake sees
`test:` defined twice and warns at generation time:

    build/container.mk:NN: warning: test was already defined in condition TRUE, which includes condition CONTAINER_DRIVER

The fix is to guard the project's own target with the negated conditional, so
the two definitions are never both live:

    if !CONTAINER_DRIVER
    test: check
    endif
    include $(top_srcdir)/build/container.mk

With that guard, `autoreconf` emits zero warnings and both modes still behave
correctly -- native runs the real suite, driver delegates to podman.

**`make install` needs `DESTDIR`.** In driver mode, `make install` without
`DESTDIR` refuses with a usage message rather than mounting the host's
`$(prefix)` read-write into the container.

## Project-owned workflows (D20, D25, D28)

`ci-local.yml`, `release-build-local.yml` and `action-test.yml` belong to the
repository and are called from its callers. The contract is in
`references/onboarding.md`, under "Project-owned workflows".

## The `rust` key (D24)

    "rust": {
      "lint": ["mdmost"],
      "test": ["mdmost", "pulldown-latex"],
      "tested_elsewhere": ["syntect"]
    }

- `lint`: crates that `rust-check` runs `cargo fmt --check -p` and
  `cargo clippy --all-targets -p <name> --no-deps -- -D warnings` on.
  Leaving `lint` out lints the whole workspace.
- `test`: crates that `rust-test` runs `cargo test -p` on, one matrix leg per
  crate. Required whenever the key is present.
- `tested_elsewhere`: workspace members whose tests run outside `rust-test`,
  for example in `ci-local.yml`. The standard runs nothing for them and cannot
  confirm that anything else does.

`rust-plan` reads the key at run time and fails, naming the crates involved,
when:

- a listed name is not a workspace member;
- a workspace member is in neither `test` nor `tested_elsewhere`;
- `lint` or `test` is present and empty, or `test` is missing;
- the key is absent and the workspace's default members differ from its
  members (a root `[package]`, or `default-members` in any workspace).

Without the key, a workspace whose default members equal its members runs
the workspace-wide commands as before. A repository whose default members
differ from its members must set the key. `ci-rust` v2 fails on the upgrade
pull request, with a message naming the members and the key, until it does.

## Markers and bytes (D30)

Every piece carries a marker on its first comment line: `# repo-infra: <piece>
vN` (`// repo-infra:` in the JS library, `dnl repo-infra:` in m4, `-- repo-infra:`
in the Lua filter). The marker says which version the file claims to be. The
bytes say whether it is that version: `check` hashes the file and compares it
with every published version of the piece in `assets/generations.json`, so a
copy is `current`, `outdated` (an older published version) or `edited` (no
published version). A hash does not report drift on every repository, because a
piece carries no repository-specific text and a repository never has a reason
to change one.

This supersedes two earlier rules. D11 ("markers, never content hashes") held
while the standard assembled `ci.yml` from blocks and a project name, an extra
matrix target or a publish job was a legitimate local edit that a hash could not
tell from an upgrade. Pieces are copied 1:1 and the repository's own text lives
in callers, so the hash now has one meaning. D29 (a hash suffix on the first
marker line, written by `apply` so it could tell its own output from an edit)
goes for the same reason: the published hashes answer that question without
writing anything into the file. A file still carrying a stamp from v0.3.1 reads
as its version, because `check` ignores the suffix.

A marker and `CHANGES.md` can answer "did this version ship?" differently, and
that is by design. The marker counts every version a piece ever reached,
including one that only lived on a branch; `CHANGES.md` records what a released
version added, so a version nobody outside this repository received earns no
entry.

An `edited` piece is merged by hand (`commands/apply.md`). A file whose marker
claims the current or a newer version than the plugin ships is never written and
never merged: there is nothing to merge into it, and writing it would be a
downgrade.
