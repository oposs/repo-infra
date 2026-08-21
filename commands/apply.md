---
description: Bring this repository up to the infrastructure standard, on a branch, through a pull request
---

Run `/repo-infra:check` first and show the user the report. If it lists an
`ambiguous` item, stop and ask the user that question before doing anything
else — `apply` refuses to guess and will raise on it anyway. If it says the
standard does not recognise this repository, stop: read
`references/teaching-the-standard.md` and teach the standard first.

Before applying, read the repository's own build, test and release setup and
compare it to what you are about to install. A block that does not fit is not a
reason to edit the repository around it — it is a gap in the standard, and
`references/teaching-the-standard.md` says what to do with one.

`apply` writes two different ways, and they need different handling:

- **File items** (`ci`, `changelog`, `release-pr`, `release-publish`,
  `dependabot`, `workflow-lib`, `container-test`, and any other build or
  publish asset the repository has selected) commit to the local
  `repo-infra/apply` branch. Nothing leaves your machine until you push.
- **Administration items** (`default-branch`, `branch-protection` /
  `required-checks`, `no-changelog-label`, `actions-open-pr`) write straight to
  the live repository through the GitHub API — no commit, no branch, no review.
  Confirm with the user before running any of these; renaming a branch,
  enabling a ruleset and granting Actions permission to open pull requests are
  all outward-facing.

## Land the file items before the administration items, even though `apply` no longer lets you get this wrong silently

A first-time onboarding always has both kinds pending at once. Running
`apply` with no `--item` processes the full list in one call — files, then
administration, in that order. The ruleset item's precondition asks GitHub
whether `ci.yml`/`changelog.yml` are confirmed on the default branch itself,
so committing them locally in the same call, without pushing or merging,
correctly refuses with "not on main yet" rather than enabling required checks
nobody can satisfy yet. That refusal is a safety net, not a plan — re-running
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
   as missing, create it first — `apply --item no-changelog-label` — or
   `gh pr create --label` will fail on a label that does not exist yet:
   ```bash
   git push -u origin repo-infra/apply
   gh pr create --fill --base main --label no-changelog
   ```
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
   wait for the merge, not just the commit — it is what turns on the ruleset.

On a repository that is already onboarded, an upgrade run has no administration
item pending, and a bare `apply` followed by push and PR is enough.

## If it exits with `NeedsMerge`

The file it names carries local edits. Read the three files it wrote under
`.git/repo-infra/merge/` (`{name}.base`, `{name}.new`, `{name}.current`), merge
the new asset into the local edits by hand, save the result anywhere, and hand
it back: `apply --item <name> --from <path to your merge>`. Never overwrite the
local edits outright — they are there for a reason, and the reason is usually
not visible in the diff.

## If it refuses an administration item

Read the refusal; each one names the concrete next action, not just what went
wrong. `default-branch` never applies automatically — renaming breaks links,
forks and clones that pin the old name, so it always tells the user to rename
by hand in Settings → General, then re-run `check`.

`required-checks`/`branch-protection` can refuse two different ways, and they
mean different things. "not on `main` yet" is a confirmed absence — merge the
file items' pull request and retry. "could not confirm" means the check
against GitHub itself failed (network, permissions) — it is not evidence
either way, so retry it rather than assuming the workflow is or isn't there.
