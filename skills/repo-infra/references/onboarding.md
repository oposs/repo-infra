# Onboarding a repository

How to bring a repository that is not in the fold onto the standard. Onboarding
brings the project up to its full shape: the CI and the release flow, and every
rule `references/project-shape.md` sets for a project of its kind. In most
repositories that is real work: more Unix-like platforms, `.deb` and `.rpm`
packages in the Gitea registry, a Homebrew formula, a manual, a README with
badges and install snippets, a demo. The default for every such item is to do
it. A rule the project does not meet today is an item of that work.

An exception is for what the program cannot do, such as a terminal program
built on a pty, `fork` and Unix sockets that has no Windows build, or for what
the owner rules out. It records that reason in `exceptions` in
`.github/repo-infra.json`.

repo-infra does not decide what a repository needs: you read it, choose pieces
from `references/catalogue.md`, and write the callers that call them. `check`
reports what is wrong and never gates the work.

A repository with the v1 layout (copied `ri-*.yml` files, `.github/workflows/lib/`,
the old `changelog.yml` and `release-pr.yml`) is not onboarded again. It runs
`apply`, which migrates it in one pull request (below).

GitHub refuses every run that calls a piece, `ci-passed` included, unless the
organisation's Actions policy (Settings, Actions, General, "Policies") allows
the reusable workflows of `oposs/repo-infra`: all actions and reusable
workflows, or `oposs/repo-infra/.github/workflows/*` listed under "Allow
specified actions and reusable workflows".

## The procedure

1. **Read the repository's real setup.** The Makefile or build file, the
   existing workflows, how a release happens today, the README and the docs.
2. **Review the shape before writing anything.** Run the shape review of
   `commands/check.md` against `references/project-shape.md`. Every rule that
   reads `gap` becomes an item of the work plan.
3. **Find the platforms by trying.** For a program users install, ask which
   Unix-like systems it runs on (Linux, macOS, illumos) and whether it runs on
   Windows, and answer by compiling for each target of `native-targets`, for
   example `cargo check --target x86_64-unknown-illumos` after
   `rustup target add`. A comment or a README line such as "never tested on a
   Mac" is not evidence. A target fails only for a reason in the program, an API
   the system lacks (a pty, `fork`, `setsid`, Unix sockets on Windows); a missing
   cross linker or C toolchain on the build machine is not one.
4. **Map each need to a piece.** One line per need: the piece, or "no piece
   fits". A release built another way today, such as packages from `cargo-deb`,
   moves to the piece, and the old build goes.
5. **Present one work plan.** The full difference between the project today and
   the standard, grouped:

   - CI: the pieces `ci.yml` calls, and the `rust` key or other config they need.
   - Release targets: every target of `native-targets` the program builds for.
   - Packages and channels: `.deb` and `.rpm` through `ri-release-nfpm` and
     `ri-publish-gitea`, the Homebrew formula, crates.io.
   - Documentation: the manual, the README (`readme-current`, `badges`,
     `install-text`), the demo or the screenshot, the `writing-style` review.

   Every item reads "do". Below the plan, apart from it, list the real gaps:
   a need no piece fits, and a target the program cannot run on that the piece
   cannot leave out. Each is a stage-1 question of
   `references/teaching-the-standard.md`, put to the owner as a question about
   the standard. Add the questions of "Questions to ask" below. The owner's
   answer settles the plan: an item they rule out becomes an exception with
   their reason.
6. **Write the callers and install the build files.** A new repository copies
   the five callers (`ci.yml`, `release-build.yml`, `release-publish.yml`,
   `release-pr.yml`, `changelog.yml`) from `references/examples/mtuspy/` and
   adapts them; `assets/callers/` holds the word-for-word parts (`changelog.yml`,
   `release-pr.yml`, the jobs `release-verdict` and `ci-passed`). Each job calls a piece
   from the catalogue with its `Call:` snippet, which reads
   `uses: oposs/repo-infra/.github/workflows/<piece>.yml@v2`. Build files are
   the only pieces installed, one at a time:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" apply --item man
   ```

   `apply --item <piece>` installs a build file (`man`, `man-lua`, `container`,
   `container-m4`, `dependabot`) that is not there yet, on the `repo-infra/apply`
   branch, as one commit named `Install <piece> vN from the repo-infra standard`.
   A bare `apply` installs every missing core build file. Write
   `.github/repo-infra.json` from the closest example in
   `references/examples/repo-infra/` or, for a Rust program users install,
   `references/examples/mtuspy/`, with the `exceptions` the plan agreed.
7. **Do the rest of the plan.** Write the manual (the `man-pages` skill), the
   `nfpm.yaml`, the formula from the template in `references/project-shape.md`,
   the README and the demo. The plan says which pull request carries each item.
8. **Run the script until it exits 0.** It reads the callers against the pieces
   they call, so a misspelt input or a missing `needs:` entry shows up before
   the first run on GitHub does.
9. **Review the shape again.** Every rule now reads `met`, `excepted` or `does
   not apply`. A `gap` is an item of the plan not yet done, and says so.
10. **Open the pull request with the `no-changelog` label at creation.** GitHub
    keeps only the latest check run per context, so a label added after the
    changelog check failed produces a green, skipped run and waves the merge
    through. Apply the administration items in the order below, each one confirmed
    with the user first: the rename and the label before the push, the rest
    after the merge.

A piece is never edited in the repository, and a called workflow cannot be.
Whatever the repository needs that the piece does not do goes into a caller,
into `ci-local.yml`, or into a new piece (`references/teaching-the-standard.md`).

## Known traps

- **A root `Cargo.toml` that is both `[package]` and `[workspace]`.** Its
  default members differ from its members, and `rust-plan` in `ri-ci-rust`
  fails on the first CI run unless `"rust"` in `.github/repo-infra.json` names
  the crates to lint and test. `check` does not see this. Write the key in step
  6 (`references/conventions.md`, "The `rust` key").
- **A target the program cannot build and the piece cannot skip.** The
  exception alone does not help: the release build still fails on that target.
  The missing input is a gap in the standard; teach it
  (`references/teaching-the-standard.md`) and pair the input with the
  exception, as `references/project-shape.md` says under "Exceptions".
- **Old claims in the code.** A comment in `Cargo.toml` or the README about
  where the program runs was true once, or never. Step 3 replaces it with a
  compile attempt.

## Migrating the v1 layout

`check` reports every file of the v1 layout as `outdated` and says to run
`apply`. A bare `apply` on such a repository writes one commit on the
`repo-infra/apply` branch, named `Migrate to the repo-infra v2 layout`:

- it removes the copied `ri-*.yml` files, `.github/workflows/lib/` and
  `ri-ci-lib.yml`;
- it points every `uses: ./.github/workflows/ri-...` at
  `oposs/repo-infra/.github/workflows/<piece>.yml@v2` and replaces
  `secrets: inherit` on those calls with the secrets by name;
- it adds the job `release-verdict` to `ci.yml`, rewrites `ci-passed` to the
  v2 form and leaves every other line of the file alone;
- it writes `changelog.yml` and `release-pr.yml` as the v2 callers, when they are
  absent or still carry the v1 marker; a file already in the v2 form stays.

A copy with local edits is removed as well. The commit body and the output list
those edits (`The migration removed these local changes`); git keeps them, and
each is ported to a caller or dropped. Then run the script until it exits 0.

Before the migration merges, check the organisation's Actions policy (see the
top of this page): v1 ran only the repository's own workflows, so a policy that
does not allow `oposs/repo-infra` went unnoticed until now.

## Callers

The repository owns these files. A caller is short: it calls pieces with
`uses: oposs/repo-infra/.github/workflows/<piece>.yml@v2`, passes `with:` and
each secret by name, and holds the repository's own jobs or calls `ci-local.yml` for them. The
catalogue gives a caller snippet for each piece.

`ci.yml` triggers on `push` and `pull_request` to `main` and on
`workflow_call` with the input `ref`, because Create release PR runs it on the
release branch. A call of a repository's own file (`ci-local.yml`,
`release-build.yml`, `action-test.yml`) stays `uses: ./.github/workflows/<file>`
and may write `secrets: inherit`; a call of a repo-infra piece never does, because
GitHub hands a workflow of another organisation empty inherited secrets.
Every job except `release-verdict` and `ci-passed` is a call (or an inline job)
that takes `ref: ${{ inputs.ref }}`. Copy the jobs
`release-verdict` (a call of `ri-release-verdict`) and `ci-passed` from
`assets/callers/ci-passed.yml` in the skill word for word and fill in the
`needs:` of `ci-passed` with every other job of the file. `ci-passed` stays an inline job because a
job that calls a reusable workflow reports as `ci-passed / <job>`, and the
ruleset requires the context `ci-passed`. `check` compares the job with that
file and reports a difference.

Every job of `ci.yml` other than `ci-passed` carries the `if:` of
`assets/callers/release-pr-skip.yml` in the skill, alone or joined with `&&` to
a further condition (D31). It is false only on the `pull_request` run of the
release pull request Create release PR opened. That run parks for approval,
Create release PR has already tested the commit, and `ci-passed` ignores the
test results there (`release-verdict` carries no such `if:`, because its verdict
is what decides there); approved without the `if:`, it builds and tests everything
a second time. The condition tests the same three fields as `isReleasePr` in
`lib/release.js`: the head branch starts with `release/`, the head is in this
repository, and `github-actions[bot]` opened the pull request. A looser one
would skip the tests of a person's or a fork's `release/x` pull request, which
`ci-passed` judges by the ordinary rules, and a skipped job counts as passed
there. When Create release PR calls `ci.yml` the event is `workflow_dispatch`,
so the jobs run.

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
- Every other job of `ci.yml` has the `if:` of
  `assets/callers/release-pr-skip.yml`, alone or joined with `&&`, never with
  `||`. Without it, approving the parked run on a release pull request builds
  and tests everything a second time.
- `finalize` has `if: needs.publish.outputs.release_id != ''`, alone or joined
  with `&&` to a further condition other than `always()`, and passes
  `release_id`, `tag` and `head` from the `publish` job's outputs, as the
  `Call:` header of `ri-publish-finalize` shows. Without the `if:` it runs after
  every push of `CHANGES.md`, also one that publishes nothing, and fails.
- Each call passes only inputs the called file declares and passes every
  required input. A call of a repo-infra piece passes every required secret by
  name (`secrets: inherit` is a finding); a call of the repository's own file
  passes them or writes `secrets: inherit`.
- Each call of a repo-infra piece reads
  `uses: oposs/repo-infra/.github/workflows/<piece>.yml@v2`: the file must be a
  piece and the ref exactly `v2`. A call of a copy through `./` is the v1 layout.
- Each call job grants at least the token permissions the called file asks for,
  recursively. A called workflow can only lower what it receives, so a job with
  too little makes GitHub refuse to start the run.
- Every checkout in `ci.yml` (except in `ci-passed`) and `release-build.yml`,
  and in every project-owned workflow called with `ref`, has
  `ref: ${{ inputs.ref }}`. In `ci.yml` and `release-build.yml`, every call to a
  file that declares `ref` passes `ref: ${{ inputs.ref }}`.
- Only the release build uploads artifacts named `release-asset-*` or
  `release-files`.
- Calls of other repositories' workflows are not reviewed.
- `changelog.yml` and `release-pr.yml` match `assets/callers/`, apart from the
  jobs a repository adds to `release-pr.yml` between `prepare` and `finish`.
- `ci.yml` and `changelog.yml` carry no `paths` or `paths-ignore` filter.
- No workflow of the repository pins an action at an older major than the
  pieces or another of its workflows do (`docs.yml` at
  `actions/upload-artifact@v4`, the pieces at `v7`). Dependabot raises an
  action to one version in every workflow, and its pull request from `v4`
  would downgrade the files already past it; raise the old pin before
  dependabot runs.

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
   need as green. The `if:` of D31 on the job in `ci.yml` that calls the file is
   the one exception: it skips only where `ci-passed` ignores the results.

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

A plugin in a subdirectory, which a marketplace entry with a `git-subdir`
source installs without the rest of the repository, takes the same entry with
its own path, for example `"path": "plugin/.claude-plugin/plugin.json"`; one
entry per plugin. `ri-ci-claude-plugin` finds every tracked
`.claude-plugin/plugin.json` and needs no input for it. When the root holds a
`.claude-plugin/marketplace.json`, its entries for this repository must point
at a directory with a `.claude-plugin/plugin.json`:

```json
{
  "name": "my-plugin",
  "source": {
    "source": "git-subdir",
    "url": "https://github.com/owner/repo.git",
    "path": "plugin"
  }
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
- **Who holds the copyright?** A company or a person. The answer goes into
  `LICENSE` and into COPYRIGHT of the manual, and the two must agree. In a
  repository owned by an organisation, suggest the company; in a personal
  repository, the person. Ask also when `LICENSE` already names a holder, and
  correct `LICENSE` first if the answer differs.

The answer picks `ri-ci-node-pnpm` or `ri-ci-node-bun`. No piece covers npm
alone; that is a gap (`references/teaching-the-standard.md`).

Candidates a repository's files suggest but do not decide:

- `docs/manual.md` suggests `ri-ci-man`, with the `man` and `man-lua` pieces
  and `MAN_NAME` plus `include build/man.mk` in the Makefile (the `man-pages`
  skill has the rest). A program with a command line and no manual gets one,
  written during the onboarding (`man-page` in `references/project-shape.md`).
- `configure.ac` with `cpanfile` suggests `ri-release-source-tarball`, which
  builds the `make dist` tarball before the release pull request exists.
- `Cargo.toml` with a binary users install suggests `ri-release-rust-binaries`,
  `ri-release-nfpm` with an `nfpm.yaml`, and `ri-release-homebrew` with
  `Formula/<bin>.rb` from the template in `references/project-shape.md`, all
  three also when the release has no archives, packages or formula today.
- `go.mod` with a main package users install suggests `ri-release-go-binaries`
  with `package` naming that main package, and `ri-release-nfpm` and
  `ri-release-homebrew` as for Rust.
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
   open the pull request with the label `no-changelog`, and get it merged. When
   `check` reports `classic-protection`, follow "A repository with classic
   branch protection" below instead.
4. **`required-checks`** (alias `branch-protection`): enables the ruleset that
   requires `ci-passed` and `changelog-updated` and an up-to-date branch. It
   asks GitHub, not the checkout, whether both workflows are on the default
   branch, and refuses with "not on main yet" until they are. A required check
   whose workflow does not exist blocks every pull request, including the one
   that would install it.
5. **`actions-open-pr`**: lets Actions create and approve pull requests, which
   Create release PR needs.
6. **`delete-merged-branches`**: switches on "Automatically delete head
   branches", so a merged release pull request does not leave its
   `release/vX.Y.Z` branch behind.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" apply --item required-checks
```

### A repository with classic branch protection

The standard protects `main` with a ruleset. Classic branch protection is
removed, never kept, and `check` reports it as the `classic-protection` conflict
with every status check it requires. A classic rule that requires a check the
onboarding replaced blocks the onboarding pull request with every check green:
oetiker/tvision-rs#29 waited for `test`, which no workflow produced any more.
The order changes for such a repository:

1. **Push `repo-infra/apply` and open the onboarding pull request**, labelled
   `no-changelog`. Do not merge it yet.
2. **`required-checks`**: with classic protection present, it accepts `ci.yml`
   and `changelog.yml` on the pushed `repo-infra/apply` branch as well as on
   `main`. The onboarding pull request produces `ci-passed` and
   `changelog-updated` itself.
3. **`classic-protection`**: deletes classic protection from the default branch.
   It refuses until an active ruleset on the default branch requires
   `ci-passed` and `changelog-updated`, so `main` is never left unprotected.
4. **Merge the onboarding pull request.**

Every other pull request open at that point stays blocked until it is rebased
onto `main` after the merge, since its branch has neither workflow.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" apply --item required-checks
python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" apply --item classic-protection
```
