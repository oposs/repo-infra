# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
except that the first subsection is called `New` rather than `Added`. The release
workflow matches on `### New`; renaming it silently drops the section from the
release notes.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### New

- A Rust workspace can list which crates `ci-rust` lints and which it tests, in a `rust` key of `.github/repo-infra.json`; each crate gets its own check. A workspace where a plain `cargo test` would skip some crates now fails the `Rust workspace plan` check until the key says where their tests run.
- `"ci_local": true` makes the jobs in `.github/workflows/ci-local.yml` part of the required `ci-passed` check.
- `"release_build": true` builds every release file inside the release pull request, into a draft release. Files such as a Homebrew formula change in that pull request, nothing is pushed to `main` after the merge, and publishing tags the commit that was built.
- The `publish-gitea-packages` add-on uploads a release's `.deb` and `.rpm` files to a Gitea package registry, which signs them; the release stays a draft until the upload succeeded.

### Changed

- The `changelog-updated` check now also runs on `release/*` branches. In a repository with `release_build` it fails when the release branch changed after its build, for example after **Update branch**; elsewhere it passes as before.
- Publish add-ons check out the tagged commit explicitly. Without `release_build` this is the same commit as before.
- Re-running the publish workflow no longer fails on a source tarball or a crate that an earlier attempt already uploaded. **Re-run failed jobs** and a whole-workflow re-run both finish a stopped release.
- When a release pull request shows the "Approve workflows to run" banner,
  Claude now knows the parked runs can be approved from the terminal with
  `gh api`, and asks before doing so. The button stays the fallback.

### Fixed

## 0.2.0 - 2026-09-28
### New
- The `ci-man` add-on (D23). A repository with its manual in `docs/manual.md`
  lists `ci-man` in the `ci` list of `.github/repo-infra.json`, and every pull
  request then builds the man page with `make man` and fails when the manual
  stops converting or roff reports a warning such as `table wider than line
  length minus indentation`. Choosing it installs `build/man.mk` and
  `build/man-deflist.lua`, which turns option lists written as
  ``- `--option`: text`` into proper man page entries, and `check` stops
  listing `man-pages` among its candidates.
- `make man` puts the page in the man section that `section:` in the manual's
  front matter names, so a daemon's manual with `section: 8` builds
  `man/<name>.8`, and `ci-man` checks pages of every section. A manual without
  a `section:` line stops `make man` with a message naming `docs/manual.md`.
- Two skills in the plugin: `writing-style` gives the house voice for READMEs,
  manuals, maintainer notes, changelog entries, code comments and commit
  messages, and `man-pages` covers how a man page is structured, built and
  shipped. They trigger on their own, without a repository check.
- The `ci-rust-musl` add-on (D22), and with it the first CI block a repository
  chooses rather than one detection finds. A Rust repository names it in a new
  `ci` list in `.github/repo-infra.json` and every pull request cross-builds a
  statically linked musl binary for `x86_64` and `aarch64`, then **asserts** the
  linkage -- `crt-static` is a hint the linker may ignore, and a binary that
  only runs on the machine that built it fails at the far end, on a host nobody
  is watching. It is opt-in because `Cargo.toml` does not say whether a
  repository ships a binary: a library crate has none to link. Once named it is
  a required check, joining `ci-passed`. See `references/conventions.md`.
- The `publish-crates-io` add-on (D21). A repository names it in its `publish`
  list and its releases go to crates.io with **no stored credential**: the job
  exchanges its GitHub OIDC identity for a short-lived token via
  `rust-lang/crates-io-auth-action`, so no `CRATES_IO_TOKEN` secret exists
  anywhere. One `cargo publish --workspace --locked` serves both the
  single-crate and the multi-crate case, in dependency order, replacing the
  hand-rolled publish-then-retry loop a workspace needs otherwise.
  Converting a crate that already publishes needs a new Trusted Publisher
  registered on crates.io first -- the pin names the workflow filename, and
  conversion renames it. See `references/conventions.md`.
- Repositories whose product is a GitHub Action are recognised. `action.yml`
  selects a `github-action` ecosystem, which validates the action manifest
  against every workflow that calls it and runs the project's own action test.
- A Python repository can declare test dependencies. `ci.yml`'s pytest job now
  installs `requirements-dev.txt` when the repository has one, the same way the
  Checkmk plugin job already did.
- repo-infra's own CI builds a real container and runs the autotools driver it
  ships against it, as a required check. The assets are the product, so a
  regression in them no longer merges.
- Autotools repositories can now build in a container end to end. `configure`
  and `make` outside the container drive podman; inside, they are plain
  autotools. A CI runner no longer probes a project's system dependencies.
  repo-infra ships the *shape* of the build environment (`build/container.mk`);
  the project keeps its Containerfile and what goes in it.
- `make test-dev TARGET=t/foo.t` runs one test file against the live working
  tree, without rebuilding the image.
- The plugin documents what to do when the standard has no answer for a
  repository's shape: question, prove, upstream, with a report that says so
  instead of a false "N items need attention" count.
- A publish add-on that attaches the `make dist` source tarball to a release. It is the first of spec 2's add-ons, and any autotools repository needs it before it can be converted without losing the tarball it publishes today.
- A CI block for Checkmk plugins: lint, tests and a throwaway package build. The Checkmk API a plugin imports is declared by the plugin, not by this block.
- The plugin reads a repository's ruleset, labels and workflow permissions.
- The plugin ships the release workflows as versioned, installable assets.
- The plugin can read and write asset version markers.
- The plugin detects a repository's ecosystems from file signals.
- The plugin assembles a repository's ci.yml from a frame plus one block per ecosystem.
- This repository's own .github/ is generated from the plugin's assets, and CI fails if the two differ.
- The plugin reports how far a repository has drifted, per asset and per CI block, and honours deliberate skips.
- /repo-infra:check reports drift as text or JSON.
- /repo-infra:apply installs missing assets on a branch, one commit per item.
- /repo-infra:apply creates the no-changelog label, sets workflow permissions and enables the ruleset, in that order.
- The plugin ships the repo-infra skill and the /repo-infra:check and /repo-infra:apply commands.
- CI blocks for rust and go.
- CI blocks for node, one for pnpm and one for bun.
- CI blocks for perl, one for autotools projects and one for Makefile.PL projects.

### Changed
- `check` reports `release-pr` and `changelog` as outdated until `apply`
  installs the new generation, whose only change is wording without em dashes.
  In the Actions log the first step of **Create release PR** is now called
  `Guard (right branch, green checks)`, and the report's first line reads
  `repo-infra check: <repo>`.
- The autotools CI block installs one fixed host toolchain and calls `make test`, rather than building natively against whatever the runner image happens to ship. A project that needs more than the toolchain declares it in its own Containerfile.
- The autotools release writes `VERSION` instead of rewriting `configure.ac`, which is where every autotools repository examined keeps its version.
- `check` now says when the standard does not recognise a repository at all, instead of reporting a count of missing items drawn from a repository kind it never identified.
- The release system is proven end to end: `v0.1.0` was cut by dispatching
  **Create release PR**, merging the pull request it opened, and letting the
  publish workflow tag and publish. The one manual step is the deliberate
  **Approve workflows to run** click on the release pull request, which exists so
  that no credential has to be stored; `RELEASING.md` explains why.

### Fixed
- `apply --item workflow-lib` refused every upgrade with `ships N files, and
  only a single-file asset can be merged or upgraded in place`, and `check`
  reported a partly upgraded library as a conflict (`files disagree`). It is now
  `outdated`, and `apply` upgrades the library file by file; a file with local
  edits stops the run before anything is written and is merged by hand.
- **Create release PR** wrote `### New` or `### Fixed` twice into the release
  notes when the `[Unreleased]` section carried a heading twice, as after
  merging two branches that each added the section skeleton. It now merges them
  into one subsection each; `workflow-lib` moves to v4 for this.
- Rewriting `.github/repo-infra.json` kept only `publish`, `build`, `skip`
  and `answers`, so a repository's `ci` and `publish_local` choices and any
  `_comment` were dropped from the file. Every key the rewrite does not compute
  is now kept as written. Nothing calls the rewrite yet, so no repository has
  lost a setting.
- Re-running "Create release PR" for a version whose branch still exists no
  longer fails with `Reference already exists`. It happened after a release PR
  was closed without deleting its branch, and after a run that committed before
  it could open the PR; the only way forward was deleting the branch by hand.
  The run now moves the existing branch to its new commit.
- A release can no longer be published with its artifacts missing. `finalize`
  flipped a release from draft to public on the strength of its `needs:` list
  alone, and that list is a generated line: a repository that had hand-added
  its own publish job to it -- the only way there was -- lost the edit at the
  next `apply`, and the revert did not fail. It simply stopped waiting. The
  release went public while the `.deb` was still building, or after that job
  had failed, and nothing anywhere went red; the first anyone knew was an
  operator downloading a release that had no package on it. Two changes, and
  both are needed. A repository's own publish job is now **declared**, in a new
  `publish_local` list in `.github/repo-infra.json`, so the `needs:` entry is
  generated and `apply` restores it instead of removing it. And `finalize` no
  longer trusts ordering at all: it lists the release's assets and asserts the
  ones the installed publish blocks say they attach, before it publishes
  anything. Ordering cannot report its own absence; an assertion cannot pass
  while being wrong. Missing assets now fail the job and leave the release a
  draft, which is the recoverable state. The matching logic is the new
  `assets.js` in the workflow library rather than text inside the `script:`
  block, so it is tested. `release-publish` is v3 and `workflow-lib` is v3:
  re-apply both, and if your repository hand-edits `finalize`'s `needs:`, move
  that job into `publish_local` and take the generated line.
- A failed release attempt no longer makes its commit permanently
  unreleasable. The release guard ignored only the current run's check runs,
  so the failed check run an aborted attempt leaves behind was read as a
  failing check by every later attempt -- and check runs cannot be deleted, so
  no retry on that commit could ever succeed. `oetiker/smalti` lost its whole
  first release to this. `release-pr` v2 gathers the ids through the new
  `checks.js:guardIgnoreIds`, which covers every run of the workflow on the
  commit; the logic moved out of the `script:` block because inline, nothing
  could test it.
- `apply` can enable required checks on a repository that already has a `main`
  ruleset. It could only create one, and GitHub rejects a duplicate name with
  422 -- so the repositories most likely to be converted, the protected ones,
  were the ones it could not finish.
- `apply` installs every file of a directory asset. It wrote only the first,
  so a fresh conversion installed one file of the workflow library and the
  next `check` reported `files disagree` on work that had just succeeded.

## 0.1.0 - 2026-08-19
### New
- `changes.js`: parse, roll and extract release notes from `CHANGES.md`, with the
  roller validating the file's shape before it writes. The previous implementations
  were single regexes that produced nothing at all on an unexpected shape, and
  "nothing" is indistinguishable from "no changes to release".
- `bump.js`: the generic version-file writer. Every write is located, rewritten and
  then read back and asserted, so a bump that does not take fails the release
  rather than tagging a repository whose files disagree with each other.
- `checks.js`: reads every check run on a commit rather than polling one named
  workflow, so the release guard keeps working when a repository names its CI
  something else. Zero checks counts as a failure, not a pass.
- `commit.js`: creates the release commit and branch through the Git Data API, so
  no workflow needs a git identity or push access to a branch.
- A changelog gate on every pull request. It compares the `[Unreleased]` block at
  base and head, so editing an old released section does not satisfy it. It is a
  required check, so `release/*` branches and the `no-changelog` label are the
  deliberate escape hatches — both job-level, so an exempt pull request skips the
  job and the required check goes green on its own.
- **Create release PR**: computes the next version from the tags, rolls
  `CHANGES.md`, sets every declared version file and opens a `release/vX.Y.Z` pull
  request. It refuses to run when no check has reported on the commit, because a
  release of untested code is exactly what the guard exists to prevent.
- **Publish release**: reads the released version back out of `CHANGES.md`,
  refuses to tag when any version file disagrees, creates an annotated tag and
  publishes the release. It exposes `version`, `tag` and `release_id` as job
  outputs — the seam that per-language publish add-ons will attach to.
- `RELEASING.md` documenting the two-step release and, more importantly, why each
  of its unusual parts is the way it is.

### Fixed
- The release guard waited for its own job. It polls every check run on the
  commit, and its own job is one of them, so it timed out after 15 minutes
  reporting `Still running: Prepare the release pull request`. `checkState` and
  `waitForChecks` now take `ignoreCheckRunIds`, and the guard passes its own
  run's job ids.
- The release workflows named their file-access object `io`, which is also the
  name `actions/github-script` injects into every `script:` block. The step died
  at parse time with `SyntaxError: Identifier 'io' has already been declared`,
  before running a line. It is now `fileIO`.
