---
description: Bring this repository up to the infrastructure standard, on a branch, through a pull request
---

Run `/repo-infra:check` first and show the user the report. If it lists an
`ambiguous` item, stop and ask the user that question before doing anything
else. `apply` refuses to guess and will raise on it anyway. If it says the
standard does not recognise this repository, stop: read
`references/teaching-the-standard.md` and teach the standard first.

Before applying, read the repository's own build, test and release setup and
compare it to what you are about to install. A block that does not fit is not a
reason to edit the repository around it. It is a gap in the standard, and
`references/teaching-the-standard.md` says what to do with one.

`apply` writes two different ways, and they need different handling:

- **File items** (`ci`, `changelog`, `release-pr`, `release-publish`,
  `dependabot`, `workflow-lib`, `container-m4`, `container`, and any other build or
  publish asset the repository has selected) commit to the local
  `repo-infra/apply` branch. Nothing leaves your machine until you push.
- **Administration items** (`default-branch`, `branch-protection` /
  `required-checks`, `no-changelog-label`, `actions-open-pr`) write straight to
  the live repository through the GitHub API, with no commit, no branch and no review.
  Confirm with the user before running any of these; renaming a branch,
  enabling a ruleset and granting Actions permission to open pull requests are
  all outward-facing.

## Land the file items before the administration items, even though `apply` no longer lets you get this wrong silently

A first-time onboarding always has both kinds pending at once. Running
`apply` with no `--item` processes the full list in one call: files, then
administration, in that order. The ruleset item's precondition asks GitHub
whether `ci.yml`/`changelog.yml` are confirmed on the default branch itself,
so committing them locally in the same call, without pushing or merging,
correctly refuses with "not on main yet" rather than enabling required checks
nobody can satisfy yet. That refusal is a safety net, not a plan. Re-running
`apply` after every refusal is slower and noisier than doing it in order once.
Split it instead:

1. **File items first**, one call per pending name (or a single bare `apply`
   if `check` shows no administration item pending):
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" apply --item ci
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" apply --item changelog
   # ...and so on, for whatever check listed as missing or outdated
   ```
2. **Push and open the pull request.** If `check` reported `no-changelog-label`
   as missing, create it first (`apply --item no-changelog-label`), or
   `gh pr create --label` will fail on a label that does not exist yet:
   ```bash
   git push -u origin repo-infra/apply
   gh pr create --fill --base main --label no-changelog
   ```
   When the upgrade installs `release-pr` v5 (D28), write the body with
   `--body` instead of `--fill`, and include this sentence: "From this
   change on, the release build and the CI run inside Create release PR see
   every repository secret; no secret may carry write access to this
   repository." When `check` reported `ci-local-seam`, `action-test-seam` or
   `release-build-local-seam`, say in the body what the file needs:
   `on: workflow_call: inputs: ref` and `ref: ${{ inputs.ref }}` on every
   `actions/checkout`. `apply` never edits those files.
   Label at creation, not after: GitHub keeps only the latest check run per
   context, so adding the label once the changelog check has already failed
   produces a fresh, skipped, green run and waves the merge through with no
   second look.
3. **Get that pull request merged into `main`.**
4. **Only then, the remaining administration items**, each confirmed first:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" apply --item actions-open-pr
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" apply --item required-checks
   ```
   `required-checks` (and its alias `branch-protection`) is the one that must
   wait for the merge, not just the commit, because it is what turns on the ruleset.

On a repository that is already onboarded, an upgrade run has no administration
item pending, and a bare `apply` followed by push and PR is enough.

## Migration to the one release flow (D28)

`apply` refuses while a release is in progress (`release-in-progress`): let
the open release pull request merge and publish, or close it, first. `apply
--item` refuses only the migration items and the items that write a release
workflow: `release-pr.yml`, `changelog.yml`, `ci.yml` (its frame and every
block), `release-publish.yml`, `release-build.yml` and the workflow library.
Administration items and other files apply. The
migration items (`release-build-rename`, `release-build-config`,
`publish-source-tarball`, `release-assets`, `cargo-lock-version-files`,
`release-pr-replace`) are one commit: they edit `.github/repo-infra.json`,
`release-build-rename` renames D26's `release-build.yml` to
`release-build-local.yml` with `git mv` and no content change, and
`release-pr-replace` replaces a `release-pr.yml` whose only marker is
`release-pr-build v1` (D26) whole with the current `release-pr` asset. A
`release-pr.yml` with any other marker `check` does not know stays a
`conflict`. After it, `apply` installs the assembled
`release-build.yml`. The ruleset gains the up-to-date rule through
`required-checks`: a bare `apply` writes it in the same run, after the file
items and before their pull request merges; with `--item`, apply it on its own
(confirm first). The rule on its own breaks nothing in the old flow.

`release-pr`, `ci` and `workflow-lib` work only together: `Create release PR`
calls `ci.yml` with the input `ref`, which only the new `ci` frame declares,
and both call functions only the new `workflow-lib` has. `apply --item ci`
alone, or a run that stops at `NeedsMerge`, leaves the pull request with some
of them old. Before that pull request merges, run `check` and apply each of
the three it still reports.

The migration comes before every other item. While a migration item is
pending, `apply --item <name>` for any other item refuses and names the
migration items; `apply --item` with any one migration item applies all of
them and stops there. A bare `apply` commits the migration first and then the
file items, rendered from the migrated configuration. The migration items act
even when `check` shows them as `conflict`, since they only edit the
configuration: `release-assets` is reported as `conflict` and `apply` adds the
missing patterns.

## If it exits with `NeedsMerge`

The file it names is not what `apply` last wrote: it has no stamp (installed
before v0.3.1) or was edited since. `apply` wrote four files under
`repo-infra/merge/` in the git dir (the error prints their full paths):
`{name}.new` (the new rendering), `{name}.current` (the file now),
`{name}.path` (which file) and `{name}.log` (the file's `git log`, newest
first).

Read the log first.

- Every commit is `Install <item> from the repo-infra standard`, `Migrate to
  ...`, or a commit that brought a repo-infra file in by hand during a
  conversion: the file has no local edits. Hand `.new` back unchanged:
  `apply --item <name> --from <path to {name}.new>`. It is written with a
  stamp and committed as `Install`, so the next upgrade goes through.
- Any other commit, including `Merge <item> ... with local edits`, may carry
  an edit. Read it (`git show <hash> -- <path>`), carry the edit into a copy
  of `.new`, and hand that back with `--from`. To see what an edit changed,
  compare with `git show <hash>:<path>` at the last `Install` commit before
  it.
- The log reads `(no history: ...)`: there is nothing to tell an edit by.
  Compare `.current` with `.new`; any difference beyond the generation change
  is an edit to carry over.

If the apply pull request was squash-merged, the `Install` subjects live in
the body of the squash commit; `git show <hash>` shows them.

The merged file must carry the new marker version. One that differs from
`.new` is committed as `Merge <item> from the repo-infra standard with local
edits` and stops the next upgrade again. For an asset that ships several
files, such as `workflow-lib`, the merge covers the one file the error names,
and nothing else is written until it is back. Run `apply` again
afterwards: it upgrades the remaining files, or names the next one. Never drop
a local edit: it is there for a reason, and the reason is usually not visible
in the diff.

## If it refuses an administration item

Read the refusal; each one names the concrete next action, not just what went
wrong. `default-branch` never applies automatically: renaming breaks links,
forks and clones that pin the old name, so it always tells the user to rename
by hand in Settings → General, then re-run `check`.

`required-checks`/`branch-protection` can refuse two different ways, and they
mean different things. "not on `main` yet" is a confirmed absence: merge the
file items' pull request and retry. "could not confirm" means the check
against GitHub itself failed (network, permissions). It is not evidence
either way, so retry it rather than assuming the workflow is or isn't there.
