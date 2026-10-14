---
name: repo-infra
description: Use when bringing a repository onto the shared infrastructure standard, or checking how far it has drifted - release flow, branch protection, CI, changelog gate. Triggers on "check this repo", "set up releases here", "why is my PR blocked", "bring this repo up to standard".
---

# repo-infra

repo-infra is a toolbox for one repository at a time: the one you are standing
in. A caller calls each workflow at
`uses: oposs/repo-infra/.github/workflows/<piece>.yml@v2`, and each release of
repo-infra moves `v2`, so a fix reaches every repository without a pull request.
Build files (`build/man.mk`, `build/man-deflist.lua`, `build/container.mk`,
`m4/repo-infra-container.m4`, `.github/dependabot.yml`) are installed by `apply`;
`check` reviews both. You choose the pieces and write the callers (D30, D33).

## The three kinds of file

| Kind | Examples | Owner | On update |
|---|---|---|---|
| Piece | `ri-*.yml` in repo-infra (called), `build/*.mk`, `dependabot.yml` (installed) | repo-infra | `v2` moves; `apply` replaces an installed one |
| Caller | `ci.yml`, `release-build.yml`, `release-publish.yml`, `release-pr.yml`, `changelog.yml`, `ci-local.yml` | the repository | you adapt it from the findings |
| Config | `.github/repo-infra.json` | the repository | you adapt it from the findings |

An installed piece opens with the marker `# repo-infra: <piece> vN` and is never
edited in the repository: what it lacks goes into a caller. A repository that
still has the v1 layout (copied `ri-*.yml`, `.github/workflows/lib/`) runs
`apply`, which migrates it in one commit.

## The two jobs

**Onboarding** a repository brings it up to the full shape of the standard: read
it, review the shape first and present the owner one work plan in which every
item reads "do", write the callers (the five of `references/examples/mtuspy/` are
the model), install the build files with `apply --item <piece>`, do the rest of
the plan, run the script until it exits 0. `references/onboarding.md` has the
procedure, and `references/project-shape.md` what a released project contains.

**Updating** a repository already in the fold:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" check
python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" apply
```

`apply` migrates a v1 layout and installs build files on the `repo-infra/apply`
branch, prints the findings, and stops. You change the callers and the config
from those and run the script until it exits 0. `/repo-infra:check` and
`/repo-infra:apply` walk through it. When no piece fits a need, ask the user,
prove the answer, upstream a new piece (`references/teaching-the-standard.md`).

## Settled decisions

Each line points at its file. `docs/superpowers/specs/` has the full text.

- D1, D3, D4: `main` is protected, Actions may open pull requests, protection is
  per repository. `references/release-flow.md`
- D2: the ruleset requires exactly `ci-passed` and `changelog-updated`.
  `references/onboarding.md`
- D5, D6: `CHANGES.md` is the version source; the first section is `### New`.
  `references/conventions.md`
- D7, D8, D9: logic in github-script from `lib/*.js`, git through the Git Data
  API. `references/conventions.md`
- D10, D12, D14, D19: skills carry decisions, the tool never guesses, names answer the
  question where they are read, pieces are tested by running them.
- D11, D29: superseded by D30; markers name a version, bytes decide.
  `references/conventions.md`
- D13: a required workflow never carries `paths`. `references/conventions.md`
- D15 to D18: unified infrastructure, the container threshold and driver.
  `references/teaching-the-standard.md`, `conventions.md`
- D20, D25: the repository brings the test and the CI jobs, called through a
  fixed path. `references/onboarding.md`
- D21, D27: crates.io Trusted Publishing (`references/conventions.md`); Gitea
  packages (`references/release-flow.md`).
- D22, D23: musl and man pages are pieces a caller chooses; D32 makes them rules
  of the shape. `references/catalogue.md`, `project-shape.md`
- D24: a Rust workspace names its lint and test crates. `conventions.md`
- D26: folded into D28. D28, D31: every release is built and tested before the merge, and its pull
  request skips `ci.yml`. `references/release-flow.md`
- D30, D33: pieces and callers instead of detection and assembly; workflows are
  called at `@v2` instead of copied. This file.
- D32, D34: a project has a shape, with exceptions; a piece input that drops
  a requirement needs its paired exceptions. `references/project-shape.md`

## Traps that stay

1. **`ci-passed` is an inline job, word for word.** Copy
   `assets/callers/ci-passed.yml` (the jobs `release-verdict` and `ci-passed`)
   and fill in `needs:`. A job that calls a workflow reports as
   `ci-passed / <job>`, which the ruleset does not match. Its `needs:` lists
   every other job of `ci.yml`, each with the `if:` of
   `assets/callers/release-pr-skip.yml` (D31); `finalize` needs every other job
   of `release-publish.yml`. `check` verifies all three.

2. **The ruleset waits for `main`.** `apply --item required-checks` refuses
   until `ci.yml` and `changelog.yml` are on the default branch: a required check
   with no workflow blocks every pull request, including the one that installs
   it. Rename the default branch, land the files, then enable the ruleset.

3. **Administration items are outward-facing.** `default-branch`,
   `required-checks`, `no-changelog-label` and `actions-open-pr` change the live
   repository with no commit. `apply` runs one only with `--item`; confirm each.

4. **A release in progress blocks `apply`.** An open release pull request, or a
   latest released version without a tag, stops every install.

5. **An `edited` build file is merged by hand.** `apply` writes the merge files
   under `repo-infra/merge/` in the git dir and stops with `NeedsMerge` (exit 3).
   `commands/apply.md` has the procedure; hand the result back with
   `apply --item <piece> --from <file>`.

## Reading further

- `references/catalogue.md`: every piece, its inputs and the job that calls it.
- `references/onboarding.md`: the procedure for a repository not yet in the fold.
- `references/project-shape.md`: what a released project contains, by trigger.
- `references/examples/repo-infra/`: repo-infra's own callers and config.
- `references/conventions.md`: the house rules that cannot be derived.
- `references/release-flow.md`: how a release happens, and how to recover one.
- `references/teaching-the-standard.md`: what to do when no piece fits.
- The `writing-style` and `man-pages` skills in this plugin: the voice of
  prose, and how a man page is written and built. They trigger on their own.
