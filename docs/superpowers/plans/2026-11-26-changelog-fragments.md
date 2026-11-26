# Changelog fragments (D40) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A repository whose CHANGES.md carries a "Changelog fragments:" note collects entries as files under CHANGES.d/<section>/, the gate enforces the fragment rules, the release pull request rolls and deletes them, and repo-infra itself switches over in the same branch.

**Architecture:** A new pure module `lib/fragments.js` holds the note parser, the fragment rules, rendering and the fragment-mode gate verdict; `changes.js` dispatches on the mode. The workflows only gather inputs (API reads, checkout reads) and call the pure functions. Python `repo_infra/fragments.py` mirrors the note parser and the fragment rules for check/apply; one JSON fixture pins both implementations to the same answers.

**Tech Stack:** Node (CommonJS, node:test) in .github/workflows/lib; actions/github-script@v9; Python 3 + pytest for check/apply and workflow harness tests.

**Spec:** docs/superpowers/specs/2026-11-26-changelog-fragments-design.md

## Global Constraints

- v2 interface frozen (D33): no new input, secret, output or permission on any piece; `changelog.yml` unchanged.
- Classic mode (no note) behaves byte for byte as today; every existing test stays green unchanged.
- Note line regex: `` ^Changelog fragments: `([^`]+?)/?` `` (on a header line, the part above the first `## ` line).
- Directory refused when absolute, containing `..`, `.github` or under it, or `CHANGES.md`.
- Sections: `new` -> `### New`, `changed` -> `### Changed`, `fixed` -> `### Fixed`, rolled in that order.
- Fragment name regex: `^[0-9]{8}-[0-9]{4}-[0-9a-f]{4}-[a-z0-9]+(-[a-z0-9]+)*\.md$`.
- Fragment body: one or more entries; an entry is a line starting with `- ` plus continuation lines starting with two spaces; blank lines between entries allowed and dropped; refused: no entry, a line starting with `#`, any other text.
- Order within a section: file names, JS default sort; entries keep their order inside a file.
- Repository is public: no internal host names, no em dash (tests/test_no_em_dash.py), prose per the writing-style skill.
- CommonJS, never ESM; never name a github-script variable `io`, `core`, `github` or the other injected names.
- Gates: `make check` (lint, pytest, node tests); `make catalogue` after a piece header change. Never more than 4 cores.

## Review Focus

- A CRLF CHANGES.md or fragment: the note, headings and entries must still be found (split on `/\r?\n/`); a test in Task 1.
- A fragment without a trailing newline, or with trailing blank lines: rolls identically to one with exactly one trailing newline; test in Task 1.
- An entry whose continuation line is indented by a tab or 4 spaces (nested list): two-space prefix accepted, a nested `  - ` line stays part of the entry above it; test in Task 1.
- A pull request with more than 100 changed files: the gate must paginate `pulls.listFiles` (github.paginate); harness test in Task 4.
- A note naming a directory with a trailing slash or without: both read as the same directory; test in Task 1.

---

### Task 1: fragments.js: note, rules, rendering

**Files:**
- Create: `.github/workflows/lib/fragments.js`, `.github/workflows/lib/fragments.test.js`
- Create: `tests/fixtures/changelog-fragments/cases.json` (shared with Task 7)

**Interfaces:**
- Produces:
  - `noteDir(text: string): string | null`: directory without trailing slash; null when no note; throws `Error` naming the reason for a refused directory.
  - `SECTIONS: [['new','### New'],['changed','### Changed'],['fixed','### Fixed']]`
  - `classifyPath(dir: string, path: string): {kind: 'outside'|'root'|'fragment'|'refused', section?: string, reason?: string}`: `root` is a file directly in dir (README.md); `refused` covers bad names, subdirectories, other directories.
  - `fragmentProblem(text: string): string | null`: null when valid, else a reason.
  - `entries(text: string): string[]`: each entry as its lines joined with `\n`, blank lines dropped.
  - `renderSection(version: string, date: string, fragments: {section,name,text}[]): string[]`: lines of the released section in the #163 layout (heading, blank, entries, blank), sections without entries left out; throws on an invalid fragment naming its path.
  - `headerEnd(lines: string[]): number`: index of the first `## ` line or lines.length.

- [ ] **Step 1:** Write cases.json: an array of `{"kind": "note"|"name"|"body", "input": str, "ok": bool, "value"?: str}` covering: note with and without trailing slash, no note, note below the first release (null), dir `../x`, `.github/x`, `/abs`; names `20261126-0921-a3f9-time-band.md` (ok), uppercase hex, missing random part, `.txt`, `topic--x`; bodies: one entry, two entries with a blank line, continuation line, nested `  - `, CRLF, no trailing newline, empty, heading, plain prose line, `* ` bullet.
- [ ] **Step 2:** Write fragments.test.js: one test per kind iterating cases.json; plus `renderSection orders by file name across fragments`, `renderSection leaves out empty sections and emits New, Changed, Fixed in order` (assert exact lines), `renderSection throws naming the path of an invalid fragment`.
- [ ] **Step 3:** Run `node --test .github/workflows/lib/fragments.test.js`; expect failures (module missing).
- [ ] **Step 4:** Implement fragments.js.
- [ ] **Step 5:** Run again; expect pass. Commit "fragments.js: the note, the fragment rules and the rolled section (D40)".

### Task 2: roll in fragment mode

**Files:**
- Modify: `.github/workflows/lib/changes.js` (roll), `.github/workflows/lib/changes.test.js`

**Interfaces:**
- Consumes: Task 1 `noteDir`, `renderSection`, `headerEnd`.
- Produces: `roll(text, version, date, fragments = [])` and `mode(text): {kind: 'classic'} | {kind: 'fragments', dir}` exported from changes.js.

- [ ] **Step 1:** Tests: `roll in fragment mode inserts the section after the header and keeps it byte for byte`; `roll in fragment mode throws "no changelog fragments in CHANGES.d - nothing to release" for an empty list`; `roll refuses a file with both the note and [Unreleased]` (message contains "the switch to fragments is not finished"); `roll in classic mode ignores the fragments argument`.
- [ ] **Step 2:** Run node tests; expect the four to fail.
- [ ] **Step 3:** Implement: roll dispatches on `mode(text)`; classic path unchanged.
- [ ] **Step 4:** Run `make test-js`; expect all pass. Commit.

### Task 3: the fragment-mode gate verdict

**Files:**
- Modify: `.github/workflows/lib/fragments.js`, `fragments.test.js`, `changes.js`

**Interfaces:**
- Consumes: Tasks 1-2.
- Produces: `changes.changelogVerdict({ baseText, mergeBaseText, headText, files, fragmentTexts, untaggedTop, remainingFragments })` -> `{ ok, message }`.
  - `files`: `pulls.listFiles` entries `{filename, status, previous_filename?}`.
  - `fragmentTexts`: `{[path]: text}` at head for every added, modified or renamed path under the dir.
  - `untaggedTop`: the topmost released version at the merge base when it has no tag, else null.
  - `remainingFragments`: the number of fragment paths under the merge base's dir that exist at head (used only when switching back).
  - Mode comes from `mergeBaseText` and `headText`; classic mode calls the existing `gateVerdict(baseText, headText)` unchanged.

Rules (from the spec, Gate section), each one test in a `test('changelogVerdict', async (t) => ...)` block with subtests:
- [ ] **Step 1:** Subtests, fragment mode: a valid added fragment passes; an invalid one fails naming the path and reason; a refused path under the dir fails; a header edit fails; an added `## ` section fails; an edit inside a released section passes without a fragment; a deleted fragment fails with "removes <path>, which another pull request added"; a rename between section dirs passes; nothing changed fails with "This pull request adds no changelog fragment. Add one under `CHANGES.d/<section>/`, or label the pull request 'no-changelog'"; abandon: removing the top section passes when untaggedTop equals its version and the added fragments hold at least as many entries, fails when tagged, fails with too few entries; switch: note at head only passes with no [Unreleased] and enough entries, fails with [Unreleased] left, fails with fewer entries; switch back: fails while `remainingFragments > 0`; classic mode returns exactly what `gateVerdict` returns.
- [ ] **Step 2:** Run; expect failures.
- [ ] **Step 3:** Implement `fragmentVerdict` in fragments.js and the `changelogVerdict` dispatcher in changes.js. Entry count of a removed section or [Unreleased] block: top-level lines starting with `- `.
- [ ] **Step 4:** `make test-js` passes. Commit.

### Task 4: ri-changelog wiring

**Files:**
- Modify: `.github/workflows/ri-changelog.yml` (verdict step, header "Supplies:"), `tests/test_changelog_gate.py`

**Interfaces:**
- Consumes: Task 3 `changelogVerdict`, Task 1 `noteDir`.

- [ ] **Step 1:** Extend the harness in test_changelog_gate.py: fake `repos.compareCommitsWithBasehead` returning `merge_base_commit.sha = 'm'`, `pulls.listFiles` through paginate (serve 150 entries in one test), `getContent` for `CHANGES.md@m` and fragment paths at `h`, `git.getRef` for `tags/v<version>` (404 = untagged), and `git.getTree` recursive at h for remainingFragments. Tests: `test_a_fragment_pull_request_passes`, `test_a_fragment_pull_request_that_edits_the_header_fails`, `test_the_gate_reads_every_page_of_changed_files`, `test_a_pull_request_from_before_the_switch_is_judged_classic` (note at b and h-tip, not at m), `test_classic_repositories_make_no_new_api_calls` (neither m nor h has the note: the compare call that finds m is made, but no listFiles, getRef or getTree call).
- [ ] **Step 2:** Run `python3 -m pytest -q tests/test_changelog_gate.py`; expect new tests fail.
- [ ] **Step 3:** Rewrite the end of the script: read CHANGES.md at base tip, merge base and head; if either merge base or head has a note, list files, read fragment texts, check the tag of the top version, count remaining fragments; call `changelogVerdict`. The label path and release path stay as they are.
- [ ] **Step 4:** Full `make test` passes (test_permissions.py proves no new permission). Commit.

### Task 5: commitFiles deletions

**Files:** Modify `.github/workflows/lib/commit.js`, `commit.test.js`

**Interfaces:** Produces `commitFiles(github, { owner, repo, branch, baseSha, message, files, deletions = [] })`.

- [ ] **Step 1:** Test `deletions become tree entries with sha null`: assert `{path, mode: '100644', type: 'blob', sha: null}` in seen.trees[0].tree and no blob created for them.
- [ ] **Step 2:** Fail, implement, pass, commit.

### Task 6: the release pull request

**Files:**
- Modify: `.github/workflows/ri-release-prepare.yml` (prepare and commit steps, header), `ri-release-finish.yml` (body line, changelog-updated check text), `lib/release.js` (`untaggedMessage`, `treeVerdict`, `refusedReleaseFiles`), `lib/publish.js` (no-record message), `skills/repo-infra/scripts/repo_infra/check.py` (`refused_release_files`), their tests (`release.test.js`, `publish.test.js`, `tests/test_release_pr.py`, `tests/test_check.py`)

**Interfaces:**
- Consumes: Tasks 1, 2, 5.
- Produces: `untaggedMessage(version, dir = null)`, `treeVerdict({..., dir = null})`, `refusedReleaseFiles(entries, versionFiles, dir = null)` (reason "is under <dir>/, which the release pull request rolls"), `refused_release_files(entries, version_files, fragment_dir=None)`, a `publish.js` message taking the dir the same way.
- Fragment-mode abandon text: "merge a pull request that removes the `## X.Y.Z` section from CHANGES.md and restores its fragments".

- [ ] **Step 1:** Tests: JS message variants with and without dir; refusals for `CHANGES.d/new/x.md` in JS and Python; a harness test in test_release_pr.py that runs the prepare step on a workspace with a note and two fragments and asserts the rolled CHANGES.md and the deletions passed to commitFiles; a finish test asserting the body line "collects 3 entries from `CHANGES.d/` into `## X.Y.Z - date`" (count = top-level `- ` lines of notesFor).
- [ ] **Step 2:** Fail, implement (prepare reads mode from the checkout, lists fragments with fs, passes them to roll, and hands their paths as deletions; finish and the callers of the messages read the dir with noteDir), pass with `make check`; `make catalogue` if a header changed. Commit.

### Task 7: Python mirror and check items

**Files:**
- Create: `skills/repo-infra/scripts/repo_infra/fragments.py`, `tests/test_fragments.py`
- Modify: `check.py` (new `changelog_items(repo_root)` in `run`; pass the dir to `refused_release_files` in config_items), `tests/test_check.py`

**Interfaces:**
- Produces: `note_dir(text) -> str | None` (raises ValueError on a refused dir), `classify_path(dir, path)`, `fragment_problem(text) -> str | None`, `entries(text) -> list[str]`; `changelog_items(repo_root) -> list[Item]` with category `"changelog"`, name `"changelog-mode"` (state ok, detail "classic" or "fragments in <dir>/") and, in fragment mode, `problem` items: dir missing, [Unreleased] present, each refused path or invalid fragment.

- [ ] **Step 1:** test_fragments.py iterates the same cases.json as Task 1; tests for each changelog_items state on tmp repos.
- [ ] **Step 2:** Fail, implement, `make test` passes. Commit.

### Task 8: apply --item changelog-fragments

**Files:**
- Modify: `fragments.py` (migration), `cli.py` (route the item), `apply.py` if commit helpers are needed, `commands/apply.md`; Create `tests/test_apply_fragments.py`

**Interfaces:**
- Produces: `switch_to_fragments(repo_root, now: datetime, rand: Callable[[], str]) -> list[str]` (written and changed paths); raises `ApplyError` listing every entry it cannot hold. CLI: `apply --item changelog-fragments`, never part of a bare `apply`; ensures the branch and commits with `commit_paths`, message "Switch the changelog to fragments (D40)".
- Writes: the note paragraph (exact text from the spec, section "The note") as the last header paragraph; removes the [Unreleased] block; one fragment per non-empty subsection at `CHANGES.d/<section>/<YYYYMMDD-HHMM>-<rand>-unreleased.md`; `CHANGES.d/README.md` stating where fragments go and the naming rule with the two shell commands.
- Refuses: a subsection other than New/Changed/Fixed, an entry with a heading, text outside a list item; already in fragment mode ("already uses fragments in <dir>/").

- [ ] **Step 1:** Tests on fixture repos: skeleton-only [Unreleased] (no fragment written, README and note written); filled New and Fixed (two fragments, entries in order, roll of the result equals the classic roll of the input); `### Removed` refused naming the entry; second run refused.
- [ ] **Step 2:** Fail, implement, pass. Add to commands/apply.md a "Changelog fragments" section: run only when the user names it; on a refusal rewrite the named entries in CHANGES.md, show the user, run again; then update the repository's CLAUDE.md, AGENTS.md or CONTRIBUTING.md lines that say to update CHANGES.md. Commit.

### Task 9: documentation

**Files:** `skills/writing-style/SKILL.md` (Changelog entries), `skills/repo-infra/references/conventions.md` (new section "Changelog fragments (D40)"), `references/release-flow.md` (abandon texts at lines ~120 and ~203, changelog-updated), `references/catalogue.md` (via make catalogue), `skills/repo-infra/SKILL.md` if it describes the changelog rule.

- [ ] **Step 1:** Write the text per the writing-style skill. tests/test_prose_skills.py and test_no_em_dash.py pass; skill evals untouched. Commit.

### Task 10: repo-infra switches

**Files:** `CHANGES.md`, `CHANGES.d/README.md`, a fragment for this feature

- [ ] **Step 1:** Run `PYTHONPATH=skills/repo-infra/scripts python3 -m repo_infra apply --item changelog-fragments` on the branch (adapt to the CLI entry point the tests use).
- [ ] **Step 2:** Add `CHANGES.d/new/<stamp>-<rand>-changelog-fragments.md` with the user-facing entries (fragments are optional per repository; the note switches; the gate and release behaviour; apply item) ending "(#172)", and `CHANGES.d/changed/…` for the abandon message wording if it is user-visible.
- [ ] **Step 3:** Run the new gate locally against this branch: a node one-off calling `changelogVerdict` with main's CHANGES.md as merge base, the branch's as head and the branch's file list from `git diff --name-status main...HEAD`; expect ok. `make check` green; `check` reports changelog-mode "fragments in CHANGES.d/". Commit.

### Task 11: end to end on the spike repository (needs the owner's go-ahead)

- [ ] **Step 1:** With the owner's approval, point oetiker/repo-infra-spike's callers at this branch, run the apply item there, open two pull requests that each add a fragment, merge both without a rebase, dispatch Create release PR, and read the rolled CHANGES.md and the draft release notes. Record the run ids in the PR body.
