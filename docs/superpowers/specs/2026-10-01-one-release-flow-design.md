# repo-infra: one release flow, tested before the merge

Date: 2026-10-01
Extends: `2026-09-29-mdmost-conversion-design.md` (D24 to D27), D15's
assembled `ci.yml`, D20's fixed-path reusable workflow, D21's publish seam
Supersedes: D26's opt-in `release_build` variant, D26's "Tagging the built
commit" rule that `main` may move under an open release pull request,
`publish-source-tarball`
Proved in: the spike repository `oetiker/repo-infra-spike` (zero-click merge,
stale guard, up-to-date rule, 2026-09-30 and 2026-10-01). Proofs 2 to 4 below
run before this document's pull request merges; proof 1 runs after it.

This document adds D28. It came out of releasing `oetiker/mdmost` v0.5.0 and
v0.6.0 on D26. D26 already builds the release before the merge and publishes
what it built. Releasing still meant three waits: the dispatch guard waits for
the CI run on `main`, the release pull request's `pull_request` runs park at
**Approve workflows to run**, and after the click the full CI runs again on a
commit the release workflow had just built. D28 removes the click and both
waits, and the variant.

## D28: every release is built and tested before the merge

### The flow

There is one `Create release PR` workflow for every repository. The
`release-pr-build` asset and the boolean `release_build` key go away.

1. **Create release PR** (dispatched by hand) runs four jobs:
   - `prepare`: the guard, the refusals (a release pull request is open; the
     latest release in `CHANGES.md` has no tag), the removal of stale drafts
     and of the parked runs of abandoned release branches, the roll, the
     version bump and the commit of `release/vX.Y.Z`. Outputs `version`,
     `date`, `head` and `base`, the dispatched `main` commit.
   - `build`: calls `.github/workflows/release-build.yml` with `version` and
     `ref: head`.
   - `test`: calls `.github/workflows/ci.yml` with `ref: head`. It runs in
     parallel with `build`.
   - `finish`: needs `prepare`, `build` and `test`. It checks and commits the
     `release_files`, checks the assets against `release_assets`, creates the
     draft release with every asset and `release-build.json`
     (`{version, base, head, assets}`), sets the commit status `release-built`
     on the head, creates the check run `changelog-updated` (success) on the
     head and opens the pull request. Then it compares the head with `main`
     and creates the check run `ci-passed`: success when the branch is not
     behind `main`, failure with the stale message (below) when `main` moved
     after `base`. The pull request is opened before this comparison, so a
     release that went stale while it built is visible and says why.
2. **The release pull request** can be merged at once. The ruleset requires
   `ci-passed` and `changelog-updated` by context only, without an app, so the
   check runs from `finish` satisfy it. Its own `pull_request` runs still park;
   nobody needs to approve them.
3. **Publish** (`release-publish.yml`, on the push of `CHANGES.md` to `main`)
   reads `release-build.json` from the draft, compares trees (below), tags the
   recorded head, runs the publish add-ons and `publish_local`, makes the
   release public, and deletes the parked runs of the release branch.

The commit `finish` adds on top of the tested head changes only the paths
listed in `release_files`, which `check` reviews. A Homebrew formula is Ruby,
so these files can be code; `finish` refuses `.github/`, `CHANGES.md`, the
version files and non-UTF-8 content, nothing else.

### The guard no longer waits

The guard on the dispatched `main` commit refuses when a check run there has
already failed, naming it. It does not wait for running checks and does not
refuse a commit without checks: the `test` job runs the same `ci.yml` on
`main` plus the release changes, and `finish` only opens a pull request when
that run is green. `guardIgnoreIds` stays, because the `build` and `test` jobs
of an earlier failed attempt leave failed check runs on that same commit.

### `main` must not move under a release

A release built from `main` at X must not be merged after another pull request
moved `main` to Y; it is abandoned and dispatched again. Three layers enforce
this.

- **The ruleset.** `ruleset-main.json` sets
  `strict_required_status_checks_policy: true`. GitHub then refuses to merge
  any pull request into the default branch whose head is behind it, checked at
  the moment of the merge. In the spike, release PR #5 had both required checks
  green and was refused with `the head branch is not up to date with the base
  branch`. The rule applies to every pull request into the default branch: an
  ordinary pull request that is behind needs **Update branch** and a new CI
  run before it merges. Pull requests into other branches are not affected.
  On the release pull request, **Update branch** creates a head without
  `release-built`, so its checks go red (below); the only way on is to close
  it and dispatch again.
- **`release-pr-current`**, a new job in `ci.yml` that runs on `push` to `main`
  only (when `ci.yml` is called from `Create release PR` the event is
  `workflow_dispatch`, and the job skips). For each open release pull request
  that is behind `main`, it creates a failed check run `ci-passed` on its head
  with the summary
  `main moved after vX.Y.Z was built; close this pull request and dispatch Create release PR again`.
  The ruleset already blocks the merge; this check says why, where GitHub
  alone offers the **Update branch** button. The job never fails itself: an
  API error is a warning. A failed job would be a failed check run on the
  `main` commit, and the guard would refuse the next dispatch from it. Needs
  `checks: write` and `pull-requests: read`.
- **Publish compares trees** in its `create` path only, before it tags; never
  in `resume` or `done`. It finds the release pull request through
  `listPullRequestsAssociatedWithCommit` on the recorded head and compares the
  tree of that pull request's `merge_commit_sha` with the tree of the recorded
  head. Not `context.sha`: a failed first publish followed by an ordinary
  merge that edits `[Unreleased]` starts a new run on a later commit. With the
  ruleset in place a mismatch means an assumption broke, for example the rule
  was switched off. Publish then fails with
  `main at <sha> does not match the release built from <head>; merge a pull request that moves the vX.Y.Z entries in CHANGES.md back under [Unreleased], then dispatch Create release PR again`,
  and tags and publishes nothing. The version files may stay as they are: the
  next dispatch computes the version from the tags and sets every file again.

The dispatch refusal for an untagged release gets the same correction. Its
text no longer starts with "Re-run the failed jobs"; it says a re-run helps
only when publish failed for another reason than the tree comparison.

### `ci.yml` is also a reusable workflow

The frame gets a third trigger:

    workflow_call:
      inputs:
        ref:
          type: string
          required: false
          default: ''

Every CI fragment checks out `ref: ${{ inputs.ref }}`. On `push` and
`pull_request` the input is empty and `actions/checkout` uses its default
commit, so ordinary runs do not change. The two jobs that call a
project-owned workflow, `ci-local` (`ci-local.yml`) and `action-test`
(`action-test.yml`), pass the input on, and both files must declare it and use
it in every `actions/checkout`.

A called workflow cannot ask for more permissions than its caller grants, and
GitHub checks every job of the called file, skipped or not. The `test` job
therefore grants the union of what `ci.yml`'s jobs request: `contents: read`,
`pull-requests: read`, `statuses: read`, `checks: write`. The workflow-level
`permissions` in `ci.yml` stay `contents: read`; `ci-passed` and
`release-pr-current` raise their own.

### Release mode of the required checks

`ci-passed` (in `ci.yml`) and `changelog-updated` (in `changelog.yml`) get a
release mode. It applies to a pull request that `isReleasePr` recognises: from
a `release/*` branch of this repository, opened by `github-actions[bot]`. A
fork's `release/x` gets the ordinary rules. In release mode the job does not
look at test results. It fails unless both hold:

- The head carries the `release-built` status. `finish` sets it on exactly the
  head it built and tested; a push to the branch makes a new head without it.
- The branch is not behind `main` (`compareCommits(main, head).behind_by`
  is 0).

The status is the proof because `release-build.json` is not readable here: a
token without push access does not see draft releases.

Both jobs check out `pr.base.sha` into a separate directory and load `lib/`
from there; `ci-passed` gets the checkout and Node setup it does not have
today. A `pull_request` run takes the workflow file itself from the merge
commit, so this does not stop someone with write access from changing their
own gate. It stops a release branch that was changed by accident, for example
by **Update branch**, from passing on library code it changed itself.

Nobody needs these runs. They exist for the case where someone approves the
parked runs anyway, or presses **Update branch** (a user event, so the runs
start without approval). In both cases the answer must agree with
`release-pr-current`, or an approved green run would replace its red check.
The spike showed that it does: after the approval, the release pull request
stayed `BLOCKED`.

### `release-build.yml` is assembled

Every repository needs a `release-build.yml`, because `Create release PR`
calls it unconditionally. It is assembled like `ci.yml` and
`release-publish.yml`:

| | CI | Release build | Publish |
|---|---|---|---|
| Managed file | `ci.yml` | `release-build.yml` | `release-publish.yml` |
| Add-ons | `"ci": [...]` | `"release_build": [...]` | `"publish": [...]` |
| Project jobs | `ci_local`: `ci-local.yml` | `release_build_local`: `release-build-local.yml` | `publish_local` |

- The frame triggers on `workflow_call` with the inputs `version` and `ref`,
  has `contents: read`, and carries one job that only prints the version. A
  repository with nothing to build gets a valid file and a release without
  assets.
- `release-source-tarball` is the first add-on: `./bootstrap`, `./configure`,
  `make dist` at `ref`, and the tarball uploaded as the artifact
  `release-asset-source`. The steps are those of `publish-source-tarball`,
  which is deleted. Detection proposes it for `perl-autotools`.
- Build add-ons declare `assets` in the manifest, as publish add-ons do today;
  `release-source-tarball` declares `*.tar.gz`. `finish` is a copied file and
  cannot know which add-ons are installed, so the patterns go into
  `release_assets`: `check` reports a `conflict` when an installed add-on's
  pattern is missing there, and `apply` adds it.
- `release-build-local.yml` has the contract mdmost's `release-build.yml` has
  today: `workflow_call` with `version` and `ref`, files to ship uploaded as
  `release-asset-*` artifacts, rewritten repository files as the artifact
  `release-files`.
- `release_assets` and `release_files` keep their meaning and their checks in
  `finish`.
- `build` and `test` run in the same workflow run and share one artifact
  namespace. `release-asset-*` and `release-files` are reserved for the build;
  `references/conventions.md` says so, and `check` reports a `conflict` when
  `ci-local.yml` or `action-test.yml` uploads an artifact with such a name.

### Secrets

`build` and `test` call their workflows with `secrets: inherit`, and so do the
nested `ci-local`, `action-test` and `release-build-local` jobs. A build that
signs a binary needs its key. The nested CI jobs also run on every
`pull_request` from a branch of the repository, so the project's own CI code
on those branches sees the secrets too; it already did for workflows that read
them directly. The build keeps `contents: read`, so it cannot write the
repository with `GITHUB_TOKEN`, and `finish` still checks `release-files`.

The remaining rule: no repository secret may carry write access to the
repository. A classic personal access token with `repo` scope, typical for
pushing to a Homebrew tap, breaks it. The rule goes into
`references/conventions.md`, `RELEASING.md` and the body of every `apply`
pull request that installs this flow.

### Permissions

- `release-pr.yml`: `prepare` gets `actions: write` for deleting parked runs,
  and `finish` gets `checks: write` for the two check runs; the workflow level
  keeps `checks: read` and `actions: read` for the guard.
- `release-publish.yml`: `actions: write` for deleting the parked runs.
- `ci.yml`: see above.

### Removed

- The `release-pr-build` asset, its `variant_of`/`when` selection and the
  `outdated (variant switch)` handling in `check` and `apply`.
- The boolean form of `release_build`.
- `publish-source-tarball`.
- The contract check `gitea-packages-build` ("needs release_build"): every
  repository now builds before the merge. The contract check `release-build`
  becomes `release-build-local`, on `release_build_local` and
  `release-build-local.yml`.
- Every "without `release_build`" path in the publish frame, in
  `changelog.yml` and in the docs, including the recovery note that a
  whole-workflow re-run skips once the tag exists.
- The guard's wait for running checks and its refusal of a commit without
  checks.
- The "Reconcile Cargo.lock with the bumped version" step in
  `publish-crates-io`. The release pull request bumps `Cargo.lock` through
  `version_files` since `6424bef`. A Rust repository whose `version_files`
  lacks the `Cargo.lock` entries for its crates gets them from `apply`
  (detection's `cargo_lock` flag); `check` reports their absence.
- The approval-banner section of `RELEASING.md` and `release-flow.md`.

## Failure paths

| Event | Result |
|---|---|
| A check on the dispatched `main` commit already failed | The guard refuses, naming it. |
| `build` or `test` fails | No pull request, no draft. The next dispatch force-moves `release/vX.Y.Z`. |
| `main` moves while `build` and `test` run | `finish` opens the pull request with a red `ci-passed` and the stale message. Close it, dispatch again. |
| `main` moves while the release pull request is open | The ruleset refuses the merge; `release-pr-current` adds the red `ci-passed` with the message. Close it, dispatch again; the next dispatch deletes the old draft and the parked runs. |
| Tree mismatch in publish | Only when the up-to-date rule is off. Publish tags nothing and names the abandon pull request; the dispatch refusal for the untagged version says the same. |
| **Update branch** on the release pull request | The new head has no `release-built` status; `ci-passed` and `changelog-updated` go red. |
| Parked runs approved | Same verdict as `release-pr-current`. |
| A publish add-on fails | **Re-run failed jobs** or a whole-workflow re-run finishes the release, as with D26. |
| Release pull request closed | The draft and the parked runs stay until the next dispatch deletes them. |
| Deleting parked runs fails | A warning. |

## Migration

D24 to D27 are not released, so D28 lands on the same branch, and the
`release-pr-build` asset and the boolean `release_build` never ship. Only
`oetiker/mdmost` runs the standard officially; its `apply` upgrade after the
release is the migration that matters.

`check` and `apply` refuse to migrate a repository while a release is in
progress: while a release pull request is open, or while the latest version in
`CHANGES.md` has no tag. The new publish expects a draft with
`release-build.json` and the new release mode expects `release-built`, which
an old release has neither of.

| Item | `check` / `apply` |
|---|---|
| `release-pr.yml`, `changelog.yml`, `ci.yml` frame, every CI fragment, publish frame, `publish-crates-io` | Version bump; ordinary three-way upgrade. |
| Ruleset `main` | `strict_required_status_checks_policy` becomes `true`; the existing ruleset item reports and applies it. |
| `release-build.yml` without a marker and `"release_build": true` | Recognised as D26's project-owned build, not as an unmanaged file. `apply` renames it to `release-build-local.yml` with `git mv` and no content change, sets `release_build_local`, and installs the assembled `release-build.yml`. This rename is the only edit `apply` makes to a project-owned file. |
| `"release_build": true` | Rewritten to `"release_build": []`. |
| `"publish": ["publish-source-tarball"]` | Moved to `"release_build": ["release-source-tarball"]`, and `*.tar.gz` added to `release_assets`. |
| `version_files` without the `Cargo.lock` entries of a Rust repository | Added by `apply`. |
| `ci-local.yml`, `action-test.yml`, `release-build-local.yml` without an input `ref`, or with an `actions/checkout` that does not use it | `conflict`, naming the file and what is missing. `apply` does not edit these files; the upgrade pull request says what to add. |
| mdmost's `release-pr.yml` (marker `release-pr-build v1`, never released) | Replaced whole in mdmost's upgrade pull request. No alias for the unreleased marker. |

The crates.io Trusted Publisher pin is untouched: publishing stays in
`release-publish.yml`.

## Tests

- Node, `workflows/lib`: release-mode verdict (bot, branch, repository,
  status, behind count); `finish`'s stale verdict; selection of stale release
  pull requests; the guard's verdict without waiting; finding the release pull
  request's merge commit and the tree comparison; selection of parked runs to
  delete, after a merge and for closed release branches; the corrected
  untagged-release message.
- Python: assembly of `release-build.yml` with and without add-ons and the
  local seam; every CI fragment checks out `inputs.ref`; every `uses: ./` job
  in `ci.yml` and `release-build.yml` passes `ref` and `secrets: inherit`; the
  seam checks (declared input, used in every checkout, no reserved artifact
  name); add-on asset patterns against `release_assets`; every migration item
  above, including the refusal during a release; the deleted variant code has
  no remaining callers.

## Proof

1. After the merge: repo-infra applies the new flow to itself and releases
   through it. Empty `release-build.yml`, no approval click.
2. `oetiker/repo-infra-spike` with a minimal autotools project
   (`configure.ac`, `Makefile.am`): one release carries the `make dist`
   tarball in the draft and in the published release.
3. mdmost, after its `apply` upgrade pull request:
   - a release merges without an approval click; the tag sits on the recorded
     head; the Gitea upload and the Homebrew bottle work as in v0.5.0; the
     parked runs of the release branch are gone afterwards;
   - an unrelated pull request merges while the release pull request is open:
     the release pull request is refused by the ruleset and shows the red
     `ci-passed` with the message; close, dispatch again, release;
   - an unrelated pull request merges while `build` runs: `finish` opens the
     pull request red;
   - with the up-to-date rule switched off for the test, a release pull
     request merged after `main` moved: publish fails on the tree comparison,
     tags nothing, and names the abandon pull request; after it, a dispatch
     releases. The rule is switched on again afterwards.
4. The open D26/D27 items of mdmost #26 carry over where they still apply:
   **Update branch** goes red; dispatch refused while a release pull request
   is open and while a merged release is unpublished; publish failing after
   the tag finishes on **Re-run failed jobs**; `finish` refuses a missing
   `release_assets` file; Gitea re-run reports the 409s and stays green; a
   `~` version installs through apt; `brew install` pours the bottle. The
   item "a PR merged into main while the release PR is open does not stop the
   release" is reversed by D28, and the variant-switch item is dropped with
   the variant.

## Not decided here

- Removing the parked runs at the source. A workflow cannot filter
  `pull_request` by author at the workflow level, so they are cleaned up
  afterwards instead.
- A merge queue. It would serialise merges without the **Update branch**
  click, but GitHub offers it only for repositories owned by an organisation,
  and mdmost is not.
- Converting further repositories (SmokePing for `release-source-tarball`,
  smalti, mkp-builder, smtp-proxy-rs).
