---
name: repo-infra
description: Use when bringing a repository onto the shared infrastructure standard, or checking how far it has drifted - release flow, branch protection, CI, changelog gate. Triggers on "check this repo", "set up releases here", "why is my PR blocked", "bring this repo up to standard".
---

# repo-infra

repo-infra is a toolbox for one repository at a time: the one you are standing
in. It ships pieces (reusable workflows, release files, build fragments) that a
repository copies 1:1, a catalogue that says what each is for, and two commands.
You choose the pieces and write the callers that use them. The tool replaces a
piece that has a newer version and reports what is wrong. There is no fleet
sweep, and nothing refuses a repository because no rule matched it (D30).

## The three kinds of file

| Kind | Examples | Owner | On update |
|---|---|---|---|
| Piece | `ri-*.yml`, `changelog.yml`, `release-pr.yml`, `lib/*.js`, `build/*.mk` | repo-infra | `apply` replaces it |
| Caller | `ci.yml`, `release-build.yml`, `release-publish.yml`, `ci-local.yml` | the repository | you adapt it from the upgrade notes |
| Config | `.github/repo-infra.json` | the repository | you adapt it from the upgrade notes |

A piece opens with the marker `# repo-infra: <piece> vN` and is never edited in
the repository: what it lacks goes into a caller.

## The two jobs

**Onboarding** a repository: read it, map each need to a piece, copy the pieces
with `apply --item <piece>`, write the callers, run `check` until it exits 0.
`references/onboarding.md` has the procedure, the caller rules, the
`version_files` entries and the administration items.
`references/catalogue.md` lists the pieces and `references/examples/repo-infra/`
holds real callers.

**Updating** a repository already in the fold:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" check
python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" apply
```

`apply` installs and replaces pieces on the `repo-infra/apply` branch, one
commit each, prints the upgrade notes of every version it crossed, and stops.
You then change the callers and the config from those notes and run `check`
until it exits 0. `/repo-infra:check` and `/repo-infra:apply` walk through it.

When no piece fits a need, do not patch the repository around the gap: ask the
user, prove the answer here, upstream it as a new piece
(`references/teaching-the-standard.md`).

## Settled decisions

Each line points at the file that explains it. `docs/superpowers/specs/` has the
full text.

- D1, D3, D4: `main` is protected, Actions may open pull requests, protection is
  per repository. `references/release-flow.md`
- D2: the ruleset requires exactly `ci-passed` and `changelog-updated`.
  `references/onboarding.md`
- D5, D6: `CHANGES.md` is the version source; the first section is `### New`.
  `references/conventions.md`
- D7, D8, D9: logic in github-script from `lib/*.js`, git through the Git Data
  API. `references/conventions.md`
- D10, D12, D14, D19: skills carry decisions, the tool never guesses, names
  answer the question where they are read, pieces are tested by running them.
- D11, D29: superseded by D30. Markers name a version and bytes decide.
  `references/conventions.md`
- D13: a required workflow never carries `paths`. `references/conventions.md`
- D15, D16, D17, D18: unified infrastructure, the container threshold, the
  container driver. `references/teaching-the-standard.md`, `conventions.md`
- D20, D25: the repository brings the test and the CI jobs, called through a
  fixed path. `references/onboarding.md`
- D21, D27: crates.io through Trusted Publishing (`references/conventions.md`);
  Gitea package registries (`references/release-flow.md`).
- D22, D23: musl and man pages are pieces a caller chooses. `references/catalogue.md`
- D24: a Rust workspace names its lint and test crates. `references/conventions.md`
- D26: folded into D28. D28: every release is built and tested before the
  merge. `references/release-flow.md`
- D30: pieces and callers instead of detection and assembly. This file.

## Traps that stay

1. **`ci-passed` is an inline job, word for word.** Copy
   `assets/callers/ci-passed.yml` and fill in `needs:`. A job that calls a
   workflow reports as `ci-passed / <job>`, which the ruleset does not match.
   Its `needs:` lists every other job of `ci.yml`, and `finalize` needs every
   other job of `release-publish.yml`; `check` verifies both.

2. **The ruleset waits for `main`.** `apply --item required-checks` asks GitHub
   whether `ci.yml` and `changelog.yml` are on the default branch and refuses
   until they are. A required check with no workflow blocks every pull request,
   including the one that installs it. Rename the default branch, land the files
   on `main`, then enable the ruleset.

3. **Administration items are outward-facing.** `default-branch`,
   `required-checks`, `no-changelog-label` and `actions-open-pr` change the live
   repository with no commit and no review. `apply` runs one only when named with
   `--item`; confirm each with the user.

4. **A release in progress blocks `apply`.** An open release pull request, or a
   latest released version without a tag, stops every piece install.

5. **An `edited` piece is merged by hand.** `apply` writes `{name}.new`,
   `{name}.current`, `{name}.path` and `{name}.log` under `repo-infra/merge/` in
   the git dir and stops with `NeedsMerge` (exit status 3). `commands/apply.md` has the procedure.
   Hand the result back with `apply --item <piece> --from <file>`.

## Reading further

- `references/catalogue.md`: every piece, what it is for, its inputs and a
  caller snippet.
- `references/onboarding.md`: the procedure for a repository not yet in the fold.
- `references/examples/repo-infra/`: repo-infra's own callers and config.
- `references/conventions.md`: the house rules that cannot be derived: the
  changelog deviation, injected names, markers and bytes, the config keys.
- `references/release-flow.md`: how a release happens, and how to recover one.
- `references/teaching-the-standard.md`: what to do when no piece fits.
- The `writing-style` and `man-pages` skills in this plugin: the voice of a
  README, manual, changelog entry or comment, and how a man page is written,
  built and checked by `ri-ci-man`. They trigger on their own, without a check.
