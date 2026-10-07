# Release flow

How a release installed by this plugin actually happens, why the shape is what
it is, and how to recover one that stalls partway. `RELEASING.md` at the
repository root is the same content, written for a human reading it once; this
is the version for a model operating one of these repositories.

## The two steps, and why a push cannot do this

**1. Dispatch `Create release PR`** (bugfix / feature / major). It refuses
when a check on the current `main` commit has already failed, when a release
pull request is open, or when the latest release in `CHANGES.md` has no tag.
Otherwise it computes the next version from the tags (and refuses if that tag
exists), rolls `CHANGES.md`, sets every version file, builds the release
(`release-build.yml`) and runs the repository's CI (`ci.yml`) on the
`release/vX.Y.Z` branch, drafts the release with every built file and opens
the pull request. Nothing is tagged yet; closing the PR cancels the release.

**2. Merge that pull request.** Nothing needs approving. The merge triggers
the publish workflow, which tags the commit that was built and publishes the
draft.

The reason it is two steps and not `git push` from a workflow: `main` is
protected by a ruleset whose `bypass_actors` is empty, and the bypass list only
accepts `User`, `Team`, `Integration`, `OrganizationAdmin`, `RepositoryRole` and
`DeployKey`. `GITHUB_TOKEN` is none of those, so it cannot be added. A pull
request needs no such bypass; it is reviewed and merged by whoever has write
access, the same as any other change. This is a property of the ruleset, not a
missing feature. Do not try to route around it by adding an `on: push` trigger
on the release branch; a push made with `GITHUB_TOKEN` does not fire workflow
triggers either.

## Built and tested before the pull request exists (D28)

`Create release PR` runs four jobs:

- `prepare`: the guard, the refusals (a release pull request is open; the
  latest release in `CHANGES.md` has no tag), the removal of stale drafts and
  of the parked runs of closed release branches, the roll, the version bump
  and the commit of `release/vX.Y.Z`. It outputs `version`, `date`, `head` and
  `base`, the dispatched `main` commit.
- `build`: calls `.github/workflows/release-build.yml` with `version` and
  `ref: head`.
- `test`: calls `.github/workflows/ci.yml` with `ref: head`, in parallel with
  `build`.
- `finish`: needs the other three. It checks and commits the `release_files`,
  checks the assets against `release_assets`, creates the draft release with
  every asset and `release-build.json` (`{version, base, head, assets}`), sets
  the commit status `release-built` on the head, creates the check run
  `changelog-updated` (success) on the head and opens the pull request. Then
  it compares the head with `main` and creates the check run `ci-passed`:
  success when the branch is not behind `main`, failure with the stale message
  below when `main` moved after `base`. The pull request is opened before this
  comparison, so a release that went stale while it built is visible and says
  why.

The ruleset requires `ci-passed` and `changelog-updated` by context only, with
no app (`integration_id`), so the two check runs `finish` writes with
`GITHUB_TOKEN` satisfy it, and the pull request merges at once.

A pull request opened by `GITHUB_TOKEN` still parks its own `pull_request`
runs in an **approval-required** state, shown as a banner in the merge box.
Nobody needs to approve them, and publish deletes them after the release. If
someone approves them anyway, or presses **Update branch** (a user event, so
the runs start without approval), the release mode of `ci-passed` and
`changelog-updated` gives the same verdict as `release-pr-current` below: red
unless the head carries `release-built` and is not behind `main`.
Of `ci.yml`, such a run starts only `ci-passed`; every other job carries the
`if:` of `assets/callers/release-pr-skip.yml` and skips on the release pull
request (D31), so nothing is built or tested a second time.

`main` must not move under a release. A release built from `main` at X is not
merged after another pull request moved `main` to Y; it is abandoned and
dispatched again. Three layers enforce this:

- **The ruleset** sets `strict_required_status_checks_policy: true`. GitHub
  refuses to merge a pull request whose head is behind `main`, with `the head
  branch is not up to date with the base branch`. This applies to every pull
  request into `main`: one that is behind needs **Update branch** and a new CI
  run before it merges.
- **`ri-release-pr-current`**, a piece the repository's `ci.yml` calls. Its job
  runs on every event but does its work on `push` only. For each open release
  pull request that is behind `main`, it creates a failed check run
  `ci-passed` on its head with `main moved after vX.Y.Z was built; close this
  pull request and dispatch Create release PR again`. The
  ruleset already blocks the merge; this check says why. The job never fails
  itself, and an API error is a warning: a failed job is a failed check run on
  the `main` commit, and the guard would refuse the next dispatch from it.
- **Publish compares trees**, in its `create` path only, before it tags;
  never in `resume` or `done`. It finds the release pull request by its branch
  (closed pull requests with head `<owner>:release/vX.Y.Z`, the merged one)
  and compares the tree of its `merge_commit_sha` with the tree of the
  recorded head. It does not look the pull request up from the head commit:
  for a commit off the default branch GitHub lists only open pull requests, so
  a squash or rebase merge would never publish. When no merged release pull
  request is found, or the trees differ, publish tags nothing and fails. A
  mismatch means the up-to-date rule was off at the merge:
  `main at <sha> does not match the release built from <head>; merge a pull request that moves the vX.Y.Z entries in CHANGES.md back under [Unreleased], then dispatch Create release PR again`.

## The guard fails fast, and is not redundant with the required checks

`Create release PR`'s guard reads every check run on the current `main` commit
(`checks.listForRef`) and refuses when one has already failed, naming it:
`Failing checks on this commit: <names>`. It does not wait for running checks
and does not refuse a commit without checks, because the `test` job runs the
same `ci.yml` on that commit plus the release changes, and `finish` opens a
pull request only when that run is green.

This is not standing in for the ruleset's required checks. It runs *before* a
branch, a build or a pull request exists. Without it, a release dispatched
against a `main` with a known failure still rolls the changelog, bumps every
version file, pushes a branch and spends a full build and CI run, only to
fail. The guard turns that into an immediate refusal with nothing to clean up.
Do not remove it because "the ruleset already requires checks": the ruleset
gates the merge; the guard gates the dispatch.

## `ignoreCheckRunIds`: the guard ignores every job of this workflow on its commit

The guard's own job is one of the check runs on the commit it inspects, and
so is every job of every earlier attempt on that commit. Since D28 those
include the `build` and `test` jobs of an earlier dispatch: when they failed,
they left failed check runs on that same `main` commit. A check run's id is
its Actions job id, so the guard reads the job ids off this workflow's runs
and passes them as `ignoreCheckRunIds`. A new job added to `release-pr.yml`
needs no special handling; it is ignored with the rest.

**Every earlier attempt counts, not just the current run.** This is the half
that was missing, and the failure it caused is permanent. A release attempt that
dies for any reason leaves a *failed* check run on that `main` commit. Check
runs cannot be deleted. So a guard that ignored only its own run saw the corpse
of the previous attempt, reported `Failing checks on this commit: Prepare the
release pull request`, and refused, and would refuse every later attempt on
that commit for as long as the repository exists. Deleting the release branch
does not help; the block is attached to the commit. `oetiker/smalti` lost its
entire first release, 0.1.0, to exactly this, and had to push an empty commit to
escape.

`checks.js:guardIgnoreIds` therefore lists **every run of this workflow on this
commit** (through `GITHUB_WORKFLOW_REF`, which needs the `actions: read`
permission) and ignores the jobs of all of them, plus the current run's jobs
unconditionally, because a run that has only just started can be missing from
the listing for a moment. The logic lives in the library rather than inline in
the `script:` block for one reason: inline, nothing could test it, and the
one-run-only rule shipped and stayed shipped.

## GitHub keeps only the latest check run per context

A second check run on the same context replaces the first for merge purposes:
a later run that skips (and so reports Success) clears an earlier failure on
that same context. This is convenient for re-running a fixed check, and a trap
for labelling: adding the `no-changelog` label to a pull request *after* the
changelog check has already failed produces a new, skipped, green run for that
context, and the pull request becomes mergeable, with no changelog entry and
no second look. Apply the label at creation
(`gh pr create --label no-changelog`), not as a fix-up after the fact.

## Recovery: re-run, never re-dispatch

A failed publish run is re-run from the Actions UI (Actions → the failed run →
**Re-run failed jobs**). There is deliberately no `workflow_dispatch` on
`release-publish.yml` (publishing is a consequence of merging a release PR,
not something started from a dropdown), and none is needed for recovery: the
version comes from `CHANGES.md` in the repository, not from run inputs, so a
re-run reads the same version and does exactly what the original attempt would
have done.

Both **Re-run failed jobs** and a whole-workflow re-run finish a stopped
publish. The publish pieces skip what an earlier attempt uploaded:
`ri-publish-crates-io` asks crates.io and publishes only the workspace crates
whose version is not there yet, and `ri-publish-gitea` counts a file Gitea
already holds as uploaded (below). A whole-workflow re-run finishes a stopped
release only when every publish job the repository wrote itself does the
same.

The one failure a re-run cannot fix is the tree comparison. A publish that
failed with `main at <sha> does not match the release built from <head>`
tagged nothing, and every re-run fails the same way. Abandon the release with
a pull request that moves its entries back under `[Unreleased]`, then dispatch
again.

## The `needs:` list of `finalize`

`release-publish.yml` ends with `finalize`, a call of `ri-publish-finalize`.
It makes the draft release public, so it must `needs:` every other job of the
file: a publish job it does not wait for can still be running, or can have
failed, when the release goes public. In the assembled workflow of D28 this
list was generated and a hand edit was silently undone. It is now the
repository's own `needs:` list, and `check` reports a job that `finalize` does
not need. Its input `expected` lists the name patterns the publish jobs attach
(`'["*.crate"]'`, for example), and `finalize` asserts them against the draft
before publishing, because ordering cannot report its own absence and an
assertion can. The same holds for `ci-passed` in `ci.yml`: it needs every other
job, and `check` verifies it.

## What the build may do

`release-build.yml` is a caller the repository owns. It triggers on
`workflow_call` with the inputs `version` and `ref`, has `contents: read` and
calls what the repository builds with:

- build pieces from the catalogue. `ri-release-source-tarball` runs
  `./bootstrap`, `./configure` and `make dist` at `ref` and uploads the tarball
  as the artifact `release-asset-source`.
- the project's own `.github/workflows/release-build-local.yml`, called with
  `version` and `ref`.

A repository with nothing to build has a valid file and a release without
assets. The build uploads the files the release ships as `release-asset-*`
artifacts, and the repository files it rewrote as the artifact
`release-files`; `references/onboarding.md` has the contract.

`finish` checks every asset against `release_assets` and commits the files
listed in `release_files` onto the release branch. It refuses an entry under
`.github/`, `CHANGES.md`, a version file and non-UTF-8 content, after
normalising the path. A Homebrew formula change is part of the pull request
diff, so reviewers see it. `finish` first removes its own earlier drafts for
the same version, including a bot-created draft that a failed upload left
without `release-build.json`.

Publish tags the head recorded in `release-build.json`, not the merge commit.
If that commit does not exist in the repository, publish fails with
`release-build.json names <sha>, which does not exist in this repository`.
A publish job the repository wrote itself checks out
`ref: ${{ needs.publish.outputs.head }}`, the tagged commit, like the publish
pieces do.

Publish also fails on every run while the tag for the newest released version
in `CHANGES.md` exists but has no GitHub release, as after a tag pushed by
hand. It stays red until the next release creates one; other tags are never
looked at.

Between the merge and `finalize` the Homebrew formula on `main` points at
release URLs that answer 404, because the release is still a draft. Usually
that lasts the few minutes publish takes. A failed publish job keeps the release a
draft and `brew install` fails until it is public. Recovery is **Re-run failed
jobs** on the publish run.

`Create release PR` refuses in two cases:

- A release pull request is already open (from a `release/*` branch of this
  repository, opened by `github-actions[bot]`). The message names it.
- The latest release in `CHANGES.md` on `main` has no tag:
  `vX.Y.Z is in CHANGES.md on main but has no tag`. The ways out are
  **Re-run failed jobs** on its publish run, when that run failed for another
  reason than the tree comparison; for a release that is already out under
  another tag, pushing `vX.Y.Z` by hand (the ruleset covers the branch, not
  tags); or, to abandon it, a pull request that moves its entries back under
  `[Unreleased]`.

**Update branch** on a release pull request moves the branch after the build.
The new head carries no `release-built` status, so `ci-passed` and
`changelog-updated` turn red with `the release branch changed after it was
built (the Update branch button does this); close this pull request and
dispatch Create release PR again`, and adding `no-changelog` does not help.
Close the pull request and dispatch `Create release PR` again. The next
dispatch deletes stale drafts (drafts with a `release-build.json` whose tag
does not exist and whose version is not the latest release in `CHANGES.md` on
`main`) and the parked runs of closed release branches.

## Gitea packages (`ri-publish-gitea`)

`release-publish.yml` calls the piece in a job that `needs: [publish]` and
passes `release_id` and `head` from the `publish` job (the catalogue has the
snippet). The job uploads every `.deb` and `.rpm` release asset to a Gitea
package registry, which signs them with its own key. No repository holds a
signing key. The release stays a draft until the upload succeeded, because
`finalize` needs the job. `check` reports a `problem` when a repository calls
the piece and `gitea_packages` lacks `url` or `owner`.

    "gitea_packages": {
      "url": "https://gitea.oetiker.ch",
      "owner": "oposs",
      "debian": {"distribution": "stable", "component": "main"},
      "rpm": {"group": ""}
    }

- `url`, `owner`: the Gitea server and the organisation that owns the
  packages.
- `debian.distribution`, `debian.component`: the channel for `.deb` files.
  The default is `stable` and `main`.
- `rpm.group`: the RPM group. Empty by default.

The job fails when no asset matches. It fails before the first upload when
`GITEA_PACKAGE_TOKEN` or `GITEA_PACKAGE_USER` is empty, naming the missing
one, and when a release carries a `.deb` or `.rpm` whose file name it cannot
parse, naming the file. The expected shapes are `name_version_arch.deb` and
`name-version-release.arch.rpm`.

The credential is the first stored one in the standard:

- A dedicated Gitea user, member of the owner organisation only, in a team
  with package write permission and nothing else.
- Token scope `write:package` only.
- The GitHub organisation secret `GITEA_PACKAGE_TOKEN` and the organisation
  variable `GITEA_PACKAGE_USER`. A repository under a personal GitHub account
  cannot see organisation secrets and carries its own copy as a repository
  secret and variable.
- Gitea tokens do not expire. Rotation is manual: once for the organisation
  secret and once per personal-account copy.

Gitea answers 409 for a version that already exists, which a **Re-run failed
jobs** meets for files that went up the first time. For a `.deb`, 409 counts
as success only when the stored file's SHA-256 equals the asset's. For an
`.rpm`, Gitea stores the signed file, so the hashes never match. There, 409
counts as success when a file with the same name, version-release and
architecture exists, and the job log says the content was not compared.

What users type on Debian and Ubuntu:

    sudo install -d -m 0755 /etc/apt/keyrings
    sudo curl -o /etc/apt/keyrings/gitea-oposs.asc https://gitea.oetiker.ch/api/packages/oposs/debian/repository.key
    echo "deb [signed-by=/etc/apt/keyrings/gitea-oposs.asc] https://gitea.oetiker.ch/api/packages/oposs/debian stable main" | sudo tee /etc/apt/sources.list.d/oposs.list

On Fedora 41 and later (dnf5):

    sudo dnf config-manager addrepo --from-repofile=https://gitea.oetiker.ch/api/packages/oposs/rpm.repo

On RHEL, Rocky and Alma, and Fedora before 41 (dnf4):

    sudo dnf config-manager --add-repo https://gitea.oetiker.ch/api/packages/oposs/rpm.repo

## Check these still hold

The prose above has no automatic test; if GitHub changes one of these
behaviours, nothing fails loudly. The workflow just stops doing what this file
says it does.

- **A check run written by `GITHUB_TOKEN` satisfies a required context that
  names no app.** Open a release pull request and look at the merge box:
  `ci-passed` and `changelog-updated` must read as required and passed. If
  GitHub starts to demand the app, the ruleset needs `integration_id` for
  GitHub Actions.
- **The up-to-date rule refuses a merge whose head is behind.** Merge an
  unrelated pull request while a release pull request is open: the release
  pull request must show `the head branch is not up to date with the base
  branch`.
- **A job-level `if:` reports Success on skip; a workflow-level filter stays
  Pending.** Open a PR that touches nothing a filter would match and watch the
  check. If this reverses, the changelog gate's escape hatch stops working and
  it can no longer be required.
- **A check run's id equals its Actions job id**, which is what makes
  `ignoreCheckRunIds` work. If a future `checks.listForRef` response uses a
  different id space, the guard needs the mapping, not just the ids.
- **GitHub evaluates only the latest run per context.** Fail a check, then
  push a change that makes the same context skip, and see whether the pull
  request goes green. If it stops doing that, labelling can move back to "any
  time before merge" instead of "at creation."
