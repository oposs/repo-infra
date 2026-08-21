---
name: repo-infra
description: Use when bringing a repository onto the shared infrastructure standard, or checking how far it has drifted - release flow, branch protection, CI, changelog gate. Triggers on "check this repo", "set up releases here", "why is my PR blocked", "bring this repo up to standard".
---

# repo-infra

Bring **the repository you are standing in** onto the shared infrastructure
standard, and report how far behind it has fallen when the standard moves.

One repository per run. There is no fleet sweep and no organisation-wide pass.

## Check first, always

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" check
```

Read the report before doing anything. `check` never writes; it exits 1 when
anything needs attention and 0 when the repository is current.

## Then apply

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" apply
```

`apply` works on the `repo-infra/apply` branch. A file item (a workflow, the
changelog gate, the dependabot config) gets one commit there; an administration
item (the label, workflow permissions, the ruleset) writes straight to the live
repository through the GitHub API instead, with no commit and no branch. `apply`
does not push the branch or open the pull request itself — that is the next
step, and `/repo-infra:apply` walks through it.

## When the standard has no answer

`check` and `apply` assume the standard knows what this repository is. Sometimes
it does not — the report says `the standard does not recognise this repository`,
or you read the repository and find the standard silent about something it needs,
or in conflict with something that already works.

Do not patch the repository around the gap, and do not grow a variant asset for
it. Teach the standard, then convert: ask the user, prove the answer in this
repository's tree, upstream it to repo-infra, and merge this repository's pull
request only once that has shipped.

`references/teaching-the-standard.md` has the procedure, including which
differences are gaps and which are just migration work.

## The four things that will surprise you

1. **A `conflict` is not a bigger `missing`.** It means adopting the item breaks
   something that already works — a release that pushes to `main`, a default
   branch that is not `main`, a required workflow behind a `paths` filter.
   Applying it is a migration. Read `references/release-flow.md` before touching
   one.

2. **`apply` refuses to merge a file that has local edits.** It writes
   `{name}.base`, `{name}.new` and `{name}.current` under
   `.git/repo-infra/merge/` and stops. Merge `.base` and `.new` into the local
   edits yourself, save the result anywhere, and hand it back:
   `apply --item ci --from .git/repo-infra/merge/ci.merged.yml`. If the target
   changed since the refusal, the re-run refuses again rather than clobbering
   the newer edit.

3. **The ruleset precondition asks GitHub, not your checkout.** `apply` won't
   enable the ruleset until `ci.yml`/`changelog.yml` are confirmed on the
   default branch itself — committing them locally isn't enough, and neither is
   pushing a branch that hasn't merged yet; either state refuses with "not on
   main yet." If the confirmation call itself fails (network, permissions), it
   refuses too, with a different message, rather than guessing which way to
   fail. So land the file items' pull request first; the administration items
   simply won't succeed until you do. `commands/apply.md` sequences this.

4. **Order is not negotiable.** Rename the default branch, land `ci.yml` and
   `changelog.yml` on `main`, *then* enable the ruleset. A required check whose
   workflow does not exist blocks every pull request in the repository,
   including the one that would install the workflow.

## Reading further

- `references/release-flow.md` — how a release actually happens, what the guard
  is for, and how to recover a half-finished one.
- `references/conventions.md` — the house rules that are not derivable: the
  changelog deviation, the github-script injected names, the marker protocol.
- `references/teaching-the-standard.md` — what to do when the standard has no
  answer for this repository, and which differences count.
