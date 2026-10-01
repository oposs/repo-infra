# D28: One Release Flow, Tested Before the Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every repository releases through one `Create release PR` workflow that builds and tests the release on the release branch before the pull request exists, so the pull request merges without an approval click, and `main` can never move under a release unnoticed.

**Architecture:** As in D24 to D27, every decision that can be wrong at run time is a pure function in `skills/repo-infra/assets/workflows/lib/*.js`, tested table-driven with `node --test`; the YAML only fetches state, calls the function and acts on its answer. `ci.yml` becomes a reusable workflow too (`workflow_call` with input `ref`), and `release-build.yml` becomes the third assembled file (frame, `release_build` add-ons, `release_build_local` seam). The Python side loses the D26 variant machinery, learns the `release_build` list, a text-based seam contract check (`seam.py`, standard library only) and a migration module (`migrate.py`) that `check` reports and `apply` performs.

**Tech Stack:** Python 3.11+ standard library (pytest and PyYAML for tests only), Node 22 (`node:test`), GitHub Actions (`actions/github-script@v9`), GitHub rulesets API.

**Spec:** `docs/superpowers/specs/2026-10-01-one-release-flow-design.md` (D28). It extends `docs/superpowers/specs/2026-09-29-mdmost-conversion-design.md` (D24 to D27). Read both before any task; section names below refer to D28's spec.

## Global Constraints

- Work only in the worktree `/scratch/oetiker/claude-worktrees/repo-infra-spec-d24-d27`, branch `spec/d24-d27`. Never touch `~/checkouts/repo-infra`. Never push `main` of any repository.
- **repo-infra is PUBLIC.** No internal host name, IP address, ssh alias or bot login other than `github-actions[bot]` in any file, commit message or pull request text. `https://gitea.oetiker.ch` and `oposs` are public.
- **Every GitHub write is owner-gated**: push, pull request creation, merge, workflow dispatch, approving runs, ruleset changes, secrets, `apply` administration items. Ask the owner before each one. Reads (`gh api` GET, `git ls-remote`, `gh run view`) are fine.
- D24 to D27 never shipped. `release-pr-build` and the boolean `release_build` are **removed**, not deprecated. No alias for the marker `release-pr-build`.
- Version changes, each made once, in the task named:
  - `workflow-lib` v5 -> v6 (Task 1)
  - CI frame `ci` v1 -> v2 (marker line in `assets/ci/ci-frame.yml`); every CI block +1: `ci-lib` 1->2, `ci-claude-plugin` 1->2, `ci-python` 2->3, `ci-rust` 2->3, `ci-rust-musl` 1->2, `ci-man` 2->3, `ci-go` 1->2, `ci-node-pnpm` 1->2, `ci-node-bun` 1->2, `ci-perl-autotools` 2->3, `ci-perl-mkpl` 1->2, `ci-repo-infra-selftest` 3->4, `ci-checkmk-plugin` 1->2, `ci-github-action` 1->2, `ci-local` 1->2 (Task 2)
  - `changelog` v3 -> v4 (Task 3)
  - `release-pr` v4 -> v5; asset `release-pr-build` deleted (Task 4)
  - new frame `release-build` v1 (marker in `assets/release-build/release-build-frame.yml`); new manifest section `release_build_blocks` with `release-source-tarball` v1 (`"assets": ["*.tar.gz"]`) and `release-build-local` v1 (`"seam": "release_build_local"`, `"assets": []`); publish block `publish-source-tarball` deleted; manifest `actions` gains `"actions/upload-artifact": "v7"` (Task 5)
  - frame `release-publish` v4 -> v5, `publish-crates-io` v2 -> v3; `publish-gitea-packages` stays v1 (Task 6)
  - `gh` `ruleset-main` v1 -> v2 (Task 7)
- Fixed names and texts from the spec, verbatim:
  - workflow inputs `ref` (string, `required: false`, `default: ''` on `ci.yml`) and `version` + `ref` (both required, on `release-build.yml` and `release-build-local.yml`)
  - config keys `release_build` (a list of build add-on ids), `release_build_local` (boolean), `release_assets`, `release_files`
  - files `.github/workflows/release-build.yml` (assembled), `.github/workflows/release-build-local.yml` (project-owned)
  - artifacts `release-asset-*` and `release-files`, reserved for the build; `release-source-tarball` uploads `release-asset-source`
  - release asset `release-build.json` = `{version, base, head, assets}`
  - commit status `release-built`; check runs `ci-passed` and `changelog-updated`; job `release-pr-current`
  - the base-commit checkout directory is `repo-infra-base` (both `ci-passed` and `changelog-updated`)
  - stale text: `main moved after vX.Y.Z was built; close this pull request and dispatch Create release PR again`
  - tree text: `main at <sha> does not match the release built from <head>; merge a pull request that moves the vX.Y.Z entries in CHANGES.md back under [Unreleased], then dispatch Create release PR again`
  - Update-branch text (unchanged from D26): `the release branch changed after it was built (the Update branch button does this); close this pull request and dispatch Create release PR again`
  - untagged prefix (unchanged): `vX.Y.Z is in CHANGES.md on main but has no tag`
  - the bot login the gates trust is exactly `github-actions[bot]`
- Permissions, verbatim from the spec: `release-pr.yml` `prepare` gets `actions: write`, `finish` gets `checks: write`, the workflow level keeps `checks: read` and `actions: read`; `test` grants `contents: read`, `pull-requests: read`, `statuses: read`, `checks: write`; `release-publish.yml` gets `actions: write` (on `finalize`, the job that deletes parked runs); `ci.yml` stays `contents: read` at workflow level, `ci-passed` and `release-pr-current` raise their own.
- `build` and `test` call their workflows with `secrets: inherit`, and so do the nested `ci-local`, `action-test` and `release-build-local` jobs.
- Assets are literal files: no substitution token (D15, D20). No `paths:` filter on a CI block or on `changelog.yml` (D13). Every non-`uses:` job in an asset sets `timeout-minutes`. Every `uses: owner/action@vN` matches `manifest.json` `actions` (`tests/test_blocks.py`).
- The Python scripts under `skills/repo-infra/scripts/` use the standard library only. PyYAML is a test dependency, never a runtime one.
- No em dash (U+2014) in anything this plan creates or edits (`tests/test_no_em_dash.py`). Write `--` or rephrase.
- repo-infra's own `.github/` is assembler output (`tests/test_self_render.py`). After changing any asset, re-render from the worktree root with exactly this command, then run the suite:

  ```bash
  python3 -c "import json,pathlib,sys; sys.path.insert(0,'skills/repo-infra/scripts'); from repo_infra.assemble import render_all; from repo_infra.detect import Detection; A=pathlib.Path('skills/repo-infra/assets'); m=json.loads((A/'manifest.json').read_text()); r=Detection.load(A/'detection.json').detect('.'); [pathlib.Path(p).write_text(t, encoding='utf-8') for p,t in render_all(A,r,m).items()]"
  ```

  From Task 5 on this also writes `.github/workflows/release-build.yml` for repo-infra itself; `git add` it.
- Gates (from the worktree root; the pytest temp dir must not be `/tmp`; at most 4 cores, the suite is single-process):
  - JS: `node --test skills/repo-infra/assets/workflows/lib/*.test.js`
  - Python: `mkdir -p /scratch/oetiker/claude-tmp/pytest && TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q -m "not container" tests`
  - Full: `mkdir -p /scratch/oetiker/claude-tmp/pytest && TMPDIR=/scratch/oetiker/claude-tmp/pytest make check`
  - Baseline before Task 1: JS `ℹ pass 138`, Python `657 passed, 5 deselected`. Every task reports its new counts and the delta it accounts for.
- Commit messages end with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Load the `repo-infra:writing-style` skill before any prose (docs, CHANGES, commit messages).
- `CHANGES.md`: bullets under `## [Unreleased]`, for users and administrators, at most three sentences, no release header.

## Review Focus

1. **`main` moves at any point between dispatch and merge.** Whatever the moment (while `build` and `test` run, while the pull request is open, or with the up-to-date rule switched off), nothing stale may be tagged or published, and the pull request must say why it is red. Pinned by `finishVerdict` and `staleReleasePrs` (Task 1), the `release-pr-current` harness (Task 2), and the publish tree-comparison harness (Task 6).
2. **Someone approves the parked runs, or presses Update branch.** `ci-passed` and `changelog-updated` must reach the same verdict as `finish` and `release-pr-current` for the same status and behind count, or an approved green run replaces a red check. Pinned by the agreement test in Task 3 that runs both gate harnesses over one table.
3. **A project-owned seam that ignores `ref`.** A `ci-local.yml` that declares `ref` but checks out its default commit makes `test` run on `main` and report the release as tested. Pinned by the seam contract tests in Task 8 (declared and used in every checkout, flow-style `on:`, quoted values, a checkout in a second job).
4. **A fork's or a person's `release/x` branch.** It must get the ordinary rules everywhere (`ci-passed` fails on failed needs, the changelog gate reads `[Unreleased]`), never release mode. Pinned by the harness cases in Task 2 and Task 3.
5. **A release pull request merged by squash or rebase, and a publish run on a later commit.** The tree comparison must pass a squash merge whose tree equals the built head, must use the release pull request's merge commit (not `context.sha`), and must never run in `resume` or `done`. Pinned by the harness cases in Task 6.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `skills/repo-infra/assets/workflows/lib/release.js` | modify | release-mode verdict, finish verdict, stale release PRs, untagged message, merge commit, tree verdict, parked runs |
| `skills/repo-infra/assets/workflows/lib/checks.js` | modify | `guardVerdict`; `waitForChecks` removed |
| `skills/repo-infra/assets/workflows/lib/*.js` | modify | marker v5 -> v6 |
| `skills/repo-infra/assets/ci/ci-frame.yml` | modify | `workflow_call` with `ref`; marker `ci v2` |
| `skills/repo-infra/assets/ci/ci-*.yml` | modify | every checkout `ref: ${{ inputs.ref }}` |
| `skills/repo-infra/assets/ci/ci-local.yml`, `ci-github-action.yml` | modify | pass `ref`, `secrets: inherit` |
| `skills/repo-infra/assets/ci/ci-aggregator.yml` | modify | `ci-passed` release mode; new `release-pr-current` |
| `skills/repo-infra/assets/workflows/changelog.yml` | modify | release mode from the base commit's library |
| `skills/repo-infra/assets/workflows/release-pr.yml` | rewrite | one flow: `prepare`, `build`, `test`, `finish` |
| `skills/repo-infra/assets/workflows/release-pr-build.yml` | delete | |
| `skills/repo-infra/assets/release-build/release-build-frame.yml` | create | frame of the assembled `release-build.yml` |
| `skills/repo-infra/assets/release-build/release-source-tarball.yml` | create | `make dist` tarball as `release-asset-source` |
| `skills/repo-infra/assets/release-build/release-build-local.yml` | create | the `release_build_local` seam job |
| `skills/repo-infra/assets/publish/publish-source-tarball.yml` | delete | |
| `skills/repo-infra/assets/publish/publish-frame.yml` | modify | one path, tree comparison |
| `skills/repo-infra/assets/publish/publish-finalize.yml` | modify | `release_assets` always; delete parked runs |
| `skills/repo-infra/assets/publish/publish-crates-io.yml` | modify | no Cargo.lock reconcile step |
| `skills/repo-infra/assets/gh/ruleset-main.json` | modify | strict policy |
| `skills/repo-infra/assets/manifest.json`, `detection.json` | modify | versions, sections, candidate |
| `skills/repo-infra/scripts/repo_infra/assemble.py` | modify | variant code out; `assemble_release_build` in |
| `skills/repo-infra/scripts/repo_infra/state.py` | modify | variant code out; strict; contracts |
| `skills/repo-infra/scripts/repo_infra/apply.py` | modify | variant code out; strict read-back |
| `skills/repo-infra/scripts/repo_infra/remote.py` | modify | `Facts.strict`, `release_prs`, `tags` |
| `skills/repo-infra/scripts/repo_infra/seam.py` | create | seam contract from text |
| `skills/repo-infra/scripts/repo_infra/migrate.py` | create | D28 migration: report and perform |
| `skills/repo-infra/scripts/repo_infra/cli.py` | modify | wiring |
| `skills/repo-infra/scripts/repo_infra/detect.py` | modify | `open_candidates` knows `release_build` |
| `tests/test_release_mode.py`, `tests/test_release_pr.py`, `tests/test_release_build_assembly.py`, `tests/test_seam.py`, `tests/test_migrate.py` | create | |
| `tests/test_release_build.py` | rename to `tests/test_release_contracts.py`, trimmed | |
| `tests/test_variant_switch.py` | delete | |
| `RELEASING.md`, `CHANGES.md`, `commands/apply.md`, `skills/repo-infra/references/{release-flow,conventions}.md` | modify | docs |

Task order differs from the brief in one place: the single `release-pr.yml` (Task 4) comes before the `release-build.yml` assembly (Task 5). `render_all`'s `release_build` argument changes meaning from a boolean variant selector to a list of add-ons; removing the variant first means no commit ever has both meanings at once.

---
## Phase 1: the library

### Task 1: `release.js` and `checks.js` learn D28's decisions

**Files:**
- Modify: `skills/repo-infra/assets/workflows/lib/release.js:98-109` (append before `module.exports`, extend the export list)
- Modify: `skills/repo-infra/assets/workflows/lib/release.test.js` (append)
- Modify: `skills/repo-infra/assets/workflows/lib/checks.js:153-167,215` (`waitForChecks` out, `guardVerdict` in)
- Modify: `skills/repo-infra/assets/workflows/lib/checks.test.js:59-93,114-127` (waitForChecks tests out, guardVerdict tests in)
- Modify: every file in `skills/repo-infra/assets/workflows/lib/` (marker v5 -> v6), `skills/repo-infra/assets/manifest.json:26` (`workflow-lib` `"version": 6`)
- Modify (re-render): `.github/workflows/lib/*`

**Interfaces:**
- Produces (release.js, all pure):
  - `CHANGED_AFTER_BUILD: string` (the Update-branch text)
  - `releaseTag(ref: string) -> string` (`'release/v1.2.0'` -> `'v1.2.0'`)
  - `staleMessage(tag: string) -> string`
  - `releaseModeVerdict({ statuses, behindBy, tag }) -> { ok: boolean, message: string }`
  - `finishVerdict({ behindBy, tag }) -> { conclusion: 'success'|'failure', title: string, summary: string }`
  - `staleReleasePrs(entries: {pr, behindBy}[], fullName) -> { number, sha, title, summary }[]`
  - `untaggedMessage(version: string) -> string`
  - `releasePrMergeCommit(prs, { fullName, tag }) -> string|null`
  - `treeVerdict({ tag, head, mergeSha, mergeTree, headTree }) -> string|null` (null = trees match)
  - `parkedRuns(runs, { fullName, branch = null, keep = [] }) -> run[]`
- Produces (checks.js): `guardVerdict(state) -> string|null`; `waitForChecks` no longer exists.

- [ ] **Step 1: Bump the library to v6**

```bash
cd /scratch/oetiker/claude-worktrees/repo-infra-spec-d24-d27
sed -i '1s|// repo-infra: workflow-lib v5|// repo-infra: workflow-lib v6|' skills/repo-infra/assets/workflows/lib/*.js
sed -i 's|"version": 5,\(\s*\)$|"version": 6,\1|' skills/repo-infra/assets/manifest.json
grep -c 'workflow-lib v6' skills/repo-infra/assets/workflows/lib/*.js | grep -v ':1$' ; grep -n '"version": 6' skills/repo-infra/assets/manifest.json
```

Expected: the first grep prints nothing (every file carries v6 once); the second prints the `workflow-lib` line only. If `"version": 5` matched another entry, fix it back by hand: only `workflow-lib` changes here.

- [ ] **Step 2: Write the failing release.js tests** (append to `release.test.js`)

```js
// --- D28 ---------------------------------------------------------------

const BUILT = [{ context: 'release-built', state: 'success', creator: { login: r.BOT } }];
const STALE = 'main moved after v1.2.0 was built; close this pull request and dispatch '
  + 'Create release PR again';

test('releaseTag reads the tag off a release branch', () => {
  assert.equal(r.releaseTag('release/v1.2.0'), 'v1.2.0');
});

test('release mode passes a built head that main has not left behind', () => {
  const v = r.releaseModeVerdict({ statuses: BUILT, behindBy: 0, tag: 'v1.2.0' });
  assert.equal(v.ok, true);
});

test('release mode fails a head without the release-built status', () => {
  assert.deepEqual(r.releaseModeVerdict({ statuses: [], behindBy: 0, tag: 'v1.2.0' }),
    { ok: false, message: r.CHANGED_AFTER_BUILD });
});

test('release mode fails a built head that main moved past', () => {
  assert.deepEqual(r.releaseModeVerdict({ statuses: BUILT, behindBy: 3, tag: 'v1.2.0' }),
    { ok: false, message: STALE });
});

test('release mode names the missing status first (Update branch)', () => {
  assert.equal(r.releaseModeVerdict({ statuses: [], behindBy: 2, tag: 'v1.2.0' }).message,
    r.CHANGED_AFTER_BUILD);
});

test('the Update-branch text is the D26 text, unchanged', () => {
  assert.equal(r.CHANGED_AFTER_BUILD, 'the release branch changed after it was built (the '
    + 'Update branch button does this); close this pull request and dispatch Create release '
    + 'PR again');
});

test('finish passes a release main has not moved past', () => {
  const v = r.finishVerdict({ behindBy: 0, tag: 'v1.2.0' });
  assert.equal(v.conclusion, 'success');
});

test('finish fails a release main moved past while it built, with the stale text', () => {
  assert.deepEqual(r.finishVerdict({ behindBy: 1, tag: 'v1.2.0' }), {
    conclusion: 'failure', title: 'main moved after v1.2.0 was built', summary: STALE,
  });
});

test('staleReleasePrs picks the bot release pull requests that are behind', () => {
  const p = (number, ref, sha, opts) => ({ ...pr(ref, opts), number, head: {
    ...pr(ref, opts).head, sha } });
  const entries = [
    { pr: p(1, 'release/v1.2.0', 'aaa'), behindBy: 2 }, // stale
    { pr: p(2, 'release/v1.3.0', 'bbb'), behindBy: 0 }, // current
    { pr: p(3, 'release/x', 'ccc', { login: 'oetiker' }), behindBy: 5 }, // a person's
    { pr: p(4, 'release/y', 'ddd', { repo: 'fork/mdmost' }), behindBy: 5 }, // a fork's
  ];
  assert.deepEqual(r.staleReleasePrs(entries, REPO), [{
    number: 1, sha: 'aaa', title: 'main moved after v1.2.0 was built', summary: STALE,
  }]);
});

test('the untagged refusal no longer starts with re-run and names the tree comparison', () => {
  const m = r.untaggedMessage('1.2.0');
  assert.ok(m.startsWith('v1.2.0 is in CHANGES.md on main but has no tag. '));
  assert.match(m, /failed for another reason than the tree comparison/);
  assert.match(m, /push v1\.2\.0 by hand/);
  assert.match(m, /back under \[Unreleased\]/);
  assert.doesNotMatch(m, /^v1\.2\.0[^.]*\. Re-run/);
});

const merged = (ref, sha, opts = {}) => ({ ...pr(ref, opts), merged_at: opts.mergedAt
  === undefined ? '2026-10-01T10:00:00Z' : opts.mergedAt, merge_commit_sha: sha });

test('releasePrMergeCommit finds the merged release pull request of this version', () => {
  const prs = [
    merged('release/v1.2.0', 'closed1', { mergedAt: null }), // an abandoned attempt
    merged('release/v1.1.0', 'old'), // another version
    merged('release/v1.2.0', 'person', { login: 'oetiker' }),
    merged('release/v1.2.0', 'mmm'),
  ];
  assert.equal(r.releasePrMergeCommit(prs, { fullName: REPO, tag: 'v1.2.0' }), 'mmm');
  assert.equal(r.releasePrMergeCommit([], { fullName: REPO, tag: 'v1.2.0' }), null);
});

test('treeVerdict passes equal trees, also after a squash merge', () => {
  assert.equal(r.treeVerdict({ tag: 'v1.2.0', head: 'h', mergeSha: 'squash', mergeTree: 't',
    headTree: 't' }), null);
});

test('treeVerdict names main, the head and the way out when the trees differ', () => {
  assert.equal(r.treeVerdict({ tag: 'v1.2.0', head: 'h', mergeSha: 'm', mergeTree: 't1',
    headTree: 't2' }), 'main at m does not match the release built from h; merge a pull '
    + 'request that moves the v1.2.0 entries in CHANGES.md back under [Unreleased], then '
    + 'dispatch Create release PR again');
});

test('treeVerdict refuses when no merged release pull request contains the head', () => {
  const m = r.treeVerdict({ tag: 'v1.2.0', head: 'h', mergeSha: null, mergeTree: null,
    headTree: 't' });
  assert.match(m, /no merged release pull request contains h/);
  assert.match(m, /Nothing was tagged/);
});

const run = (id, branch, opts = {}) => ({
  id, event: opts.event || 'pull_request', head_branch: branch,
  status: opts.status || 'completed', conclusion: opts.conclusion === undefined
    ? 'action_required' : opts.conclusion,
  head_repository: opts.repo === null ? null : { full_name: opts.repo || REPO },
});

test('parkedRuns keeps only parked pull_request runs of this repository\'s release branches', () => {
  const runs = [
    run(1, 'release/v1.2.0'), // parked
    run(2, 'release/v1.2.0', { status: 'action_required', conclusion: null }), // parked, other spelling
    run(3, 'release/v1.2.0', { conclusion: 'success' }), // someone approved it; it ran
    run(4, 'feature/x'), // not a release branch
    run(5, 'release/v1.2.0', { repo: 'fork/mdmost' }), // a fork's
    run(6, 'release/v1.2.0', { event: 'push' }),
    run(7, 'release/v1.1.0'),
  ];
  assert.deepEqual(r.parkedRuns(runs, { fullName: REPO }).map((x) => x.id), [1, 2, 7]);
  assert.deepEqual(r.parkedRuns(runs, { fullName: REPO, branch: 'release/v1.2.0' })
    .map((x) => x.id), [1, 2]);
  assert.deepEqual(r.parkedRuns(runs, { fullName: REPO, keep: ['release/v1.1.0'] })
    .map((x) => x.id), [1, 2]);
});
```

- [ ] **Step 3: Write the failing checks.js tests**

In `checks.test.js`, delete the four tests `waitForChecks returns as soon as something fails`, `waitForChecks polls until pending clears`, `waitForChecks gives up after the timeout` (lines 59-93) and `waitForChecks does not wait for its own job` (lines 114-127). Append:

```js
// --- D28: the guard does not wait ------------------------------------------

test('guardVerdict refuses a failed check by name', async () => {
  const state = await checks.checkState(fakeGithub([[ok('CI'), bad('Changelog')]]), PARAMS);
  assert.equal(checks.guardVerdict(state), 'Failing checks on this commit: Changelog');
});

test('guardVerdict does not wait for a running check', async () => {
  const state = await checks.checkState(fakeGithub([[ok('CI'), running('Slow')]]), PARAMS);
  assert.equal(checks.guardVerdict(state), null);
});

test('guardVerdict does not refuse a commit without checks', async () => {
  // The test job runs ci.yml on this commit plus the release changes.
  const state = await checks.checkState(fakeGithub([[]]), PARAMS);
  assert.equal(checks.guardVerdict(state), null);
});

test('guardVerdict ignores an earlier attempt\'s failed build and test jobs', async () => {
  const github = fakeGithub([[
    withId(1, 'CI', 'completed', 'success'),
    withId(31, 'test / Lint', 'completed', 'failure'),
    withId(32, 'build / Build the source tarball', 'completed', 'failure'),
  ]]);
  const state = await checks.checkState(github, PARAMS, { ignoreCheckRunIds: [31, 32] });
  assert.equal(checks.guardVerdict(state), null);
});

test('waitForChecks is gone', () => {
  assert.equal(checks.waitForChecks, undefined);
});
```

`withId` is defined at line 99, before the appended tests, so it is in scope.

- [ ] **Step 4: Run the tests to see them fail**

Run: `node --test skills/repo-infra/assets/workflows/lib/*.test.js 2>&1 | tail -12`
Expected: failures such as `TypeError: r.releaseTag is not a function` and `TypeError: checks.guardVerdict is not a function`.

- [ ] **Step 5: Implement in `release.js`** (insert after `releaseBuilt`, before `module.exports`)

```js
// --- D28: one release flow, tested before the merge ------------------------

const CHANGED_AFTER_BUILD = 'the release branch changed after it was built (the Update '
  + 'branch button does this); close this pull request and dispatch Create release PR again';

function releaseTag(ref) {
  return ref.replace(/^release\//, '');
}

function staleMessage(tag) {
  return `main moved after ${tag} was built; close this pull request and dispatch `
    + 'Create release PR again';
}

// ci-passed and changelog-updated on a release pull request. The test results
// do not count: finish built and tested exactly the head that carries
// release-built, and the up-to-date rule needs it not to be behind main. The
// answer must equal finishVerdict's and staleReleasePrs', or an approved
// parked run would turn their red check green.
function releaseModeVerdict({ statuses, behindBy, tag }) {
  if (!releaseBuilt(statuses)) return { ok: false, message: CHANGED_AFTER_BUILD };
  if (behindBy > 0) return { ok: false, message: staleMessage(tag) };
  return {
    ok: true,
    message: `${tag}: this head was built and tested, and main has not moved since.`,
  };
}

// finish opens the pull request first and judges it afterwards, so a release
// that went stale while it built is visible and says why.
function finishVerdict({ behindBy, tag }) {
  if (behindBy > 0) {
    return { conclusion: 'failure', title: `main moved after ${tag} was built`,
      summary: staleMessage(tag) };
  }
  return { conclusion: 'success', title: `${tag} is built and tested`,
    summary: `Create release PR built and tested ${tag} on the current main.` };
}

// release-pr-current: every open release pull request main has moved past.
function staleReleasePrs(entries, fullName) {
  return entries
    .filter(({ pr, behindBy }) => isReleasePr(pr, fullName) && behindBy > 0)
    .map(({ pr }) => {
      const tag = releaseTag(pr.head.ref);
      return { number: pr.number, sha: pr.head.sha,
        title: `main moved after ${tag} was built`, summary: staleMessage(tag) };
    });
}

// A re-run helps only when publish failed for a reason other than the tree
// comparison; after that one, abandoning is the way out.
function untaggedMessage(version) {
  return `v${version} is in CHANGES.md on main but has no tag. If its Publish release run `
    + 'failed for another reason than the tree comparison, re-run its failed jobs; if it '
    + `is already out under another tag, push v${version} by hand; to abandon it, merge a `
    + 'pull request that moves its entries back under [Unreleased].';
}

// The release pull request whose merge put this version on main, found from
// the recorded head. Not context.sha: a failed first publish followed by an
// ordinary merge starts a new run on a later commit.
function releasePrMergeCommit(prs, { fullName, tag }) {
  const found = prs.find((pr) => isReleasePr(pr, fullName)
    && pr.head.ref === `release/${tag}` && pr.merged_at);
  return found ? found.merge_commit_sha : null;
}

// With the up-to-date rule on, the merge commit's tree is the built head's
// tree (also after a squash or rebase). A mismatch means the rule was off.
function treeVerdict({ tag, head, mergeSha, mergeTree, headTree }) {
  if (!mergeSha) {
    return `${tag}: no merged release pull request contains ${head}, so publish cannot `
      + 'compare main with the release that was built. Nothing was tagged.';
  }
  if (mergeTree === headTree) return null;
  return `main at ${mergeSha} does not match the release built from ${head}; merge a pull `
    + `request that moves the ${tag} entries in CHANGES.md back under [Unreleased], then `
    + 'dispatch Create release PR again';
}

// The pull_request runs of a release branch park for an approval nobody needs
// to give. A run someone approved ran, and is kept. GitHub reports a parked
// run with status or conclusion `action_required`, depending on the endpoint.
const isParked = (run) => run.status === 'action_required'
  || run.conclusion === 'action_required';

function parkedRuns(runs, { fullName, branch = null, keep = [] }) {
  return runs.filter((run) => run.event === 'pull_request' && isParked(run)
    && Boolean(run.head_repository) && run.head_repository.full_name === fullName
    && typeof run.head_branch === 'string' && run.head_branch.startsWith('release/')
    && (branch === null || run.head_branch === branch)
    && !keep.includes(run.head_branch));
}
```

Replace the export block:

```js
module.exports = {
  BUILD_RECORD, BOT, isReleasePr, blockingReleasePr, untaggedRelease,
  staleDrafts, ownDrafts, refusedReleaseFiles, undeclaredReleaseFiles,
  decodeText, releaseBuilt,
  CHANGED_AFTER_BUILD, releaseTag, staleMessage, releaseModeVerdict, finishVerdict,
  staleReleasePrs, untaggedMessage, releasePrMergeCommit, treeVerdict, parkedRuns,
};
```

- [ ] **Step 6: Implement in `checks.js`**

Delete `waitForChecks` (lines 153-167). Add before `module.exports`:

```js
// D28: the guard does not wait. A check that already failed on the dispatched
// commit is refused by name. A running check, or none at all, is not: the
// test job runs the same ci.yml on this commit plus the release changes, and
// finish opens no pull request unless it is green.
function guardVerdict(state) {
  if (state.failed.length === 0) return null;
  return `Failing checks on this commit: ${state.failed.map((c) => c.name).join(', ')}`;
}
```

Export line: `module.exports = { checkState, guardVerdict, guardIgnoreIds };`. In the comment above `guardIgnoreIds` (lines 176-189) replace "the set a guard waiting on its own commit must ignore" with "the set the guard must ignore: its own jobs, and the build and test jobs of every earlier attempt, which leave failed check runs on this same commit".

- [ ] **Step 7: Run the JS tests to see them pass**

Run: `node --test skills/repo-infra/assets/workflows/lib/*.test.js 2>&1 | tail -9`
Expected: `ℹ fail 0`; `ℹ pass 154` (138 - 4 waitForChecks tests + 15 release + 5 checks). Report the real number and the arithmetic.

- [ ] **Step 8: Re-render and run the Python suite**

Run the re-render command (Global Constraints), then `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q -m "not container" tests 2>&1 | tail -3`.
Expected: `657 passed`. `tests/test_release_guard.py::test_the_guard_gathers_its_ignore_ids_through_the_tested_function` still passes, because `release-pr.yml` still says `waitForChecks` until Task 4 (the YAML is not executed here).

- [ ] **Step 9: Commit**

```bash
git add skills/repo-infra/assets/workflows/lib skills/repo-infra/assets/manifest.json .github/workflows/lib
git commit -m "workflow-lib v6: D28 verdicts for release mode, finish, publish and the guard

The release-mode, finish and release-pr-current verdicts share one
stale text so an approved parked run cannot disagree with them. The
guard no longer waits; waitForChecks is gone.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Phase 2: the required checks

### Task 2: `ci.yml` is a reusable workflow; `ci-passed` release mode; `release-pr-current`

**Files:**
- Modify: `skills/repo-infra/assets/ci/ci-frame.yml` (marker v2, `workflow_call`)
- Modify: every `skills/repo-infra/assets/ci/ci-*.yml` that has an `actions/checkout@v7` step (all except `ci-frame.yml`, `ci-aggregator.yml`, `ci-local.yml`)
- Modify: `skills/repo-infra/assets/ci/ci-local.yml`, `skills/repo-infra/assets/ci/ci-github-action.yml:104-105`
- Modify: `skills/repo-infra/assets/ci/ci-aggregator.yml` (whole file)
- Modify: `skills/repo-infra/assets/manifest.json:34-48` (block versions)
- Create: `tests/test_release_mode.py`
- Modify: `tests/test_ci_local.py:33-36`, `tests/test_github_action.py:187-192`
- Modify (re-render): `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `isReleasePr`, `releaseTag`, `releaseModeVerdict`, `staleReleasePrs` from Task 1.
- Produces: `ci.yml` callable as `uses: ./.github/workflows/ci.yml` with `with: { ref }` (Task 4); `ci-passed` step `id: release` output `mode` (`release` | `ordinary`); test helper `ci_passed(tmp_path, **case) -> {"failures": [...], "outputs": {...}}` in `tests/test_release_mode.py` (Task 3 imports it).

- [ ] **Step 1: Write the failing tests** (`tests/test_release_mode.py`)

```python
"""D28: ci.yml as a reusable workflow, ci-passed's release mode, release-pr-current."""

import json
import os
import pathlib
import shutil
import subprocess

import pytest
import yaml

from repo_infra.assemble import assemble_ci, render_all
from repo_infra.detect import Detection

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
BOT = "github-actions[bot]"
REF = "${{ inputs.ref }}"
BUILT = [{"context": "release-built", "state": "success", "creator": {"login": BOT}}]
BLURB = ("the release branch changed after it was built (the Update branch button "
         "does this); close this pull request and dispatch Create release PR again")
STALE = ("main moved after v1.2.0 was built; close this pull request and dispatch "
         "Create release PR again")


def on(doc):
    # PyYAML reads the bare key `on` as the boolean True.
    return doc.get("on", doc.get(True))


def ci_jobs(blocks=()):
    return yaml.safe_load(assemble_ci(ASSETS, list(blocks), MANIFEST))["jobs"]


def test_ci_yml_is_also_a_reusable_workflow_with_an_optional_ref():
    doc = yaml.safe_load(assemble_ci(ASSETS, [], MANIFEST))
    assert on(doc)["workflow_call"] == {
        "inputs": {"ref": {"type": "string", "required": False, "default": ""}}}
    assert set(on(doc)) == {"push", "pull_request", "workflow_call"}
    assert doc["permissions"] == {"contents": "read"}


@pytest.mark.parametrize("block", sorted(MANIFEST["ci_blocks"]))
def test_every_ci_fragment_checks_out_the_called_ref(block):
    jobs = yaml.safe_load((ASSETS / "ci" / (block + ".yml")).read_text(encoding="utf-8"))
    for job_id, job in jobs.items():
        for step in job.get("steps", []):
            if str(step.get("uses", "")).startswith("actions/checkout@"):
                assert (step.get("with") or {}).get("ref") == REF, "%s: %s" % (block, job_id)


def test_every_called_workflow_gets_ref_and_secrets(tmp_path):
    (tmp_path / "action.yml").write_text("name: x\n")
    result = Detection.load(ASSETS / "detection.json").detect(tmp_path)
    jobs = yaml.safe_load(render_all(ASSETS, result, MANIFEST, ci_local=True)[
        ".github/workflows/ci.yml"])["jobs"]
    called = {k: j for k, j in jobs.items() if str(j.get("uses", "")).startswith("./")}
    assert sorted(called) == ["action-test", "ci-local"]
    for job in called.values():
        assert job["with"] == {"ref": REF}
        assert job["secrets"] == "inherit"


def test_ci_passed_raises_only_what_release_mode_reads():
    assert ci_jobs()["ci-passed"]["permissions"] == {
        "contents": "read", "pull-requests": "read", "statuses": "read"}


def test_release_pr_current_runs_on_push_only_and_may_write_checks():
    job = ci_jobs()["release-pr-current"]
    assert job["if"] == "github.event_name == 'push'"
    assert job["permissions"] == {
        "contents": "read", "pull-requests": "read", "checks": "write"}
    assert "release-pr-current" not in ci_jobs()["ci-passed"]["needs"]


def test_release_mode_loads_the_library_from_the_base_commit():
    steps = ci_jobs()["ci-passed"]["steps"]
    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@"))
    assert checkout["with"] == {"ref": "${{ github.event.pull_request.base.sha }}",
                                "path": "repo-infra-base"}
    script = next(s for s in steps if s.get("id") == "release")["with"]["script"]
    assert "repo-infra-base/.github/workflows/lib" in script


def test_the_failure_step_is_skipped_in_release_mode():
    last = ci_jobs()["ci-passed"]["steps"][-1]
    assert last["run"] == "exit 1"
    assert last["if"] == ("steps.release.outputs.mode != 'release' && "
                          "(contains(needs.*.result, 'failure') || "
                          "contains(needs.*.result, 'cancelled'))")


def _node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    return node


def _workspace(tmp_path, base_too=True):
    ws = tmp_path / "ws"
    shutil.copytree(ROOT / ".github/workflows/lib", ws / ".github/workflows/lib")
    if base_too:
        shutil.copytree(ROOT / ".github/workflows/lib",
                        ws / "repo-infra-base/.github/workflows/lib")
    return ws


def _run(tmp_path, ws, script, prelude):
    harness = prelude + "\n(async () => {\n" + script + "\n})().then(() => console.log(" \
        "JSON.stringify({ failures, outputs, warnings, notices, created })));\n"
    path = tmp_path / "harness.js"
    path.write_text(harness, encoding="utf-8")
    proc = subprocess.run([_node(), str(path)], capture_output=True, text=True, cwd=ws,
                          env={"GITHUB_WORKSPACE": str(ws), "PATH": os.environ["PATH"]})
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


PRELUDE = """
const failures = []; const outputs = {}; const warnings = []; const notices = [];
const created = [];
const core = { setFailed: (m) => failures.push(m), setOutput: (k, v) => { outputs[k] = v; },
  warning: (m) => warnings.push(m), notice: (m) => notices.push(m) };
"""


def ci_passed(tmp_path, *, head_ref="release/v1.2.0", login=BOT, head_repo="o/r",
              statuses=(), behind=0, sabotage_merge_lib=False):
    """Run ci-passed's release step against a fake API; the D28 verdict table."""
    script = next(s for s in ci_jobs()["ci-passed"]["steps"]
                  if s.get("id") == "release")["with"]["script"]
    ws = _workspace(tmp_path)
    if sabotage_merge_lib:
        (ws / ".github/workflows/lib/release.js").write_text("module.exports = {};\n")
    pr = {"number": 7, "user": {"login": login},
          "head": {"ref": head_ref, "sha": "h",
                   "repo": {"full_name": head_repo} if head_repo else None},
          "base": {"ref": "main", "sha": "b"}}
    prelude = PRELUDE + """
const statuses = %s;
const github = {
  paginate: async (fn) => (fn === 'statuses' ? statuses : []),
  rest: { repos: { listCommitStatusesForRef: 'statuses',
    compareCommitsWithBasehead: async ({ basehead }) => {
      if (basehead !== 'main...h') throw new Error(`basehead ${basehead}`);
      return { data: { behind_by: %d } }; } } },
};
const context = { repo: { owner: 'o', repo: 'r' }, payload: { pull_request: %s } };
""" % (json.dumps(list(statuses)), behind, json.dumps(pr))
    return _run(tmp_path, ws, script, prelude)


def test_a_built_current_release_pull_request_passes_ci_passed(tmp_path):
    out = ci_passed(tmp_path, statuses=BUILT)
    assert out["failures"] == [] and out["outputs"] == {"mode": "release"}


def test_a_stale_release_pull_request_fails_ci_passed(tmp_path):
    assert ci_passed(tmp_path, statuses=BUILT, behind=2)["failures"] == [STALE]


def test_an_unbuilt_release_head_fails_ci_passed(tmp_path):
    assert ci_passed(tmp_path)["failures"] == [BLURB]


@pytest.mark.parametrize("case", [{"login": "oetiker"}, {"head_repo": "fork/r"},
                                  {"head_repo": None}])
def test_someone_elses_release_branch_gets_the_ordinary_rules(tmp_path, case):
    out = ci_passed(tmp_path, head_ref="release/x", **case)
    assert out["failures"] == [] and out["outputs"] == {"mode": "ordinary"}


def test_ci_passed_reads_the_library_of_the_base_commit(tmp_path):
    # A release branch that broke its own release.js still gets the base's verdict.
    assert ci_passed(tmp_path, statuses=BUILT, behind=1,
                     sabotage_merge_lib=True)["failures"] == [STALE]


def release_pr_current(tmp_path, prs, behind, fail_compare=False):
    script = ci_jobs()["release-pr-current"]["steps"][-1]["with"]["script"]
    ws = _workspace(tmp_path, base_too=False)
    prelude = PRELUDE + """
const prs = %s; const behind = %s; const failCompare = %s;
const github = {
  paginate: async (fn, args) => { if (fn !== 'pulls' || args.state !== 'open') throw new Error(fn);
    return prs; },
  rest: {
    pulls: { list: 'pulls' },
    repos: { compareCommitsWithBasehead: async ({ basehead }) => {
      if (failCompare) { const e = new Error('Server Error'); e.status = 500; throw e; }
      return { data: { behind_by: behind[basehead.split('...')[1]] } }; } },
    checks: { create: async (a) => { created.push(a); return { data: {} }; } },
  },
};
const context = { repo: { owner: 'o', repo: 'r' } };
""" % (json.dumps(prs), json.dumps(behind), "true" if fail_compare else "false")
    return _run(tmp_path, ws, script, prelude)


def _pr(number, ref, sha, login=BOT, repo="o/r"):
    return {"number": number, "user": {"login": login}, "base": {"ref": "main"},
            "head": {"ref": ref, "sha": sha, "repo": {"full_name": repo}}}


def test_release_pr_current_marks_only_the_stale_release_pull_request(tmp_path):
    prs = [_pr(1, "release/v1.2.0", "s1"), _pr(2, "release/v1.3.0", "s2"),
           _pr(3, "release/x", "s3", login="oetiker"), _pr(4, "fix/x", "s4")]
    out = release_pr_current(tmp_path, prs, {"s1": 1, "s2": 0, "s3": 9, "s4": 9})
    assert out["created"] == [{
        "owner": "o", "repo": "r", "name": "ci-passed", "head_sha": "s1",
        "status": "completed", "conclusion": "failure",
        "output": {"title": "main moved after v1.2.0 was built", "summary": STALE}}]
    assert out["failures"] == []


def test_release_pr_current_never_fails_on_an_api_error(tmp_path):
    out = release_pr_current(tmp_path, [_pr(1, "release/v1.2.0", "s1")], {},
                             fail_compare=True)
    assert out["failures"] == [] and out["created"] == []
    assert len(out["warnings"]) == 1 and "Server Error" in out["warnings"][0]
```

In `tests/test_ci_local.py`, replace the first assertion of `test_ci_local_renders_the_seam_job_and_requires_it` with:

```python
    assert jobs["ci-local"] == {"uses": "./.github/workflows/ci-local.yml",
                                "with": {"ref": "${{ inputs.ref }}"}, "secrets": "inherit"}
```

In `tests/test_github_action.py`, `test_the_seam_names_the_one_path_the_contract_fixes`, replace the assertion with:

```python
    assert block["action-test"] == {"uses": "./.github/workflows/action-test.yml",
                                    "with": {"ref": "${{ inputs.ref }}"},
                                    "secrets": "inherit"}
```

Then read the next test, `test_the_seam_job_carries_no_keys_a_uses_job_cannot_have`, and make sure `with` and `secrets` are on its allowed list (GitHub allows `uses`, `with`, `secrets`, `needs`, `if`, `permissions`, `strategy`, `concurrency`, `name` on a calling job); add them if that test lists allowed keys.

- [ ] **Step 2: Run them to see them fail**

Run: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests/test_release_mode.py tests/test_ci_local.py tests/test_github_action.py 2>&1 | tail -5`
Expected: failures, e.g. `KeyError: 'workflow_call'` and `KeyError: 'release-pr-current'`.

- [ ] **Step 3: The frame** (`skills/repo-infra/assets/ci/ci-frame.yml`, whole file)

```yaml
name: CI
# repo-infra: ci v2

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  # D28: Create release PR runs this same file on the release branch before
  # it opens the pull request. On push and pull_request `inputs.ref` is empty
  # and every checkout uses its default commit.
  workflow_call:
    inputs:
      ref:
        type: string
        required: false
        default: ''

permissions:
  contents: read

jobs:
```

- [ ] **Step 4: Every fragment checks out `inputs.ref`**

Run this once, before Step 6 adds the aggregator's own checkouts:

```bash
python3 - <<'PY'
import pathlib
old = "      - uses: actions/checkout@v7\n"
new = old + "        with:\n          ref: ${{ inputs.ref }}\n"
for p in sorted(pathlib.Path("skills/repo-infra/assets/ci").glob("ci-*.yml")):
    if p.name in ("ci-frame.yml", "ci-aggregator.yml"):
        continue
    t = p.read_text(encoding="utf-8")
    if old in t:
        p.write_text(t.replace(old, new), encoding="utf-8")
        print(p.name, t.count(old))
PY
```

Expected output, one line per file with its checkout count: `ci-checkmk-plugin.yml 3`, `ci-claude-plugin.yml 1`, `ci-github-action.yml 1`, `ci-go.yml 2`, `ci-lib.yml 1`, `ci-man.yml 1`, `ci-node-bun.yml 1`, `ci-node-pnpm.yml 1`, `ci-perl-autotools.yml 1`, `ci-perl-mkpl.yml 1`, `ci-python.yml 2`, `ci-repo-infra-selftest.yml 2`, `ci-rust-musl.yml 1`, `ci-rust.yml 3`. Then `grep -n -A1 'actions/checkout@' skills/repo-infra/assets/ci/ci-*.yml | grep -v 'with:\|checkout@\|^--$'` must print nothing.

- [ ] **Step 5: The two seams pass `ref` and the secrets**

`skills/repo-infra/assets/ci/ci-local.yml`, the job at its end:

```yaml
  ci-local:
    uses: ./.github/workflows/ci-local.yml
    with:
      ref: ${{ inputs.ref }}
    secrets: inherit
```

Add to the comment above it: `# The file declares the workflow_call input ref and checks it out in every` / `# actions/checkout (D28); Create release PR passes the release branch here.`

`skills/repo-infra/assets/ci/ci-github-action.yml`, the job at its end:

```yaml
  action-test:
    uses: ./.github/workflows/action-test.yml
    with:
      ref: ${{ inputs.ref }}
    secrets: inherit
```

- [ ] **Step 6: The aggregator** (`skills/repo-infra/assets/ci/ci-aggregator.yml`, whole file)

```yaml
  # The single context the ruleset requires (spec D2). It exists so branch
  # protection can name one check that means "this repository's CI passed",
  # whatever this repository's jobs happen to be. The needs list is generated
  # by the assembler from the blocks that went into this file.
  #
  # `if: always()` is load-bearing. Without it this job is *skipped* when a
  # dependency fails, and a skipped job reports Success -- so the required
  # check would go green on a red build. It fails open, silently, and looks
  # like it is working.
  #
  # Release mode (D28): on a release pull request the test results do not
  # count. Create release PR tested exactly the head that carries the
  # release-built status, and the head must not be behind main. The verdict
  # is lib/release.js:releaseModeVerdict, loaded from the base commit, so a
  # release branch changed by accident cannot pass on library code it changed.
  ci-passed:
    if: always()
    needs: []
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions:
      contents: read
      pull-requests: read
      statuses: read
    steps:
      - if: github.event_name == 'pull_request' && startsWith(github.head_ref, 'release/')
        uses: actions/checkout@v7
        with:
          ref: ${{ github.event.pull_request.base.sha }}
          path: repo-infra-base

      - if: github.event_name == 'pull_request' && startsWith(github.head_ref, 'release/')
        uses: actions/setup-node@v7
        with:
          node-version: 22

      - id: release
        name: Release mode
        if: github.event_name == 'pull_request' && startsWith(github.head_ref, 'release/')
        uses: actions/github-script@v9
        with:
          script: |
            const lib = `${process.env.GITHUB_WORKSPACE}/repo-infra-base/.github/workflows/lib`;
            const releaseLib = require(`${lib}/release.js`);
            const { owner, repo } = context.repo;
            const pr = context.payload.pull_request;
            // A fork's or a person's release/x gets the ordinary rules.
            if (!releaseLib.isReleasePr(pr, `${owner}/${repo}`)) {
              core.setOutput('mode', 'ordinary');
              return;
            }
            core.setOutput('mode', 'release');
            const statuses = await github.paginate(
              github.rest.repos.listCommitStatusesForRef,
              { owner, repo, ref: pr.head.sha, per_page: 100 },
            );
            const { data: compared } = await github.rest.repos.compareCommitsWithBasehead({
              owner, repo, basehead: `${pr.base.ref}...${pr.head.sha}`,
            });
            const verdict = releaseLib.releaseModeVerdict({
              statuses,
              behindBy: compared.behind_by,
              tag: releaseLib.releaseTag(pr.head.ref),
            });
            if (!verdict.ok) {
              core.setFailed(verdict.message);
              return;
            }
            core.notice(verdict.message);

      - if: steps.release.outputs.mode != 'release' && (contains(needs.*.result, 'failure') || contains(needs.*.result, 'cancelled'))
        run: exit 1

  # D28: when main moves, every open release pull request is stale. The
  # ruleset's up-to-date rule already refuses its merge; this check run says
  # why, where GitHub alone offers the Update branch button. Push to main
  # only: when Create release PR calls this file the event is
  # workflow_dispatch and the job skips. It never fails: a failed job is a
  # failed check run on this main commit, and the guard of the next dispatch
  # would refuse it. An API error is a warning.
  release-pr-current:
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions:
      contents: read
      pull-requests: read
      checks: write
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ inputs.ref }}

      - uses: actions/setup-node@v7
        with:
          node-version: 22

      - name: Mark stale release pull requests
        uses: actions/github-script@v9
        with:
          script: |
            try {
              const releaseLib = require(
                `${process.env.GITHUB_WORKSPACE}/.github/workflows/lib/release.js`);
              const { owner, repo } = context.repo;
              const fullName = `${owner}/${repo}`;
              const prs = await github.paginate(github.rest.pulls.list, {
                owner, repo, state: 'open', per_page: 100,
              });
              const entries = [];
              for (const pr of prs.filter((p) => releaseLib.isReleasePr(p, fullName))) {
                const { data: compared } = await github.rest.repos.compareCommitsWithBasehead({
                  owner, repo, basehead: `${pr.base.ref}...${pr.head.sha}`,
                });
                entries.push({ pr, behindBy: compared.behind_by });
              }
              for (const stale of releaseLib.staleReleasePrs(entries, fullName)) {
                await github.rest.checks.create({
                  owner, repo, name: 'ci-passed', head_sha: stale.sha,
                  status: 'completed', conclusion: 'failure',
                  output: { title: stale.title, summary: stale.summary },
                });
                core.notice(`#${stale.number}: ${stale.summary}`);
              }
            } catch (error) {
              core.warning(`Could not mark stale release pull requests: ${error.message}`);
            }
```

- [ ] **Step 7: Bump the CI block versions** in `manifest.json` `ci_blocks` exactly as listed in Global Constraints (15 entries).

- [ ] **Step 8: Run the tests**

Run: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests/test_release_mode.py tests/test_ci_local.py tests/test_github_action.py tests/test_blocks.py tests/test_assemble.py tests/test_ci_rust.py tests/test_ci_man.py tests/test_ci_rust_musl.py 2>&1 | tail -3`
Expected: all pass. `tests/test_assemble.py` uses its own mini fixture and is unaffected.

- [ ] **Step 9: Re-render, full gate, commit**

Re-render, then the Full gate. Expected: JS unchanged from Task 1; Python 657 + 30 new tests of `test_release_mode.py` (15 parametrized over the CI blocks + 15 others) = `687 passed`. Then:

```bash
git add skills/repo-infra/assets/ci skills/repo-infra/assets/manifest.json tests/test_release_mode.py tests/test_ci_local.py tests/test_github_action.py .github/workflows/ci.yml
git commit -m "ci v2: callable with a ref, release mode for ci-passed, release-pr-current (D28)

Every CI fragment checks out inputs.ref, so Create release PR can run
the same ci.yml on the release branch. The seams pass ref and the
secrets on. ci-passed judges a release pull request by its build
status and its distance to main, from the base commit's library.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `changelog` v4: release mode from the base commit's library

**Files:**
- Modify: `skills/repo-infra/assets/workflows/changelog.yml` (whole file below), `skills/repo-infra/assets/manifest.json:16` (`"version": 4`)
- Modify: `tests/test_changelog_gate.py` (harness and the release tests)
- Modify (re-render): `.github/workflows/changelog.yml`

**Interfaces:**
- Consumes: `isReleasePr`, `releaseTag`, `releaseModeVerdict` (Task 1); `ci_passed` from `tests/test_release_mode.py` (Task 2).

- [ ] **Step 1: Rewrite the harness and the release tests** in `tests/test_changelog_gate.py`

Replace `gate()` and every test from `test_the_job_may_read_statuses` through `test_a_forks_release_branch_gets_the_ordinary_rules` (lines 25-120) with the following; keep the four tests after it unchanged.

```python
def gate(tmp_path, *, head_ref, login=BOT, head_repo="o/r", labels=(), statuses=(),
         behind=0, head_changes=SAME, base_changes=SAME, sabotage_merge_lib=False):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = job()["steps"][-1]["with"]["script"]
    ws = tmp_path / "ws"
    shutil.copytree(ROOT / ".github/workflows/lib", ws / ".github/workflows/lib")
    shutil.copytree(ROOT / ".github/workflows/lib", ws / "repo-infra-base/.github/workflows/lib")
    if sabotage_merge_lib:
        (ws / ".github/workflows/lib/release.js").write_text("module.exports = {};\n")
    contents = {"CHANGES.md@b": base_changes, "CHANGES.md@h": head_changes}
    contents = {k: v for k, v in contents.items() if v is not None}
    pr = {"number": 1, "labels": [{"name": n} for n in labels], "user": {"login": login},
          "head": {"ref": head_ref, "sha": "h",
                   "repo": {"full_name": head_repo} if head_repo else None},
          "base": {"ref": "main", "sha": "b"}}
    harness = """
const contents = %s;
const statuses = %s;
const failures = [];
const github = {
  paginate: async (fn) => (fn === 'statuses' ? statuses : []),
  rest: { repos: {
    listCommitStatusesForRef: 'statuses',
    compareCommitsWithBasehead: async ({ basehead }) => {
      if (basehead !== 'main...h') throw new Error(`basehead ${basehead}`);
      return { data: { behind_by: %d } }; },
    getContent: async ({ path, ref }) => {
      const text = contents[`${path}@${ref}`];
      if (text === undefined) { const e = new Error('Not Found'); e.status = 404; throw e; }
      return { data: { content: Buffer.from(text).toString('base64') } };
    },
  } },
};
const core = { setFailed: (m) => failures.push(m), notice: () => {} };
const context = { repo: { owner: 'o', repo: 'r' }, payload: { pull_request: %s } };
(async () => {
%s
})().then(() => console.log(JSON.stringify({ failures })));
""" % (json.dumps(contents), json.dumps(list(statuses)), behind, json.dumps(pr), script)
    path = tmp_path / "gate.js"
    path.write_text(harness, encoding="utf-8")
    proc = subprocess.run([node, str(path)], capture_output=True, text=True, cwd=ws,
                          env={"GITHUB_WORKSPACE": str(ws), "PATH": os.environ["PATH"]})
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)["failures"]


BUILT = [{"context": "release-built", "state": "success", "creator": {"login": BOT}}]
STALE = ("main moved after v1.2.0 was built; close this pull request and dispatch "
         "Create release PR again")


def test_the_job_runs_on_release_branches():
    # The harness never evaluates this expression, so only an exact comparison
    # notices `&&` in place of `||` or a dropped `!`.
    assert job()["if"] == ("startsWith(github.head_ref, 'release/') || "
                           "!contains(github.event.pull_request.labels.*.name, 'no-changelog')")


def test_the_job_may_read_statuses():
    wf = yaml.safe_load(ASSET.read_text(encoding="utf-8"))
    assert wf["permissions"]["statuses"] == "read"


def test_the_base_commit_is_checked_out_beside_the_merge_commit():
    checkouts = [s for s in job()["steps"] if str(s.get("uses", "")).startswith("actions/checkout@")]
    assert checkouts[0].get("with") is None
    assert checkouts[1]["with"] == {"ref": "${{ github.event.pull_request.base.sha }}",
                                    "path": "repo-infra-base"}


def test_every_repository_gates_its_release_pull_requests(tmp_path):
    # D28: no release_build switch any more; the exemption is gone.
    assert gate(tmp_path, head_ref="release/v1.2.0") == [BLURB]


def test_a_built_current_release_pull_request_passes(tmp_path):
    assert gate(tmp_path, head_ref="release/v1.2.0", statuses=BUILT) == []


def test_a_release_pull_request_main_moved_past_fails(tmp_path):
    assert gate(tmp_path, head_ref="release/v1.2.0", statuses=BUILT, behind=1) == [STALE]


def test_the_label_does_not_rescue_a_release_pull_request(tmp_path):
    assert gate(tmp_path, head_ref="release/v1.2.0", labels=["no-changelog"]) == [BLURB]


def test_a_status_someone_else_set_does_not_count(tmp_path):
    fake = [{**BUILT[0], "creator": {"login": "oetiker"}}]
    assert gate(tmp_path, head_ref="release/v1.2.0", statuses=fake) == [BLURB]


def test_release_mode_reads_the_library_of_the_base_commit(tmp_path):
    assert gate(tmp_path, head_ref="release/v1.2.0", statuses=BUILT, behind=1,
                sabotage_merge_lib=True) == [STALE]


def test_a_persons_release_branch_gets_the_ordinary_rules(tmp_path):
    failures = gate(tmp_path, head_ref="release/x", login="oetiker")
    assert len(failures) == 1 and "[Unreleased]" in failures[0]
    assert gate(tmp_path, head_ref="release/x", login="oetiker", labels=["no-changelog"]) == []


def test_a_forks_release_branch_gets_the_ordinary_rules(tmp_path):
    assert gate(tmp_path, head_ref="release/x", head_repo="fork/r", head_changes=MORE) == []


@pytest.mark.parametrize("statuses,behind", [(BUILT, 0), (BUILT, 2), ((), 0), ((), 3)])
def test_both_required_checks_agree_on_a_release_pull_request(tmp_path, statuses, behind):
    # Review Focus 2: an approved parked run must not disagree with finish
    # and release-pr-current.
    from test_release_mode import ci_passed

    ours = gate(tmp_path / "gate", head_ref="release/v1.2.0", statuses=statuses, behind=behind)
    theirs = ci_passed(tmp_path / "ci", statuses=statuses, behind=behind)["failures"]
    assert ours == theirs
```

Also replace the module docstring with `"""changelog v4 (D28): every release pull request is gated on its build and on main."""` and make each `tmp_path / "gate"` and `tmp_path / "ci"` exist (`(tmp_path / "gate").mkdir()` / `(tmp_path / "ci").mkdir()` at the top of the agreement test).

- [ ] **Step 2: Run it to see it fail**

Run: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests/test_changelog_gate.py 2>&1 | tail -5`
Expected: failures; `test_every_repository_gates_its_release_pull_requests` gets `[]` (the D26 exemption) instead of the BLURB.

- [ ] **Step 3: Write `changelog.yml` v4** (whole file)

```yaml
name: Changelog
# repo-infra: changelog v4
#
# Required, not advisory (spec D2). Being required is only safe because the
# escape hatch below is a JOB-level `if:`. A job skipped by a condition
# reports Success, while a WORKFLOW skipped by a paths/branches filter stays
# Pending forever and blocks the merge. Never add paths: or paths-ignore: to
# this workflow (spec D13).
#
# A release pull request is opened by GITHUB_TOKEN, so its runs park until
# someone approves them. Nobody needs to (D28): Create release PR writes this
# check itself. This job exists for the case where someone approves them
# anyway, or presses Update branch, and then agrees with Create release PR.

on:
  pull_request:
    branches: [main]
    types: [opened, synchronize, reopened, labeled, unlabeled]

permissions:
  contents: read
  pull-requests: read
  # D28 release mode: the release-built commit status on the head.
  statuses: read

jobs:
  # No `name:`: the check context is the job id, `changelog-updated`, which is
  # what the ruleset requires. Renaming this job silently un-requires the check.
  changelog-updated:
    # The no-changelog label is the deliberate escape hatch for typo and CI-only
    # changes. Without it every weekly dependabot PR is blocked, since this
    # check is required. The label must exist in the repository: a label that
    # does not exist is silently ignored by dependabot.
    #
    # release/* always runs: a release pull request is gated on its build, and
    # the label must not turn that red check green after an Update branch.
    if: >-
      startsWith(github.head_ref, 'release/') ||
      !contains(github.event.pull_request.labels.*.name, 'no-changelog')
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v7

      # Release mode loads the library from the base commit (D28).
      - uses: actions/checkout@v7
        with:
          ref: ${{ github.event.pull_request.base.sha }}
          path: repo-infra-base

      - uses: actions/github-script@v9
        with:
          script: |
            const ws = process.env.GITHUB_WORKSPACE;
            const changes = require(`${ws}/.github/workflows/lib/changes.js`);
            const { owner, repo } = context.repo;
            const pr = context.payload.pull_request;

            if (pr.head.ref.startsWith('release/')) {
              const releaseLib = require(
                `${ws}/repo-infra-base/.github/workflows/lib/release.js`);
              if (releaseLib.isReleasePr(pr, `${owner}/${repo}`)) {
                // The head commit's statuses, not the merge commit's: finish
                // sets release-built on the head it built.
                const statuses = await github.paginate(
                  github.rest.repos.listCommitStatusesForRef,
                  { owner, repo, ref: pr.head.sha, per_page: 100 },
                );
                const { data: compared } = await github.rest.repos.compareCommitsWithBasehead({
                  owner, repo, basehead: `${pr.base.ref}...${pr.head.sha}`,
                });
                const verdict = releaseLib.releaseModeVerdict({
                  statuses,
                  behindBy: compared.behind_by,
                  tag: releaseLib.releaseTag(pr.head.ref),
                });
                if (!verdict.ok) {
                  core.setFailed(verdict.message);
                  return;
                }
                core.notice(verdict.message);
                return;
              }
              // Anyone else's release/* branch: the ordinary rules, label included.
            }

            if (pr.labels.some((label) => label.name === 'no-changelog')) {
              core.notice("Labelled 'no-changelog'.");
              return;
            }

            // Both sides come from the API rather than from the checkout. On a
            // pull_request event the checkout is the merge commit, and comparing
            // against a base that is not in a shallow clone needs fetch-depth: 0.
            const readOptional = async (path, ref) => {
              try {
                const { data } = await github.rest.repos.getContent({ owner, repo, path, ref });
                return Buffer.from(data.content, 'base64').toString('utf8');
              } catch (error) {
                if (error.status === 404) return null;
                throw error;
              }
            };

            const verdict = changes.gateVerdict(
              await readOptional('CHANGES.md', pr.base.sha),
              await readOptional('CHANGES.md', pr.head.sha),
            );
            if (!verdict.ok) {
              core.setFailed(verdict.message);
              return;
            }

            core.notice(verdict.message);
```

Set `manifest.json` `changelog` to `"version": 4`.

- [ ] **Step 4: Re-render, run, commit**

Re-render, then `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests/test_changelog_gate.py tests/test_self_render.py tests/test_blocks.py tests/test_manifest.py 2>&1 | tail -3` (all pass), then the Full gate.

```bash
git add skills/repo-infra/assets/workflows/changelog.yml skills/repo-infra/assets/manifest.json tests/test_changelog_gate.py .github/workflows/changelog.yml
git commit -m "changelog v4: release mode for every repository, from the base library (D28)

A release pull request passes only when its head carries release-built
and is not behind main, the same verdict ci-passed gives. The
release_build switch and its exemption are gone.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
## Phase 3: the release workflow

### Task 4: one `release-pr.yml` (v5); the variant is removed

**Files:**
- Rewrite: `skills/repo-infra/assets/workflows/release-pr.yml` (whole file below)
- Delete: `skills/repo-infra/assets/workflows/release-pr-build.yml`
- Modify: `skills/repo-infra/assets/manifest.json:3-14` (`release-pr` `"version": 5`; the `release-pr-build` entry removed)
- Modify: `skills/repo-infra/scripts/repo_infra/assemble.py:204-257` (`render_all`: the `release_build` argument and the variant selection removed)
- Modify: `skills/repo-infra/scripts/repo_infra/state.py:143-151,171-175` (sibling markers removed)
- Modify: `skills/repo-infra/scripts/repo_infra/apply.py:204-213` (variant-switch base removed)
- Modify: `skills/repo-infra/scripts/repo_infra/cli.py:70-74` (no `release_build=` argument)
- Create: `tests/test_release_pr.py`
- Rename and trim: `tests/test_release_build.py` -> `tests/test_release_contracts.py`
- Delete: `tests/test_variant_switch.py`
- Modify: `tests/test_release_guard.py`
- Modify (re-render): `.github/workflows/release-pr.yml`

**Interfaces:**
- Consumes: `guardVerdict`, `checkState`, `guardIgnoreIds` (checks.js); `blockingReleasePr`, `untaggedRelease`, `untaggedMessage`, `staleDrafts`, `parkedRuns`, `refusedReleaseFiles`, `undeclaredReleaseFiles`, `decodeText`, `ownDrafts`, `finishVerdict`, `BUILD_RECORD` (release.js); `ci.yml`'s `workflow_call` input `ref` (Task 2).
- Produces: `render_all(assets_root, result, manifest, publish=(), build=(), ci=(), publish_local=(), ci_local=False)` (Task 5 adds two keyword arguments); `release-build.json` = `{version, base, head, assets}`; `prepare` outputs `version`, `date`, `head`, `base`.

The workflow calls `./.github/workflows/release-build.yml`, which Task 5 assembles. Between the two commits repo-infra's own `release-pr.yml` names a file that does not exist yet; nothing dispatches it on this branch.

- [ ] **Step 1: Write the failing tests** (`tests/test_release_pr.py`)

```python
"""release-pr v5 (D28): one release flow, built and tested before the merge."""

import json
import pathlib

import yaml

from repo_infra.assemble import render_all
from repo_infra.detect import Detection
from repo_infra.markers import parse_markers

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
ASSET = ASSETS / "workflows/release-pr.yml"
REPO_INFRA = ROOT / "skills/repo-infra/scripts/repo_infra"


def workflow():
    return yaml.safe_load(ASSET.read_text(encoding="utf-8"))


def script(job, step_name):
    steps = workflow()["jobs"][job]["steps"]
    return next(s["with"]["script"] for s in steps if s.get("name") == step_name)


FINISH = "Commit the release files, draft the release, open the pull request"
REFUSE = "Refuse an open or unpublished release; delete stale drafts and parked runs"


def test_four_jobs_build_and_test_beside_each_other():
    jobs = workflow()["jobs"]
    assert list(jobs) == ["prepare", "build", "test", "finish"]
    assert jobs["build"]["needs"] == "prepare" and jobs["test"]["needs"] == "prepare"
    assert jobs["finish"]["needs"] == ["prepare", "build", "test"]


def test_build_calls_the_assembled_release_build_with_the_secrets():
    build = workflow()["jobs"]["build"]
    assert build["uses"] == "./.github/workflows/release-build.yml"
    assert build["permissions"] == {"contents": "read"}
    assert build["secrets"] == "inherit"
    assert build["with"] == {"version": "${{ needs.prepare.outputs.version }}",
                             "ref": "${{ needs.prepare.outputs.head }}"}


def test_test_calls_ci_yml_on_the_release_branch_with_the_union_of_permissions():
    test = workflow()["jobs"]["test"]
    assert test["uses"] == "./.github/workflows/ci.yml"
    assert test["with"] == {"ref": "${{ needs.prepare.outputs.head }}"}
    assert test["secrets"] == "inherit"
    assert test["permissions"] == {"contents": "read", "pull-requests": "read",
                                   "statuses": "read", "checks": "write"}


def test_the_union_covers_every_permission_ci_yml_asks_for(tmp_path):
    (tmp_path / "action.yml").write_text("name: x\n")
    result = Detection.load(ASSETS / "detection.json").detect(tmp_path)
    ci = yaml.safe_load(render_all(ASSETS, result, MANIFEST, ci_local=True)[
        ".github/workflows/ci.yml"])
    granted = workflow()["jobs"]["test"]["permissions"]
    rank = {"read": 1, "write": 2}
    for perms in [ci["permissions"]] + [j.get("permissions", {}) for j in ci["jobs"].values()]:
        for scope, level in perms.items():
            assert scope in granted and rank[granted[scope]] >= rank[level], (scope, level)


def test_permissions_per_job():
    wf = workflow()
    assert wf["permissions"]["checks"] == "read" and wf["permissions"]["actions"] == "read"
    assert wf["jobs"]["prepare"]["permissions"]["actions"] == "write"
    assert wf["jobs"]["finish"]["permissions"] == {
        "contents": "write", "pull-requests": "write", "statuses": "write", "checks": "write"}


def test_prepare_outputs_the_dispatched_main_commit_as_base():
    outputs = workflow()["jobs"]["prepare"]["outputs"]
    assert outputs["base"] == "${{ steps.commit.outputs.base }}"
    assert "core.setOutput('base', context.sha)" in script("prepare", "Commit the release branch")


def test_the_guard_does_not_wait():
    guard = script("prepare", "Guard (right branch, no failed check)")
    assert "checks.guardVerdict(state)" in guard
    for gone in ("waitForChecks", "timedOut", "No checks ran"):
        assert gone not in guard


def test_prepare_refuses_then_cleans_up_before_it_writes_anything():
    steps = [s.get("name") for s in workflow()["jobs"]["prepare"]["steps"]]
    assert steps.index(REFUSE) < steps.index("Compute the version and rewrite the files")
    refuse = script("prepare", REFUSE)
    assert refuse.index("blockingReleasePr") < refuse.index("untaggedMessage") \
        < refuse.index("staleDrafts") < refuse.index("parkedRuns")
    assert "deleteWorkflowRun" in refuse and "core.warning" in refuse
    assert "Re-run the failed jobs" not in refuse


def test_finish_checks_everything_before_it_creates_the_draft():
    s = script("finish", FINISH)
    for guard in ("refusedReleaseFiles", "undeclaredReleaseFiles", "decodeText", "missingAssets"):
        assert s.index(guard) < s.index("createRelease"), guard


def test_finish_records_base_and_head_in_the_build_record():
    assert "{ version, base, head, assets: assetNames }" in script("finish", FINISH)


def test_finish_opens_the_pull_request_before_it_judges_it_against_main():
    s = script("finish", FINISH)
    assert s.index("createRelease") < s.index("'release-built'") \
        < s.index("name: 'changelog-updated'") < s.index("pulls.create") \
        < s.index("compareCommitsWithBasehead") < s.index("finishVerdict") \
        < s.index("name: 'ci-passed'")
    assert "target_commitish: head" in s


def test_finish_downloads_both_artifact_kinds():
    steps = workflow()["jobs"]["finish"]["steps"]
    patterns = [s["with"]["pattern"] for s in steps
                if s.get("uses", "").startswith("actions/download-artifact@")]
    assert patterns == ["release-asset-*", "release-files"]


def test_the_rust_lockfile_note_survives():
    assert "detection lists Cargo.lock in version_files" in ASSET.read_text(encoding="utf-8")


def test_the_variant_is_gone():
    assert "release-pr-build" not in MANIFEST["assets"]
    assert not (ASSETS / "workflows/release-pr-build.yml").exists()
    for spec in MANIFEST["assets"].values():
        assert "variant_of" not in spec and "when" not in spec
    for module in ("assemble.py", "state.py", "apply.py", "cli.py"):
        text = (REPO_INFRA / module).read_text(encoding="utf-8")
        assert "variant" not in text, module
    assert [m.asset for m in parse_markers(ASSET.read_text(encoding="utf-8"))] == ["release-pr"]
```


Rewrite `tests/test_release_guard.py` lines 100-103 and 122-127:

```python
def test_the_guard_gathers_its_ignore_ids_through_the_tested_function(workflow):
    assert "checks.guardIgnoreIds(github, {" in workflow
    assert "{ ignoreCheckRunIds }" in workflow, "the gathered ids must reach checkState"
    assert "guardIgnoreIds" in CHECKS_JS.read_text(encoding="utf-8")


def test_the_workflow_may_read_the_actions_api(workflow):
    """Listing this workflow's runs and their jobs is `actions: read`; prepare
    also deletes parked runs, which is `actions: write` on that job (D28)."""
    permissions = workflow.split("permissions:", 1)[1].split("\njobs:", 1)[0]
    assert "actions: read" in permissions
```

Rename and trim the D26 test file:

```bash
git mv tests/test_release_build.py tests/test_release_contracts.py
git rm -q tests/test_variant_switch.py
```

In `tests/test_release_contracts.py` delete `VARIANT`, `workflow()`, `script()` and every test from `test_release_build_selects_the_variant_for_the_same_target` through `test_the_rust_lockfile_note_survives_in_the_variant` (lines 18-115); drop the now unused imports (`AssemblyError`, `render_all`, `parse_markers`, `yaml`; keep `pytest`, `json`, `pathlib`, `Detection`, `classify_contracts`, `refused_release_files`). Set its docstring to `"""check's release contracts: release_files, release-build-local, Gitea config."""`. The remaining contract tests change in Task 8.

- [ ] **Step 2: Run them to see them fail**

Run: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests/test_release_pr.py tests/test_release_guard.py tests/test_release_contracts.py 2>&1 | tail -5`
Expected: failures (`['prepare'] != [...]`, `release-pr-build` still in the manifest, `variant` found in `assemble.py`).

- [ ] **Step 3: Write `release-pr.yml` v5** (whole file)

```yaml
name: Create release PR
# repo-infra: release-pr v5
#
# One release flow for every repository (D28). The release is built and
# tested on the release branch before the pull request exists, so the pull
# request can be merged at once:
#
#   prepare  guard, refusals, stale drafts and parked runs, roll, bump,
#            commit the release branch
#   build    .github/workflows/release-build.yml (assembled; the project's
#            own build jobs live in release-build-local.yml)
#   test     .github/workflows/ci.yml on the release branch, beside build
#   finish   commit the declared release files, draft the release, mark the
#            head, write the two required checks, open the pull request,
#            then judge it against main
#
# main is protected and GITHUB_TOKEN cannot be given a ruleset bypass: the
# bypass list takes users, teams and GitHub Apps, and the Actions token is
# none of those. So the release still lands through a pull request. Merging
# it triggers release-publish.yml.

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
  # The guard reads the check runs on the dispatched commit, and the job ids
  # of this workflow's runs on it: this run, so the guard can exclude itself,
  # and every earlier attempt, whose failed build and test jobs sit on the
  # same commit.
  checks: read
  actions: read
  statuses: write

jobs:
  prepare:
    name: Prepare the release branch
    runs-on: ubuntu-latest
    timeout-minutes: 15
    permissions:
      contents: write
      pull-requests: read
      checks: read
      # Deleting the parked runs of abandoned release branches.
      actions: write
    outputs:
      version: ${{ steps.prepare.outputs.version }}
      date: ${{ steps.prepare.outputs.date }}
      head: ${{ steps.commit.outputs.head }}
      base: ${{ steps.commit.outputs.base }}
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-node@v7
        with:
          node-version: 22

      - name: Guard (right branch, no failed check)
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

            // The guard does not wait (D28): the test job runs the same
            // ci.yml on this commit plus the release changes, and finish
            // opens no pull request unless it is green. A check that already
            // failed here is refused by name. This workflow's own jobs, and
            // the build and test jobs of every earlier attempt, are check
            // runs on this same commit; checks.js:guardIgnoreIds drops them
            // all, or one failed attempt would block every retry.
            const ignoreCheckRunIds = await checks.guardIgnoreIds(github, {
              owner: context.repo.owner,
              repo: context.repo.repo,
              ref: context.sha,
              workflowRef: process.env.GITHUB_WORKFLOW_REF,
              runId: context.runId,
            });
            const state = await checks.checkState(github, {
              owner: context.repo.owner,
              repo: context.repo.repo,
              ref: context.sha,
            }, { ignoreCheckRunIds });
            const refusal = checks.guardVerdict(state);
            if (refusal) {
              core.setFailed(refusal);
              return;
            }
            core.notice(`No failed check on ${context.sha}.`);

      - name: Refuse an open or unpublished release; delete stale drafts and parked runs
        uses: actions/github-script@v9
        with:
          script: |
            const fs = require('fs');
            const ws = process.env.GITHUB_WORKSPACE;
            const lib = `${ws}/.github/workflows/lib`;
            const releaseLib = require(`${lib}/release.js`);
            const changesLib = require(`${lib}/changes.js`);
            const owner = context.repo.owner;
            const repo = context.repo.repo;

            // A second dispatch would force-move the open pull request's branch
            // under its reviewers.
            const prs = await github.paginate(github.rest.pulls.list, {
              owner, repo, state: 'open', per_page: 100,
            });
            const blocking = releaseLib.blockingReleasePr(prs, `${owner}/${repo}`);
            if (blocking) {
              core.setFailed(
                `Release pull request #${blocking.number} (${blocking.head.ref}) is `
                + 'still open. Merge or close it before dispatching again.'
              );
              return;
            }

            // Without this, a dispatch while publish is running or has failed
            // computes the same version again and roll writes a second heading.
            const refs = await github.paginate(github.rest.git.listMatchingRefs, {
              owner, repo, ref: 'tags/v', per_page: 100,
            });
            const tags = refs.map((r) => r.ref.replace('refs/tags/', ''));
            const latest = changesLib.latestRelease(
              fs.readFileSync(`${ws}/CHANGES.md`, 'utf8'),
            );
            const untagged = releaseLib.untaggedRelease(latest, tags);
            if (untagged) {
              core.setFailed(releaseLib.untaggedMessage(untagged));
              return;
            }

            const releases = await github.paginate(github.rest.repos.listReleases, {
              owner, repo, per_page: 100,
            });
            const stale = releaseLib.staleDrafts(releases, {
              tags, latestVersion: latest && latest.version,
            });
            for (const draft of stale) {
              await github.rest.repos.deleteRelease({ owner, repo, release_id: draft.id });
              core.notice(`Deleted the stale draft release ${draft.tag_name}.`);
            }

            // The parked pull_request runs of abandoned release branches. No
            // release pull request is open at this point (refused above), so
            // every parked release run belongs to a closed one. A failure here
            // is a warning: the runs are clutter, not state.
            try {
              const runs = await github.paginate(github.rest.actions.listWorkflowRunsForRepo, {
                owner, repo, event: 'pull_request', status: 'action_required', per_page: 100,
              });
              for (const run of releaseLib.parkedRuns(runs, { fullName: `${owner}/${repo}` })) {
                await github.rest.actions.deleteWorkflowRun({ owner, repo, run_id: run.id });
                core.notice(`Deleted the parked run ${run.id} of ${run.head_branch}.`);
              }
            } catch (error) {
              core.warning(`Could not delete parked runs of closed release branches: ${error.message}`);
            }

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

            const fileIO = {
              read: (p) => fs.readFileSync(path.join(ws, p), 'utf8'),
              write: (p, c) => fs.writeFileSync(path.join(ws, p), c, 'utf8'),
            };

            const date = new Date().toISOString().slice(0, 10);
            // roll throws when [Unreleased] is empty, which is the hard backstop
            // behind the required changelog gate.
            fileIO.write('CHANGES.md', changesLib.roll(fileIO.read('CHANGES.md'), version, date));
            bumpLib.bumpAll(config.version_files, version, fileIO);

            core.setOutput('version', version);
            core.setOutput('date', date);
            core.notice(`Preparing ${latest} -> v${version} (${date}).`);

      # A lockfile that only its own tool can rewrite gets that tool as a step
      # here, between the rewrite and the commit; repo-infra has none. The
      # commit below takes exactly CHANGES.md and the version_files paths, so
      # such a step only lands if its file is listed there. Rust needs no step:
      # detection lists Cargo.lock in version_files, with one regex per crate.

      - name: Commit the release branch
        id: commit
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
            const paths = ['CHANGES.md', ...config.version_files.map((f) => f.path)];
            const head = await commitLib.commitFiles(github, {
              owner: context.repo.owner,
              repo: context.repo.repo,
              branch: `release/v${version}`,
              baseSha: context.sha,
              message: `Release v${version}`,
              files: paths.map((p) => ({
                path: p, content: fs.readFileSync(path.join(ws, p), 'utf8'),
              })),
            });
            core.setOutput('head', head);
            core.setOutput('base', context.sha);

  # The assembled build (D28): add-ons from "release_build" and the project's
  # own release-build-local.yml. The `uses:` path resolves at the dispatched
  # commit on main. contents: read, so its one way to write the repository is
  # the release-files artifact, which `finish` checks against release_files.
  # It gets the secrets: a build that signs a binary needs its key. No
  # repository secret may carry write access to the repository
  # (references/conventions.md).
  build:
    needs: prepare
    permissions:
      contents: read
    uses: ./.github/workflows/release-build.yml
    with:
      version: ${{ needs.prepare.outputs.version }}
      ref: ${{ needs.prepare.outputs.head }}
    secrets: inherit

  # The same ci.yml every pull request runs, on the release branch, beside
  # build. GitHub checks the permissions of every job of the called file,
  # skipped or not, so this grants the union of what ci.yml's jobs ask for.
  test:
    needs: prepare
    permissions:
      contents: read
      pull-requests: read
      statuses: read
      checks: write
    uses: ./.github/workflows/ci.yml
    with:
      ref: ${{ needs.prepare.outputs.head }}
    secrets: inherit

  finish:
    name: Draft the release and open the pull request
    needs: [prepare, build, test]
    runs-on: ubuntu-latest
    timeout-minutes: 30
    permissions:
      contents: write
      pull-requests: write
      statuses: write
      # The two required checks on the head: changelog-updated and ci-passed.
      checks: write
    steps:
      - uses: actions/checkout@v7

      # A called workflow's jobs belong to this run, so their artifacts are
      # found here by pattern.
      - uses: actions/download-artifact@v8
        with:
          pattern: release-asset-*
          path: ${{ runner.temp }}/assets
          merge-multiple: true

      - uses: actions/download-artifact@v8
        with:
          pattern: release-files
          path: ${{ runner.temp }}/release-files
          merge-multiple: true

      - name: Commit the release files, draft the release, open the pull request
        uses: actions/github-script@v9
        with:
          script: |
            const fs = require('fs');
            const path = require('path');
            const ws = process.env.GITHUB_WORKSPACE;
            const tmp = process.env.RUNNER_TEMP;
            const lib = `${ws}/.github/workflows/lib`;
            const releaseLib = require(`${lib}/release.js`);
            const assetsLib = require(`${lib}/assets.js`);
            const changesLib = require(`${lib}/changes.js`);
            const commitLib = require(`${lib}/commit.js`);
            const owner = context.repo.owner;
            const repo = context.repo.repo;
            const config = JSON.parse(
              fs.readFileSync(`${ws}/.github/repo-infra.json`, 'utf8')
            );
            const version = '${{ needs.prepare.outputs.version }}';
            const date = '${{ needs.prepare.outputs.date }}';
            const prepared = '${{ needs.prepare.outputs.head }}';
            const base = '${{ needs.prepare.outputs.base }}';
            const tag = `v${version}`;
            const branch = `release/${tag}`;

            // 1. The declared list itself, again: this reads it from the
            //    dispatched main, whether or not anyone ran `check`.
            const declared = config.release_files || [];
            const refused = releaseLib.refusedReleaseFiles(declared, config.version_files);
            if (refused.length > 0) {
              core.setFailed('release_files in .github/repo-infra.json: '
                + refused.map((r) => `${r.path} ${r.reason}`).join('; '));
              return;
            }

            // 2. What the build wrote back: declared paths, UTF-8 text only.
            const walk = (dir, prefix = '') => (fs.existsSync(dir)
              ? fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory()
                ? walk(path.join(dir, e.name), `${prefix}${e.name}/`)
                : [`${prefix}${e.name}`]))
              : []);
            const filesDir = `${tmp}/release-files`;
            const written = walk(filesDir);
            const undeclared = releaseLib.undeclaredReleaseFiles(written, declared);
            if (undeclared.length > 0) {
              core.setFailed(`release-build.yml wrote ${undeclared.join(', ')}, which `
                + 'release_files in .github/repo-infra.json does not list.');
              return;
            }
            const files = [];
            for (const p of written) {
              const content = releaseLib.decodeText(fs.readFileSync(path.join(filesDir, p)));
              if (content === null) {
                core.setFailed(`release-build.yml wrote ${p}, which is not UTF-8 text.`);
                return;
              }
              files.push({ path: p, content });
            }

            // 3. What the build produced, against what the release must carry.
            //    Declared independently of the build, so a build that drops a
            //    file cannot shrink the list along with it.
            const assetDir = `${tmp}/assets`;
            const assetNames = fs.existsSync(assetDir)
              ? fs.readdirSync(assetDir).filter((n) => fs.statSync(path.join(assetDir, n)).isFile())
              : [];
            const missing = assetsLib.missingAssets(assetNames, config.release_assets || []);
            if (missing.length > 0) {
              core.setFailed(`The build produced nothing for ${missing.join(', ')} `
                + `(release_assets). Built: ${assetNames.join(', ') || 'nothing'}.`);
              return;
            }
            if (assetNames.includes(releaseLib.BUILD_RECORD)) {
              core.setFailed(`The build produced a file named ${releaseLib.BUILD_RECORD}; `
                + 'that name is reserved.');
              return;
            }

            // 4. The built files land on the branch before the pull request
            //    exists.
            let head = prepared;
            if (files.length > 0) {
              head = await commitLib.commitFiles(github, {
                owner, repo, branch, baseSha: prepared,
                message: `Release ${tag}: built files`, files,
              });
            }

            // 5. A draft for this version with a build record belongs to an
            //    abandoned attempt: prepare passed both refusals.
            const releases = await github.paginate(github.rest.repos.listReleases, {
              owner, repo, per_page: 100,
            });
            for (const old of releaseLib.ownDrafts(releases, version)) {
              await github.rest.repos.deleteRelease({ owner, repo, release_id: old.id });
            }
            const { data: rolled } = await github.rest.repos.getContent({
              owner, repo, path: 'CHANGES.md', ref: head,
            });
            const { data: draft } = await github.rest.repos.createRelease({
              owner, repo,
              tag_name: tag,
              target_commitish: head,
              name: tag,
              body: changesLib.notesFor(
                Buffer.from(rolled.content, 'base64').toString('utf8'), version,
              ),
              draft: true,
              prerelease: false,
              make_latest: 'true',
            });
            const upload = (name, data, type) => github.rest.repos.uploadReleaseAsset({
              owner, repo, release_id: draft.id, name, data,
              headers: { 'content-type': type, 'content-length': data.length },
            });
            for (const name of assetNames) {
              await upload(name, fs.readFileSync(path.join(assetDir, name)),
                'application/octet-stream');
            }
            await upload(releaseLib.BUILD_RECORD,
              Buffer.from(JSON.stringify({ version, base, head, assets: assetNames }, null, 2)),
              'application/json');

            // 6. The release-mode gates read this status. A later push to the
            //    branch is a new commit without it.
            await github.rest.repos.createCommitStatus({
              owner, repo, sha: head, state: 'success', context: 'release-built',
              description: `${tag} built and tested`,
            });

            // 7. The ruleset requires its two contexts without naming an app,
            //    so check runs written here satisfy it. The pull request's own
            //    pull_request runs park; nobody needs to approve them.
            await github.rest.checks.create({
              owner, repo, name: 'changelog-updated', head_sha: head,
              status: 'completed', conclusion: 'success',
              output: { title: `${tag} rolls CHANGES.md`,
                summary: 'Create release PR rolled [Unreleased] into this version.' },
            });

            const body = [
              'Prepared by the **Create release PR** workflow.',
              '',
              `- rolls \`CHANGES.md\` \`[Unreleased]\` into \`## ${version} - ${date}\``,
              `- sets ${config.version_files.map((f) => `\`${f.path}\``).join(', ')} to \`${version}\``,
              ...(files.length > 0
                ? [`- writes ${files.map((f) => `\`${f.path}\``).join(', ')} from the build`]
                : []),
              `- built ${assetNames.length} files into a draft release for \`${tag}\``,
              '- ran this repository\'s CI on the release branch before this pull request was opened',
              '',
              'Review, then merge; nothing needs approving. Merging triggers **Publish',
              `release**, which tags the built commit \`${head.slice(0, 12)}\` as \`${tag}\``,
              'and publishes the draft. Merge with a merge commit if you can.',
              '',
              'If main moves before the merge, this pull request cannot be merged: close',
              'it and dispatch Create release PR again. Do not press **Update branch**.',
            ].join('\n');
            const { data: pr } = await github.rest.pulls.create({
              owner, repo,
              head: branch,
              base: context.payload.repository.default_branch,
              title: `Release ${tag}`,
              body,
            });
            core.notice(`Release pull request opened: ${pr.html_url}`);

            // 8. Opened first, so a release that went stale while it built is
            //    visible and says why.
            const { data: compared } = await github.rest.repos.compareCommitsWithBasehead({
              owner, repo, basehead: `${context.payload.repository.default_branch}...${head}`,
            });
            const verdict = releaseLib.finishVerdict({ behindBy: compared.behind_by, tag });
            await github.rest.checks.create({
              owner, repo, name: 'ci-passed', head_sha: head,
              status: 'completed', conclusion: verdict.conclusion,
              output: { title: verdict.title, summary: verdict.summary },
            });
            if (verdict.conclusion !== 'success') {
              core.setFailed(`${pr.html_url}: ${verdict.summary}`);
              return;
            }
            await core.summary
              .addHeading(`Release ${tag} built and tested`)
              .addLink('Review and merge to publish', pr.html_url)
              .write();
```

`finish` fails after opening a stale pull request, so the dispatcher sees a red run that names it. `guardIgnoreIds` drops that failed job on the next dispatch from the same commit.

- [ ] **Step 4: Remove the variant**

```bash
git rm -q skills/repo-infra/assets/workflows/release-pr-build.yml
```

`manifest.json`: delete the `"release-pr-build": {...}` entry (lines 8-14) and set `release-pr` to `"version": 5`.

`assemble.py`, `render_all`: signature `def render_all(assets_root, result, manifest, publish=(), build=(), ci=(), publish_local=(), ci_local=False):`; delete lines 230-243 (the selection) and the docstring's last sentence ``"`release_build` selects the `release-pr-build` variant (D26)."``; the loop becomes:

```python
    files = {}
    for name, spec in manifest["assets"].items():
        source = assets_root / spec["source"]
```

`state.py`, `classify_files`: delete the comment and the `siblings` dict (lines 145-151) and the `elif have is None and siblings.get(...)` branch (lines 171-175).

`apply.py` lines 204-213 become:

```python
    # outdated
    installed = (pathlib.Path(repo_root) / path).read_text(encoding="utf-8")
    found = parse_markers(installed)
    source = _asset_source(plugin_root, found[0].asset)
    base = base_version_of(plugin_root, source, found[0].version) if source else None
```

`cli.py` `_load`: drop the `release_build=bool(config.get("release_build"))` argument (line 74) and the now unused `config = _config(root)` line if nothing else in `_load` reads it.

- [ ] **Step 5: Run, re-render, gate**

Run: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests/test_release_pr.py tests/test_release_guard.py tests/test_release_contracts.py tests/test_manifest.py tests/test_state.py tests/test_apply_files.py tests/test_cli.py 2>&1 | tail -3` (all pass). Re-render; `git status --short .github` shows only `release-pr.yml` modified. Full gate: report the counts; the delta is +14 (`test_release_pr.py`) -4 (`test_variant_switch.py`) -11 (the variant and workflow tests removed from the old `test_release_build.py`), net -1.

- [ ] **Step 6: Commit**

```bash
git add -A skills/repo-infra tests .github/workflows/release-pr.yml
git commit -m "release-pr v5: one flow, built and tested before the pull request (D28)

prepare, build and test, then finish writes changelog-updated, opens
the pull request and writes ci-passed by comparing the head with main.
The guard no longer waits. The release-pr-build variant, its manifest
selection and the variant switch in check and apply are removed: they
never shipped.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `release-build.yml` is assembled; `release-source-tarball` replaces `publish-source-tarball`

**Files:**
- Create: `skills/repo-infra/assets/release-build/release-build-frame.yml`, `release-source-tarball.yml`, `release-build-local.yml`
- Delete: `skills/repo-infra/assets/publish/publish-source-tarball.yml`
- Modify: `skills/repo-infra/assets/manifest.json` (new `release_build_blocks`; `publish-source-tarball` removed from `publish_blocks`; `actions` gains `"actions/upload-artifact": "v7"`)
- Modify: `skills/repo-infra/scripts/repo_infra/assemble.py` (module docstring; `release_build_addon_blocks`, `assemble_release_build`; `render_all` gains `release_build=()`, `release_build_local=False`)
- Modify: `skills/repo-infra/scripts/repo_infra/cli.py:70-74`
- Create: `tests/test_release_build_assembly.py`
- Modify: `tests/test_manifest.py:235`, `tests/test_blocks.py:153-157`, `tests/test_publish.py` (tarball tests out, local-job tests onto `publish-crates-io`), `tests/test_publish_build.py:203`
- Create (re-render): `.github/workflows/release-build.yml`

**Interfaces:**
- Consumes: nothing new.
- Produces: `assemble_release_build(assets_root, addons, manifest, local=False) -> str`; `render_all(..., ci_local=False, release_build=(), release_build_local=False)`; manifest `release_build_blocks[name] = {"version", "jobs", "assets", "seam"?}` (Task 8 reads `assets`).

- [ ] **Step 1: Write the failing tests** (`tests/test_release_build_assembly.py`)

```python
"""release-build.yml, the third assembled file (D28)."""

import json
import pathlib

import pytest
import yaml

from repo_infra import cli
from repo_infra.assemble import AssemblyError, assemble_release_build, render_all
from repo_infra.detect import Detection
from repo_infra.markers import parse_markers

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
TARGET = ".github/workflows/release-build.yml"
REF = "${{ inputs.ref }}"


def doc(addons=(), local=False):
    return yaml.safe_load(assemble_release_build(ASSETS, list(addons), MANIFEST, local))


def on(d):
    return d.get("on", d.get(True))


def test_every_repository_gets_a_valid_release_build(tmp_path):
    result = Detection.load(ASSETS / "detection.json").detect(tmp_path)
    files = render_all(ASSETS, result, MANIFEST)
    d = yaml.safe_load(files[TARGET])
    assert on(d) == {"workflow_call": {"inputs": {
        "version": {"type": "string", "required": True},
        "ref": {"type": "string", "required": True}}}}
    assert d["permissions"] == {"contents": "read"}
    assert list(d["jobs"]) == ["release-version"]
    assert [m.asset for m in parse_markers(files[TARGET])] == ["release-build"]


def test_the_tarball_add_on_lands_after_the_frame_with_its_marker():
    text = assemble_release_build(ASSETS, ["release-source-tarball"], MANIFEST)
    assert [(m.asset, m.version) for m in parse_markers(text)] == [
        ("release-build", 1), ("release-source-tarball", 1)]
    assert list(yaml.safe_load(text)["jobs"]) == ["release-version", "release-source-tarball"]


def test_the_tarball_add_on_builds_at_ref_and_uploads_a_release_asset():
    job = doc(["release-source-tarball"])["jobs"]["release-source-tarball"]
    checkout = job["steps"][0]
    assert checkout["uses"] == "actions/checkout@v7" and checkout["with"] == {"ref": REF}
    runs = [s.get("run", "") for s in job["steps"]]
    assert "./bootstrap" in runs and "./configure" in runs
    assert any("make dist" in r for r in runs)
    upload = job["steps"][-1]
    assert upload["uses"].startswith("actions/upload-artifact@")
    assert upload["with"]["name"] == "release-asset-source"
    assert upload["with"]["if-no-files-found"] == "error"
    assert job["timeout-minutes"] == 30


def test_the_tarball_add_on_refuses_zero_or_two_tarballs():
    text = (ASSETS / "release-build/release-source-tarball.yml").read_text(encoding="utf-8")
    assert "make dist produced no tarball" in text
    assert "more than one tarball in the source root" in text


def test_the_local_seam_passes_version_ref_and_the_secrets():
    job = doc(local=True)["jobs"]["release-build-local"]
    assert job == {"uses": "./.github/workflows/release-build-local.yml",
                   "with": {"version": "${{ inputs.version }}", "ref": REF},
                   "secrets": "inherit"}


def test_add_ons_come_before_the_local_seam():
    jobs = list(doc(["release-source-tarball"], local=True)["jobs"])
    assert jobs == ["release-version", "release-source-tarball", "release-build-local"]


def test_every_build_block_declares_its_assets_and_jobs():
    from repo_infra.assemble import block_job_ids
    for name, meta in MANIFEST["release_build_blocks"].items():
        assert isinstance(meta.get("assets"), list), name
        text = (ASSETS / "release-build" / (name + ".yml")).read_text(encoding="utf-8")
        assert block_job_ids(text) == meta["jobs"], name
    assert MANIFEST["release_build_blocks"]["release-source-tarball"]["assets"] == ["*.tar.gz"]


@pytest.mark.parametrize("addons,match", [
    (["release-nothing"], "not declared in the manifest"),
    (["release-build-local"], '"release_build_local": true'),
    (["release-source-tarball", "release-source-tarball"], "named twice"),
    (True, "must be a list"),
])
def test_a_bad_release_build_value_is_an_assembly_error(addons, match):
    with pytest.raises(AssemblyError, match=match):
        assemble_release_build(ASSETS, addons, MANIFEST)


def test_publish_source_tarball_is_gone():
    assert "publish-source-tarball" not in MANIFEST["publish_blocks"]
    assert not (ASSETS / "publish/publish-source-tarball.yml").exists()


def test_load_reads_release_build_and_release_build_local(tmp_path):
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github/repo-infra.json").write_text(json.dumps(
        {"release_build": ["release-source-tarball"], "release_build_local": True}))
    _m, _r, rendered = cli._load(tmp_path)
    assert list(yaml.safe_load(rendered[TARGET])["jobs"]) == [
        "release-version", "release-source-tarball", "release-build-local"]
```

Edits to existing tests:
- `tests/test_manifest.py:235`: the key set gains `"release_build_blocks"`.
- `tests/test_blocks.py:156`: `"publish/publish-source-tarball.yml"` -> `"release-build/release-source-tarball.yml"`.
- `tests/test_publish.py`: delete `test_the_tarball_addon_lands_between_publish_and_finalize`, `test_the_tarball_addon_carries_its_marker`, `test_the_tarball_addon_declares_exactly_the_job_it_contains`, `test_the_tarball_addon_refuses_to_upload_nothing`, `test_the_tarball_block_can_drive_a_container` (lines 38-67), `_run_tarball_upload` and its two tests (lines 496-545). In the local-job tests use `publish-crates-io`: `needs == ["publish", "publish-crates-io", "publish-deb-container"]`; the collision test uses `["publish-crates-io"]` and `[{"job": "publish-crates-io", "assets": []}]`; `test_finalize_expects_the_assets_the_installed_blocks_attach` uses `addons=["publish-crates-io"]` and asserts `"['*.deb', 'smtp-proxy-*-musl']" in script`.
- `tests/test_publish_build.py:203`: parametrize over `["publish-crates-io", "publish-gitea-packages"]`.

- [ ] **Step 2: Run them to see them fail**

Run: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests/test_release_build_assembly.py 2>&1 | tail -3`
Expected: `ImportError: cannot import name 'assemble_release_build'`.

- [ ] **Step 3: The three blocks**

`skills/repo-infra/assets/release-build/release-build-frame.yml`:

```yaml
name: Release build
# repo-infra: release-build v1
#
# Called by Create release PR (release-pr.yml) on the release branch, before
# the pull request exists (D28). Assembled like ci.yml: this frame, one job
# block per add-on named in "release_build" in .github/repo-infra.json, and
# the project's own jobs through release-build-local.yml when
# "release_build_local" is set.
#
# Every file the release ships is an artifact whose name starts with
# release-asset-; the repository files the build rewrote are the artifact
# release-files. Both names are reserved for this workflow
# (references/conventions.md).

on:
  workflow_call:
    inputs:
      version:
        type: string
        required: true
      ref:
        type: string
        required: true

permissions:
  contents: read

jobs:
  # A repository with nothing to build still gets a valid file, and a release
  # without assets.
  release-version:
    name: Release version
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - run: echo "Building v${VERSION} from ${REF}"
        env:
          VERSION: ${{ inputs.version }}
          REF: ${{ inputs.ref }}
```

`skills/repo-infra/assets/release-build/release-source-tarball.yml`:

```yaml
  # The make dist tarball, built from the release branch before the merge.
  # These are publish-source-tarball's steps, moved in front of the merge
  # (D28); finish attaches the file to the draft.
  release-source-tarball:
    name: Build the source tarball
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ inputs.ref }}

      # `make dist` is a container call in a repository that converted to the
      # D18 driver, and a plain automake dist in one that did not. The same two
      # commands cover both, so long as the engine is here.
      - name: Install the autotools host toolchain
        run: |
          sudo apt-get update
          sudo apt-get install -y autoconf automake gettext podman

      - run: ./bootstrap

      - run: ./configure

      - name: Build the distribution tarball
        run: make dist

      # `make dist` names the tarball from AC_INIT, which is not necessarily the
      # repository name -- so find it rather than guess it. Exactly one is
      # expected; two means a stale tarball is committed and the upload would be
      # a coin toss.
      - name: Locate the tarball
        run: |
          set -euo pipefail
          mapfile -t found < <(find . -maxdepth 1 -name '*.tar.gz' -printf '%P\n' | sort)
          if [ "${#found[@]}" -eq 0 ]; then
            echo "make dist produced no tarball" >&2
            exit 1
          fi
          if [ "${#found[@]}" -gt 1 ]; then
            echo "more than one tarball in the source root: ${found[*]}" >&2
            echo "remove the committed ones; this job cannot tell which to upload" >&2
            exit 1
          fi
          if ! [[ "${found[0]}" =~ ^[A-Za-z0-9._+-]+\.tar\.gz$ ]]; then
            echo "unexpected tarball name: ${found[0]@Q}" >&2
            exit 1
          fi
          mkdir -p "$RUNNER_TEMP/release-asset-source"
          mv "${found[0]}" "$RUNNER_TEMP/release-asset-source/"

      - uses: actions/upload-artifact@v7
        with:
          name: release-asset-source
          path: ${{ runner.temp }}/release-asset-source/
          if-no-files-found: error
```

`skills/repo-infra/assets/release-build/release-build-local.yml`:

```yaml
  # The project brings the build, the standard brings the seam (D20's shape,
  # D28). .github/workflows/release-build-local.yml is the project's own file:
  # it triggers on workflow_call only with the inputs version and ref, checks
  # out ref in every actions/checkout, sets timeout-minutes on each of its
  # jobs, uploads each shipped file as a release-asset-* artifact and the
  # repository files it rewrote as release-files. references/conventions.md.
  release-build-local:
    uses: ./.github/workflows/release-build-local.yml
    with:
      version: ${{ inputs.version }}
      ref: ${{ inputs.ref }}
    secrets: inherit
```

```bash
git rm -q skills/repo-infra/assets/publish/publish-source-tarball.yml
```

Manifest: remove the `publish-source-tarball` entry from `publish_blocks`; after `publish_blocks` add

```json
  "release_build_blocks": {
    "release-source-tarball": {"version": 1, "jobs": ["release-source-tarball"],
                               "assets": ["*.tar.gz"]},
    "release-build-local": {"version": 1, "jobs": ["release-build-local"], "assets": [],
                            "seam": "release_build_local"}
  },
```

and add `"actions/upload-artifact": "v7",` after `"actions/download-artifact": "v8",` (v7 is the newest major tag of `actions/upload-artifact` on 2026-10-01; confirm with `git ls-remote --tags https://github.com/actions/upload-artifact | grep -o 'refs/tags/v[0-9]*$' | sort -V | tail -1`).

- [ ] **Step 4: The assembler** (`assemble.py`)

Module docstring, first paragraph: "Three files are assembled rather than copied: ci.yml, ...; release-publish.yml, ...; and release-build.yml (D28), from a frame, one job block per build add-on, and the project's own seam."

Add after `assemble_publish`:

```python
def release_build_addon_blocks(addons, manifest):
    """The build add-ons a repository named in "release_build" (D28)."""
    if not isinstance(addons, (list, tuple)):
        raise AssemblyError(
            '"release_build" in .github/repo-infra.json must be a list of build add-ons, '
            f"not {addons!r}")
    chosen = []
    for name in addons:
        meta = manifest["release_build_blocks"].get(name)
        if meta is None:
            raise AssemblyError(f"release_build add-on {name} is not declared in the manifest")
        if meta.get("seam"):
            raise AssemblyError(
                f"release_build add-on {name} is a seam; set \"{meta['seam']}\": true in "
                ".github/repo-infra.json instead of naming it")
        if name in chosen:
            raise AssemblyError(f"release_build add-on {name} is named twice")
        chosen.append(name)
    return chosen


def assemble_release_build(assets_root, addons, manifest, local=False):
    """release-build.yml: the frame, the build add-ons, then the local seam.

    No generated `needs:` list: Create release PR's finish job waits for the
    whole called workflow, and finish checks the artifacts against
    release_assets.
    """
    folder = pathlib.Path(assets_root) / "release-build"
    parts = [_read(folder / "release-build-frame.yml").rstrip("\n")]
    blocks = release_build_addon_blocks(addons, manifest)
    if local:
        blocks.append("release-build-local")
    for block in blocks:
        meta = manifest["release_build_blocks"][block]
        parts.append("")
        parts.append(markers.marker_line(block, meta["version"], indent="  "))
        parts.append(_read(folder / (block + ".yml")).rstrip("\n"))
    return "\n".join(parts) + "\n"
```

`render_all`: signature gains `release_build=(), release_build_local=False`; docstring gains "`release_build` names the build add-ons and `release_build_local` adds the project's own build seam (D28)."; before `return files`:

```python
    files[".github/workflows/release-build.yml"] = assemble_release_build(
        assets_root, release_build, manifest, release_build_local)
```

`cli.py` `_load`:

```python
    config = _config(root)
    rendered = render_all(ASSETS, result, manifest,
                          _chosen(root, "publish"), _chosen(root, "build"),
                          ci, _chosen(root, "publish_local"),
                          ci_local=bool(config.get("ci_local")),
                          release_build=config.get("release_build", []),
                          release_build_local=bool(config.get("release_build_local")))
```

- [ ] **Step 5: Run, re-render, gate**

Run the new test file and `tests/test_publish.py tests/test_publish_build.py tests/test_blocks.py tests/test_manifest.py`: all pass. Re-render; `git status --short .github` shows `?? .github/workflows/release-build.yml` (frame only, for repo-infra). Full gate; report counts (+13 new, -7 tarball tests in `test_publish.py`, net +6).

- [ ] **Step 6: Commit**

```bash
git add -A skills/repo-infra tests .github/workflows/release-build.yml
git commit -m "release-build.yml is assembled; release-source-tarball replaces publish-source-tarball (D28)

Every repository gets the file Create release PR calls: a frame, the
build add-ons named in release_build, and release-build-local.yml when
release_build_local is set. The make dist tarball is built before the
merge now and travels as release-asset-source.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
## Phase 4: publishing

### Task 6: publish v5: one path, tree comparison, parked runs; `publish-crates-io` v3

**Files:**
- Modify: `skills/repo-infra/assets/publish/publish-frame.yml:2,15-22,127-164` (marker v5, header, the non-`release_build` path out, tree comparison in)
- Modify: `skills/repo-infra/assets/publish/publish-finalize.yml:15-20,50-52` and a new last step
- Modify: `skills/repo-infra/assets/publish/publish-crates-io.yml:17-19,38-82,123-126`
- Modify: `skills/repo-infra/assets/manifest.json` (`publish-crates-io` `"version": 3`)
- Modify: `tests/test_publish_build.py` (harness: trees, pull requests; the non-`release_build` test out; tree tests in)
- Modify: `tests/test_publish.py` (frame marker 5, crates-io marker 3, reconcile tests out, finalize tests)
- Modify (re-render): `.github/workflows/release-publish.yml`

**Interfaces:**
- Consumes: `releasePrMergeCommit`, `treeVerdict`, `parkedRuns`, `BUILD_RECORD` (Task 1).
- Produces: nothing new for later tasks.

- [ ] **Step 1: Write the failing publish tests** (`tests/test_publish_build.py`)

Change the harness: `run()` loses the `release_build` parameter, writes `{"version_files": []}` as config, and gains `prs=None, trees=None` (defaults: one merged bot pull request from `release/v1.2.0` with `merge_commit_sha` `MERGE`, and equal trees for `HEAD` and `MERGE`):

```python
MERGE = "e" * 40


def merged_pr(sha=MERGE, ref="release/v1.2.0", login="github-actions[bot]"):
    return {"number": 9, "user": {"login": login}, "merged_at": "2026-10-01T10:00:00Z",
            "merge_commit_sha": sha, "head": {"ref": ref, "repo": {"full_name": "o/r"}}}
```

In `run()` add to `state`: `"prs": [merged_pr()] if prs is None else prs, "trees": {HEAD: "T", MERGE: "T"} if trees is None else trees`. In the JS fake, replace `getCommit` and add the pull request lookup:

```js
      getCommit: async (a) => { calls.push(['getCommit', a]);
        if (!state.headExists) throw notFound();
        return { data: { tree: { sha: state.trees[a.commit_sha] } } }; },
```

```js
      listPullRequestsAssociatedWithCommit: async (a) => {
        calls.push(['listPullRequestsAssociatedWithCommit', a]); return { data: state.prs }; },
```

(the second goes into `repos`). Delete `test_without_release_build_the_merge_commit_is_tagged_as_before`. Append:

```python
TREE_TEXT = (f"main at {MERGE} does not match the release built from {HEAD}; merge a pull "
             "request that moves the v1.2.0 entries in CHANGES.md back under [Unreleased], "
             "then dispatch Create release PR again")


def test_create_compares_the_release_pr_merge_commit_with_the_recorded_head(tmp_path):
    out = run(tmp_path, releases=[draft()], record={"head": HEAD})
    assert out["failures"] == []
    (lookup,) = called(out, "listPullRequestsAssociatedWithCommit")
    assert lookup["commit_sha"] == HEAD  # the recorded head, not context.sha
    assert {c["commit_sha"] for c in called(out, "getCommit")} >= {HEAD, MERGE}


def test_a_tree_mismatch_tags_nothing_and_names_the_way_out(tmp_path):
    out = run(tmp_path, releases=[draft()], record={"head": HEAD},
              trees={HEAD: "T", MERGE: "U"})
    assert out["failures"] == [TREE_TEXT]
    assert called(out, "createTag") == [] and called(out, "createRef") == []
    assert called(out, "updateRelease") == [] and out["outputs"] == {}


def test_a_squash_merge_with_the_same_tree_publishes(tmp_path):
    squash = "f" * 40
    out = run(tmp_path, releases=[draft()], record={"head": HEAD},
              prs=[merged_pr(sha=squash)], trees={HEAD: "T", squash: "T"},
              compare="diverged")
    assert out["failures"] == []
    assert [t["object"] for t in called(out, "createTag")] == [HEAD]


def test_no_merged_release_pull_request_tags_nothing(tmp_path):
    out = run(tmp_path, releases=[draft()], record={"head": HEAD}, prs=[])
    assert len(out["failures"]) == 1
    assert f"no merged release pull request contains {HEAD}" in out["failures"][0]
    assert called(out, "createTag") == []


def test_a_persons_merged_release_branch_is_not_the_release_pull_request(tmp_path):
    out = run(tmp_path, releases=[draft()], record={"head": HEAD},
              prs=[merged_pr(login="oetiker")])
    assert "no merged release pull request" in out["failures"][0]


def test_resume_never_compares_trees(tmp_path):
    out = run(tmp_path, tag=HEAD, releases=[draft()], record={"head": HEAD},
              trees={HEAD: "T", MERGE: "U"})
    assert out["failures"] == []
    assert called(out, "listPullRequestsAssociatedWithCommit") == []


def test_done_never_compares_trees(tmp_path):
    out = run(tmp_path, tag=HEAD, releases=[draft(record=False, published=True)],
              trees={HEAD: "T", MERGE: "U"})
    assert out["failures"] == [] and out["calls"] == []


def test_the_frame_has_one_path():
    assert "release_build" not in publish_script()


def test_publish_may_read_the_release_pull_request():
    # listPullRequestsAssociatedWithCommit needs pull-requests: read; the
    # workflow level grants nothing it does not name.
    assert workflow()["permissions"] == {"contents": "write", "pull-requests": "read"}
```

- [ ] **Step 2: Write the failing finalize and crates-io tests** (`tests/test_publish.py`)

- Line 23: `("release-publish", 5)`; line 103: `("publish-crates-io", 3)`.
- `_finalize_script`: `assert len(script) == 2` and `return script[0]` (the new step is a second github-script).
- `_build_workspace`: write `{"version_files": [], "release_assets": release_assets}` (no `release_build` key).
- Delete `test_the_lock_is_reconciled_before_the_publish_not_after`, `test_the_lock_reconciliation_moves_no_dependency`, `test_the_reconciled_lock_is_committed_before_packaging`, `test_the_reconcile_step_actually_leaves_the_tree_clean`.
- Append:

```python
def test_the_crates_io_addon_never_rewrites_the_lock():
    # The release pull request bumps Cargo.lock through version_files (D28).
    for run in (s.get("run", "") for s in _crates_io_job()["steps"]):
        assert "cargo update" not in _shell_code(run)
        assert "git" not in _shell_code(run).split()


def test_finalize_may_delete_runs():
    assert _finalize()["permissions"] == {"contents": "write", "actions": "write"}


def _parked_step():
    steps = _finalize()["steps"]
    return next(s for s in steps if s.get("name") == "Delete the parked runs of the release branch")


def _run_parked(tmp_path, runs, fail=False):
    import os
    import re
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = re.sub(r"\$\{\{[^}]*\}\}", "v1.2.3", _parked_step()["with"]["script"])
    harness = """
const runs = %s; const fail = %s; const deleted = []; const warnings = []; let listed;
const github = {
  paginate: async (fn, a) => { if (fail) throw new Error('Server Error'); listed = a; return runs; },
  rest: { actions: { listWorkflowRunsForRepo: 'list',
    deleteWorkflowRun: async (a) => { deleted.push(a.run_id); } } },
};
const core = { warning: (m) => warnings.push(m), setFailed: (m) => { throw new Error(m); } };
const context = { repo: { owner: 'o', repo: 'r' } };
(async () => {
%s
})().then(() => console.log(JSON.stringify({ deleted, warnings, listed })));
""" % (json.dumps(runs), "true" if fail else "false", script)
    path = tmp_path / "parked.js"
    path.write_text(harness, encoding="utf-8")
    proc = subprocess.run([node, str(path)], capture_output=True, text=True, cwd=ROOT,
                          env={"GITHUB_WORKSPACE": str(ROOT), "PATH": os.environ["PATH"]})
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _parked(id, branch, conclusion="action_required", repo="o/r"):
    return {"id": id, "event": "pull_request", "head_branch": branch, "status": "completed",
            "conclusion": conclusion, "head_repository": {"full_name": repo}}


def test_finalize_deletes_only_the_parked_runs_of_its_release_branch(tmp_path):
    out = _run_parked(tmp_path, [_parked(1, "release/v1.2.3"),
                                 _parked(2, "release/v1.2.3", conclusion="success"),
                                 _parked(3, "release/v1.2.2"),
                                 _parked(4, "release/v1.2.3", repo="fork/r")])
    assert out["deleted"] == [1]
    assert out["listed"]["branch"] == "release/v1.2.3"
    assert out["listed"]["event"] == "pull_request"


def test_a_failed_deletion_is_a_warning(tmp_path):
    out = _run_parked(tmp_path, [], fail=True)
    assert out["deleted"] == [] and "Server Error" in out["warnings"][0]


def test_finalize_asserts_release_assets_for_every_repository(tmp_path):
    ws = _build_workspace(tmp_path, ["*.tar.gz"])
    out = _run_finalize(tmp_path, ["x.deb"], local=(), workspace=ws)
    assert out["published"] == 0 and "*.tar.gz" in out["failures"][0]
```

- [ ] **Step 3: Run them to see them fail**

Run: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests/test_publish_build.py tests/test_publish.py 2>&1 | tail -5`
Expected: failures (`TREE_TEXT` not produced, marker 4 != 5, no `Delete the parked runs` step).

- [ ] **Step 4: The frame**

Marker line: `# repo-infra: release-publish v5`. The workflow-level `permissions:` becomes `contents: write` and `pull-requests: read` (the lookup of the release pull request below needs the second; the spec names only `actions: write`, which `finalize` gets). Replace header lines 15-22 with:

```yaml
# Recovery (D28): `publish` decides from the tag and the releases together
# (lib/publish.js), so **Re-run failed jobs** and a whole-workflow re-run both
# finish a stopped release: a whole-workflow re-run also repeats the add-ons
# that already succeeded, and each standard add-on skips what an earlier
# attempt uploaded. A `publish_local` job must do the same.
#
# Before it tags, publish compares the tree of the release pull request's
# merge commit with the tree of the head that was built. With the ruleset's
# up-to-date rule on they are equal; a mismatch tags nothing.
```

Delete the whole `if (!config.release_build) { ... }` block (lines 127-162) and the comment line `// release_build (D26): the release pull request built the release` / `// into a draft. Tag the commit that was built, not this merge.`, replacing the comment with `// The release pull request built the release into a draft (D26, D28).` / `// Tag the commit that was built, not this merge.`

In the `create` branch, between the `validateBuildRecord` check and `head = record.head;`, insert:

```js
              // D28: main must be the release that was built. The release pull
              // request's merge commit, found from the recorded head, not
              // context.sha: a failed first publish followed by an ordinary
              // merge starts a new run on a later commit.
              const { data: associated } = await github.rest.repos
                .listPullRequestsAssociatedWithCommit({ owner, repo, commit_sha: record.head });
              const mergeSha = releaseLib.releasePrMergeCommit(associated, {
                fullName: `${owner}/${repo}`, tag,
              });
              const treeOf = async (sha) => (await github.rest.git.getCommit({
                owner, repo, commit_sha: sha,
              })).data.tree.sha;
              const treeProblem = releaseLib.treeVerdict({
                tag,
                head: record.head,
                mergeSha,
                mergeTree: mergeSha ? await treeOf(mergeSha) : null,
                headTree: await treeOf(record.head),
              });
              if (treeProblem) {
                core.setFailed(treeProblem);
                return;
              }
```

- [ ] **Step 5: Finalize**

Job permissions:

```yaml
    permissions:
      contents: write
      # D28: deleting the parked pull_request runs of the release branch.
      actions: write
```

Lines 50-52 become:

```js
            // D26, D28: the release must carry every file the repository
            // declared, read at the tagged head.
            const declared = config.release_assets || [];
```

Append the step after the publishing step:

```yaml
      # The release pull request's own pull_request runs parked for an
      # approval nobody needed to give (D28). Nothing depends on them.
      - name: Delete the parked runs of the release branch
        uses: actions/github-script@v9
        with:
          script: |
            try {
              const releaseLib = require(
                `${process.env.GITHUB_WORKSPACE}/.github/workflows/lib/release.js`);
              const { owner, repo } = context.repo;
              const branch = 'release/${{ needs.publish.outputs.tag }}';
              const runs = await github.paginate(github.rest.actions.listWorkflowRunsForRepo, {
                owner, repo, event: 'pull_request', status: 'action_required', branch,
                per_page: 100,
              });
              for (const run of releaseLib.parkedRuns(runs, { fullName: `${owner}/${repo}`, branch })) {
                await github.rest.actions.deleteWorkflowRun({ owner, repo, run_id: run.id });
              }
            } catch (error) {
              core.warning(`Could not delete the parked runs of the release branch: ${error.message}`);
            }
```

- [ ] **Step 6: `publish-crates-io` v3**

Delete the comment and the step `Reconcile Cargo.lock with the bumped version` (lines 38-82). Lines 17-19 become:

```yaml
      # The commit `publish` tagged: the head the release pull request built
      # (D26). Its Cargo.toml and Cargo.lock carry the bumped version: the
      # release pull request rewrites both through version_files (D28).
```

Lines 123-126 become:

```yaml
      # --locked guards every pin in Cargo.lock: the release pull request
      # bumped the workspace's own entries, and nothing here re-resolves.
```

Manifest: `publish-crates-io` `"version": 3`.

- [ ] **Step 7: Re-render, run, gate, commit**

Re-render; run `tests/test_publish_build.py tests/test_publish.py tests/test_publish_gitea.py tests/test_self_render.py` (all pass); Full gate; report counts (`test_publish_build.py` +9 -1, `test_publish.py` +5 -4).

```bash
git add skills/repo-infra/assets tests/test_publish_build.py tests/test_publish.py .github/workflows/release-publish.yml
git commit -m "release-publish v5: one path, a tree comparison before the tag (D28)

publish compares the tree of the release pull request's merge commit
with the built head and tags nothing on a mismatch. finalize asserts
release_assets for every repository and deletes the parked runs of
the release branch. publish-crates-io no longer rewrites Cargo.lock.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Phase 5: check and apply

### Task 7: the ruleset requires up-to-date branches

**Files:**
- Modify: `skills/repo-infra/assets/gh/ruleset-main.json` (`"strict_required_status_checks_policy": true`), `skills/repo-infra/assets/manifest.json` (`"ruleset-main": {"version": 2, ...}`)
- Modify: `skills/repo-infra/scripts/repo_infra/remote.py:12-14,112-136`
- Modify: `skills/repo-infra/scripts/repo_infra/state.py:227-231`
- Modify: `skills/repo-infra/scripts/repo_infra/apply.py:422-440`
- Modify: `skills/repo-infra/scripts/repo_infra/cli.py:35-38`
- Modify: `tests/test_state.py:144-149`, `tests/test_apply_admin.py:85-98`, `tests/test_remote.py`

**Interfaces:**
- Produces: `Facts(..., strict=False, release_prs=(), tags=None)` (namedtuple defaults; Task 8 fills `release_prs` and `tags`).

- [ ] **Step 1: Write the failing tests**

`tests/test_state.py`: `facts()` base gains `strict=True`; append

```python
def test_a_ruleset_without_the_up_to_date_rule_is_outdated():
    item = next(i for i in classify_remote(facts(strict=False)) if i.name == "required-checks")
    assert item.state == "outdated"
    assert "strict_required_status_checks_policy" in item.detail


def test_missing_contexts_win_over_the_up_to_date_rule():
    items = states(classify_remote(facts(strict=False, required_contexts={"ci-passed"})))
    assert items["required-checks"] == "missing"
```

`tests/test_apply_admin.py`: in `faithful_ruleset`, the rule's parameters gain `"strict_required_status_checks_policy": True`; append

```python
def test_the_shipped_ruleset_requires_up_to_date_branches():
    payload = json.loads((ASSETS / "gh/ruleset-main.json").read_text(encoding="utf-8"))
    rule = next(r for r in payload["rules"] if r["type"] == "required_status_checks")
    assert rule["parameters"]["strict_required_status_checks_policy"] is True


def test_a_ruleset_that_reads_back_without_the_up_to_date_rule_is_refused(tmp_path):
    lax = json.loads(faithful_ruleset())
    lax["rules"][0]["parameters"]["strict_required_status_checks_policy"] = False
    recorder = Recorder({LIST: EXISTING, "rulesets": json.dumps(lax)})
    with pytest.raises(ApplyError, match="strict_required_status_checks_policy"):
        apply_admin_item(Gh(run=recorder), "o/r", "required-checks", facts(), ASSETS, tmp_path)
```

`tests/test_remote.py`: append

```python
def test_reads_the_up_to_date_rule():
    assert facts().strict is False  # the recorded ruleset predates D28
```

- [ ] **Step 2: Run them to see them fail**

Run: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests/test_state.py tests/test_apply_admin.py tests/test_remote.py 2>&1 | tail -5`
Expected: `TypeError: Facts.__new__() got an unexpected keyword argument 'strict'` and the payload assertion.

- [ ] **Step 3: Implement**

`remote.py`:

```python
Facts = namedtuple(
    "Facts",
    "default_branch protected required_contexts labels workflow_permissions can_approve_pr "
    "strict release_prs tags",
    defaults=(False, (), None))
```

In `facts()`, `strict = False` beside `contexts = set()`, and the rule loop becomes:

```python
            for rule in ruleset.get("rules", []):
                if rule.get("type") == "required_status_checks":
                    parameters = rule["parameters"]
                    strict = strict or parameters.get(
                        "strict_required_status_checks_policy") is True
                    for check in parameters["required_status_checks"]:
                        contexts.add(check["context"])
```

and `Facts(...)` gains `strict=strict`.

`state.py` `classify_remote`, the `required-checks` item:

```python
    wanted = {"ci-passed", "changelog-updated"}
    missing = sorted(wanted - facts.required_contexts)
    if missing:
        items.append(Item("required-checks", "missing",
                          "the ruleset does not require " + " or ".join(missing)))
    elif not facts.strict:
        items.append(Item(
            "required-checks", "outdated",
            "the ruleset lets a pull request merge while its branch is behind main "
            "(strict_required_status_checks_policy is off); a release built from an "
            "older main could then merge (D28)"))
    else:
        items.append(Item("required-checks", "ok", ""))
```

`apply.py`, before the `bypass_actors` check:

```python
        strict = any(rule.get("parameters", {}).get("strict_required_status_checks_policy")
                     is True for rule in created.get("rules", [])
                     if rule.get("type") == "required_status_checks")
        if not strict:
            raise ApplyError(
                f"{name}: wrote the ruleset but it read back with "
                "strict_required_status_checks_policy off, so a pull request whose "
                "branch is behind main can still merge. Check it in Settings -> Rules "
                f"-> Rulesets on repos/{repo} by hand.")
```

and the return text becomes `"enabled the branch ruleset with both required checks and up-to-date branches"`.

`cli.py` `CONFORMING_FACTS` gains `strict=True`. `ruleset-main.json`: `"strict_required_status_checks_policy": true`; manifest `gh.ruleset-main.version` 2.

- [ ] **Step 4: Run, gate, commit**

Run the three files (pass), then the Full gate (+5).

```bash
git add skills/repo-infra tests/test_state.py tests/test_apply_admin.py tests/test_remote.py
git commit -m "ruleset: require branches to be up to date before merging (D28)

check reports a ruleset without the rule as outdated and apply writes
it and reads it back. A release built from an older main can no longer
merge.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 8: `check` and `apply` migrate a repository to D28

**Files:**
- Create: `skills/repo-infra/scripts/repo_infra/seam.py`
- Create: `skills/repo-infra/scripts/repo_infra/migrate.py`
- Modify: `skills/repo-infra/scripts/repo_infra/state.py:255-320` (`classify_contracts`)
- Modify: `skills/repo-infra/scripts/repo_infra/remote.py` (`facts()` reads open release pull requests and tags)
- Modify: `skills/repo-infra/scripts/repo_infra/cli.py` (`_prepare`, `check`, `apply_command`)
- Create: `tests/test_seam.py`, `tests/test_migrate.py`, `tests/fixtures/gh/pulls-open.json`, `tests/fixtures/gh/tags.json`
- Modify: `tests/test_release_contracts.py`, `tests/test_remote.py`, `tests/test_ci_local.py`

**Interfaces:**
- Consumes: `manifest["release_build_blocks"][name]["assets"]` (Task 5); `Facts.release_prs`, `Facts.tags` (Task 7 declared them); `DetectResult.version_files` with detection's `Cargo.lock` entries (`detect._cargo_lock_entries`).
- Produces:
  - `seam.seam_problems(text: str, reserved_artifacts: bool) -> list[str]`
  - `migrate.migrated_config(repo_root, config, result, manifest) -> (dict, list[Item])`
  - `migrate.without_superseded(items, migrations) -> list[Item]`
  - `migrate.apply_migrations(repo_root, config, effective) -> list[str]` (paths staged for one commit)
  - `migrate.release_in_progress(repo_root, facts) -> Item | None`, `migrate.touches_release_flow(items) -> bool`
  - `migrate.NAMES` (the migration item names), `migrate.RELEASE_FLOW`
  - `state.classify_contracts(repo_root, result, config=None, pending_rename=False)`
  - `cli._prepare(root) -> (manifest, result, rendered, config, migrations)`; `cli._load(root)` keeps returning the first three.

Item names this task introduces: `release-build-rename`, `release-build-config`, `publish-source-tarball`, `release-assets`, `cargo-lock-version-files` (migrations); `ci-local-seam`, `action-test-seam`, `release-build-local-seam`, `release-build-local` (contracts); `release-in-progress` (refusal). The contract item `release-build` and `gitea-packages-build` disappear.

The spec asks `check` to report a missing add-on pattern in `release_assets` as `conflict` and `apply` to add it. Elsewhere `apply` refuses every conflict. This task keeps the spec's state for `release-assets` and lets `apply` act on migration items in any state, because the migration items are config edits, not file items; see the report at the end of this plan.

- [ ] **Step 1: Write the failing seam tests** (`tests/test_seam.py`)

```python
"""The D28 contract of a project-owned reusable workflow, read from text."""

import pytest

from repo_infra.seam import seam_problems

GOOD = """\
name: Local CI
on:
  workflow_call:
    inputs:
      ref:
        type: string
        required: false
        default: ''
jobs:
  windows:
    runs-on: windows-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ inputs.ref }}
      - run: cargo check
  lint:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Check out
        uses: "actions/checkout@v7"
        with:
          fetch-depth: 0
          ref: ${{ inputs.ref }}
"""


def test_a_conforming_file_has_no_problem():
    assert seam_problems(GOOD, reserved_artifacts=True) == []


def test_a_flow_style_trigger_declares_no_ref():
    text = GOOD.replace(GOOD.split("jobs:")[0], "name: x\non: [workflow_call]\n")
    assert seam_problems(text, False) == ["declares no workflow_call input `ref`"]


def test_an_input_of_another_name_is_not_ref():
    text = GOOD.replace("      ref:\n        type", "      reference:\n        type")
    assert "declares no workflow_call input `ref`" in seam_problems(text, False)


def test_a_checkout_in_a_second_job_without_ref_is_named():
    text = GOOD.replace("          fetch-depth: 0\n          ref: ${{ inputs.ref }}\n",
                        "          fetch-depth: 0\n")
    assert seam_problems(text, False) == [
        "has an actions/checkout step that does not check out `ref: ${{ inputs.ref }}`"]


def test_a_checkout_without_with_is_named():
    text = GOOD.replace("      - uses: actions/checkout@v7\n        with:\n"
                        "          ref: ${{ inputs.ref }}\n", "      - uses: actions/checkout@v7\n")
    assert len(seam_problems(text, False)) == 1


def test_a_comment_mentioning_ref_does_not_count():
    text = GOOD.replace("          fetch-depth: 0\n          ref: ${{ inputs.ref }}\n",
                        "          fetch-depth: 0\n          # ref: ${{ inputs.ref }}\n")
    assert len(seam_problems(text, False)) == 1


@pytest.mark.parametrize("name", ["release-asset-x", "'release-files'", '"release-asset-"'])
def test_a_reserved_artifact_name_is_named_where_it_is_reserved(name):
    text = GOOD + ("      - uses: actions/upload-artifact@v7\n        with:\n"
                   f"          name: {name}\n          path: out/\n")
    problems = seam_problems(text, reserved_artifacts=True)
    assert len(problems) == 1 and "reserved for the release build" in problems[0]
    assert seam_problems(text, reserved_artifacts=False) == []


def test_a_step_display_name_is_not_an_artifact_name():
    text = GOOD + ("      - name: release-files\n        uses: actions/upload-artifact@v7\n"
                   "        with:\n          name: coverage\n          path: out/\n")
    assert seam_problems(text, reserved_artifacts=True) == []
```

- [ ] **Step 2: Write `seam.py`**

```python
"""The contract of a project-owned reusable workflow (D20, D25, D28).

ci.yml calls ci-local.yml and action-test.yml, and release-build.yml calls
release-build-local.yml, each with the input `ref`: the commit to test or to
build. A file that does not declare it makes GitHub reject the caller. A file
that declares it and checks out its default commit instead tests main while
the release pull request says it tested the release. Both are read from the
text here, because the scripts use the standard library only; the reader
understands block-style YAML as GitHub workflows write it.
"""

import re

_LINE = re.compile(r"^(?P<indent>\s*)(?P<dash>-\s+)?(?P<key>[A-Za-z_][\w-]*)\s*:\s*(?P<value>.*)$")
_INPUT_REF = re.compile(r"\$\{\{\s*inputs\.ref\s*\}\}")
_RESERVED = re.compile(r"^(release-asset-.*|release-files)$")


def _strip(value):
    return value.strip().strip("'\"")


def _parse(text):
    """One (indent, dash, key, value) per key line. `dash` is the column of a
    list item's `-` or None; `indent` is the column of the key itself."""
    lines = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        match = _LINE.match(raw)
        if not match:
            continue
        value = match["value"]
        if " #" in value and not value.lstrip().startswith(("'", '"')):
            value = value.split(" #", 1)[0]
        dash = len(match["indent"]) if match["dash"] else None
        indent = len(match["indent"]) + (len(match["dash"]) if match["dash"] else 0)
        lines.append((indent, dash, match["key"], value.strip()))
    return lines


def _nested(lines, i):
    """The lines nested under line i, by indentation."""
    j = i + 1
    while j < len(lines) and lines[j][0] > lines[i][0]:
        j += 1
    return lines[i + 1:j]


def _declares_ref(lines):
    for i, (_indent, _dash, key, _value) in enumerate(lines):
        if key != "workflow_call":
            continue
        for k, line in enumerate(lines[i + 1:], start=i + 1):
            if line[0] <= lines[i][0]:
                break
            if line[2] == "inputs":
                children = _nested(lines, k)
                if children and any(c[0] == children[0][0] and c[2] == "ref" for c in children):
                    return True
    return False


def _steps(lines):
    """Each list item with everything nested under it."""
    steps = []
    for i, (_indent, dash, _key, _value) in enumerate(lines):
        if dash is None:
            continue
        j = i + 1
        while j < len(lines) and lines[j][0] > dash and not (
                lines[j][1] is not None and lines[j][1] <= dash):
            j += 1
        steps.append(lines[i:j])
    return steps


def seam_problems(text, reserved_artifacts):
    lines = _parse(text)
    problems = []
    if not _declares_ref(lines):
        problems.append("declares no workflow_call input `ref`")
    for step in _steps(lines):
        uses = next((_strip(v) for _i, _d, k, v in step if k == "uses"), "")
        if uses.startswith("actions/checkout@"):
            if not any(k == "ref" and _INPUT_REF.search(v) for _i, _d, k, v in step):
                problems.append("has an actions/checkout step that does not check out "
                                "`ref: ${{ inputs.ref }}`")
        if reserved_artifacts and uses.startswith("actions/upload-artifact@"):
            with_indent = next((i for i, _d, k, _v in step if k == "with"), None)
            for indent, _d, key, value in step:
                if (with_indent is not None and indent > with_indent and key == "name"
                        and _RESERVED.match(_strip(value))):
                    problems.append(f"uploads an artifact named {_strip(value)}, a name "
                                    "reserved for the release build")
    return list(dict.fromkeys(problems))
```

Run: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests/test_seam.py 2>&1 | tail -3` -- Expected: `10 passed`.

- [ ] **Step 3: Write the failing contract tests** (`tests/test_release_contracts.py`)

Replace `test_release_build_without_the_project_build_is_a_conflict`, `test_a_refused_release_file_is_a_conflict`, `gitea_config` and `test_gitea_packages_without_release_build_is_a_conflict` with:

```python
SEAM_OK = ("on:\n  workflow_call:\n    inputs:\n      ref:\n        type: string\n"
           "jobs:\n  a:\n    runs-on: x\n    steps:\n      - uses: actions/checkout@v7\n"
           "        with:\n          ref: ${{ inputs.ref }}\n")
SEAM_NO_REF = "on: [workflow_call]\njobs:\n  a:\n    runs-on: x\n    steps:\n      - run: true\n"


def write(tmp_path, name, text):
    (tmp_path / ".github/workflows").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".github/workflows" / name).write_text(text)


def test_release_build_local_without_its_file_is_a_conflict(tmp_path):
    items = classify_contracts(tmp_path, result(tmp_path), {"release_build_local": True})
    assert [(i.name, i.state) for i in items] == [("release-build-local", "conflict")]
    assert ".github/workflows/release-build-local.yml" in items[0].detail


def test_the_d26_contract_items_are_gone(tmp_path):
    items = classify_contracts(tmp_path, result(tmp_path), {
        "release_build": True, "publish": ["publish-gitea-packages"],
        "gitea_packages": GITEA_OK})
    assert items == []


@pytest.mark.parametrize("key,name,item", [
    ("ci_local", "ci-local.yml", "ci-local-seam"),
    ("release_build_local", "release-build-local.yml", "release-build-local-seam"),
])
def test_a_seam_without_ref_is_a_conflict_naming_the_file(tmp_path, key, name, item):
    write(tmp_path, name, SEAM_NO_REF)
    items = classify_contracts(tmp_path, result(tmp_path), {key: True})
    assert [(i.name, i.state) for i in items] == [(item, "conflict")]
    assert f".github/workflows/{name}" in items[0].detail
    assert "declares no workflow_call input `ref`" in items[0].detail


def test_the_action_test_seam_is_checked_too(tmp_path):
    (tmp_path / "action.yml").write_text("name: x\n")
    write(tmp_path, "action-test.yml", SEAM_NO_REF)
    items = classify_contracts(tmp_path, result(tmp_path), {})
    assert [(i.name, i.state) for i in items] == [("action-test-seam", "conflict")]


def test_ci_local_may_not_upload_a_release_asset(tmp_path):
    write(tmp_path, "ci-local.yml", SEAM_OK + "      - uses: actions/upload-artifact@v7\n"
          "        with:\n          name: release-files\n          path: x\n")
    (item,) = classify_contracts(tmp_path, result(tmp_path), {"ci_local": True})
    assert item.name == "ci-local-seam" and "release-files" in item.detail


def test_release_build_local_may_upload_release_assets(tmp_path):
    write(tmp_path, "release-build-local.yml", SEAM_OK + "      - uses: actions/upload-artifact@v7\n"
          "        with:\n          name: release-asset-linux\n          path: x\n")
    assert classify_contracts(tmp_path, result(tmp_path), {"release_build_local": True}) == []


def test_a_pending_rename_checks_the_d26_file_under_the_new_name(tmp_path):
    write(tmp_path, "release-build.yml", SEAM_NO_REF)
    items = classify_contracts(tmp_path, result(tmp_path), {"release_build_local": True},
                               pending_rename=True)
    assert [(i.name, i.state) for i in items] == [("release-build-local-seam", "conflict")]


def test_a_refused_release_file_is_a_conflict(tmp_path):
    config = {"release_files": ["./CHANGES.md"], "version_files": []}
    items = classify_contracts(tmp_path, result(tmp_path), config)
    assert [(i.name, i.state) for i in items] == [("release-files", "conflict")]
    assert "./CHANGES.md" in items[0].detail


def gitea_config(tmp_path, **over):
    config = {"publish": ["publish-gitea-packages"], "gitea_packages": GITEA_OK}
    config.update(over)
    return classify_contracts(tmp_path, result(tmp_path), config)


def test_gitea_packages_with_its_config_is_fine(tmp_path):
    assert gitea_config(tmp_path) == []
```

Keep `test_gitea_packages_without_url_or_owner_is_a_conflict` as is. Also update `tests/test_ci_local.py`'s `test_a_present_ci_local_workflow_reports_nothing` to write a conforming file: `.write_text("on:\n  workflow_call:\n    inputs:\n      ref:\n        type: string\njobs: {}\n")`.

- [ ] **Step 4: Implement the contracts** (`state.py` `classify_contracts`)

Signature `def classify_contracts(repo_root, result, config=None, pending_rename=False):`. Keep the `action-test` and `ci-local-workflow` missing-file items. Replace the `release_build` block and the `gitea-packages-build` block (lines 286-302) with:

```python
    root = pathlib.Path(repo_root)
    local_build = ".github/workflows/release-build-local.yml"
    if config.get("release_build_local") and not pending_rename:
        if not (root / local_build).is_file():
            items.append(Item(
                "release-build-local", "conflict",
                "release_build_local is set and .github/workflows/release-build-local.yml "
                "does not exist; release-build.yml calls it and GitHub rejects the whole "
                "release workflow. Write it (references/conventions.md), or remove "
                "\"release_build_local\" from .github/repo-infra.json."))
    # D28: each seam declares `ref` and checks it out; only the build may
    # upload release-asset-* and release-files. While the D26 rename is
    # pending, the build is still release-build.yml.
    seams = []
    if "github-action" in result.ecosystems:
        seams.append(("action-test-seam", ".github/workflows/action-test.yml", True))
    if config.get("ci_local"):
        seams.append(("ci-local-seam", ".github/workflows/ci-local.yml", True))
    if config.get("release_build_local"):
        seams.append(("release-build-local-seam",
                      ".github/workflows/release-build.yml" if pending_rename else local_build,
                      False))
    for name, rel, reserved in seams:
        path = root / rel
        if not path.is_file():
            continue
        problems = seam_problems(path.read_text(encoding="utf-8"), reserved)
        if problems:
            items.append(Item(
                name, "conflict",
                f"{rel} " + "; ".join(problems) + ". apply does not edit this file: declare "
                "`on: workflow_call: inputs: ref` and give every actions/checkout "
                "`ref: ${{ inputs.ref }}` (references/conventions.md)."))
```

Add `from .seam import seam_problems` to the imports.

- [ ] **Step 5: Write the failing migration tests** (`tests/test_migrate.py`)

```python
"""D28 migration: what check reports and what apply moves."""

import json
import pathlib
import subprocess

import pytest

from repo_infra import cli
from repo_infra.apply import ApplyError
from repo_infra.migrate import migrated_config, release_in_progress
from repo_infra.remote import Facts

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
D26_BUILD = ("name: Release build\non:\n  workflow_call:\n    inputs:\n      version:\n"
             "        type: string\n      ref:\n        type: string\njobs:\n  b:\n"
             "    runs-on: x\n    timeout-minutes: 5\n    steps:\n"
             "      - uses: actions/checkout@v7\n        with:\n          ref: ${{ inputs.ref }}\n")
CHANGES = "# Changes\n\n## [Unreleased]\n\n## 0.6.0 - 2026-09-30\n\n- x\n"


def facts(**over):
    base = dict(cli.CONFORMING_FACTS._asdict())
    base.update(tags=frozenset({"v0.6.0"}))
    base.update(over)
    return Facts(**base)


def repo(tmp_path, config, files=None):
    root = tmp_path / "repo"
    (root / ".github/workflows").mkdir(parents=True)
    (root / ".github/repo-infra.json").write_text(json.dumps(config, indent=2) + "\n")
    (root / "CHANGES.md").write_text(CHANGES)
    for path, text in (files or {}).items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    for args in (("init", "-q", "-b", "main"), ("add", "-A"),
                 ("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "seed")):
        subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True)
    return root


def migrations(root):
    return {i.name: i.state for i in cli._prepare(root)[4]}


def test_the_d26_build_is_renamed_not_reported_as_unmanaged(tmp_path):
    root = repo(tmp_path, {"release_build": True, "version_files": []},
                {".github/workflows/release-build.yml": D26_BUILD})
    assert migrations(root) == {"release-build-rename": "outdated",
                                "release-build-config": "outdated"}
    config = cli._prepare(root)[3]
    assert config["release_build"] == [] and config["release_build_local"] is True


def test_boolean_release_build_without_a_d26_file_only_becomes_a_list(tmp_path):
    root = repo(tmp_path, {"release_build": False, "version_files": []})
    assert migrations(root) == {"release-build-config": "outdated"}


def test_the_source_tarball_moves_to_the_build(tmp_path):
    root = repo(tmp_path, {"publish": ["publish-source-tarball", "publish-crates-io"],
                           "version_files": []})
    assert migrations(root) == {"publish-source-tarball": "outdated",
                                "release-assets": "conflict"}
    config = cli._prepare(root)[3]
    assert config["publish"] == ["publish-crates-io"]
    assert config["release_build"] == ["release-source-tarball"]
    assert config["release_assets"] == ["*.tar.gz"]


def test_an_add_on_pattern_missing_from_release_assets_is_a_conflict(tmp_path):
    root = repo(tmp_path, {"release_build": ["release-source-tarball"],
                           "release_assets": ["x-*.zip"], "version_files": []})
    assert migrations(root) == {"release-assets": "conflict"}
    assert cli._prepare(root)[3]["release_assets"] == ["x-*.zip", "*.tar.gz"]


def test_missing_cargo_lock_entries_are_reported_and_added(tmp_path):
    root = repo(tmp_path, {"version_files": [{"path": "Cargo.toml", "pattern": "^version",
                                              "replacement": "x", "verify": "x"}]},
                {"Cargo.toml": '[package]\nname = "app"\nversion = "0.6.0"\n',
                 "Cargo.lock": '[[package]]\nname = "app"\nversion = "0.6.0"\n'})
    assert migrations(root) == {"cargo-lock-version-files": "missing"}
    lock = [e for e in cli._prepare(root)[3]["version_files"] if e["path"] == "Cargo.lock"]
    assert [e["pattern"] for e in lock] == ['^name = "app"\nversion = "[^"]*"']


def test_present_cargo_lock_entries_are_left_alone(tmp_path):
    entry = {"path": "Cargo.lock", "pattern": '^name = "app"\nversion = "[^"]*"',
             "replacement": 'name = "app"\nversion = "$VERSION"',
             "verify": '^name = "app"\nversion = "$VERSION"'}
    root = repo(tmp_path, {"version_files": [entry]},
                {"Cargo.toml": '[package]\nname = "app"\nversion = "0.6.0"\n',
                 "Cargo.lock": '[[package]]\nname = "app"\nversion = "0.6.0"\n'})
    assert migrations(root) == {}


def test_a_current_config_needs_no_migration(tmp_path):
    root = repo(tmp_path, {"release_build": [], "version_files": []})
    assert migrations(root) == {}


def test_an_open_release_pull_request_is_a_release_in_progress(tmp_path):
    root = repo(tmp_path, {"version_files": []})
    item = release_in_progress(root, facts(release_prs=((12, "release/v0.6.1"),)))
    assert (item.name, item.state) == ("release-in-progress", "conflict")
    assert "#12" in item.detail and "release/v0.6.1" in item.detail


def test_an_untagged_latest_release_is_a_release_in_progress(tmp_path):
    root = repo(tmp_path, {"version_files": []})
    item = release_in_progress(root, facts(tags=frozenset({"v0.5.0"})))
    assert "v0.6.0 is in CHANGES.md but has no tag" in item.detail


def test_unknown_tags_are_not_a_refusal(tmp_path):
    root = repo(tmp_path, {"version_files": []})
    assert release_in_progress(root, facts(tags=None)) is None


def run_check(root, monkeypatch, capsys, the_facts):
    monkeypatch.setattr(cli, "read_facts", lambda repo: the_facts)
    code = cli.main(["check", "--repo", "o/r", "--root", str(root), "--json"])
    return code, {i["name"]: i for i in json.loads(capsys.readouterr().out)["items"]}


def test_check_reports_migrations_and_the_refusal(tmp_path, monkeypatch, capsys):
    root = repo(tmp_path, {"release_build": True, "version_files": []},
                {".github/workflows/release-build.yml": D26_BUILD})
    code, items = run_check(root, monkeypatch, capsys,
                            facts(release_prs=((12, "release/v0.6.1"),)))
    assert code == 1
    assert items["release-build-rename"]["state"] == "outdated"
    assert items["release-in-progress"]["state"] == "conflict"
    # The D26 file is not reported as unmanaged while its rename is pending.
    assert items.get("release-build", {}).get("state") != "conflict"


def test_check_says_nothing_about_a_release_when_nothing_migrates(tmp_path, monkeypatch, capsys):
    root = ROOT  # repo-infra itself is current
    code, items = run_check(root, monkeypatch, capsys,
                            facts(release_prs=((12, "release/v0.6.1"),)))
    assert "release-in-progress" not in items


def test_apply_refuses_while_a_release_is_in_progress(tmp_path, monkeypatch):
    root = repo(tmp_path, {"release_build": True, "version_files": []},
                {".github/workflows/release-build.yml": D26_BUILD})
    monkeypatch.setattr(cli, "read_facts",
                        lambda repo: facts(release_prs=((12, "release/v0.6.1"),)))
    with pytest.raises(ApplyError, match="release-in-progress"):
        cli.main(["apply", "--repo", "o/r", "--root", str(root),
                  "--item", "release-build-rename"])
    head = subprocess.run(["git", "log", "--oneline"], cwd=root, capture_output=True,
                          text=True).stdout
    assert head.count("\n") == 1  # nothing committed


def test_apply_renames_the_d26_build_unchanged_and_rewrites_the_config(tmp_path, monkeypatch):
    root = repo(tmp_path, {"release_build": True, "version_files": []},
                {".github/workflows/release-build.yml": D26_BUILD})
    monkeypatch.setattr(cli, "read_facts", lambda repo: facts())
    cli.main(["apply", "--repo", "o/r", "--root", str(root), "--item", "release-build-rename"])
    status = subprocess.run(["git", "show", "--name-status", "-M", "--format=", "HEAD"],
                            cwd=root, capture_output=True, text=True).stdout.splitlines()
    assert ("R100\t.github/workflows/release-build.yml\t"
            ".github/workflows/release-build-local.yml") in status
    assert "M\t.github/repo-infra.json" in status
    config = json.loads((root / ".github/repo-infra.json").read_text())
    assert config["release_build"] == [] and config["release_build_local"] is True
    assert (root / ".github/workflows/release-build-local.yml").read_text() == D26_BUILD


def test_the_assembled_build_is_installed_after_the_rename(tmp_path, monkeypatch):
    root = repo(tmp_path, {"release_build": True, "version_files": []},
                {".github/workflows/release-build.yml": D26_BUILD})
    monkeypatch.setattr(cli, "read_facts", lambda repo: facts())
    cli.main(["apply", "--repo", "o/r", "--root", str(root), "--item", "release-build-rename"])
    cli.main(["apply", "--repo", "o/r", "--root", str(root), "--item", "release-build"])
    text = (root / ".github/workflows/release-build.yml").read_text()
    assert "# repo-infra: release-build v1" in text
    assert "uses: ./.github/workflows/release-build-local.yml" in text
```

- [ ] **Step 6: Run them to see them fail**

Run: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests/test_migrate.py tests/test_release_contracts.py tests/test_ci_local.py 2>&1 | tail -5`
Expected: `ModuleNotFoundError: No module named 'repo_infra.migrate'` and contract failures.

- [ ] **Step 7: Write `migrate.py`**

```python
"""Migration of a repository to the one release flow (D28).

D24 to D27 never shipped, so a repository on them was converted from the
branch. `check` reports what moves and `apply` moves it: the
.github/repo-infra.json keys D28 replaced, the Cargo.lock entries detection
proposes, and D26's project-owned release-build.yml, which becomes
release-build-local.yml unchanged. Everything is rendered from the migrated
config, so `check` shows the files as they will be after the move.
"""

import copy
import json
import pathlib
import re

from .apply import ApplyError, _git
from .markers import parse_markers
from .state import Item

CONFIG = ".github/repo-infra.json"
D26_BUILD = ".github/workflows/release-build.yml"
LOCAL_BUILD = ".github/workflows/release-build-local.yml"
NAMES = ("release-build-rename", "release-build-config", "publish-source-tarball",
         "release-assets", "cargo-lock-version-files")
# Items whose change alters how a release in flight would finish.
RELEASE_FLOW = frozenset({"release-pr", "changelog", "ci", "release-publish",
                          "release-build", "workflow-lib", *NAMES})
_LOCK_NAME = re.compile(r'name = "([^"]+)"')
_RELEASE = re.compile(r"^## (\d+\.\d+\.\d+) - \d{4}-\d{2}-\d{2}\s*$")


def _is_d26_build(repo_root):
    path = pathlib.Path(repo_root) / D26_BUILD
    return path.is_file() and not parse_markers(path.read_text(encoding="utf-8"))


def _lock_crate(entry):
    if entry.get("path") != "Cargo.lock":
        return None
    match = _LOCK_NAME.search(entry.get("pattern", ""))
    return match.group(1) if match else None


def migrated_config(repo_root, config, result, manifest):
    """The config after D28's migration, and one Item per change it makes."""
    new = copy.deepcopy(config)
    items = []

    build = new.get("release_build")
    if isinstance(build, bool):
        if build and _is_d26_build(repo_root):
            new["release_build_local"] = True
            items.append(Item(
                "release-build-rename", "outdated",
                f"{D26_BUILD} is D26's project-owned build. apply renames it to "
                f"{LOCAL_BUILD} with git mv, unchanged, sets \"release_build_local\": true "
                "and installs the assembled release-build.yml."))
        new["release_build"] = []
        items.append(Item(
            "release-build-config", "outdated",
            f"\"release_build\": {json.dumps(build)} becomes \"release_build\": [], the "
            "list of build add-ons."))

    publish = new.get("publish", [])
    if "publish-source-tarball" in publish:
        new["publish"] = [p for p in publish if p != "publish-source-tarball"]
        builds = list(new.get("release_build") or [])
        if "release-source-tarball" not in builds:
            builds.append("release-source-tarball")
        new["release_build"] = builds
        items.append(Item(
            "publish-source-tarball", "outdated",
            "the tarball is built before the merge now: apply moves "
            "\"publish-source-tarball\" from \"publish\" to \"release_build\": "
            "[\"release-source-tarball\"]."))

    blocks = manifest.get("release_build_blocks", {})
    builds = new.get("release_build") if isinstance(new.get("release_build"), list) else []
    declared = list(new.get("release_assets", []))
    wanted = [p for name in builds for p in blocks.get(name, {}).get("assets", [])]
    absent = [p for p in dict.fromkeys(wanted) if p not in declared]
    if absent:
        new["release_assets"] = declared + absent
        items.append(Item(
            "release-assets", "conflict",
            "release_assets in .github/repo-infra.json lacks " + ", ".join(absent)
            + ", which an installed release_build add-on builds; finish would accept a "
            "build that drops it. apply adds it."))

    if "version_files" in new:
        have = {_lock_crate(e) for e in new["version_files"]}
        lock = [e for e in result.version_files
                if _lock_crate(e) and _lock_crate(e) not in have]
        if lock:
            new["version_files"] = list(new["version_files"]) + lock
            items.append(Item(
                "cargo-lock-version-files", "missing",
                "version_files has no Cargo.lock entry for "
                + ", ".join(_lock_crate(e) for e in lock)
                + "; the release pull request would leave Cargo.lock at the old version. "
                "apply adds them."))
    return new, items


def renaming(migrations):
    return any(i.name == "release-build-rename" for i in migrations)


def without_superseded(items, migrations):
    """The D26 build reads as an unmanaged release-build.yml until it is renamed."""
    if not renaming(migrations):
        return items
    return [i for i in items if not (i.name == "release-build" and i.state == "conflict")]


def apply_migrations(repo_root, config, effective):
    """Perform the migration and stage it; returns the paths to commit."""
    root = pathlib.Path(repo_root)
    written = []
    if effective.get("release_build_local") and not config.get("release_build_local") \
            and _is_d26_build(root):
        _git(root, "mv", D26_BUILD, LOCAL_BUILD)
        written.append(LOCAL_BUILD)
    if effective != config:
        target = root / CONFIG
        target.write_text(json.dumps(effective, indent=2) + "\n", encoding="utf-8")
        if json.loads(target.read_text(encoding="utf-8")) != effective:
            raise ApplyError(f"{CONFIG}: wrote the migrated config and read back something else")
        written.append(CONFIG)
    return written


def commit_migration(repo_root, written):
    if not written:
        return None
    _git(repo_root, "add", *written)
    _git(repo_root, "commit", "-m",
         "Migrate to the one release flow (repo-infra D28)\n\n"
         "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>")
    return _git(repo_root, "rev-parse", "HEAD").strip()


def latest_release(text):
    for line in text.splitlines():
        match = _RELEASE.match(line)
        if match:
            return match.group(1)
    return None


def release_in_progress(repo_root, facts):
    """Why this repository cannot migrate right now, or None.

    The new publish expects a draft with release-build.json and the new
    release mode expects release-built; a release started by the old flow
    has neither.
    """
    if facts.release_prs:
        number, branch = facts.release_prs[0]
        return Item(
            "release-in-progress", "conflict",
            f"release pull request #{number} ({branch}) is open. Merge or close it and "
            "let its publish finish, then migrate: the new flow cannot finish a release "
            "the old one started.")
    changes = pathlib.Path(repo_root) / "CHANGES.md"
    latest = latest_release(changes.read_text(encoding="utf-8")) if changes.is_file() else None
    if latest and facts.tags is not None and f"v{latest}" not in facts.tags:
        return Item(
            "release-in-progress", "conflict",
            f"v{latest} is in CHANGES.md but has no tag: its publish has not finished. "
            "Finish or abandon that release, then migrate.")
    return None


def touches_release_flow(items):
    return any(i.name in RELEASE_FLOW and i.state not in ("ok", "skipped") for i in items)
```

`commit_migration` uses the same co-author line as `apply.commit_item` (repo-infra's commits in the target repository), so the two cannot drift; change both together if that line ever changes.

- [ ] **Step 8: `remote.py` reads release pull requests and tags**

In `facts()`, before the `return`:

```python
        release_prs = tuple(
            (pr["number"], pr["head"]["ref"])
            for pr in self._api_paginated_list(f"repos/{repo}/pulls?state=open")
            if pr["head"]["ref"].startswith("release/")
            and (pr["head"].get("repo") or {}).get("full_name") == repo
            and pr["user"]["login"] == "github-actions[bot]")
        tags = frozenset(t["name"] for t in self._api_paginated_list(f"repos/{repo}/tags"))
```

and `Facts(...)` gains `release_prs=release_prs, tags=tags`. Fixtures: `tests/fixtures/gh/pulls-open.json` = `[{"number": 12, "user": {"login": "github-actions[bot]"}, "head": {"ref": "release/v0.3.0", "repo": {"full_name": "oposs/repo-infra"}}}, {"number": 13, "user": {"login": "oetiker"}, "head": {"ref": "release/x", "repo": {"full_name": "oposs/repo-infra"}}}]`; `tests/fixtures/gh/tags.json` = `[{"name": "v0.2.0"}, {"name": "v0.1.0"}]`. In `tests/test_remote.py` add `"/pulls?state=open": "pulls-open.json"` and `"/tags": "tags.json"` to `RECORDED` and to the three hand-built mappings (lines 84-90, 99-106, 112-119), and append:

```python
def test_reads_the_open_release_pull_requests_of_the_bot_only():
    assert facts().release_prs == ((12, "release/v0.3.0"),)


def test_reads_the_tags():
    assert facts().tags == frozenset({"v0.2.0", "v0.1.0"})
```

- [ ] **Step 9: Wire `cli.py`**

```python
from . import migrate, report
from .apply import ApplyError, apply_admin_item, apply_file_item, commit_item, ensure_branch
```

Replace `_chosen` and `_load` with:

```python
def _prepare(root):
    """Everything `check` and `apply` read, rendered from the migrated config (D28)."""
    manifest = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
    detection = Detection.load(ASSETS / "detection.json")
    result = detection.detect(root)
    config, migrations = migrate.migrated_config(root, _config(root), result, manifest)
    ci = config.get("ci", [])
    rendered = render_all(ASSETS, result, manifest,
                          config.get("publish", []), config.get("build", []),
                          ci, config.get("publish_local", []),
                          ci_local=bool(config.get("ci_local")),
                          release_build=config.get("release_build", []),
                          release_build_local=bool(config.get("release_build_local")))
    result.candidates = detection.open_candidates(result.candidates, ci)
    return manifest, result, rendered, config, migrations


def _load(root):
    return _prepare(root)[:3]


def _blocker(root, facts, items):
    blocker = migrate.release_in_progress(root, facts)
    return blocker if blocker and migrate.touches_release_flow(items) else None
```

`check`:

```python
def check(args):
    manifest, result, rendered, config, migrations = _prepare(args.root)
    repo = args.repo or Gh().current_repo()
    facts = read_facts(repo)
    items = migrate.without_superseded(classify(args.root, rendered, manifest, facts),
                                       migrations) + migrations
    items += classify_ambiguities(result)
    items += classify_contracts(args.root, result, config,
                                pending_rename=migrate.renaming(migrations))
    blocker = _blocker(args.root, facts, items)
    if blocker:
        items.append(blocker)
    renderer = report.render_json if args.json else report.render_text
    print(renderer(repo, result, items))
    return 1 if any(i.state in NEEDS_ATTENTION_STATES for i in items) else 0
```

`apply_command`:

```python
def apply_command(args):
    manifest, result, rendered, config, migrations = _prepare(args.root)
    repo = args.repo or Gh().current_repo()
    facts = read_facts(repo)
    items = migrate.without_superseded(classify(args.root, rendered, manifest, facts),
                                       migrations) + migrations
    blocker = _blocker(args.root, facts, items)
    if blocker:
        raise ApplyError(f"release-in-progress: {blocker.detail}")
    plugin_root = ASSETS.parent

    ensure_branch(args.root)
    if migrations and (args.item is None or args.item in migrate.NAMES):
        # One config edit, one commit: the items are views of the same file.
        written = migrate.apply_migrations(args.root, _config(args.root), config)
        migrate.commit_migration(args.root, written)
        print("applied " + ", ".join(i.name for i in migrations))
        if args.item:
            return 0
        manifest, result, rendered, config, migrations = _prepare(args.root)
        items = classify(args.root, rendered, manifest, facts)

    names = [args.item] if args.item else _ordered_names(items)
    for name in names:
        if name in ADMIN:
            print(apply_admin_item(Gh(), repo, name, facts, ASSETS, args.root))
            continue
        written = apply_file_item(args.root, name, rendered, items, plugin_root,
                                  merged=args.from_file)
        commit_item(args.root, name, written)
        print(f"applied {name}")
    return 0
```

`_ordered_names` needs no change: after the migration commit, `items` holds no migration item.

- [ ] **Step 10: Run, gate, commit**

Run: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests/test_seam.py tests/test_migrate.py tests/test_release_contracts.py tests/test_remote.py tests/test_ci_local.py tests/test_cli.py tests/test_ci_man.py tests/test_ci_rust_musl.py 2>&1 | tail -3` (all pass), then the Full gate and `uvx ruff check .`. Report counts: `test_seam.py` 10, `test_migrate.py` 15, `test_release_contracts.py` +10 -4, `test_remote.py` +2.

```bash
git add skills/repo-infra/scripts/repo_infra tests
git commit -m "check and apply: migrate to the one release flow (D28)

check reports the config keys D28 replaced, a missing add-on asset
pattern, missing Cargo.lock entries and a D26 release-build.yml, and
apply moves them in one commit, renaming the D26 build with git mv.
Both refuse while a release is in progress. ci-local.yml,
action-test.yml and release-build-local.yml must declare ref and check
it out; the CI seams may not upload release-asset-* or release-files.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: detection proposes `release-source-tarball` for `perl-autotools`

**Files:**
- Modify: `skills/repo-infra/assets/detection.json` (`candidates`)
- Modify: `skills/repo-infra/scripts/repo_infra/detect.py:121-132`
- Modify: `skills/repo-infra/scripts/repo_infra/cli.py` (`_prepare`: pass the chosen build add-ons)
- Modify: `tests/test_detect.py`

**Interfaces:**
- Produces: `Detection.open_candidates(candidates, chosen_ci, chosen_release_build=()) -> list[str]`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_detect.py`)

```python
def test_an_autotools_perl_repository_is_proposed_the_source_tarball():
    detection = Detection.load(REAL)
    result = detection.detect(HERE / "fixtures/repo-perl-autotools")
    assert "release-source-tarball" in result.candidates
    assert "release-source-tarball" not in detection.open_candidates(
        result.candidates, [], ["release-source-tarball"])


def test_a_python_repository_is_not_proposed_the_source_tarball():
    result = Detection.load(REAL).detect(HERE / "fixtures/repo-python")
    assert "release-source-tarball" not in result.candidates
```

- [ ] **Step 2: Run to see them fail**, then implement:

`detection.json` `candidates` gains:

```json
    {"id": "release-source-tarball", "signals": {"all": ["configure.ac", "cpanfile"]},
     "release_build": "release-source-tarball"}
```

`detect.py`:

```python
    def open_candidates(self, candidates, chosen_ci, chosen_release_build=()):
        """The candidates a repository has not acted on yet (D23, D28).

        A candidate is a hint that more of the standard fits this repository.
        Once the repository has chosen what answers it -- the CI block `ci-man`
        for `man-pages`, the build add-on `release-source-tarball` for an
        autotools tree -- the hint has been acted on. Detection cannot see the
        choice, so the caller passes the `ci` and `release_build` lists in.
        """
        served = {entry["id"] for entry in self.data.get("candidates", [])
                  if (entry.get("ci_block") and entry["ci_block"] in chosen_ci)
                  or (entry.get("release_build")
                      and entry["release_build"] in chosen_release_build)}
        return [c for c in candidates if c not in served]
```

`cli._prepare`: `result.candidates = detection.open_candidates(result.candidates, ci, config.get("release_build", []))`.

- [ ] **Step 3: Run, gate, commit**

`tests/test_detect.py tests/test_ci_man.py` pass; Full gate (+2).

```bash
git add skills/repo-infra/assets/detection.json skills/repo-infra/scripts/repo_infra tests/test_detect.py
git commit -m "detect: propose release-source-tarball for autotools repositories (D28)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
## Phase 6: documentation

### Task 10: RELEASING.md, release-flow.md, conventions.md, CHANGES.md, apply.md

Load the `repo-infra:writing-style` skill first. Every text below is the content to write; adjust wording only where the skill demands it, never the facts.

**Files:**
- Modify: `RELEASING.md`, `skills/repo-infra/references/release-flow.md`, `skills/repo-infra/references/conventions.md`, `CHANGES.md` (`## [Unreleased]` only), `commands/apply.md`
- Test: `tests/test_no_em_dash.py`, `tests/test_skill.py`, `tests/test_prose_skills.py` (existing; must stay green)

- [ ] **Step 1: RELEASING.md**

Replace lines 5-18 (the two halves) with:

```markdown
**1. Run the `Create release PR` workflow** (Actions → Create release PR →
Run workflow → bugfix / feature / major). It:

1. refuses when a check on the current `main` commit has already failed, when
   a release pull request is open, or when the latest release in `CHANGES.md`
   has no tag,
2. computes the next version from the tags and refuses if it already exists,
3. rolls the `CHANGES.md` `[Unreleased]` section into a dated version section
   and sets every file listed in `.github/repo-infra.json` to the same version,
4. builds the release (`release-build.yml`) and runs this repository's CI
   (`ci.yml`) on the `release/vX.Y.Z` branch,
5. drafts the release with every built file and opens the pull request.

Nothing is tagged or published yet. Closing the pull request cancels the release.

**2. Review and merge.** Nothing needs approving. The merge triggers the
publish workflow, which tags the commit that was built and publishes the draft.
```

Delete the section `## Why the release pull request needs an approval` (lines 29-64) and put in its place:

```markdown
## Why the release pull request merges without an approval

The ruleset requires two checks, `ci-passed` and `changelog-updated`, and
requires the branch to be up to date with `main`. `Create release PR` writes
both checks on the release branch itself, after it built and tested that
exact commit. The pull request's own runs still park in an approval-required
state, because `GITHUB_TOKEN` opened it; nobody needs to approve them, and
publishing deletes them.

If `main` moves before the merge, GitHub refuses the merge (`the head branch
is not up to date with the base branch`) and `ci-passed` turns red with
`main moved after vX.Y.Z was built; close this pull request and dispatch
Create release PR again`. Do that. Do not press **Update branch**: the new
head was neither built nor tested, and both checks turn red.

## Secrets

The release build and the CI run inside `Create release PR` get the
repository's secrets, so a build can sign a binary. No repository secret may
carry write access to the repository. A classic personal access token with
`repo` scope, typical for pushing to a Homebrew tap, breaks that rule.
```

Replace the section `## Releases that build before the merge` (lines 85-104) with:

```markdown
## When a release gets stuck

- Merge release pull requests with a merge commit. All three merge methods
  stay allowed, but after a squash or rebase `git describe` on `main` no
  longer finds the tag.
- `Create release PR` refuses with `vX.Y.Z is in CHANGES.md on main but has
  no tag` while the last release has no tag. If its publish run failed for
  another reason than the tree comparison, **Re-run failed jobs** on it. For
  a release that is already out under another tag, push `vX.Y.Z` by hand (the
  ruleset covers the branch, not tags). To abandon it, merge a pull request
  that moves its entries back under `[Unreleased]`.
- Publish fails with `main at <sha> does not match the release built from
  <head>` only when the up-to-date rule was off at the merge. It tags
  nothing. Abandon the release as above, then dispatch again.
- A tag pushed by hand for the newest released version, without a GitHub
  release, makes every publish run fail until the next release creates one.
```

- [ ] **Step 2: references/release-flow.md**

- Lines 10-17 (the two steps): the same content as RELEASING.md Step 1 above, in this file's voice.
- Delete `## The approval-required banner is expected` (lines 29-52). Put in its place `## Built and tested before the pull request exists (D28)`: the four jobs (`prepare`, `build`, `test`, `finish`) as in the spec's "The flow", the two check runs `finish` writes and why they satisfy the ruleset (required by context only, no app), the parked runs that nobody approves and that publish deletes, and the three layers of "`main` must not move under a release" (ruleset `strict_required_status_checks_policy`, `release-pr-current`, the tree comparison in publish's `create` path only).
- `## The guard fails fast, ...` (lines 54-65): it refuses only a check that already failed, names it, and does not wait or refuse a commit without checks, because `test` runs the same `ci.yml` on that commit plus the release changes. Keep the paragraph on why it is not redundant with the ruleset.
- `## ignoreCheckRunIds ...` (lines 67-94): replace "waits for itself" framing with: the guard ignores its own jobs and every job of every earlier attempt, which now includes the failed `build` and `test` jobs of an earlier dispatch; keep the smalti history paragraph.
- `## Recovery: re-run, never re-dispatch` (lines 107-127): drop the tag-exists paragraph and the "Without it, a whole-workflow re-run skips everything" sentence; say both kinds of re-run finish a stopped publish, publish add-ons skip what an earlier attempt uploaded, and the tree-comparison failure is the one case a re-run cannot fix.
- Replace `## Releases that build before the merge (release_build)` (lines 129-187) with `## What the build may do`: `release_build` names build add-ons (`release-source-tarball`), `release_build_local` adds `release-build-local.yml`; `release_files` and `release_assets` as now; `finish` refuses `.github/`, `CHANGES.md`, the version files and non-UTF-8 content; publish tags the head in `release-build.json`; the Homebrew window paragraph; the two refusals (open release pull request; untagged release, with `untaggedMessage`'s three ways out); **Update branch** turns both checks red; the next dispatch deletes stale drafts and the parked runs of closed release branches.
- `## Gitea packages` line 193-195: drop "so it needs `release_build`; `check` reports a conflict without it, and"; keep "`check` reports a conflict when `gitea_packages` lacks `url` or `owner`."
- `## Check these still hold`: replace the first bullet with two: "**A check run written by `GITHUB_TOKEN` satisfies a required context that names no app.** Open a release pull request and look at the merge box: `ci-passed` and `changelog-updated` must read as required and passed. If GitHub starts to demand the app, the ruleset needs `integration_id` for GitHub Actions." and "**The up-to-date rule refuses a merge whose head is behind.** Merge an unrelated pull request while a release pull request is open: the release pull request must show `the head branch is not up to date with the base branch`."

- [ ] **Step 3: references/conventions.md**

- Line 92-96, the `publish` bullet: replace the `["publish-source-tarball"]` sentences with: "`publish-crates-io` and `publish-gitea-packages` are the publish add-ons. The `make dist` tarball is no longer a publish add-on: it is the build add-on `release-source-tarball` (see `release_build`), a blocking prerequisite for converting any autotools repository that already publishes one."
- After the `publish_local` bullet add:

```markdown
- `release_build` -- the build add-ons the assembled `release-build.yml`
  runs on the release branch before the pull request exists (D28), by id
  (`manifest.json` `release_build_blocks`). `["release-source-tarball"]`
  builds the `make dist` tarball. Each add-on declares the asset name
  patterns it produces, and `release_assets` must list them: `finish` is a
  copied file and cannot know which add-ons are installed. `check` reports a
  missing pattern and `apply` adds it.
- `release_build_local` -- `true` adds the project's own
  `.github/workflows/release-build-local.yml` to `release-build.yml`.
- `release_assets`, `release_files` -- every file the release must carry, as
  name patterns, and the repository paths the build may rewrite (D26).
```

- Section title `## Project-owned workflows behind a fixed seam (D20, D25, D26)` becomes `(D20, D25, D28)`. Add rule 4 to the numbered list: "4. **Declare the input `ref` and check it out.** `on: workflow_call: inputs: ref`, and `ref: ${{ inputs.ref }}` on every `actions/checkout`. `Create release PR` runs `ci.yml` on the release branch and passes that commit here; a checkout without it tests `main` and reports the release as tested. `check` reports a missing input or checkout as `conflict` (`action-test-seam`, `ci-local-seam`, `release-build-local-seam`), and `apply` does not edit these files." After the list add: "These files get the repository's secrets (`secrets: inherit`) and must not ask for more permissions than `contents: read`; `ci.yml`'s callers grant no more."
- Replace `### release-build (D26)` (lines 302-324) with:

```markdown
### release-build-local (D28)

`"release_build_local": true` makes the assembled `release-build.yml` call
`.github/workflows/release-build-local.yml`, the project's own build. What it
must do:

- Trigger on `workflow_call` with the string inputs `version` and `ref`, and
  check out `inputs.ref` in every `actions/checkout`.
- Upload each file the release ships as an artifact whose name starts with
  `release-asset-`.
- Upload the repository files the build rewrote, for example a Homebrew
  formula, as one artifact named `release-files`. Its paths are repository
  paths, and each one is listed in `release_files`.
- Ask for no more than `contents: read`.

Upload `release-files` from a staging directory whose tree holds the
repository paths, because `upload-artifact` strips the common parent
directory: uploading `Formula/mdmost.rb` directly yields `mdmost.rb`, which is
refused as undeclared. Files with the same name in several `release-asset-*`
artifacts overwrite each other.

`build` and `test` run in the same workflow run and share one artifact
namespace, so `release-asset-*` and `release-files` are reserved for the
build: `check` reports a `conflict` when `ci-local.yml` or `action-test.yml`
uploads an artifact with such a name. A file named `release-build.json` is
refused: that name is the build record `finish` writes itself.

The build and the CI run get the repository's secrets. No repository secret
may carry write access to the repository; a classic personal access token
with `repo` scope breaks that rule.
```

- [ ] **Step 4: CHANGES.md `## [Unreleased]`** (D24 to D27 never shipped, so their entries are rewritten, not followed by corrections)

`### New`: replace the `"release_build": true` bullet with:

```markdown
- **Create release PR** builds the release and runs the CI on the release branch before it opens the pull request, so the pull request merges without an **Approve workflows to run** click. Build steps come from `release_build` add-ons and the project's own `.github/workflows/release-build-local.yml`; files such as a Homebrew formula change in the pull request, and publishing tags the commit that was built.
- The `release-source-tarball` build add-on attaches the `make dist` tarball, built before the merge. It replaces the `publish-source-tarball` publish add-on, and `apply` moves the setting.
```

`### Changed`: replace the `changelog-updated` bullet, the re-run bullet and the "Approve workflows to run" bullet with:

```markdown
- The branch ruleset now requires a pull request to be up to date with `main` before it merges; behind pull requests need **Update branch** first. A release pull request that `main` moved past cannot merge and shows a red `ci-passed`: "main moved after vX.Y.Z was built; close this pull request and dispatch Create release PR again".
- `Create release PR` no longer waits for the checks on `main`; it refuses only a check that already failed.
- Re-running the publish workflow no longer fails on a crate an earlier attempt already uploaded, and both **Re-run failed jobs** and a whole-workflow re-run finish a stopped release. Publish refuses to tag when `main` does not match the release that was built.
- The release build and the CI run get the repository's secrets. No repository secret may carry write access to the repository.
- `check` reports `ci-local.yml`, `action-test.yml` and `release-build-local.yml` as a conflict when they do not declare the input `ref` or do not check it out.
```

`### Fixed`: replace the `release-pr` v4 bullet with nothing (the variant and the v4 comment change never shipped; `release-pr` is v5 in this release). Keep the Cargo.lock, worktree and `[Unreleased]` heading bullets.

- [ ] **Step 5: commands/apply.md**

After step 2's code block add:

```markdown
   When the upgrade installs `release-pr` v5 (D28), write the body with
   `--body` instead of `--fill`, and include this sentence: "From this
   change on, the release build and the CI run inside Create release PR see
   every repository secret; no secret may carry write access to this
   repository." When `check` reported `ci-local-seam`, `action-test-seam` or
   `release-build-local-seam`, say in the body what the file needs:
   `on: workflow_call: inputs: ref` and `ref: ${{ inputs.ref }}` on every
   `actions/checkout`. `apply` never edits those files.
```

and a section before `## If it exits with NeedsMerge`:

```markdown
## Migration to the one release flow (D28)

`apply` refuses while a release is in progress (`release-in-progress`): let
the open release pull request merge and publish, or close it, first. The
migration items (`release-build-rename`, `release-build-config`,
`publish-source-tarball`, `release-assets`, `cargo-lock-version-files`) are
one commit: they edit `.github/repo-infra.json`, and `release-build-rename`
renames D26's `release-build.yml` to `release-build-local.yml` with `git mv`
and no content change. After it, `apply` installs the assembled
`release-build.yml`. Afterwards apply `required-checks` (confirm first): the
ruleset gains the up-to-date rule.
```

- [ ] **Step 6: Run and commit**

Run the Full gate; `grep -rnP '\x{2014}' RELEASING.md commands skills | head` prints nothing. Then:

```bash
git add RELEASING.md CHANGES.md commands/apply.md skills/repo-infra/references
git commit -m "Docs: one release flow, tested before the merge (D28)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Phase 7: the proofs (owner-gated)

Every step that writes to GitHub needs the owner's go first: pushes, pull requests, merges, dispatches, ruleset and settings changes. `RI=/scratch/oetiker/claude-worktrees/repo-infra-spec-d24-d27`. Record each result (run URL, pass or fail) in the pull request description of the repository under test as it happens. A failed proof stops the plan: fix repo-infra on `spec/d24-d27` with its gates, re-install with `apply`, prove again.

### Task 11: proof 2, an autotools release in `oetiker/repo-infra-spike`

- [ ] **Step 1: Check out the spike** (read-only)

```bash
git clone https://github.com/oetiker/repo-infra-spike /scratch/oetiker/claude-worktrees/repo-infra-spike
cd /scratch/oetiker/claude-worktrees/repo-infra-spike
python3 "$RI/skills/repo-infra/scripts/repo_infra" check --repo oetiker/repo-infra-spike
```

Read the report. It names what this branch would install; the spike already ran the standard for the zero-click spikes of 2026-09-30.

- [ ] **Step 2: A minimal autotools project** on a branch `proof/autotools`

`configure.ac`:

```
AC_INIT([spike], m4_esyscmd_s([cat VERSION]))
AM_INIT_AUTOMAKE([foreign])
AC_CONFIG_FILES([Makefile])
AC_OUTPUT
```

`Makefile.am`: `EXTRA_DIST = VERSION`. `bootstrap` (mode 0755): `#!/bin/sh` / `exec autoreconf --install`. `VERSION`: the spike's current version. `.github/repo-infra.json` gains `"release_build": ["release-source-tarball"]`, `"release_assets": ["*.tar.gz"]`, and a `version_files` entry for `VERSION` (detection.json's `perl-autotools` entry). Check locally: `./bootstrap && ./configure && make dist` leaves one `spike-<version>.tar.gz`; remove it and the generated files.

- [ ] **Step 3: Install the flow from this branch**

```bash
python3 "$RI/skills/repo-infra/scripts/repo_infra" apply --repo oetiker/repo-infra-spike
python3 "$RI/skills/repo-infra/scripts/repo_infra" check --repo oetiker/repo-infra-spike
```

Expected: every file item `ok`; `required-checks` `outdated` until Step 5.

- [ ] **Step 4 (owner): push, open the pull request, merge it.**
- [ ] **Step 5 (owner): `apply --item required-checks`**, then `check` reads `required-checks ok`.
- [ ] **Step 6 (owner): dispatch Create release PR (bugfix).** Expected: `prepare`, `build` (with `release-source-tarball`), `test` and `finish` green; the draft carries `spike-<version>.tar.gz` and `release-build.json` with `base` and `head`; the pull request shows `ci-passed` and `changelog-updated` green with no approval click.
- [ ] **Step 7 (owner): merge.** Expected: publish tags the recorded head, the public release carries the tarball and no `release-build.json`, and `gh run list -R oetiker/repo-infra-spike --branch release/v<version>` lists no parked run.

### Task 12: proofs 3 and 4 in `oetiker/mdmost`

- [ ] **Step 1: A worktree for the upgrade** (read-only for GitHub)

```bash
git -C /home/oetiker/checkouts/mdmost fetch origin
git -C /home/oetiker/checkouts/mdmost worktree add /scratch/oetiker/claude-worktrees/mdmost-d28 -b repo-infra/apply origin/main
```

If a local branch `repo-infra/apply` already exists, ask the owner before reusing or deleting it.

- [ ] **Step 2: Read the report**

```bash
cd /scratch/oetiker/claude-worktrees/mdmost-d28
python3 "$RI/skills/repo-infra/scripts/repo_infra" check --repo oetiker/mdmost
```

Expected: `release-build-rename` and `release-build-config` outdated; `release-pr` conflict (the file carries the never-released marker `release-pr-build v1`); `ci`, the CI blocks, `changelog`, `workflow-lib`, `release-publish` outdated; `release-build` absent from the list (superseded by the rename); `required-checks` outdated; `ci-local-seam` conflict unless `ci-local.yml` already takes `ref`; `cargo-lock-version-files` missing if mdmost's `version_files` lacks them. No `release-in-progress`; if it appears, stop until that release is finished.

- [ ] **Step 3: The project-owned files**

Give `.github/workflows/ci-local.yml` the input and the ref (keep everything else):

```yaml
on:
  workflow_call:
    inputs:
      ref:
        type: string
        required: false
        default: ''
```

and `with: ref: ${{ inputs.ref }}` on each of its `actions/checkout` steps. Check that `release-build.yml` (D26's) checks out `inputs.ref` everywhere and asks for no more than `contents: read`; `check` names it as `release-build-local-seam` if not.

- [ ] **Step 4 (ask first, local destructive): replace `release-pr.yml` whole.** `git rm .github/workflows/release-pr.yml`, commit "Remove the never-released release-pr-build workflow", so `apply` installs `release-pr` v5 as missing.

- [ ] **Step 5: Apply and verify**

```bash
python3 "$RI/skills/repo-infra/scripts/repo_infra" apply --repo oetiker/mdmost
git show --name-status -M HEAD~0 | head
python3 "$RI/skills/repo-infra/scripts/repo_infra" check --repo oetiker/mdmost
```

Expected: one migration commit with `R100 .github/workflows/release-build.yml -> .github/workflows/release-build-local.yml`; then every file item `ok`, only `required-checks` outdated. Resolve any `NeedsMerge` as `commands/apply.md` says.

- [ ] **Step 6 (owner): push, open the pull request** with the secrets sentence from `commands/apply.md`; **merge** after `ci-passed` and `changelog-updated` are green; then **`apply --item required-checks`**.

- [ ] **Step 7: Proof 3** (each dispatch and merge by the owner)
  - [ ] A release merges without an approval click; the tag sits on the recorded head; the Gitea upload and the Homebrew bottle work as in v0.5.0; `gh run list -R oetiker/mdmost --branch release/vX.Y.Z` shows no parked run afterwards.
  - [ ] An unrelated pull request merges while the release pull request is open: the release pull request is refused by the ruleset and shows the red `ci-passed` with the stale text (from `release-pr-current`); close it, dispatch again, release.
  - [ ] An unrelated pull request merges while `build` runs: `finish` opens the pull request with a red `ci-passed` and the run fails naming it.
  - [ ] With the up-to-date rule switched off for this test (owner, Settings → Rules), a release pull request merged after `main` moved: publish fails with the tree text, tags nothing; the next dispatch is refused with the untagged text; merge the abandon pull request, dispatch, release. Switch the rule on again (`apply --item required-checks`) and confirm `check` reads it `ok`.

- [ ] **Step 8: Proof 4** (the D26/D27 items of mdmost #26 that still apply)
  - [ ] **Update branch** on a release pull request turns `ci-passed` and `changelog-updated` red (approve the parked runs to see `ci-passed` report).
  - [ ] A dispatch is refused while a release pull request is open, and while a merged release is unpublished (untagged text).
  - [ ] A publish that fails after the tag finishes on **Re-run failed jobs** (force it with a temporary wrong `GITEA_PACKAGE_USER`, owner).
  - [ ] `finish` refuses a build that drops a `release_assets` file (temporary branch change).
  - [ ] A Gitea re-run reports the 409s and stays green.
  - [ ] A `~` version installs through apt; `brew install oetiker/mdmost/mdmost` pours the bottle.

## Phase 8: merge order

### Task 13: merge, then proof 1

- [ ] **Step 1:** Rebase `spec/d24-d27` onto `origin/main`, run the Full gate, and (owner) push and open the repo-infra pull request with the proof results by link and the CHANGES entries.
- [ ] **Step 2 (owner):** merge it. repo-infra's own `ci.yml`, `release-pr.yml` and `release-build.yml` are already the D28 files (self-render); apply `required-checks` to `oposs/repo-infra` (owner) so its ruleset has the up-to-date rule.
- [ ] **Step 3: Proof 1 (owner dispatch):** repo-infra releases through the new flow: the empty `release-build.yml` runs only `release-version`, the release has no assets, the pull request merges without an approval click.
- [ ] **Step 4:** Re-run `apply` in mdmost against the released plugin so its markers name released versions; merge that pull request (owner).

