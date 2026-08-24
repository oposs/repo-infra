# Conventions

House rules that are not derivable from the repository you are standing in.
Facts with values — action majors, the ruleset payload, the detection table —
live in `assets/manifest.json`, `assets/gh/ruleset-main.json` and
`assets/detection.json`. This file carries only the reasoning that made those
values the way they are, and the traps a model reaches for by default instead.

## `### New`, never `### Added`

Keep a Changelog calls the section `### Added`. This project's roller matches
literally on `### New`. A model told only "use Keep a Changelog" writes
`### Added` with full confidence, and the roller finds nothing under
`[Unreleased]` to move — not an error, just an empty release notes section, on
a release that has content. Nothing fails; the section is just gone.

## `actions/github-script` injects ten names into every `script:` block

`context`, `core`, `github`, `octokit`, `getOctokit`, `exec`, `glob`, `io`,
`require`, `__original_require__`. Declaring a variable with any of these names
shadows the injected one at best, and at worst collides at parse time before a
single line of your script runs.

`io` is the one that actually happened here: the release workflows named their
file-access object `io`, and the step died with
`SyntaxError: Identifier 'io' has already been declared` before executing
anything — an entire release attempt, gone with no useful log. It is `fileIO`
now, in every workflow that touches files through github-script.

## A required job carries no `name:`

A workflow's `name:` is what a human reads in the Actions UI. A job's **check
context** — what the ruleset actually matches against — is its job id, unless
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
workflow-level `paths` or `paths-ignore` filter, ever — conditional work moves
inside a job instead. A `branches: [main]` filter is fine on `pull_request`
because it matches the PR's base, which is what the ruleset gates; it is not a
license to add a `paths` filter alongside it.

## `dtolnay/rust-toolchain@stable` is meant to stay a branch reference

It looks like a version that dependabot forgot to bump. It is not a version at
all — `@stable` tracks the toolchain channel, not a tagged release of the
action, and dependabot correctly leaves branch references alone. Do not "fix"
it to a SHA or a version tag; that pins the Rust toolchain to whatever was
current on the day of the pin, which is the opposite of what this line is for.

## The workflow library is CommonJS, not ESM

`.github/workflows/lib/*.js` uses `require()` and `module.exports`, because
that is what `actions/github-script` provides to a `script:` block — there is
no way to `import` an ES module into one. An editor with type-aware completion
will suggest `import`/`export` the moment it sees a `.js` file; the suggestion
is wrong for this directory specifically, not a style preference to override.

## `.github/repo-infra.json` is the repository's own decisions, not detection output

Detection answers what a repository's files show; this file answers what
cannot be read off them. Nothing writes it at runtime -- `write_config` exists
for `apply` to call one day, but nothing calls it yet, so today it is
hand-authored and hand-edited. `check` and `apply` only read it.

- `ecosystems` -- the detected list, recorded so a later run can tell "still
  this" from "detection changed underneath me". Not itself a lever to pull.
- `moving_major_tag` -- whether publishing also moves a floating `vN` tag
  alongside the exact `vN.N.N` one. Off by default; most consumers pin exact
  tags, and a floating major tag is a promise to keep it working forever.
- `version_files` -- where the release workflow writes the version, and what
  it reads back to confirm the write took (D5/D6 and the module docstring in
  `apply.py`).
- `publish` -- which publish add-ons this repository's release workflow
  assembles, by id (`manifest.json` `publish_blocks`). This branch makes the
  key meaningful: `["publish-source-tarball"]` attaches the `make dist`
  tarball to the release, and it is a **blocking prerequisite** for converting
  any autotools repository that already publishes one -- convert without it
  and the tarball a project ships today silently stops shipping.
- `build` -- which build assets this repository's Makefile and `configure.ac`
  install, by id (`manifest.json` `build_assets`). A containerized autotools
  repository names both: `["container-m4", "container"]` installs
  `m4/repo-infra-container.m4` and `build/container.mk`, which together make
  the tree a container driver (D18). Nothing installs them automatically; it is
  a decision, not a detection (see `references/teaching-the-standard.md`).
- `skip` -- items a human deliberately declined, name to reason. `check` reads
  this to stop nagging about a considered "no" instead of an oversight.
- `answers` -- resolved ambiguities, id to the answer given. Recorded so
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

## Markers record a generation, never a content hash

Every installed asset carries `# repo-infra: <asset> vN` (or `// repo-infra:
<asset> vN` in the JS library). `check` compares that number against
`assets/manifest.json`; it never hashes the file. A hash would report drift on
every repository, forever — a project name in `ci.yml`, an extra matrix target,
a publish job bolted onto `release-publish.yml`, are all local edits a
repository is entitled to make, and a hash cannot tell "edited" from
"upgraded". The marker answers a narrower question — *which generation of the
asset is this* — and a local edit that keeps the marker at the current version
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
