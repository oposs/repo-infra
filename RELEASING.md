# Releasing

`main` is protected, so a release lands in two halves.

**1. Run the `Create release PR` workflow** (Actions → Create release PR →
Run workflow → bugfix / feature / major). It:

1. refuses when a check on the current `main` commit has already failed, when
   a release pull request is open, or when the latest release in `CHANGES.md`
   has no tag,
2. computes the next version from the tags and refuses if it already exists,
3. rolls the `CHANGES.md` `[Unreleased]` section into a dated version section
   and sets every file listed in `.github/repo-infra.json` to the same version,
4. builds the release (`release-build.yml`) and runs this repository's CI
   (`ci.yml`) on the `release/vX.Y.Z` branch,
5. drafts the release with every built file and opens the pull request.

Nothing is tagged or published yet. Closing the pull request cancels the release.

**2. Review and merge.** Nothing needs approving. The merge triggers the
publish workflow, which tags the commit that was built and publishes the draft.

## Why a pull request

`main` is protected by a repository ruleset, and the built-in `GITHUB_TOKEN`
cannot be given a bypass: the bypass list accepts users, teams and GitHub Apps,
and the Actions token is none of those. Landing the release through a pull
request needs no stored credential and works with the protection rather than
around it. Tagging is unaffected: the ruleset targets branches, and tags live in
a separate ref namespace.

## Why the release pull request merges without an approval

The ruleset requires two checks, `ci-passed` and `changelog-updated`, and
requires the branch to be up to date with `main`. `Create release PR` writes
both checks on the release branch itself, after it built and tested that
exact commit. The pull request's own runs still park in an approval-required
state, because `GITHUB_TOKEN` opened it; nobody needs to approve them, and
publishing deletes them. Approving one anyway runs only `ci-passed`: every
other job of `ci.yml` skips on the release pull request (D31).

If `main` moves before the merge, GitHub refuses the merge (`the head branch
is not up to date with the base branch`) and `ci-passed` turns red with
`main moved after vX.Y.Z was built; close this pull request and dispatch
Create release PR again`. Do that. Do not press **Update branch**: the new
head was neither built nor tested, and both checks turn red.

## Secrets

The release build and the CI run inside `Create release PR` get the
repository's secrets, so a build can sign a binary. No repository secret may
carry write access to the repository. A classic personal access token with
`repo` scope, typical for pushing to a Homebrew tap, breaks that rule.

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

## When a release gets stuck

- Merge release pull requests with a merge commit. All three merge methods
  stay allowed, but after a squash or rebase `git describe` on `main` no
  longer finds the tag.
- `Create release PR` refuses with `vX.Y.Z is in CHANGES.md on main but has
  no tag` while the last release has no tag. If its publish run failed for
  another reason than the tree comparison, **Re-run failed jobs** on it. For
  a release that is already out under another tag, push `vX.Y.Z` by hand (the
  ruleset covers the branch, not tags). To abandon it, merge a pull request
  that moves its entries back under `[Unreleased]`.
- Publish fails with `main at <sha> does not match the release built from
  <head>` only when the up-to-date rule was off at the merge. It tags
  nothing. Abandon the release as above, then dispatch again.
- A tag pushed by hand for the newest released version, without a GitHub
  release, makes every publish run fail until the next release creates one.
