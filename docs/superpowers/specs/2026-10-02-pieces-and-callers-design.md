# Pieces and callers: repo-infra as a toolbox the AI applies

Date: 2026-10-02
Status: approved; amended the same day with the decisions of the implementation plan (see "Amendment")
Decision: D30 (supersedes the detection gate and the workflow assembler; the release flow of D28 stays, and D25's `ci-local.yml` stays as a file a caller calls)

## Why

repo-infra was meant to teach an AI how these repositories are structured,
built, tested, reviewed and released, and to give it a toolbox to do that with.
What it became is a detector that decides which parts a repository needs and an
assembler that renders them into generated workflow files.

Onboarding Smalti on 2026-10-02 showed where that breaks. `repo_infra check`
answered `detected nothing` and "the standard does not recognise this
repository", and refused to go on, for a repository that needs exactly three
things the estate already knows how to do: run `make check`, build a `.deb` and
an `.rpm` with nfpm, and publish them to the Gitea registry the way mdmost does.
The only way forward the tool offered was to teach detection a new ecosystem
before anything else could happen.

Choosing pieces for a repository is judgement, and judgement is the AI's job.
Replacing a file that has a newer version is mechanical, and mechanical work is
the tool's job. This design splits the two along that line.

## Decisions

- Onboarding a repository is done by the AI, from the skill. No detector
  decides what a repository needs, and nothing refuses a repository because no
  rule matched it.
- Updating a repository that is already in the fold is done by the tool for the
  mechanical part and by the AI for the rest, guided by per-piece upgrade notes.
- Standard files are used 1:1 and never edited when applied, so an update is a
  plain replacement.
- Composition is by local include: `uses: ./.github/workflows/<file>.yml`.
  Assembly stays allowed where it is purely mechanical, but no file in this
  design needs it.
- No remote references. A repository's infrastructure works standalone; nothing
  at run time reaches back to repo-infra.
- mdmost, the only repository on the assembled files today, is migrated by the
  AI by hand. The tool gets no migration code path.

## File kinds in a repository

| Kind | Examples | Owner | On update |
|---|---|---|---|
| Piece | `ri-ci-rust.yml`, `ri-ci-make.yml`, `ri-release-nfpm.yml`, `ri-publish-gitea.yml`, `release-pr.yml`, `changelog.yml`, `lib/*.js` | repo-infra | the tool replaces it |
| Caller | `ci.yml`, `release-build.yml`, `release-publish.yml`, `ci-local.yml` | the repository, written by the AI | the AI adapts it from the upgrade notes |
| Config | `.github/repo-infra.json` | the repository | the AI adapts it from the upgrade notes |

### Pieces

- Every workflow piece is a complete reusable workflow (`on: workflow_call`)
  with typed `inputs` and declared `secrets`. Each input and secret carries a
  `description:`.
- The first comment line is the marker `# repo-infra: <piece> vN`.
- A piece carries no repository-specific text. Byte comparison against the
  published versions therefore tells whether a copy was edited.
- Pieces that are not workflows (`lib/*.js`, `build/*.mk`, `m4/*.m4`) follow
  the same rules with the comment syntax of their language.
- A piece opens with a header comment block giving its purpose, when to choose
  it, and what the repository must supply (make targets, files, secrets,
  variables). The catalogue is generated from this block (see "The skill").

### Callers

- A caller is short and readable. It calls pieces with `with:` and
  `secrets: inherit`, and holds the repository's own jobs or calls
  `ci-local.yml` for them.
- `ci.yml` ends with the `ci-passed` job and `changelog.yml` provides
  `changelog-updated`. These two names stay the required checks.
- `ci-passed` follows one fixed pattern, given word for word in the skill: it
  `needs:` every other job in `ci.yml`, runs `if: always()`, and fails unless
  every needed job succeeded.
- `release-publish.yml` ends with `finalize`, which `needs:` every publish job.

GitHub limits that bound this design, from the GitHub documentation on reusing
workflows: at most ten levels of nested workflows, at most 50 unique reusable
workflows called from one workflow file, a called workflow can only lower the
`GITHUB_TOKEN` permissions it receives, and workflow-level `env` is not passed
to a called workflow. Everything a piece needs therefore arrives as an input or
a secret.

### Config

`.github/repo-infra.json` keeps only what the borrowed release machinery
(`release-pr.yml`, `lib/*.js`) reads and what cannot be seen in a caller:

- `version_files`
- `release_assets`
- `release_files`
- `gitea_packages`
- `moving_major_tag`

The keys `ecosystems`, `ci`, `ci_local`, `publish`, `release_build`,
`release_build_local` and `publish_local` go away. The callers state the same
facts directly.

### What goes away

- `detection.json` as a gate, and the "does not recognise this repository"
  refusal.
- The assembler for `ci.yml`, `release-build.yml` and `release-publish.yml`.
- The generated `needs:` list of `finalize`. Its silent loss is the failure
  `conventions.md` describes today (a release made public while its `.deb`
  was still building); in this design `check` validates it instead.

### What stays

- The release flow of D28 (release branch, build before the pull request,
  draft release, `finalize`).
- The administration items: `default-branch`, `branch-protection` and
  `required-checks`, `no-changelog-label`, `actions-open-pr`.
- Every numbered decision not named above as superseded.
- The merge procedure for an edited piece (`.new`, `.current`, `.path`, `.log`
  under `repo-infra/merge/` in the git dir).

## The skill

The goal: an AI that loads the skill knows at once which pieces exist, what
each is for, what it needs from the repository, and how to call it.

| File | Content |
|---|---|
| `SKILL.md` | What repo-infra is; the three file kinds; the two jobs (onboard, update); one line per settled decision with a link; links to the files below. About 100 lines. |
| `references/catalogue.md` | Generated. One entry per piece: purpose, when to choose it, inputs, secrets, what the repository must supply, assets produced, a caller snippet. |
| `references/onboarding.md` | The onboarding procedure below. |
| `references/examples/` | Real callers and configs from repositories in the fold: mdmost (Rust, musl, man, Gitea) and Smalti (make, nfpm, Gitea, Pages) once each is converted. |
| `references/conventions.md`, `references/release-flow.md` | The numbered decisions and the release flow, with the detection and assembler material removed. |
| `references/teaching-the-standard.md` | When no piece fits: question, prove in the repository, upstream a new piece. The trigger becomes "no piece fits", no longer "detection failed". |

### The catalogue is generated

A generator reads each piece's header block and the `description:` of its
inputs and secrets and writes `references/catalogue.md`. A repo-infra test runs
the generator and fails when the committed catalogue differs, so the catalogue
cannot fall behind the pieces.

### Onboarding procedure

1. Read the repository's real build, test and release setup: the Makefile or
   build file, the existing workflows, how a release happens today.
2. Map each need to a catalogue piece. Show the user the mapping: need to
   piece, or need to "no piece fits".
3. For a need no piece fits, ask the user (teaching stage 1). Never patch the
   repository around the gap.
4. Copy the pieces 1:1. Write the callers and `repo-infra.json`, starting from
   the closest example.
5. Run `check` until it exits 0.
6. Open the pull request with the `no-changelog` label at creation. After it
   merges, apply the administration items, confirming each with the user first.

## The tool

### `check`

Reports. It never gates onboarding.

For every file carrying a marker, it compares the bytes with the published
versions of that piece (the hashes in `generations.json`) and reports one state:

- `current`: the latest version, unedited.
- `outdated`: an older published version, unedited; `apply` can replace it.
- `edited`: the bytes match no published version.
- `unknown`: the marker names a piece repo-infra does not have.

It validates the callers. For every `uses: ./.github/workflows/<piece>.yml` it
reports:

- a missing piece file;
- an input passed that the piece does not declare;
- a required input that is not passed;
- a secret the piece declares as required that the caller neither passes nor
  inherits.

It validates the two fixed patterns:

- `ci-passed` needs every other job in `ci.yml`;
- `finalize` needs every publish job in `release-publish.yml`.

It reports the administration items as today. Exit code: 0 when nothing needs
attention, 1 otherwise.

### `apply`

1. On the local branch `repo-infra/apply`, replace every `outdated` piece, one
   commit per piece: `Install <piece> vN from the repo-infra standard`.
2. Print the upgrade notes of every version step crossed, from the piece's
   `CHANGES.md` in repo-infra.
3. Run the caller validation again and print what it finds, for example a new
   required input that no caller passes yet.
4. Stop. The AI changes callers and config from the notes and the findings and
   runs `check` until it exits 0.

An `edited` piece stops `apply` with the merge files, as today. Administration
items work as today and are confirmed with the user first.

### Upgrade notes

Each piece has `CHANGES.md` beside it in repo-infra. One section per version,
saying what a caller or the config must change for that version. A version
that needs no caller change says so. The `CHANGES.md` is part of the piece and
a version bump without an entry fails a repo-infra test.

## Converting the existing assets

| Today | Becomes |
|---|---|
| `ci/ci-<ecosystem>.yml` blocks (rust, rust-musl, python, go, node-pnpm, node-bun, perl-autotools, perl-mkpl, checkmk-plugin, claude-plugin, github-action, man, lib, repo-infra-selftest) | one piece each: `ri-ci-<name>.yml` |
| `ci/ci-frame.yml`, `ci/ci-aggregator.yml` | the `ci.yml` caller pattern in the skill and the examples |
| `release-build/release-source-tarball.yml` | piece `ri-release-source-tarball.yml` |
| `release-build/release-build-frame.yml`, `release-build-local-job.yml` | the `release-build.yml` caller pattern |
| `publish/publish-crates-io.yml`, `publish-gitea-packages.yml` | pieces `ri-publish-crates-io.yml`, `ri-publish-gitea.yml` |
| `publish/publish-frame.yml` | the `release-publish.yml` caller pattern; its publish job becomes piece `ri-publish-tag.yml` |
| `publish/publish-finalize.yml` | piece `ri-publish-finalize.yml` |
| the `release-pr-current` job of `ci-aggregator.yml` | piece `ri-release-pr-current.yml` |
| `workflows/release-pr.yml`, `changelog.yml`, `dependabot.yml`, `lib/*.js` | pieces unchanged in role |
| `build/*.mk`, `m4/*.m4` | pieces unchanged in role |

The plugin version takes a major step.

## New pieces proven on Smalti

Smalti is the first repository onboarded under this design and the proof
(teaching stage 2) for two new pieces.

### `ri-ci-make`

- Inputs: `ref` (D28), `target` (default `check`), `python` (default: set up
  Python only when `requirements.txt` exists).
- Steps: checkout `ref`, `actions/setup-python` when asked, `make <target>`.
- Contract stated in its header: the target must work on a fresh
  `ubuntu-latest` runner with `make` and, when `requirements.txt` exists,
  Python. Anything more is D16.

### `ri-release-nfpm`

The piece runs nfpm. The repository supplies an nfpm config and a make target
that prepares the files to package.

- Inputs: `ref`, `version`, `config` (path of the nfpm YAML), `prepare` (make
  target run first), `packagers` (JSON object, one key per packager, each value
  a map of variables for that packager).
- The piece pins nfpm by version and SHA256 and checks the download.
- `SOURCE_DATE_EPOCH` is the committer time of `ref` and is exported for
  `prepare` too, so the packaged files and the packages agree on their
  timestamp. `MTIME` is the same instant in RFC 3339 for nfpm's `mtime:`
  field, because nfpm 2.47.0 ignores `SOURCE_DATE_EPOCH`.
- The piece expands `${VAR}` across the whole config itself before nfpm reads
  it, because nfpm's own expansion reaches only top-level scalars and not the
  `src:`/`dst:` paths under `contents:`. An unset variable fails the job.
- Every package is read back: `dpkg-deb` for a `.deb`, `rpm` for an `.rpm`
  (installed by the piece, as `release-source-tarball` installs its
  toolchain). The read-back checks the version and that the file list is not
  empty, and checks the file name against the shapes `ri-publish-gitea`
  accepts, so a name Gitea would refuse fails at build time and not at
  publish time.
- Output: artifact `release-asset-packages`.

Smalti's caller, as intended:

```yaml
packages:
  uses: ./.github/workflows/ri-release-nfpm.yml
  with:
    ref: ${{ inputs.ref }}
    version: ${{ inputs.version }}
    config: packaging/nfpm.yaml
    prepare: ttf
    packagers: >-
      {"deb": {"PKG_NAME": "fonts-smalti", "PKG_ARCH": "all",
               "PKG_FONTDIR": "/usr/share/fonts/truetype/smalti"},
       "rpm": {"PKG_NAME": "smalti-fonts", "PKG_ARCH": "noarch",
               "PKG_FONTDIR": "/usr/share/fonts/smalti"}}
```

Smalti publishes to the Gitea registry through `ri-publish-gitea` with
`gitea_packages.owner` `oposs` on `https://gitea.oetiker.ch`. `oetiker/smalti`
belongs to a person, so it carries its own secret `GITEA_PACKAGE_TOKEN` and
variable `GITEA_PACKAGE_USER`.

## Amendment: decisions taken in the implementation plan

The plan (`docs/superpowers/plans/2026-10-02-pieces-and-callers.md`) settles
these points where this spec was silent or contradicted itself. They are part
of the design.

- The publish job, `finalize` and `release-pr-current` are pieces
  (`ri-publish-tag`, `ri-publish-finalize`, `ri-release-pr-current`). Each holds
  100 to 250 lines of github-script, which a caller could neither keep short
  nor receive on update.
- `ci-passed` stays an inline job in `ci.yml`. A job that calls a reusable
  workflow reports its check as `ci-passed / <job>`, which the ruleset does not
  match. Its text ships as `assets/callers/ci-passed.yml`, and `check` compares
  the caller's job with it structurally, ignoring `needs:`.
- `check` validates permissions. For every call, the calling job's grant must
  cover what the jobs of the called file ask for, recursively. Create release
  PR grants `ci.yml` a fixed set of permissions, so a caller that asks for more
  breaks every release.
- Header grammar: after the marker line, one empty comment line, then the
  fields `Purpose:`, `Choose:`, `Supplies:` (required), `Pieces:`, `Produces:`
  and `Call:` (optional). `Call:` is required for every piece a caller calls,
  which excludes `changelog` and `release-pr`. A field continues on lines
  indented by two more spaces. The first empty comment line or code line ends
  the header. A test validates each `Call:` against its piece.
- The D28 ref contract is checked on the YAML structure, for the inline jobs
  of `ci.yml` (except `ci-passed`) and `release-build.yml` and for every
  project-owned workflow called with `ref`. `seam.py` goes.
- The D29 stamp goes. A piece is identified by its bytes against
  `generations.json`. The merge procedure stays, triggered by `edited`. D11
  ("markers, never content hashes") is superseded for pieces.
- `rust` stays in `.github/repo-infra.json`, because `lib/rust-plan.js` reads
  it.
- `apply --item <piece>` installs a piece that is not there yet, so onboarding
  copies pieces with the same code that upgrades them. Bare `apply` installs
  outdated pieces, missing core pieces and missing dependencies.
  Administration items run only with `--item`, one at a time, each confirmed
  with the user.
- A remote reusable-workflow reference (`owner/repo/.github/workflows/x.yml@ref`)
  is reported as a problem.
- `ri-publish-gitea` reads `gitea_packages` from the config and takes no owner
  or URL input.
- The default of the `python` input of `ri-ci-make` is settled in the Smalti
  plan.
- Carried-over pieces keep their history: `generations.json` lists the old
  hashes of `changelog`, `release-pr` and the other carried-over files under
  the new paths, so a repository on an older version reads `outdated`.
- Obsolete config keys are reported as a problem, so a migrated repository is
  told to remove them.

## Order of work

1. repo-infra: convert the assets to pieces, write the catalogue generator,
   rewrite `check` and `apply`, rewrite the skill, add per-piece `CHANGES.md`.
2. mdmost: migrated by the AI with `onboarding.md`, proving the Rust, musl,
   man and Gitea paths on the new model.
3. Smalti: onboarded with `ri-ci-make` and `ri-release-nfpm` proven in its
   tree and green in CI, then upstreamed to repo-infra; Smalti's conversion
   pull request merges after that release of the plugin.

## Testing

- Catalogue: the generator output equals the committed `catalogue.md`.
- Pieces: every piece has a marker, a header block, a `description:` on every
  input and secret, and a `CHANGES.md` entry for its current version; every
  published version's hash is in `generations.json`.
- `check`: fixtures for `current`, `outdated`, `edited`, `unknown`; caller
  fixtures for each validation finding; `ci-passed` and `finalize` fixtures
  with one job left out.
- `apply`: replaces an outdated piece and prints the notes in between; stops on
  an edited piece with the merge files.
- End to end: mdmost and Smalti green in CI on the new model.

## Out of scope

- Remote references to repo-infra workflows.
- Gitea Actions as a runner for the pieces.
- A tool path for migrating repositories (only mdmost needs it).
- The `.apk` packager in `ri-release-nfpm`; the `packagers` input admits it
  later without a caller change for deb and rpm users.
