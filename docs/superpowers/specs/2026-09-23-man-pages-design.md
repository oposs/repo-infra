# repo-infra: man pages, and the house writing style

Date: 2026-09-23
Extends: `2026-08-17-repo-infra-design.md` (replaces its "Spec 3: prose" outline),
D22's opt-in CI seam (`2026-09-14-static-musl-ci-design.md`)
Proved in: `oetiker/mdmost` (`docs/manual.md`, `docs/man-deflist.lua`, the `man`
target in its `Makefile`, the `docs` job in `.github/workflows/ci.yml`, and the two
style commits `fef7f53` ("the manual reads like a man page, not an essay") and
`8cdcddc` ("the install section is three commands, not an essay"))
First consumer: `oposs/smtp-proxy-rs`

This document adds one decision, D23, one CI block, two build assets, two skills,
and one widening of the D22 seam: an opt-in block that belongs to no ecosystem.

## The gap

Spec 3 was written as an outline before mdmost built its manual, and mdmost then
found out what the outline got wrong. Three points differ:

| Point | Spec 3 outline | What mdmost settled |
|---|---|---|
| Em dashes in prose | "leaves the em dashes alone" | removed from manual and README prose |
| Rationale | "every explanation names the concrete thing that went wrong" | none in the manual; it moves to `docs/maintainer-notes.md` |
| Person and tense | not stated | manual: present tense, third person, no "you" or "we" |

The outline's rule about concrete detail is correct for code comments and commit
messages, where the reader is a developer asking "why". It is wrong for a manual,
where the reader asks "what does it do" and the essay voice buries the answer. The
mdmost owner rejected the essay voice on 2026-08-17 and accepted `man-pages(7)` and
`groff_man_style(7)` as the authorities.

The build half of the outline stands as written and is now proved: `docs/manual.md`
is the one source, pandoc converts it, `man/` is gitignored, CI proves it converts.

## D23: a man page is a build artifact, checked on every pull request by an opt-in block that no ecosystem owns

### The `ci-man` block

`skills/repo-infra/assets/ci/ci-man.yml`, one job, `man`:

1. `actions/checkout`
2. `sudo apt-get update && sudo apt-get install -y pandoc groff man-db`
3. `make man`
4. Render every `man/*.[1-9]*` (amended 2026-09-28, `ci-man` v2; was `man/*.1`) with `man --warnings -l` and fail on any warning other than
   pandoc's own `cannot select font 'C'` and `cannot select font 'CB'`. mdmost met
   both on every build and they are not defects. The warning that is one, and that
   mdmost hit twice, is `table wider than line length minus indentation`: a Markdown
   table with a prose column that roff cannot fit.

Nothing consumes the page in CI. The job exists so a manual that stops converting,
or converts into a page roff cannot lay out, fails the pull request that broke it.

Manifest entry:

```json
"ci-man": {"version": 1, "jobs": ["man"], "optional": true,
           "build": ["man", "man-lua"]}
```

### Opt-in, like D22

A repository chooses it: `"ci": ["ci-man"]` in `.github/repo-infra.json`. It is not
detected, for the reason D22 gives: `docs/manual.md` existing does not say the owner
wants a required check on it. Once chosen it joins `ci-passed` through the generic
`ci_addon_blocks` path, with no new code there.

The `man-pages` entry under `detection.json` `candidates` stays. The report drops it
from the candidate list once `ci-man` is chosen, so the hint disappears when it has
been acted on.

### Widening the seam: no `requires`

D22 made `requires` mandatory for an optional block, and
`test_an_optional_block_declares_the_ecosystem_it_needs` enforces it. A man page has
no ecosystem: mdmost is Rust, but a Perl or Go tool ships one the same way.

The rule becomes: **an optional block may omit `requires`, and then fits any
ecosystem.** `ci_addon_blocks` skips the ecosystem check when the key is absent. The
test is renamed to `test_an_optional_block_names_its_ecosystem_or_none`, and asserts
that `requires`, when present, is a known ecosystem id. Its refusals (unknown block,
not optional, already detected, named twice) are unchanged.

### One choice, not two: a block carries its build assets

`ci-man` runs `make man`, so it is useless without the Makefile fragment that defines
that target. D18's container pattern would make the repository name the fragment
separately in `build`. That is a second knob whose only valid setting follows from
the first, and a repository that sets one and forgets the other gets a red CI with no
explanation.

So a `ci_blocks` entry may declare `"build": [...]`, and choosing the block installs
those build assets as if they had been listed in `build`. Naming one of them in
`build` as well is allowed and is not a duplicate. `container` keeps its explicit form;
converting it is out of scope.

### The build assets

- `build/man.mk` (`build_assets` id `man`, comment `#`). It defines one phony target,
  `man`, which builds `man/$(MAN_NAME).<section>` from `docs/manual.md` with
  `pandoc --standalone --from markdown-smart --to man --lua-filter build/man-deflist.lua`.
  Amended 2026-09-24 (`man` v2): without `-smart`, pandoc turns `--` in running
  text into an en dash, so **--api** reached the page as `–api`.
  Amended 2026-09-28 (`man` v3): the section comes from `section:` in the manual's
  front matter, which pandoc already reads for `.TH`, so a daemon's page is
  `man/<name>.8`. A `MAN_SECTION` variable was rejected: it could disagree with the
  front matter. A manual with no usable `section:` stops `make man` and no other
  target. The repository
  sets `MAN_NAME` before `include build/man.mk`; the fragment refuses with a clear
  `$(error ...)` when it is unset.
- `build/man-deflist.lua` (`build_assets` id `man-lua`, comment `--`). Ported from
  mdmost's filter with a different input: it turns bullet lists in which every item
  opens with an inline code span followed directly by a colon
  (`` `--listen <ip:port>`: Address and port to listen on.``) into definition lists
  whose term is the code span in bold, so GitHub renders the source as lists and the
  man writer emits `.TP`. mdmost keyed on a bold term and an em dash. Owner ruling,
  2026-09-23: no em dash anywhere, which supersedes "unchanged in behaviour".

Both carry the usual `repo-infra: <asset> v1` marker. The date in the page header
comes from `date:` in the manual's front matter, never from the build, so two builds
of one source produce one page. The footer carries no version, so a release does not
change the page.

`test_every_non_yaml_asset_is_covered_by_a_test` gains `.lua`, and both assets get a
test: the filter turns a ``- `term`: text`` list into a definition list and leaves
mdmost's bold-term form and a list that matches only in part as bullet lists (run
through pandoc when it is on the PATH, skipped with a reason when it is not), and
`man.mk` builds a two-section fixture manual into `man/fixture.1`. Owner ruling,
2026-09-23: with `CI` set, a missing pandoc fails these tests instead of skipping
them, and repo-infra's own CI installs pandoc so they run there.

## The two skills

Spec 1 already placed these outside the `repo-infra` skill, because they trigger on
their own ("help me write this README") with no repository audit involved. A later
`docs-site` skill joins them the same way, pointing to `writing-style` for its voice.

### `writing-style`: the voice of all prose

Applies to READMEs, manuals, maintainer notes, changelog entries, code comments and
commit messages. It states the rules per kind of text, because the kinds differ:

- **Manual** (`docs/manual.md`): present tense, third person, no "you" or "we". Facts
  only: what it does, what it accepts, what it prints. No rationale, no self-praise
  ("so the two cannot drift apart"), no justification clauses ("which is what makes
  it usable for"). Noun-phrase headings ("Layout rules", not "Rules worth knowing").
- **README**: its own voice, second person allowed. No self-congratulation. An install
  section is the commands, not an essay about them.
- **Maintainer notes** (`docs/maintainer-notes.md`): the rationale the manual and the
  README do not carry. Rationale cut from either moves here and is never deleted.
- **Changelog**: the rules in force for CHANGES entries: lead with what the reader
  observed, three sentences at most, names the reader can act on, the issue tag last.
- **Code comments and commit messages**: every explanation names the concrete thing
  that went wrong. This is the one place the outline's rule applies, and it keeps its
  example (the v0.1.1 tag with `Cargo.lock` still at 0.1.0).

Across all of them: no emoji headings; no rhetorical "X, not Y" framing; no lists of
three made for rhythm; no em dashes anywhere, and option and term lists use the
``- `code`: text`` form (owner ruling, 2026-09-23); "for example", not "e.g."; singular "they" for a person of unknown gender;
sentence-case subsection headings.

The skill carries a short before/after pair for the manual taken from `fef7f53`, since
the rules are easier to apply against an example than against a list.

### `man-pages`: structure and build of a man page

- Section order from `man-pages(7)`: NAME, SYNOPSIS, CONFIGURATION, DESCRIPTION,
  OPTIONS, EXIT STATUS, ENVIRONMENT, FILES, VERSIONS, STANDARDS, HISTORY, NOTES,
  CAVEATS, BUGS, EXAMPLES, SEE ALSO. Sections a tool needs that the list lacks (for
  example KEYS, SIGNALS, API) go between OPTIONS and EXIT STATUS.
- Semantic newlines in the source.
- Front matter: `title`, `section`, `header`, `footer` without a version, `date` edited
  by hand on a substantive revision.
- Options as bullet lists of ``- `code`: text`` items (the filter's input); no
  Markdown table with a prose column.
- Level-1 headings are anchors other documents link to; renaming one is a breaking
  change to those links.
- Setup in a repository: `MAN_NAME` plus `include build/man.mk` in the Makefile,
  `man/` in `.gitignore`, `"ci": ["ci-man"]`, and the packaging paths (deb assets,
  tarballs) take the page from the working tree after `make man`.
- Voice: `writing-style`, manual section. The skill does not repeat those rules.

Both skills are built and evaluated with `skill-creator`, each with a small eval set:
a draft manual section with essay voice to be rewritten, a README install section to
be cut down, and a request that must *not* trigger them (a code-comment question
belongs to neither).

## What is not proved here

- **`ci-man` has not run on a GitHub runner.** mdmost's `docs` job is the proof of
  pandoc on `ubuntu-latest`; the warning check in step 4 is new. Its first real run is
  smtp-proxy-rs's first pull request after adoption.
- **The skills' trigger descriptions are tuned only against their evals**, not against
  real sessions.

## Changes elsewhere in this repository

- `docs/superpowers/specs/2026-08-17-repo-infra-design.md`: the "Spec 3: prose"
  section is replaced by a pointer to this document. Its "Hygiene" line moves to a
  short note, since it is not part of D23.
- `references/conventions.md`: the `ci` bullet names `ci-man`, and the `build` bullet
  says a CI block may carry build assets.
- `skills/repo-infra/SKILL.md`, "Reading further": one line pointing to the two skills.
- `CHANGES.md`: one entry under `### New`.
