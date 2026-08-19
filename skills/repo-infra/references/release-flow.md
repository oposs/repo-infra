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
`DeployKey` — `GITHUB_TOKEN` is none of those, so it cannot be added. A pull
request needs no such bypass; it is reviewed and merged by whoever has write
access, the same as any other change. This is a property of the ruleset, not a
missing feature — do not try to route around it by adding an `on: push` trigger
on the release branch; a push made with `GITHUB_TOKEN` does not fire workflow
triggers either.

## The "Approve workflows to run" click is expected

A pull request opened by `GITHUB_TOKEN` does not skip its `pull_request`
workflow runs — it parks them in an **approval-required** state, shown as a
banner in the merge box. Anyone with write access clicks **Approve workflows to
run** once, and both `ci-passed` and `changelog-updated` then report for real.
Seeing that banner on a release PR is the system working, not a stuck release.
The alternative — opening the PR with a stored PAT or GitHub App so the runs
start unattended — was rejected: it is a credential to create, store and
rotate, to save one click that already happens on a PR someone reviews anyway.

## The guard fails fast, and is not redundant with the required checks

`Create release PR`'s `guard` job reads every check run on the current `main`
commit (`checks.listForRef`) and refuses if any failed, any is still running
past its timeout, or none ran at all. This is not standing in for the ruleset's
required checks — it runs *before* a branch, a commit, a pull request or an
approval click exists. Without it, a release dispatched against a red `main`
still rolls the changelog, bumps every version file, pushes a branch and opens
a PR — and only then parks on a check someone has to approve in order to watch
it fail. The guard turns that into an immediate refusal with nothing to clean
up. Do not remove it because "the ruleset already requires checks" — the
ruleset gates the merge; the guard gates the dispatch.

## `ignoreCheckRunIds`: a job that waits on its own commit's checks waits for itself

The guard's own job run is one of the check runs on the commit it is
inspecting. Without excluding its own run, it polls for every check to
complete — including the one that is currently doing the polling — and times
out. A check run's id is its Actions job id, so the guard reads its own job ids
from the current run and passes them as `ignoreCheckRunIds` before it starts
waiting. Any new job added to `release-pr.yml` needs no special handling for
this; only the guard job itself, because only it waits on checks at all.

## GitHub keeps only the latest check run per context

A second check run on the same context replaces the first for merge purposes —
a later run that skips (and so reports Success) clears an earlier failure on
that same context. This is convenient for re-running a fixed check, and a trap
for labelling: adding the `no-changelog` label to a pull request *after* the
changelog check has already failed produces a new, skipped, green run for that
context, and the pull request becomes mergeable — with no changelog entry and
no second look. Apply the label at creation
(`gh pr create --label no-changelog`), not as a fix-up after the fact.

## Recovery: re-run, never re-dispatch

A failed publish run is re-run from the Actions UI (Actions → the failed run →
**Re-run failed jobs**). There is deliberately no `workflow_dispatch` on
`release-publish.yml` — publishing is a consequence of merging a release PR,
not something started from a dropdown — and none is needed for recovery: the
version comes from `CHANGES.md` in the repository, not from run inputs, so a
re-run reads the same version and does exactly what the original attempt would
have done. The one case this does not cover: if a failed run got as far as
creating the tag before dying, the tag-exists check at the top of the job
returns early on the re-run, before tagging *or* creating the release — so a
failure between those two steps needs the tag removed by hand
(`git push origin --delete vX.Y.Z`, confirmed with the user first) before a
re-run can finish the job.

## Check these still hold

The prose above has no automatic test; if GitHub changes one of these
behaviours, nothing fails loudly — the workflow just stops doing what this file
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
