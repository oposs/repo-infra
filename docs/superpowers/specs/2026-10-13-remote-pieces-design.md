# Remote pieces: consumers call repo-infra's workflows instead of copying them

Date: 2026-10-13
Status: draft for review, revised after one pushback review of the same day
Decision: D33 (replaces D30's rule that pieces are copied byte for byte into
every repository; keeps D30's split between pieces and callers, D28 and D31's
release flow and D32's project shape)

## Why

Under D30 every repository carries a byte copy of each `ri-*.yml` piece it
calls and of `.github/workflows/lib/` (12 modules, 12 test files). A fix to a
piece reaches a repository only through an `apply` pull request in that
repository, and `check` exists largely to find copies that fell behind. mtuspy
alone carries ten pieces and the library next to 255 lines of its own callers.

repo-infra itself keeps two copies of the library
(`skills/repo-infra/assets/pieces/workflow-lib/lib` and `.github/workflows/lib`)
that a test holds equal.

## Decisions

- **Pieces are called remotely.** A caller writes
  `uses: oposs/repo-infra/.github/workflows/ri-<name>.yml@v2`. No `ri-*.yml`
  and no `lib/` is copied into a consumer.
- **Consumers pin the moving major tag `v2`.** Every repo-infra release moves
  `v2`; consumers get fixes without a pull request.
- **Pieces keep a stable interface within `v2`** (see "Compatibility within
  v2"), because every consumer runs every release.
- **Same pieces as today.** Each repository still chooses and wires its own
  pieces in its callers. One entry workflow per ecosystem is a later step,
  decided per element once several repositories run on v2 (see "Later").
- **The release of repo-infra is the gate.** Before `v2` moves, a separate
  workflow run builds mtuspy with the pieces of the release commit.
- **v1 freezes.** repo-infra 2.0.0 ships only the remote layout. v1 gets no
  further fixes; `check` reports a v1 repository as one to migrate and `apply`
  migrates it in one pull request.

## Layout in repo-infra

- Every piece lives once, as `.github/workflows/ri-<name>.yml`. GitHub runs a
  reusable workflow only from that directory.
- The library lives once, in `.github/workflows/lib/`. The second copy under
  `skills/repo-infra/assets/pieces/workflow-lib/` and the test that holds the
  two equal are removed.
- `skills/repo-infra/assets/pieces/` keeps the fragments GitHub cannot load
  remotely: `man.mk`, `man-deflist.lua`, `container.mk`,
  `repo-infra-container.m4` and `dependabot.yml`. `skills/repo-infra/assets/gh/ruleset-main.json`
  stays where it is. These keep the byte model and their entries in
  `generations.json`.
- `manifest.json` keeps every remote piece with its `group` and `core`, marked
  `"kind": "remote"` and without bytes or generations, so `apply` still picks
  pieces by group. Remote pieces leave `generations.json`.
- `ri-ci-lib` tests the library and becomes a repo-infra piece only: it leaves
  the catalogue for consumers.
- repo-infra's own callers call its pieces as `./.github/workflows/ri-*.yml`,
  so repo-infra runs each piece from the commit under test. The two judges
  that D28 loads from the base commit (`changelog-updated` and the release
  mode of `ci-passed`) call `@v2` instead, so a pull request to repo-infra that
  changes the library is judged by the released library.

## Loading the library

A piece runs in the consumer's repository; its checkout holds the consumer's
files, not repo-infra's. Every piece that uses the library checks out
repo-infra at the commit the piece itself was loaded from:

```yaml
- uses: actions/checkout@v7
  with:
    repository: ${{ job.workflow_repository }}
    ref: ${{ job.workflow_sha }}
    path: .repo-infra
    sparse-checkout: .github/workflows/lib
```

and its `actions/github-script` step requires
`${GITHUB_WORKSPACE}/.repo-infra/.github/workflows/lib/<module>.js`.

- In a job that also checks out the source, the source checkout comes first.
  `actions/checkout` cleans the workspace by default and would remove
  `.repo-infra` otherwise.
- `.repo-infra/` is untracked in the source tree while the job runs. A piece
  whose build reads the whole tree (an archive, a `git status` check) does its
  library work in a job of its own.

`job.workflow_repository` and `job.workflow_sha` describe the file that
defines the job, not the caller (GitHub changelog, early September 2026). They
are absent on GitHub Enterprise Server, which no consumer uses.

Called from a release branch of repo-infra, the same step loads the library of
that branch, so the gate tests the library and the pieces of one commit.

## A source input on every piece

Every piece that checks out the source already takes `ref`. It also takes
`repository` (default `${{ github.repository }}`), and each source checkout
passes both. A piece that derives a URL or a name from `$GITHUB_REPOSITORY`
uses the input instead; `ri-release-homebrew` builds the bottle `root-url`
this way. Callers in consumers leave `repository` unset. The gate sets it to
`oetiker/mtuspy`.

## Required checks stay inline

The ruleset requires the contexts `ci-passed` and `changelog-updated`, and
`release-pr` writes statuses under the same names. A job that calls a
reusable workflow reports as `<caller job> / <called job>`, and a called
workflow cannot read the caller's `needs`. Both required jobs therefore stay
inline in the callers, under their current job ids. The library work moves
into pieces:

- `ri-release-verdict` computes D28's release mode for a pull request from a
  `release/*` branch and returns `mode` (`release`, `ordinary`) and `ok` as
  outputs. The inline `ci-passed` keeps `if: always()`, lists the verdict job
  and every other job in `needs:`, and fails when the verdict job did not
  succeed, when `mode` is `release` and `ok` is false, or when `mode` is not
  `release` and a needed job failed or was cancelled.
- `ri-changelog` checks `CHANGES.md` and returns its verdict as an output. The
  inline `changelog-updated` keeps today's label condition in its `if:`, joined
  with `always()`, needs the `ri-changelog` job, and fails unless that job
  succeeded. A required job skipped because a needed job failed would report
  success; `always()` prevents that. The `ri-changelog` job carries the same
  label condition, so the `no-changelog` label skips both.

`assets/callers/ci-passed.yml` and a new `assets/callers/changelog.yml` hold
the inline jobs word for word; `check` compares them as it does today.

## release-pr splits

`release-pr.yml` calls the consumer's own `release-build.yml` and `ci.yml`
with `secrets: inherit` and with the union of permissions their jobs need. A
piece in `oposs/repo-infra` cannot pass `inherit` to a repository of another
organisation, and it cannot know each consumer's secrets and permissions.
`release-pr` therefore splits into two pieces:

- `ri-release-prepare` creates the release branch, rolls `CHANGES.md` and sets
  the version files; it returns the version and the branch head.
- `ri-release-finish` collects the build artifacts, writes the draft release,
  sets the `release-built`, `ci-passed` and `changelog-updated` statuses and
  opens the pull request.

The consumer's `release-pr.yml` keeps `workflow_dispatch` and wires
`prepare`, its own `release-build`, its own `ci` and `finish`, passing secrets
by name. `assets/callers/release-pr.yml` holds it.

`ri-ci-github-action` calls the consumer's `./.github/workflows/action-test.yml`
with `secrets: inherit` and is restructured the same way: the consumer's
`ci.yml` calls `action-test.yml` itself, and the piece keeps only the work
that needs no consumer file.

The plan opens with a probe of how `./` resolves inside a workflow called from
another repository, which GitHub does not document. It no longer decides the
design; it decides whether a piece may use `./` for anything, and calls from
one repo-infra piece to another use the documented `$/` prefix (same
repository, same commit as the calling piece).

`changelog.yml`'s `pull_request` trigger and `release-publish.yml` stay in the
consumer as callers.

## Secrets

`secrets: inherit` works only when caller and called workflow belong to the
same organisation or enterprise. Every caller passes each secret by name.

## The release gate

The gate is its own workflow run, so its artifacts never reach the run that
builds repo-infra's release.

- `.github/workflows/gate-mtuspy.yml` in repo-infra has `workflow_dispatch`
  with an input `ref`. It runs mtuspy's CI jobs (`ri-ci-rust`,
  `ri-ci-rust-musl`, `ri-ci-man`) and release-build jobs
  (`ri-release-rust-binaries`, `ri-release-nfpm`, `ri-release-homebrew`)
  through `./.github/workflows/ri-*.yml` at that ref, with `repository` and
  `ref` set from the example's source record. It runs no publish piece and
  needs no secret.
- repo-infra's `release-build.yml` dispatches it on the release branch head,
  finds the run by head commit and creation time, waits for it and fails
  unless it succeeded. A failed gate stops the release pull request; `v2`
  does not move.
- `references/examples/mtuspy/source.json` records the source:
  `repository`, `ref` (a tag) and `version`. The gate reads it.
- A test holds the gate's jobs and inputs equal to the example callers,
  apart from `repository`, `ref` and the `@v2` versus `./` form of `uses:`.

## Compatibility within v2

Every consumer runs every release of `v2`, and the gate exercises only the
pieces mtuspy uses. Within `v2` a piece may:

- add an input only with a default,
- add a secret only as optional,
- add an output,

and may not remove or rename an input, secret or output, make one required,
or widen the `permissions:` of a job (a called workflow cannot raise what its
caller grants). Any such change waits for `v3`.

A test compares each piece's `workflow_call` interface and job permissions
with the same piece at the latest release tag and fails on a change outside
these rules.

## The tag

- repo-infra's `.github/repo-infra.json` sets `moving_major_tag: true`;
  `ri-publish-tag` moves `v2` after the release tag.
- A tag ruleset on `v*` in repo-infra blocks updates and deletion. A GitHub
  App on the ruleset's bypass list moves the tag. `ri-publish-tag` gets an
  optional secret for the App's token and uses it to move the major tag when
  it is set. repo-infra's caller passes it; consumers without it keep today's
  behaviour.
- `RELEASING.md` documents the rollback: an admin points `v2` at the previous
  release tag's commit, then the defect is reverted on `main` before the next
  release, which moves `v2` forward again.

## check

- Every `uses:` that names a repo-infra piece reads
  `oposs/repo-infra/.github/workflows/ri-<name>.yml@v2`.
- A local `.github/workflows/ri-*.yml` or `.github/workflows/lib/` is a finding:
  v1 layout, migrate.
- The inline jobs `ci-passed` and `changelog-updated` match
  `assets/callers/`, `ci-passed`'s `needs:` names every other job.
- Each called piece gets the inputs it requires and each secret it declares
  `required: true`. `check` reads the interfaces from the pieces in the
  installed plugin, whose version is the release `v2` points at.
- Fragments are compared by bytes against `generations.json`, as today.
- The project shape review is unchanged.

## apply

- `apply` writes callers and fragments, never pieces.
- Migration from v1 is one pull request on the branch `repo-infra/apply`: it
  removes the copied `ri-*.yml` and `.github/workflows/lib/`, rewrites the
  `uses:` lines, replaces the inline `ci-passed`, `changelog.yml` and
  `release-pr.yml` with their v2 callers, passes secrets by name and keeps the
  fragments. The repository's CI on that pull request is the test.

## Order of work

1. Probe `./` inside a cross-repository call.
2. repo-infra 2.0.0 on one branch: the layout, the split pieces, the inline
   jobs, the gate, the compatibility test, the tag ruleset and App, `check`
   and `apply`. `references/examples/mtuspy/` gets hand-written v2 callers and
   `source.json` pointing at mtuspy `v0.2.1`, version `0.2.1`; the gate is
   tested against them.
3. Release 2.0.0; `v2` appears.
4. Migrate mtuspy with `apply`; its callers equal the example. Release mtuspy.
5. Move `source.json` to that mtuspy release.

## Later

- One entry workflow per ecosystem (for example a Rust program running CI,
  build and publish behind one call), decided element by element once several
  repositories run on v2.
- The defects deferred in the D32 final report (packagers values unescaped in
  YAML, duplicate archive targets, missing `--locked`, and the rest) are fixed
  in the pieces under v2, each on its own.

## Out of scope

- Consumers outside github.com.
- Pinning by exact tag or commit SHA.
- Keeping v1 maintained.
