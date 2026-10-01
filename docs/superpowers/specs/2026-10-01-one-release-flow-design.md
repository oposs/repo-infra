# repo-infra: one release flow, tested before the merge

Date: 2026-10-01
Extends: `2026-09-29-mdmost-conversion-design.md` (D24 to D27), D15's
assembled `ci.yml`, D20's fixed-path reusable workflow, D21's publish seam
Supersedes: D26's opt-in `release_build` variant, `publish-source-tarball`
Proved in: the spike repository `oetiker/repo-infra-spike` (zero-click merge
and stale guard, 2026-09-30); the rest before this document's pull request
merges (see "Proof").

This document adds D28. It came out of releasing `oetiker/mdmost` v0.5.0 and
v0.6.0 on D26. D26 already builds the release before the merge and publishes
what it built. The release pull request was still slow: its `pull_request`
runs park at **Approve workflows to run**, and after the click the full CI runs
again on a commit the release workflow had just built. D28 removes the click,
the second CI run and the variant.

## D28: every release is built and tested before the merge

### The flow

There is one `Create release PR` workflow for every repository. The
`release-pr-build` asset and the boolean `release_build` key go away.

1. **Create release PR** (dispatched by hand) runs four jobs:
   - `prepare`: the guard (every check on the dispatched `main` commit is
     green), the refusals (a release pull request is open; the latest release
     in `CHANGES.md` has no tag), the removal of stale drafts, the roll, the
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
     on the head, creates the check runs `ci-passed` and `changelog-updated`
     (conclusion success) on the head, and then opens the pull request.
2. **The release pull request** can be merged at once. The ruleset requires
   `ci-passed` and `changelog-updated` by context only, without an app, so the
   check runs from `finish` satisfy it. Its own `pull_request` runs still park;
   nobody needs to approve them.
3. **Publish** (`release-publish.yml`, on the push of `CHANGES.md` to `main`)
   reads `release-build.json` from the draft, compares trees (below), tags the
   recorded head, runs the publish add-ons and `publish_local`, makes the
   release public, and deletes the parked runs of the release branch.

The commit `finish` adds on top of the tested head carries only the
`release_files` (for example the Homebrew formula). `finish` already refuses
anything under `.github/`, `CHANGES.md`, a version file and non-UTF-8 content
there, so the difference between the tested and the released commit is data,
not code.

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
commit, so ordinary runs do not change. The `ci-local` job passes the input
on, and `ci-local.yml` must declare it.

A called workflow cannot ask for more permissions than its caller grants, and
GitHub checks every job of the called file, skipped or not. The `test` job
therefore grants the union of what `ci.yml`'s jobs request: `contents: read`,
`pull-requests: read`, `statuses: read`, `checks: write`. The workflow-level
`permissions` in `ci.yml` stay `contents: read`; the two jobs below raise their
own.

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
token without push access does not see draft releases. The library code the
check runs comes from the base commit, never from the pull request, so a
pull request cannot turn its own gate off. This is how `changelog.yml` reads
its config today.

Nobody needs these runs. They exist for the case where someone approves the
parked runs anyway, or presses **Update branch** (a user event, so the runs
start without approval). In both cases the answer must agree with the guard
below, or an approved green run would replace its red check. The spike showed
that it does: after the approval, the release pull request stayed `BLOCKED`.

### The stale guard

A release built from `main` at X must not be merged after another pull
request moved `main` to Y. The guard has two layers.

- `release-pr-current`, a new job in `ci.yml` that runs on `push` to `main`
  only (when `ci.yml` is called from `Create release PR`, the event is
  `workflow_dispatch` and the job skips). It lists open release pull requests
  and, for each one that is behind `main`, creates a failed check run
  `ci-passed` on its head with the summary
  `main moved after vX.Y.Z was built; close this pull request and dispatch Create release PR again`.
  GitHub counts only the newest check run per context, so the pull request is
  blocked. Needs `checks: write` and `pull-requests: read`.
- Publish compares trees before it tags. The tree of the commit that landed on
  `main` must equal the tree of the recorded head. When it does not, publish
  fails with `main at <sha> does not match the release built from <head>`,
  tags nothing and publishes nothing. This catches two merges close enough
  together that the first layer had no time, and it works for merge, squash
  and rebase merges alike. When the trees are equal, the tag on the recorded
  head describes exactly what is on `main`.

D26's proof item "a PR merged into main while the release PR is open does not
stop the release" is reversed by this decision.

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
- `release-build-local.yml` has the contract mdmost's `release-build.yml` has
  today: `workflow_call` with `version` and `ref`, files to ship uploaded as
  `release-asset-*` artifacts, rewritten repository files as the artifact
  `release-files`.
- `release_assets` and `release_files` keep their meaning and their checks in
  `finish`.

### Secrets

`build` and `test` call their workflows with `secrets: inherit`, and so do the
nested `ci-local` and `release-build-local` jobs. A build that signs a binary
needs its key, and CI already runs with the repository's secrets on every push
to `main`. The build keeps `contents: read`, so it cannot write the
repository with `GITHUB_TOKEN`, and `finish` still checks `release-files`.
`RELEASING.md` states the remaining rule: no repository secret may carry write
access to the repository.

### Removed

- The `release-pr-build` asset, its `variant_of`/`when` selection and the
  `outdated (variant switch)` handling in `check` and `apply`.
- The boolean form of `release_build`.
- `publish-source-tarball`.
- Every "without `release_build`" path in the publish frame, in
  `changelog.yml` and in the docs, including the recovery note that a
  whole-workflow re-run skips once the tag exists.
- The "Reconcile Cargo.lock with the bumped version" step in
  `publish-crates-io`. The release pull request bumps `Cargo.lock` through
  `version_files` since `6424bef`, so the step has nothing left to do.
- The approval-banner section of `RELEASING.md` and `release-flow.md`.

## Failure paths

| Event | Result |
|---|---|
| `build` or `test` fails | No pull request, no draft. The next dispatch force-moves `release/vX.Y.Z`. Their check runs sit on the dispatched `main` commit; `guardIgnoreIds` already ignores every job of every run of this workflow there. |
| Another pull request merges first | `release-pr-current` turns the release pull request red. Close it, dispatch again; the next dispatch deletes the old draft as stale. |
| Two merges close together | Publish fails on the tree comparison before tagging. The dispatch refusal for an untagged release names the ways out. |
| **Update branch** | The new head has no `release-built` status; `ci-passed` and `changelog-updated` go red. |
| Parked runs approved | Same verdict as the guard. |
| A publish add-on fails | **Re-run failed jobs** or a whole-workflow re-run finishes the release, as with D26. |
| Release pull request closed | The draft stays until the next dispatch deletes it. |
| Deleting the parked runs fails | A warning. The release is already public. |

## Migration

D24 to D27 are not released, so D28 lands on the same branch, and the
`release-pr-build` asset and the boolean `release_build` never ship. Only
`oetiker/mdmost` runs the standard officially; its `apply` upgrade after the
release is the migration that matters.

| Item | `check` / `apply` |
|---|---|
| `release-pr.yml`, `changelog.yml`, `ci.yml` frame, every CI fragment, publish frame, `publish-crates-io` | Version bump; ordinary three-way upgrade. |
| `release-build.yml` | Created by assembly. A project-owned `release-build.yml` is renamed to `release-build-local.yml` and `release_build_local` is set. |
| `"release_build": true` | Rewritten to the list form. |
| `"publish": ["publish-source-tarball"]` | Moved to `"release_build": ["release-source-tarball"]`. |
| `ci-local.yml`, `release-build-local.yml` without an input `ref` | `conflict`, naming the missing input. `apply` does not edit project-owned files; the upgrade pull request says what to add. |
| mdmost's `release-pr.yml` (marker `release-pr-build v1`, never released) | Replaced whole in mdmost's upgrade pull request. No alias for the unreleased marker. |

The crates.io Trusted Publisher pin is untouched: publishing stays in
`release-publish.yml`.

## Tests

- Node, `workflows/lib`: release-mode verdict (bot, branch, repository,
  status, behind count), selection of stale release pull requests, tree
  comparison verdict, selection of parked runs to delete.
- Python: assembly of `release-build.yml` with and without add-ons and the
  local seam; every CI fragment checks out `inputs.ref`; the migration items
  above in `check` and `apply`; the deleted variant code has no remaining
  callers.

## Proof

1. repo-infra releases this work through its own flow: an empty
   `release-build.yml`, zero-click merge.
2. `oetiker/repo-infra-spike` with a minimal autotools project
   (`configure.ac`, `Makefile.am`): one release carries the `make dist`
   tarball in the draft and in the published release.
3. mdmost, after its `apply` upgrade pull request:
   - a release merges without an approval click; the tag sits on the recorded
     head; the Gitea upload and the Homebrew bottle work as in v0.5.0;
   - the parked runs of the release branch are gone afterwards;
   - stale guard: with a release pull request open, an unrelated pull request
     merges; the release pull request goes red with the message above; close,
     dispatch again, release.
4. The open D26/D27 items of mdmost #26 carry over where they still apply:
   **Update branch** goes red; dispatch refused while a release pull request
   is open and while a merged release is unpublished; publish failing after
   the tag finishes on **Re-run failed jobs**; `finish` refuses a missing
   `release_assets` file; Gitea re-run reports the 409s and stays green; a
   `~` version installs through apt; `brew install` pours the bottle. The
   variant-switch item is dropped with the variant.

## Not decided here

- Removing the parked runs at the source. A workflow cannot filter
  `pull_request` by author at the workflow level, so they are cleaned up
  after the merge instead.
- Converting further repositories (SmokePing for `release-source-tarball`,
  smalti, mkp-builder, smtp-proxy-rs).
