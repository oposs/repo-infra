# Remote pieces: consumers call repo-infra's workflows instead of copying them

Date: 2026-10-13
Status: draft for review, revised after two pushback reviews of the same day
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
- repo-infra's own callers call every piece as `./.github/workflows/ri-*.yml`,
  the two judges (`ri-changelog`, `ri-release-verdict`) included, so repo-infra
  runs each piece from the commit under test before `v2` moves, and needs no
  `v2` to release 2.0.0. A pull request to repo-infra that changes the library
  is therefore judged by its own library; in consumers the judges come from
  `v2`, which a pull request cannot change.

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

Every CI and release-build piece that checks out the source already takes
`ref`. It also takes
`repository` (default `${{ github.repository }}`), and each source checkout
passes both. A piece that derives a URL or a name from `$GITHUB_REPOSITORY`
uses the input instead; `ri-release-homebrew` builds the bottle `root-url`
this way. Callers in consumers leave `repository` unset. The gate sets it to
`oetiker/mtuspy`.

## Required checks stay inline

The ruleset requires the contexts `ci-passed` and `changelog-updated`, and
`release-pr`'s finish writes check runs under the same names. A job that calls a
reusable workflow reports as `<caller job> / <called job>`, and a called
workflow cannot read the caller's `needs`. Both required jobs therefore stay
inline in the callers, under their current job ids. The library work moves
into pieces:

- `ri-release-verdict` computes D28's release mode for a pull request from a
  `release/*` branch and returns `mode` (`release`, `ordinary`), `ok` and
  `message` as outputs. On every other event (push, `workflow_dispatch`, `workflow_call`
  from `release-pr`, an ordinary pull request) it succeeds with
  `mode=ordinary`. The verdict job runs on every event: it is exempt from
  D31's `release-pr-skip` condition, in `assets/callers/` and in `check`,
  because the bot-opened release pull request is the run where the verdict
  decides. The inline `ci-passed` keeps `if: always()`, lists the verdict job
  and every other job in `needs:`, and fails when the verdict job did not
  succeed, when `mode` is `release` and `ok` is false, or when `mode` is not
  `release` and a needed job failed or was cancelled.
- `ri-changelog` checks `CHANGES.md` and returns its verdict as an output. The
  inline `changelog-updated` keeps today's label condition in its `if:`, joined
  with `!cancelled()`, needs the `ri-changelog` job, and fails unless that job
  succeeded. A required job skipped because a needed job failed would report
  success; `!cancelled()` prevents that without turning a cancelled run red.
  The `ri-changelog` job carries the same label condition, so the
  `no-changelog` label skips both.
- repo-infra's `changelog.yml` calls `ri-changelog` and its `ci.yml` calls
  `ri-release-verdict`, both through `./`, so both run on every repo-infra pull request before a release moves
  `v2`.

`assets/callers/ci-passed.yml` and a new `assets/callers/changelog.yml` hold
the inline jobs word for word; `check` compares them as it does today.

## release-pr splits

`release-pr.yml` calls the consumer's own `release-build.yml` and `ci.yml`
with `secrets: inherit` and with the union of permissions their jobs need. A
piece in `oposs/repo-infra` cannot pass `inherit` to a repository of another
organisation, and it cannot know each consumer's secrets and permissions.
`release-pr` therefore splits into two pieces:

- `ri-release-prepare` creates the release branch, rolls `CHANGES.md` and sets
  the version files; it returns the version, the date, the base commit and
  the branch head.
- `ri-release-finish` collects the build artifacts, writes the draft release,
  sets the `release-built` status and the `ci-passed` and
  `changelog-updated` check runs (`statuses: write`, `checks: write`) and
  opens the pull request.

The consumer's `release-pr.yml` keeps `workflow_dispatch` and wires
`prepare`, its own `release-build`, its own `ci` and `finish`.
`assets/callers/release-pr.yml` holds it. Its calls to the consumer's own
`release-build.yml` and `ci.yml` stay in one repository and keep
`secrets: inherit`; its calls to repo-infra pieces pass secrets by name.

`check` reviews a repository's `release-pr.yml` by structure (`prepare` and
`finish` present, `release-build` and `ci` between them, `finish` needing all
of them), not word for word, so a repository may add jobs between `prepare`
and `finish`. repo-infra adds its gate there.

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
same organisation or enterprise. Every call to a repo-infra piece passes each
secret by name. Calls inside one repository may keep `inherit`.

## The release gate

The gate is its own workflow run, so its artifacts never reach the run that
builds repo-infra's release.

- `.github/workflows/gate-mtuspy.yml` in repo-infra has `workflow_dispatch`
  and no inputs. Dispatched on a ref, it runs the pieces of that ref: mtuspy's
  CI jobs (`ri-ci-rust`, `ri-ci-rust-musl`, `ri-ci-man`) and release-build
  jobs (`ri-release-rust-binaries`, `ri-release-nfpm`, `ri-release-homebrew`)
  through `./.github/workflows/ri-*.yml`, with `repository`, `ref` and
  `version` read from the example's source record. It runs no publish piece
  and needs no secret.
- A job `gate` in repo-infra's own `release-pr.yml`, between `prepare` and
  `finish`, holds `actions: write`. It dispatches the gate on the release
  branch with `return_run_details` (the dispatch API returns the run id since
  February 2026), waits for that run and fails unless it succeeded. `finish`
  needs `gate`, so a failed gate stops the release pull request and `v2`
  does not move. Consumers' build jobs never get `actions: write`.
- `references/examples/mtuspy/source.json` records the source:
  `repository`, `ref` (a tag) and `version`.
- A test holds the gate's jobs and inputs equal to the six example caller
  jobs named above, apart from `repository`, `ref`, `version`, the D31
  skip condition in `if:`, the `needs:` on the source record, and the `@v2`
  versus `./` form of `uses:`. The example's `ci-passed`, verdict job and
  `ri-release-pr-current` are not part of the gate.
- GitHub dispatches only workflows that exist on the default branch, so the
  gate is first run after the 2.0.0 branch is merged and before the 2.0.0
  release is dispatched (see "Order of work").

## Compatibility within v2

Every consumer runs every release of `v2`, and the gate exercises only the
pieces mtuspy uses. Within `v2` a piece may:

- add an input only with a default,
- add a secret only as optional,
- add an output,

and may not remove a piece, remove or rename an input, secret or output,
change an input's `type`, make an input or secret required, or widen
`permissions:` at workflow level, on a job, or through a new job that declares
them (a called workflow cannot raise what its caller grants). Any such change
waits for `v3`.

A test compares the pieces with the commit `v2` points at. It iterates the
pieces of that commit, so a removed piece fails, and compares each
`workflow_call` interface and every `permissions:` block. After a rollback
`v2` points at the previous release, so reverting the bad release passes.
Before 2.0.0 there is no `v2`, and the test is skipped.

## The tag

- repo-infra's `.github/repo-infra.json` sets `moving_major_tag: true`;
  `ri-publish-tag` moves `v2` after the release tag.
- A tag ruleset on `v*` in repo-infra blocks updates and deletion. Its
  bypass list holds a GitHub App and the Repository admin role.
- `ri-publish-tag` gets two optional secrets, `app-client-id` and
  `app-private-key`; the repository secret `RELEASE_APP_CLIENT_ID` holds the
  App's Client ID. When both are set it mints an installation token with
  `actions/create-github-app-token` and moves the major tag with it. An
  installation token lasts one hour, so it cannot be stored as a secret, and
  a token handed over as a job output is redacted. repo-infra's caller passes
  both; consumers without them keep today's behaviour.
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
  installed plugin.
- The repo-infra entry in the `oposs/claude-plugins` marketplace sets
  `"ref": "v2"` in its source, so the installed plugin is the release `v2`
  points at, and `apply` never writes an input that `v2` does not define.
  Plugin fixes reach users with a release, as piece fixes do.
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
   `source.json` pointing at mtuspy `v0.2.1`, version `0.2.1`; the test holds
   the gate equal to them.
3. Merge; dispatch the gate on `main` by hand and fix it until it is green.
   Create the App and the tag ruleset.
4. Release 2.0.0; `v2` appears. Pin the marketplace entry to `ref: v2`.
5. Migrate mtuspy with `apply`; its callers equal the example. Release mtuspy.
6. Move `source.json` to that mtuspy release.

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
