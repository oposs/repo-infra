# Release flow

How a release installed by this plugin actually happens, why the shape is what
it is, and how to recover one that stalls partway. `RELEASING.md` at the
repository root is the same content, written for a human reading it once; this
is the version for a model operating one of these repositories.

## The two steps, and why a push cannot do this

**1. Dispatch `Create release PR`** (bugfix / feature / major). It refuses
unless every check on the current `main` commit is green, computes the next
version, rolls `CHANGES.md`, bumps every version file, and opens a
`release/vX.Y.Z` pull request. Nothing is tagged yet; closing the PR cancels
the release.

**2. Merge that pull request.** The merge triggers the publish workflow, which
re-reads the version out of `CHANGES.md`, tags, and publishes the release.

The reason it is two steps and not `git push` from a workflow: `main` is
protected by a ruleset whose `bypass_actors` is empty, and the bypass list only
accepts `User`, `Team`, `Integration`, `OrganizationAdmin`, `RepositoryRole` and
`DeployKey`. `GITHUB_TOKEN` is none of those, so it cannot be added. A pull
request needs no such bypass; it is reviewed and merged by whoever has write
access, the same as any other change. This is a property of the ruleset, not a
missing feature. Do not try to route around it by adding an `on: push` trigger
on the release branch; a push made with `GITHUB_TOKEN` does not fire workflow
triggers either.

## The approval-required banner is expected

A pull request opened by `GITHUB_TOKEN` does not skip its `pull_request`
workflow runs. It parks them in an **approval-required** state, shown as a
banner in the merge box. Anyone with write access approves them once, and both
`ci-passed` and `changelog-updated` then report for real. Seeing that banner on
a release PR is the system working, not a stuck release.

The runs can be approved without the browser. List the runs of the release
branch, then approve each parked one by its ID (`gh` fills in `{owner}/{repo}`
from the current repository):

```sh
gh run list --branch release/vX.Y.Z
gh api --method POST repos/{owner}/{repo}/actions/runs/<id>/approve
```

Approving is a write to GitHub; ask before doing it. The **Approve workflows to
run** button in the merge box stays the fallback.

The alternative (opening the PR with a stored PAT or GitHub App so the runs
start unattended) was rejected: it is a credential to create, store and
rotate, to save one approval that already happens on a PR someone reviews
anyway.

## The guard fails fast, and is not redundant with the required checks

`Create release PR`'s `guard` job reads every check run on the current `main`
commit (`checks.listForRef`) and refuses if any failed, any is still running
past its timeout, or none ran at all. This is not standing in for the ruleset's
required checks. It runs *before* a branch, a commit, a pull request or an
approval exists. Without it, a release dispatched against a red `main`
still rolls the changelog, bumps every version file, pushes a branch and opens
a PR, and only then parks on a check someone has to approve in order to watch
it fail. The guard turns that into an immediate refusal with nothing to clean
up. Do not remove it because "the ruleset already requires checks": the
ruleset gates the merge; the guard gates the dispatch.

## `ignoreCheckRunIds`: a job that waits on its own commit's checks waits for itself

The guard's own job run is one of the check runs on the commit it is
inspecting. Without excluding its own run, it polls for every check to
complete, including the one that is currently doing the polling, and times
out. A check run's id is its Actions job id, so the guard reads the job ids off
this workflow's runs and passes them as `ignoreCheckRunIds` before it starts
waiting. Any new job added to `release-pr.yml` needs no special handling for
this; only the guard job itself, because only it waits on checks at all.

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
have done. The one case this does not cover: if a failed run got as far as
creating the tag before dying, the tag-exists check at the top of the job
returns early on the re-run, before tagging *or* creating the release, so a
failure between those two steps needs the tag removed by hand
(`git push origin --delete vX.Y.Z`, confirmed with the user first) before a
re-run can finish the job.

Publish add-ons are safe to re-run. `publish-source-tarball` skips the upload
when the release already has an asset of that name, and `publish-crates-io`
asks crates.io and publishes only the workspace crates whose version is not
there yet. **Re-run failed jobs** therefore finishes a stopped release. With
`release_build` a whole-workflow re-run does too. Without it, a whole-workflow
re-run skips everything once the tag exists and the release stays a draft.

## Releases that build before the merge (release_build)

`"release_build": true` moves the build in front of the merge. The `Create
release PR` workflow then has three jobs:

- `prepare`: the guard, the two refusals below, the removal of stale drafts,
  and the roll and version bump as usual.
- `build`: calls the project's `.github/workflows/release-build.yml` with
  `contents: read` and no secrets. It uploads the release files as
  `release-asset-*` artifacts, and the repository files it rewrote as the
  artifact `release-files`.
- `finish`: commits the files listed in `release_files` onto the release
  branch, creates a draft release with the assets and `release-build.json`,
  sets the commit status `release-built` and opens the pull request. It
  first removes its own earlier drafts for the same version, including a
  bot-created draft that a failed upload left without `release-build.json`.

The formula change is part of the pull request diff, so reviewers see it. The
`finish` job refuses a `release_files` entry that reaches `CHANGES.md`, a
version file, `.github/repo-infra.json` or anything under `.github/`, after
normalising the path.

Publish tags the head recorded in `release-build.json`, not the merge commit.
If that commit does not exist in the repository, publish fails with
`release-build.json names <sha>, which does not exist in this repository`.
Repository-owned `publish_local` jobs check out
`ref: ${{ needs.publish.outputs.head }}`, the tagged commit, like the add-ons
do. Without `release_build` that is the merge commit, as before. A
whole-workflow re-run finishes a stopped release only when every `publish_local`
job skips what an earlier attempt already uploaded.

Between the merge and `finalize` the Homebrew formula on `main` points at
release URLs that answer 404, because the release is still a draft. Usually
that lasts the few minutes publish takes. A failed add-on keeps the release a
draft and `brew install` fails until it is public. Recovery is **Re-run failed
jobs** on the publish run.

`Create release PR` refuses in two cases:

- A release pull request is already open (from a `release/*` branch of this
  repository, opened by `github-actions[bot]`). The message names it.
- The latest release in `CHANGES.md` on `main` has no tag:
  `vX.Y.Z is in CHANGES.md on main but has no tag`. The ways out are
  **Re-run failed jobs** on its publish run; for a release that is already
  out under another tag, pushing `vX.Y.Z` by hand (the ruleset covers the
  branch, not tags); or, to abandon it, a pull request that moves its entries
  back under `[Unreleased]`.

**Update branch** on a release pull request moves the branch after the build.
`changelog-updated` then turns red, and adding `no-changelog` does not help.
Close the pull request and dispatch `Create release PR` again. The next
dispatch also deletes stale drafts: drafts with a `release-build.json` whose
tag does not exist and whose version is not the latest release in `CHANGES.md`
on `main`.

## Gitea packages (publish-gitea-packages)

The add-on uploads every `.deb` and `.rpm` release asset to a Gitea package
registry, which signs them with its own key. No repository holds a signing
key. The release stays a draft until the upload succeeded. The add-on uploads
what the release pull request built, so it needs `release_build`; `check`
reports a conflict without it, and when `gitea_packages` lacks `url` or `owner`.

    "publish": ["publish-gitea-packages"],
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

- **`GITHUB_TOKEN`-opened pull requests park runs rather than skip them.**
  Open a release PR and look for the approval banner. If runs are not created
  at all, neither required check can ever report, and the ruleset needs to
  drop them.
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
