---
description: Bring this repository up to the infrastructure standard, on a branch, through a pull request
---

Run `/repo-infra:check` first and show the user the report. If a piece reads
`edited`, ask the user before acting on it. If the repository has no pieces yet,
it is an onboarding: follow `references/onboarding.md` in the skill, where
`apply --item <piece>` copies each piece.

Before applying, read the repository's own build, test and release setup and
compare it to what you are about to install. A need no piece fits is not a
reason to edit the repository around it. It is a gap in the standard, and
`references/teaching-the-standard.md` says what to do with one.

`apply` writes two different ways, and they need different handling:

- **Pieces** (every row of the `pieces` section of `check`) are written to the
  working tree of the local `repo-infra/apply` branch, one commit per piece.
  Nothing leaves the machine until you push.
- **Administration items** (`default-branch`, `branch-protection` /
  `required-checks`, `no-changelog-label`, `actions-open-pr`) write straight to
  the live repository through the GitHub API, with no commit, no branch and no
  review. They run only with `--item`. Confirm each with the user first:
  renaming a branch, enabling a ruleset and granting Actions permission to open
  pull requests are all outward-facing.

## Bare `apply`

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" apply
```

Bare `apply` installs and replaces pieces, prints what it did and stops. It
never edits a caller or the config. In order:

1. It refuses while a release is in progress (`release-in-progress`): an open
   release pull request, or a latest released version in `CHANGES.md` that has
   no tag yet (checked when GitHub's tag list could be read). This
   blocks the install of every piece, not only the release-flow pieces, because
   the pieces call each other and a new copy cannot finish a release the old
   one started. Let the release pull request merge and publish, or close it,
   then run `apply` again.
2. It installs every pending piece that has no local edit: each outdated piece,
   each core piece that is missing, and each piece an installed piece needs.
   Each is one commit named `Install <piece> vN from the repo-infra standard`.
3. Merges run last. When a piece has an edited file, `apply` installs all the
   other pending pieces first and then stops with the merge hand-back for the
   first edited piece (see below).
4. It prints the upgrade notes of every version it crossed, so a piece that went
   from v2 to v4 prints the notes of v3 and v4. They say what a caller or the
   config must change.
5. It prints the findings: what `check` now reports about the callers and the
   config, and the edited files a piece no longer ships. When `apply` stops for a
   merge it prints the notes but not the findings; run `check` after the merge.

Then you change the callers and the config from the notes and findings, and run
`check` until it exits 0.

### What it does with each file

One rule applies per file, for a bare `apply` and for `apply --item`:

- A shipped file at published bytes, or absent, is written.
- An edited file whose marker claims an older version than the piece, or none,
  is a merge candidate.
- An edited file that claims the current or a newer version is never written and
  never merged. There is nothing to merge into it, and writing it would be a
  downgrade. `check` and `apply` name it. A newer claim means the plugin is out
  of date. For a current claim, delete the file and run `apply --item <piece>`: the file
  then counts as absent, and `apply` writes the published one.

Files an older version shipped and the new one does not (dropped files) are
removed when their bytes are a published version. A dropped file with local edits
is left where it is and named in the findings; remove it by hand if nothing
uses it.

## One piece with `--item`

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" apply --item ri-ci-python
```

`apply --item <piece>` does the same for one piece, and installs it when it is
not there yet. That is how a repository copies the pieces it chooses from the
catalogue. The release check of step 1 applies to it as well.

## Administration items, push, merge

The order is one sequence, the same as in `references/onboarding.md`:

1. **Before the push**, each confirmed with the user:
   - `default-branch`: rename the default branch to `main` by hand in Settings,
     General (`apply --item default-branch` only says so), then run `check`.
     `gh pr create --base main` fails while the default branch has another name.
   - `no-changelog-label`, when `check` reports it missing:

     ```bash
     python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" apply --item no-changelog-label
     ```

2. **Push and open the pull request** with the label at creation:

   ```bash
   git push -u origin repo-infra/apply
   gh pr create --fill --base main --label no-changelog
   ```

   When the upgrade installs `release-pr` v5 or later, write the body with
   `--body` instead of `--fill`, and include this sentence: "From this change on,
   the release build and the CI run inside Create release PR see every repository
   secret; no secret may carry write access to this repository." Label at
   creation, not after: GitHub keeps only the latest check run per context, so
   adding the label once the changelog check has failed produces a fresh,
   skipped, green run and waves the merge through with no second look.
3. **Get that pull request merged into `main`**, so `ci.yml` and `changelog.yml`
   are on the default branch.
4. **After the merge**, each confirmed with the user:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" apply --item required-checks
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" apply --item actions-open-pr
   ```

   `required-checks` (alias `branch-protection`) turns on the ruleset, which is
   why it waits for the merge. `references/onboarding.md` has the reasons for the
   order.

On a repository that is already onboarded, an upgrade has no administration item
pending: a bare `apply`, the caller changes, a push and the pull request are
enough.

## If it exits with `NeedsMerge`

The piece named has a file whose bytes match no published version, and whose
marker claims an older version or none. `apply` wrote four files under
`repo-infra/merge/` in the git dir (the error prints their full paths):
`{name}.new` (the new version), `{name}.current` (the file now), `{name}.path`
(which file) and `{name}.log` (the file's `git log`, newest first).

Read the log first.

- Every commit is `Install <piece> vN from the repo-infra standard`, or a
  commit that brought a repo-infra file in by hand during a conversion: the file
  has no local edits. Hand `.new` back unchanged; it is committed as `Install`.
- Any other commit, including `Merge <piece> vN from the repo-infra standard with
  local edits`, may carry an edit. Read it (`git show <hash> -- <path>`), carry
  the edit into a copy of `.new`, and hand that back with `--from`. To see what
  an edit changed, compare with `git show <hash>:<path>` at the last `Install`
  commit before it.
- The log reads `(no history: ...)`: there is nothing to tell an edit by. Compare
  `.current` with `.new`; any difference beyond the version change is an edit to
  carry over.

If the apply pull request was squash-merged, the `Install` subjects live in the
body of the squash commit; `git show <hash>` shows them. A piece is used as
published, so first ask whether the edit belongs in a caller or in a new piece
instead. When it does, move it there and hand back `.new` unchanged.

Hand the merged file back:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" apply --item <piece> --from <merged file>
```

The merged file must carry the new marker version, or `apply` refuses it. The
hand-back completes the whole piece: it writes the merged file and every other
shipped file that is not edited, removes the dropped files whose bytes are
published, and commits the lot as `Merge <piece> vN from the repo-infra standard
with local edits`. When the target changed since the merge was prepared, the
hand-back refuses rather than overwriting the newer edit; redo the merge. A
piece committed with local edits stops the next upgrade again: its bytes still
match no published version. Run `apply` again afterwards: it installs the
remaining pieces or names the next merge. Never drop a local edit: it is there
for a reason, and the reason is usually not visible in the diff.

After the merge, `check` reads the piece `edited` and exits 1 until its bytes are
published ones again. Move the local edit into a caller, delete the file and run
`apply --item <piece>`; it writes the published file and commits it as `Install`.

## If it refuses an administration item

Read the refusal; each one names the concrete next action. `default-branch`
never applies automatically: renaming breaks links, forks and clones that pin the
old name, so it tells the user to rename by hand in Settings, General, then
re-run `check`.

`required-checks` and `branch-protection` can refuse two different ways, and they
mean different things. "not on main yet" is a confirmed absence: merge the
pull request that installs `ci.yml` and `changelog.yml` and retry. "could not
confirm" means the check against GitHub itself failed (network, permissions). It
is not evidence either way, so retry rather than assuming the workflow is or
is not there.
