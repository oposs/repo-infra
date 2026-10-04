# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
except that the first subsection is called `New` rather than `Added`. The release
workflow matches on `### New`; renaming it silently drops the section from the
release notes.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### New

### Changed

### Fixed

## 1.0.0 - 2026-10-04
### Changed
- `check` no longer stops with "the standard does not recognise this repository": it reports every installed piece as `current`, `outdated`, `edited` or `unknown`, checks the repository's own `ci.yml`, `release-build.yml` and `release-publish.yml` against the pieces they call, and lists the administration items. A repository picks its pieces from the catalogue in the skill and calls them from these files.
- The workflows repo-infra ships are now separate files named `ri-*.yml` that the repository calls; `ci.yml`, `release-build.yml` and `release-publish.yml` are no longer generated and belong to the repository. A repository on the generated files sees `unknown` for them in `check` until they are rewritten (see `references/onboarding.md` in the skill).
- `apply` replaces outdated pieces, installs missing core pieces and the pieces they need, and removes files a newer version no longer ships, one commit per piece named `Install <piece> vN from the repo-infra standard`. It then prints the upgrade notes of every version it crossed and what the callers must change, and stops.
- `apply` refuses to install any piece (`release-in-progress`) while a release pull request is open or the latest released version in `CHANGES.md` has no tag yet.
- Branch protection, the `no-changelog` label and the Actions setting are applied only when named with `apply --item`.
- A piece with a local edit that still carries the current version used to read `ok`; `check` now reads it `edited` and exits 1. It says how to get back to the published file: move the change into a caller, delete the file and run `apply --item <piece>`.
- `apply` no longer prints "already vN" for a piece whose file carries a local edit and claims the current or a newer version. It prints what `check` says about it: the way back to the published file, or "update the plugin" when the file is newer than the plugin.
- When `apply` stops for a hand merge or refuses, it prints the message (`NeedsMerge: ...`, exit status 3, or `refused: ...`, exit status 1) instead of a Python traceback.
- When a `gh` call fails or the plugin's files are damaged, `check` and `apply` print the message (`gh: ...` or `the plugin's asset store is broken ...`) and exit 1 instead of a Python traceback. `apply` refuses a misspelt piece name or a misplaced `--from` before it contacts GitHub.
- `apply` no longer appends ` sha256=` to the marker line of the files it writes. Files that carry it from v0.3.1 still read as the version they claim.
- Commits made by `apply` end with `Co-Authored-By: Claude <noreply@anthropic.com>` instead of naming a model version.
- `.github/repo-infra.json` no longer reads `ecosystems`, `ci`, `ci_local`, `publish`, `build`, `publish_local`, `release_build`, `release_build_local`, `skip` or `answers`; `check` asks for them to be removed.

### Fixed
- `check` reports a call that would fail at the start of a run: an input or secret the called workflow does not declare or requires, a missing workflow file, or a job that grants fewer token permissions than the workflow it calls needs.
- `check` reports a caller that would misbehave once it runs: a `ci-passed` job that differs from the shipped pattern, a `finalize` that does not need every other job, a `finalize` without `if: needs.publish.outputs.release_id != ''` (the Publish run turns red after every merge that releases nothing) or wired to the wrong outputs, a call to a workflow in another repository, and a call that does not hand `ref: ${{ inputs.ref }}` to a workflow taking it.
- `check` reports a `ci.yml` that does not run on `push` and `pull_request` to `main` or does not call `ri-release-pr-current`, and a `release-publish.yml` that does not run on `push` to `main` with `paths: [CHANGES.md]` alone, lacks the `release-publish` concurrency group, cancels a running publish or has a `workflow_dispatch` trigger.
- `check` reports an installed workflow piece that no workflow calls, such as `ri-ci-python.yml` left behind when its job was removed from `ci.yml`.
- `apply` replaces the files a repository got from repo-infra v0.2.0 (`changelog` v2, `release-pr` v3, `workflow-lib` v4, `container` v1) instead of stopping for a hand merge of each one; `check` reads them `outdated`. Copies of `changelog.yml` and `release-pr.yml` taken from v0.1.0 read `outdated` as well.

## 0.3.1 - 2026-10-02
### Fixed
- `apply` with the installed plugin no longer stops on every changed workflow file with "local edits present": files it writes end their `# repo-infra:` line in ` sha256=...`, which must not be edited, and an unedited file is upgraded in place. A file from an earlier version stops once, for the `apply` skill to check its git log for local edits; handed back without edits, it gets the suffix and is committed as `Install <item> from the repo-infra standard`. A file with local edits is committed as `Merge <item> from the repo-infra standard with local edits` and stops again at the next upgrade.
- `apply` keeps short lists in `.github/repo-infra.json` on one line, such as `"ci": ["ci-man", "ci-rust-musl"]`, instead of rewriting the file one value per line.

## 0.3.0 - 2026-10-02
### New
- **Create release PR** builds the release and runs the CI on the release branch before it opens the pull request, and writes the required checks itself, so the pull request can merge at once. The **Approve workflows to run** banner still appears on it, but nobody needs to approve those runs: publishing deletes them, and the next **Create release PR** deletes those of a closed release pull request.
- `.github/workflows/release-build.yml` is now installed and kept up to date by `apply` in every repository. It runs the build add-ons listed in `release_build`, and with `"release_build_local": true` also the project's own `.github/workflows/release-build-local.yml`; files such as a Homebrew formula change in the pull request, and publishing tags the commit that was built.
- The `release-source-tarball` build add-on attaches the `make dist` tarball, built before the merge. It replaces the `publish-source-tarball` publish add-on, and `apply` moves the setting.
- A Rust workspace can list which crates `ci-rust` lints and which it tests, in a `rust` key of `.github/repo-infra.json`; each crate gets its own check. A workspace where a plain `cargo test` would skip some crates now fails the `Rust workspace plan` check until the key says where their tests run.
- `"ci_local": true` makes the jobs in `.github/workflows/ci-local.yml` part of the required `ci-passed` check.
- The `publish-gitea-packages` add-on uploads a release's `.deb` and `.rpm` files to a Gitea package registry, which signs them; the release stays a draft until the upload succeeded.

### Changed
- The branch ruleset now requires a pull request to be up to date with `main` before it merges; behind pull requests need **Update branch** first, and `check` reports `required-checks` as outdated until `apply` writes the rule. A release pull request that `main` moved past cannot merge and shows a red `ci-passed`: "main moved after vX.Y.Z was built; close this pull request and dispatch Create release PR again".
- **Update branch** on a release pull request turns `ci-passed` and `changelog-updated` red with "the release branch changed after it was built (the Update branch button does this); close this pull request and dispatch Create release PR again".
- `Create release PR` no longer waits for the checks on `main`; it refuses only a check that already failed. It also refuses while a release pull request is open or while the latest release in `CHANGES.md` has no tag.
- Publish refuses to tag when `main` does not match the release that was built: "main at <sha> does not match the release built from <head>; merge a pull request that moves the vX.Y.Z entries in CHANGES.md back under [Unreleased], then dispatch Create release PR again".
- Publish refuses to tag when it finds no merged release pull request for the version: "vX.Y.Z: no merged release pull request from release/vX.Y.Z, so publish cannot compare main with the release that was built. Nothing was tagged."
- Re-running the publish workflow no longer fails on a crate an earlier attempt already uploaded, and both **Re-run failed jobs** and a whole-workflow re-run finish a stopped release.
- Publishing to crates.io uses the `Cargo.lock` of the release pull request as it is (`cargo publish --locked`) and no longer runs `cargo update --workspace` first. For a Rust repository whose `version_files` lacks the `Cargo.lock` entries, `check` reports `cargo-lock-version-files` and `apply` adds them.
- `apply` refuses with `release-in-progress` while a release pull request is open or the latest release in `CHANGES.md` has no tag. Merge and publish that release, or close it, then run `apply` again; `apply --item` still applies administration items and files outside the release workflows.
- The release build and the CI run get the repository's secrets. No repository secret may carry write access to the repository.
- `check` reports `ci-local.yml`, `action-test.yml` and `release-build-local.yml` as a conflict when they do not declare the input `ref` or do not check it out. It also reports `ci-local.yml` and `action-test.yml` when they upload an artifact named `release-asset-*` or `release-files` in any letter case, names the release build keeps for itself.
- `check` reports `container` as outdated; only a comment in `build/container.mk` changed.

### Fixed
- `apply` without `--item` no longer stops with "git commit -m Install ci-lib from the repo-infra standard ... failed" when a workflow file has more than one block to install, as `ci.yml` and `release-build.yml` do. The first item writes the whole file; each further block of that file is reported as "installed with" that item instead of getting a commit of its own.
- `changelog-updated` applies the changelog rules of `main`; a pull request that edits `.github/workflows/lib/changes.js` no longer decides its own verdict. The pull request that first installs the workflow library still uses its own copy, since `main` has none yet.
- When a git command that `apply` runs fails, the error now includes what git printed on standard output, such as "nothing to commit". Before, those messages ended after "failed:".
- When `apply` first writes `.github/repo-infra.json` for a Rust repository with a `Cargo.lock`, `version_files` now lists `Cargo.lock` too: one entry for the main crate and one for each workspace crate with `version.workspace = true`. Before, the release pull request left `Cargo.lock` at the old version unless someone added the entry by hand.
- `apply` works in a linked git worktree. It stopped there with `NotADirectoryError` when it installed the branch ruleset or prepared a merge of a locally edited file.
- The changelog check no longer fails with "CHANGES.md has no '## [Unreleased]' heading" on the pull request that introduces that heading. A pull request that removes the heading fails with a message naming it.

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
