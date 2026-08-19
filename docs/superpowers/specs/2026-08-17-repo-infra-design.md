# repo-infra — design

**Date:** 2026-08-17
**Repo:** `oposs/repo-infra` (Claude Code plugin, listed in the `oposs/claude-plugins` marketplace)
**Status:** design approved; specs 2–4 to be designed separately

## Purpose

Bring **one repository — the one you are standing in — onto a shared infrastructure
standard**: release flow, branch protection, CI, packaging, documentation. Either from
nothing, or from an older generation of the standard up to the current one.

The second half is the harder half. A scaffolder that runs once is easy. This tool has to
be re-runnable for years, report how far behind this repo has fallen, and upgrade it
without discarding the local edits every repo legitimately has.

The unit of work is always a single repository, chosen deliberately. There is no fleet
sweep, no inventory and no organisation-wide pass. Repositories are converted one at a
time, by running the tool inside each.

`github.com/oposs` and `github.com/oetiker` are not a target list. They are the evidence
of what a single run has to survive: ten languages, two incompatible release shapes and
three divergent sets of action versions — any of which the tool may meet in whichever
repository it is pointed at next.

### The problem, measured

Three repositories were surveyed to size that variety. All three do the same jobs
differently, and none is current.

| Action | latest | mkp-builder | mdmost | byonk |
|---|---|---|---|---|
| `actions/checkout` | v7 | v4 | v7 | v4 |
| `actions/upload-artifact` | v7 | — | v7 | v4 |
| `actions/download-artifact` | v8 | — | v8 | v4 |
| `actions/cache` | v6 | — | v6 | v4 |
| `actions/github-script` | v9 | v7 | — | — |
| `softprops/action-gh-release` | v3 | v2 | v3 | v2 |
| `docker/build-push-action` | v7 | — | — | v5 |
| `docker/login-action` | v4 | — | — | v3 |
| `docker/setup-buildx-action` | v4 | — | — | v3 |
| `docker/setup-qemu-action` | v4 | — | — | v3 |

Beyond versions, the same logic is written three ways: two different `CHANGES.md`
heading conventions, two different release shapes (PR-based and push-to-main), and the
changelog roller implemented twice in embedded Perl.

### Languages in scope

Rust, Python (including ~15 near-identical `cmk-oposs_*` Checkmk plugins), Perl,
TypeScript/JavaScript/Svelte, Go, PHP, Shell, Raku, C.

## Scope and decomposition

Four specs, shipped in order. This document holds the cross-cutting decisions and the
full detail for spec 1. Specs 2–4 get their own design documents.

| Spec | Contents |
|---|---|
| **1 — the frame** | plugin skeleton, detection, drift checker, branch protection, action versions, CI per language, release core, changelog gate |
| **2 — publish add-ons** | the seam, plus crates.io, MKP, npm, nfpm deb/rpm/apk, Windows zip + winget, ghcr containers |
| **3 — prose** | writing-style skill, man-page skill, repo hygiene files |
| **4 — docs sites** | mdBook build, `gh-pages` branch store, versioning, cull, backfill, linkcheck |

Spec 1 alone standardises every repository. Specs 2–4 add capability to repos that need
it, through a seam spec 1 defines.

## Cross-cutting decisions

These apply to all four specs. Numbered so the implementation plans can cite them.

### D1 — `main` is protected everywhere; the two-step PR release is the only release flow

There is one standard, not two profiles. Repos that currently push to `main` during a
release are **migrated**, not exempted.

Consequence: mdmost pushes to `main` three times during a release (version commit,
Homebrew formula, bottle block). Adopting protection there is a rework, not a toggle.
The checker must report this as a `conflict`, never as a plain `missing`.

### D2 — the ruleset requires exactly two status checks

Tests must pass before anything merges, always. The payload (`pull_request` rule verified
on `oposs/mkp-builder`, ruleset 20940234; the `required_status_checks` rule is new):

```json
{ "name": "main", "target": "branch", "enforcement": "active",
  "bypass_actors": [],
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "rules": [
    { "type": "deletion" },
    { "type": "creation" },
    { "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "allowed_merge_methods": ["merge", "squash", "rebase"],
        "dismiss_stale_reviews_on_push": false,
        "dismissal_restriction": { "allowed_actors": [], "enabled": false },
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": false,
        "required_reviewers": [] } },
    { "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": false,
        "required_status_checks": [
          { "context": "ci-passed" },
          { "context": "changelog-updated" } ] } } ] }
```

**Two contexts, never the matrix legs.** `ci-passed` is an aggregator job that every generated
CI workflow ends with (see *CI templates*); `changelog-updated` is the changelog check. Both
names are stable across every ecosystem, so one ruleset payload fits every repository.
Requiring matrix legs directly is brittle in both directions: adding a target silently
changes which checks are required, and renaming one silently un-requires it.

**`strict_required_status_checks_policy: false`** — deliberately not "require branches to
be up to date". With `true`, every push to `main` makes an open release PR stale, and
re-syncing it re-parks its checks behind another manual approval (below).

**`required_approving_review_count: 0`** lets a solo maintainer merge their own release PR.

**`bypass_actors` is empty.** `GITHUB_TOKEN` cannot be added — the bypass list accepts
`User`, `Team`, `Integration`, `OrganizationAdmin`, `RepositoryRole` and `DeployKey`, and
the Actions token is none of those. This is why the release lands through a PR rather than
a push. Note also that rulesets grant admins **no** implicit bypass: the live ruleset above
reports `current_user_can_bypass: "never"` for the repository owner. Nobody merges past a
red check by accident.

#### The release PR: parked, not blocked

A pull request opened by `GITHUB_TOKEN` does **not** silently skip its checks. GitHub's
current behaviour:

> `pull_request` events with the `opened`, `synchronize`, or `reopened` activity types:
> when a workflow using `GITHUB_TOKEN` creates or updates a pull request, the resulting
> `pull_request` event creates workflow runs in an **approval-required** state. The pull
> request displays a banner in the merge box, and a user with write access to the
> repository can start the runs by selecting **Approve workflows to run**.

So the release PR's checks are parked, not suppressed. The maintainer clicks *Approve
workflows to run* once; `ci-passed` then runs against the real merge result and
`changelog-updated` skips itself to green on `release/*` (D13). Then the PR merges like any
other.

One deliberate click on a pull request that is reviewed by hand anyway. The alternative —
opening the release PR with a GitHub App or PAT so the runs start unattended — was
rejected: it is the first credential this design would introduce, to be created, stored and
rotated per organisation, and it buys only the click.

**No workflow triggers on the release branch itself.** The same restriction covers pushes:
*"if a workflow run pushes code using the repository's `GITHUB_TOKEN`, a new workflow will
not run even when the repository contains a workflow configured to run when `push` events
occur."* The release branch is created by the Actions token through the Git Data API (D9),
so no `push`-triggered CI fires on it either. The approval click is the only route to a
green required check on a release PR — do not try to engineer around it with `on: push`.

### D3 — Actions must be allowed to open pull requests

```
PUT /repos/{owner}/{repo}/actions/permissions/workflow
    default_workflow_permissions       = write
    can_approve_pull_request_reviews   = true
```

This is the API behind the UI's "Allow GitHub Actions to create and approve pull
requests". Evidence: `oposs/mkp-builder` has it `true` and opens release PRs
successfully; `oetiker/mdmost` has it `false` and does not open PRs. `apply` reads the
setting back after writing rather than assuming the write took.

Org-level policy can override the repository setting. Reading `orgs/oposs/actions/permissions/workflow`
requires the `admin:org` scope (`gh auth refresh -h github.com -s admin:org`); this was
not verified during design.

### D4 — protection is applied per repository, not per organisation

This follows directly from the Purpose: the tool converts the repository it is run in, and
nothing else. An organisation-wide ruleset would silently reach beyond that boundary.

It would also be a trap. On the day such a ruleset is created, every repository not yet
converted loses the ability to push to `main` — including any release in flight, and
including every repository whose CI has no `ci-passed` job yet, which the ruleset would block
entirely (D13). Per-repo means one repository changes at a time and nothing else notices.

`oetiker` is a personal account and has no organisation rulesets, so per-repo is the only
option there regardless.

Consolidating `oposs` to a single organisation ruleset is a reasonable cleanup **once**
every repository has been converted — a separate, deliberate act, never something `apply`
does.

### D5 — `CHANGES.md` is the single source of truth for the released version

The topmost `## X.Y.Z - YYYY-MM-DD` heading in `CHANGES.md` **is** the released version.
Version files (`Cargo.toml`, `package.json`, `plugin.json`, …) are a derived copy.

`CHANGES.md` is the only file that exists in every repository — Go, PHP and Shell repos
have no version file at all — and it changes on exactly one occasion. It also gives the
publisher a universal trigger:

```yaml
on:
  push:
    branches: [main]
    paths: ['CHANGES.md']
```

An ordinary PR that adds notes under `[Unreleased]` fires this too and is harmless: the
topmost released heading is already tagged, so the publisher no-ops. Idempotence is a
property of the design rather than a bolt-on.

**Guard:** the publisher cross-checks `CHANGES.md` against every version file and fails
loudly on disagreement. This catches a half-applied release PR — the failure mdmost hit
when `Cargo.toml` said 0.1.1 and `Cargo.lock` said 0.1.0, tagged and broken.

### D6 — the changelog format is Keep a Changelog with one documented deviation

```
## [Unreleased]        <- brackets; mdmost currently writes `## Unreleased`
### New                <- Keep a Changelog says "Added"
### Changed
### Fixed
```

`### New`, not `### Added`. A model told only "use Keep a Changelog" writes `### Added`
confidently, and the roller — which matches on `### New` — silently drops the section
from the release notes. The deviation is therefore written down; the concept of a
changelog is not.

The bracket form is standardised on. The checker flags `## Unreleased` as a `conflict`
and `apply` migrates it. The roller **validates before it writes** and fails with a clear
message; both current implementations are single large regexes that produce nothing at
all on an unexpected shape, and "nothing" looks a lot like "no changes to release".

### D7 — logic in github-script, tool invocation in shell

Workflow logic — version arithmetic, the changelog roll, version-file rewrites, API calls
— is JavaScript. Only actual tools stay as `run:` steps, because there is no JavaScript
way to run a compiler:

```bash
cargo update --workspace     # not --offline: the resolve needs the registry
                             # not || true:  swallowing this broke v0.1.1
```

### D8 — workflow logic lives in real `.js` files, not YAML strings

```
.github/workflows/lib/
  changes.js        parse, roll, extract release notes
  version.js        semver arithmetic, next-version
  bump.js           the generic version-file writer
  checks.js         read check runs for a SHA
  commit.js         create a commit through the Git Data API
  docs-versions.js  (spec 4) cull, versions.json, redirect
```

Workflows `require()` these after checkout. Three consequences:

1. **Testable.** `node --test .github/workflows/lib/` runs in CI. The changelog roller is
   currently a Perl program inside a YAML string, tested only by cutting a release.
2. **Shareable.** The roller is identical in every repo, so fixing it is one asset
   version bump rather than forty hand-edits.
3. **Diffable.** A change to release logic shows as a change to a `.js` file, not as
   changed indentation inside a heredoc.

This is the largest quality gain in spec 1 and it is only possible because the logic
moved to github-script.

### D9 — git operations go through the Git Data API, never `git push`

Tagging is `git.createTag` followed by `git.createRef` — **annotated**, not a bare
`createRef`, which produces a lightweight tag. `git describe` prefers annotated tags and
the existing repos have annotated tags; a silent switch would change local tooling
behaviour for no reason. The moving major tag uses `updateRef({force: true})`.

The release commit and PR likewise go through `createBlob` → `createTree` →
`createCommit` → `createRef` → `pulls.create`.

The alternative is honest: `git checkout -b && git commit && git push` works, because
only `main` is protected. The API version wins on two counts — no `git config user.email`
dance repeated in every repository, and the commit is atomic rather than a sequence that
can half-fail. It costs about forty lines, written once in `commit.js`.

The publisher needs no checkout, no `git config` and no push at all.

### D10 — skills carry decisions, traps and local conventions, never tutorials

The test for every line: *would a competent current-generation model get this right
unaided?* If yes, cut it. If it would get it **plausibly wrong** — confidently wrong, in
a way review does not catch — keep it and say why.

That test alone is unsafe, because the answer moves with every model release and fails
silently. So a second, harder rule sits underneath it:

> **Anything that is a fact with a value goes in a data file the script reads. Only the
> reasoning goes in prose.**

Action versions, ruleset JSON, the language→version-file map, file paths. These are
exactly what a model states confidently and gets wrong, and in prose they rot unnoticed.
In a data file they are machine-checked and appear in a diff when they change.

Applied:

| Rejected | Adopted |
|---|---|
| `references/detection.md` — prose table | `assets/detection.json` — data |
| `references/github-script.md` — how github-script works | ~15 lines of house rules only (D7, D9) |
| `references/branch-protection.md` — prose description | `assets/gh/ruleset-main.json` — the exact payload; prose keeps only the two traps |
| `references/changes-format.md` — the changelog format | the deviations only (D6) |
| `references/release-flow.md` | kept nearly intact — all decision and consequence, none derivable |

### D11 — drift is detected by version markers, not content hashes

Every installed asset carries a header line:

```yaml
# repo-infra: release-pr v3 — do not delete this line
```

**A file assembled from several assets carries several markers.** `ci.yml` is built from a
frame plus one job block per ecosystem (see *CI templates*), so the frame's marker sits on
line 2 and each block carries its own marker directly above it:

```yaml
name: CI
# repo-infra: ci v1
...
jobs:
  # repo-infra: ci-rust v2
  fmt: ...
  clippy: ...
  # repo-infra: ci-claude-plugin v1
  validate: ...
```

The checker reads every marker in a file, not only line 2, and reports drift per block. A
rust repo can therefore upgrade its rust jobs without touching its plugin jobs. Without
this, one CI file would mean one version number for all ecosystems, and adding an
ecosystem would force every other block to be re-applied.

The checker compares each marker against `assets/manifest.json`. A content hash is wrong
here: every repo legitimately edits its workflows — project name, matrix targets, publish
jobs — so a hash would report drift on every repo forever. The marker records only
*which generation of the asset this is*. Upgrading re-applies the new asset and re-merges
local edits as a reviewed diff, never a blind overwrite.

This also survives dependabot, which edits contents while leaving the marker alone.

### D12 — the tool never guesses

Ambiguous signals — a `package.json` that is tooling config rather than a published
package, a repo with both `pyproject.toml` and `Cargo.toml` — produce state `ambiguous`
and stop. `apply` asks, then records the answer in `.github/repo-infra.json`.

A wrong guess about which file holds the version produces a release that looks fine and
is broken, discovered by a user. Asking once costs a question.

### D13 — a required workflow never carries a workflow-level filter

`ci.yml` and `changelog.yml` are required by D2. Neither may use `paths` or
`paths-ignore` under `on: pull_request`. Ever.

A `branches` filter is permitted **only** where it cannot exclude a pull request the
ruleset gates. `branches: [main]` qualifies: it matches on the pull request's *base*, and
the ruleset covers `~DEFAULT_BRANCH`, so every gated PR runs the workflow while stacked
PRs onto other bases are spared. That equivalence is a coincidence of two settings
agreeing, not a guarantee — if the ruleset is ever widened past the default branch, this
filter must be widened in the same commit.

The reason is a distinction that is easy to miss and impossible to debug from the symptom:

| How the work is skipped | Reported as | Effect on a required check |
|---|---|---|
| **job** skipped by a job-level `if:` | **Success** | merges fine |
| **workflow** skipped by `paths` / `branches` filtering | stays **Pending** | blocks the PR forever |

GitHub states it plainly: *"You should not use path or branch filtering to skip workflow
runs if the workflow is required."*

So conditional execution is expressed **inside** a job, never in the trigger:

```yaml
on:
  pull_request:
    branches: [main]      # base-branch filter only; never paths / paths-ignore
jobs:
  changelog-updated:
    if: >-                # job-level — skipping here reports Success
      !startsWith(github.head_ref, 'release/') &&
      !contains(github.event.pull_request.labels.*.name, 'no-changelog')
```

This is what lets the changelog gate be *required* and still have an escape hatch: an
exempt PR skips the job and the required check goes green on its own.

The failure this prevents does not look like a configuration error. It looks like a stuck
pull request with a check that never appears and no log to read — in a repository where
someone reasonably added `paths: ['src/**']` to save CI minutes. The checker therefore
treats a workflow-level filter on a required workflow as a `conflict`, not a `missing`.

### D14 — names answer the question asked where they are read

A name appears in two places that ask different questions, and the same string cannot serve
both. So each is named for its reader.

| | file + marker | workflow `name:` | required job id |
|---|---|---|---|
| | the **asset id** | what it is, and whether you run it | the **state** you must reach |
| | `ci` | `CI` | `ci-passed` |
| | `changelog` | `Changelog` | `changelog-updated` |
| | `release-pr` | `Create release PR` | — |
| | `release-publish` | `Publish release (automatic)` | — |
| | `dependabot` | — | — |

**Asset id** governs the file name and the marker, so `changelog.yml` carries
`# repo-infra: changelog v1` and nothing has to be looked up. Blocks assembled into a file
extend it with a suffix: `ci-rust`, `ci-python` (D11).

**A required job carries no `name:`.** Its check context is then its job id, which cannot
drift apart from the ruleset. Every other job may have a friendly `name:`. Renaming a
required job silently un-requires the check, so the two must be impossible to separate.

**Required job ids name the state, not the mechanism.** The merge box is read by someone
who is blocked and wants to know what to do. `changelog-updated` says it; `changelog-gate`
only reports that a gate exists. This is why the job id is not simply the asset id.

**Exactly one workflow reads as a button.** `Create release PR` is the only thing anyone
dispatches, and it is named for what pressing it actually does — it opens a pull request,
it does not publish. Its counterpart says `(automatic)` in the name, which answers "why is
there no *Run workflow* button?" before the question is asked. Naming the two halves as a
symmetric pair was rejected: it presents a choice between two things when only one is
choosable.

Prose does not use the display names. `Publish release (automatic)` appears in the Actions
sidebar; documentation says "the publish workflow" or `release-publish.yml`.

## Spec 1 — the frame

### Repository layout

```
oposs/repo-infra
  .claude-plugin/plugin.json
  CHANGES.md  RELEASING.md  README.md  LICENSE
  commands/
    check.md                    /repo-infra:check   read-only
    apply.md                    /repo-infra:apply   writes, via a PR
  skills/
    repo-infra/
      SKILL.md
      references/
        release-flow.md         the decision, the traps, the recovery
        conventions.md          D6 deviations, D7/D9 house rules, D11 marker protocol
      assets/
        manifest.json           asset -> version; action -> current major
        detection.json          signals -> ecosystems -> version files
        gh/ruleset-main.json    the exact payload from D2
        workflows/              release-pr.yml, release-publish.yml,
                                changelog.yml, ci-frame.yml, lib/*.js
        ci/                     ci-rust.yml, ci-python.yml, ci-node.yml, …
                                job blocks assembled into ci.yml, not whole workflows
        dependabot.yml
      scripts/repo_infra_check.py
      evals/evals.json
  .github/workflows/            its own two-step release — it eats its own cooking
```

The plugin is **one** skill, not four. Detection, checking and applying are one workflow;
four skills would compete for the same trigger and each need separate description tuning.
Depth goes into `references/`, loaded only when needed, keeping `SKILL.md` short.

`skill-creator` governs the skill and its evals. `plugin-dev` governs the plugin shell
(`plugin.json`, `commands/`, hooks). Specs 3 and 4 add `writing-style` and `man-pages` as
*separate* skills, because those trigger on their own ("help me write this README") with
no repo audit involved.

### The run model

`/repo-infra:check` never writes. It detects, compares, prints a report, stops.

`/repo-infra:apply` works on a branch and opens a PR, because `main` is protected and the
plugin gets no exemption from the standard it installs. One commit per item, so any single
item can be dropped at review.

**Ordering is not free: the ruleset goes last.** A required status check whose workflow
does not exist never reports, and blocks every pull request in the repository — including
the one that would have installed the workflow. So `apply` proceeds in this order, and
never collapses it into one step:

1. create the `no-changelog` label,
2. land `ci.yml` (with its `ci-passed` job) and `changelog.yml` on `main` through the
   apply PR,
3. **then** enable the ruleset with its two required contexts (D2).

Step 3 runs only after step 2 has merged. On a repository that is being upgraded rather
than onboarded, `check` reports which of the three are already done, so a re-run resumes
rather than repeats.

### Per-repo state

```json
// .github/repo-infra.json
{
  "ecosystems": ["rust"],
  "moving_major_tag": false,
  "version_files": [
    { "path": "Cargo.toml",
      "pattern": "^version = \"[^\"]*\"",
      "replacement": "version = \"$VERSION\"",
      "verify": "^version = \"$VERSION\"" }
  ],
  "skip": { "man-pages": "library crate, no CLI" }
}
```

Without `skip`, the checker nags about man pages on every library crate forever. This file
is the only way to record a deliberate "no" so the tool stops asking. It also records
answers to `ambiguous` questions (D12) so they are asked once.

**JSON, not YAML.** `actions/github-script` bundles no YAML parser, so a YAML config would
mean installing a dependency inside every workflow of every repo for one small file. JSON
needs `JSON.parse` and nothing else. The cost is losing comments; the file is written by
`apply` and only occasionally hand-edited, so that is acceptable.

Each `version_files` entry carries its own locate/replace/verify patterns rather than just a
path. This is what keeps D10 honest: adding an ecosystem is a data entry, not code.

### Detection

`assets/detection.json`, one entry per ecosystem. A repo may match several — `mkp-builder`
is `python` **and** `claude-plugin`, and both are bumped in the same release PR.

| Signal | Ecosystem | Version file(s) |
|---|---|---|
| `Cargo.toml` | rust | `Cargo.toml`, `Cargo.lock` |
| `.claude-plugin/plugin.json` | claude-plugin | that file |
| `pyproject.toml` | python | `pyproject.toml` |
| `.mkp-builder.ini`, `local/lib/python3/cmk_addons/` | checkmk-plugin | *none* — the action takes the tag |
| `package.json` | node | `package.json` (+ `package-lock.json` if present) |
| `configure.ac` | autotools | `AC_INIT` in `configure.ac` |
| `dist.ini`, `Makefile.PL`, `cpanfile` | perl | `our $VERSION` in the main `.pm` |
| `go.mod` | go | *none* — tags only |
| `composer.json` | php | *none* — tags only |

**Rust workspaces.** If `[workspace.package] version` exists, that is the field to bump and
members inherit it; otherwise the root `[package] version`. Detection records which it
found in `.github/repo-infra.json`.

**Reported but not acted on in spec 1:** *ships a CLI* (`[[bin]]`, `bin` in
`package.json`, `console_scripts`, a `bin/` directory) → man-page candidate; publish
candidates → spec 2; an existing `book.toml` → spec 4. These appear in the report as
candidates from day one, so a repository converted before specs 2–4 exist still shows what
it will eventually be able to adopt.

### The version-file writer

Each `detection.json` entry carries a locate pattern, a replacement and a **verify**
pattern. One generic writer consumes them all:

1. locate
2. rewrite
3. **read back and assert**

Step 3 is the point. Without it, `|| true` swallowed a failed bump, `v0.1.1` was tagged
internally inconsistent, and the publish died six minutes later. The assert is not
optional and not per-language. Adding an ecosystem means adding a JSON entry, never
writing code.

The read-back also covers a residual uncertainty: `package-lock.json` records the root
version and must move with it; `pnpm-lock.yaml` is believed not to. If that is backwards,
the assert fails on the first release rather than shipping a broken tag.

### `release-pr.yml`

```yaml
on: workflow_dispatch            # bugfix | feature | major
concurrency: { group: release, cancel-in-progress: false }
permissions: { contents: write, pull-requests: write, checks: read }

jobs:
  guard:      # on main? are all checks green on this SHA?
  prepare:    # compute, roll, bump, commit, open PR
```

**The guard** uses `checks.listForRef({ref: sha})`, which returns every check on the
commit — CI, the changelog gate, anything added later:

- any conclusion failed → fail
- any still running → poll until the job's `timeout-minutes` expires
- none at all → fail, "no checks ran on this commit"

This replaces mkp-builder's ~150-line `verify-tests` job, which polls
`listWorkflowRuns` for a hardcoded `test.yml` and therefore sees one workflow and breaks
when a repo names its CI something else.

**The guard is not made redundant by D2's required checks — do not delete it.** Its job
changed, not its value. It no longer *substitutes* for a required check; it now fails
**fast**, on the commit, before any branch, commit, PR or approval click exists. Without
it a release started from a red `main` still gets a rolled changelog, a bumped version, a
pushed branch and an open PR — and only then parks on a check the maintainer has to
approve in order to watch it go red. The guard turns that into an immediate refusal with
nothing to clean up.

**Prepare always checks out.** Checkout costs about five seconds; a Rust toolchain costs
minutes. So checkout is unconditional and only tool steps are conditional:

```yaml
- uses: dtolnay/rust-toolchain@stable
  if: contains(needs.detect.outputs.ecosystems, 'rust')
- run: cargo update --workspace
  if: contains(needs.detect.outputs.ecosystems, 'rust')
```

Everything else is JavaScript over `fs`. The commit and PR go through the Git Data API
(D9). The job refuses to proceed if the computed tag already exists.

### `release-publish.yml`

```yaml
on:
  push:
    branches: [main]
    paths: ['CHANGES.md']
concurrency: { group: release-publish, cancel-in-progress: false }
permissions: { contents: write }
```

**No `workflow_dispatch`, by design.** Publishing should be a consequence of merging a
release PR, never something started from a dropdown. Combined with D1, that leaves exactly
one route to a release. Recovery does not need a manual trigger: a failed run is re-run
from the Actions UI, and because the version comes from the repository rather than from
run inputs, the re-run does exactly what the original attempt would have done.

Steps:

1. Read `CHANGES.md`; take the topmost `## X.Y.Z - date` heading (D5).
2. Cross-check every version file; disagreement fails loudly.
3. If the tag exists, no-op and exit.
4. Annotated tag via `git.createTag` + `git.createRef` (D9).
5. Moving major tag `vX` via `updateRef({force: true})`, only where
   `.github/repo-infra.json` asks for it. A library crate does not need one; a GitHub
   Action does.
6. Extract notes from `CHANGES.md`.
7. `repos.createRelease` — **as a draft** (see the seam below).

**Outputs, forming the seam for spec 2:**

```yaml
outputs: { version: 1.4.2, tag: v1.4.2, release_id: 12345678 }
```

Add-ons declare `needs: publish`, build, and upload to the draft release. A `finalize`
job publishes it once add-ons finish. Its `needs:` list is **written by `apply`** when it
installs an add-on, so the core template stays add-on-agnostic while the wiring stays
visible in the repository. Without the draft, binaries trickle into a published release
over several minutes; without the generated `needs:` list, the core would depend on the
add-ons, inverting the dependency.

### The changelog check

Every PR must add something under `[Unreleased]`.

**Required, not advisory.** The job is named `changelog-updated` and is one of the two
contexts the ruleset requires (D2). Two layers:

| When | What | Strength |
|---|---|---|
| PR opened | "this PR adds nothing under `[Unreleased]`" | **blocks the merge** |
| Release run | "`[Unreleased]` is empty, nothing to release" | hard failure |

Being required is only safe because the escape hatch below is a **job-level** `if:`, which
reports Success when it skips (D13). A `paths` filter here would deadlock every PR in the
repository.

An advisory version of this check was considered and rejected. An advisory check that is
routinely ignored is worse than no check: it teaches that red is normal, and then a
genuinely broken build looks exactly like a missing changelog line.

The release-time check already exists in mkp-builder and only catches an entirely empty
changelog. The PR check catches the real problem: entries written at release time, from
memory, weeks after the change.

**It compares the section, not the file.** Checking "did `CHANGES.md` change" would pass
on an edit to an old released section. The job fetches the `[Unreleased]` block at base
and at head with two `repos.getContent` calls and requires them to differ. No checkout is
needed, which also avoids `fetch-depth: 0` and the merge-commit awkwardness of
`git diff`.

**The escape hatch is not optional** — and now that the gate blocks, it is the only way a
legitimate no-changelog PR ever merges:

```yaml
jobs:
  changelog-updated:
    if: >-
      !startsWith(github.head_ref, 'release/') &&
      !contains(github.event.pull_request.labels.*.name, 'no-changelog')
```

`release/*` exempts the release PR, whose whole diff *is* the changelog roll. The
`no-changelog` label lets a deliberate exemption be stated once, per PR, in public.

**The `no-changelog` label must exist in the repository.** This is a real trap, because
nothing reports it. Dependabot's `dependabot.yml` requests the label (see *Action
versions*), but **Dependabot cannot create labels, and a label that does not exist is
silently ignored** — so every weekly dependabot PR would arrive unlabelled and hang on a
required gate, with no error anywhere to explain why. Therefore `apply` creates the label
(`POST /repos/{owner}/{repo}/labels`) **before** enabling the ruleset, and `check` reports
its absence as a distinct item.

### Action versions: dependabot, not the checker

GitHub already solves this, per repo, without our involvement, and it never goes stale.

```yaml
# .github/dependabot.yml      # repo-infra: dependabot v1
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule: { interval: weekly }
    labels: [dependencies, no-changelog]
```

The `no-changelog` label is why the gate needed an escape hatch: without it every weekly
dependabot PR is **blocked**, not merely red, since the gate is required (D2).

That makes the label load-bearing, and it fails silently. Dependabot cannot create labels;
a label missing from the repository is ignored without comment. `apply` therefore creates
`no-changelog` explicitly, and `check` verifies it — see *The changelog gate*.

Labelling dependabot's PRs was chosen over exempting the `dependabot[bot]` actor inside the
gate. The exemption then lives in a config file, shows up in a diff, and can be overridden
on any single PR that does deserve a changelog entry.

The split:

- `assets/manifest.json` pins the majors **our shipped workflows use**, so a freshly
  installed asset starts current. Seeded from the table at the top of this document.
- dependabot keeps every repo current afterwards, including our installed assets.
- the checker reports pinned majors only as a **fallback**, for repos where dependabot is
  off.

`dtolnay/rust-toolchain@stable` is a branch reference, not a version; dependabot leaves it
alone, and that is correct. Noted in `conventions.md` so nobody "fixes" it.

### CI templates

**One `ci.yml` per repository — never one file per ecosystem.** This is forced by D2. The
required context `ci-passed` is a single aggregator job, and `needs:` cannot reach across
workflow files. A repository matching two ecosystems — `mkp-builder` is `python` **and**
`claude-plugin` — would otherwise produce either two jobs called `ci-passed` or none, and
the required check would be ambiguous or absent.

So `ci.yml` is **assembled**: a frame, plus one job block per detected ecosystem, plus the
aggregator.

| Ecosystem | Block asset | Jobs |
|---|---|---|
| rust | `ci-rust` | `fmt --check`, `clippy -D warnings`, `test`, cache |
| python | `ci-python` | `ruff`, `pytest` |
| checkmk-plugin | `ci-checkmk-plugin` | mkp-builder's existing `validate.yml`, adopted as-is |
| node | `ci-node` | `pnpm install --frozen-lockfile`, lint, test |
| perl | `ci-perl` | `prove -l t/` |
| go | `ci-go` | `go vet`, `go test` |
| php | `ci-php` | `composer install`, `phpunit` |

Plus two jobs every repo gets. The first is `node --test .github/workflows/lib/` — the
release logic tests itself. The second is the aggregator that D2 requires:

```yaml
  ci-passed:
    if: always()
    needs: [fmt, clippy, test, workflow-lib]   # every job above, per ecosystem
    runs-on: ubuntu-latest
    steps:
      - if: contains(needs.*.result, 'failure') || contains(needs.*.result, 'cancelled')
        run: exit 1
```

`ci-passed` exists so the ruleset can name **one** context that means "this repository's CI
passed", whatever that repository's jobs happen to be. `if: always()` is required — without
it the job is skipped when a dependency fails, and a skipped job reports Success (D13),
which would turn the required check green on a red build. That inversion is the single
most dangerous mistake in this file: it fails open, silently, and looks like it is working.

Two hard requirements, and nothing else is coupled to a filename:

- CI runs on `push` **and** `pull_request`, so it produces check runs the release guard can
  read on a commit as well as on a PR.
- Neither trigger carries a `paths`, `paths-ignore` or `branches` filter (D13).

### The report

```
repo-infra check — oetiker/mdmost

detected   rust (Cargo.toml, Cargo.lock) · ships a CLI

  release-pr            outdated   v1 installed, v3 available
  release-publish       ok
  changelog             missing
  changes-format        conflict   '## Unreleased' → '## [Unreleased]'
  branch-protection     missing    main is unprotected
  required-checks       missing    ruleset requires neither ci-passed nor
                                   changelog-updated
  no-changelog-label    missing    dependabot requests it; it does not exist
  actions-open-pr       missing    can_approve_pull_request_reviews = false
  dependabot            missing
  ci                    ok         frame v1
  ci-rust               outdated   block v1 installed, v2 available

  ! release.yml pushes to main 3× (version commit, formula, bottles).
    Protecting main breaks it. Migration required, not an upgrade.
  ! ci.yml filters on: pull_request by paths. Required checks would leave
    every unmatched PR pending forever. Move the condition into the job.

  candidates (later specs)
  publish-crate  homebrew  os-packages  containers  man-pages  docs-site

7 items need attention.  /repo-infra:apply
```

States: `ok`, `missing`, `outdated`, `conflict`, `ambiguous`, `skipped`. `--json` emits
the same structure for `apply` to consume.

`conflict` is the state that earns its keep. Everything else means "install a file". A
conflict means adopting one item breaks something already working. Reported as plain
`missing`, `apply` would cheerfully enable the ruleset and the breakage would surface at
the next release rather than at apply time.

The checker is Python 3, standard library only, shelling out to `gh`.

## Spec 2 — publish add-ons (outline)

The seam is defined in spec 1: `needs: publish`, consume `version`/`tag`/`release_id`,
upload to the draft release, and `apply` adds the job to `finalize`'s `needs:` list.

| Add-on | Notes |
|---|---|
| crates.io | `cargo publish --locked`; token via `CARGO_REGISTRY_TOKEN` env, not `--token` (deprecated) |
| MKP | the existing `oposs/mkp-builder` action |
| npm | pnpm |
| **OS packages** | **nfpm** — one static Go binary, one YAML file, emits deb/rpm/apk for *any* language. `cargo-deb`/`cargo-generate-rpm` read `Cargo.toml` and would work only for Rust. |
| Windows | portable zip (proven in mdmost) plus a winget manifest — no code-signing certificate needed |
| containers | multi-arch to `ghcr.io` from **pre-built static musl binaries** via `FROM scratch`, byonk's approach: nothing compiles inside Docker, so no compiler runs under QEMU. Tags `latest`, `x.y.z`, `x.y`, `x`. |
| Homebrew | formula + bottles, ported from mdmost; the formula and bottle commits must move off `main` to satisfy D1 |

Artifacts attach to the GitHub release. No apt/yum repository is hosted — that would need
a GPG key per organisation, stored and rotated, and would be the first credential this
design introduces.

Cross-compilation: `Cross.toml` pinning `ghcr.io/cross-rs/*-musl` images with `RUSTFLAGS`
passthrough, and `cross` itself pinned (`--version 0.2.5 --locked`) because the static
musl build cannot be rehearsed locally and so must not rest on a moving dependency.

## Spec 3 — prose (outline)

Two skills plus hygiene files.

**`man-pages`.** `man-pages(7)` is a real, citable standard: section order (NAME,
SYNOPSIS, CONFIGURATION, DESCRIPTION, OPTIONS, EXIT STATUS, ENVIRONMENT, FILES, VERSIONS,
STANDARDS, HISTORY, NOTES, CAVEATS, BUGS, EXAMPLES, SEE ALSO), semantic newlines,
gender-neutral language with singular "they", sentence-case subsection headings,
"for example" over "e.g.", and no implementation detail unless needed to use the
interface. Per D10 the skill encodes the standard rather than inventing one.

Build system ported from mdmost: `docs/manual.md` + `docs/man-deflist.lua` + `make man`,
with `man/` gitignored — a generated file not in version control cannot disagree with its
source. CI gets a "manual converts" job so a broken manual fails the PR that broke it
rather than surfacing at release time.

**`writing-style`.** Not an anti-AI checklist. The measurable machine-writing markers are
emoji section headers, low sentence-length variance, and structural formulas ("not just X,
but Y"; everything arriving in threes). The commonly cited ones — em dashes, "delve",
"robust" — are weak individually.

More usefully: the existing house prose breaks the popular rules and is unmistakably
human, because it cites **specific, checkable, hard-won detail**:

> `# And no || true. Swallowing the failure is what turned a broken step into a broken
> release: v0.1.1 was tagged with Cargo.toml at 0.1.1 and Cargo.lock still at 0.1.0, and
> the publish failed 6 minutes later.`

So the skill encodes *that* house style — every explanation names the concrete thing that
went wrong — bans emoji headers and the structural formulas, and leaves the em dashes
alone.

**Hygiene:** LICENSE, CONTRIBUTING.md, `.gitignore`, issue templates, CLAUDE.md scaffold.

## Spec 4 — docs sites (outline)

mdBook on GitHub Pages, versioned. byonk's design is kept; its storage mechanism is not.

**Kept:** `/dev/` for `main` and `/vX.Y.Z/` per release, `versions.json` for the version
selector, a root redirect to the newest, a cull policy (latest patch of the last 4 minor
versions), and a backfill mode that rebuilds docs for old tags.

**Replaced — this is a data-loss bug.** To preserve old versions, the deploy downloads the
live site over HTTP with `wget --mirror` and re-uploads it as the complete new site:

```bash
wget --mirror ... "$PAGES_URL/" 2>/dev/null || echo "No existing site to mirror"
```

If that `wget` fails — transient network error, Pages briefly 404ing, DNS hiccup — the
step succeeds anyway and the artifact uploaded a few steps later contains only the new
version. Every previously published version is silently deleted. This is the `|| true`
failure the house style already warns against.

A second, independent path to the same loss: `docs.yml` sets
`concurrency: {group: pages}`, but the `deploy-docs` job in `release.yml` sets no
concurrency group at all, so a release and a docs push can run at once, each mirroring a
site the other is replacing.

**The fix: a branch is the store.** Keep the published site in `gh-pages` and serve Pages
from that branch.

```
checkout gh-pages → drop in vX.Y.Z/ → regenerate versions.json + redirect
                  → cull → commit → push
```

Old versions are preserved by git rather than reconstructed over HTTP: exact, atomic,
concurrent-safe (a push either lands or is rejected) and **recoverable** — a bad deploy is
one `git revert` away. The `wget` step, both filename-mangling cleanup hacks and the
silent-wipe path disappear together. `main` stays protected; `gh-pages` is not, so a
workflow may push to it.

**Also:**

- Toolchain via `taiki-e/install-action` (verified to support `mdbook`, `mdbook-mermaid`
  and `mdbook-linkcheck`) rather than curling pinned tarballs. It pins, caches, and —
  the real win — dependabot can see the version, which a URL in a shell heredoc never
  will.
- Backfill computes its matrix from tags. `matrix: version: [v0.8.0, v0.7.1, …]` is
  hand-maintained and stale the day after a release.
- `mdbook-linkcheck` in CI, so broken internal links fail the PR that made them.
- Version-management logic moves to `lib/docs-versions.js` under D8.

## Risks and things to re-verify

The prose that survives D10 is the part explaining *why*, and that part has no automatic
test. If a trap stops being true, nothing fails — the skill merely carries a stale reason.
Each entry below gets a "check this still holds" line in `references/release-flow.md`
naming what to test.

| Assumption | How to re-check | If it changes |
|---|---|---|
| `GITHUB_TOKEN`-created PRs park their `pull_request` runs in an approval-required state rather than skipping them (**re-verified 2026-08-18**; this reversed the original D2) | open a release PR; the merge box should show an *Approve workflows to run* banner | if runs stop being created at all, the two required checks can never report and D2 must revert to no required checks |
| a job skipped by a job-level `if:` reports Success, while a workflow skipped by `paths`/`branches` stays Pending | open a PR that touches nothing the filter matches; watch the check | D13's whole escape-hatch mechanism fails; the changelog gate cannot be required |
| Dependabot ignores a label that does not exist, silently | delete the `no-changelog` label; open a dependabot PR | the label-creation step in `apply` becomes unnecessary, not harmful |
| `can_approve_pull_request_reviews` is the create-PR toggle | set it `false` on a test repo and run the release | D3 needs a different field |
| an empty `bypass_actors` is required (the Actions token cannot be listed) | attempt to add it via the rulesets API | the two-step release could collapse to one step |
| org policy does not override D3 on `oposs` | `gh auth refresh -h github.com -s admin:org`, then read `orgs/oposs/actions/permissions/workflow` | protection may need an org-level change first |
| `pnpm-lock.yaml` does not record the root version | first node release; the read-back assert fires | add the lockfile to that ecosystem's version files |

## Sources

- [`man-pages(7)`](https://man7.org/linux/man-pages/man7/man-pages.7.html) — man page conventions
- [Signs of AI Writing (2026)](https://slopdetector.org/blog/signs-of-ai-writing) — measurable markers
- [Maintaining open source in the age of generative AI](https://blog.probabl.ai/maintaining-open-source-age-of-gen-ai)
- [The Last Fingerprint: How Markdown Training Shapes LLM Prose](https://arxiv.org/pdf/2603.27006)
- `oposs/mkp-builder` — two-step release, `RELEASING.md`, ruleset 20940234
- `oetiker/mdmost` — man page build, cross-compilation, Homebrew, the `Cargo.lock` lesson
- `oetiker/byonk` — containers, `Cross.toml`, versioned mdBook docs
