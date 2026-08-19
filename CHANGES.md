# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
except that the first subsection is called `New` rather than `Added`. The release
workflow matches on `### New`; renaming it silently drops the section from the
release notes.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### New
- The plugin ships the release workflows as versioned, installable assets.
- The plugin can read and write asset version markers.

### Changed

- The release system is proven end to end: `v0.1.0` was cut by dispatching
  **Create release PR**, merging the pull request it opened, and letting the
  publish workflow tag and publish. The one manual step is the deliberate
  **Approve workflows to run** click on the release pull request, which exists so
  that no credential has to be stored; `RELEASING.md` explains why.

### Fixed

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
