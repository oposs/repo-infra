# D24-D27 and the mdmost Conversion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teach the standard D24 (scoped Rust workspaces), D25 (the `ci-local` seam), D26 (the release pull request builds the release) and D27 (Gitea package publishing), prove each in `oetiker/mdmost`, then merge repo-infra's pull request before mdmost's.

**Architecture:** Every decision that can be wrong at run time is a pure function in the workflow library (`skills/repo-infra/assets/workflows/lib/*.js`), tested table-driven with `node --test`; the YAML assets only fetch state from the API, call the function and act on its answer. The Python side (`assemble.py`, `state.py`, `apply.py`, `cli.py`) learns three config keys (`ci_local`, `release_build`, `release_files`), one optional seam block, and one asset variant (`release-pr-build`, rendered to the same target as `release-pr`). mdmost is converted on its `repo-infra/apply` branch and carries the project-owned halves: `.github/workflows/ci-local.yml` and `.github/workflows/release-build.yml`.

**Tech Stack:** Python 3.11+ (pytest, PyYAML), Node 22 (`node:test`), GitHub Actions (`actions/github-script@v9`), cargo metadata, Homebrew, cargo-deb, cargo-generate-rpm, Gitea 1.27 package registry, nginx.

**Spec:** `docs/superpowers/specs/2026-09-29-mdmost-conversion-design.md` (D24-D27). Read it before any task; section names below refer to it.

## Global Constraints

- repo-infra work happens in the worktree `/scratch/oetiker/claude-worktrees/repo-infra-spec-d24-d27`, branch `spec/d24-d27`. Never touch `~/checkouts/repo-infra` (other sessions work there). Never push `main` of either repository; `main` moves only when a pull request merges.
- mdmost work happens in a worktree `/scratch/oetiker/claude-worktrees/mdmost-repo-infra`, branch `repo-infra/apply` (the name `apply.py` hard-codes as `BRANCH`). Create it with `git -C /home/oetiker/checkouts/mdmost worktree add /scratch/oetiker/claude-worktrees/mdmost-repo-infra -b repo-infra/apply origin/main`.
- **repo-infra is PUBLIC.** No internal host name, IP address, ssh alias or nginx snippet in any file of it, in a commit message, or in a pull request text. `https://gitea.oetiker.ch` and the owner `oposs` are public and may appear.
- Version changes, all made once, in the task named:
  - `workflow-lib` v4 -> v5 (Task 1; every later lib file is born at v5)
  - `ci-rust` v1 -> v2, jobs `["rust-plan", "rust-check", "rust-test"]` (Task 2)
  - new CI block `ci-local` v1, jobs `["ci-local"]`, `"optional": true`, `"seam": "ci_local"` (Task 3)
  - new asset `release-pr-build` v1, source `workflows/release-pr-build.yml`, target `.github/workflows/release-pr.yml`, `"variant_of": "release-pr"`, `"when": "release_build"`; `release-pr` stays v3 (Task 6)
  - `changelog` v2 -> v3 (Task 8)
  - frame `release-publish` v3 -> v4, `publish-source-tarball` v2 -> v3, `publish-crates-io` v1 -> v2 (Task 9)
  - new publish block `publish-gitea-packages` v1, jobs `["publish-gitea-packages"]`, `"assets": []` (Task 11)
  - manifest `actions` gains `"actions/download-artifact": "v8"` (Task 6)
- Fixed names from the spec, verbatim: config keys `rust` (`lint`, `test`, `tested_elsewhere`), `ci_local`, `release_build`, `release_files`, `release_assets`, `gitea_packages` (`url`, `owner`, `debian.distribution`, `debian.component`, `rpm.group`); files `.github/workflows/ci-local.yml`, `.github/workflows/release-build.yml`; artifacts `release-asset-*` and `release-files`; release asset `release-build.json`; commit status context `release-built`; secret `GITEA_PACKAGE_TOKEN`, variable `GITEA_PACKAGE_USER`.
- The bot login the gates trust is exactly `github-actions[bot]`.
- Refusal texts quoted in the spec are used verbatim:
  - `vX.Y.Z is in CHANGES.md on main but has no tag`
  - `the release branch changed after it was built (the Update branch button does this); close this pull request and dispatch Create release PR again`
- Assets are literal files: no substitution token (D15, D20). The only generated text is `needs:` and finalize's `expected` list. No `paths:` filter on a CI block or on `changelog.yml` (D13). Every job in an asset sets `timeout-minutes` (a `uses:` job cannot, and gets none).
- Every `uses: owner/action@vN` in an asset must match `manifest.json` `actions` (`tests/test_blocks.py`).
- No em dash (U+2014) in anything this plan creates (`tests/test_no_em_dash.py`). Write `--` or rephrase.
- repo-infra's own `.github/` is the assembler's output (`tests/test_self_render.py`). After changing any asset that repo-infra itself installs (workflow lib, `changelog.yml`, the publish frame and finalize), re-render with this exact command from the worktree root, then run the suite:

  ```bash
  python3 -c "import json,pathlib,sys; sys.path.insert(0,'skills/repo-infra/scripts'); from repo_infra.assemble import render_all; from repo_infra.detect import Detection; A=pathlib.Path('skills/repo-infra/assets'); m=json.loads((A/'manifest.json').read_text()); r=Detection.load(A/'detection.json').detect('.'); [pathlib.Path(p).write_text(t, encoding='utf-8') for p,t in render_all(A,r,m).items()]"
  ```

- Gates (run from the repo-infra worktree root; the pytest temp dir must not be `/tmp`):
  - JS: `node --test skills/repo-infra/assets/workflows/lib/*.test.js`
  - Python: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests`
  - Full: `mkdir -p /scratch/oetiker/claude-tmp/pytest && TMPDIR=/scratch/oetiker/claude-tmp/pytest make check`
- Cargo in mdmost: at most 4 jobs (`-j 4`), own target dir `CARGO_TARGET_DIR=/scratch/oetiker/cargo-target-mdmost-repo-infra`.
- `CHANGES.md` of repo-infra: bullets under `## [Unreleased]` (`### New` / `### Changed`), readers are users and administrators, three sentences at most, no release header. Load the `repo-infra:writing-style` skill before writing any prose (docs, CHANGES, commit messages).
- Every ssh command to a server needs the owner's explicit confirmation, one command at a time. Tasks 13 and 14 are owner-run; the agent prepares and verifies from outside.
- English in code, comments, docs and commit messages.

## Review Focus

1. **A release whose publish run fails half way.** Every state of the tag/draft machine (tag present or absent x published, draft, none, several x `release-build.json` present or absent x peeled tag commit) must end in `done`, a resumable state, or a failure that names the state. Pinned by the table in Task 5 and the harness test in Task 9.
2. **A release pull request whose branch moved after the build** (the **Update branch** button). The changelog gate must go red even when someone adds `no-changelog`. Pinned in Task 8.
3. **A path in `release_files` that reaches a protected file through normalisation** (`./CHANGES.md`, `Formula/../CHANGES.md`, `.github//repo-infra.json`, an absolute path). `check` and `finish` must both refuse. Pinned in Task 4 (JS) and Task 7 (Python).
4. **A Rust repository already on the standard whose default members differ from its members.** Its first upgrade to `ci-rust` v2 must go red with a message that names the members and the key to add, never green with fewer tests. Pinned in Task 1.
5. **A Gitea re-run after a partial upload.** A 409 for a `.deb` passes only on equal SHA-256; a 409 for an `.rpm` passes on equal file name (name, version-release, arch) and says the content was not compared. Pinned in Task 10.

---

## Phase 0: the gate

### Task 0: Homebrew bottle from a `file://` tarball (spike, mdmost)

The spec's D26 bottle half rests on this. If it fails, stop, report to the owner, and revise D26 before any other task.

**Files:**
- Create (throwaway, never merged): `.github/workflows/spike-bottle.yml` in mdmost, on branch `spike/file-bottle`

- [ ] **Step 1: Create the spike branch in its own worktree**

```bash
git -C /home/oetiker/checkouts/mdmost fetch origin
git -C /home/oetiker/checkouts/mdmost worktree add /scratch/oetiker/claude-worktrees/mdmost-spike-bottle -b spike/file-bottle origin/main
```

- [ ] **Step 2: Write the spike workflow**

It builds the aarch64-apple-darwin tarball the way `release.yml` does, writes a formula into a local tap whose `url` is `file://` with the tarball's real sha256, and runs the two commands `release-build.yml` will run.

```yaml
name: Spike -- bottle from a file:// tarball

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  bottle:
    runs-on: macos-14
    timeout-minutes: 40
    env:
      HOMEBREW_NO_AUTO_UPDATE: 1
      HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK: 1
      VERSION: 0.0.0-spike
    steps:
      - uses: actions/checkout@v7

      - uses: dtolnay/rust-toolchain@stable
        with:
          targets: aarch64-apple-darwin

      - name: Build the tarball as release.yml does
        run: |
          set -euo pipefail
          brew install pandoc
          make man
          cargo build --release --target aarch64-apple-darwin
          mkdir -p dist staging/mdmost/man
          cp target/aarch64-apple-darwin/release/mdmost staging/mdmost/
          cp man/mdmost.1 staging/mdmost/man/
          cp README.md LICENSE staging/mdmost/
          cp -R integrations staging/mdmost/
          tar -czf "dist/mdmost-${VERSION}-aarch64-apple-darwin.tar.gz" -C staging mdmost

      - uses: Homebrew/actions/setup-homebrew@main

      - name: Local tap with a file:// url
        run: |
          set -euo pipefail
          TARBALL="$PWD/dist/mdmost-${VERSION}-aarch64-apple-darwin.tar.gz"
          SHA=$(shasum -a 256 "$TARBALL" | cut -d' ' -f1)
          brew tap-new --no-git spike/local
          TAP="$(brew --repository)/Library/Taps/spike/homebrew-local"
          # The real formula with its url and sha256 rewritten, and the bottle
          # block emptied: exactly what release-build.yml will do.
          sed -e "s|^  version \".*\"|  version \"${VERSION}\"|" \
              -e "s|url \"https://github.com/oetiker/mdmost/releases/download/v#{version}/mdmost-#{version}-aarch64-apple-darwin.tar.gz\"|url \"file://${TARBALL}\"|" \
              -e "s|sha256 \"[0-9a-f]*\" # mac-arm|sha256 \"${SHA}\" # mac-arm|" \
              Formula/mdmost.rb \
            | awk '/# BOTTLE-START/{print; skip=1; next} /# BOTTLE-END/{skip=0} !skip' \
            > "$TAP/Formula/mdmost.rb"
          grep -n 'file://' "$TAP/Formula/mdmost.rb"
          brew trust --formula spike/local/mdmost || true

      - name: Build the bottle
        run: |
          set -euo pipefail
          brew install --build-bottle spike/local/mdmost
          brew bottle --json --no-rebuild \
            --root-url="https://github.com/oetiker/mdmost/releases/download/v${VERSION}" \
            spike/local/mdmost
          ls -la ./*.bottle.*
          cat ./*.bottle.json
          jq -r '.[].bottle.tags[] | "\(.local_filename) -> \(.filename)"' ./*.bottle.json

      - uses: actions/upload-artifact@v7
        with:
          name: spike-bottle
          path: |
            ./*.bottle.tar.gz
            ./*.bottle.json
```

- [ ] **Step 3: Push the spike branch and dispatch it**

Pushing a non-main branch to origin is allowed; ask the owner before the push anyway, since it is outward-facing.

```bash
cd /scratch/oetiker/claude-worktrees/mdmost-spike-bottle
git add .github/workflows/spike-bottle.yml
git commit -m "Spike: bottle from a file:// tarball (throwaway)"
git push -u origin spike/file-bottle
gh workflow run spike-bottle.yml --ref spike/file-bottle -R oetiker/mdmost
gh run watch -R oetiker/mdmost "$(gh run list -R oetiker/mdmost -w spike-bottle.yml -L1 --json databaseId -q '.[0].databaseId')"
```

A `workflow_dispatch` workflow must exist on the default branch to be dispatched. If `gh workflow run` answers `could not find any workflows named spike-bottle.yml`, add `push: branches: [spike/file-bottle]` to `on:`, push again, and use that run.

- [ ] **Step 4: Read the result and record it**

PASS means: the log shows `brew install --build-bottle` pouring from `file://`, `brew bottle` writing `mdmost--0.0.0-spike.arm64_sonoma.bottle.tar.gz` and a json whose `filename` is `mdmost-0.0.0-spike.arm64_sonoma.bottle.tar.gz`, and the root url printed is the GitHub one.

FAIL means any of: Homebrew refuses a `file://` url, refuses a formula from a local tap, or `brew bottle` needs the formula's url to be https. Then stop the plan, report the exact error to the owner, and revise D26's bottle half first.

Record the outcome (run URL, PASS/FAIL, the two file names) in the handoff, not in the repository.

- [ ] **Step 5: Clean up after the owner has seen the result**

Ask before each: `git push origin --delete spike/file-bottle`, `git -C /home/oetiker/checkouts/mdmost worktree remove /scratch/oetiker/claude-worktrees/mdmost-spike-bottle`, `git -C /home/oetiker/checkouts/mdmost branch -D spike/file-bottle`.

---
## Phase 1: CI (D24, D25)

### Task 1: `rust-plan.js`, the workspace plan as a pure function (D24)

**Files:**
- Create: `skills/repo-infra/assets/workflows/lib/rust-plan.js`
- Create: `skills/repo-infra/assets/workflows/lib/rust-plan.test.js`
- Modify: every file in `skills/repo-infra/assets/workflows/lib/` (marker v4 -> v5)
- Modify: `skills/repo-infra/assets/manifest.json` (`workflow-lib` `"version": 5`)
- Modify (re-render): `.github/workflows/lib/*`

**Interfaces:**
- Produces: `rustPlan(config, metadata) -> { lint: string[], test: string[] }`, throws `Error` with the user-facing message. `config` is the parsed `.github/repo-infra.json` (or `{}`); `metadata` is the parsed output of `cargo metadata --no-deps --format-version 1`. An entry `''` means "no `-p`, today's workspace-wide command".

- [ ] **Step 1: Bump the library to v5**

```bash
cd /scratch/oetiker/claude-worktrees/repo-infra-spec-d24-d27
sed -i 's|^// repo-infra: workflow-lib v4$|// repo-infra: workflow-lib v5|' skills/repo-infra/assets/workflows/lib/*.js
grep -L 'workflow-lib v5' skills/repo-infra/assets/workflows/lib/*.js   # expect no output
```

In `manifest.json` change `"workflow-lib": {"version": 4,` to `"version": 5,`.

- [ ] **Step 2: Write the failing test**

`skills/repo-infra/assets/workflows/lib/rust-plan.test.js`:

```js
// repo-infra: workflow-lib v5
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { rustPlan } = require('./rust-plan.js');

// cargo metadata --no-deps for a workspace shaped like mdmost's: a root
// [package] plus two vendored members. The root [package] makes mdmost the
// only default member, so a bare `cargo test` skips the other two.
function metadata(members, defaults = members) {
  const id = (name) => `path+file:///w/${name}#${name}@1.0.0`;
  return {
    packages: members.map((name) => ({ name, id: id(name) })),
    workspace_members: members.map(id),
    workspace_default_members: defaults.map(id),
  };
}
const MDMOST = metadata(['mdmost', 'pulldown-latex', 'syntect'], ['mdmost']);
const RUST = {
  lint: ['mdmost'],
  test: ['mdmost', 'pulldown-latex'],
  tested_elsewhere: ['syntect'],
};

test('a single crate without the key runs the workspace-wide commands', () => {
  assert.deepEqual(rustPlan({}, metadata(['one'])), { lint: [''], test: [''] });
});

test('a virtual workspace without default-members needs no key', () => {
  assert.deepEqual(rustPlan({}, metadata(['a', 'b'])), { lint: [''], test: [''] });
});

test('default members that differ from members fail without the key', () => {
  // The silent gap D24 closes: bare `cargo test` would run mdmost alone.
  assert.throws(() => rustPlan({}, MDMOST), (e) => {
    assert.match(e.message, /pulldown-latex, syntect/);
    assert.match(e.message, /"rust"/);
    return true;
  });
});

test('the declared lists become the matrix', () => {
  assert.deepEqual(rustPlan({ rust: RUST }, MDMOST), {
    lint: ['mdmost'],
    test: ['mdmost', 'pulldown-latex'],
  });
});

test('lint may be left out and then lints the whole workspace', () => {
  const { lint, ...rest } = RUST;
  assert.deepEqual(rustPlan({ rust: rest }, MDMOST).lint, ['']);
});

test('a name that is not a workspace member fails and is named', () => {
  const rust = { ...RUST, test: ['mdmost', 'pulldown-latx'] };
  assert.throws(() => rustPlan({ rust }, MDMOST), /pulldown-latx/);
});

test('a misspelt tested_elsewhere entry fails too', () => {
  const rust = { ...RUST, tested_elsewhere: ['syntec'] };
  assert.throws(() => rustPlan({ rust }, MDMOST), /syntec\b/);
});

test('a member in neither test nor tested_elsewhere fails and is named', () => {
  const rust = { ...RUST, tested_elsewhere: [] };
  assert.throws(() => rustPlan({ rust }, MDMOST), (e) => {
    assert.match(e.message, /syntect/);
    assert.match(e.message, /neither/);
    return true;
  });
});

test('a missing test list fails', () => {
  const { test: _t, ...rest } = RUST;
  assert.throws(() => rustPlan({ rust: rest }, MDMOST), /"test"/);
});

test('an empty test list fails', () => {
  assert.throws(() => rustPlan({ rust: { ...RUST, test: [] } }, MDMOST), /"test"/);
});

test('an empty lint list fails', () => {
  assert.throws(() => rustPlan({ rust: { ...RUST, lint: [] } }, MDMOST), /"lint"/);
});

test('a cargo without workspace_default_members fails with the version it needs', () => {
  const old = { ...metadata(['one']) };
  delete old.workspace_default_members;
  assert.throws(() => rustPlan({}, old), /1\.71/);
});
```

- [ ] **Step 3: Run it to verify it fails**

Run: `node --test skills/repo-infra/assets/workflows/lib/rust-plan.test.js`
Expected: FAIL with `Cannot find module './rust-plan.js'`

- [ ] **Step 4: Write the implementation**

`skills/repo-infra/assets/workflows/lib/rust-plan.js`:

```js
// repo-infra: workflow-lib v5
'use strict';

// Which workspace members ci-rust lints and tests (D24).
//
// A bare `cargo test` runs the default members only. With a root [package],
// or with `default-members`, that is not every member, and the others' tests
// stop running without an error. So a workspace like that must say, in
// .github/repo-infra.json, which crates are its own and where each one's
// tests run. This function is the whole rule; the rust-plan job only feeds it
// `cargo metadata --no-deps` and turns its answer into matrix entries.
//
// An entry '' means "no -p": today's workspace-wide command.

function names(metadata, ids) {
  const byId = new Map(metadata.packages.map((p) => [p.id, p.name]));
  return ids.map((id) => byId.get(id) || id);
}

function list(rust, key) {
  const value = rust[key];
  if (value === undefined) return undefined;
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error(
      `.github/repo-infra.json: "rust"."${key}" must list at least one crate`
      + (key === 'test' ? '; "no tests" is not a configuration the standard offers' : ''),
    );
  }
  return value;
}

function rustPlan(config, metadata) {
  if (!Array.isArray(metadata.workspace_default_members)) {
    throw new Error(
      'cargo metadata reports no workspace_default_members; cargo 1.71 or later is needed',
    );
  }
  const members = names(metadata, metadata.workspace_members).sort();
  const defaults = names(metadata, metadata.workspace_default_members).sort();
  const rust = (config || {}).rust;

  if (rust === undefined) {
    const skipped = members.filter((m) => !defaults.includes(m));
    if (skipped.length > 0) {
      throw new Error(
        `a bare cargo test runs ${defaults.join(', ')} only and skips `
        + `${skipped.join(', ')}. Add a "rust" key to .github/repo-infra.json `
        + 'with "lint", "test" and "tested_elsewhere" (references/conventions.md).',
      );
    }
    return { lint: [''], test: [''] };
  }

  const test = list(rust, 'test');
  if (test === undefined) {
    throw new Error('.github/repo-infra.json: "rust" needs a "test" list');
  }
  const lint = list(rust, 'lint');
  const elsewhere = rust.tested_elsewhere || [];

  const unknown = [...(lint || []), ...test, ...elsewhere]
    .filter((name) => !members.includes(name));
  if (unknown.length > 0) {
    throw new Error(
      `.github/repo-infra.json "rust" names ${[...new Set(unknown)].join(', ')}, `
      + `which is not a workspace member (members: ${members.join(', ')})`,
    );
  }

  const untested = members.filter((m) => !test.includes(m) && !elsewhere.includes(m));
  if (untested.length > 0) {
    throw new Error(
      `${untested.join(', ')} is in neither "rust"."test" nor `
      + '"rust"."tested_elsewhere" in .github/repo-infra.json; its tests would not run',
    );
  }

  return { lint: lint || [''], test };
}

module.exports = { rustPlan };
```

- [ ] **Step 5: Run the JS suite**

Run: `node --test skills/repo-infra/assets/workflows/lib/*.test.js`
Expected: PASS, 12 more tests than before.

- [ ] **Step 6: Re-render repo-infra's own `.github/` and run the Python suite**

Run the re-render command from Global Constraints, then `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests`.
Expected: PASS. `git status` shows `.github/workflows/lib/rust-plan.js`, `rust-plan.test.js` and the v5 marker on every other lib file.

- [ ] **Step 7: Commit**

```bash
git add skills/repo-infra/assets/workflows/lib skills/repo-infra/assets/manifest.json .github/workflows/lib
git commit -m "workflow-lib v5: rust-plan decides which crates ci-rust lints and tests (D24)"
```

---

### Task 2: `ci-rust` v2 runs the plan as a matrix (D24)

**Files:**
- Modify: `skills/repo-infra/assets/ci/ci-rust.yml`
- Modify: `skills/repo-infra/assets/manifest.json` (`ci-rust`)
- Create: `tests/test_ci_rust.py`

**Interfaces:**
- Consumes: `rustPlan` from Task 1, required as `${GITHUB_WORKSPACE}/.github/workflows/lib/rust-plan.js`.
- Produces: jobs `rust-plan` (outputs `lint`, `test`, both JSON arrays), `rust-check` and `rust-test` (matrix key `package`).

- [ ] **Step 1: Write the failing test**

`tests/test_ci_rust.py`:

```python
"""ci-rust v2 (D24): a planned matrix instead of one workspace-wide run."""

import json
import pathlib

import yaml

from repo_infra.assemble import assemble_ci

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))


def jobs():
    return yaml.safe_load(assemble_ci(ASSETS, ["ci-rust"], MANIFEST))["jobs"]


def run_lines(job):
    return "\n".join(step.get("run", "") for step in job["steps"])


def test_the_plan_is_a_required_job():
    # If rust-plan fails, both matrix jobs are skipped, and ci-passed counts a
    # skipped need as green. rust-plan in ci-passed's needs is what stops a
    # run whose Rust checks never ran from going green.
    assert jobs()["ci-passed"]["needs"] == ["rust-plan", "rust-check", "rust-test"]


def test_the_matrix_jobs_wait_for_the_plan_and_read_its_lists():
    j = jobs()
    for name, output in (("rust-check", "lint"), ("rust-test", "test")):
        assert j[name]["needs"] == "rust-plan"
        assert j[name]["strategy"]["matrix"]["package"] == (
            "${{ fromJSON(needs.rust-plan.outputs.%s) }}" % output)
        assert j[name]["strategy"]["fail-fast"] is False


def test_the_plan_reads_cargo_metadata_without_resolving_dependencies():
    assert "cargo metadata --no-deps --format-version 1" in run_lines(jobs()["rust-plan"])


def test_the_plan_calls_the_library_function():
    script = next(s["with"]["script"] for s in jobs()["rust-plan"]["steps"]
                  if s.get("id") == "plan")
    assert "rust-plan.js" in script
    assert "core.setFailed" in script


def test_clippy_on_a_named_package_skips_the_other_members():
    # clippy-driver replaces rustc for every workspace member regardless of
    # -p, so without --no-deps the vendored crates are linted anyway.
    run = run_lines(jobs()["rust-check"])
    assert 'cargo clippy --all-targets -p "$PACKAGE" --no-deps -- -D warnings' in run
    assert "cargo clippy --all-targets -- -D warnings" in run


def test_fmt_and_test_take_the_package_only_when_one_is_named():
    assert 'cargo fmt --check ${PACKAGE:+-p "$PACKAGE"}' in run_lines(jobs()["rust-check"])
    assert 'cargo test ${PACKAGE:+-p "$PACKAGE"}' in run_lines(jobs()["rust-test"])


def test_the_package_reaches_the_shell_through_env_not_interpolation():
    # A crate name interpolated into `run:` would be shell code from a config
    # file; env keeps it a value.
    for name in ("rust-check", "rust-test"):
        assert "${{ matrix.package }}" not in run_lines(jobs()[name])
        assert jobs()[name]["env"]["PACKAGE"] == "${{ matrix.package }}"


def test_every_job_has_a_timeout():
    for name in ("rust-plan", "rust-check", "rust-test"):
        assert isinstance(jobs()[name]["timeout-minutes"], int)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests/test_ci_rust.py`
Expected: FAIL (`KeyError: 'rust-plan'`).

- [ ] **Step 3: Replace the block**

`skills/repo-infra/assets/ci/ci-rust.yml`, whole file:

```yaml
  # D24. A bare `cargo test` runs the workspace's default members only, and a
  # root [package] makes that one crate. rust-plan reads the "rust" key of
  # .github/repo-infra.json and `cargo metadata`, and hands the two matrix
  # jobs below the crates they run for. Without the key, and where default
  # members equal members, it hands them one empty entry and they run the
  # workspace-wide commands. Every other case fails here, naming the crates.
  rust-plan:
    name: Rust workspace plan
    runs-on: ubuntu-latest
    timeout-minutes: 10
    outputs:
      lint: ${{ steps.plan.outputs.lint }}
      test: ${{ steps.plan.outputs.test }}
    steps:
      - uses: actions/checkout@v7

      - uses: dtolnay/rust-toolchain@stable

      - run: cargo metadata --no-deps --format-version 1 > "$RUNNER_TEMP/cargo-metadata.json"

      - id: plan
        uses: actions/github-script@v9
        with:
          script: |
            const fs = require('fs');
            const ws = process.env.GITHUB_WORKSPACE;
            const { rustPlan } = require(`${ws}/.github/workflows/lib/rust-plan.js`);
            const configPath = `${ws}/.github/repo-infra.json`;
            const config = fs.existsSync(configPath)
              ? JSON.parse(fs.readFileSync(configPath, 'utf8'))
              : {};
            const metadata = JSON.parse(
              fs.readFileSync(`${process.env.RUNNER_TEMP}/cargo-metadata.json`, 'utf8'),
            );
            try {
              const plan = rustPlan(config, metadata);
              core.setOutput('lint', JSON.stringify(plan.lint));
              core.setOutput('test', JSON.stringify(plan.test));
              core.notice(`lint: ${plan.lint.join(', ') || 'workspace'}; `
                + `test: ${plan.test.join(', ') || 'workspace'}`);
            } catch (error) {
              core.setFailed(error.message);
            }

  rust-check:
    name: Rust check and lint ${{ matrix.package }}
    needs: rust-plan
    runs-on: ubuntu-latest
    timeout-minutes: 20
    strategy:
      fail-fast: false
      matrix:
        package: ${{ fromJSON(needs.rust-plan.outputs.lint) }}
    env:
      CARGO_TERM_COLOR: always
      PACKAGE: ${{ matrix.package }}
    steps:
      - uses: actions/checkout@v7

      - uses: dtolnay/rust-toolchain@stable
        with:
          components: rustfmt, clippy

      - uses: actions/cache@v6
        with:
          path: |
            ~/.cargo/registry
            ~/.cargo/git
            target
          key: ${{ runner.os }}-cargo-${{ hashFiles('**/Cargo.lock') }}
          restore-keys: |
            ${{ runner.os }}-cargo-

      - run: cargo fmt --check ${PACKAGE:+-p "$PACKAGE"}

      # --no-deps with -p: clippy-driver replaces rustc for every workspace
      # member regardless of -p, so -p alone still lints vendored crates.
      - run: |
          if [ -n "$PACKAGE" ]; then
            cargo clippy --all-targets -p "$PACKAGE" --no-deps -- -D warnings
          else
            cargo clippy --all-targets -- -D warnings
          fi

  rust-test:
    name: Rust tests ${{ matrix.package }}
    needs: rust-plan
    runs-on: ubuntu-latest
    timeout-minutes: 30
    strategy:
      fail-fast: false
      matrix:
        package: ${{ fromJSON(needs.rust-plan.outputs.test) }}
    env:
      CARGO_TERM_COLOR: always
      PACKAGE: ${{ matrix.package }}
    steps:
      - uses: actions/checkout@v7

      - uses: dtolnay/rust-toolchain@stable

      - uses: actions/cache@v6
        with:
          path: |
            ~/.cargo/registry
            ~/.cargo/git
            target
          key: ${{ runner.os }}-cargo-${{ hashFiles('**/Cargo.lock') }}
          restore-keys: |
            ${{ runner.os }}-cargo-

      - run: cargo test ${PACKAGE:+-p "$PACKAGE"}
```

In `manifest.json`: `"ci-rust": {"version": 2, "jobs": ["rust-plan", "rust-check", "rust-test"]},`.

- [ ] **Step 4: Run the tests**

Run: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests`
Expected: PASS. If `tests/test_ci_rust_musl.py` pins `ci-rust`'s job list or `needs:` order, update the expectation there to the three-job list; do not change `ci-rust-musl.yml`.

- [ ] **Step 5: Commit**

```bash
git add skills/repo-infra/assets/ci/ci-rust.yml skills/repo-infra/assets/manifest.json tests/test_ci_rust.py tests/test_ci_rust_musl.py
git commit -m "ci-rust v2: lint and test the crates rust-plan names, one matrix leg each (D24)"
```

---

### Task 3: the `ci-local` seam (D25)

**Files:**
- Create: `skills/repo-infra/assets/ci/ci-local.yml`
- Modify: `skills/repo-infra/assets/manifest.json` (`ci_blocks`)
- Modify: `skills/repo-infra/scripts/repo_infra/assemble.py` (`ci_addon_blocks`, `render_all`)
- Modify: `skills/repo-infra/scripts/repo_infra/cli.py` (`_config`, `_chosen`, `_load`, `check`)
- Modify: `skills/repo-infra/scripts/repo_infra/state.py` (`classify_contracts`)
- Create: `tests/test_ci_local.py`

**Interfaces:**
- Produces: `render_all(assets_root, result, manifest, publish=(), build=(), ci=(), publish_local=(), ci_local=False, release_build=False)` (the `release_build` parameter is added here and used from Task 6 on); `classify_contracts(repo_root, result, config=None)`; `cli._config(root) -> dict`.

- [ ] **Step 1: Write the failing tests**

`tests/test_ci_local.py`:

```python
"""The ci-local seam (D25): project-owned jobs, required through one fixed path."""

import json
import pathlib

import pytest
import yaml

from repo_infra import cli
from repo_infra.assemble import AssemblyError, render_all
from repo_infra.detect import Detection
from repo_infra.state import classify_contracts

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))


def rust_repo(tmp_path, config=None):
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\nversion = "0.1.0"\n')
    if config is not None:
        (tmp_path / ".github").mkdir()
        (tmp_path / ".github/repo-infra.json").write_text(json.dumps(config))
    return Detection.load(ASSETS / "detection.json").detect(tmp_path)


def ci_jobs(files):
    return yaml.safe_load(files[".github/workflows/ci.yml"])["jobs"]


def test_ci_local_renders_the_seam_job_and_requires_it(tmp_path):
    files = render_all(ASSETS, rust_repo(tmp_path), MANIFEST, ci_local=True)
    jobs = ci_jobs(files)
    assert jobs["ci-local"] == {"uses": "./.github/workflows/ci-local.yml"}
    assert jobs["ci-passed"]["needs"][-1] == "ci-local"


def test_without_the_key_there_is_no_seam(tmp_path):
    jobs = ci_jobs(render_all(ASSETS, rust_repo(tmp_path), MANIFEST))
    assert "ci-local" not in jobs


def test_the_seam_cannot_be_named_as_an_ordinary_add_on(tmp_path):
    with pytest.raises(AssemblyError, match='"ci_local": true'):
        render_all(ASSETS, rust_repo(tmp_path), MANIFEST, ci=["ci-local"])


def test_a_missing_ci_local_workflow_is_a_conflict(tmp_path):
    result = rust_repo(tmp_path)
    items = classify_contracts(tmp_path, result, {"ci_local": True})
    assert [(i.name, i.state) for i in items] == [("ci-local", "conflict")]
    assert ".github/workflows/ci-local.yml" in items[0].detail


def test_a_present_ci_local_workflow_reports_nothing(tmp_path):
    result = rust_repo(tmp_path)
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/ci-local.yml").write_text("on: [workflow_call]\n")
    assert classify_contracts(tmp_path, result, {"ci_local": True}) == []


def test_load_reads_ci_local_from_the_config(tmp_path):
    rust_repo(tmp_path, {"ci_local": True})
    _manifest, _result, rendered = cli._load(tmp_path)
    assert "ci-local" in ci_jobs(rendered)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests/test_ci_local.py`
Expected: FAIL (`TypeError: render_all() got an unexpected keyword argument 'ci_local'`).

- [ ] **Step 3: Add the block and its manifest entry**

`skills/repo-infra/assets/ci/ci-local.yml`:

```yaml
  # The project brings the jobs, the standard brings the seam (D25, D20's
  # shape). .github/workflows/ci-local.yml is the project's own file: it
  # triggers on workflow_call only, sets timeout-minutes on each of its jobs,
  # and keeps its conditions inside steps, never on a job -- a reusable
  # workflow whose every job is skipped reports ci-local as skipped, and
  # ci-passed counts skipped as green. references/conventions.md.
  ci-local:
    uses: ./.github/workflows/ci-local.yml
```

In `manifest.json` `ci_blocks`, after `ci-github-action`:

```json
    "ci-local": {"version": 1, "jobs": ["ci-local"], "optional": true, "seam": "ci_local"}
```

- [ ] **Step 4: Teach the assembler**

In `assemble.py`, `ci_addon_blocks`, directly after the `meta is None` check:

```python
        if meta.get("seam"):
            raise AssemblyError(
                f"ci add-on {name} is a seam; set \"{meta['seam']}\": true in "
                ".github/repo-infra.json instead of naming it")
```

Change `render_all`'s signature and the line that builds `blocks`:

```python
def render_all(assets_root, result, manifest, publish=(), build=(), ci=(),
               publish_local=(), ci_local=False, release_build=False):
```

```python
    blocks = result.blocks + addons + (["ci-local"] if ci_local else [])
```

Add to the docstring, after the paragraph about optional blocks carrying build assets:

```
    `ci_local` adds the `ci-local` seam after every other block (D25), so
    the project's own jobs join the generated `needs:` list. `release_build`
    selects the `release-pr-build` variant (D26).
```

- [ ] **Step 5: Teach the CLI to read booleans and pass them on**

In `cli.py` replace `_chosen` with:

```python
def _config(root):
    """The repository's recorded decisions, or {} for an unconverted one."""
    config = pathlib.Path(root) / ".github/repo-infra.json"
    if not config.is_file():
        return {}
    return json.loads(config.read_text(encoding="utf-8"))


def _chosen(root, key):
    """A list the repository recorded in its own config, or nothing.

    Detection cannot answer these: whether a repository publishes a tarball,
    builds in a container, ships a static binary, or runs a publish job of its
    own that finalize must wait for is a decision (D12, D16, D22, A1). An
    unconverted repository has no config file and has chosen nothing.
    """
    return _config(root).get(key, [])
```

In `_load`:

```python
    config = _config(root)
    rendered = render_all(ASSETS, result, manifest,
                          _chosen(root, "publish"), _chosen(root, "build"),
                          ci, _chosen(root, "publish_local"),
                          ci_local=bool(config.get("ci_local")),
                          release_build=bool(config.get("release_build")))
```

In `check`: `items += classify_contracts(args.root, result, _config(args.root))`.

- [ ] **Step 6: Teach `classify_contracts` the seam**

In `state.py`, change the signature to `def classify_contracts(repo_root, result, config=None):`, put `config = config or {}` first in the body, and append before `return items`:

```python
    if config.get("ci_local"):
        seam = pathlib.Path(repo_root) / ".github/workflows/ci-local.yml"
        if not seam.is_file():
            items.append(Item(
                "ci-local", "conflict",
                "ci.yml's ci-local job calls .github/workflows/ci-local.yml "
                "and this repository has no such file; GitHub rejects the whole "
                "workflow, so every check stops reporting. Write it as the "
                "project's own jobs (references/conventions.md), or remove "
                "\"ci_local\" from .github/repo-infra.json."))
```

- [ ] **Step 7: Run the tests**

Run: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests`
Expected: PASS, including `test_a_block_declares_exactly_the_jobs_it_contains[ci-local]` and the existing `test_github_action.py` contract tests (they call `classify_contracts` with two arguments, which still works).

- [ ] **Step 8: Commit**

```bash
git add skills/repo-infra/assets/ci/ci-local.yml skills/repo-infra/assets/manifest.json skills/repo-infra/scripts/repo_infra tests/test_ci_local.py
git commit -m "ci-local: a required seam for jobs the project writes itself (D25)"
```

---
## Phase 2: the release pull request builds the release (D26)

### Task 4: `release.js`, the release pull request's decisions (D26)

**Files:**
- Create: `skills/repo-infra/assets/workflows/lib/release.js`
- Create: `skills/repo-infra/assets/workflows/lib/release.test.js`
- Modify (re-render): `.github/workflows/lib/`

**Interfaces:**
- Produces (all pure, no API calls):
  - `BUILD_RECORD = 'release-build.json'`, `BOT = 'github-actions[bot]'`
  - `isReleasePr(pr, fullName) -> boolean` (`pr` is a REST pull request object; `fullName` is `owner/repo`)
  - `blockingReleasePr(prs, fullName) -> pr | null`
  - `untaggedRelease(latest, tags) -> string | null` (`latest` is `changes.latestRelease(...)`'s value; `tags` are tag names)
  - `staleDrafts(releases, { tags, latestVersion }) -> release[]`
  - `ownDrafts(releases, version) -> release[]`
  - `refusedReleaseFiles(entries, versionFiles) -> [{ path, reason }]`
  - `undeclaredReleaseFiles(paths, declared) -> string[]`
  - `decodeText(buffer) -> string | null`
  - `releaseBuilt(statuses) -> boolean`
  - A `release` here is `{ id, tag_name, draft, assets: [{ id, name }] }`, the shape `repos.listReleases` returns.

- [ ] **Step 1: Write the failing test**

`skills/repo-infra/assets/workflows/lib/release.test.js`:

```js
// repo-infra: workflow-lib v5
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const r = require('./release.js');

const REPO = 'oetiker/mdmost';
const pr = (ref, { repo = REPO, login = r.BOT } = {}) => ({
  number: 7, head: { ref, repo: repo && { full_name: repo } }, user: { login },
});
const release = (tag, draft, assets = [r.BUILD_RECORD], id = 1) => ({
  id, tag_name: tag, draft, assets: assets.map((name, i) => ({ id: 100 + i, name })),
});

test('a release pull request is a bot branch release/* in this repository', () => {
  assert.equal(r.isReleasePr(pr('release/v1.2.0'), REPO), true);
});

test('a fork naming a branch release/x is not a release pull request', () => {
  assert.equal(r.isReleasePr(pr('release/x', { repo: 'someone/mdmost' }), REPO), false);
});

test('a person pushing release/x is not a release pull request', () => {
  assert.equal(r.isReleasePr(pr('release/x', { login: 'oetiker' }), REPO), false);
});

test('a deleted fork has no head repo and is not a release pull request', () => {
  assert.equal(r.isReleasePr(pr('release/x', { repo: null }), REPO), false);
});

test('blockingReleasePr finds the one that blocks', () => {
  const prs = [pr('feature/a'), pr('release/v1.2.0')];
  assert.equal(r.blockingReleasePr(prs, REPO).head.ref, 'release/v1.2.0');
  assert.equal(r.blockingReleasePr([pr('feature/a')], REPO), null);
});

test('the latest CHANGES.md release without a tag is reported', () => {
  const latest = { version: '1.2.0', date: '2026-09-29' };
  assert.equal(r.untaggedRelease(latest, ['v1.1.0']), '1.2.0');
  assert.equal(r.untaggedRelease(latest, ['v1.1.0', 'v1.2.0']), null);
  assert.equal(r.untaggedRelease(null, []), null);
});

test('a draft with a build record, no tag, not the latest release is stale', () => {
  const releases = [
    release('v1.2.0', true, undefined, 1), // abandoned pull request
    release('v1.1.1', true, undefined, 2), // merged, publish not finished
    release('v1.0.0', true, ['notes.txt'], 3), // someone's own draft
    release('v1.1.0', false, [], 4), // published
    release('v0.9.0', true, undefined, 5), // tagged
  ];
  const stale = r.staleDrafts(releases, { tags: ['v0.9.0', 'v1.1.0'], latestVersion: '1.1.1' });
  assert.deepEqual(stale.map((x) => x.id), [1]);
});

test('ownDrafts picks this version\'s drafts that carry a build record', () => {
  const releases = [release('v1.2.0', true, undefined, 1), release('v1.2.0', true, ['x'], 2),
    release('v1.3.0', true, undefined, 3)];
  assert.deepEqual(r.ownDrafts(releases, '1.2.0').map((x) => x.id), [1]);
});

const VERSION_FILES = [{ path: 'Cargo.toml' }];

test('a formula path is an acceptable release file', () => {
  assert.deepEqual(r.refusedReleaseFiles(['Formula/mdmost.rb'], VERSION_FILES), []);
});

for (const [entry, why] of [
  ['CHANGES.md', /CHANGES\.md/],
  ['./CHANGES.md', /CHANGES\.md/],
  ['Formula/../CHANGES.md', /CHANGES\.md/],
  ['Cargo.toml', /version file/],
  ['.github/repo-infra.json', /\.github/],
  ['.github//workflows/ci.yml', /\.github/],
  ['/etc/passwd', /absolute/],
  ['../outside', /outside/],
  ['', /empty/],
]) {
  test(`release file ${JSON.stringify(entry)} is refused`, () => {
    const refused = r.refusedReleaseFiles([entry], VERSION_FILES);
    assert.equal(refused.length, 1);
    assert.match(refused[0].reason, why);
  });
}

test('undeclared build output is named after normalising both sides', () => {
  assert.deepEqual(
    r.undeclaredReleaseFiles(['Formula/mdmost.rb', 'CHANGES.md'], ['./Formula/mdmost.rb']),
    ['CHANGES.md'],
  );
});

test('decodeText accepts UTF-8 and refuses anything else', () => {
  assert.equal(r.decodeText(Buffer.from('class Mdmost < Formula\n')), 'class Mdmost < Formula\n');
  assert.equal(r.decodeText(Buffer.from([0xff, 0xfe, 0x00])), null);
});

test('releaseBuilt needs a successful release-built status from the bot', () => {
  const s = (context, state, login) => ({ context, state, creator: { login } });
  assert.equal(r.releaseBuilt([s('release-built', 'success', r.BOT)]), true);
  assert.equal(r.releaseBuilt([s('release-built', 'success', 'oetiker')]), false);
  assert.equal(r.releaseBuilt([s('release-built', 'failure', r.BOT)]), false);
  assert.equal(r.releaseBuilt([s('ci-passed', 'success', r.BOT)]), false);
  assert.equal(r.releaseBuilt([]), false);
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `node --test skills/repo-infra/assets/workflows/lib/release.test.js`
Expected: FAIL with `Cannot find module './release.js'`

- [ ] **Step 3: Write the implementation**

`skills/repo-infra/assets/workflows/lib/release.js`:

```js
// repo-infra: workflow-lib v5
'use strict';

// Decisions of a release pull request that builds its release (D26). Each is
// a pure function over what the API returned, so every state the workflows
// can meet is a line in release.test.js rather than a hope in YAML.

const path = require('path');

const BUILD_RECORD = 'release-build.json';
const BOT = 'github-actions[bot]';

// A fork can name a branch release/x, and a person can push one. Neither is
// the pull request `Create release PR` opened, and neither may block it or
// be judged by the release-built status.
function isReleasePr(pr, fullName) {
  return pr.head.ref.startsWith('release/')
    && Boolean(pr.head.repo) && pr.head.repo.full_name === fullName
    && pr.user.login === BOT;
}

function blockingReleasePr(prs, fullName) {
  return prs.find((pr) => isReleasePr(pr, fullName)) || null;
}

// A merged release whose publish has not finished (or failed). Dispatching
// again would compute the same version from the tags, and `roll` would
// write a second heading for it into CHANGES.md.
function untaggedRelease(latest, tags) {
  if (!latest) return null;
  return tags.includes(`v${latest.version}`) ? null : latest.version;
}

const carriesRecord = (release) => release.assets.some((a) => a.name === BUILD_RECORD);

// Drafts a closed release pull request left behind. Only ours (they carry the
// build record), only untagged, and never the latest release in CHANGES.md:
// that one belongs to a merged release publish has not finished.
function staleDrafts(releases, { tags, latestVersion }) {
  return releases.filter((release) => release.draft && carriesRecord(release)
    && !tags.includes(release.tag_name)
    && release.tag_name !== `v${latestVersion}`);
}

function ownDrafts(releases, version) {
  return releases.filter((release) => release.draft && carriesRecord(release)
    && release.tag_name === `v${version}`);
}

function normalise(entry) {
  return path.posix.normalize(entry).replace(/\/+$/, '');
}

// The build job is read-only. Its one way to write the repository is the
// release-files artifact, which `finish` commits. These paths would turn that
// channel into a way to rewrite the changelog, a version or a workflow.
function refusedReleaseFiles(entries, versionFiles) {
  const versions = new Set((versionFiles || []).map((f) => normalise(f.path)));
  const refused = [];
  for (const entry of entries) {
    const reason = (() => {
      if (typeof entry !== 'string' || entry === '') return 'is empty';
      if (path.posix.isAbsolute(entry)) return 'is an absolute path';
      const p = normalise(entry);
      if (p === '..' || p.startsWith('../')) return 'points outside the repository';
      if (p === 'CHANGES.md') return 'is CHANGES.md, which the release pull request rolls';
      if (versions.has(p)) return 'is a version file, which the release pull request bumps';
      if (p === '.github' || p.startsWith('.github/')) return 'is under .github/';
      return null;
    })();
    if (reason) refused.push({ path: entry, reason });
  }
  return refused;
}

function undeclaredReleaseFiles(paths, declared) {
  const allowed = new Set(declared.map(normalise));
  return paths.filter((p) => !allowed.has(normalise(p)));
}

// The commit library writes strings. A binary file would be mangled on the
// way into the release branch, so it is refused instead.
function decodeText(buffer) {
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(buffer);
  } catch (error) {
    return null;
  }
}

// Anyone who can push can set a status of any name, so this guards against
// the Update branch button, not against people with write access.
function releaseBuilt(statuses) {
  return statuses.some((s) => s.context === 'release-built'
    && s.state === 'success' && s.creator && s.creator.login === BOT);
}

module.exports = {
  BUILD_RECORD, BOT, isReleasePr, blockingReleasePr, untaggedRelease,
  staleDrafts, ownDrafts, refusedReleaseFiles, undeclaredReleaseFiles,
  decodeText, releaseBuilt,
};
```

- [ ] **Step 4: Run the JS suite**

Run: `node --test skills/repo-infra/assets/workflows/lib/*.test.js`
Expected: PASS.

- [ ] **Step 5: Re-render, run the Python suite, commit**

Re-render (Global Constraints), then `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests` (PASS).

```bash
git add skills/repo-infra/assets/workflows/lib .github/workflows/lib
git commit -m "workflow-lib: release.js, the release pull request's decisions (D26)"
```

---

### Task 5: `publish.js`, the publish state machine (D26)

**Files:**
- Create: `skills/repo-infra/assets/workflows/lib/publish.js`
- Create: `skills/repo-infra/assets/workflows/lib/publish.test.js`
- Modify (re-render): `.github/workflows/lib/`

**Interfaces:**
- Consumes: `BUILD_RECORD` from `release.js`.
- Produces:
  - `publishDecision({ tag, tagCommit, releases }) -> { action: 'done' } | { action: 'resume', releaseId, head } | { action: 'create', releaseId, recordAssetId } | { action: 'fail', message }`. `tagCommit` is the peeled commit sha or `null` when the tag does not exist; `releases` are the releases whose `tag_name === tag`, shaped as in Task 4.
  - `validateBuildRecord(record, version, latestAtHead) -> string | null` (a message, or `null` when valid). `latestAtHead` is `changes.latestRelease(CHANGES.md at record.head)`.

- [ ] **Step 1: Write the failing test**

`skills/repo-infra/assets/workflows/lib/publish.test.js`:

```js
// repo-infra: workflow-lib v5
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { publishDecision, validateBuildRecord } = require('./publish.js');

const TAG = 'v1.2.0';
const HEAD = 'a'.repeat(40);
let nextId = 1;
const rel = (draft, record) => ({
  id: nextId++, tag_name: TAG, draft,
  assets: record ? [{ id: 900, name: 'release-build.json' }, { id: 901, name: 'x.deb' }]
    : [{ id: 901, name: 'x.deb' }],
});
const decide = (tagCommit, releases) => publishDecision({ tag: TAG, tagCommit, releases });

// The whole state table of spec D26 "Publishing": tag present/absent x
// published/draft/none/several x build record present/absent.

test('case 1: tag, one published release, no record: done', () => {
  assert.deepEqual(decide(HEAD, [rel(false, false)]), { action: 'done' });
});

test('case 2: tag and one draft: resume at the tag commit (record or not)', () => {
  for (const record of [true, false]) {
    const d = rel(true, record);
    assert.deepEqual(decide(HEAD, [d]), { action: 'resume', releaseId: d.id, head: HEAD });
  }
});

test('case 3: no tag and one draft with a record: create', () => {
  const d = rel(true, true);
  assert.deepEqual(decide(null, [d]), { action: 'create', releaseId: d.id, recordAssetId: 900 });
});

test('case 3 refused: no tag and one draft without a record', () => {
  const out = decide(null, [rel(true, false)]);
  assert.equal(out.action, 'fail');
  assert.match(out.message, /release-build\.json/);
});

test('case 3 refused: no tag and no draft names the count', () => {
  const out = decide(null, []);
  assert.equal(out.action, 'fail');
  assert.match(out.message, /found 0/);
});

test('case 3 refused: no tag and two drafts names the count', () => {
  const out = decide(null, [rel(true, true), rel(true, true)]);
  assert.equal(out.action, 'fail');
  assert.match(out.message, /found 2/);
});

test('case 4: tag but no release at all', () => {
  const out = decide(HEAD, []);
  assert.equal(out.action, 'fail');
  assert.match(out.message, /no release/);
});

test('case 4: a published release that still carries the record was published by hand', () => {
  for (const tagCommit of [HEAD, null]) {
    const out = decide(tagCommit, [rel(false, true)]);
    assert.equal(out.action, 'fail');
    assert.match(out.message, /by hand/);
  }
});

test('case 4: tag and several matching releases', () => {
  const out = decide(HEAD, [rel(true, false), rel(true, true)]);
  assert.equal(out.action, 'fail');
  assert.match(out.message, /2 drafts/);
});

test('case 4: tag, a published release and a draft', () => {
  assert.equal(decide(HEAD, [rel(false, false), rel(true, true)]).action, 'fail');
});

test('case 4: no tag but a published release', () => {
  assert.equal(decide(null, [rel(false, false)]).action, 'fail');
});

test('a valid record passes', () => {
  assert.equal(validateBuildRecord({ head: HEAD }, '1.2.0', { version: '1.2.0' }), null);
});

test('a record without a commit sha is refused', () => {
  assert.match(validateBuildRecord({}, '1.2.0', { version: '1.2.0' }), /head/);
  assert.match(validateBuildRecord({ head: 'main' }, '1.2.0', { version: '1.2.0' }), /head/);
});

test('a head whose CHANGES.md is at another version is refused', () => {
  assert.match(validateBuildRecord({ head: HEAD }, '1.2.0', { version: '1.1.0' }), /1\.1\.0/);
  assert.match(validateBuildRecord({ head: HEAD }, '1.2.0', null), /no released version/);
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `node --test skills/repo-infra/assets/workflows/lib/publish.test.js`
Expected: FAIL with `Cannot find module './publish.js'`

- [ ] **Step 3: Write the implementation**

`skills/repo-infra/assets/workflows/lib/publish.js`:

```js
// repo-infra: workflow-lib v5
'use strict';

// What the publish job does for a repository with release_build set (D26),
// decided from the tag and the releases together. Every late review of the
// spec found a release-stranding state in this machine, so it lives here,
// with one test per state, and the workflow only acts on the answer.
//
// Once the tag exists, the tag is the record of what was built; the
// release-build.json asset matters only before that (case 3).

const { BUILD_RECORD } = require('./release.js');

const fail = (message) => ({ action: 'fail', message });

function publishDecision({ tag, tagCommit, releases }) {
  const drafts = releases.filter((r) => r.draft);
  const published = releases.filter((r) => !r.draft);
  const record = (r) => r.assets.find((a) => a.name === BUILD_RECORD);

  if (published.some(record)) {
    return fail(`${tag}: a published release still carries ${BUILD_RECORD}. It was `
      + 'published by hand, which skips every publish add-on; check what the '
      + 'add-ons would have done, then delete the asset.');
  }

  if (tagCommit) {
    if (published.length === 1 && drafts.length === 0) return { action: 'done' };
    if (published.length === 0 && drafts.length === 1) {
      return { action: 'resume', releaseId: drafts[0].id, head: tagCommit };
    }
    if (releases.length === 0) {
      return fail(`${tag} exists but no release matches it (was a draft deleted after `
        + 'tagging?). Create a draft release for the tag, then re-run this workflow.');
    }
    return fail(`${tag}: several releases match it: ${published.length} published, `
      + `${drafts.length} drafts. Delete the extra ones, then re-run.`);
  }

  if (published.length > 0) {
    return fail(`${tag} does not exist but a published release names it; `
      + 'this workflow does not know which commit it describes.');
  }
  if (drafts.length !== 1) {
    return fail(`${tag}: expected exactly one draft release built by the release `
      + `pull request, found ${drafts.length}.`);
  }
  const asset = record(drafts[0]);
  if (!asset) {
    return fail(`${tag}: the draft release carries no ${BUILD_RECORD}, so the built `
      + 'commit is unknown. Dispatch Create release PR again.');
  }
  return { action: 'create', releaseId: drafts[0].id, recordAssetId: asset.id };
}

function validateBuildRecord(record, version, latestAtHead) {
  if (!record || typeof record.head !== 'string' || !/^[0-9a-f]{40}$/.test(record.head)) {
    return `${BUILD_RECORD} names no head commit`;
  }
  if (!latestAtHead) {
    return `CHANGES.md at ${record.head} has no released version`;
  }
  if (latestAtHead.version !== version) {
    return `CHANGES.md at ${record.head} releases ${latestAtHead.version}, not ${version}`;
  }
  return null;
}

module.exports = { publishDecision, validateBuildRecord };
```

- [ ] **Step 4: Run the JS suite, re-render, run the Python suite**

Run: `node --test skills/repo-infra/assets/workflows/lib/*.test.js` (PASS), the re-render command, then `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests` (PASS).

- [ ] **Step 5: Commit**

```bash
git add skills/repo-infra/assets/workflows/lib .github/workflows/lib
git commit -m "workflow-lib: publish.js, the tag and draft state machine as a table (D26)"
```

---
### Task 6: the `release-pr-build` asset and its selection (D26)

**Files:**
- Create: `skills/repo-infra/assets/workflows/release-pr-build.yml`
- Modify: `skills/repo-infra/assets/manifest.json` (`assets`, `actions`)
- Modify: `skills/repo-infra/scripts/repo_infra/assemble.py` (`render_all`)
- Create: `tests/test_release_build.py`

**Interfaces:**
- Consumes: `release.js` (Task 4): `blockingReleasePr`, `untaggedRelease`, `staleDrafts`, `ownDrafts`, `refusedReleaseFiles`, `undeclaredReleaseFiles`, `decodeText`, `BUILD_RECORD`; `assets.js` `missingAssets`; `changes.js` `latestRelease`, `notesFor`, `roll`; `commit.js` `commitFiles` (returns the new commit sha); `render_all(..., release_build=False)` from Task 3.
- Produces: the project contract for `.github/workflows/release-build.yml`: `on: workflow_call` with string inputs `version` and `ref`; uploads each shipped file as an artifact named `release-asset-*`; uploads repository files it rewrote as one artifact `release-files` whose tree is repository paths. Manifest keys `variant_of` and `when` on an `assets` entry.

- [ ] **Step 1: Write the failing tests**

`tests/test_release_build.py`:

```python
"""The release_build variant of the release workflow (D26)."""

import json
import pathlib

import pytest
import yaml

from repo_infra.assemble import AssemblyError, render_all
from repo_infra.detect import Detection
from repo_infra.markers import parse_markers

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
TARGET = ".github/workflows/release-pr.yml"
VARIANT = ASSETS / "workflows/release-pr-build.yml"


def result(tmp_path):
    return Detection.load(ASSETS / "detection.json").detect(tmp_path)


def workflow():
    return yaml.safe_load(VARIANT.read_text(encoding="utf-8"))


def script(job, step_name):
    steps = workflow()["jobs"][job]["steps"]
    return next(s["with"]["script"] for s in steps if s.get("name") == step_name)


def test_release_build_selects_the_variant_for_the_same_target(tmp_path):
    files = render_all(ASSETS, result(tmp_path), MANIFEST, release_build=True)
    assert [m.asset for m in parse_markers(files[TARGET])][0] == "release-pr-build"


def test_without_release_build_the_plain_workflow_is_installed(tmp_path):
    files = render_all(ASSETS, result(tmp_path), MANIFEST)
    assert [m.asset for m in parse_markers(files[TARGET])][0] == "release-pr"


def test_an_unknown_when_key_is_an_assembly_error(tmp_path):
    manifest = json.loads(json.dumps(MANIFEST))
    manifest["assets"]["release-pr-build"]["when"] = "no_such_key"
    with pytest.raises(AssemblyError, match="no_such_key"):
        render_all(ASSETS, result(tmp_path), manifest)


def test_three_jobs_and_the_build_is_the_project_seam():
    jobs = workflow()["jobs"]
    assert list(jobs) == ["prepare", "build", "finish"]
    assert jobs["build"]["uses"] == "./.github/workflows/release-build.yml"
    assert jobs["build"]["permissions"] == {"contents": "read"}
    assert "secrets" not in jobs["build"]
    assert jobs["build"]["with"] == {
        "version": "${{ needs.prepare.outputs.version }}",
        "ref": "${{ needs.prepare.outputs.head }}",
    }
    assert jobs["finish"]["needs"] == ["prepare", "build"]


def test_the_guard_is_the_same_text_as_in_release_pr():
    # The two variants differ in job structure only (spec D26).
    plain = yaml.safe_load((ASSETS / "workflows/release-pr.yml").read_text(encoding="utf-8"))
    guard = next(s for s in plain["jobs"]["release-pr"]["steps"]
                 if s.get("name") == "Guard (right branch, green checks)")
    assert script("prepare", "Guard (right branch, green checks)") == guard["with"]["script"]


def test_prepare_refuses_before_it_writes_anything():
    steps = [s.get("name") for s in workflow()["jobs"]["prepare"]["steps"]]
    assert steps.index("Refuse an open or unpublished release; delete stale drafts") < steps.index(
        "Compute the version and rewrite the files")
    refuse = script("prepare", "Refuse an open or unpublished release; delete stale drafts")
    assert "blockingReleasePr" in refuse
    assert "is in CHANGES.md on main but has no tag" in refuse
    assert "staleDrafts" in refuse


def test_finish_checks_everything_before_it_creates_the_draft():
    s = script("finish", "Commit the release files, draft the release, open the pull request")
    for guard in ("refusedReleaseFiles", "undeclaredReleaseFiles", "decodeText", "missingAssets"):
        assert s.index(guard) < s.index("createRelease"), guard


def test_finish_marks_the_head_before_it_opens_the_pull_request():
    s = script("finish", "Commit the release files, draft the release, open the pull request")
    assert s.index("ownDrafts") < s.index("createRelease")
    assert s.index("createRelease") < s.index("'release-built'") < s.index("pulls.create")
    assert "target_commitish: head" in s


def test_finish_downloads_both_artifact_kinds():
    steps = workflow()["jobs"]["finish"]["steps"]
    patterns = [s["with"]["pattern"] for s in steps
                if s.get("uses", "").startswith("actions/download-artifact@")]
    assert patterns == ["release-asset-*", "release-files"]


def test_the_rust_lockfile_note_survives_in_the_variant():
    # Its absence is what shipped mdmost v0.1.1 with a stale Cargo.lock.
    assert "cargo update --workspace" in VARIANT.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests/test_release_build.py`
Expected: FAIL (`FileNotFoundError` for `release-pr-build.yml`).

- [ ] **Step 3: Write the asset**

`skills/repo-infra/assets/workflows/release-pr-build.yml`. The `Guard` step and the `Compute the version and rewrite the files` step are copied **verbatim** from `release-pr.yml` (steps with those names; the guard test above compares them byte for byte). Everything else:

```yaml
name: Create release PR
# repo-infra: release-pr-build v1
#
# The release_build variant of release-pr.yml (D26). The release pull request
# builds the release before anyone merges it, so nothing is written to main
# after the merge and publishing never rebuilds. A reusable workflow can only
# be called as a job, so this is three jobs:
#
#   prepare  guard, two refusals, stale drafts, roll, bump, commit the branch
#   build    .github/workflows/release-build.yml -- the project's own file,
#            read-only, no secrets
#   finish   commit the declared release files, draft the release with every
#            built file and release-build.json attached, mark the head
#            `release-built`, then open the pull request

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
  actions: read
  statuses: write

jobs:
  prepare:
    name: Prepare the release branch
    runs-on: ubuntu-latest
    timeout-minutes: 25
    outputs:
      version: ${{ steps.prepare.outputs.version }}
      date: ${{ steps.prepare.outputs.date }}
      head: ${{ steps.commit.outputs.head }}
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-node@v7
        with:
          node-version: 22

      # (verbatim copy of release-pr.yml's "Guard (right branch, green checks)" step)

      - name: Refuse an open or unpublished release; delete stale drafts
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
              core.setFailed(
                `v${untagged} is in CHANGES.md on main but has no tag. `
                + 'Re-run the failed jobs of its Publish release run; if it is '
                + `already out under another tag, push v${untagged} by hand; to `
                + 'abandon it, merge a pull request that moves its entries back '
                + 'under [Unreleased]. RELEASING.md has the details.'
              );
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

      # (verbatim copy of release-pr.yml's "Compute the version and rewrite the files" step, id: prepare)

      # Ecosystems whose lockfile can only be rewritten by their own tool run
      # here, between the rewrite and the commit. A Rust repository gets,
      # verbatim:
      #
      #   - uses: dtolnay/rust-toolchain@stable
      #   - run: cargo update --workspace
      #
      # Not --offline: the resolve needs the registry. Not || true: swallowing
      # that failure is what tagged mdmost v0.1.1 with an inconsistent lockfile.

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

  # The project's own build (D20's seam). The `uses:` path resolves at the
  # dispatched commit on main, not on the release branch. Read-only, and no
  # secrets: its only way to write the repository is the release-files
  # artifact, which `finish` checks against release_files.
  build:
    needs: prepare
    permissions:
      contents: read
    uses: ./.github/workflows/release-build.yml
    with:
      version: ${{ needs.prepare.outputs.version }}
      ref: ${{ needs.prepare.outputs.head }}

  finish:
    name: Draft the release and open the pull request
    needs: [prepare, build]
    runs-on: ubuntu-latest
    timeout-minutes: 30
    permissions:
      contents: write
      pull-requests: write
      statuses: write
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

            // 4. The commit lands before the pull request exists, so the one
            //    "Approve workflows to run" click covers its checks.
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
              Buffer.from(JSON.stringify({ version, head, assets: assetNames }, null, 2)),
              'application/json');

            // 6. The changelog gate reads this status. A later push to the
            //    branch is a new commit without it.
            await github.rest.repos.createCommitStatus({
              owner, repo, sha: head, state: 'success', context: 'release-built',
              description: `${tag} built into a draft release`,
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
              '',
              'Review, then merge. Merging triggers **Publish release**, which tags',
              `the built commit \`${head.slice(0, 12)}\` as \`${tag}\` and publishes the draft.`,
              '',
              'Do not press **Update branch**: the build would no longer match the',
              'branch, and the changelog check goes red. Closing this pull request',
              'cancels the release.',
            ].join('\n');
            const { data: pr } = await github.rest.pulls.create({
              owner, repo,
              head: branch,
              base: context.payload.repository.default_branch,
              title: `Release ${tag}`,
              body,
            });
            core.notice(`Release pull request opened: ${pr.html_url}`);
            await core.summary
              .addHeading(`Release ${tag} built`)
              .addLink('Review and merge to publish', pr.html_url)
              .write();
```

Replace each `# (verbatim copy ...)` line with the named step from `release-pr.yml`, unchanged.

- [ ] **Step 4: Declare it in the manifest**

In `manifest.json` `assets`, after `release-pr`:

```json
    "release-pr-build": {
      "version": 1,
      "source": "workflows/release-pr-build.yml",
      "target": ".github/workflows/release-pr.yml",
      "variant_of": "release-pr",
      "when": "release_build"
    },
```

In `actions`, add `"actions/download-artifact": "v8",`.

- [ ] **Step 5: Teach `render_all` to choose**

In `assemble.py`, at the top of `render_all`'s body, replace the loop over `manifest["assets"]` with:

```python
    # Two assets may share a target (D26): a variant carries `variant_of`
    # (the asset it replaces) and `when` (the config flag that selects it).
    # The selection rule decides, never the order of the manifest's entries.
    options = {"release_build": release_build}
    chosen = set()
    for name, spec in manifest["assets"].items():
        when = spec.get("when")
        if when is None:
            continue
        if when not in options:
            raise AssemblyError(f"asset {name}: unknown selector {when!r}")
        if options[when]:
            chosen.add(name)
    replaced = {manifest["assets"][name]["variant_of"] for name in chosen}

    files = {}
    for name, spec in manifest["assets"].items():
        if name in replaced or (spec.get("when") and name not in chosen):
            continue
        source = assets_root / spec["source"]
        if spec.get("kind") == "dir":
            if not source.is_dir():
                raise AssemblyError(f"asset {name}: {source} is not a directory")
            for child in sorted(source.iterdir()):
                if child.is_file():
                    files[f"{spec['target']}/{child.name}"] = _read(child)
        else:
            files[spec["target"]] = _read(source)
```

- [ ] **Step 6: Run the suite**

Run: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests`
Expected: PASS, including `test_manifest.py` (the variant carries its own marker) and `test_blocks.py` (the download-artifact pin). `test_self_render.py` is unaffected: repo-infra does not set `release_build`.

- [ ] **Step 7: Commit**

```bash
git add skills/repo-infra/assets/workflows/release-pr-build.yml skills/repo-infra/assets/manifest.json skills/repo-infra/scripts/repo_infra/assemble.py tests/test_release_build.py
git commit -m "release-pr-build: the release pull request builds the release (D26)"
```

---

### Task 7: `check` and `apply` learn the variant switch and the release contract (D26)

**Files:**
- Modify: `skills/repo-infra/scripts/repo_infra/state.py` (`classify_files`, `classify_contracts`, new `refused_release_files`)
- Modify: `skills/repo-infra/scripts/repo_infra/apply.py` (`apply_file_item`, outdated branch)
- Create: `tests/test_variant_switch.py`
- Modify: `tests/test_release_build.py` (contract tests)

**Interfaces:**
- Consumes: manifest `variant_of` (Task 6); `classify_contracts(repo_root, result, config=None)` (Task 3).
- Produces: `state.refused_release_files(entries, version_files) -> list[tuple[str, str]]` (path, reason); items `release-build` and `release-files` (state `conflict`); `outdated` items whose detail starts with `variant switch`.

- [ ] **Step 1: Write the failing tests**

`tests/test_variant_switch.py`:

```python
"""Turning release_build on or off switches the variant of release-pr.yml (D26)."""

import pathlib
import subprocess

import pytest

from repo_infra.apply import NeedsMerge, apply_file_item
from repo_infra.markers import marker_line
from repo_infra.state import classify_files

MANIFEST = {"assets": {
    "release-pr": {"version": 3, "source": "workflows/release-pr.yml",
                   "target": ".github/workflows/release-pr.yml"},
    "release-pr-build": {"version": 1, "source": "workflows/release-pr-build.yml",
                         "target": ".github/workflows/release-pr.yml",
                         "variant_of": "release-pr", "when": "release_build"},
}}
TARGET = ".github/workflows/release-pr.yml"
PLAIN = "name: Create release PR\n" + marker_line("release-pr", 3) + "\njobs: {}\n"
BUILD = "name: Create release PR\n" + marker_line("release-pr-build", 1) + "\njobs: {a: 1}\n"


@pytest.fixture
def plugin(tmp_path):
    """A plugin checkout whose history holds release-pr v3 and release-pr-build v1."""
    root = tmp_path / "plugin"
    (root / "assets/workflows").mkdir(parents=True)
    (root / "assets/workflows/release-pr.yml").write_text(PLAIN)
    (root / "assets/workflows/release-pr-build.yml").write_text(BUILD)
    for args in (("init", "-q"), ("add", "."), ("-c", "user.name=t", "-c", "user.email=t@t",
                                                 "commit", "-qm", "assets")):
        subprocess.run(("git",) + args, cwd=root, check=True)
    return root


def install(repo, text):
    path = repo / TARGET
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_the_sibling_marker_reads_as_a_variant_switch(tmp_path):
    install(tmp_path, PLAIN)
    (item,) = classify_files(tmp_path, {TARGET: BUILD}, MANIFEST)
    assert (item.name, item.state) == ("release-pr-build", "outdated")
    assert item.detail.startswith("variant switch")
    assert "release-pr v3" in item.detail


def test_switching_back_is_a_variant_switch_too(tmp_path):
    install(tmp_path, BUILD)
    (item,) = classify_files(tmp_path, {TARGET: PLAIN}, MANIFEST)
    assert (item.name, item.state) == ("release-pr", "outdated")


def test_an_unedited_file_is_replaced_whole(tmp_path, plugin):
    repo = tmp_path / "repo"
    install(repo, PLAIN)
    items = classify_files(repo, {TARGET: BUILD}, MANIFEST)
    assert apply_file_item(repo, "release-pr-build", {TARGET: BUILD}, items, plugin) == [TARGET]
    assert (repo / TARGET).read_text() == BUILD


def test_a_local_edit_is_merged_three_ways_with_the_sibling_as_base(tmp_path, plugin):
    # The Rust `cargo update --workspace` step is such an edit, and dropping it
    # is what shipped mdmost v0.1.1 with a stale Cargo.lock.
    repo = tmp_path / "repo"
    edited = PLAIN + "# cargo update --workspace\n"
    install(repo, edited)
    items = classify_files(repo, {TARGET: BUILD}, MANIFEST)
    with pytest.raises(NeedsMerge) as refused:
        apply_file_item(repo, "release-pr-build", {TARGET: BUILD}, items, plugin)
    assert pathlib.Path(refused.value.base).read_text() == PLAIN
    assert pathlib.Path(refused.value.current).read_text() == edited
```

Append to `tests/test_release_build.py`:

```python
from repo_infra.state import classify_contracts, refused_release_files


@pytest.mark.parametrize("entry", [
    "CHANGES.md", "./CHANGES.md", "Formula/../CHANGES.md", "Cargo.toml",
    ".github/repo-infra.json", ".github//workflows/ci.yml", "/etc/passwd", "../x", "",
])
def test_check_refuses_a_release_file_that_reopens_the_channel(entry):
    assert [p for p, _ in refused_release_files([entry], [{"path": "Cargo.toml"}])] == [entry]


def test_check_accepts_the_formula():
    assert refused_release_files(["Formula/mdmost.rb"], [{"path": "Cargo.toml"}]) == []


def test_release_build_without_the_project_build_is_a_conflict(tmp_path):
    items = classify_contracts(tmp_path, result(tmp_path), {"release_build": True})
    assert [(i.name, i.state) for i in items] == [("release-build", "conflict")]


def test_a_refused_release_file_is_a_conflict(tmp_path):
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/release-build.yml").write_text("on: [workflow_call]\n")
    config = {"release_build": True, "release_files": ["./CHANGES.md"], "version_files": []}
    items = classify_contracts(tmp_path, result(tmp_path), config)
    assert [(i.name, i.state) for i in items] == [("release-files", "conflict")]
    assert "./CHANGES.md" in items[0].detail
```

- [ ] **Step 2: Run them to verify they fail**

Run: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests/test_variant_switch.py tests/test_release_build.py`
Expected: FAIL (`ImportError: cannot import name 'refused_release_files'`, and the variant item reads `conflict`).

The `NeedsMerge` attributes `base`, `new`, `current` are the scratch file paths `_prepare_merge` writes. Read `_prepare_merge` in `apply.py` (below line 200) before Step 4 and adjust the two `read_text` lines of the last test if it records something else.

- [ ] **Step 3: `state.py`**

Add `import posixpath` at the top. In `classify_files`, before the loop:

```python
    # A variant and its base share a target (D26). A file carrying the other
    # one's marker is a variant switch, not an unmanaged file.
    siblings = {}
    for name, spec in manifest.get("assets", {}).items():
        if spec.get("variant_of"):
            siblings[name] = spec["variant_of"]
            siblings[spec["variant_of"]] = name
```

Replace the `elif have is None:` branch with:

```python
            elif have is None and siblings.get(marker.asset) in found:
                other = siblings[marker.asset]
                per_path.append((path, Item(marker.asset, "outdated",
                                  f"variant switch: {other} v{found[other]} installed, "
                                  f"{marker.asset} v{marker.version} selected")))
            elif have is None:
```

Add after `classify_contracts`'s `ci_local` check (Task 3), before `return items`:

```python
    if config.get("release_build"):
        seam = pathlib.Path(repo_root) / ".github/workflows/release-build.yml"
        if not seam.is_file():
            items.append(Item(
                "release-build", "conflict",
                "release_build is set and .github/workflows/release-build.yml does "
                "not exist; the release workflow calls it and GitHub rejects the "
                "whole workflow. Write it (references/release-flow.md)."))
    refused = refused_release_files(config.get("release_files", []),
                                    config.get("version_files", []))
    if refused:
        items.append(Item(
            "release-files", "conflict",
            "release_files in .github/repo-infra.json: "
            + "; ".join(f"{path} {reason}" for path, reason in refused)))
```

And the function, next to `carries_a_path_filter`:

```python
def refused_release_files(entries, version_files):
    """release_files entries that would reopen the channel D26 closes.

    The read-only build writes the repository only through the files `finish`
    commits. A path that is, after normalising, CHANGES.md, a version file or
    anything under .github/ would let it rewrite the changelog, a version or a
    workflow. `finish` checks the same rule at run time (release.js).
    """
    versions = {posixpath.normpath(f["path"]) for f in version_files or []}
    refused = []
    for entry in entries:
        if not isinstance(entry, str) or entry == "":
            refused.append((entry, "is empty"))
            continue
        if entry.startswith("/"):
            refused.append((entry, "is an absolute path"))
            continue
        path = posixpath.normpath(entry)
        if path == ".." or path.startswith("../"):
            refused.append((entry, "points outside the repository"))
        elif path == "CHANGES.md":
            refused.append((entry, "is CHANGES.md, which the release pull request rolls"))
        elif path in versions:
            refused.append((entry, "is a version file, which the release pull request bumps"))
        elif path == ".github" or path.startswith(".github/"):
            refused.append((entry, "is under .github/"))
    return refused
```

- [ ] **Step 4: `apply.py`**

In `apply_file_item`, replace the three lines after `# outdated`:

```python
    installed = (pathlib.Path(repo_root) / path).read_text(encoding="utf-8")
    found = parse_markers(installed)
    # A variant switch (D26): the file carries the sibling's marker, and the
    # merge base is the sibling's own source at that version -- replacing the
    # file whole would drop a local edit such as the `cargo update` step.
    own = next((m for m in found if m.asset == name), None)
    base_marker = own or found[0]
    source = _asset_source(plugin_root, base_marker.asset)
    base = base_version_of(plugin_root, source, base_marker.version) if source else None
```

The two lines that follow (`if base is not None and base == installed:` and `_prepare_merge(...)`) stay as they are; remove the old `have = ...` and `source = ...` lines they replaced.

- [ ] **Step 5: Run the suite**

Run: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add skills/repo-infra/scripts/repo_infra/state.py skills/repo-infra/scripts/repo_infra/apply.py tests/test_variant_switch.py tests/test_release_build.py
git commit -m "check and apply: variant switch, release-build.yml contract, release_files refusal (D26)"
```

---
### Task 8: `changelog` v3, the release-branch gate (D26)

**Files:**
- Modify: `skills/repo-infra/assets/workflows/changelog.yml`
- Modify: `skills/repo-infra/assets/manifest.json` (`changelog` `"version": 3`)
- Modify (re-render): `.github/workflows/changelog.yml`
- Create: `tests/test_changelog_gate.py`

**Interfaces:**
- Consumes: `release.js` `isReleasePr`, `releaseBuilt` (Task 4); `changes.js` `unreleasedBlock`.

- [ ] **Step 1: Write the failing tests**

`tests/test_changelog_gate.py` runs the real script from the asset under node against a fake API, the way `tests/test_publish.py::_run_finalize` does:

```python
"""changelog v3 (D26): release/* branches of release_build repositories are gated."""

import json
import os
import pathlib
import shutil
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSET = ROOT / "skills/repo-infra/assets/workflows/changelog.yml"
BOT = "github-actions[bot]"
BLURB = ("the release branch changed after it was built (the Update branch button "
         "does this); close this pull request and dispatch Create release PR again")
SAME = "# Changes\n\n## [Unreleased]\n\n## 1.0.0 - 2026-01-01\n"
MORE = "# Changes\n\n## [Unreleased]\n\n### New\n\n- x\n\n## 1.0.0 - 2026-01-01\n"


def job():
    return yaml.safe_load(ASSET.read_text(encoding="utf-8"))["jobs"]["changelog-updated"]


def gate(tmp_path, *, head_ref, login=BOT, head_repo="o/r", labels=(), config=None,
         statuses=(), head_changes=SAME):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = job()["steps"][-1]["with"]["script"]
    contents = {"CHANGES.md@b": SAME, "CHANGES.md@h": head_changes}
    if config is not None:
        contents[".github/repo-infra.json@b"] = json.dumps(config)
    pr = {"number": 1, "labels": [{"name": n} for n in labels], "user": {"login": login},
          "head": {"ref": head_ref, "sha": "h",
                   "repo": {"full_name": head_repo} if head_repo else None},
          "base": {"sha": "b"}}
    harness = """
const contents = %s;
const statuses = %s;
const failures = [];
const github = {
  paginate: async (fn) => (fn === 'statuses' ? statuses : []),
  rest: { repos: {
    listCommitStatusesForRef: 'statuses',
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
""" % (json.dumps(contents), json.dumps(list(statuses)), json.dumps(pr), script)
    path = tmp_path / "gate.js"
    path.write_text(harness, encoding="utf-8")
    proc = subprocess.run([node, str(path)], capture_output=True, text=True, cwd=ROOT,
                          env={"GITHUB_WORKSPACE": str(ROOT), "PATH": os.environ["PATH"]})
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)["failures"]


BUILT = [{"context": "release-built", "state": "success", "creator": {"login": BOT}}]


def test_the_job_runs_on_release_branches_now():
    condition = job()["if"]
    assert "startsWith(github.head_ref, 'release/') ||" in condition
    assert "no-changelog" in condition


def test_the_job_may_read_statuses():
    wf = yaml.safe_load(ASSET.read_text(encoding="utf-8"))
    assert wf["permissions"]["statuses"] == "read"


def test_a_repository_without_release_build_keeps_release_branches_exempt(tmp_path):
    assert gate(tmp_path, head_ref="release/v1.2.0", config={}) == []
    assert gate(tmp_path, head_ref="release/v1.2.0", config=None) == []


def test_a_built_release_pull_request_passes(tmp_path):
    assert gate(tmp_path, head_ref="release/v1.2.0", config={"release_build": True},
                statuses=BUILT) == []


def test_a_release_branch_that_moved_after_the_build_fails(tmp_path):
    assert gate(tmp_path, head_ref="release/v1.2.0",
                config={"release_build": True}) == [BLURB]


def test_the_label_does_not_rescue_a_moved_release_branch(tmp_path):
    assert gate(tmp_path, head_ref="release/v1.2.0", labels=["no-changelog"],
                config={"release_build": True}) == [BLURB]


def test_a_status_someone_else_set_does_not_count(tmp_path):
    fake = [{**BUILT[0], "creator": {"login": "oetiker"}}]
    assert gate(tmp_path, head_ref="release/v1.2.0", config={"release_build": True},
                statuses=fake) == [BLURB]


def test_a_persons_release_branch_gets_the_ordinary_rules(tmp_path):
    failures = gate(tmp_path, head_ref="release/x", login="oetiker",
                    config={"release_build": True})
    assert len(failures) == 1 and "[Unreleased]" in failures[0]
    assert gate(tmp_path, head_ref="release/x", login="oetiker", labels=["no-changelog"],
                config={"release_build": True}) == []


def test_a_forks_release_branch_gets_the_ordinary_rules(tmp_path):
    assert gate(tmp_path, head_ref="release/x", head_repo="fork/r",
                config={"release_build": True}, head_changes=MORE) == []


def test_an_ordinary_pull_request_is_checked_as_before(tmp_path):
    assert gate(tmp_path, head_ref="fix/x", login="oetiker", head_changes=MORE) == []
    assert len(gate(tmp_path, head_ref="fix/x", login="oetiker")) == 1
```

- [ ] **Step 2: Run them to verify they fail**

Run: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests/test_changelog_gate.py`
Expected: FAIL (the job-level `if:` has no `||`; the release-branch tests see no failure).

- [ ] **Step 3: Rewrite the asset**

`skills/repo-infra/assets/workflows/changelog.yml`, whole file:

```yaml
name: Changelog
# repo-infra: changelog v3
#
# Required, not advisory (spec D2). Being required is only safe because the
# escape hatch below is a JOB-level `if:`. A job skipped by a condition
# reports Success, while a WORKFLOW skipped by a paths/branches filter stays
# Pending forever and blocks the merge. Never add paths: or paths-ignore: to
# this workflow (spec D13).
#
# The release PR is not blocked by being GITHUB_TOKEN-authored: its runs are
# created in an approval-required state and start when a maintainer clicks
# "Approve workflows to run".

on:
  pull_request:
    branches: [main]
    types: [opened, synchronize, reopened, labeled, unlabeled]

permissions:
  contents: read
  pull-requests: read
  # D26: the release-built commit status on a release pull request's head.
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
    # release/* always runs (D26): on a repository with release_build set, a
    # release pull request is gated on its build below, and the label must
    # not turn that red check green after an Update branch.
    if: >-
      startsWith(github.head_ref, 'release/') ||
      !contains(github.event.pull_request.labels.*.name, 'no-changelog')
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v7

      - uses: actions/github-script@v9
        with:
          script: |
            const lib = `${process.env.GITHUB_WORKSPACE}/.github/workflows/lib`;
            const changes = require(`${lib}/changes.js`);
            const releaseLib = require(`${lib}/release.js`);
            const { owner, repo } = context.repo;
            const pr = context.payload.pull_request;

            // Both sides come from the API rather than from the checkout. On a
            // pull_request event the checkout is the merge commit, and comparing
            // against a base that is not in a shallow clone needs fetch-depth: 0.
            const read = async (path, ref) => {
              const { data } = await github.rest.repos.getContent({ owner, repo, path, ref });
              return Buffer.from(data.content, 'base64').toString('utf8');
            };

            if (pr.head.ref.startsWith('release/')) {
              // From the base commit: a pull request must not be able to turn
              // its own gate off.
              let config = {};
              try {
                config = JSON.parse(await read('.github/repo-infra.json', pr.base.sha));
              } catch (error) {
                if (error.status !== 404) throw error;
              }
              if (!config.release_build) {
                core.notice('release/* is exempt: the release workflow writes CHANGES.md itself.');
                return;
              }
              if (releaseLib.isReleasePr(pr, `${owner}/${repo}`)) {
                const statuses = await github.paginate(
                  github.rest.repos.listCommitStatusesForRef,
                  { owner, repo, ref: pr.head.sha, per_page: 100 },
                );
                if (!releaseLib.releaseBuilt(statuses)) {
                  core.setFailed(
                    'the release branch changed after it was built (the Update branch '
                    + 'button does this); close this pull request and dispatch Create '
                    + 'release PR again'
                  );
                  return;
                }
                core.notice(`${pr.head.sha} is the commit the release was built from.`);
                return;
              }
              // Anyone else's release/* branch: the ordinary rules, label included.
            }

            if (pr.labels.some((label) => label.name === 'no-changelog')) {
              core.notice("Labelled 'no-changelog'.");
              return;
            }

            const base = changes.unreleasedBlock(await read('CHANGES.md', pr.base.sha));
            const head = changes.unreleasedBlock(await read('CHANGES.md', pr.head.sha));

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

In `manifest.json`: `"changelog": {"version": 3, ...}`.

- [ ] **Step 4: Re-render and run the suite**

Re-render (Global Constraints), then `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests`.
Expected: PASS, including `test_no_required_workflow_carries_a_path_filter[changelog.yml]` and `test_self_render.py`.

- [ ] **Step 5: Commit**

```bash
git add skills/repo-infra/assets/workflows/changelog.yml skills/repo-infra/assets/manifest.json .github/workflows/changelog.yml tests/test_changelog_gate.py
git commit -m "changelog v3: a release pull request must be the commit that was built (D26)"
```

---

### Task 9: publish frame v4, finalize and the add-ons' explicit ref (D26)

**Files:**
- Modify: `skills/repo-infra/assets/publish/publish-frame.yml` (marker `release-publish v4`, the `publish` job)
- Modify: `skills/repo-infra/assets/publish/publish-finalize.yml`
- Modify: `skills/repo-infra/assets/publish/publish-source-tarball.yml` (marker v3, checkout `ref:`)
- Modify: `skills/repo-infra/assets/publish/publish-crates-io.yml` (marker v2, checkout `ref:`)
- Modify: `skills/repo-infra/assets/manifest.json` (block versions)
- Modify: `tests/test_publish.py` (version pins, finalize harness)
- Create: `tests/test_publish_build.py`
- Modify (re-render): `.github/workflows/release-publish.yml`

**Interfaces:**
- Consumes: `publish.js` `publishDecision`, `validateBuildRecord` (Task 5); `release.js` `BUILD_RECORD`.
- Produces: `publish` job output `head` (the commit that was tagged: `context.sha` without `release_build`, the recorded head with it). Every add-on and `finalize` check out `${{ needs.publish.outputs.head }}`.

- [ ] **Step 1: Write the failing tests**

`tests/test_publish_build.py`:

```python
"""The publish job with release_build set (D26), run under node against a fake API."""

import json
import os
import pathlib
import shutil
import subprocess

import pytest
import yaml

from repo_infra.assemble import assemble_publish

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
MAIN = "m" * 40
HEAD = "a" * 40
CHANGES = "# Changes\n\n## [Unreleased]\n\n## 1.2.0 - 2026-09-29\n\n### New\n\n- x\n"
AT_HEAD_OLD = "# Changes\n\n## [Unreleased]\n\n## 1.1.0 - 2026-09-01\n"


def workflow(addons=()):
    return yaml.safe_load(assemble_publish(ASSETS, list(addons), MANIFEST))


def publish_script():
    steps = workflow()["jobs"]["publish"]["steps"]
    return next(s["with"]["script"] for s in steps if s.get("id") == "publish")


def draft(record=True, rid=5, published=False):
    assets = [{"id": 901, "name": "x.deb"}]
    if record:
        assets.append({"id": 900, "name": "release-build.json"})
    return {"id": rid, "tag_name": "v1.2.0", "draft": not published, "assets": assets}


def run(tmp_path, *, release_build=True, tag=None, releases=(), record=None,
        changes_at_head=CHANGES, compare="ahead"):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    ws = tmp_path / "ws"
    shutil.copytree(ROOT / ".github/workflows/lib", ws / ".github/workflows/lib")
    (ws / "CHANGES.md").write_text(CHANGES)
    (ws / ".github/repo-infra.json").write_text(json.dumps(
        {"version_files": [], "release_build": release_build}))
    state = {"tag": tag, "releases": list(releases), "record": record,
             "changesAtHead": changes_at_head, "compare": compare}
    harness = """
const state = %s;
const calls = [];
const outputs = {};
const failures = [];
const notices = [];
const notFound = () => { const e = new Error('Not Found'); e.status = 404; return e; };
const github = {
  paginate: async (fn) => (fn === 'listReleases' ? state.releases : []),
  rest: {
    git: {
      getRef: async () => { if (!state.tag) throw notFound();
        return { data: { object: { type: 'tag', sha: 'tagobject' } } }; },
      getTag: async () => ({ data: { object: { sha: state.tag } } }),
      createTag: async (a) => { calls.push(['createTag', a]); return { data: { sha: `obj-${a.tag}` } }; },
      createRef: async (a) => { calls.push(['createRef', a]); return { data: {} }; },
      updateRef: async (a) => { calls.push(['updateRef', a]); return { data: {} }; },
    },
    repos: {
      listReleases: 'listReleases',
      getReleaseAsset: async (a) => { calls.push(['getReleaseAsset', a]);
        return { data: Buffer.from(JSON.stringify(state.record)) }; },
      getContent: async (a) => { calls.push(['getContent', a]);
        if (state.changesAtHead === null) throw notFound();
        return { data: { content: Buffer.from(state.changesAtHead).toString('base64') } }; },
      updateRelease: async (a) => { calls.push(['updateRelease', a]); return { data: {} }; },
      createRelease: async (a) => { calls.push(['createRelease', a]); return { data: { id: 77 } }; },
      compareCommitsWithBasehead: async (a) => ({ data: { status: state.compare } }),
    },
  },
};
const core = {
  setFailed: (m) => failures.push(m), notice: (m) => notices.push(m),
  setOutput: (k, v) => { outputs[k] = v; },
};
const context = { repo: { owner: 'o', repo: 'r' }, sha: '%s' };
(async () => {
%s
})().then(() => console.log(JSON.stringify({ calls, outputs, failures, notices })));
""" % (json.dumps(state), MAIN, publish_script())
    path = tmp_path / "publish.js"
    path.write_text(harness, encoding="utf-8")
    proc = subprocess.run([node, str(path)], capture_output=True, text=True, cwd=ws,
                          env={"GITHUB_WORKSPACE": str(ws), "PATH": os.environ["PATH"]})
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def called(out, name):
    return [args for n, args in out["calls"] if n == name]


def test_without_release_build_the_merge_commit_is_tagged_as_before(tmp_path):
    out = run(tmp_path, release_build=False)
    assert [t["object"] for t in called(out, "createTag")] == [MAIN]
    assert out["outputs"]["head"] == MAIN
    assert len(called(out, "createRelease")) == 1


def test_case_3_tags_the_recorded_head_not_the_merge_commit(tmp_path):
    out = run(tmp_path, releases=[draft()], record={"head": HEAD})
    assert out["failures"] == []
    assert [t["object"] for t in called(out, "createTag")] == [HEAD]
    assert called(out, "createRef")[0]["ref"] == "refs/tags/v1.2.0"
    (update,) = called(out, "updateRelease")
    assert (update["release_id"], update["tag_name"], update["target_commitish"]) == (
        5, "v1.2.0", HEAD)
    assert out["outputs"] == {"version": "1.2.0", "tag": "v1.2.0", "release_id": "5",
                              "head": HEAD}
    assert called(out, "createRelease") == []


def test_case_3_refuses_a_head_whose_changes_name_another_version(tmp_path):
    out = run(tmp_path, releases=[draft()], record={"head": HEAD},
              changes_at_head=AT_HEAD_OLD)
    assert len(out["failures"]) == 1 and "1.1.0" in out["failures"][0]
    assert called(out, "createTag") == [] and out["outputs"] == {}


def test_case_3_refuses_a_head_that_does_not_exist(tmp_path):
    out = run(tmp_path, releases=[draft()], record={"head": HEAD}, changes_at_head=None)
    assert len(out["failures"]) == 1 and called(out, "createTag") == []


def test_case_2_resumes_at_the_tag_commit_without_retagging(tmp_path):
    out = run(tmp_path, tag=HEAD, releases=[draft(record=False)])
    assert out["failures"] == []
    assert called(out, "createTag") == [] and called(out, "createRef") == []
    assert out["outputs"]["head"] == HEAD
    assert called(out, "updateRelease")[0]["target_commitish"] == HEAD


def test_case_1_an_ordinary_merge_after_the_release_does_nothing(tmp_path):
    out = run(tmp_path, tag=HEAD, releases=[draft(record=False, published=True)])
    assert out["failures"] == [] and out["outputs"] == {} and out["calls"] == []


def test_case_4_a_tag_without_a_release_fails_and_says_so(tmp_path):
    out = run(tmp_path, tag=HEAD, releases=[])
    assert len(out["failures"]) == 1 and "no release" in out["failures"][0]


def test_a_squash_merge_is_noticed(tmp_path):
    out = run(tmp_path, releases=[draft()], record={"head": HEAD}, compare="diverged")
    assert any("merge commit" in n for n in out["notices"])


@pytest.mark.parametrize("addon", ["publish-source-tarball", "publish-crates-io"])
def test_every_addon_checks_out_the_tagged_head(addon):
    job = workflow([addon])["jobs"][addon]
    checkout = next(s for s in job["steps"] if s.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["ref"] == "${{ needs.publish.outputs.head }}"


def test_finalize_checks_out_the_tagged_head():
    job = workflow()["jobs"]["finalize"]
    checkout = next(s for s in job["steps"] if s.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["ref"] == "${{ needs.publish.outputs.head }}"


def test_publish_exposes_the_head():
    assert workflow()["jobs"]["publish"]["outputs"]["head"] == "${{ steps.publish.outputs.head }}"
```

In `tests/test_publish.py`:
- `test_the_frame_marker_survives_assembly`: `("release-publish", 4)`.
- `test_the_tarball_addon_carries_its_marker`: `("publish-source-tarball", 3)`.
- `test_the_crates_io_addon_carries_its_marker`: `("publish-crates-io", 2)`.
- In `_run_finalize`, change the signature to `def _run_finalize(tmp_path, attached, local=(DEB,), workspace=ROOT):`, the fake `paginate` to `async () => attached.map((name, i) => ({ name, id: i + 1 }))`, add `const deleted = [];` and `deleteReleaseAsset: async (a) => { deleted.push(a.asset_id); },` beside `updateRelease`, record the order with `const order = [];` (push `'delete'` and `'publish'` in the two fakes), print `{ published: published.length, failures, deleted, order }`, and pass `env={"GITHUB_WORKSPACE": str(workspace), ...}` and `cwd=workspace`.
- Append:

```python
def _build_workspace(tmp_path, release_assets):
    ws = tmp_path / "ws"
    shutil.copytree(ROOT / ".github/workflows/lib", ws / ".github/workflows/lib")
    (ws / ".github/repo-infra.json").write_text(json.dumps(
        {"version_files": [], "release_build": True, "release_assets": release_assets}))
    return ws


def test_finalize_asserts_release_assets_when_the_release_was_built(tmp_path):
    ws = _build_workspace(tmp_path, ["*.rpm"])
    out = _run_finalize(tmp_path, ["x_1.2.3_amd64.deb", "release-build.json"],
                        local=(), workspace=ws)
    assert out["published"] == 0 and "*.rpm" in out["failures"][0]
    assert out["deleted"] == []


def test_finalize_deletes_the_build_record_before_it_publishes(tmp_path):
    ws = _build_workspace(tmp_path, ["*.deb"])
    out = _run_finalize(tmp_path, ["x_1.2.3_amd64.deb", "release-build.json"],
                        local=(), workspace=ws)
    assert out["failures"] == [] and out["published"] == 1
    assert out["deleted"] == [2]
    assert out["order"] == ["delete", "publish"]
```

(`shutil` needs importing at the top of `test_publish.py` if it is not.)

- [ ] **Step 2: Run them to verify they fail**

Run: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests/test_publish_build.py tests/test_publish.py`
Expected: FAIL (no `head` output; markers still at the old versions).

- [ ] **Step 3: Rewrite the `publish` job of the frame**

In `publish-frame.yml`: marker line `# repo-infra: release-publish v4`. Replace the header paragraph that starts `There is deliberately no workflow_dispatch.` with:

```yaml
# There is deliberately no workflow_dispatch. Publishing should be a consequence
# of merging a release pull request, never something started from a dropdown.
#
# Recovery without release_build: `publish` is idempotent by tag presence, so a
# whole-workflow re-run after the tag exists skips everything and the release
# stays a draft. Use **Re-run failed jobs**, which keeps the successful job's
# outputs. With release_build (D26), `publish` decides from the tag and the
# releases together (lib/publish.js), and both kinds of re-run finish a
# stopped release.
```

Add `head: ${{ steps.publish.outputs.head }}` to the job's `outputs`. Replace the script from the line `// Idempotent: an ordinary pull request` to the end with:

```js
            // Annotated, not a bare createRef. A bare ref makes a lightweight tag,
            // and `git describe` prefers annotated ones; the existing repositories
            // have annotated tags and a silent switch would change local tooling
            // behaviour for no reason.
            const makeTag = async (name, message, sha) => {
              const { data: object } = await github.rest.git.createTag({
                owner, repo, tag: name, message, object: sha, type: 'commit',
              });
              return object.sha;
            };
            const moveMajor = async (sha) => {
              if (!config.moving_major_tag) return;
              const major = `v${version.split('.')[0]}`;
              const tagSha = await makeTag(major, `Update ${major} to ${tag}`, sha);
              try {
                await github.rest.git.updateRef({
                  owner, repo, ref: `tags/${major}`, sha: tagSha, force: true,
                });
              } catch (error) {
                if (error.status !== 422) throw error;
                await github.rest.git.createRef({
                  owner, repo, ref: `refs/tags/${major}`, sha: tagSha,
                });
              }
              core.notice(`Moved ${major} to ${tag}.`);
            };

            if (!config.release_build) {
              // Idempotent: an ordinary pull request that edits [Unreleased] also
              // triggers this workflow, finds the tag already present, and stops.
              try {
                await github.rest.git.getRef({ owner, repo, ref: `tags/${tag}` });
                core.notice(`${tag} is already tagged - nothing to do.`);
                return;
              } catch (error) {
                if (error.status !== 404) throw error;
              }

              await github.rest.git.createRef({
                owner, repo, ref: `refs/tags/${tag}`,
                sha: await makeTag(tag, `Release ${tag}`, context.sha),
              });
              core.notice(`Tagged ${tag}.`);
              await moveMajor(context.sha);

              // Draft, so publish add-ons can attach artifacts before anyone
              // sees the release. The finalize job below publishes it.
              const { data: created } = await github.rest.repos.createRelease({
                owner, repo,
                tag_name: tag,
                name: tag,
                body: changesLib.notesFor(fileIO.read('CHANGES.md'), version),
                draft: true,
                prerelease: false,
                make_latest: 'true',
              });

              core.setOutput('version', version);
              core.setOutput('tag', tag);
              core.setOutput('release_id', String(created.id));
              core.setOutput('head', context.sha);
              return;
            }

            // release_build (D26): the release pull request built the release
            // into a draft. Tag the commit that was built, not this merge.
            const publishLib = require(`${lib}/publish.js`);
            let tagCommit = null;
            try {
              const { data: ref } = await github.rest.git.getRef({
                owner, repo, ref: `tags/${tag}`,
              });
              // publish makes annotated tags: the ref points at a tag object.
              tagCommit = ref.object.type === 'tag'
                ? (await github.rest.git.getTag({ owner, repo, tag_sha: ref.object.sha }))
                  .data.object.sha
                : ref.object.sha;
            } catch (error) {
              if (error.status !== 404) throw error;
            }
            // getReleaseByTag answers 404 for a draft; list them instead.
            const releases = (await github.paginate(github.rest.repos.listReleases, {
              owner, repo, per_page: 100,
            })).filter((r) => r.tag_name === tag);

            const decision = publishLib.publishDecision({ tag, tagCommit, releases });
            if (decision.action === 'done') {
              core.notice(`${tag} is released - nothing to do.`);
              return;
            }
            if (decision.action === 'fail') {
              core.setFailed(decision.message);
              return;
            }

            let head = decision.head;
            if (decision.action === 'create') {
              // browser_download_url does not serve drafts; the API does.
              const { data: raw } = await github.rest.repos.getReleaseAsset({
                owner, repo, asset_id: decision.recordAssetId,
                headers: { accept: 'application/octet-stream' },
              });
              const record = JSON.parse(Buffer.from(raw).toString('utf8'));
              let latestAtHead = null;
              try {
                const { data } = await github.rest.repos.getContent({
                  owner, repo, path: 'CHANGES.md', ref: record.head,
                });
                latestAtHead = changesLib.latestRelease(
                  Buffer.from(data.content, 'base64').toString('utf8'),
                );
              } catch (error) {
                if (error.status !== 404 && error.status !== 422) throw error;
              }
              const problem = publishLib.validateBuildRecord(record, version, latestAtHead);
              if (problem) {
                core.setFailed(`${tag}: ${problem}. Nothing was tagged.`);
                return;
              }
              head = record.head;
              await github.rest.git.createRef({
                owner, repo, ref: `refs/tags/${tag}`,
                sha: await makeTag(tag, `Release ${tag}`, head),
              });
              core.notice(`Tagged ${tag} at the built commit ${head}.`);
            }

            // Idempotent, so a resumed run repeats it harmlessly.
            await github.rest.repos.updateRelease({
              owner, repo, release_id: decision.releaseId,
              tag_name: tag, target_commitish: head,
            });
            await moveMajor(head);

            const { data: compared } = await github.rest.repos.compareCommitsWithBasehead({
              owner, repo, basehead: `${head}...${context.sha}`,
            });
            if (compared.status === 'diverged') {
              core.notice(`${tag} is not on main's history (the release pull request `
                + 'was squashed or rebased). The release is correct; git describe on '
                + 'main will not find it. RELEASING.md recommends a merge commit.');
            }

            core.setOutput('version', version);
            core.setOutput('tag', tag);
            core.setOutput('release_id', String(decision.releaseId));
            core.setOutput('head', head);
```

- [ ] **Step 4: finalize**

In `publish-finalize.yml`, give the checkout step `with: ref: ${{ needs.publish.outputs.head }}` and a comment `# The tagged head: a re-run reads release_assets the same way.`. In the script, after the `assetsLib` require add:

```js
            const fs = require('fs');
            const releaseLib = require(`${lib}/release.js`);
            const config = JSON.parse(fs.readFileSync(
              `${process.env.GITHUB_WORKSPACE}/.github/repo-infra.json`, 'utf8'));
```

Keep the generated `const expected = [];` line exactly as it is. Below it add:

```js
            // D26: a release the pull request built must carry every file the
            // repository declared, read at the tagged head.
            const declared = config.release_build ? (config.release_assets || []) : [];
```

Change `assetsLib.missingAssets(names, expected)` to `assetsLib.missingAssets(names, [...expected, ...declared])`. Between the `if (missing.length > 0) {...}` block and `updateRelease`, add:

```js
            // The build record is never public. Deleting it after publishing
            // would be impossible with GitHub's immutable releases on.
            const record = attached.find((a) => a.name === releaseLib.BUILD_RECORD);
            if (record) {
              try {
                await github.rest.repos.deleteReleaseAsset({ owner, repo, asset_id: record.id });
              } catch (error) {
                if (error.status !== 404) throw error;
              }
            }
```

- [ ] **Step 5: The add-ons check out the tagged head**

In `publish-source-tarball.yml` (marker `v3`) and `publish-crates-io.yml` (marker `v2`), give `- uses: actions/checkout@v7` a `with: ref: ${{ needs.publish.outputs.head }}`. In `publish-crates-io.yml` replace the comment above it (`# No ref: on a push event ...`) with:

```yaml
      # The commit `publish` tagged: the merge commit, or with release_build
      # (D26) the commit the release pull request built. Either way its
      # Cargo.toml carries the bumped version.
```

In `manifest.json`: `publish-source-tarball` `"version": 3`, `publish-crates-io` `"version": 2`.

- [ ] **Step 6: Re-render and run everything**

Re-render (Global Constraints). Run: `node --test skills/repo-infra/assets/workflows/lib/*.test.js` and `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests`.
Expected: PASS. repo-infra's own `release-publish.yml` now carries `release-publish v4` and the new finalize.

- [ ] **Step 7: Commit**

```bash
git add skills/repo-infra/assets/publish skills/repo-infra/assets/manifest.json .github/workflows/release-publish.yml tests/test_publish.py tests/test_publish_build.py
git commit -m "release-publish v4: tag the built commit, resume a stopped release, keep the build record private (D26)"
```

---
## Phase 3: Gitea packages (D27)

### Task 10: `gitea.js`, names, URLs and the 409 verdict (D27)

**Files:**
- Create: `skills/repo-infra/assets/workflows/lib/gitea.js`
- Create: `skills/repo-infra/assets/workflows/lib/gitea.test.js`
- Modify (re-render): `.github/workflows/lib/`

**Interfaces:**
- Produces:
  - `packageConfig(config) -> { url, owner, distribution, component, group }`, throws when `gitea_packages.url` or `.owner` is missing
  - `parsePackageFile(fileName) -> { kind: 'debian' | 'rpm', name, version, arch, file } | null`
  - `uploadUrl(cfg, pkg) -> string`, `filesUrl(cfg, pkg) -> string`
  - `missingCredentials(env) -> string[]`
  - `conflictVerdict(pkg, assetSha256, files) -> { ok: boolean, message: string }`; `files` is the JSON array Gitea's `GET /api/v1/packages/{owner}/{type}/{name}/{version}/files` returns (`[{ name, sha256, ... }]`).

- [ ] **Step 1: Write the failing test**

`skills/repo-infra/assets/workflows/lib/gitea.test.js`:

```js
// repo-infra: workflow-lib v5
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const g = require('./gitea.js');

const CONFIG = { gitea_packages: { url: 'https://gitea.oetiker.ch/', owner: 'oposs' } };
const CFG = g.packageConfig(CONFIG);

test('the default layout is one channel', () => {
  assert.deepEqual(CFG, {
    url: 'https://gitea.oetiker.ch', owner: 'oposs',
    distribution: 'stable', component: 'main', group: '',
  });
});

test('a config without url or owner is refused', () => {
  assert.throws(() => g.packageConfig({}), /gitea_packages/);
  assert.throws(() => g.packageConfig({ gitea_packages: { url: 'https://x' } }), /owner/);
});

test('cargo-deb and cargo-generate-rpm names parse', () => {
  assert.deepEqual(g.parsePackageFile('mdmost_0.5.0-1_amd64.deb'), {
    kind: 'debian', name: 'mdmost', version: '0.5.0-1', arch: 'amd64',
    file: 'mdmost_0.5.0-1_amd64.deb',
  });
  assert.deepEqual(g.parsePackageFile('smtp-proxy-0.1.0-1.aarch64.rpm'), {
    kind: 'rpm', name: 'smtp-proxy', version: '0.1.0-1', arch: 'aarch64',
    file: 'smtp-proxy-0.1.0-1.aarch64.rpm',
  });
});

test('a pre-release deb version with ~ parses', () => {
  assert.equal(g.parsePackageFile('mdmost_1.0.0~rc.1-1_arm64.deb').version, '1.0.0~rc.1-1');
});

test('anything else is not a package', () => {
  for (const name of ['mdmost-0.5.0-x86_64-unknown-linux-musl.tar.gz', 'release-build.json',
    'mdmost.deb', 'x.rpm']) {
    assert.equal(g.parsePackageFile(name), null, name);
  }
});

test('upload urls follow the Gitea API, rpm is always signed', () => {
  assert.equal(g.uploadUrl(CFG, g.parsePackageFile('mdmost_0.5.0-1_amd64.deb')),
    'https://gitea.oetiker.ch/api/packages/oposs/debian/pool/stable/main/upload');
  assert.equal(g.uploadUrl(CFG, g.parsePackageFile('mdmost-0.5.0-1.x86_64.rpm')),
    'https://gitea.oetiker.ch/api/packages/oposs/rpm/upload?sign=true');
  assert.equal(g.uploadUrl({ ...CFG, group: 'el9' }, g.parsePackageFile('mdmost-0.5.0-1.x86_64.rpm')),
    'https://gitea.oetiker.ch/api/packages/oposs/rpm/el9/upload?sign=true');
});

test('the files url names type, package and version', () => {
  assert.equal(g.filesUrl(CFG, g.parsePackageFile('mdmost_1.0.0~rc.1-1_amd64.deb')),
    'https://gitea.oetiker.ch/api/v1/packages/oposs/debian/mdmost/1.0.0~rc.1-1/files');
});

test('missing credentials are named, both of them', () => {
  assert.deepEqual(g.missingCredentials({}), ['GITEA_PACKAGE_TOKEN', 'GITEA_PACKAGE_USER']);
  assert.deepEqual(g.missingCredentials({ GITEA_PACKAGE_TOKEN: 't', GITEA_PACKAGE_USER: '' }),
    ['GITEA_PACKAGE_USER']);
  assert.deepEqual(g.missingCredentials({ GITEA_PACKAGE_TOKEN: 't', GITEA_PACKAGE_USER: 'u' }), []);
});

const DEB = g.parsePackageFile('mdmost_0.5.0-1_amd64.deb');
const RPM = g.parsePackageFile('mdmost-0.5.0-1.x86_64.rpm');

test('a 409 for a deb with the same SHA-256 is success', () => {
  const v = g.conflictVerdict(DEB, 'abc', [{ name: DEB.file, sha256: 'abc' }]);
  assert.equal(v.ok, true);
  assert.match(v.message, /SHA-256/);
});

test('a 409 for a different deb under the same version fails', () => {
  const v = g.conflictVerdict(DEB, 'abc', [{ name: DEB.file, sha256: 'def' }]);
  assert.equal(v.ok, false);
  assert.match(v.message, /different/);
});

test('a 409 for an rpm matches by file name and says the content was not compared', () => {
  const v = g.conflictVerdict(RPM, 'abc', [{ name: RPM.file, sha256: 'signed' }]);
  assert.equal(v.ok, true);
  assert.match(v.message, /not compared/);
});

test('a 409 whose file Gitea does not list fails for either kind', () => {
  assert.equal(g.conflictVerdict(DEB, 'abc', []).ok, false);
  assert.equal(g.conflictVerdict(RPM, 'abc', [{ name: 'mdmost-0.5.0-1.aarch64.rpm' }]).ok, false);
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `node --test skills/repo-infra/assets/workflows/lib/gitea.test.js`
Expected: FAIL with `Cannot find module './gitea.js'`

- [ ] **Step 3: Write the implementation**

`skills/repo-infra/assets/workflows/lib/gitea.js`:

```js
// repo-infra: workflow-lib v5
'use strict';

// publish-gitea-packages (D27): which release assets are packages, where
// Gitea wants them, and what a 409 on a re-run means.

function packageConfig(config) {
  const c = (config || {}).gitea_packages;
  if (!c || !c.url) {
    throw new Error('.github/repo-infra.json: "gitea_packages" needs a "url"');
  }
  if (!c.owner) {
    throw new Error('.github/repo-infra.json: "gitea_packages" needs an "owner"');
  }
  return {
    url: c.url.replace(/\/+$/, ''),
    owner: c.owner,
    distribution: (c.debian && c.debian.distribution) || 'stable',
    component: (c.debian && c.debian.component) || 'main',
    group: (c.rpm && c.rpm.group) || '',
  };
}

// name_version_arch.deb (cargo-deb) and name-version-release.arch.rpm
// (cargo-generate-rpm). Gitea's RPM version is the version-release pair.
const DEB = /^([a-z0-9][a-z0-9+.-]*)_([^_/]+)_([a-z0-9]+)\.deb$/;
const RPM = /^(.+)-([^-/]+)-([^-/]+)\.([A-Za-z0-9_]+)\.rpm$/;

function parsePackageFile(file) {
  let m = DEB.exec(file);
  if (m) return { kind: 'debian', name: m[1], version: m[2], arch: m[3], file };
  m = RPM.exec(file);
  if (m) return { kind: 'rpm', name: m[1], version: `${m[2]}-${m[3]}`, arch: m[4], file };
  return null;
}

const seg = encodeURIComponent;

function uploadUrl(cfg, pkg) {
  const base = `${cfg.url}/api/packages/${seg(cfg.owner)}`;
  if (pkg.kind === 'debian') {
    return `${base}/debian/pool/${seg(cfg.distribution)}/${seg(cfg.component)}/upload`;
  }
  // Gitea's generated .repo sets gpgcheck=1, so an unsigned rpm would not
  // install. Gitea signs with its per-owner key.
  return `${base}/rpm${cfg.group ? `/${seg(cfg.group)}` : ''}/upload?sign=true`;
}

function filesUrl(cfg, pkg) {
  // `~` is unreserved; encodeURIComponent leaves it alone.
  return `${cfg.url}/api/v1/packages/${seg(cfg.owner)}/${pkg.kind}/`
    + `${seg(pkg.name)}/${seg(pkg.version)}/files`;
}

function missingCredentials(env) {
  return ['GITEA_PACKAGE_TOKEN', 'GITEA_PACKAGE_USER'].filter((k) => !env[k]);
}

// Gitea answers 409 for a version it already has. On a re-run after a partial
// upload that is the file that went up the first time -- or a different file
// under the same version, which must fail.
function conflictVerdict(pkg, assetSha256, files) {
  const stored = (files || []).find((f) => f.name === pkg.file);
  if (!stored) {
    return { ok: false, message: `${pkg.file}: Gitea answered 409 but lists no such file` };
  }
  if (pkg.kind === 'debian') {
    return stored.sha256 === assetSha256
      ? { ok: true, message: `${pkg.file}: already uploaded, SHA-256 matches` }
      : { ok: false, message: `${pkg.file}: Gitea holds a different file under this version` };
  }
  // With ?sign=true Gitea stores the signed file, whose SHA-256 never equals
  // the unsigned asset's.
  return {
    ok: true,
    message: `${pkg.file}: already uploaded; name, version-release and architecture `
      + 'match; the content was not compared (Gitea stores the signed file)',
  };
}

module.exports = {
  packageConfig, parsePackageFile, uploadUrl, filesUrl, missingCredentials, conflictVerdict,
};
```

- [ ] **Step 4: Run the JS suite, re-render, run the Python suite, commit**

Run: `node --test skills/repo-infra/assets/workflows/lib/*.test.js` (PASS); re-render; `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests` (PASS).

```bash
git add skills/repo-infra/assets/workflows/lib .github/workflows/lib
git commit -m "workflow-lib: gitea.js, package names, upload URLs and the 409 verdict (D27)"
```

---

### Task 11: the `publish-gitea-packages` block (D27)

**Files:**
- Create: `skills/repo-infra/assets/publish/publish-gitea-packages.yml`
- Modify: `skills/repo-infra/assets/manifest.json` (`publish_blocks`)
- Create: `tests/test_publish_gitea.py`

**Interfaces:**
- Consumes: `gitea.js` (Task 10); `publish` outputs `release_id` and `head` (Task 9).

- [ ] **Step 1: Write the failing tests**

`tests/test_publish_gitea.py`:

```python
"""publish-gitea-packages (D27)."""

import json
import pathlib

import yaml

from repo_infra.assemble import assemble_publish, block_job_ids

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
BLOCK = "publish-gitea-packages"


def workflow():
    return yaml.safe_load(assemble_publish(ASSETS, [BLOCK], MANIFEST))


def job():
    return workflow()["jobs"][BLOCK]


def script():
    return next(s["with"]["script"] for s in job()["steps"] if "script" in s.get("with", {}))


def test_the_block_declares_its_one_job():
    text = (ASSETS / f"publish/{BLOCK}.yml").read_text(encoding="utf-8")
    assert block_job_ids(text) == MANIFEST["publish_blocks"][BLOCK]["jobs"] == [BLOCK]


def test_a_failed_upload_keeps_the_release_a_draft():
    # Blocking: a version public on GitHub but absent from apt and dnf is the
    # inconsistency worth preventing.
    assert BLOCK in workflow()["jobs"]["finalize"]["needs"]


def test_it_waits_for_publish_and_honours_the_guard():
    assert job()["needs"] == ["publish"]
    assert job()["if"] == "needs.publish.outputs.release_id != ''"


def test_it_can_see_the_draft():
    # A token that cannot push cannot see a draft release or its assets.
    assert job()["permissions"] == {"contents": "write"}


def test_the_credential_reaches_the_script_only_through_env():
    step = next(s for s in job()["steps"] if "script" in s.get("with", {}))
    assert step["env"] == {
        "GITEA_PACKAGE_TOKEN": "${{ secrets.GITEA_PACKAGE_TOKEN }}",
        "GITEA_PACKAGE_USER": "${{ vars.GITEA_PACKAGE_USER }}",
    }
    assert "secrets." not in script()


def test_it_refuses_before_uploading_anything():
    s = script()
    for guard in ("packageConfig", "missingCredentials", "no .deb or .rpm"):
        assert s.index(guard) < s.index("method: 'PUT'"), guard


def test_a_conflict_is_judged_not_ignored():
    s = script()
    assert "res.status === 409" in s and "conflictVerdict" in s


def test_every_job_has_a_timeout():
    assert isinstance(job()["timeout-minutes"], int)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests/test_publish_gitea.py`
Expected: FAIL (`publish add-on publish-gitea-packages is not declared in the manifest`).

- [ ] **Step 3: Write the block**

`skills/repo-infra/assets/publish/publish-gitea-packages.yml`:

```yaml
  # D27. Uploads every .deb and .rpm on the release to the Gitea package
  # registry named in .github/repo-infra.json "gitea_packages". Gitea signs
  # the Debian and RPM metadata and, with ?sign=true, each rpm, with its own
  # per-owner key; no repository holds a signing key.
  #
  # The credential is a dedicated Gitea user's token, scope write:package, in
  # the GitHub organisation secret GITEA_PACKAGE_TOKEN with the variable
  # GITEA_PACKAGE_USER. A repository under a personal account carries its own
  # copy of both (references/release-flow.md).
  publish-gitea-packages:
    name: Publish packages to Gitea
    needs: [publish]
    if: needs.publish.outputs.release_id != ''
    runs-on: ubuntu-latest
    timeout-minutes: 20
    # write, not read: a draft release and its assets are invisible to a token
    # that cannot push.
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ needs.publish.outputs.head }}

      - uses: actions/github-script@v9
        env:
          GITEA_PACKAGE_TOKEN: ${{ secrets.GITEA_PACKAGE_TOKEN }}
          GITEA_PACKAGE_USER: ${{ vars.GITEA_PACKAGE_USER }}
        with:
          script: |
            const crypto = require('crypto');
            const fs = require('fs');
            const ws = process.env.GITHUB_WORKSPACE;
            const gitea = require(`${ws}/.github/workflows/lib/gitea.js`);
            const owner = context.repo.owner;
            const repo = context.repo.repo;
            const release_id = Number('${{ needs.publish.outputs.release_id }}');

            let cfg;
            try {
              cfg = gitea.packageConfig(JSON.parse(
                fs.readFileSync(`${ws}/.github/repo-infra.json`, 'utf8')));
            } catch (error) {
              core.setFailed(error.message);
              return;
            }
            const missing = gitea.missingCredentials(process.env);
            if (missing.length > 0) {
              core.setFailed(`${missing.join(' and ')} is empty. Set the secret `
                + 'GITEA_PACKAGE_TOKEN and the variable GITEA_PACKAGE_USER on the '
                + 'organisation, or on the repository if it belongs to a person.');
              return;
            }

            const assets = await github.paginate(github.rest.repos.listReleaseAssets, {
              owner, repo, release_id, per_page: 100,
            });
            const packages = assets
              .map((asset) => ({ asset, pkg: gitea.parsePackageFile(asset.name) }))
              .filter((entry) => entry.pkg);
            if (packages.length === 0) {
              core.setFailed('The release carries no .deb or .rpm, so '
                + 'publish-gitea-packages would upload nothing. Attached: '
                + `${assets.map((a) => a.name).join(', ') || 'nothing'}.`);
              return;
            }

            const user = process.env.GITEA_PACKAGE_USER;
            const token = process.env.GITEA_PACKAGE_TOKEN;
            const authorization = `Basic ${Buffer.from(`${user}:${token}`).toString('base64')}`;

            for (const { asset, pkg } of packages) {
              // By asset id through the API: browser_download_url does not
              // serve drafts.
              const { data } = await github.rest.repos.getReleaseAsset({
                owner, repo, asset_id: asset.id,
                headers: { accept: 'application/octet-stream' },
              });
              const body = Buffer.from(data);
              const sha256 = crypto.createHash('sha256').update(body).digest('hex');

              const res = await fetch(gitea.uploadUrl(cfg, pkg), {
                method: 'PUT',
                headers: { authorization, 'content-type': 'application/octet-stream' },
                body,
              });
              if (res.ok) {
                core.notice(`${asset.name}: uploaded to ${cfg.owner}'s ${pkg.kind} registry.`);
                continue;
              }
              if (res.status === 409) {
                const list = await fetch(gitea.filesUrl(cfg, pkg), { headers: { authorization } });
                if (!list.ok) {
                  core.setFailed(`${asset.name}: Gitea answered 409, and listing the stored `
                    + `files answered ${list.status}: ${await list.text()}`);
                  return;
                }
                const verdict = gitea.conflictVerdict(pkg, sha256, await list.json());
                if (!verdict.ok) {
                  core.setFailed(verdict.message);
                  return;
                }
                core.notice(verdict.message);
                continue;
              }
              core.setFailed(`${asset.name}: Gitea answered ${res.status}: ${await res.text()}`);
              return;
            }
```

In `manifest.json` `publish_blocks`:

```json
    "publish-gitea-packages": {"version": 1, "jobs": ["publish-gitea-packages"], "assets": []}
```

- [ ] **Step 4: Run the suite and commit**

Run: `TMPDIR=/scratch/oetiker/claude-tmp/pytest python3 -m pytest -q tests` (PASS, including `test_every_publish_block_declares_what_it_attaches`).

```bash
git add skills/repo-infra/assets/publish/publish-gitea-packages.yml skills/repo-infra/assets/manifest.json tests/test_publish_gitea.py
git commit -m "publish-gitea-packages: .deb and .rpm to a Gitea registry, blocking (D27)"
```

---

### Task 12: documentation and changelog

Load `repo-infra:writing-style` first. No em dash. No internal host names (Global Constraints).

**Files:**
- Modify: `skills/repo-infra/references/conventions.md`
- Modify: `skills/repo-infra/references/release-flow.md`
- Modify: `RELEASING.md`
- Modify: `skills/repo-infra/SKILL.md` (config keys, if it lists them)
- Modify: `docs/superpowers/specs/2026-08-17-repo-infra-design.md` (lines ~1147 and ~1149)
- Modify: `CHANGES.md`

- [ ] **Step 1: `conventions.md`**

Rename the heading `## The action-test contract (D20)` to `## Project-owned workflows behind a fixed seam (D20, D25, D26)` and, after its existing text, add three subsections:

1. `### ci-local (D25)`: `"ci_local": true` in `.github/repo-infra.json` adds `ci-local: uses: ./.github/workflows/ci-local.yml` to `ci.yml` and to `ci-passed`'s `needs:`. The three action-test rules apply unchanged (workflow_call only, `timeout-minutes` on each job, the file must exist; `check` reports a missing one as `conflict`). One more rule: conditions go inside steps, never on a job, because a reusable workflow whose every job is skipped reports `ci-local` as skipped, and `ci-passed` counts that as green.
2. `### release-build (D26)`: `on: workflow_call` with string inputs `version` and `ref`; check out `inputs.ref`; upload each shipped file as an artifact whose name starts `release-asset-`; upload the repository files the build rewrote (for example a Homebrew formula) as one artifact `release-files` whose paths are repository paths, each listed in `release_files`; the job runs with `contents: read` and no secrets. A file named `release-build.json` is refused.
3. `### The "rust" key (D24)`: the example from the spec, the meaning of `lint`, `test`, `tested_elsewhere`, and the four `rust-plan` failures, one line each. State that a repository whose default members differ from its members must set the key, and that `ci-rust` v2 fails on the upgrade pull request until it does.

- [ ] **Step 2: `release-flow.md` and `RELEASING.md`**

Add a section `## Releases that build before the merge (release_build)` to `release-flow.md`: the three jobs; that the formula change is in the pull request diff; that publish tags the recorded head; the Homebrew 404 window between merge and `finalize`, and its recovery (**Re-run failed jobs**); the two refusals of `Create release PR` with the three ways out of the second one, verbatim from the spec (D26, `prepare`); that **Update branch** on a release pull request turns `changelog-updated` red and the fix is to close it and dispatch again; stale drafts are deleted by the next dispatch.

Add `## Gitea packages (publish-gitea-packages)`: the config block, the credential (dedicated Gitea user, team with package write only, token scope `write:package`, org secret `GITEA_PACKAGE_TOKEN` and org variable `GITEA_PACKAGE_USER`, a repository copy for personal-account repositories, manual rotation), the 409 behaviour, and the three "What users type" snippets from the spec, verbatim.

In `RELEASING.md`, add: the merge-commit recommendation for release pull requests of `release_build` repositories (all three methods stay allowed; after squash or rebase `git describe` on `main` no longer finds the tag); do not press **Update branch** on a release pull request; the three ways out of `vX.Y.Z is in CHANGES.md on main but has no tag`.

- [ ] **Step 3: The main design**

In `docs/superpowers/specs/2026-08-17-repo-infra-design.md`, append to the paragraph at line ~1147 ("must move off `main`"): `D26 moves them into the release pull request (2026-09-29-mdmost-conversion-design.md).` Append to the refusal at line ~1149: `Reversed by D27 for Gitea's registry, where Gitea holds the signing key; the upload token is the first stored credential (2026-09-29-mdmost-conversion-design.md).`

- [ ] **Step 4: `CHANGES.md`**

Under `## [Unreleased]`:

```markdown
### New

- A Rust workspace can list which crates `ci-rust` lints and which it tests, in a `rust` key of `.github/repo-infra.json`; each crate gets its own check. A workspace where a plain `cargo test` would skip some crates now fails the `Rust workspace plan` check until the key says where their tests run.
- `"ci_local": true` makes the jobs in `.github/workflows/ci-local.yml` part of the required `ci-passed` check.
- `"release_build": true` builds every release file inside the release pull request, into a draft release. Files such as a Homebrew formula change in that pull request, nothing is pushed to `main` after the merge, and publishing tags the commit that was built.
- The `publish-gitea-packages` add-on uploads a release's `.deb` and `.rpm` files to a Gitea package registry, which signs them; the release stays a draft until the upload succeeded.

### Changed

- The `changelog-updated` check now also runs on `release/*` branches. In a repository with `release_build` it fails when the release branch changed after its build, for example after **Update branch**; elsewhere it passes as before.
- Publish add-ons check out the tagged commit explicitly. Without `release_build` this is the same commit as before.
```

- [ ] **Step 5: Run the full gate and commit**

Run: `mkdir -p /scratch/oetiker/claude-tmp/pytest && TMPDIR=/scratch/oetiker/claude-tmp/pytest make check` (PASS, `test_no_em_dash.py` included).

```bash
git add skills/repo-infra/references RELEASING.md skills/repo-infra/SKILL.md docs/superpowers/specs/2026-08-17-repo-infra-design.md CHANGES.md
git commit -m "Document D24-D27: the rust key, ci-local, release_build, Gitea packages"
```

---
## Phase 4: servers (owner-run)

These tasks change production servers and GitHub settings. The agent drafts each command and verifies from outside; the owner confirms every ssh command one by one (global rule). The host names, the ssh aliases, the upstream address and the nginx snippet belong in the handoff and in an `oep_wiki` note, never in repo-infra.

### Task 13: Gitea bot users, tokens and the GitHub secret

- [ ] **Step 1:** In the Gitea web UI (as admin): create user `oposs-package-writer` and user `oposs-package-reader` (no password login, mail to the owner). In organisation `oposs` create team `package-writers` (unit **Packages**: write, every other unit: none) with the writer as member, and team `package-readers` (Packages: read, others none) with the reader.
- [ ] **Step 2:** Log in as each bot (or use `sudo -u git gitea admin user generate-access-token` on the server, owner-confirmed) and create a token: writer scope `write:package`, reader scope `read:package`. Store both in the owner's password store.
- [ ] **Step 3: Verify the writer from outside**

```bash
curl -sS -o /dev/null -w '%{http_code}\n' -u "oposs-package-writer:$WRITER" \
  https://gitea.oetiker.ch/api/v1/packages/oposs
```

Expected: `200`.

- [ ] **Step 4: GitHub secrets.** The owner runs (the values never pass through the agent):

```bash
gh secret set GITEA_PACKAGE_TOKEN --org oposs --visibility all
gh variable set GITEA_PACKAGE_USER --org oposs --visibility all --body oposs-package-writer
gh secret set GITEA_PACKAGE_TOKEN -R oetiker/mdmost
gh variable set GITEA_PACKAGE_USER -R oetiker/mdmost --body oposs-package-writer
```

Verify: `gh secret list -R oetiker/mdmost` lists `GITEA_PACKAGE_TOKEN`; `gh variable list -R oetiker/mdmost` lists `GITEA_PACKAGE_USER`.

### Task 14: anonymous reads through the proxy, and the wiki note

- [ ] **Step 1: Draft the nginx locations** (in the handoff and the wiki note, not here). One `location` per prefix, `/api/packages/oposs/debian/`, `/api/packages/oposs/rpm/` and `= /api/packages/oposs/rpm.repo`, that: keeps the bare `proxy_pass` of the existing server block; returns 400 when `$request_uri` contains a `.` or `..` segment, `//`, or a percent-encoded `/`, `.`, `?`, `#`, `\` or `%` (case-insensitive `%2f %2e %3f %23 %5c %25`); and, only for `GET`/`HEAD` without an `Authorization` header, sets `proxy_set_header Authorization "token <reader token>"`. Everything else passes unchanged.
- [ ] **Step 2:** The owner applies it on the proxy host, runs `nginx -t`, then reloads (each command confirmed).
- [ ] **Step 3: Verify from outside**

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://gitea.oetiker.ch/api/packages/oposs/debian/repository.key   # 200
curl -sS -o /dev/null -w '%{http_code}\n' https://gitea.oetiker.ch/api/packages/oposs/rpm.repo                # 200
curl -sS -o /dev/null -w '%{http_code}\n' https://gitea.oetiker.ch/api/packages/oposs/generic/x/1/y           # 401
curl -sS -o /dev/null -w '%{http_code}\n' https://gitea.oetiker.ch/api/v1/packages/oposs                       # 401
curl -sS -o /dev/null -w '%{http_code}\n' --path-as-is https://gitea.oetiker.ch/api/packages/oposs/debian/%2e%2e/generic/x   # 400
curl -sS -o /dev/null -w '%{http_code}\n' https://gitea.oetiker.ch/api/packages/oposs/debian/a%2Fb                  # 400
```

- [ ] **Step 4:** Write the `oep_wiki` note with the `oep:wiki-note` skill: bot users, teams, token scopes and where they are stored, the nginx locations as applied, the verification commands, and the rotation procedure (new token, update org secret, repository copies, and the proxy's reader token).

---

## Phase 5: mdmost (the proof)

### Task 15: convert mdmost onto the branch

Work in `/scratch/oetiker/claude-worktrees/mdmost-repo-infra` (Global Constraints). `RI=/scratch/oetiker/claude-worktrees/repo-infra-spec-d24-d27`.

**Files (mdmost):**
- Create: `.github/repo-infra.json`, `.github/workflows/ci-local.yml`
- Modify: `CHANGES.md` (`## Unreleased` -> `## [Unreleased]`), `Makefile` (man rule -> `include build/man.mk`), `Formula/mdmost.rb` (comments that name `release.yml`)
- Delete: `docs/man-deflist.lua`, `.github/workflows/ci.yml`'s old content (replaced by the assembled file)
- Installed by `apply`: `.github/workflows/{ci,changelog,release-pr,release-publish}.yml`, `.github/workflows/lib/`, `.github/dependabot.yml`, `build/man.mk`, `build/man-deflist.lua`

- [ ] **Step 1: Write `.github/repo-infra.json`**

```json
{
  "ecosystems": ["rust"],
  "moving_major_tag": false,
  "version_files": [
    {
      "path": "Cargo.toml",
      "pattern": "^version\\s*=\\s*\"[^\"]*\"",
      "replacement": "version = \"$VERSION\"",
      "verify": "^version\\s*=\\s*\"$VERSION\""
    }
  ],
  "ci": ["ci-man", "ci-rust-musl"],
  "ci_local": true,
  "release_build": true,
  "publish": ["publish-gitea-packages"],
  "build": [],
  "release_files": ["Formula/mdmost.rb"],
  "release_assets": [
    "mdmost-*-x86_64-unknown-linux-musl.tar.gz",
    "mdmost-*-aarch64-unknown-linux-musl.tar.gz",
    "mdmost-*-x86_64-apple-darwin.tar.gz",
    "mdmost-*-aarch64-apple-darwin.tar.gz",
    "mdmost-*-x86_64-pc-windows-msvc.zip",
    "mdmost_*_amd64.deb", "mdmost_*_arm64.deb",
    "mdmost-*.x86_64.rpm", "mdmost-*.aarch64.rpm",
    "mdmost-*.arm64_sonoma.bottle.tar.gz"
  ],
  "rust": {"lint": ["mdmost"], "test": ["mdmost", "pulldown-latex"],
           "tested_elsewhere": ["syntect"]},
  "gitea_packages": {
    "url": "https://gitea.oetiker.ch",
    "owner": "oposs",
    "debian": {"distribution": "stable", "component": "main"},
    "rpm": {"group": ""}
  }
}
```

Before committing, run `check` (Step 3) once without this file to compare `version_files` with what detection proposes for Rust, and keep detection's pattern if it differs.

- [ ] **Step 2: Write `.github/workflows/ci-local.yml`**

The three jobs `ci.yml` has today that no block covers, moved verbatim with their comments (the `One syntect only` step, the syntect fixture fetch plus `cargo test -p syntect`, the Windows compile), under `on: [workflow_call]`, each with `timeout-minutes` and no job-level `if:`:

```yaml
name: CI (mdmost's own jobs)

# Called by ci.yml's ci-local job (repo-infra D25); never triggered on its own.
on: [workflow_call]

permissions:
  contents: read

env:
  CARGO_TERM_COLOR: always

jobs:
  one-syntect:
    name: One syntect only
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v7
      - uses: dtolnay/rust-toolchain@stable
      # (the comment from ci.yml's "One syntect only" step)
      - run: cargo tree -p syntect --quiet

  syntect:
    name: Vendored syntect tests
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v7
      - uses: dtolnay/rust-toolchain@stable
      # (ci.yml's "Fetch syntect's test fixtures" step and its comment, verbatim)
      # (ci.yml's "Run the vendored syntect's tests" step and its comment, verbatim)

  windows:
    name: Windows compile
    runs-on: windows-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v7
      - uses: dtolnay/rust-toolchain@stable
      # (the comment from ci.yml's windows job)
      - run: cargo check --all-targets -p mdmost
```

Replace each `# (...)` line with the named text from `.github/workflows/ci.yml` at `origin/main`.

- [ ] **Step 3: Run `check`, then `apply`**

```bash
cd /scratch/oetiker/claude-worktrees/mdmost-repo-infra
PYTHONPATH=$RI/skills/repo-infra/scripts python3 -m repo_infra check --root . --repo oetiker/mdmost
PYTHONPATH=$RI/skills/repo-infra/scripts python3 -m repo_infra apply --root . --repo oetiker/mdmost
```

`ci`, `release-publish` and friends read `conflict` before the conversion (unmanaged files). Resolve each by deleting the old file (`git rm .github/workflows/ci.yml`, ask first) so it becomes `missing`, then `apply` installs it. Do not let `apply` touch the ruleset or repository settings in this task: if it reaches an administration item, stop and ask the owner. Expected afterwards: `check` reports every file item `ok`, and no `conflict` for `ci-local`, `release-build` (after Task 16) or `release-files`.

- [ ] **Step 4: The settled migrations**

In `CHANGES.md` rename `## Unreleased` to `## [Unreleased]` and add under it `### Changed` with: `- Releases are built inside the release pull request. Debian and Ubuntu can install mdmost with apt and Fedora, RHEL, Rocky and Alma with dnf, from the oposs package registry.` In the `Makefile` replace the `man` rule with `include build/man.mk` (keep whatever variables `build/man.mk` documents as required); `git rm docs/man-deflist.lua`. In `Formula/mdmost.rb` change the two comments naming `.github/workflows/release.yml` to name `.github/workflows/release-build.yml`, which writes the formula in the release pull request.

Run: `make man && man --warnings -l man/mdmost.1 >/dev/null` (no warnings other than pandoc's `cannot select font 'C'`/`'CB'`), and `CARGO_TARGET_DIR=/scratch/oetiker/cargo-target-mdmost-repo-infra cargo test -j 4 -p mdmost`.

- [ ] **Step 5: Commit** (one commit per logical piece; `apply` already committed its items)

```bash
git add .github/repo-infra.json .github/workflows/ci-local.yml CHANGES.md Makefile Formula/mdmost.rb
git commit -m "Adopt repo-infra: rust key, ci-local, release_build, Gitea packages"
```

### Task 16: mdmost's `release-build.yml`

**Files (mdmost):**
- Create: `.github/workflows/release-build.yml`
- Delete: `.github/workflows/release.yml` (in the same commit, once this file covers it)

The jobs are `release.yml`'s `build-binaries`, `bottles` and `publish-bottles`, re-cut for the D26 contract. Carry every comment of those jobs over that still describes the new file; drop the ones about pushing to `main`.

- [ ] **Step 1: Write the file**

```yaml
name: Release build

# Called by the release pull request's `build` job (repo-infra D26). Builds
# every file the release ships, uploads each as a `release-asset-*` artifact,
# and uploads the rewritten Formula/mdmost.rb as the artifact `release-files`.
# Read-only: nothing here writes the repository.
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

env:
  CARGO_TERM_COLOR: always

jobs:
  binaries:
    name: Build ${{ matrix.target }}
    runs-on: ${{ matrix.os }}
    timeout-minutes: 60
    strategy:
      matrix:
        include:
          # (the matrix of release.yml's build-binaries, unchanged)
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ inputs.ref }}
      # (release.yml's build-binaries steps from "Install Rust toolchain" to
      #  "Build deb and rpm", unchanged except that every
      #  `${{ needs.version.outputs.version }}` becomes `${{ inputs.version }}`)
      - uses: actions/upload-artifact@v7
        with:
          name: release-asset-${{ matrix.target }}
          path: dist/*

  bottles:
    name: Bottle on ${{ matrix.os }}
    needs: binaries
    runs-on: ${{ matrix.os }}
    timeout-minutes: 40
    continue-on-error: ${{ matrix.optional || false }}
    strategy:
      fail-fast: false
      matrix:
        include:
          # (release.yml's bottles matrix and its comments, unchanged)
    env:
      HOMEBREW_NO_AUTO_UPDATE: 1
      HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK: 1
      VERSION: ${{ inputs.version }}
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ inputs.ref }}
      - uses: actions/download-artifact@v8
        with:
          pattern: release-asset-*-apple-darwin
          path: dist
          merge-multiple: true
      - uses: Homebrew/actions/setup-homebrew@main
      # The release does not exist yet, so the formula's GitHub url would 404.
      # A local tap points it at the tarball this run built (proved by the
      # Task 0 spike); `brew bottle` still records the GitHub root url.
      - name: Local tap with the built tarballs
        run: |
          set -euo pipefail
          arm="$PWD/dist/mdmost-${VERSION}-aarch64-apple-darwin.tar.gz"
          x86="$PWD/dist/mdmost-${VERSION}-x86_64-apple-darwin.tar.gz"
          brew tap-new --no-git local/mdmost
          TAP="$(brew --repository)/Library/Taps/local/homebrew-mdmost"
          sed -e "s|^  version \".*\"|  version \"${VERSION}\"|" \
              -e "s|url \"https://github.com/oetiker/mdmost/releases/download/v#{version}/mdmost-#{version}-aarch64-apple-darwin.tar.gz\"|url \"file://${arm}\"|" \
              -e "s|url \"https://github.com/oetiker/mdmost/releases/download/v#{version}/mdmost-#{version}-x86_64-apple-darwin.tar.gz\"|url \"file://${x86}\"|" \
              -e "s|sha256 \"[0-9a-f]*\" # mac-arm|sha256 \"$(shasum -a 256 "$arm" | cut -d' ' -f1)\" # mac-arm|" \
              -e "s|sha256 \"[0-9a-f]*\" # mac-x86|sha256 \"$(shasum -a 256 "$x86" | cut -d' ' -f1)\" # mac-x86|" \
              Formula/mdmost.rb \
            | awk '/# BOTTLE-START/{print; skip=1; next} /# BOTTLE-END/{skip=0} !skip' \
            > "$TAP/Formula/mdmost.rb"
          brew trust --formula local/mdmost/mdmost || true
      - name: Build the bottle
        run: |
          set -euo pipefail
          brew install --build-bottle local/mdmost/mdmost
          brew bottle --json --no-rebuild \
            --root-url="https://github.com/oetiker/mdmost/releases/download/v${VERSION}" \
            local/mdmost/mdmost
          # (release.yml's rename comment) brew bottle writes name--version,
          # the URL Homebrew fetches has one dash; the json carries both names.
          mkdir -p bottle
          for json in ./*.bottle.json; do
            jq -r '.[].bottle.tags[] | "\(.local_filename)\t\(.filename)"' "$json" \
            | while IFS=$'\t' read -r local_name upload_name; do
                mv "$local_name" "bottle/$upload_name"
              done
          done
          cp ./*.bottle.json bottle/
          ls -la bottle
      - uses: actions/upload-artifact@v7
        with:
          name: release-asset-bottle-${{ matrix.os }}
          path: bottle/*.bottle.tar.gz
      - uses: actions/upload-artifact@v7
        with:
          name: bottle-json-${{ matrix.os }}
          path: bottle/*.bottle.json

  formula:
    name: Rewrite the formula
    needs: [binaries, bottles]
    # One architecture's bottle is worth publishing alone (the optional leg).
    if: ${{ !cancelled() && needs.binaries.result == 'success' }}
    runs-on: ubuntu-latest
    timeout-minutes: 10
    env:
      VERSION: ${{ inputs.version }}
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ inputs.ref }}
      - uses: actions/download-artifact@v8
        with:
          pattern: release-asset-*
          path: artifacts
          merge-multiple: true
      - uses: actions/download-artifact@v8
        with:
          pattern: bottle-json-*
          path: bottles
          merge-multiple: true
      - name: Version, sha256 lines and the bottle block
        run: |
          set -euo pipefail
          # (release.yml's "Rewrite the formula" sed, with VERSION from env)
          # (release.yml's "Rewrite the bottle block" script, with
          #  `${{ needs.version.outputs.tag }}` replaced by `v${VERSION}`)
          # The same check release.yml's last step made: zero bottles fails.
          shopt -s nullglob
          jsons=(bottles/*.bottle.json)
          [ ${#jsons[@]} -gt 0 ] || { echo "::error::no bottles were built"; exit 1; }
          # The rename must have produced exactly the names the json records.
          for json in "${jsons[@]}"; do
            jq -r '.[].bottle.tags[].filename' "$json" | while read -r name; do
              [ -f "artifacts/$name" ] || { echo "::error::bottle $name was not built under that name"; exit 1; }
            done
          done
          mkdir -p release-files/Formula
          cp Formula/mdmost.rb release-files/Formula/mdmost.rb
          cat release-files/Formula/mdmost.rb
      - uses: actions/upload-artifact@v7
        with:
          name: release-files
          path: release-files/
```

Replace each `# (...)` placeholder comment with the named text from `release.yml` at `origin/main` before committing; the file must not keep any of them.

- [ ] **Step 2: Remove `release.yml` and commit**

```bash
git rm .github/workflows/release.yml
git add .github/workflows/release-build.yml
git commit -m "release-build.yml: build every release file inside the release pull request"
```

- [ ] **Step 3: Check again**

`PYTHONPATH=$RI/skills/repo-infra/scripts python3 -m repo_infra check --root . --repo oetiker/mdmost` reports no `release-build` or `release-files` conflict.

### Task 17: the proofs

Push `repo-infra/apply` (ask first) and open a draft pull request in mdmost. Every item of the spec's **Proof** section is one checkbox; record each result (run URL, pass or fail) in the pull request description as it happens. A failed proof stops the plan: fix repo-infra on `spec/d24-d27` (re-run its gates), re-install into mdmost with `apply`, and prove again.

- [ ] D24, D25: `ci-passed` green on the pull request; a commit that breaks a vendored pulldown-latex test turns it red (revert after).
- [ ] D24: a misspelt crate in `rust.test` turns `ci-passed` red; so does removing `syntect` from `tested_elsewhere` (revert both).
- [ ] D26: merge the conversion pull request only after repo-infra's pull request is approved (Task 18), then dispatch **Create release PR**: exactly one **Approve workflows to run** click; the formula change is in the diff; the draft carries every `release_assets` file.
- [ ] D26: **Update branch** on that release pull request turns `changelog-updated` red with the re-dispatch message (then close it and dispatch again).
- [ ] D26: dispatching while the release pull request is open is refused, and its draft survives.
- [ ] D26: a pull request merged into `main` while the release pull request is open does not stop the release.
- [ ] D26: after the merge, publish tags the recorded head, `release-build.json` is gone from the public release, and `brew install oetiker/mdmost/mdmost` pours the bottle.
- [ ] D26: a publish run that fails after the tag, and one that fails before `finalize`, both finish on **Re-run failed jobs**; an ordinary pull request merged afterwards leaves publish green with a notice. (Force the failures with a temporary wrong `GITEA_PACKAGE_USER`.)
- [ ] D26: dispatching while a merged release is unpublished is refused and `CHANGES.md` is unchanged.
- [ ] D26: a build that drops a declared `release_assets` file is refused by `finish` (temporary change on a branch).
- [ ] D26: in a scratch repository at `release-pr` v3 with the `cargo update` edit, turning `release_build` on shows `outdated (variant switch)` and `apply` keeps the edit.
- [ ] D27: the release is in the registry; podman containers `debian:12`, `ubuntu:24.04`, `fedora:41` and `rockylinux:9` install mdmost anonymously with the "What users type" lines, `gpgcheck=1` active on dnf; a re-run of the Gitea job reports the `.deb` 409 as SHA-256 match and the `.rpm` 409 as name, version and architecture match, and stays green.
- [ ] D27: the proxy checks of Task 14 Step 3 pass; a hand-uploaded test package with a `~` version installs through apt.

## Phase 6: merge order

### Task 18: upstream first

- [ ] **Step 1:** Rebase `spec/d24-d27` onto `origin/main`, run `make check`, push, open the repo-infra pull request (body: the four decisions, the proof results from mdmost's pull request by link, and the CHANGES entries). Ask before pushing.
- [ ] **Step 2:** After the owner merges it and a repo-infra release carries it, re-run `apply` in mdmost against the released plugin, so mdmost's markers name released versions.
- [ ] **Step 3:** Only then merge mdmost's conversion pull request.
- [ ] **Step 4:** Rewrite both handoffs (`oep-handoff:controller-handoff`), and remove the `spec/d24-d27` one once its branch is merged.
