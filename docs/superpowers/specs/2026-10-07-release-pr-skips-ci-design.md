# The release pull request skips the jobs of ci.yml

Date: 2026-10-07
Status: approved
Decision: D31 (builds on D28's release mode of `ci-passed` and on D30's callers)

## Problem

Create release PR (`release-pr.yml`) runs `ci.yml` as a `workflow_call` and
the release build on the release branch, then opens the release pull request
with `GITHUB_TOKEN`. GitHub parks that pull request's own `pull_request` run of
`ci.yml` as `action_required`. Nobody needs to approve it, but someone did on
oetiker/mdmost (run 37503956034), and every heavy CI job ran a second time on
a commit Create release PR had already tested. The result counted for nothing:
on that pull request `ci-passed` is in release mode and ignores every test
result (`releaseModeVerdict` in `lib/release.js`).

## Decision

Every job of `ci.yml` other than `ci-passed` carries this `if:`, stored once in
`assets/callers/release-pr-skip.yml`:

```yaml
if: ${{ !(github.event_name == 'pull_request' && startsWith(github.head_ref, 'release/') && github.event.pull_request.head.repo.full_name == github.repository && github.event.pull_request.user.login == 'github-actions[bot]') }}
```

A stricter guard joined with `&&` is fine. `check` reports every job of
`ci.yml` whose `if:` does not require the condition: a missing `if:`, or one
that joins it with `||`. Jobs in other files are not checked. When Create
release PR calls `ci.yml` the event is `workflow_dispatch`, so the jobs run
there.

The `${{ }}` is required: a YAML scalar that starts with `!` is a tag, and the
file would not parse.

## Why in the caller and not in the pieces

- `ci.yml` also holds jobs no piece ships: a call to `ci-local.yml`, or an
  inline job the repository wrote. A guard inside each piece would leave those
  running.
- The skip is only safe because `ci-passed` ignores the test results on the
  same pull request. Both live in `ci.yml`, and `check` reads both there.
- No piece changes bytes, so no piece needs a new version.

## Exactly the pull request isReleasePr names

The four terms are the payload fields `isReleasePr` in `lib/release.js` tests:
the event is a pull request, the head branch starts with `release/`, the head
is in this repository, and `github-actions[bot]` opened it. `ci-passed` enters
release mode exactly when `isReleasePr` is true.

A looser condition, for example the head branch prefix alone, would also skip
the jobs of a person's or a fork's `release/x` pull request. `ci-passed` judges
that pull request by the ordinary rules, a skipped need counts as success
there, and the pull request would go green untested. A stricter condition only
costs the duplicate run this decision removes. `tests/test_release_mode.py`
compares the asset with the exact text and ties each term to the source of
`isReleasePr`, since the test harness never evaluates expressions.

## Migration

The callers belong to the repository, so `apply` does not touch them. A
repository edits its `ci.yml` by hand and copies the `if:` onto each job other
than `ci-passed`. Until then, `check` reports each such job as a problem and
exits 1.
