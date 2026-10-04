# Onboarding a repository

How to bring a repository that is not in the fold onto the standard. repo-infra
does not decide what a repository needs: you read it, choose pieces from
`references/catalogue.md`, copy them, and write the callers. `check` reports
what is wrong and never gates the work.

## The procedure

1. **Read the repository's real setup.** The Makefile or build file, the
   existing workflows, how a release happens today.
2. **Map each need to a piece.** Show the user the mapping, one line per need:
   the piece, or "no piece fits".
3. **For a need no piece fits, ask the user.** That is stage 1 of
   `references/teaching-the-standard.md`. Never patch the repository around
   the gap.
4. **Copy the pieces 1:1.** One piece at a time:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" apply --item ri-ci-python
   ```

   `apply --item <piece>` installs a piece that is not there yet, on the
   `repo-infra/apply` branch, as one commit named `Install <piece> vN from the
   repo-infra standard`. Install the core pieces (`changelog`, `release-pr`,
   `workflow-lib`, `dependabot`, `ri-ci-lib`, `ri-release-pr-current`,
   `ri-publish-tag`, `ri-publish-finalize`) the same way, or let a bare `apply`
   install every missing core piece in one run. Then write the callers and
   `.github/repo-infra.json`, starting from the closest example in
   `references/examples/repo-infra/`.
5. **Run `check` until it exits 0.** It reads the callers against the pieces
   they call, so a misspelt input or a missing `needs:` entry shows up before
   the first run on GitHub does.
6. **Open the pull request with the `no-changelog` label at creation.** GitHub
   keeps only the latest check run per context, so a label added after the
   changelog check failed produces a green, skipped run and waves the merge
   through. Apply the administration items in the order below, each one confirmed
   with the user first: the rename and the label before the push, the rest
   after the merge.

A piece is never edited in the repository. Whatever the repository needs that
the piece does not do goes into a caller, into `ci-local.yml`, or into a new
piece (`references/teaching-the-standard.md`).

## Callers

The repository owns these files. A caller is short: it calls pieces with
`uses: ./.github/workflows/<piece>.yml`, passes `with:` and `secrets: inherit`,
and holds the repository's own jobs or calls `ci-local.yml` for them. The
catalogue gives a caller snippet for each piece.

`ci.yml` triggers on `push` and `pull_request` to `main` and on
`workflow_call` with the input `ref`, because Create release PR runs it on the
release branch. Every job is a call (or an inline job) that takes
`ref: ${{ inputs.ref }}`, followed by `ci-passed`. Copy `ci-passed` from
`assets/callers/ci-passed.yml` in the skill word for word and fill in its
`needs:` with every other job of the file. It stays an inline job because a
job that calls a reusable workflow reports as `ci-passed / <job>`, and the
ruleset requires the context `ci-passed`. `check` compares the job with that
file and reports a difference.

`release-build.yml` triggers on `workflow_call` with the inputs `version` and
`ref`. It calls the build pieces (`ri-release-source-tarball`, for example) and the
project's own `release-build-local.yml`.

`release-publish.yml` triggers on `push` to `main` with `paths: [CHANGES.md]`,
carries `concurrency:` with `group: release-publish` and `cancel-in-progress:
false`, and has one job `publish` calling `ri-publish-tag`, the publish pieces
(`ri-publish-crates-io`, `ri-publish-gitea`) and the closing job `finalize`
calling `ri-publish-finalize`. The concurrency group keeps two publish runs
from overlapping; without it a second merge starts a run while the first is
still attaching files. The file has no `workflow_dispatch` trigger on purpose:
publishing is a consequence of merging a release pull request, never something
started from a dropdown, and a re-run of a failed run reads the same version
from `CHANGES.md` and finishes the job. The comment in repo-infra's own
`.github/workflows/release-publish.yml` says the same.

What `check` enforces on the callers:

- `ci.yml` runs on `push` and `pull_request` to `main` and calls
  `ri-release-pr-current`. Without the `pull_request` trigger `ci-passed` never
  reports and every pull request waits for it.
- `release-publish.yml` runs on `push` to `main` with `paths: [CHANGES.md]` and
  no other path, carries `concurrency:` with `group: release-publish` and
  without `cancel-in-progress: true`, and has no `workflow_dispatch` trigger.
- Every `needs:` list is complete. `ci-passed` needs every other job of
  `ci.yml` and `finalize` needs every other job of `release-publish.yml`. A
  missing entry lets a release go public while a job it should have waited for
  is still running.
- `ci-passed` has `if: always()`. Without it the job is skipped when a need
  fails, and a skipped required check counts as passed.
- `finalize` has `if: needs.publish.outputs.release_id != ''`, alone or joined
  with `&&` to a further condition other than `always()`, and passes
  `release_id`, `tag` and `head` from the `publish` job's outputs, as the
  `Call:` header of `ri-publish-finalize` shows. Without the `if:` it runs after
  every push of `CHANGES.md`, also one that publishes nothing, and fails.
- Each call passes only inputs the called file declares, passes every required
  input, and passes every required secret or writes `secrets: inherit`.
- Each call job grants at least the token permissions the called file asks for,
  recursively. A called workflow can only lower what it receives, so a job with
  too little makes GitHub refuse to start the run.
- Every checkout in `ci.yml` (except in `ci-passed`) and `release-build.yml`,
  and in every project-owned workflow called with `ref`, has
  `ref: ${{ inputs.ref }}`. In `ci.yml` and `release-build.yml`, every call to a
  file that declares `ref` passes `ref: ${{ inputs.ref }}`.
- Only the release build uploads artifacts named `release-asset-*` or
  `release-files`.
- No call names a workflow in another repository. Everything stays local.
- Every installed workflow piece that has a `Call:` snippet is called by some
  workflow. One that nothing calls never runs.
- `ci.yml` and `changelog.yml` carry no `paths` or `paths-ignore` filter.

## Project-owned workflows

Three files hold what the repository does itself. They are not pieces: not
shipped, not versioned, not replaced by `apply`. A caller calls them, and
`check` reads them like any callee.

- `ci-local.yml`: the repository's own CI jobs, called from `ci.yml`.
- `release-build-local.yml`: the repository's own release build, called from
  `release-build.yml`.
- `action-test.yml`: the test of a GitHub Action, which runs the action with
  `uses: ./` and real inputs, called from `ci.yml`.

What each must do:

1. **Trigger on `workflow_call` and nothing else.** A `push` or `pull_request`
   trigger beside it runs every job twice, once directly and once through
   `ci.yml`, which reads as flakiness.
2. **Set `timeout-minutes` on every job.** GitHub rejects `runs-on`, `steps`
   and `timeout-minutes` on a job that calls a reusable workflow, so the timeout
   has to come from inside.
3. **Declare the input `ref` and check it out.** `on: workflow_call: inputs:
   ref`, and `ref: ${{ inputs.ref }}` on every `actions/checkout`. Create
   release PR runs `ci.yml` on the release branch and passes that commit down;
   a checkout without it tests `main` and reports the release as tested.
4. **Ask for no more than `contents: read`.**
5. **Keep conditions inside steps, never on a job.** A reusable workflow whose
   every job is skipped reports as skipped, and `ci-passed` counts a skipped
   need as green.

`release-build-local.yml` also takes the string inputs `version` and `ref`,
uploads each file the release ships as an artifact whose name starts with
`release-asset-`, and uploads repository files the build rewrote (a Homebrew
formula, for example) as one artifact named `release-files`. Each path in
`release-files` is a repository path and is listed in `release_files` in
`.github/repo-infra.json`. Stage them in a directory whose tree holds the
repository paths, because `upload-artifact` strips the common parent: uploading
`Formula/mdmost.rb` directly yields `mdmost.rb`, which the release refuses as
undeclared. Files with the same name in several `release-asset-*` artifacts
overwrite each other. A file named `release-build.json` is refused: that name
is the build record the release writes itself. `release_assets` lists the name
patterns the release must carry.

The build and the CI run get the repository's secrets, so no repository secret
may carry write access to the repository. A classic personal access token with
`repo` scope breaks that rule.

## version_files by build file

`version_files` in `.github/repo-infra.json` lists every file Create release PR
rewrites with the new version. Each entry has a `path`, a `pattern` that
matches the current version, a `replacement` and a `verify` pattern the release
reads back to confirm the write. Add the entries for the build files the
repository has.

`.claude-plugin/plugin.json`:

```json
{
  "path": ".claude-plugin/plugin.json",
  "pattern": "\"version\"\\s*:\\s*\"[^\"]*\"",
  "replacement": "\"version\": \"$VERSION\"",
  "verify": "\"version\"\\s*:\\s*\"$VERSION\""
}
```

`pyproject.toml` and `Cargo.toml`:

```json
{
  "path": "pyproject.toml",
  "pattern": "^version\\s*=\\s*\"[^\"]*\"",
  "replacement": "version = \"$VERSION\"",
  "verify": "^version\\s*=\\s*\"$VERSION\""
}
```

For `Cargo.toml` change `path` and keep the rest.

`package.json` (pnpm or bun):

```json
{
  "path": "package.json",
  "pattern": "\"version\"\\s*:\\s*\"[^\"]*\"",
  "replacement": "\"version\": \"$VERSION\"",
  "verify": "\"version\"\\s*:\\s*\"$VERSION\""
}
```

`VERSION` (Perl autotools repositories, with `configure.ac` and `cpanfile`):

```json
{
  "path": "VERSION",
  "pattern": "^[0-9][^\\n]*$",
  "replacement": "$VERSION",
  "verify": "^$VERSION$"
}
```

A repository with a `Cargo.lock` needs one more entry per crate the release
versions: the root package, and every workspace member that takes its version
from `[workspace.package]` (`version.workspace = true`). A member with a version
of its own, such as a vendored crate, is not released with the repository. The
release pull request commits only the paths listed in `version_files`, so a
lockfile left out keeps the old version: mdmost v0.1.1 was tagged with
`Cargo.toml` at 0.1.1 and `Cargo.lock` at 0.1.0, and the publish failed under
`cargo --locked`. For a crate named `mdmost`:

```json
{
  "path": "Cargo.lock",
  "pattern": "^name = \"mdmost\"\nversion = \"[^\"]*\"",
  "replacement": "name = \"mdmost\"\nversion = \"$VERSION\"",
  "verify": "^name = \"mdmost\"\nversion = \"$VERSION\""
}
```

Go, the Checkmk plugin, the GitHub Action and Perl `Makefile.PL` repositories
have no entry here. Name the file that holds their version if they keep one.

## Questions to ask

Ask these before choosing. Do not answer them yourself.

- **`pnpm-lock.yaml` and `package-lock.json` are both present.** Which package
  manager is authoritative? Installing CI for the wrong one resolves different
  dependency versions than the developer does. Options: pnpm, npm.
- **`pnpm-lock.yaml` and `bun.lock` are both present.** Which package manager is
  authoritative? Same risk. Options: pnpm, bun.
- **`bun.lock` and `package-lock.json` are both present.** Which package manager
  is authoritative? Same risk. Options: bun, npm.

The answer picks `ri-ci-node-pnpm` or `ri-ci-node-bun`. No piece covers npm
alone; that is a gap (`references/teaching-the-standard.md`).

Candidates a repository's files suggest but do not decide:

- `docs/manual.md` suggests `ri-ci-man`, with the `man` and `man-lua` pieces
  and `MAN_NAME` plus `include build/man.mk` in the Makefile (the `man-pages`
  skill has the rest).
- `configure.ac` with `cpanfile` suggests `ri-release-source-tarball`, which
  builds the `make dist` tarball before the release pull request exists.
- `book.toml` is a documentation site. No piece covers it.

## Administration items

These change the live repository through the GitHub API, with no commit and no
review, and each is outward-facing. Apply them one at a time with `apply
--item`, and confirm each with the user first. The order matters:

1. **`default-branch`**: rename the default branch to `main` by hand in
   Settings, General. `apply` never does this: a rename breaks links, forks and
   clones that pin the old name. Run `check` afterwards.
2. **`no-changelog-label`** when `check` reports it missing: creates the label
   the pull request of the next step carries and dependabot requests.
3. **Land `ci.yml` and `changelog.yml` on `main`**: push `repo-infra/apply`,
   open the pull request with the label `no-changelog`, and get it merged.
4. **`required-checks`** (alias `branch-protection`): enables the ruleset that
   requires `ci-passed` and `changelog-updated` and an up-to-date branch. It
   asks GitHub, not the checkout, whether both workflows are on the default
   branch, and refuses with "not on main yet" until they are. A required check
   whose workflow does not exist blocks every pull request, including the one
   that would install it.
5. **`actions-open-pr`**: lets Actions create and approve pull requests, which
   Create release PR needs.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" apply --item required-checks
```
