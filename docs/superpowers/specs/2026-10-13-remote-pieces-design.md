# Remote pieces: consumers call repo-infra's workflows instead of copying them

Date: 2026-10-13
Status: draft for review
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
  `v2`; consumers get fixes without a pull request. A bad release is undone by
  moving `v2` back.
- **Same pieces as today.** Each repository still chooses and wires its own
  pieces in its callers. One entry workflow per ecosystem is a later step,
  decided per element once several repositories run on v2 (see "Later").
- **The release of repo-infra is the gate.** Before `v2` moves, the release
  build runs mtuspy's CI and release-build jobs against the release commit.
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
  `repo-infra-container.m4`, `dependabot.yml`, and `gh/ruleset-main.json`.
  These keep the byte model and their entries in `generations.json`. Entries
  for pieces that became remote leave `generations.json` and `manifest.json`.
- repo-infra's own callers call its pieces as `./.github/workflows/ri-*.yml`,
  so repo-infra runs each piece from the commit under test.

## Loading the library

A piece runs in the consumer's repository; its checkout holds the consumer's
files, not repo-infra's. Every piece that uses the library first checks out
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

`job.workflow_repository` and `job.workflow_sha` describe the file that
defines the job, not the caller (GitHub, April 2026). They are absent on GitHub
Enterprise Server, which no consumer uses.

Called from a release branch of repo-infra, the same step loads the library of
that branch, so the gate tests the library and the pieces of one commit.

## A source input on every piece

Every piece that checks out the source already takes `ref`. It also takes
`repository` (default `${{ github.repository }}`), and each source checkout
passes both. Callers in consumers leave it unset. The release gate sets it to
`oetiker/mtuspy`.

## Core workflows

`changelog.yml` (triggered by `pull_request`) and `release-pr.yml` (triggered
by `workflow_dispatch`, 519 lines) are whole workflows today, copied as pieces.

- `changelog` becomes `ri-changelog.yml` with `workflow_call`. The consumer
  keeps a caller with the `pull_request` trigger and the job name
  `changelog-updated` that the ruleset requires.
- `release-pr` calls the consumer's own `release-build.yml` and `ci.yml`
  through `./.github/workflows/`. Which repository `./` names inside a
  remotely called workflow is not documented for workflow calls. The first
  task of the plan is a probe: a piece in repo-infra, called from a test
  caller in another repository, calls `./.github/workflows/<file>.yml`, and
  the run shows which repository's file ran.
  - If `./` names the caller's repository, `release-pr` stays one piece
    (`ri-release-pr.yml`, `workflow_call`) behind a consumer caller with
    `workflow_dispatch`. Calls from one repo-infra piece to another then use
    the `$/` prefix (GitHub, July 2026), which names the piece's own
    repository at the running commit.
  - Otherwise `release-pr` splits into `ri-release-prepare.yml` and
    `ri-release-finish.yml`, and the consumer's `release-pr.yml` wires
    `prepare`, its own `release-build`, its own `ci` and `finish`.
- Jobs that callers carry inline and that load the library become pieces:
  `ci-passed` (from `assets/callers/ci-passed.yml`) and the release-PR check in
  mtuspy's `ci.yml`. `ci-passed` keeps `if: always()`.
- `release-publish.yml` already calls only pieces; its `uses:` lines change.

## Secrets

`secrets: inherit` works only when caller and called workflow belong to the
same organisation or enterprise. mtuspy (`oetiker/`) calls `oposs/repo-infra`,
so every caller passes each secret by name, as callers do today.

## The release gate

`.github/workflows/gate-mtuspy.yml` in repo-infra, called by repo-infra's
`release-build.yml` on the release branch, before the release pull request
opens:

- It runs mtuspy's CI jobs (`ri-ci-lib`, `ri-ci-rust`, `ri-ci-rust-musl`,
  `ri-ci-man`) and release-build jobs (`ri-release-rust-binaries`,
  `ri-release-nfpm`, `ri-release-homebrew`) through
  `./.github/workflows/ri-*.yml`, with `repository: oetiker/mtuspy` and
  `ref` set to the mtuspy tag that `references/examples/mtuspy/` records.
- It runs no publish piece and needs no secret.
- A failed gate stops the release pull request; `v2` does not move.
- A test holds the gate's jobs and inputs equal to the example callers under
  `references/examples/mtuspy/`, apart from `repository` and `ref`.

## The tag

repo-infra's `.github/repo-infra.json` sets `moving_major_tag: true`. The
existing publish piece moves `v2` after the release tag.

## check

- Every `uses:` that names a repo-infra piece reads
  `oposs/repo-infra/.github/workflows/ri-<name>.yml@v2`.
- A local `.github/workflows/ri-*.yml` or `.github/workflows/lib/` is a finding:
  v1 layout, migrate.
- The jobs the ruleset requires exist: `ci-passed` with `if: always()`, and
  `changelog-updated`.
- Each called piece gets the inputs it requires, and each secret it declares
  `required: true`.
- Fragments are compared by bytes against `generations.json`, as today.
- The project shape review is unchanged.

## apply

- `apply` writes callers and fragments, never pieces.
- Migration from v1 is one pull request on the branch `repo-infra/apply`: it
  removes the copied `ri-*.yml` and `.github/workflows/lib/`, rewrites the
  `uses:` lines, replaces inline library jobs with their pieces, passes
  secrets by name and keeps the fragments. The repository's CI on that pull
  request is the test.
- mtuspy migrates first. After its migration `references/examples/mtuspy/`
  holds its v2 callers.

## Version

repo-infra 2.0.0. The tag `v2` appears with it.

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
