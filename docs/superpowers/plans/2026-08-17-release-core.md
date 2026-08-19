# Release Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the two-step release system as a tested JavaScript library plus four workflows, and prove it by having `oposs/repo-infra` release itself with it.

**Architecture:** All release logic lives in CommonJS modules under `.github/workflows/lib/`, unit-tested with the Node built-in test runner. Workflows are thin `actions/github-script` wrappers that `require()` those modules. `CHANGES.md` is the source of truth for the released version; `.github/repo-infra.json` declares which other files carry a derived copy. Nothing pushes to a branch — commits, tags and releases go through the Git Data and Releases APIs.

**Tech Stack:** Node 22 (CommonJS, `node:test`, `node:assert/strict`), GitHub Actions, `actions/github-script@v9`, `gh` CLI for one-off repository administration.

**Spec:** `docs/superpowers/specs/2026-08-17-repo-infra-design.md`

## Scope

This plan covers **part of spec 1** — the release core, developed and proven inside `repo-infra` itself.

A second plan covers the rest of spec 1: the plugin shell, `detection.json`, `manifest.json`, the Python checker, `SKILL.md` and the `check`/`apply` commands. That plan turns the artefacts this one produces into installable assets. It comes second because the assets must exist and be proven before there is any point shipping a tool that installs them.

Success for this plan: `oposs/repo-infra` cuts release `v0.1.0` by dispatching **Create release PR**, a human merging that PR, and the publish workflow tagging and publishing with no further action.

## Global Constraints

- **Node 22**, pinned via `actions/setup-node@v7`. Library modules are **CommonJS** (`module.exports` / `require`) because that is what `actions/github-script` provides.
- **Action versions** (verified 2026-08-17): `actions/checkout@v7`, `actions/setup-node@v7`, `actions/github-script@v9`.
- **Every workflow file** carries a marker comment on its second line: `# repo-infra: <asset-name> v<n>` (spec D11).
- **No `git push`, no `git tag`, no `git config`** in any workflow. Git operations use the Git Data API (spec D9).
- **No `|| true`** and no swallowed failures anywhere. A step that cannot do its job fails the run.
- **Changelog headings**: `## [Unreleased]` with `### New` / `### Changed` / `### Fixed`. `New`, not `Added` (spec D6).
- **Every commit message** ends with:
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`
- **From Task 3 onward `main` is protected.** Every subsequent task lands through a branch and a pull request. Direct pushes to `main` will be rejected, and that is the point.
- Repository-level administration (`gh repo create`, ruleset creation) is **outward-facing**. Confirm with the user before running those commands.

## Deviation from the spec

The spec calls the per-repo state file `.github/repo-infra.yml`. **This plan uses `.github/repo-infra.json` instead.** `actions/github-script` bundles no YAML parser, so YAML would mean installing a dependency inside every workflow of every repo, for one small config file. JSON parses with `JSON.parse` and nothing else. The file is written by `apply` and only occasionally hand-edited, so losing comments is a small price. Update the spec when this plan lands.

## Module interfaces

Defined once here so tasks stay consistent. Each is implemented by the task named.

| Module | Exports | Task |
|---|---|---|
| `version.js` | `parse(tag)`, `compare(a, b)`, `latest(tags)`, `next(latestTag, releaseType)` | 2 |
| `changes.js` | `unreleasedBlock(text)`, `isEmpty(block)`, `roll(text, version, date)`, `latestRelease(text)`, `notesFor(text, version)` | 4 |
| `bump.js` | `bumpFile(spec, version, io)`, `bumpAll(specs, version, io)`, `verifyFile(spec, version, io)` | 5 |
| `checks.js` | `checkState(github, params)`, `waitForChecks(github, params, opts)` | 6 |
| `commit.js` | `commitFiles(github, params)` | 7 |

## File structure

```
.claude-plugin/plugin.json        version file (derived copy of CHANGES.md)
.github/
  repo-infra.json                 per-repo config: version_files, moving_major_tag
  dependabot.yml
  workflows/
    ci.yml                        runs the library tests
    changelog.yml            required: does this PR touch [Unreleased]?
    release-pr.yml         half one of the release
    release-publish.yml         half two of the release
    lib/
      version.js  version.test.js
      changes.js  changes.test.js
      bump.js     bump.test.js
      checks.js   checks.test.js
      commit.js   commit.test.js
CHANGES.md                        source of truth for the released version
README.md  LICENSE  RELEASING.md  .gitignore
```

Each module has one responsibility and no dependency on any other module, so they can be written and reviewed independently. The workflows are the only place they are composed.

---

### Task 1: Repository bootstrap

**Files:**
- Create: `CHANGES.md`, `README.md`, `LICENSE`, `.gitignore`, `.claude-plugin/plugin.json`, `.github/repo-infra.json`

**Interfaces:**
- Consumes: nothing
- Produces: `CHANGES.md` in the exact shape `changes.js` parses (Task 4); `.github/repo-infra.json` in the exact shape the workflows read (Tasks 9, 10)

- [ ] **Step 1: Create `CHANGES.md`**

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
except that the first subsection is called `New` rather than `Added`. The release
workflow matches on `### New`; renaming it silently drops the section from the
release notes.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### New

### Changed

### Fixed
```

- [ ] **Step 2: Create `.claude-plugin/plugin.json`**

```json
{
  "name": "repo-infra",
  "description": "Bring a repository's release, protection, CI and documentation infrastructure up to the current standard, and keep it there.",
  "version": "0.0.0",
  "author": {
    "name": "Tobias Oetiker",
    "email": "tobi@oetiker.ch"
  }
}
```

`0.0.0` is deliberate: no release has happened yet, and Task 11 is what moves it.

- [ ] **Step 3: Create `.github/repo-infra.json`**

```json
{
  "ecosystems": ["claude-plugin"],
  "moving_major_tag": false,
  "version_files": [
    {
      "path": ".claude-plugin/plugin.json",
      "pattern": "\"version\"\\s*:\\s*\"[^\"]*\"",
      "replacement": "\"version\": \"$VERSION\"",
      "verify": "\"version\"\\s*:\\s*\"$VERSION\""
    }
  ]
}
```

`moving_major_tag` is `false` because nothing consumes `repo-infra` as a GitHub Action. A repo that is consumed as an action sets it `true` and gets a moving `vX` tag.

- [ ] **Step 4: Create `.gitignore`**

```gitignore
node_modules/
*~
.DS_Store
```

- [ ] **Step 5: Create `LICENSE`**

Write the MIT licence text, copyright `2026 Tobias Oetiker`.

- [ ] **Step 6: Create `README.md`**

```markdown
# repo-infra

A Claude Code plugin that brings a repository's release, protection, CI and
documentation infrastructure up to the current standard — and reports how far
behind it has drifted when the standard moves.

Design: [`docs/superpowers/specs/2026-08-17-repo-infra-design.md`](docs/superpowers/specs/2026-08-17-repo-infra-design.md)

## Status

Under construction. The release core is being built and proven here first; the
plugin that installs it elsewhere comes next.
```

- [ ] **Step 7: Verify the files parse**

Run:
```bash
cd /home/oetiker/checkouts/repo-infra
node -e 'JSON.parse(require("fs").readFileSync(".claude-plugin/plugin.json","utf8")); JSON.parse(require("fs").readFileSync(".github/repo-infra.json","utf8")); console.log("both parse")'
```
Expected: `both parse`

- [ ] **Step 8: Commit**

```bash
git add CHANGES.md README.md LICENSE .gitignore .claude-plugin .github
git commit -m "Bootstrap the repository

CHANGES.md is the source of truth for the released version, so it exists
before anything that reads it. .github/repo-infra.json declares the one
derived copy: .claude-plugin/plugin.json.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `version.js` — semver arithmetic

**Files:**
- Create: `.github/workflows/lib/version.js`
- Test: `.github/workflows/lib/version.test.js`

**Interfaces:**
- Consumes: nothing
- Produces: `parse(tag) -> {major,minor,patch}|null`, `compare(a,b) -> number`, `latest(tags: string[]) -> string`, `next(latestTag: string, releaseType: 'bugfix'|'feature'|'major') -> string`. `next` returns a bare version with **no leading `v`**, because that is what `CHANGES.md` headings use.

- [ ] **Step 1: Write the failing test**

Create `.github/workflows/lib/version.test.js`:

```js
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const version = require('./version.js');

test('parse accepts a release tag', () => {
  assert.deepEqual(version.parse('v1.2.3'), { major: 1, minor: 2, patch: 3 });
});

test('parse rejects anything that is not vX.Y.Z', () => {
  assert.equal(version.parse('v1.2'), null);
  assert.equal(version.parse('1.2.3'), null);
  assert.equal(version.parse('v1.2.3-rc1'), null);
  assert.equal(version.parse('nightly'), null);
});

test('latest sorts numerically, not lexically', () => {
  // The case a plain string sort gets wrong: '1.9.0' > '1.10.0' as text.
  assert.equal(version.latest(['v1.0.0', 'v1.9.0', 'v1.10.0', 'v1.2.0']), 'v1.10.0');
});

test('latest ignores tags that are not releases', () => {
  assert.equal(version.latest(['v1.0.0', 'nightly', 'v2.0.0', 'v2.0.0-rc1']), 'v2.0.0');
});

test('latest of no tags is the zero version', () => {
  assert.equal(version.latest([]), 'v0.0.0');
});

test('next increments the right component', () => {
  assert.equal(version.next('v1.2.3', 'bugfix'), '1.2.4');
  assert.equal(version.next('v1.2.3', 'feature'), '1.3.0');
  assert.equal(version.next('v1.2.3', 'major'), '2.0.0');
});

test('next resets lower components', () => {
  assert.equal(version.next('v1.9.7', 'feature'), '1.10.0');
  assert.equal(version.next('v1.9.7', 'major'), '2.0.0');
});

test('the first release of a fresh repo', () => {
  assert.equal(version.next('v0.0.0', 'feature'), '0.1.0');
});

test('next rejects an unknown release type', () => {
  assert.throws(() => version.next('v1.2.3', 'patch'), /unknown release type: patch/);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd /home/oetiker/checkouts/repo-infra && node --test .github/workflows/lib/*.test.js
```
Expected: FAIL — `Cannot find module './version.js'`

- [ ] **Step 3: Write the implementation**

Create `.github/workflows/lib/version.js`:

```js
'use strict';

// Release tags are exactly vX.Y.Z. Pre-release and build suffixes are deliberately
// not matched: the release flow has no concept of them, and quietly accepting one
// would let it compute a "next" version from a tag it cannot reproduce.
const TAG_RE = /^v(\d+)\.(\d+)\.(\d+)$/;

function parse(tag) {
  const m = TAG_RE.exec(tag);
  if (!m) return null;
  return { major: Number(m[1]), minor: Number(m[2]), patch: Number(m[3]) };
}

function compare(a, b) {
  const pa = parse(a);
  const pb = parse(b);
  if (!pa) throw new Error(`not a release tag: ${a}`);
  if (!pb) throw new Error(`not a release tag: ${b}`);
  return (pa.major - pb.major) || (pa.minor - pb.minor) || (pa.patch - pb.patch);
}

function latest(tags) {
  const releases = tags.filter((t) => TAG_RE.test(t));
  if (releases.length === 0) return 'v0.0.0';
  return releases.sort(compare)[releases.length - 1];
}

function next(latestTag, releaseType) {
  const v = parse(latestTag);
  if (!v) throw new Error(`not a release tag: ${latestTag}`);
  switch (releaseType) {
    case 'major': return `${v.major + 1}.0.0`;
    case 'feature': return `${v.major}.${v.minor + 1}.0`;
    case 'bugfix': return `${v.major}.${v.minor}.${v.patch + 1}`;
    default: throw new Error(`unknown release type: ${releaseType}`);
  }
}

module.exports = { parse, compare, latest, next };
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
cd /home/oetiker/checkouts/repo-infra && node --test .github/workflows/lib/*.test.js
```
Expected: PASS — 9 tests, 0 failures

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/lib/version.js .github/workflows/lib/version.test.js
git commit -m "Add version.js: semver arithmetic for the release flow

Release tags are exactly vX.Y.Z; anything else is ignored rather than
guessed at. latest() sorts numerically, because a string sort puts
v1.9.0 above v1.10.0 and would silently release backwards.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: GitHub repository, CI, and protection

This is the task that makes everything after it land through a pull request.

**Files:**
- Create: `.github/workflows/ci.yml`, `.github/dependabot.yml`, `ruleset-main.json` (temporary, not committed)

**Interfaces:**
- Consumes: `.github/workflows/lib/version.test.js` (Task 2) — CI needs at least one test to run
- Produces: a protected `main` on `oposs/repo-infra`; a CI check named `Workflow library tests` that Task 9's guard will read

- [ ] **Step 1: Create `.github/workflows/ci.yml`**

```yaml
name: CI
# repo-infra: ci v1

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  lib:
    name: Workflow library tests
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-node@v7
        with:
          node-version: 22

      # The release logic is a library, so it is tested like one. Before this,
      # the changelog roller was a Perl program inside a YAML string whose only
      # test was cutting a release.
      - name: Run the workflow library tests
        run: node --test .github/workflows/lib/*.test.js

  # The single context the ruleset requires (spec D2). It exists so branch
  # protection can name one check that means "this repository's CI passed",
  # whatever this repository's jobs happen to be. Add every job above to needs.
  ci-passed:
    if: always()
    needs: [lib]
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - if: contains(needs.*.result, 'failure') || contains(needs.*.result, 'cancelled')
        run: exit 1
```

`if: always()` is not optional and not cosmetic. Without it, `ci-passed` is *skipped* when a dependency fails — and GitHub reports a skipped job as **Success** to branch protection. The required check would go green on a red build. This fails open, silently, and looks like it is working; it is the most dangerous single line in this plan to get wrong.

The job has no `name:`, so its check context is the job id, `ci-passed` — which is what the ruleset in Step 8 names.

- [ ] **Step 2: Create `.github/dependabot.yml`**

```yaml
version: 2
# repo-infra: dependabot v1
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
    labels:
      - dependencies
      - no-changelog
```

The `no-changelog` label matters more than it looks. The changelog gate added in Task 8 is a **required** check, so without the label every weekly dependabot pull request is blocked, not merely red.

**Create the label now — Dependabot cannot.** Dependabot never creates labels, and a label that does not exist in the repository is **silently ignored**: the config above would look correct, apply nothing, and leave dependabot's PRs hanging on a required check with no error anywhere explaining why.

```bash
gh label create no-changelog \
  --description "Change needs no changelog entry" \
  --color ededed
```

Run this once the repository exists (Step 4). Verify with `gh label list --search no-changelog`.

- [ ] **Step 3: Commit locally**

```bash
git add .github/workflows/ci.yml .github/dependabot.yml
git commit -m "Add CI and dependabot

CI runs the workflow library tests. dependabot keeps action versions
current per repository, which is a job GitHub already does better than a
checker that has to be told the answers.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 4: Create the GitHub repository — CONFIRM WITH THE USER FIRST**

This creates a public repository in the `oposs` organisation. Ask before running it.

```bash
cd /home/oetiker/checkouts/repo-infra
gh repo create oposs/repo-infra \
  --public \
  --source=. \
  --remote=origin \
  --description "Bring a repository's release, protection, CI and documentation infrastructure up to the current standard" \
  --push
```

- [ ] **Step 5: Verify CI ran and is green**

Run:
```bash
gh run list --repo oposs/repo-infra --workflow ci.yml --limit 1
gh run watch --repo oposs/repo-infra "$(gh run list --repo oposs/repo-infra --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
```
Expected: conclusion `success`, job name `Workflow library tests`

If CI is red here, stop. Everything downstream assumes the library tests run in CI.

- [ ] **Step 6: Allow Actions to open pull requests (spec D3)**

```bash
gh api -X PUT repos/oposs/repo-infra/actions/permissions/workflow \
  -f default_workflow_permissions=write \
  -F can_approve_pull_request_reviews=true
```

- [ ] **Step 7: Verify the setting took**

Run:
```bash
gh api repos/oposs/repo-infra/actions/permissions/workflow
```
Expected: `{"default_workflow_permissions":"write","can_approve_pull_request_reviews":true}`

Read it back rather than trusting the write. If `can_approve_pull_request_reviews` is `false`, an organisation policy is overriding the repository setting and Task 11 will fail with "GitHub Actions is not permitted to create or approve pull requests". Resolve that before continuing.

- [ ] **Step 8: Protect `main` (spec D1, D2)**

Write `ruleset-main.json` to a scratch path (do **not** commit it; the plugin will ship it as an asset in the next plan):

```json
{
  "name": "main",
  "target": "branch",
  "enforcement": "active",
  "bypass_actors": [],
  "conditions": {
    "ref_name": {
      "include": ["~DEFAULT_BRANCH"],
      "exclude": []
    }
  },
  "rules": [
    { "type": "deletion" },
    { "type": "creation" },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "allowed_merge_methods": ["merge", "squash", "rebase"],
        "dismiss_stale_reviews_on_push": false,
        "dismissal_restriction": { "allowed_actors": [], "enabled": false },
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": false,
        "required_reviewers": []
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": false,
        "required_status_checks": [
          { "context": "ci-passed" }
        ]
      }
    }
  ]
}
```

Then:
```bash
gh api -X POST repos/oposs/repo-infra/rulesets \
  --input /scratch/oetiker/claude-tmp/ruleset-main.json
```

**Only `ci-passed` is required at this point, not `changelog-updated`.** The gate does not exist until Task 8. A required status check whose workflow is absent never reports and blocks *every* pull request in the repository — including the ones that build the rest of this plan. Task 8 adds the second context after the gate is merged.

This is the same ordering rule `apply` follows on any repository (spec, *The run model*): create the label, land the workflows, **then** require the checks. `repo-infra` gets no exemption from it.

`strict_required_status_checks_policy` is `false` on purpose: with `true`, every push to `main` makes an open release PR stale, and re-syncing it re-parks its checks behind another approval click.

`required_approving_review_count` is `0` so a solo maintainer can merge their own release PR.

**The release PR needs one click.** A pull request opened by `GITHUB_TOKEN` creates its `pull_request` workflow runs in an *approval-required* state — the merge box shows a banner, and a user with write access starts them with **Approve workflows to run**. The checks are parked, not skipped, so a required check does report and the PR does merge. Do not try to avoid the click with an `on: push` trigger on the release branch: pushes made with `GITHUB_TOKEN` do not trigger workflows either (spec D2).

- [ ] **Step 9: Verify protection is active and direct pushes are refused**

Run:
```bash
gh api repos/oposs/repo-infra/rulesets --jq '.[] | "\(.name) \(.target) \(.enforcement)"'
```
Expected: `main branch active`

Then prove it:
```bash
cd /home/oetiker/checkouts/repo-infra
git commit --allow-empty -m "protection probe"
git push origin main
```
Expected: **FAIL** — `protected branch hook declined` or `Changes must be made through a pull request`

Then undo the probe commit locally:
```bash
git reset --soft HEAD~1
```

This step is the one that proves the rest of the plan is being executed under the same rules it installs. If the push succeeds, protection is not active and you must fix it before continuing.

---

### Task 4: `changes.js` — the changelog roller

From here on, work on a branch and open a pull request.

Every such step ends `gh pr create` / `gh pr checks --watch` / `gh pr merge`.
The wait is not optional: the ruleset requires `ci-passed`, so a merge issued
in the same breath as the create is refused for a check that has not reported
yet. `gh pr merge --auto` is the alternative, but it returns before the merge
happens, so the following `git pull` would race it.

**Files:**
- Create: `.github/workflows/lib/changes.js`
- Test: `.github/workflows/lib/changes.test.js`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `unreleasedBlock(text) -> string` — the content under `## [Unreleased]`, heading excluded. Throws if the heading is absent.
  - `isEmpty(block) -> boolean` — true when the block holds only `### ` headings and blank lines.
  - `roll(text, version, date) -> string` — returns the new file content. Throws if the heading is absent or the block is empty.
  - `latestRelease(text) -> {version, date}|null` — the topmost `## X.Y.Z - YYYY-MM-DD`.
  - `notesFor(text, version) -> string` — that version's section body, trimmed. Throws if absent.

- [ ] **Step 1: Create the branch**

```bash
cd /home/oetiker/checkouts/repo-infra
git checkout -b lib/changes
```

- [ ] **Step 2: Write the failing test**

Create `.github/workflows/lib/changes.test.js`:

```js
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const changes = require('./changes.js');

const EMPTY = [
  '# Changelog',
  '',
  'Preamble that must survive.',
  '',
  '## [Unreleased]',
  '',
  '### New',
  '',
  '### Changed',
  '',
  '### Fixed',
  '',
].join('\n');

const FILLED = [
  '# Changelog',
  '',
  'Preamble that must survive.',
  '',
  '## [Unreleased]',
  '',
  '### New',
  '- a new thing',
  '',
  '### Changed',
  '',
  '### Fixed',
  '- a fixed thing',
  '',
  '## 1.2.3 - 2026-08-01',
  '### New',
  '- an older thing',
  '',
  '## 1.2.2 - 2026-07-01',
  '### Fixed',
  '- an even older thing',
  '',
].join('\n');

test('unreleasedBlock returns the block without its heading', () => {
  assert.match(changes.unreleasedBlock(FILLED), /a new thing/);
  assert.doesNotMatch(changes.unreleasedBlock(FILLED), /Unreleased/);
  assert.doesNotMatch(changes.unreleasedBlock(FILLED), /an older thing/);
});

test('unreleasedBlock fails loudly on the wrong heading style', () => {
  const wrong = EMPTY.replace('## [Unreleased]', '## Unreleased');
  assert.throws(() => changes.unreleasedBlock(wrong), /no '## \[Unreleased\]' heading/);
});

test('isEmpty is true for a skeleton and false once something is added', () => {
  assert.equal(changes.isEmpty(changes.unreleasedBlock(EMPTY)), true);
  assert.equal(changes.isEmpty(changes.unreleasedBlock(FILLED)), false);
});

test('roll refuses to release an empty Unreleased section', () => {
  assert.throws(() => changes.roll(EMPTY, '1.3.0', '2026-08-17'), /nothing to release/);
});

test('roll moves the content into a dated section', () => {
  const out = changes.roll(FILLED, '1.3.0', '2026-08-17');
  assert.match(out, /^## 1\.3\.0 - 2026-08-17$/m);
  assert.match(out, /## 1\.3\.0 - 2026-08-17\n### New\n- a new thing/);
});

test('roll drops subsections that had no entries', () => {
  const out = changes.roll(FILLED, '1.3.0', '2026-08-17');
  const section = changes.notesFor(out, '1.3.0');
  assert.match(section, /### New/);
  assert.match(section, /### Fixed/);
  assert.doesNotMatch(section, /### Changed/);
});

test('roll leaves a fresh empty Unreleased skeleton behind', () => {
  const out = changes.roll(FILLED, '1.3.0', '2026-08-17');
  assert.equal(changes.isEmpty(changes.unreleasedBlock(out)), true);
  assert.match(out, /## \[Unreleased\]\n\n### New\n\n### Changed\n\n### Fixed/);
});

test('roll preserves the preamble and every earlier release', () => {
  const out = changes.roll(FILLED, '1.3.0', '2026-08-17');
  assert.match(out, /Preamble that must survive/);
  assert.match(out, /## 1\.2\.3 - 2026-08-01/);
  assert.match(out, /## 1\.2\.2 - 2026-07-01/);
});

test('rolling twice is possible: the result is still parseable', () => {
  const once = changes.roll(FILLED, '1.3.0', '2026-08-17');
  assert.throws(() => changes.roll(once, '1.4.0', '2026-08-18'), /nothing to release/);
});

test('latestRelease returns the topmost version', () => {
  assert.deepEqual(changes.latestRelease(FILLED), { version: '1.2.3', date: '2026-08-01' });
});

test('latestRelease is null before the first release', () => {
  assert.equal(changes.latestRelease(EMPTY), null);
});

test('notesFor returns only that version', () => {
  const notes = changes.notesFor(FILLED, '1.2.3');
  assert.match(notes, /an older thing/);
  assert.doesNotMatch(notes, /an even older thing/);
  assert.doesNotMatch(notes, /## 1\.2\.2/);
});

test('notesFor fails loudly for a version that is not there', () => {
  assert.throws(() => changes.notesFor(FILLED, '9.9.9'), /no section for 9\.9\.9/);
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run:
```bash
cd /home/oetiker/checkouts/repo-infra && node --test .github/workflows/lib/*.test.js
```
Expected: FAIL — `Cannot find module './changes.js'`

- [ ] **Step 4: Write the implementation**

Create `.github/workflows/lib/changes.js`:

```js
'use strict';

// The bracketed form, per Keep a Changelog. mdmost used a bare '## Unreleased';
// supporting both would make this a guessing machine, so the odd one out is
// migrated instead.
const UNRELEASED_HEADING = '## [Unreleased]';
const RELEASE_RE = /^## (\d+\.\d+\.\d+) - (\d{4}-\d{2}-\d{2})\s*$/;

// Where a '## ' block ends: at the next '## ', or at the end of the file.
function blockEnd(lines, start) {
  for (let i = start + 1; i < lines.length; i += 1) {
    if (lines[i].startsWith('## ')) return i;
  }
  return lines.length;
}

function findUnreleased(lines) {
  const start = lines.findIndex((l) => l.trim() === UNRELEASED_HEADING);
  if (start === -1) return null;
  return { start, end: blockEnd(lines, start) };
}

function unreleasedBlock(text) {
  const lines = text.split('\n');
  const range = findUnreleased(lines);
  if (!range) {
    throw new Error(`CHANGES.md has no '${UNRELEASED_HEADING}' heading`);
  }
  return lines.slice(range.start + 1, range.end).join('\n');
}

function isEmpty(block) {
  return block
    .split('\n')
    .filter((l) => l.trim() !== '' && !l.trim().startsWith('### '))
    .length === 0;
}

// Split a block into its '### ' subsections, with each body trimmed.
function subsections(block) {
  const out = [];
  let current = null;
  for (const line of block.split('\n')) {
    if (line.trim().startsWith('### ')) {
      current = { heading: line.trim(), body: [] };
      out.push(current);
    } else if (current) {
      current.body.push(line);
    }
  }
  return out.map((s) => ({ heading: s.heading, body: s.body.join('\n').trim() }));
}

function roll(text, version, date) {
  const lines = text.split('\n');
  const range = findUnreleased(lines);
  if (!range) {
    throw new Error(`CHANGES.md has no '${UNRELEASED_HEADING}' heading`);
  }

  const block = lines.slice(range.start + 1, range.end).join('\n');
  const kept = subsections(block).filter((s) => s.body !== '');
  if (kept.length === 0) {
    throw new Error(`'${UNRELEASED_HEADING}' is empty - nothing to release`);
  }

  const skeleton = [UNRELEASED_HEADING, '', '### New', '', '### Changed', '', '### Fixed', ''];
  const released = [`## ${version} - ${date}`];
  for (const s of kept) {
    released.push(s.heading, s.body, '');
  }

  return [
    ...lines.slice(0, range.start),
    ...skeleton,
    ...released,
    ...lines.slice(range.end),
  ].join('\n');
}

function latestRelease(text) {
  for (const line of text.split('\n')) {
    const m = RELEASE_RE.exec(line);
    if (m) return { version: m[1], date: m[2] };
  }
  return null;
}

function notesFor(text, version) {
  const lines = text.split('\n');
  const start = lines.findIndex((l) => {
    const m = RELEASE_RE.exec(l);
    return m !== null && m[1] === version;
  });
  if (start === -1) {
    throw new Error(`CHANGES.md has no section for ${version}`);
  }
  return lines.slice(start + 1, blockEnd(lines, start)).join('\n').trim();
}

module.exports = { unreleasedBlock, isEmpty, roll, latestRelease, notesFor };
```

- [ ] **Step 5: Run the tests to verify they pass**

Run:
```bash
cd /home/oetiker/checkouts/repo-infra && node --test .github/workflows/lib/*.test.js
```
Expected: PASS — 22 tests total (9 from Task 2, 13 here), 0 failures

- [ ] **Step 6: Add a changelog entry**

Under `### New` in `CHANGES.md`:

```markdown
- `changes.js`: parse, roll and extract release notes from `CHANGES.md`, with the
  roller validating the file's shape before it writes. The previous implementations
  were single regexes that produced nothing at all on an unexpected shape, and
  "nothing" is indistinguishable from "no changes to release".
```

- [ ] **Step 7: Commit, push, open and merge the pull request**

```bash
git add .github/workflows/lib/changes.js .github/workflows/lib/changes.test.js CHANGES.md
git commit -m "Add changes.js: the changelog roller

Validates before it writes. Both previous implementations were single
large regexes that silently produced nothing when the file shape was
unexpected, which reads exactly like 'no changes to release'.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push -u origin lib/changes
gh pr create --fill --base main
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

---

### Task 5: `bump.js` — the version-file writer

**Files:**
- Create: `.github/workflows/lib/bump.js`
- Test: `.github/workflows/lib/bump.test.js`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `bumpFile(spec, version, io) -> string` — locates, rewrites, then **reads back and asserts**. `spec` is `{path, pattern, replacement, verify}` exactly as stored in `.github/repo-infra.json`. `io` is `{read(path) -> string, write(path, content) -> void}`. Returns the new content. Throws if the pattern does not match or the read-back fails.
  - `bumpAll(specs, version, io) -> void`
  - `verifyFile(spec, version, io) -> boolean` — does the file already carry this version? Used by the publisher's cross-check.

- [ ] **Step 1: Create the branch**

```bash
cd /home/oetiker/checkouts/repo-infra && git checkout -b lib/bump
```

- [ ] **Step 2: Write the failing test**

Create `.github/workflows/lib/bump.test.js`:

```js
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const bump = require('./bump.js');

const PLUGIN_SPEC = {
  path: '.claude-plugin/plugin.json',
  pattern: '"version"\\s*:\\s*"[^"]*"',
  replacement: '"version": "$VERSION"',
  verify: '"version"\\s*:\\s*"$VERSION"',
};

const CARGO_SPEC = {
  path: 'Cargo.toml',
  pattern: '^version = "[^"]*"',
  replacement: 'version = "$VERSION"',
  verify: '^version = "$VERSION"',
};

function memIO(files) {
  return {
    read: (p) => {
      if (!(p in files)) throw new Error(`ENOENT: ${p}`);
      return files[p];
    },
    write: (p, c) => { files[p] = c; },
  };
}

test('bumpFile rewrites the version', () => {
  const files = { '.claude-plugin/plugin.json': '{\n  "version": "0.0.0"\n}\n' };
  bump.bumpFile(PLUGIN_SPEC, '1.2.3', memIO(files));
  assert.match(files['.claude-plugin/plugin.json'], /"version": "1\.2\.3"/);
});

test('bumpFile leaves the rest of the file alone', () => {
  const files = {
    '.claude-plugin/plugin.json': '{\n  "name": "x",\n  "version": "0.0.0"\n}\n',
  };
  bump.bumpFile(PLUGIN_SPEC, '1.2.3', memIO(files));
  assert.match(files['.claude-plugin/plugin.json'], /"name": "x"/);
});

test('bumpFile anchors to the start of a line where the pattern says so', () => {
  // A Cargo.toml dependency also has a `version = "..."` line, but indented
  // under a table. The ^ anchor is what keeps the package version distinct.
  const files = {
    'Cargo.toml': '[package]\nversion = "0.1.0"\n\n[dependencies]\nanyhow = { version = "1.0" }\n',
  };
  bump.bumpFile(CARGO_SPEC, '0.2.0', memIO(files));
  assert.match(files['Cargo.toml'], /^version = "0\.2\.0"$/m);
  assert.match(files['Cargo.toml'], /anyhow = \{ version = "1\.0" \}/);
});

test('bumpFile fails loudly when the pattern does not match', () => {
  const files = { '.claude-plugin/plugin.json': '{\n  "name": "x"\n}\n' };
  assert.throws(
    () => bump.bumpFile(PLUGIN_SPEC, '1.2.3', memIO(files)),
    /no match for/,
  );
});

test('bumpFile fails when the write did not take', () => {
  // This is the whole reason the read-back exists. mdmost tagged v0.1.1 with
  // Cargo.toml at 0.1.1 and Cargo.lock still at 0.1.0 because a failed write
  // was swallowed; the publish died six minutes later.
  const files = { '.claude-plugin/plugin.json': '{\n  "version": "0.0.0"\n}\n' };
  const brokenIO = { read: (p) => files[p], write: () => { /* silently drops it */ } };
  assert.throws(
    () => bump.bumpFile(PLUGIN_SPEC, '1.2.3', brokenIO),
    /did not take/,
  );
});

test('bumpAll bumps every file', () => {
  const files = {
    '.claude-plugin/plugin.json': '{\n  "version": "0.0.0"\n}\n',
    'Cargo.toml': '[package]\nversion = "0.1.0"\n',
  };
  bump.bumpAll([PLUGIN_SPEC, CARGO_SPEC], '2.0.0', memIO(files));
  assert.match(files['.claude-plugin/plugin.json'], /"version": "2\.0\.0"/);
  assert.match(files['Cargo.toml'], /^version = "2\.0\.0"$/m);
});

test('verifyFile reports whether the file already carries the version', () => {
  const files = { '.claude-plugin/plugin.json': '{\n  "version": "1.2.3"\n}\n' };
  const io = memIO(files);
  assert.equal(bump.verifyFile(PLUGIN_SPEC, '1.2.3', io), true);
  assert.equal(bump.verifyFile(PLUGIN_SPEC, '1.2.4', io), false);
});

test('verifyFile is not fooled by a version that is a prefix of another', () => {
  const files = { '.claude-plugin/plugin.json': '{\n  "version": "1.2.30"\n}\n' };
  assert.equal(bump.verifyFile(PLUGIN_SPEC, '1.2.3', memIO(files)), false);
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run:
```bash
cd /home/oetiker/checkouts/repo-infra && node --test .github/workflows/lib/*.test.js
```
Expected: FAIL — `Cannot find module './bump.js'`

- [ ] **Step 4: Write the implementation**

Create `.github/workflows/lib/bump.js`:

```js
'use strict';

function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// The verify pattern is a template containing $VERSION. The version is escaped
// before substitution so its dots match literally: an unescaped '1.2.3' would
// also match '1x2x3', and — worse — '1.2.3' would match inside '1.2.30'.
function verifyPattern(spec, version) {
  return new RegExp(spec.verify.replace(/\$VERSION/g, escapeRegExp(version)) + '(?![0-9])', 'm');
}

function verifyFile(spec, version, io) {
  return verifyPattern(spec, version).test(io.read(spec.path));
}

function bumpFile(spec, version, io) {
  const before = io.read(spec.path);
  const locate = new RegExp(spec.pattern, 'm');

  if (!locate.test(before)) {
    throw new Error(
      `${spec.path}: no match for /${spec.pattern}/ - cannot set the version. `
      + 'Either the file changed shape or .github/repo-infra.json is wrong.',
    );
  }

  const after = before.replace(locate, spec.replacement.replace(/\$VERSION/g, version));
  io.write(spec.path, after);

  // Read back rather than trust the write. Without this a failed or swallowed
  // write produces a release that is internally inconsistent and looks fine
  // until something downstream refuses it.
  if (!verifyFile(spec, version, io)) {
    throw new Error(
      `${spec.path}: version ${version} did not take - the file does not match `
      + `/${spec.verify}/ after writing`,
    );
  }

  return after;
}

function bumpAll(specs, version, io) {
  for (const spec of specs) {
    bumpFile(spec, version, io);
  }
}

module.exports = { bumpFile, bumpAll, verifyFile };
```

- [ ] **Step 5: Run the tests to verify they pass**

Run:
```bash
cd /home/oetiker/checkouts/repo-infra && node --test .github/workflows/lib/*.test.js
```
Expected: PASS — 30 tests total, 0 failures

- [ ] **Step 6: Add a changelog entry**

Under `### New`:

```markdown
- `bump.js`: the generic version-file writer. Every write is located, rewritten and
  then read back and asserted, so a bump that does not take fails the release
  rather than tagging a repository whose files disagree with each other.
```

- [ ] **Step 7: Commit, push, merge**

```bash
git add .github/workflows/lib/bump.js .github/workflows/lib/bump.test.js CHANGES.md
git commit -m "Add bump.js: the generic version-file writer

Locate, rewrite, read back and assert. The read-back is the point: a
swallowed write is what tagged mdmost v0.1.1 with Cargo.toml at 0.1.1
and Cargo.lock at 0.1.0.

Adding an ecosystem is a JSON entry in .github/repo-infra.json, not code.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push -u origin lib/bump
gh pr create --fill --base main
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

---

### Task 6: `checks.js` — reading and waiting on check runs

**Files:**
- Create: `.github/workflows/lib/checks.js`
- Test: `.github/workflows/lib/checks.test.js`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `checkState(github, {owner, repo, ref}) -> Promise<{total, failed, pending, ok}>` where `failed` and `pending` are arrays of check-run objects and `ok` is true only when `total > 0` and both arrays are empty.
  - `waitForChecks(github, params, opts) -> Promise<state>` — polls until nothing is pending, something failed, or the timeout passes (in which case the result carries `timedOut: true`). `opts` accepts `{intervalMs, timeoutMs, sleep, now}` so it is testable without real time.

- [ ] **Step 1: Create the branch**

```bash
cd /home/oetiker/checkouts/repo-infra && git checkout -b lib/checks
```

- [ ] **Step 2: Write the failing test**

Create `.github/workflows/lib/checks.test.js`:

```js
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const checks = require('./checks.js');

const PARAMS = { owner: 'oposs', repo: 'repo-infra', ref: 'abc123' };

// A fake Octokit whose paginate returns successive fixtures, one per call.
function fakeGithub(pages) {
  let call = 0;
  return {
    rest: { checks: { listForRef: 'listForRef' } },
    paginate: async () => {
      const page = pages[Math.min(call, pages.length - 1)];
      call += 1;
      return page;
    },
    calls: () => call,
  };
}

const ok = (name) => ({ name, status: 'completed', conclusion: 'success' });
const bad = (name) => ({ name, status: 'completed', conclusion: 'failure' });
const running = (name) => ({ name, status: 'in_progress', conclusion: null });
const skipped = (name) => ({ name, status: 'completed', conclusion: 'skipped' });

test('all checks green is ok', async () => {
  const state = await checks.checkState(fakeGithub([[ok('CI'), ok('Changelog')]]), PARAMS);
  assert.equal(state.ok, true);
  assert.equal(state.total, 2);
});

test('a failure is not ok and is named', async () => {
  const state = await checks.checkState(fakeGithub([[ok('CI'), bad('Changelog')]]), PARAMS);
  assert.equal(state.ok, false);
  assert.deepEqual(state.failed.map((c) => c.name), ['Changelog']);
});

test('a running check is not ok and is named', async () => {
  const state = await checks.checkState(fakeGithub([[ok('CI'), running('Slow')]]), PARAMS);
  assert.equal(state.ok, false);
  assert.deepEqual(state.pending.map((c) => c.name), ['Slow']);
});

test('a skipped check does not count as a failure', async () => {
  const state = await checks.checkState(fakeGithub([[ok('CI'), skipped('Optional')]]), PARAMS);
  assert.equal(state.ok, true);
});

test('no checks at all is not ok', async () => {
  // The dangerous case: releasing a commit nothing ever tested.
  const state = await checks.checkState(fakeGithub([[]]), PARAMS);
  assert.equal(state.ok, false);
  assert.equal(state.total, 0);
});

test('waitForChecks returns as soon as something fails', async () => {
  const github = fakeGithub([[bad('CI')]]);
  const state = await checks.waitForChecks(github, PARAMS, {
    sleep: async () => { throw new Error('should not have slept'); },
  });
  assert.equal(state.ok, false);
  assert.equal(github.calls(), 1);
});

test('waitForChecks polls until pending clears', async () => {
  const github = fakeGithub([
    [running('CI')],
    [running('CI')],
    [ok('CI')],
  ]);
  let slept = 0;
  const state = await checks.waitForChecks(github, PARAMS, {
    sleep: async () => { slept += 1; },
  });
  assert.equal(state.ok, true);
  assert.equal(slept, 2);
});

test('waitForChecks gives up after the timeout', async () => {
  const github = fakeGithub([[running('CI')]]);
  let clock = 0;
  const state = await checks.waitForChecks(github, PARAMS, {
    intervalMs: 1000,
    timeoutMs: 3000,
    now: () => clock,
    sleep: async (ms) => { clock += ms; },
  });
  assert.equal(state.timedOut, true);
  assert.equal(state.ok, false);
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run:
```bash
cd /home/oetiker/checkouts/repo-infra && node --test .github/workflows/lib/*.test.js
```
Expected: FAIL — `Cannot find module './checks.js'`

- [ ] **Step 4: Write the implementation**

Create `.github/workflows/lib/checks.js`:

```js
'use strict';

// Everything that reported on the commit, whatever workflow produced it. The
// previous version polled listWorkflowRuns for a hardcoded 'test.yml', which
// saw one workflow and broke whenever a repo named its CI something else.
const PASSING = new Set(['success', 'neutral', 'skipped']);

async function checkState(github, { owner, repo, ref }) {
  const runs = await github.paginate(github.rest.checks.listForRef, {
    owner, repo, ref, per_page: 100,
  });

  const pending = runs.filter((r) => r.status !== 'completed');
  const failed = runs.filter(
    (r) => r.status === 'completed' && !PASSING.has(r.conclusion),
  );

  return {
    total: runs.length,
    pending,
    failed,
    // Zero checks is not success. Releasing a commit that nothing tested is
    // exactly the state this guard exists to prevent.
    ok: runs.length > 0 && pending.length === 0 && failed.length === 0,
  };
}

async function waitForChecks(github, params, opts = {}) {
  const intervalMs = opts.intervalMs ?? 15000;
  const timeoutMs = opts.timeoutMs ?? 15 * 60 * 1000;
  const sleep = opts.sleep ?? ((ms) => new Promise((r) => { setTimeout(r, ms); }));
  const now = opts.now ?? (() => Date.now());

  const started = now();
  for (;;) {
    const state = await checkState(github, params);
    if (state.failed.length > 0) return state;
    if (state.pending.length === 0) return state;
    if (now() - started >= timeoutMs) return { ...state, timedOut: true };
    await sleep(intervalMs);
  }
}

module.exports = { checkState, waitForChecks };
```

- [ ] **Step 5: Run the tests to verify they pass**

Run:
```bash
cd /home/oetiker/checkouts/repo-infra && node --test .github/workflows/lib/*.test.js
```
Expected: PASS — 38 tests total, 0 failures

- [ ] **Step 6: Add a changelog entry**

Under `### New`:

```markdown
- `checks.js`: reads every check run on a commit rather than polling one named
  workflow, so the release guard keeps working when a repository names its CI
  something else. Zero checks counts as a failure, not a pass.
```

- [ ] **Step 7: Commit, push, merge**

```bash
git add .github/workflows/lib/checks.js .github/workflows/lib/checks.test.js CHANGES.md
git commit -m "Add checks.js: read and wait on check runs

Uses checks.listForRef, so it sees every check on the commit instead of
one hardcoded workflow file. Zero checks is a failure: releasing a commit
nothing tested is what the guard exists to prevent.

The wait takes injectable sleep and now, so the timeout path has a test.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push -u origin lib/checks
gh pr create --fill --base main
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

---

### Task 7: `commit.js` — commits through the Git Data API

**Files:**
- Create: `.github/workflows/lib/commit.js`
- Test: `.github/workflows/lib/commit.test.js`

**Interfaces:**
- Consumes: nothing
- Produces: `commitFiles(github, {owner, repo, branch, baseSha, message, files}) -> Promise<string>` where `files` is `[{path, content}]` and the return value is the new commit SHA. Creates `refs/heads/<branch>` pointing at it.

- [ ] **Step 1: Create the branch**

```bash
cd /home/oetiker/checkouts/repo-infra && git checkout -b lib/commit
```

- [ ] **Step 2: Write the failing test**

Create `.github/workflows/lib/commit.test.js`:

```js
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const commit = require('./commit.js');

function fakeGithub() {
  const seen = { blobs: [], trees: [], commits: [], refs: [] };
  return {
    seen,
    rest: {
      git: {
        getCommit: async ({ commit_sha: sha }) => ({
          data: { sha, tree: { sha: `tree-of-${sha}` } },
        }),
        createBlob: async (params) => {
          seen.blobs.push(params);
          return { data: { sha: `blob-${seen.blobs.length}` } };
        },
        createTree: async (params) => {
          seen.trees.push(params);
          return { data: { sha: 'new-tree' } };
        },
        createCommit: async (params) => {
          seen.commits.push(params);
          return { data: { sha: 'new-commit' } };
        },
        createRef: async (params) => {
          seen.refs.push(params);
          return { data: { ref: params.ref } };
        },
      },
    },
  };
}

const ARGS = {
  owner: 'oposs',
  repo: 'repo-infra',
  branch: 'release/v1.2.3',
  baseSha: 'base-sha',
  message: 'Release v1.2.3',
  files: [
    { path: 'CHANGES.md', content: '# Changelog\n' },
    { path: '.claude-plugin/plugin.json', content: '{}\n' },
  ],
};

test('creates one blob per file, utf-8 encoded', async () => {
  const github = fakeGithub();
  await commit.commitFiles(github, ARGS);
  assert.equal(github.seen.blobs.length, 2);
  assert.equal(github.seen.blobs[0].content, '# Changelog\n');
  assert.equal(github.seen.blobs[0].encoding, 'utf-8');
});

test('the tree is based on the base commit tree, not the commit sha', async () => {
  // createTree's base_tree wants a tree SHA. Passing a commit SHA is the
  // mistake that silently produces a tree with no history behind it.
  const github = fakeGithub();
  await commit.commitFiles(github, ARGS);
  assert.equal(github.seen.trees[0].base_tree, 'tree-of-base-sha');
});

test('every entry is a normal file blob', async () => {
  const github = fakeGithub();
  await commit.commitFiles(github, ARGS);
  for (const entry of github.seen.trees[0].tree) {
    assert.equal(entry.mode, '100644');
    assert.equal(entry.type, 'blob');
  }
  assert.deepEqual(
    github.seen.trees[0].tree.map((e) => e.path),
    ['CHANGES.md', '.claude-plugin/plugin.json'],
  );
});

test('the commit has the base as its only parent', async () => {
  const github = fakeGithub();
  await commit.commitFiles(github, ARGS);
  assert.deepEqual(github.seen.commits[0].parents, ['base-sha']);
  assert.equal(github.seen.commits[0].tree, 'new-tree');
  assert.equal(github.seen.commits[0].message, 'Release v1.2.3');
});

test('the branch ref is created and the commit sha returned', async () => {
  const github = fakeGithub();
  const sha = await commit.commitFiles(github, ARGS);
  assert.equal(github.seen.refs[0].ref, 'refs/heads/release/v1.2.3');
  assert.equal(github.seen.refs[0].sha, 'new-commit');
  assert.equal(sha, 'new-commit');
});

test('an empty file list is refused', async () => {
  const github = fakeGithub();
  await assert.rejects(
    () => commit.commitFiles(github, { ...ARGS, files: [] }),
    /nothing to commit/,
  );
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run:
```bash
cd /home/oetiker/checkouts/repo-infra && node --test .github/workflows/lib/*.test.js
```
Expected: FAIL — `Cannot find module './commit.js'`

- [ ] **Step 4: Write the implementation**

Create `.github/workflows/lib/commit.js`:

```js
'use strict';

// Commits go through the Git Data API rather than `git commit && git push`.
// Two reasons: no `git config user.email` dance repeated in every repository,
// and the commit lands atomically instead of as a sequence that can half-fail.
async function commitFiles(github, {
  owner, repo, branch, baseSha, message, files,
}) {
  if (!files || files.length === 0) {
    throw new Error('nothing to commit - the file list is empty');
  }

  // createTree's base_tree takes a *tree* SHA. Resolve the base commit to its
  // tree rather than passing the commit SHA and hoping it is dereferenced.
  const { data: base } = await github.rest.git.getCommit({
    owner, repo, commit_sha: baseSha,
  });

  const tree = [];
  for (const file of files) {
    const { data: blob } = await github.rest.git.createBlob({
      owner, repo, content: file.content, encoding: 'utf-8',
    });
    tree.push({
      path: file.path, mode: '100644', type: 'blob', sha: blob.sha,
    });
  }

  const { data: newTree } = await github.rest.git.createTree({
    owner, repo, base_tree: base.tree.sha, tree,
  });

  const { data: newCommit } = await github.rest.git.createCommit({
    owner, repo, message, tree: newTree.sha, parents: [baseSha],
  });

  await github.rest.git.createRef({
    owner, repo, ref: `refs/heads/${branch}`, sha: newCommit.sha,
  });

  return newCommit.sha;
}

module.exports = { commitFiles };
```

- [ ] **Step 5: Run the tests to verify they pass**

Run:
```bash
cd /home/oetiker/checkouts/repo-infra && node --test .github/workflows/lib/*.test.js
```
Expected: PASS — 44 tests total, 0 failures

- [ ] **Step 6: Add a changelog entry**

Under `### New`:

```markdown
- `commit.js`: creates the release commit and branch through the Git Data API, so
  no workflow needs a git identity or push access to a branch.
```

- [ ] **Step 7: Commit, push, merge**

```bash
git add .github/workflows/lib/commit.js .github/workflows/lib/commit.test.js CHANGES.md
git commit -m "Add commit.js: commits through the Git Data API

blob -> tree -> commit -> ref. base_tree is resolved from the base commit
rather than passed the commit sha, which is the mistake that produces a
tree with nothing behind it.

No git config, no push, and the commit lands atomically.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push -u origin lib/commit
gh pr create --fill --base main
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

---

### Task 8: `changelog.yml` — the changelog check

**Files:**
- Create: `.github/workflows/changelog.yml`

**Interfaces:**
- Consumes: `changes.js` `unreleasedBlock` (Task 4)
- Produces: a check run named `changelog-updated` on every pull request — the second context the ruleset requires (spec D2)

- [ ] **Step 1: Create the branch**

```bash
cd /home/oetiker/checkouts/repo-infra && git checkout -b workflow/changelog
```

- [ ] **Step 2: Write the workflow**

Create `.github/workflows/changelog.yml`:

```yaml
name: Changelog
# repo-infra: changelog v1
#
# Required, not advisory (spec D2). Being required is only safe because the
# escape hatch below is a JOB-level `if:` — a job skipped by a condition
# reports Success, while a WORKFLOW skipped by a paths/branches filter stays
# Pending forever and blocks the merge. Never add paths: or paths-ignore: to
# this workflow (spec D13).
#
# The release PR is not blocked by being GITHUB_TOKEN-authored: its runs are
# created in an approval-required state and start when a maintainer clicks
# "Approve workflows to run". This job then skips itself on release/* anyway.

on:
  pull_request:
    branches: [main]
    types: [opened, synchronize, reopened, labeled, unlabeled]

permissions:
  contents: read
  pull-requests: read

jobs:
  # No `name:` — the check context is the job id, `changelog-updated`, which is
  # what the ruleset requires. Renaming this job silently un-requires the check.
  changelog-updated:
    # release/* is exempt because the release workflow writes CHANGES.md itself.
    # The no-changelog label is the deliberate escape hatch for typo and CI-only
    # changes — without it every weekly dependabot PR is blocked, since this
    # check is required. The label must exist in the repository (Task 3): a
    # label that does not exist is silently ignored by dependabot.
    if: >-
      !startsWith(github.head_ref, 'release/') &&
      !contains(github.event.pull_request.labels.*.name, 'no-changelog')
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v7

      - uses: actions/github-script@v9
        with:
          script: |
            const changes = require(
              `${process.env.GITHUB_WORKSPACE}/.github/workflows/lib/changes.js`
            );

            // Both sides come from the API rather than from the checkout. On a
            // pull_request event the checkout is the merge commit, and comparing
            // against a base that is not in a shallow clone needs fetch-depth: 0.
            // Two getContent calls avoid both problems and make it unambiguous
            // which two refs are being compared.
            const read = async (ref) => {
              const { data } = await github.rest.repos.getContent({
                owner: context.repo.owner,
                repo: context.repo.repo,
                path: 'CHANGES.md',
                ref,
              });
              return Buffer.from(data.content, 'base64').toString('utf8');
            };

            const pr = context.payload.pull_request;
            const base = changes.unreleasedBlock(await read(pr.base.sha));
            const head = changes.unreleasedBlock(await read(pr.head.sha));

            if (base === head) {
              core.setFailed(
                "This pull request adds nothing under '## [Unreleased]' in "
                + 'CHANGES.md. Add an entry describing the change, or label the '
                + "pull request 'no-changelog' if it genuinely needs none."
              );
              return;
            }

            core.notice('CHANGES.md [Unreleased] was updated.');
```

- [ ] **Step 3: Add a changelog entry**

Under `### New`:

```markdown
- A changelog gate on every pull request. It compares the `[Unreleased]` block at
  base and head, so editing an old released section does not satisfy it. It is a
  required check, so `release/*` branches and the `no-changelog` label are the
  deliberate escape hatches — both job-level, so an exempt pull request skips the
  job and the required check goes green on its own.
```

- [ ] **Step 4: Commit, push, and open the pull request**

```bash
git add .github/workflows/changelog.yml CHANGES.md
git commit -m "Add the changelog gate

Compares the [Unreleased] block at base and head, so touching an old
released section does not satisfy it.

Required, not advisory. The escape hatch is a job-level if:, so an exempt
pull request skips the job and reports Success; a paths filter here would
leave every PR pending forever instead.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push -u origin workflow/changelog
gh pr create --fill --base main
```

- [ ] **Step 5: Verify the gate passes on this pull request**

Run:
```bash
gh pr checks --watch
```
Expected: `Unreleased entry` — **pass** (this PR does add an `### New` entry)

- [ ] **Step 6: Prove the gate fails when it should**

Open a throwaway pull request that changes nothing in `CHANGES.md`:

```bash
git checkout main && git pull
git checkout -b probe/no-changelog
printf '\n' >> README.md
git commit -am "probe: no changelog entry

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push -u origin probe/no-changelog
gh pr create --fill --base main
gh pr checks --watch
```
Expected: `Unreleased entry` — **fail**, with the message about adding an entry

Then confirm the escape hatch works:
```bash
gh pr edit --add-label no-changelog
```
(Create the label first if `gh` reports it does not exist: `gh label create no-changelog --description "Change needs no changelog entry"`.)

Expected: the job is skipped on the next run.

Finally close the probe:
```bash
gh pr close --delete-branch
```

A gate that has never been seen to fail is not known to work. This step is the test.

- [ ] **Step 7: Merge the gate pull request**

```bash
gh pr checkout workflow/changelog
gh pr merge --squash --delete-branch
git checkout main && git pull
```

- [ ] **Step 8: Now require the gate (spec D2)**

Only now, with `changelog.yml` merged to `main`, is it safe to require the second context. Requiring it earlier would have blocked every pull request in this plan, including the one that just merged.

Read the current ruleset, add the context, and write it back:

```bash
RULESET_ID=$(gh api repos/oposs/repo-infra/rulesets --jq '.[] | select(.name=="main") | .id')

gh api repos/oposs/repo-infra/rulesets/$RULESET_ID --jq '{name,target,enforcement,bypass_actors,conditions,rules}' \
  | python3 -c '
import json,sys
rs = json.load(sys.stdin)
for rule in rs["rules"]:
    if rule["type"] == "required_status_checks":
        checks = rule["parameters"]["required_status_checks"]
        if not any(c["context"] == "changelog-updated" for c in checks):
            checks.append({"context": "changelog-updated"})
json.dump(rs, sys.stdout, indent=2)
' > /scratch/oetiker/claude-tmp/ruleset-main-v2.json

gh api -X PUT repos/oposs/repo-infra/rulesets/$RULESET_ID \
  --input /scratch/oetiker/claude-tmp/ruleset-main-v2.json
```

**Read it back and assert** — the same pattern `bump.js` uses, for the same reason. A write that silently did not take leaves protection weaker than the plan claims:

```bash
gh api repos/oposs/repo-infra/rulesets/$RULESET_ID \
  --jq '[.rules[] | select(.type=="required_status_checks") | .parameters.required_status_checks[].context] | sort | join(",")'
```

Expected exactly: `changelog-updated,ci-passed`

If either context is missing, stop. Do not proceed to Task 9 with a ruleset that does not match the spec.

---

### Task 9: `release-pr.yml` — half one of the release

**Files:**
- Create: `.github/workflows/release-pr.yml`

**Interfaces:**
- Consumes: `version.js` (Task 2), `changes.js` (Task 4), `bump.js` (Task 5), `checks.js` (Task 6), `commit.js` (Task 7), `.github/repo-infra.json` (Task 1)
- Produces: a pull request from `release/vX.Y.Z` to `main` containing a rolled `CHANGES.md` and every version file set to `X.Y.Z`

- [ ] **Step 1: Create the branch**

```bash
cd /home/oetiker/checkouts/repo-infra && git checkout -b workflow/release-pr
```

- [ ] **Step 2: Write the workflow**

Create `.github/workflows/release-pr.yml`:

```yaml
name: Create release PR
# repo-infra: release-pr v1
#
# Half one of a two-step release. main is protected and GITHUB_TOKEN cannot be
# given a ruleset bypass — the bypass list takes users, teams and GitHub Apps,
# and the Actions token is none of those. So the release lands through a pull
# request like any other change. Merging it triggers release-publish.yml.

on:
  workflow_dispatch:
    inputs:
      release_type:
        description: Release type
        required: true
        default: bugfix
        type: choice
        options:
          - bugfix
          - feature
          - major

concurrency:
  group: release
  cancel-in-progress: false

permissions:
  contents: write
  pull-requests: write
  checks: read

jobs:
  release-pr:
    name: Prepare the release pull request
    runs-on: ubuntu-latest
    timeout-minutes: 25
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-node@v7
        with:
          node-version: 22

      - name: Guard — right branch, green checks
        uses: actions/github-script@v9
        with:
          script: |
            const lib = `${process.env.GITHUB_WORKSPACE}/.github/workflows/lib`;
            const checks = require(`${lib}/checks.js`);

            const def = context.payload.repository.default_branch;
            if (context.ref !== `refs/heads/${def}`) {
              core.setFailed(
                `Releases run from ${def} only. This run is on ${context.ref}.`
              );
              return;
            }

            // Required status checks cannot be used on the ruleset (they would
            // deadlock the release PR), so the tests are verified here, on the
            // commit, before any PR exists.
            const state = await checks.waitForChecks(github, {
              owner: context.repo.owner,
              repo: context.repo.repo,
              ref: context.sha,
            });

            if (state.timedOut) {
              core.setFailed(
                `Timed out waiting for checks on ${context.sha}. Still running: `
                + state.pending.map((c) => c.name).join(', ')
              );
              return;
            }
            if (state.total === 0) {
              core.setFailed(
                `No checks ran on ${context.sha}. Refusing to release a commit `
                + 'that nothing tested.'
              );
              return;
            }
            if (state.failed.length > 0) {
              core.setFailed(
                'Failing checks on this commit: '
                + state.failed.map((c) => c.name).join(', ')
              );
              return;
            }

            core.notice(`All ${state.total} checks green on ${context.sha}.`);

      - name: Compute the version and rewrite the files
        id: prepare
        uses: actions/github-script@v9
        with:
          script: |
            const fs = require('fs');
            const path = require('path');
            const ws = process.env.GITHUB_WORKSPACE;
            const lib = `${ws}/.github/workflows/lib`;
            const versionLib = require(`${lib}/version.js`);
            const changesLib = require(`${lib}/changes.js`);
            const bumpLib = require(`${lib}/bump.js`);

            const config = JSON.parse(
              fs.readFileSync(`${ws}/.github/repo-infra.json`, 'utf8')
            );

            const refs = await github.paginate(github.rest.git.listMatchingRefs, {
              owner: context.repo.owner,
              repo: context.repo.repo,
              ref: 'tags/v',
              per_page: 100,
            });
            const tags = refs.map((r) => r.ref.replace('refs/tags/', ''));
            const latest = versionLib.latest(tags);
            const version = versionLib.next(latest, context.payload.inputs.release_type);

            if (tags.includes(`v${version}`)) {
              core.setFailed(`v${version} is already tagged.`);
              return;
            }

            const io = {
              read: (p) => fs.readFileSync(path.join(ws, p), 'utf8'),
              write: (p, c) => fs.writeFileSync(path.join(ws, p), c, 'utf8'),
            };

            const date = new Date().toISOString().slice(0, 10);
            // roll throws when [Unreleased] is empty, which is the hard backstop
            // behind the required changelog gate.
            io.write('CHANGES.md', changesLib.roll(io.read('CHANGES.md'), version, date));
            bumpLib.bumpAll(config.version_files, version, io);

            core.setOutput('version', version);
            core.setOutput('date', date);
            core.notice(`Preparing ${latest} -> v${version} (${date}).`);

      # Ecosystems whose lockfile can only be rewritten by their own tool run
      # here, between the rewrite and the commit. repo-infra has none. A Rust
      # repository gets, verbatim:
      #
      #   - uses: dtolnay/rust-toolchain@stable
      #   - run: cargo update --workspace
      #
      # Not --offline: the resolve needs the registry. Not || true: swallowing
      # that failure is what tagged mdmost v0.1.1 with an inconsistent lockfile.

      - name: Commit and open the pull request
        uses: actions/github-script@v9
        with:
          script: |
            const fs = require('fs');
            const path = require('path');
            const ws = process.env.GITHUB_WORKSPACE;
            const commitLib = require(`${ws}/.github/workflows/lib/commit.js`);

            const config = JSON.parse(
              fs.readFileSync(`${ws}/.github/repo-infra.json`, 'utf8')
            );
            const version = '${{ steps.prepare.outputs.version }}';
            const date = '${{ steps.prepare.outputs.date }}';
            const branch = `release/v${version}`;

            // A fixed list, read off disk after every step that may have touched
            // it. This is what lets a tool step (cargo update) participate without
            // the commit step needing to know it ran.
            const paths = ['CHANGES.md', ...config.version_files.map((f) => f.path)];
            const files = paths.map((p) => ({
              path: p,
              content: fs.readFileSync(path.join(ws, p), 'utf8'),
            }));

            await commitLib.commitFiles(github, {
              owner: context.repo.owner,
              repo: context.repo.repo,
              branch,
              baseSha: context.sha,
              message: `Release v${version}`,
              files,
            });

            const body = [
              'Prepared by the **Create release PR** workflow.',
              '',
              `- rolls \`CHANGES.md\` \`[Unreleased]\` into \`## ${version} - ${date}\``,
              `- sets ${config.version_files.map((f) => `\`${f.path}\``).join(', ')} to \`${version}\``,
              '',
              'Review the changelog, then merge. Merging triggers **Release',
              `publisher**, which tags \`v${version}\` and publishes the release.`,
              '',
              'Nothing is tagged or published until this is merged; closing it',
              'cancels the release.',
            ].join('\n');

            const { data: pr } = await github.rest.pulls.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              head: branch,
              base: context.payload.repository.default_branch,
              title: `Release v${version}`,
              body,
            });

            core.notice(`Release pull request opened: ${pr.html_url}`);
            await core.summary
              .addHeading(`Release v${version} prepared`)
              .addLink('Review and merge to publish', pr.html_url)
              .write();
```

- [ ] **Step 3: Add a changelog entry**

Under `### New`:

```markdown
- **Create release PR**: computes the next version from the tags, rolls
  `CHANGES.md`, sets every declared version file and opens a `release/vX.Y.Z` pull
  request. It refuses to run when no check has reported on the commit, because a
  release of untested code is exactly what the guard exists to prevent.
```

- [ ] **Step 4: Commit, push, merge**

```bash
git add .github/workflows/release-pr.yml CHANGES.md
git commit -m "Add Create release PR: half one of the release

Computes the version from the tags, rolls CHANGES.md, bumps the declared
version files, commits through the Git Data API and opens the PR.

The guard verifies checks on the commit before any branch or PR exists,
so a release started from a red main is refused immediately instead of
after producing a branch, a commit and an open pull request. This is in
addition to the required checks on the ruleset, not a substitute for them.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push -u origin workflow/release-pr
gh pr create --fill --base main
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

---

### Task 10: `release-publish.yml` — half two of the release

**Files:**
- Create: `.github/workflows/release-publish.yml`

**Interfaces:**
- Consumes: `changes.js` (Task 4), `bump.js` `verifyFile` (Task 5), `.github/repo-infra.json` (Task 1)
- Produces: job outputs `version`, `tag`, `release_id` — the seam that spec 2's publish add-ons attach to

- [ ] **Step 1: Create the branch**

```bash
cd /home/oetiker/checkouts/repo-infra && git checkout -b workflow/release-publish
```

- [ ] **Step 2: Write the workflow**

Create `.github/workflows/release-publish.yml`:

```yaml
name: Publish release (automatic)
# repo-infra: release-publish v1
#
# Half two. Merging the release pull request lands the rolled CHANGES.md on main,
# and that merge triggers this.
#
# There is deliberately no workflow_dispatch. Publishing should be a consequence
# of merging a release pull request, never something started from a dropdown.
# With main protected against direct pushes, that leaves exactly one route to a
# release. Recovery does not need a manual trigger either: a failed run is re-run
# from the Actions UI, and because the version is read from the repository rather
# than from run inputs, the re-run does what the original attempt would have.

on:
  push:
    branches: [main]
    paths:
      - CHANGES.md

concurrency:
  group: release-publish
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  publish:
    name: Tag and publish
    runs-on: ubuntu-latest
    timeout-minutes: 10
    outputs:
      version: ${{ steps.publish.outputs.version }}
      tag: ${{ steps.publish.outputs.tag }}
      release_id: ${{ steps.publish.outputs.release_id }}
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-node@v7
        with:
          node-version: 22

      - name: Tag and create the draft release
        id: publish
        uses: actions/github-script@v9
        with:
          script: |
            const fs = require('fs');
            const path = require('path');
            const ws = process.env.GITHUB_WORKSPACE;
            const lib = `${ws}/.github/workflows/lib`;
            const changesLib = require(`${lib}/changes.js`);
            const bumpLib = require(`${lib}/bump.js`);

            const owner = context.repo.owner;
            const repo = context.repo.repo;

            const io = {
              read: (p) => fs.readFileSync(path.join(ws, p), 'utf8'),
              write: () => { throw new Error('the publisher never writes'); },
            };

            const config = JSON.parse(io.read('.github/repo-infra.json'));

            // CHANGES.md is the source of truth. It is the only file every
            // repository has, and it changes on exactly one occasion.
            const release = changesLib.latestRelease(io.read('CHANGES.md'));
            if (!release) {
              core.notice('CHANGES.md has no released version yet - nothing to do.');
              return;
            }
            const version = release.version;
            const tag = `v${version}`;

            // Every version file is a derived copy. If one disagrees, the release
            // pull request half-applied, and tagging now would repeat the failure
            // that shipped an inconsistent v0.1.1 elsewhere.
            const stale = config.version_files.filter(
              (spec) => !bumpLib.verifyFile(spec, version, io)
            );
            if (stale.length > 0) {
              core.setFailed(
                `CHANGES.md says ${version} but these disagree: `
                + stale.map((s) => s.path).join(', ')
              );
              return;
            }

            // Idempotent: an ordinary pull request that edits [Unreleased] also
            // triggers this workflow, finds the tag already present, and stops.
            try {
              await github.rest.git.getRef({ owner, repo, ref: `tags/${tag}` });
              core.notice(`${tag} is already tagged - nothing to do.`);
              return;
            } catch (error) {
              if (error.status !== 404) throw error;
            }

            // Annotated, not a bare createRef. A bare ref makes a lightweight tag,
            // and `git describe` prefers annotated ones; the existing repositories
            // have annotated tags and a silent switch would change local tooling
            // behaviour for no reason.
            const makeTag = async (name, message) => {
              const { data: object } = await github.rest.git.createTag({
                owner, repo, tag: name, message, object: context.sha, type: 'commit',
              });
              return object.sha;
            };

            await github.rest.git.createRef({
              owner, repo, ref: `refs/tags/${tag}`,
              sha: await makeTag(tag, `Release ${tag}`),
            });
            core.notice(`Tagged ${tag}.`);

            if (config.moving_major_tag) {
              const major = `v${version.split('.')[0]}`;
              const sha = await makeTag(major, `Update ${major} to ${tag}`);
              try {
                await github.rest.git.updateRef({
                  owner, repo, ref: `tags/${major}`, sha, force: true,
                });
              } catch (error) {
                if (error.status !== 422) throw error;
                await github.rest.git.createRef({
                  owner, repo, ref: `refs/tags/${major}`, sha,
                });
              }
              core.notice(`Moved ${major} to ${tag}.`);
            }

            // Draft, so publish add-ons (spec 2) can attach artifacts before
            // anyone sees the release. The finalize job below publishes it.
            const { data: created } = await github.rest.repos.createRelease({
              owner, repo,
              tag_name: tag,
              name: tag,
              body: changesLib.notesFor(io.read('CHANGES.md'), version),
              draft: true,
              prerelease: false,
              make_latest: 'true',
            });

            core.setOutput('version', version);
            core.setOutput('tag', tag);
            core.setOutput('release_id', String(created.id));

  finalize:
    name: Publish the release
    # `apply` appends publish add-on job names to this list when it installs them.
    # Keeping the list generated is what stops the core from depending on them.
    needs: [publish]
    if: needs.publish.outputs.release_id != ''
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions:
      contents: write
    steps:
      - uses: actions/github-script@v9
        with:
          script: |
            const { data: released } = await github.rest.repos.updateRelease({
              owner: context.repo.owner,
              repo: context.repo.repo,
              release_id: Number('${{ needs.publish.outputs.release_id }}'),
              draft: false,
            });
            core.notice(`Published ${released.html_url}`);
            await core.summary
              .addHeading(`Released ${{ needs.publish.outputs.tag }}`)
              .addLink('Release', released.html_url)
              .write();
```

- [ ] **Step 3: Write `RELEASING.md`**

Create `RELEASING.md`:

```markdown
# Releasing

`main` is protected, so a release lands in two halves.

**1. Run the `Create release PR` workflow** (Actions → Create release PR →
Run workflow → bugfix / feature / major). It:

1. refuses unless every check on the current `main` commit is green,
2. computes the next version from the tags and refuses if it already exists,
3. rolls the `CHANGES.md` `[Unreleased]` section into a dated version section,
4. sets every file listed in `.github/repo-infra.json` to the same version,
5. pushes a `release/vX.Y.Z` branch and opens a pull request.

Nothing is tagged or published yet. Closing the pull request cancels the release.

**2. Review the changelog and merge.** That triggers the publish workflow, which
reads the version back out of `CHANGES.md`, checks every version file agrees,
tags, and publishes the GitHub release.

## Why a pull request

`main` is protected by a repository ruleset, and the built-in `GITHUB_TOKEN`
cannot be given a bypass — the bypass list accepts users, teams and GitHub Apps,
and the Actions token is none of those. Landing the release through a pull
request needs no stored credential and works with the protection rather than
around it. Tagging is unaffected: the ruleset targets branches, and tags live in
a separate ref namespace.

## Why the release pull request needs a click

The ruleset requires two status checks, `ci-passed` and `changelog-updated`. Nothing
merges to `main` without them, including a release.

A pull request opened by `GITHUB_TOKEN` does not start its `pull_request`
workflow runs automatically. They are created in an **approval-required** state:
the merge box shows a banner, and anyone with write access starts them with
**Approve workflows to run**. The checks are parked, not skipped — so they do
report, and the pull request does merge.

That single click is deliberate. The alternative is to open the release pull
request with a GitHub App or personal access token so the runs start unattended,
which means a credential to create, store and rotate. The click costs less.

Do not try to route around it with an `on: push` trigger on the release branch.
The same restriction covers pushes: a push made with `GITHUB_TOKEN` does not
trigger workflows either, and the release branch is created by the Actions token
through the Git Data API. There is no automatic path to a green check here.

`changelog-updated` skips itself on `release/*` branches. A skipped job reports
Success, so it satisfies the requirement without running.

**Check this still holds** by opening a release pull request and looking for the
banner. If the runs are not created at all, neither required check can ever
report, and the ruleset must drop them until another route exists.

## Why a required workflow never uses a `paths` filter

A job skipped by a job-level `if:` reports **Success** and merges fine. A whole
workflow skipped by a `paths` or `branches` filter stays **Pending** forever and
blocks the pull request. GitHub's own guidance: do not use path or branch
filtering to skip workflow runs if the workflow is required.

So `ci.yml` and `changelog.yml` carry no `paths` filter, and every
conditional lives inside a job. If someone adds `paths:` to save CI minutes,
every pull request that does not match it becomes unmergeable, with no failing
check and no log to explain why.

## Why publishing has no manual trigger

Publishing should be a consequence of merging a release pull request, not
something anyone starts from a dropdown. A failed run is re-run from the Actions
UI, and because the version comes from `CHANGES.md` rather than from run inputs,
the re-run does exactly what the original attempt would have done.
```

- [ ] **Step 4: Add a changelog entry**

Under `### New`:

```markdown
- **Publish release**: reads the released version back out of `CHANGES.md`,
  refuses to tag when any version file disagrees, creates an annotated tag and
  publishes the release. It exposes `version`, `tag` and `release_id` as job
  outputs — the seam that per-language publish add-ons will attach to.
- `RELEASING.md` documenting the two-step release and, more importantly, why each
  of its unusual parts is the way it is.
```

- [ ] **Step 5: Commit, push, merge**

```bash
git add .github/workflows/release-publish.yml RELEASING.md CHANGES.md
git commit -m "Add release-publish: half two of the release

Reads the version back out of CHANGES.md, so this works for repositories
that have no version file at all. Cross-checks every declared version
file and refuses to tag when one disagrees.

Annotated tags via createTag + createRef. The release is created as a
draft and published by a finalize job, so spec 2's add-ons have somewhere
to attach artifacts before anyone sees it.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push -u origin workflow/release-publish
gh pr create --fill --base main
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

---

### Task 11: Release `v0.1.0` — the proof

Nothing before this proves the system works end to end. This task is the test.

**Files:**
- Modify: `CHANGES.md`, `.claude-plugin/plugin.json` (both written by the workflow, not by hand)

**Interfaces:**
- Consumes: everything
- Produces: tag `v0.1.0`, a published GitHub release, and `plugin.json` at `0.1.0`

- [ ] **Step 1: Confirm `main` is green and `[Unreleased]` is not empty**

Run:
```bash
cd /home/oetiker/checkouts/repo-infra && git checkout main && git pull
gh run list --repo oposs/repo-infra --branch main --limit 3
node -e '
  const c = require("./.github/workflows/lib/changes.js");
  const t = require("fs").readFileSync("CHANGES.md", "utf8");
  console.log("unreleased empty:", c.isEmpty(c.unreleasedBlock(t)));
'
```
Expected: latest runs `success`; `unreleased empty: false`

- [ ] **Step 2: Dispatch the release**

```bash
gh workflow run release-pr.yml --repo oposs/repo-infra -f release_type=feature
```

`feature` gives `0.1.0` from the zero version, which is the right first release for something not yet complete.

- [ ] **Step 3: Watch the run and confirm the guard passed**

Run:
```bash
gh run watch --repo oposs/repo-infra \
  "$(gh run list --repo oposs/repo-infra --workflow release-pr.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
```
Expected: conclusion `success`, with a notice reading `All N checks green on <sha>`

If it fails with "GitHub Actions is not permitted to create or approve pull requests", the Task 3 Step 6 setting did not stick — an organisation policy is overriding it. Fix that before retrying.

- [ ] **Step 4: Inspect the release pull request before merging**

Run:
```bash
gh pr list --repo oposs/repo-infra --head release/v0.1.0
gh pr diff --repo oposs/repo-infra "$(gh pr list --repo oposs/repo-infra --head release/v0.1.0 --json number --jq '.[0].number')"
```

Expected in the diff:
- `CHANGES.md` has a new `## 0.1.0 - <today>` section holding everything that was under `[Unreleased]`
- `CHANGES.md` `[Unreleased]` is back to an empty `### New` / `### Changed` / `### Fixed` skeleton
- `.claude-plugin/plugin.json` `version` is `0.1.0`
- **no other file changed**

Also confirm the changelog gate **skipped** on it — the `release/` exemption should have skipped the job, which reports Success and satisfies the required check without running.

- [ ] **Step 5: Approve the parked workflow runs**

This pull request was opened by `GITHUB_TOKEN`, so its `pull_request` runs were created in an **approval-required** state and have not started. The merge box shows a banner. Click **Approve workflows to run**.

```bash
gh pr view --repo oposs/repo-infra --web \
  "$(gh pr list --repo oposs/repo-infra --head release/v0.1.0 --json number --jq '.[0].number')"
```

This is expected behaviour and the deliberate cost of not introducing a credential (spec D2). It is **not** a bug and not a permissions failure.

Then wait for both required contexts to report:

```bash
gh pr checks --repo oposs/repo-infra --watch \
  "$(gh pr list --repo oposs/repo-infra --head release/v0.1.0 --json number --jq '.[0].number')"
```

Expected: `ci-passed` **pass** (it ran), `changelog-updated` **skipping** or **pass** (exempt on `release/*`). The PR must report mergeable before the next step.

If the banner never appears and the checks stay pending with no runs at all, stop — that means GitHub no longer creates runs for `GITHUB_TOKEN`-authored pull requests, which invalidates spec D2 and makes both required contexts unreachable. Record it against the spec's risk register before working around it.

- [ ] **Step 6: Merge the release pull request**

```bash
gh pr merge --repo oposs/repo-infra --squash --delete-branch \
  "$(gh pr list --repo oposs/repo-infra --head release/v0.1.0 --json number --jq '.[0].number')"
```

Note: a squash merge produces a single commit on `main` that changes `CHANGES.md`, which is what the publisher's `paths:` filter needs.

- [ ] **Step 7: Watch the publisher**

Run:
```bash
gh run watch --repo oposs/repo-infra \
  "$(gh run list --repo oposs/repo-infra --workflow release-publish.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
```
Expected: both `publish` and `finalize` jobs `success`

- [ ] **Step 8: Verify the release**

Run:
```bash
gh release view v0.1.0 --repo oposs/repo-infra
git fetch --tags && git cat-file -t v0.1.0
```
Expected:
- the release exists, is **not** a draft, and its body is the `## 0.1.0` section from `CHANGES.md`
- `git cat-file -t v0.1.0` prints `tag`, not `commit` — proving the tag is annotated

- [ ] **Step 9: Verify idempotence**

Push a trivial `[Unreleased]` edit through a pull request and confirm the publisher runs and does nothing:

```bash
git checkout main && git pull
git checkout -b probe/idempotence
# add a line under ### Changed in CHANGES.md describing this probe
git commit -am "probe: confirm the publisher no-ops on an Unreleased edit

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push -u origin probe/idempotence
gh pr create --fill --base main
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
gh run watch --repo oposs/repo-infra \
  "$(gh run list --repo oposs/repo-infra --workflow release-publish.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
```
Expected: the run succeeds with the notice `v0.1.0 is already tagged - nothing to do.` and **no** second release

This is the property that makes the `paths: [CHANGES.md]` trigger safe. If a second release appears, the idempotence check is broken and must be fixed before any other repository adopts this.

- [ ] **Step 10: Record the outcome**

Add to `CHANGES.md` under `### Changed` on a new pull request, then merge it:

```markdown
- The release system is proven end to end: `v0.1.0` was cut by dispatching
  **Create release PR**, merging the pull request it opened, and letting the
  publish workflow tag and publish, with no manual step in between.
```

---

## Self-review

**Spec coverage.** Against spec 1: D1 Task 3 Step 8; D2 Task 3 Steps 1 and 8 (the `ci-passed` job and the `ci-passed` context), Task 8 Step 8 (the `changelog-updated` context), Task 11 Step 5 (the approval click) and `RELEASING.md`; D3 Task 3 Steps 6–7; D5 Tasks 4 and 10; D6 Tasks 1 and 4; D7 Task 9 (the tool-step comment block); D8 Tasks 2, 4–7 and the CI job in Task 3; D9 Tasks 7 and 10; D11 markers on every workflow file; D12 not exercised here because `repo-infra`'s own config is written by hand — it lands in the plugin plan with `detection.json`; D13 Tasks 3 and 8 (neither required workflow carries a `paths` filter; both escape hatches are job-level).

**Deliberately deferred to the plugin plan** (spec 1, second half): `detection.json`, `manifest.json`, `SKILL.md`, `references/`, the `check` and `apply` commands, the Python checker, and packaging `ruleset-main.json` as a shipped asset rather than a scratch file. D4 (per-repo rather than org-level protection) is a policy this plan follows and the plugin plan enforces.

**Placeholders.** None. Every code step carries complete code; every verification step names the exact command and expected output.

**Type consistency.** `io` is `{read, write}` everywhere (Tasks 5, 9, 10). `spec` is `{path, pattern, replacement, verify}` in `.github/repo-infra.json` (Task 1), `bump.js` (Task 5) and both workflows. `checkState` returns `{total, pending, failed, ok}` and `waitForChecks` adds `timedOut` (Task 6), both consumed in Task 9. `commitFiles` takes `{owner, repo, branch, baseSha, message, files}` and returns a SHA (Task 7), called that way in Task 9. `next()` returns a bare version and every heading, tag and API call adds the `v` itself.

**One risk this plan cannot remove.** Task 3 Step 7 reads back `can_approve_pull_request_reviews`, but an organisation policy on `oposs` could still override it in a way the repository-level read does not reveal. That surfaces at Task 11 Step 3 as a permissions failure. Reading `orgs/oposs/actions/permissions/workflow` first would catch it earlier and needs `gh auth refresh -h github.com -s admin:org`.
