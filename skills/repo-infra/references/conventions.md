# Conventions

House rules that are not derivable from the repository you are standing in.
Facts with values (action majors, the ruleset payload, the detection table)
live in `assets/manifest.json`, `assets/gh/ruleset-main.json` and
`assets/detection.json`. This file carries only the reasoning that made those
values the way they are, and the traps a model reaches for by default instead.

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
*other* job in a generated workflow is free to carry a `name:`; only the two the
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

## `.github/repo-infra.json` is the repository's own decisions, not detection output

Detection answers what a repository's files show; this file answers what
cannot be read off them. Nothing writes it at runtime -- `write_config` exists
for `apply` to call one day, but nothing calls it yet, so today it is
hand-authored and hand-edited. `check` and `apply` only read it.

- `ecosystems`: the detected list, recorded so a later run can tell "still
  this" from "detection changed underneath me". Not itself a lever to pull.
- `moving_major_tag`: whether publishing also moves a floating `vN` tag
  alongside the exact `vN.N.N` one. Off by default; most consumers pin exact
  tags, and a floating major tag is a promise to keep it working forever.
- `version_files`: where the release workflow writes the version, and what
  it reads back to confirm the write took (D5/D6 and the module docstring in
  `apply.py`). In a Rust repository with a `Cargo.lock`, detection adds one
  `Cargo.lock` entry for the root package and for every workspace member with
  `version.workspace = true`; the release PR commits only these paths, so a
  lockfile left out keeps the old version.
- `publish`: which publish add-ons this repository's release workflow
  assembles, by id (`manifest.json` `publish_blocks`). `publish-crates-io` and
  `publish-gitea-packages` are the publish add-ons. The `make dist` tarball is
  no longer a publish add-on: it is the build add-on `release-source-tarball`
  (see `release_build`), a blocking prerequisite for converting any autotools
  repository that already publishes one.
  `["publish-crates-io"]` publishes the whole cargo workspace to crates.io
  (D21). It carries a prerequisite that lives outside the repository: crates.io
  pins a Trusted Publisher to a *(repository, workflow filename)* pair, and the
  filename the standard renders is always
  `.github/workflows/release-publish.yml`. A crate that published before it was
  converted has its publisher registered against its **old** workflow name, and
  that pin does not follow the rename -- so register a new Trusted Publisher
  per publishable crate before the first converted release, or the release
  stays a draft and the crate never ships. `check` queries GitHub, not
  crates.io, and cannot see this for you.
- `publish_local`: publish jobs the repository writes **itself**, which
  `finalize` must wait for and whose assets `finalize` must find. Each entry is
  `{"job": "<job id>", "assets": ["<name pattern>", ...]}`. This exists because
  some repositories run a publish job the standard does not ship yet --
  smtp-proxy-rs builds a `.deb` and a container image, and there is no add-on
  for that pair (R32: prove it here, upstream it later). The job block itself
  is a local edit to the assembled `release-publish.yml`, which `apply` reports
  as a conflict and a human merges; that half is loud and survives. Its entry
  in `finalize`'s `needs:` used to be a local edit too, and that half did not
  survive: one generated line, silently rewritten by the next `apply`, and the
  revert **does not fail** -- `finalize` simply stops waiting and flips a
  release to public while the `.deb` is still building, or after it failed.
  Naming the job here makes that line generated instead, so `apply` restores it
  rather than removing it. `assets` are asset **name patterns**, where `*`
  stands for any run of characters: `["*.deb"]`, not a literal name that would
  carry the version and go red on the next release. They are what `finalize`
  asserts against the real release before publishing it -- ordering cannot
  report its own absence, an assertion can. Declaring a job the assembler
  already generates is refused at assembly.
- `release_build`: the build add-ons the assembled `release-build.yml`
  runs on the release branch before the pull request exists (D28), by id
  (`manifest.json` `release_build_blocks`). `["release-source-tarball"]`
  builds the `make dist` tarball. Each add-on declares the asset name
  patterns it produces, and `release_assets` must list them: `finish` is a
  copied file and cannot know which add-ons are installed. `check` reports a
  missing pattern and `apply` adds it.
- `release_build_local`: `true` adds the project's own
  `.github/workflows/release-build-local.yml` to `release-build.yml`.
- `release_assets`, `release_files`: every file the release must carry, as
  name patterns, and the repository paths the build may rewrite (D26).
- `build`: which build assets this repository's Makefile and `configure.ac`
  install, by id (`manifest.json` `build_assets`). A containerized autotools
  repository names both: `["container-m4", "container"]` installs
  `m4/repo-infra-container.m4` and `build/container.mk`, which together make
  the tree a container driver (D18). Nothing installs them automatically; it is
  a decision, not a detection (see `references/teaching-the-standard.md`).
  A CI block may carry build assets of its own (D23): choosing `ci-man`
  installs `build/man.mk` and `build/man-deflist.lua` as if they were listed
  here, and listing them here as well is allowed.
- `ci`: which **opt-in** CI blocks this repository's `ci.yml` assembles, by id
  (`manifest.json` `ci_blocks`, the entries marked `"optional": true`). Every
  other CI block arrives by detection; these are the ones detection cannot
  answer, because the repository's files do not state the intent.
  `["ci-rust-musl"]` adds a statically linked musl cross-build for
  `x86_64` and `aarch64` (D22) -- a Rust repository that ships a Linux binary
  wants it, and a library crate has no binary to link, which is why
  `Cargo.toml` alone is not enough to decide. `["ci-man"]` builds the man page
  from `docs/manual.md` with `make man` and fails on any roff warning except
  pandoc's two font warnings (D23). It names no ecosystem and fits any, and
  choosing it installs the build assets `make man` runs; the repository sets
  `MAN_NAME` and adds `include build/man.mk` to its Makefile. The `man-pages`
  skill has the rest. Once named an add-on is **required**,
  not advisory: the job joins `ci-passed`'s generated `needs:` list like any
  other block, so a broken cross-compile blocks the pull request instead of
  surfacing at release time. Naming a block whose ecosystem this repository
  does not have, or one detection already installs, is refused at assembly
  rather than rendered -- the second would emit a duplicate job id, which makes
  the whole of `ci.yml` invalid so that *no* job runs at all.
- `skip`: items a human deliberately declined, name to reason. `check` reads
  this to stop nagging about a considered "no" instead of an oversight.
- `answers`: resolved ambiguities, id to the answer given. Recorded so
  `apply` never has to guess on the next run.

## The Containerfile contract (D18)

repo-infra owns the *shape* of the build environment; the project owns its
*content*. The `Containerfile` is therefore the project's own file and is not
shipped, versioned or drift-checked -- every project must edit it to name its
own packages, and a checker could not tell an intended edit from a stale copy.

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

## Project-owned workflows behind a fixed seam (D20, D25, D28)

Same shape as the Containerfile contract, one layer over: repo-infra owns the
*seam*, the project owns the *test*. An action's real test is `uses: ./` with
real inputs, and repo-infra cannot know what inputs this action takes -- so it
does not try. It ships one literal job that calls a reusable workflow at a
fixed path:

    action-test:
      uses: ./.github/workflows/action-test.yml

`.github/workflows/action-test.yml` is therefore the project's own file: not
shipped, not versioned, not drift-checked, and **not** assembler output despite
living beside files that are. What it must do:

1. **Trigger on `workflow_call` and nothing else.** `on: workflow_call:`. Add
   `push` or `pull_request` beside it and every run happens twice -- once here
   and once through `ci.yml` -- which reads as flakiness rather than as a
   duplicated trigger.
2. **Carry its own `timeout-minutes`,** on each of its jobs. GitHub rejects
   `runs-on`, `steps` and `timeout-minutes` on a job that calls a reusable
   workflow, so the calling job cannot impose one and the standard's usual
   per-job timeout has to come from inside.
3. **Exist.** A `uses:` pointing at a missing workflow makes the whole of
   `ci.yml` invalid, so *no* job runs and the pull request blocks on a check
   that never reports -- loud, but the message names YAML rather than this
   contract. `check` reports it as its own line for that reason.
4. **Declare the input `ref` and check it out.** `on: workflow_call: inputs:
   ref`, and `ref: ${{ inputs.ref }}` on every `actions/checkout`, directly
   under that step's own `with:`. `Create release PR` runs `ci.yml` on the
   release branch and passes that commit here; a checkout without it tests
   `main` and reports the release as tested. `check` reads these files as
   text, so every step is block-style YAML: `- uses: ...` with its keys on the
   lines below, without flow mappings, anchors or aliases. A step it cannot
   read counts as a violation (`cannot read`). `check` reports a missing
   input, a checkout without `ref` and an unreadable step as `conflict`
   (`action-test-seam`, `ci-local-seam`, `release-build-local-seam`), naming
   the file, and `apply` does not edit these files.

These files get the repository's secrets (`secrets: inherit`) and must not ask
for more permissions than `contents: read`; `ci.yml`'s callers grant no more.
The artifact names `release-asset-*` and `release-files` are reserved for the
build (see release-build-local below).

The path is fixed rather than configurable on purpose: a name in
`.github/repo-infra.json` would be one more thing per repository to get wrong,
for no gain over renaming one file during conversion.

The block's other job, `action-manifest`, is repo-infra's own and needs nothing
from the project. It reads `action.yml` and every workflow beside it, and fails
on either half of a mismatch between the two -- an input a workflow passes that
`action.yml` does not declare, or a `required: true` input a workflow omits.
Both are silent in GitHub's own runner: the first prints `Unexpected input(s)`
as a warning and drops the value, and the second is not enforced at all. A test
that hits either one is green while testing nothing.

The manifest is `action.yml`. GitHub also accepts `action.yaml`; the standard
does not, and a repository spelling it the other way renames the file during
conversion.

### ci-local (D25)

`"ci_local": true` in `.github/repo-infra.json` adds
`ci-local: uses: ./.github/workflows/ci-local.yml` to `ci.yml` and `ci-local`
to `ci-passed`'s `needs:`. The four action-test rules apply unchanged: the
file triggers on `workflow_call` only, every job in it sets `timeout-minutes`,
the file exists, and it declares the input `ref` and checks it out. `check`
reports a missing file as `conflict` under the item `ci-local-workflow`, and a
file without `ref` under `ci-local-seam`.

One more rule: conditions go inside steps, never on a job. A reusable workflow
whose every job is skipped reports `ci-local` as skipped, and `ci-passed`
counts a skipped need as green.

### release-build-local (D28)

`"release_build_local": true` makes the assembled `release-build.yml` call
`.github/workflows/release-build-local.yml`, the project's own build. What it
must do:

- Trigger on `workflow_call` with the string inputs `version` and `ref`, and
  check out `inputs.ref` in every `actions/checkout`.
- Upload each file the release ships as an artifact whose name starts with
  `release-asset-`.
- Upload the repository files the build rewrote, for example a Homebrew
  formula, as one artifact named `release-files`. Its paths are repository
  paths, and each one is listed in `release_files`.
- Ask for no more than `contents: read`.

`check` reports a missing file as `conflict` under the item
`release-build-local`, and a file that does not declare or check out `ref`
under `release-build-local-seam`.

Upload `release-files` from a staging directory whose tree holds the
repository paths, because `upload-artifact` strips the common parent
directory: uploading `Formula/mdmost.rb` directly yields `mdmost.rb`, which is
refused as undeclared. Files with the same name in several `release-asset-*`
artifacts overwrite each other.

`build` and `test` run in the same workflow run and share one artifact
namespace, so `release-asset-*` and `release-files` are reserved for the
build: `check` reports a `conflict` when `ci-local.yml` or `action-test.yml`
uploads an artifact with such a name. A file named `release-build.json` is
refused: that name is the build record `finish` writes itself.

The build and the CI run get the repository's secrets. No repository secret
may carry write access to the repository; a classic personal access token
with `repo` scope breaks that rule.

### The `rust` key (D24)

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

## Markers record a generation, never a content hash

Every installed asset carries `# repo-infra: <asset> vN` (`// repo-infra:` in
the JS library, `dnl repo-infra:` in m4, `-- repo-infra:` in the Lua filter).
`check` compares that number against
`assets/manifest.json`; it never hashes the file. A hash would report drift on
every repository, forever. A project name in `ci.yml`, an extra matrix target,
a publish job bolted onto `release-publish.yml`, are all local edits a
repository is entitled to make, and a hash cannot tell "edited" from
"upgraded". The marker answers a narrower question (*which generation of the
asset is this*), and a local edit that keeps the marker at the current version
reads as a healthy `ok`, not drift.

A file assembled from several blocks carries one marker per block: `ci.yml`'s
frame marker sits on line 2, and each ecosystem's block carries its own marker
directly above its jobs. `check` reads every marker in the file, so a
Python-and-Claude-plugin repository can be outdated on `ci-python` while
`ci-claude-plugin` is current, and upgrading one never touches the other.

A marker and `CHANGES.md` can answer "did this generation ship?" differently,
and that is by design, not an inconsistency to reconcile: the marker's question
is "is what I have exactly what `apply` installs right now", so it must count
every generation an asset ever reached, including one that only ever lived on a
branch; `CHANGES.md`'s question is "what did a released version add", so a
generation nobody outside this repository received earns no bullet. A marker
bump with no matching changelog entry is not a gap between the two files -- it
is the two files doing their separate jobs correctly.

### The stamp (D29)

Every file `apply` writes from a rendered asset ends its first marker line in
` sha256=<16 hex digits>`, the start of the SHA-256 of the file without that
suffix. It answers one question: is this file byte for byte what `apply`
wrote? If so, an upgrade overwrites it. `check` never reads it, so the
argument above stands. A hand merge (`--from`) gets no stamp, so the next
upgrade stops at it again. This replaced looking the old generation up in the
plugin's git history, which an installed plugin does not have.
