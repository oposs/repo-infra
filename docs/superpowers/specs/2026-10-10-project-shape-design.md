# Project shape: what a repository contains, and the pieces that build it

Date: 2026-10-10
Status: draft for review, revised after the pushback review of the same day
Decision: D32 (adds a project shape on top of D30 and amends D30's rule for `.github/repo-infra.json`; changes nothing in the release flow of D28 and D31)

## Why

The standard says how a repository is built, tested and released. It says
nothing about what a released project should contain. D22 and D23 leave musl
builds and man pages to the caller's choice, and onboarding suggests a man page
only when `docs/manual.md` already exists.

The result is visible across the terminal tools onboarded so far:

- mdmost, edaptor and mtuspy each carry their own copy of the same release
  build (binaries, `.deb`/`.rpm`, Homebrew bottles, formula rewrite). The three
  copies have drifted: only edaptor and mtuspy build illumos, only mtuspy builds
  Windows arm64, and mtuspy's illumos leg asks for `crt-static`, which illumos
  does not have.
- Their READMEs install the apt key under two different names
  (`gitea-oposs.asc`, `oposs.asc`), only some create `/etc/apt/keyrings` first,
  and edaptor omits `brew trust`, which Homebrew 6 needs (#57).
- Only mtuspy shows a CI and a release badge. ansidrama shows CI only; edaptor
  and mdmost show none.

## Decisions

- **A project has a shape.** A base applies to every repository; every other
  rule is attached to a trigger that describes the project, such as "has a
  command line" or "is installed by users". A repository matches as many
  triggers as apply to it. SmokePing, for example, has a command line, a web
  interface, and is a program users install that runs on an interpreter.
- **Triggers name what users receive, not how the code is written.** A library,
  a plugin or a GitHub Action that another tool loads is not "installed by
  users" and owes no packages. A rule that needs a piece applies only where the
  piece exists: `native-targets` applies to Rust programs until a binaries
  piece exists for another language.
- **The LLM judges the shape; the script measures pieces.** The shape is prose
  in the skill. The LLM decides which triggers apply, reads the README, the
  manual, the demo and the release build, and reports. No script detects the
  kind of project, judges a README or interprets the exceptions.
- **Every rule applies unless an exception says why not.** Exceptions live in
  `.github/repo-infra.json`, one reason per rule id.
- **This amends D30's rule for `.github/repo-infra.json`.** D30 kept in that
  file only what the release machinery reads, and removed the old `skip` key,
  which had this purpose. The file now also holds `exceptions`, which only the
  shape review reads. `check` tells a repository that still has `skip` to
  rename it to `exceptions` and to rewrite its keys as rule ids.
- **The shape review belongs to the command `/repo-infra:check`, not to the
  script.** The person running the command gets the script report and the
  shape review. The loops that run the script until it exits 0 (onboarding,
  `apply`) stay mechanical and repeat no review. `/repo-infra:apply` runs the
  shape review only when it onboards a repository.
- **The archive is the contract between the release pieces.** Only the binaries
  piece knows the language. Packaging and Homebrew read the archives it built.
- **The pieces are proven in a consumer before they are upstreamed**
  (`teaching-the-standard.md`, stage 2). What runs green today is cargo-deb and
  a formula rewrite with the owner written into it; nfpm on unpacked archives
  and the parametrised rewrite have not run anywhere yet.

## The shape

The shape lives in a new reference, `skills/repo-infra/references/project-shape.md`.
Each rule has a unique id (also its exception key), a trigger, what it
requires, how the LLM verifies it, and what meets it. A rule whose requirement
differs by project, such as `linux-packages`, keeps one id and states the
variants under "what meets it".

### Base: every project

- `readme-current`: The README describes the project as it is now. The LLM
  compares it with the manual or with the argument definitions in the source,
  with the channels in `release_assets` and `gitea_packages`, and with the
  supported platforms. It reports features that are missing, options that no
  longer exist and channels that are not mentioned.
- `badges`: The top of the README shows the CI badge
  (`https://github.com/<owner>/<repo>/actions/workflows/ci.yml/badge.svg`,
  linked to the workflow) and the version badge
  (`https://img.shields.io/github/v/release/<owner>/<repo>`, linked to the
  latest release). `project-shape.md` carries the snippet. Other badges may
  follow.
- `install-text`: A project that publishes to any channel has one install
  section with the canonical snippet for each channel it publishes to (below).
- `writing-style`: The README, `docs/manual.md`, the rest of `docs/` and the
  unreleased section of `CHANGES.md` follow the `writing-style` skill. The LLM
  loads that skill and reports each violation with its file, the quoted text
  and the rule. For a large documentation site it reads the README and the
  manual in full, samples the rest, and says that it sampled.

### Has a command line

- `man-page`: `docs/manual.md`, built by the `man` pieces and checked by
  `ri-ci-man`. Onboarding asks for it; it does not wait for the file to exist.

### Runs in a terminal (CLI or TUI)

- `demo`: An ansidrama script `demo/<name>.toml`, the rendered
  `docs/demo/<name>.webp` near the top of the README, and a `make demo` target
  that renders it. The WebP is committed and regenerated by hand. The LLM
  reports a demo that shows commands or screens that no longer exist.

### Has a web or graphical interface

- `screenshot`: A current image of the interface near the top of the README.

### Is installed by users

A program, a daemon or data such as a font, delivered on its own. Not a
library, a plugin or an action that another tool loads.

- `native-targets` (Rust programs): Archives for `x86_64-unknown-linux-musl`,
  `aarch64-unknown-linux-musl`, `x86_64-apple-darwin`, `aarch64-apple-darwin`,
  `x86_64-pc-windows-msvc`, `aarch64-pc-windows-msvc` and
  `x86_64-unknown-illumos`, named `<name>-<version>-<target>.tar.gz` (`.zip`
  for Windows). mise's `github:` backend picks an asset by these names, so
  `mise use -g github:<owner>/<name>` works without further setup (tested on
  edaptor 1.8.0). A program in another compiled language has no
  `native-targets` rule until a binaries piece exists for it; the shape review
  says so instead of reporting a gap.
- `source-archive` (programs that run on an interpreter): The source archive
  of the release, for autotools through `ri-release-source-tarball`.
- `linux-packages`: `.deb` and `.rpm`, published to the Gitea registry by
  `ri-publish-gitea`. What meets it:
  - a Rust program: amd64 and arm64 packages built from the musl archives by
    `ri-release-nfpm`;
  - an interpreted program that bundles native modules (SmokePing's
    `thirdparty/` compiles XS modules such as `FCGI` and `Socket6`): packages
    per architecture;
  - an interpreted program or data that depends only on distribution packages:
    `noarch` packages, as Smalti builds them.
- `homebrew`: `Formula/<name>.rb` in the repository, which is its own tap.
  What meets it: for a Rust program, bottles built by `ri-release-homebrew`;
  for an interpreted program, a formula that builds from the source archive.

No piece in this design builds the interpreted variants beyond what
`ri-release-source-tarball` and `ri-release-nfpm` already cover. The SmokePing
onboarding proves the rest first.

## Exceptions

`.github/repo-infra.json` gains one key:

```json
"exceptions": {
  "homebrew": "a service that needs root and a web server; brew is the wrong channel"
}
```

The value maps a rule id to a reason. The script accepts the key and reports a
`problem` when the value is not an object whose values are non-empty strings.
It does not know the rule ids. The shape review reports an exception whose id
matches no rule, and a gap that has no exception.

A piece input that drops a requirement is allowed only together with the
exceptions for every rule it weakens. The shape review checks the pairing:

| Input | Needs exceptions for |
|---|---|
| `skip_targets` of `ri-release-rust-binaries`, any target | `native-targets` |
| `skip_targets` naming `aarch64-apple-darwin` or `x86_64-apple-darwin` | also `homebrew` |
| `skip_targets` naming `x86_64-unknown-linux-musl` or `aarch64-unknown-linux-musl` | also `homebrew` and `linux-packages` |
| `man: false` of `ri-release-rust-binaries` | `man-page` |

## The shape review

`commands/check.md` gains a second step after the script report:

1. Read `references/project-shape.md`.
2. State which triggers apply, each with its evidence ("has a command line:
   `src/main.rs` parses arguments with clap").
3. Give every rule of those triggers one state: `met`, `gap` with what is
   missing, or `excepted` with the recorded reason.
4. List exceptions that match no rule, and piece inputs that lack their
   paired exceptions.

The script's exit code stays the result of the script. `check.md` says that
the shape review is a separate part of the report and does not change the
exit code. `SKILL.md`, `commands/apply.md` and `onboarding.md` say "run the
script until it exits 0" where they say "run `check` until it exits 0" today.

`references/onboarding.md` gains a step: run the shape review once, then agree
with the owner which gaps this run closes and which become exceptions.

## Install snippets

`project-shape.md` holds one canonical snippet per channel. Placeholders:
`<owner>` and `<name>` for the GitHub repository and the formula, `<deb-name>`
and `<rpm-name>` for the package names (Smalti publishes `fonts-smalti` and
`smalti-fonts`), `<gitea-url>` and `<gitea-owner>` from `gitea_packages`.
These settle the differences #57 lists.

- Debian and Ubuntu: create the keyring directory first, and name the key
  after the registry owner:

  ```sh
  sudo install -d -m 0755 /etc/apt/keyrings
  sudo curl -fsSL -o /etc/apt/keyrings/gitea-<gitea-owner>.asc <gitea-url>/api/packages/<gitea-owner>/debian/repository.key
  echo "deb [signed-by=/etc/apt/keyrings/gitea-<gitea-owner>.asc] <gitea-url>/api/packages/<gitea-owner>/debian stable main" | sudo tee /etc/apt/sources.list.d/<gitea-owner>.list
  sudo apt update && sudo apt install <deb-name>
  ```

- Fedora, RHEL, Rocky, Alma: one command for dnf4 and dnf5 alike:

  ```sh
  sudo curl -fsSL -o /etc/yum.repos.d/<gitea-owner>.repo <gitea-url>/api/packages/<gitea-owner>/rpm.repo
  sudo dnf install <rpm-name>
  ```

- Homebrew:

  ```sh
  brew tap <owner>/<name> https://github.com/<owner>/<name>
  brew trust --formula <owner>/<name>/<name>
  brew install <name>
  ```

  with one sentence that `brew trust` exists from Homebrew 6 on.

- mise: `mise use -g github:<owner>/<name>`.
- Direct download: a link to the latest GitHub release.

For the oposs registry this gives `gitea-oposs.asc`, the name in
`release-flow.md`, edaptor and mtuspy; mdmost's `oposs.asc` changes.
`release-flow.md` replaces its "What users type" block with a pointer to these.

## Pieces

Three new pieces, each at v1. The archive layout is the contract:

```
<name>-<version>-<target>.tar.gz
  <name>/<name>
  <name>/man/<every page in man/>
  <name>/README.md
  <name>/LICENSE
  <name>/<extra paths>
```

`man/` holds whatever `make man` produced. `man.mk` takes the section from the
manual's front matter and the page name from `MAN_NAME`, so a daemon ships
`man/<page>.8`. The Windows `.zip` has the same layout without `man/`.

### `ri-release-rust-binaries`

Lifted from the three copies.

- Inputs: `version`, `ref`, `bin`, `extra_paths` (space-separated repository
  paths copied into the archive, for example `examples` or `integrations`),
  `skip_targets` (space-separated; see the pairing table), `man` (default
  true).
- One matrix leg per target of `native-targets`, `fail-fast: false`.
- Linux musl and illumos build with `cross`, pinned by version. Only the musl
  legs set `-C target-feature=+crt-static`.
- `make man` runs on every leg that is not Windows, when `man` is true.
- `cargo build --release --bin <bin> --target <target>`.
- Packs the archive by the contract above and uploads it as
  `release-asset-<target>`.

### `ri-release-nfpm`

The D30 design for this piece stays: `config`, `prepare`, `packagers`, nfpm
pinned by version and SHA256, `${VAR}` expanded across the whole config by the
piece (nfpm expands only top-level scalars), an unset variable failing the
job, every package read back with `dpkg-deb` or `rpm`, and file names checked
against the shapes `ri-publish-gitea` accepts. Output:
`release-asset-packages`.

This design adds two inputs:

- `archives`: space-separated targets. For each, the piece downloads
  `release-asset-<target>` and unpacks it.
- `check`: a make target run after all packages are built and read back, for
  example Smalti's `check-packages`.

`prepare` runs once, before anything is unpacked, when it is set; it may be set
together with `archives`. Without `archives`, nfpm runs once per packager.
With `archives`, it runs once per target and packager.

Each nfpm run gets these variables:

| Variable | Value | Mode |
|---|---|---|
| `VERSION` | the `version` input | both |
| `SOURCE_DATE_EPOCH` | committer time of `ref`, in seconds | both |
| `MTIME` | the same instant in RFC 3339, for nfpm's `mtime:` field (nfpm 2.47.0 ignores `SOURCE_DATE_EPOCH`) | both |
| `PACKAGER` | `deb` or `rpm` | both |
| every key of `packagers.<packager>` | its value | both |
| `TARGET` | the target triple | archives |
| `STAGE` | the unpacked `<name>/` folder of that target | archives |
| `ARCH` | `amd64` for `x86_64-unknown-linux-musl`, `arm64` for `aarch64-unknown-linux-musl`; nfpm translates it for rpm | archives |

A key in `packagers` that names one of the piece's own variables fails the job,
so a config cannot shadow `VERSION` or `ARCH`.

The file names stay `<name>_<version>-1_<arch>.deb` and
`<name>-<version>-1.<arch>.rpm`, so `release_assets` does not change.

What a conversion changes in the consumers:

- mtuspy, edaptor and mdmost move their `Cargo.toml` tables into an
  `nfpm.yaml`. For mtuspy: `extended-description` becomes `description`;
  `section = "net"` becomes `section: net`; `recommends = "libcap2-bin"`
  becomes `overrides.deb.recommends`, with the rpm equivalent `libcap` under
  `overrides.rpm.recommends`; `license-file` becomes a `contents` entry for
  `/usr/share/doc/<name>/copyright` on deb and `/usr/share/doc/<name>/LICENSE`
  on rpm; the scripts `pkg/debian/postinst` and `pkg/rpm/post-install.sh`
  become `overrides.deb.scripts.postinstall` and
  `overrides.rpm.scripts.postinstall`; `auto-req = "no"` has no counterpart,
  because nfpm adds no automatic requirements. The `contents` take their
  sources from `${STAGE}`.
- Smalti renames `PKG_VERSION` to `VERSION` and `PKG_MTIME` to `MTIME` in
  `packaging/nfpm.yaml`, moves its `envsubst` step into the piece's own
  expansion, and keeps `PKG_NAME`, `PKG_ARCH` and `PKG_FONTDIR` in
  `packagers`. Its count of exactly one `.deb` and one `.rpm` moves into its
  `check-packages` target.

### `ri-release-homebrew`

Lifted from the three copies.

- Inputs: `version`, `ref`, `name` (the formula, default the repository name).
  The formula is `Formula/<name>.rb`.
- Needs the archives of `aarch64-apple-darwin`, `x86_64-apple-darwin`,
  `x86_64-unknown-linux-musl` and `aarch64-unknown-linux-musl`.
- Bottles on `macos-14` (required) and `macos-15-intel` (optional,
  `continue-on-error`), with `Homebrew/actions/setup-homebrew@main` and
  `brew trust` guarded for Homebrew 5.
- For the local tap, rewrites each `url` line that directly precedes a
  `# mac-arm` or `# mac-x86` sha256 line to point at the built archive, and
  fails when such a `url` line is missing. The owner and the name come from
  the inputs and `github.repository`, not from the file.
- Renames each bottle from the name `brew bottle` writes to the name its json
  records.
- Rewrites the formula: the `version` line, the four `sha256` lines found by
  their marker comments (`# mac-arm`, `# mac-x86`, `# linux-x86`,
  `# linux-arm`), and the bottle block generated between `# BOTTLE-START` and
  `# BOTTLE-END`. It fails when no bottle was built, when a bottle is missing
  under its recorded name, or when a marker is gone.
- Outputs: the bottles as `release-asset-bottle-<os>`, and the formula as the
  artifact `release-files`. A repository that uses this piece has no other job
  that writes `release-files`.

`project-shape.md` carries a formula template with the `url` shape
(`https://github.com/<owner>/<name>/releases/download/v#{version}/<name>-#{version}-<target>.tar.gz`)
and all markers in place. The template installs `bin/<name>` and every page
under `man/`. The formula belongs to the repository, because it decides what
else is installed (mdmost installs `integrations/`, edaptor `examples/`).

## Proof and conversion

mtuspy is the poster child of the shape. It is proven there, released there,
and becomes the reference example (`references/examples/mtuspy/`) that
onboarding points to. The owner has allowed mtuspy releases for this work.

1. On a branch of mtuspy, its release build is rewritten as three local
   workflows shaped exactly like the pieces, without piece markers, called from
   `release-build.yml`. The `Cargo.toml` package tables move into `nfpm.yaml`.
2. A temporary `proof.yml` on that branch runs on `pull_request` and calls
   `release-build.yml` with version `0.0.0` and the branch head as `ref`. It
   creates no tag, no release and no release branch. Its run must be green, and
   the packages, bottles and rewritten formula it uploads are compared with
   those of mtuspy v0.1.3. This catches failures before a release is spent.
3. The branch drops `proof.yml` and merges, and mtuspy is released through the
   local workflows. The release must publish to every channel: the GitHub
   release, the Gitea apt and rpm registries, the Homebrew tap and mise. Each
   is installed once from its channel and `mtuspy --version` is run.
4. The three files are copied into repo-infra unchanged except for the marker
   and the header block, with tests, and repo-infra is released.
5. mtuspy installs the pieces with `apply --item` in place of its local
   copies, closes every gap the shape review reports (demo, badges, install
   text, writing style), and is released again. That release is the first
   through the pieces, and its files become `references/examples/mtuspy/`.

Then, one repository per run and each with the owner's OK: edaptor, Smalti
(its `packages` job becomes `ri-release-nfpm` with `check: check-packages`),
and mdmost, without a release until the owner says so.

## Testing

Pieces are tested by running them (D19).

- `ri-release-homebrew`: pytest runs the url rewrite, the formula rewrite and
  the bottle-block generation as the piece ships them, on the formula template,
  fake archives and a recorded `brew bottle --json` output. Cases: two
  bottles, the optional one missing, zero bottles, a sha256 marker missing, a
  `url` line missing, a second run that changes nothing.
- `ri-release-nfpm`: pytest runs the nfpm step in a podman container with the
  pinned nfpm, once in archives mode on a fixture archive and once in
  `prepare` mode. The archives case compares file list, control fields and
  postinst with the packages of mtuspy v0.1.3. The `prepare` case builds
  `noarch` packages from a fixture config shaped like Smalti's. A `packagers`
  key that shadows `VERSION` fails.
- `ri-release-rust-binaries`: structure tests (the seven targets, `crt-static`
  only on musl, `skip_targets`, `man`), and the packing step run on a fake
  `target/` tree, checking the archive layout and names, with a man page in
  section 8 among them.
- `project-shape.md`: a test that every rule has an id, a trigger, a
  requirement and a verification line, and that no id appears twice.
  `test_no_em_dash.py` and `test_prose_skills.py` cover its prose.
- The `exceptions` key: `check` accepts an object of strings, reports anything
  else, and tells a repository with `skip` to rename it.

## Order of work

1. The shape without new pieces: `project-shape.md`, the `exceptions` key and
   the `skip` message, the shape review in `check.md` and `onboarding.md`, the
   script wording in `SKILL.md` and `apply.md`, the install snippets and the
   pointer in `release-flow.md`, D32 in `SKILL.md`, the amended rule in
   `conventions.md`. This can be released on its own.
2. The proof in mtuspy and its first release (steps 1 to 3 above).
3. The three pieces in repo-infra, with tests, catalogue, generations and
   `CHANGES.md`, and a release.
4. mtuspy on the pieces with its full shape, released, and recorded as the
   example (step 5 above).
5. The other conversions, in the order above.

## Closes

#53 and #57. #59 (dependabot downgrades) stays a separate issue. #56 stays
open and becomes more pressing: every Rust program gains three workflow files
in its Actions list.

## Out of scope

- Packaging pieces for interpreted projects beyond `ri-release-source-tarball`
  and `ri-release-nfpm`; the SmokePing onboarding proves them first.
- A binaries piece for Go or another compiled language; the contract leaves
  room for it.
- An entry in the mise registry for short names; it needs a pull request to
  another project per tool.
- Rendering the demo in CI.
- Linux bottles; the formula installs the musl archive on Linux.
