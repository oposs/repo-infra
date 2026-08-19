# Releasing

`main` is protected, so a release lands in two halves.

**1. Run the `Create release PR` workflow** (Actions → Create release PR →
Run workflow → bugfix / feature / major). It:

1. refuses unless every check on the current `main` commit is green,
2. computes the next version from the tags and refuses if it already exists,
3. rolls the `CHANGES.md` `[Unreleased]` section into a dated version section,
4. sets every file listed in `.github/repo-infra.json` to the same version,
5. pushes a `release/vX.Y.Z` branch and opens a pull request.

Nothing is tagged or published yet. Closing the pull request cancels the release.

**2. Review the changelog and merge.** That triggers the publish workflow, which
reads the version back out of `CHANGES.md`, checks every version file agrees,
tags, and publishes the GitHub release.

## Why a pull request

`main` is protected by a repository ruleset, and the built-in `GITHUB_TOKEN`
cannot be given a bypass — the bypass list accepts users, teams and GitHub Apps,
and the Actions token is none of those. Landing the release through a pull
request needs no stored credential and works with the protection rather than
around it. Tagging is unaffected: the ruleset targets branches, and tags live in
a separate ref namespace.

## Why the release pull request needs a click

The ruleset requires two status checks, `ci-passed` and `changelog-updated`. Nothing
merges to `main` without them, including a release.

A pull request opened by `GITHUB_TOKEN` does not start its `pull_request`
workflow runs automatically. They are created in an **approval-required** state:
the merge box shows a banner, and anyone with write access starts them with
**Approve workflows to run**. The checks are parked, not skipped — so they do
report, and the pull request does merge.

That single click is deliberate. The alternative is to open the release pull
request with a GitHub App or personal access token so the runs start unattended,
which means a credential to create, store and rotate. The click costs less.

Do not try to route around it with an `on: push` trigger on the release branch.
The same restriction covers pushes: a push made with `GITHUB_TOKEN` does not
trigger workflows either, and the release branch is created by the Actions token
through the Git Data API. There is no automatic path to a green check here.

`changelog-updated` skips itself on `release/*` branches. A skipped job reports
Success, so it satisfies the requirement without running.

**Check this still holds** by opening a release pull request and looking for the
banner. If the runs are not created at all, neither required check can ever
report, and the ruleset must drop them until another route exists.

## Why a required workflow never uses a `paths` filter

A job skipped by a job-level `if:` reports **Success** and merges fine. A whole
workflow skipped by a `paths` or `branches` filter stays **Pending** forever and
blocks the pull request. GitHub's own guidance: do not use path or branch
filtering to skip workflow runs if the workflow is required.

So `ci.yml` and `changelog.yml` carry no `paths` filter, and every
conditional lives inside a job. If someone adds `paths:` to save CI minutes,
every pull request that does not match it becomes unmergeable, with no failing
check and no log to explain why.

## Why publishing has no manual trigger

Publishing should be a consequence of merging a release pull request, not
something anyone starts from a dropdown. A failed run is re-run from the Actions
UI, and because the version comes from `CHANGES.md` rather than from run inputs,
the re-run does exactly what the original attempt would have done.
