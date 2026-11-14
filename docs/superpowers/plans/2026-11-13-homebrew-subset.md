# ri-release-homebrew platform subset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `ri-release-homebrew` bottles and rewrites a formula that carries only some of the four platform markers, as long as the formula and the built archives agree (#150).

**Architecture:** One new function in `lib/homebrew.js` decides which markers a formula carries and checks them against the archives that exist; the bottle leg (`pointAtArchives`) and the formula job (`rewriteFormula`) both call it and then act only on those markers. No workflow input changes.

**Tech Stack:** Node (node:test), pytest for the doc and piece structure tests.

**Spec:** `docs/superpowers/specs/2026-11-13-homebrew-subset-design.md`

## Global Constraints

- v2 interface frozen: no new input, no changed output of `ri-release-homebrew`.
- `# mac-arm` is required in every formula.
- For each of `mac-arm`, `mac-x86`, `linux-x86`, `linux-arm`: marker present exactly when `<bin>-<version>-<target>.tar.gz` exists. Bottle leg compares the two mac markers against `dist/`; formula job compares all four against `artifacts/`.
- Existing messages stay: `<path> was not built`, `the marker # <m> is gone from <formula>`, `the marker # <m> stands on <n> lines of <formula>`.
- Prose: no em dash, house style (`repo-infra:writing-style`).

## Review Focus

- An arm-only formula next to archives the formula never names, such as `tool-1.2.3-x86_64-unknown-linux-gnu.tar.gz` or distro packages in `artifacts/`: must pass (Task 1 test `other archives beside an arm-only formula are ignored`).
- A four-marker formula (mtuspy, mdmost): unchanged output (existing tests stay green unmodified).
- A marker that appears twice: still fails with the "stands on" message (existing behaviour, kept by Task 1).
- A formula that lost `# mac-x86` while the Intel archive was built: fails in the bottle leg already, before any bottle build (Task 1 test).
- A formula without any url/sha256 for Linux and a Linux user running `brew install`: Homebrew's own error; out of scope, documented in Task 2.

---

### Task 1: The formula and the archives agree

**Files:**
- Modify: `.github/workflows/lib/homebrew.js` (`localFormula`, `releaseFormula`, `pointAtArchives`, `rewriteFormula`, header comment, exports)
- Test: `.github/workflows/lib/homebrew.test.js`

**Interfaces:**
- Produces: `platforms(text: string, { formula: string, archive: (marker) => string, exists: (path) => boolean, markers: string[] }) -> string[]`, exported. Returns the markers of `markers` found in `text`, in `markers` order. Throws, joining all problems with `; `:
  - `# mac-arm` absent: `the marker # mac-arm is gone from ${formula}`
  - a marker on more than one line: `the marker # ${m} stands on ${n} lines of ${formula}`
  - marker present, archive missing: `${archive(m)} was not built`
  - marker absent, archive present: `the marker # ${m} is gone from ${formula}, but ${archive(m)} was built`
- `localFormula` and `releaseFormula` act on the keys of the `archives` / `shas` object they are given, not on a fixed list.

- [ ] **Step 1: Write the failing tests** in `homebrew.test.js`. Add a helper `without(text, ...markers)` that removes, for each marker, its `url` line and `sha256` line, then removes `on_intel do`/`on_arm do`/`on_linux do` blocks left empty. Add `const ARM_ONLY = without(FORMULA, 'mac-x86', 'linux-x86', 'linux-arm');` and assert in the first test that it contains `on_macos do` and `# mac-arm` and none of `on_linux`, `on_intel`, `# mac-x86`.
  - `an arm-only formula bottles from the arm archive alone`: `pointAtArchives` with `dist/` holding only `aarch64-apple-darwin`; the local formula contains `url "file:///w/dist/tool-1.2.3-aarch64-apple-darwin.tar.gz"` and the archive digest, and no `# mac-x86`.
  - `an arm-only formula is rewritten from the arm archive alone`: `rewriteFormula` with `artifacts/` holding only the arm archive and `jsons: [ARM]`; text has `version "1.2.3"`, the arm digest on the `# mac-arm` line, one `sha256 cellar:` line for `arm64_sonoma`, no `# linux-`.
  - `other archives beside an arm-only formula are ignored`: as above plus `artifacts/tool-1.2.3-x86_64-unknown-linux-gnu.tar.gz` and `artifacts/tool_1.2.3~trixie-1_amd64.deb`; succeeds.
  - `a built archive whose marker is gone fails`: for the bottle leg, `without(FORMULA, 'mac-x86')` with both mac archives in `dist/` refuses `/^the marker # mac-x86 is gone from Formula\/tool\.rb, but \/w\/dist\/tool-1\.2\.3-x86_64-apple-darwin\.tar\.gz was built$/`; for the formula job, `without(FORMULA, 'linux-arm')` with all four archives refuses `/^the marker # linux-arm is gone from Formula\/tool\.rb, but artifacts\/tool-1\.2\.3-aarch64-unknown-linux-musl\.tar\.gz was built$/`.
  - `a formula without # mac-arm fails`: `without(FORMULA, 'mac-arm')`, in both steps, refuses `/^the marker # mac-arm is gone from Formula\/tool\.rb$/` (bottle leg with only the Intel archive in `dist/`; formula job with the three other archives).
  - Leave every existing test unchanged; they pin the four-marker behaviour.

- [ ] **Step 2: Run them, expect the new ones to fail**

Run: `node --test .github/workflows/lib/homebrew.test.js`
Expected: the arm-only tests fail with `was not built` for the missing archives; the "is gone ... but" tests fail on message mismatch.

- [ ] **Step 3: Implement `platforms` and use it** in `homebrew.js`. `pointAtArchives` calls it with `markers: ['mac-arm', 'mac-x86']` and `archive` giving `${io.cwd()}/dist/...`; `rewriteFormula` with all four and `artifacts/...`. Both then read sha256 only for the returned markers. `localFormula` loops over `Object.keys(archives)`; `releaseFormula` over `Object.keys(shas)`. Update the header comment and the comment over `pointAtArchives` (`dist/ holds the two mac archives`) to say the formula carries `# mac-arm` and any of the other three, each with its archive.

- [ ] **Step 4: Run the gates**

Run: `make test-js` then `uv run pytest tests/test_release_homebrew.py -q`
Expected: all pass, test count up by the new tests.

- [ ] **Step 5: Commit** `homebrew.js` and `homebrew.test.js`.

### Task 2: Docs, piece comments and changelog

**Files:**
- Modify: `skills/repo-infra/references/project-shape.md` (exceptions table lines 251-255, `## Formula template` intro)
- Modify: `.github/workflows/ri-release-homebrew.yml` (comments only: "The version, the four archive checksums", the Intel-bottle comment if it says Intel Macs always get an archive)
- Modify: `CHANGES.md` (`### New` under `[Unreleased]`)
- Test: `tests/test_project_shape.py` (only if a pinned sentence changes)

- [ ] **Step 1: project-shape.md.** Exceptions table: the `x86_64-apple-darwin` row and the musl row no longer list `homebrew`; a new row `aarch64-apple-darwin` lists `also homebrew`. Replace the sentence at line 254 with: `ri-release-homebrew` needs the `aarch64-apple-darwin` archive and an archive for each other platform its formula names; `ri-release-nfpm` builds from the musl archives. Formula template intro: the template carries all four platforms; a formula may leave out the `on_intel` block of `on_macos` and the whole `on_linux` block, or either of its blocks, together with their archives; `# mac-arm` stays; a platform left out has no formula, and `brew install` on it fails with Homebrew's own message. Keep the template itself unchanged (it is pinned by `test_the_library_tests_use_the_template_of_the_shape_reference`).

- [ ] **Step 2: Piece comments.** "four archive checksums" becomes "the checksum of each archive the formula names". No YAML change.

- [ ] **Step 3: CHANGES.md** `### New`, at most three sentences, observable effect first, for example: "`ri-release-homebrew` releases a formula that names only some platforms, such as `on_macos` with `on_arm` alone: it needs the archive of each platform the formula names and no others. `# mac-arm` stays required, and an archive that was built for a platform the formula leaves out still fails the release. (#150)"

- [ ] **Step 4: Gates**

Run: `make test`, `make test-js`, `make lint`
Expected: all green.

- [ ] **Step 5: Commit**, push, open the PR. The PR body names #150 without "closes" (lectover must prove it first). PR CI runs no macOS bottle leg: the mtuspy gate (`gh workflow run gate-mtuspy.yml --ref <branch>`) proves the four-marker path still bottles.
