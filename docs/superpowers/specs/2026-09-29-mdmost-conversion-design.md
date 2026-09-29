# repo-infra: scoped Rust workspaces, local CI jobs, pre-built releases, Gitea packages

Date: 2026-09-29
Extends: `2026-08-17-repo-infra-design.md` (the D-series), D15's assembled `ci.yml`,
D20's fixed-path reusable workflow, D21's publish seam
Proved in: not yet. Each decision is proved in `oetiker/mdmost` before this
document's pull request merges (see "Proof").

This document adds four decisions, D24 to D27. All four came out of converting
`oetiker/mdmost`, the repository several of the standard's assets were first
ported from. `check` on mdmost reports `ci`, `ci-lib` and `ci-rust` as
`conflict`, and reading mdmost's own `ci.yml` and `release.yml` against the
standard shows three places where adopting the standard as it stands breaks
something that works today, plus one thing mdmost wants that the standard
refused in writing.

## The gaps

**Workspace-wide lint on vendored code.** mdmost is a cargo workspace whose
other members, `vendor/pulldown-latex` and `vendor/syntect`, are upstream code
frozen at a release. `ci-rust` runs `cargo clippy --all-targets -- -D warnings`
over the whole workspace, and that fails today on `vendor/syntect`
(`mismatched_lifetime_syntaxes` in `yaml_load.rs`, upstream's own signature).
mdmost runs `cargo clippy --all-targets -p mdmost --no-deps -- -D warnings`
instead: `-p` alone is not enough, because clippy-driver replaces rustc for
every workspace member regardless of `-p`. `cargo fmt --check` over the whole
workspace passes today, so formatting is not the problem, only lint scope.

**Tests the standard would drop.** `ci-rust` runs a bare `cargo test`. The root
manifest carries a `[package]`, so cargo's default member is mdmost alone and
the vendored crates' tests stop running without an error. Those tests are the
regression net for the patches that are the reason the crates are vendored.

**Jobs no block covers.** mdmost runs a Windows `cargo check`, a `cargo tree -p
syntect` guard against a silently ignored `[patch.crates-io]`, and syntect's
suite after fetching four upstream fixture repositories at pinned commits. None
is an ecosystem concern, and the standard has no place for a required job the
repository writes itself.

**A release that pushes to `main`.** mdmost's `release.yml` updates
`Formula/mdmost.rb` and its bottle block by pushing to `main` after the release.
The ruleset (D1, empty `bypass_actors`) forbids that push. The main design
already noted that the formula and bottle commits "must move off `main` to
satisfy D1" and did not say where to.

**apt and dnf.** mdmost ships `.deb` and `.rpm` files as release assets and now
wants them installable from a package repository. The main design refused this
(line 1149): "No apt/yum repository is hosted, that would need a GPG key per
organisation, stored and rotated, and would be the first credential this design
introduces."

## D24: a Rust workspace names the packages it lints and tests

`.github/repo-infra.json` gains an optional `rust` object:

    "rust": {
      "lint": ["mdmost"],
      "test": ["mdmost", "pulldown-latex"]
    }

- `lint`: `rust-check` runs `cargo fmt --check -p <name>` and
  `cargo clippy --all-targets -p <name> --no-deps -- -D warnings` for each
  name. `--no-deps` is required, for the clippy-driver reason above.
- `test`: `rust-test` runs `cargo test -p <name>` as one step per name, so a
  red step names the crate that broke.

Absent, both jobs keep today's workspace-wide commands. Present, the lists are
rendered into the block as literal steps; the assembler does the loop, since
workflow YAML has none. A name that is not a workspace member is refused at
assembly (`cargo metadata` is the authority), so a renamed crate cannot turn
into a step that tests nothing.

The key records which code is the project's own. That is a fact about the
repository, so it lives beside `version_files` rather than among a CI block's
options. Detection cannot answer it: a path under `vendor/` is a convention
that states nothing (D12).

## D25: project-owned CI jobs, required through one fixed seam

D20 already solved "the project brings jobs the standard cannot write" for
action tests: one generated job calls a reusable workflow at a fixed path. D25
reuses that seam for any repository:

    "ci_local": true

renders, into `ci.yml`,

    ci-local:
      uses: ./.github/workflows/ci-local.yml

and adds `ci-local` to `ci-passed`'s generated `needs:` list. The job inherits
the D20 contract unchanged: `ci-local.yml` is the project's own file (not
shipped, not versioned, not drift-checked), triggers on `workflow_call` only,
and sets `timeout-minutes` on each of its own jobs because the calling job
cannot. `check` reports a missing `ci-local.yml` as its own line, as it does for
`action-test.yml`.

The alternative raised first was a `publish_local`-style list of job ids that
the repository writes into `ci.yml` itself. It was dropped: those job blocks
would be local edits to an assembled file, so every upgrade of any CI block
would stop with `NeedsMerge`. A separate file keeps `ci.yml` pure assembler
output and still makes the jobs required.

For mdmost, `ci-local.yml` carries the Windows check, the one-syntect guard,
and the syntect fixture fetch plus `cargo test -p syntect` (which is why
`syntect` is not in D24's `test` list).

## D26: the release pull request builds the release

### What moves

Today the release pull request only rolls `CHANGES.md` and bumps version
files; everything is built after the merge. D26 moves building to before the
merge, for repositories that opt in:

    "release_build": true

1. `Create release PR` prepares the release branch as today (guard, roll,
   bump, commit).
2. It calls `.github/workflows/release-build.yml` (D20 seam again: project-owned,
   `workflow_call`, inputs `version` and `ref`) against the release branch head.
   The project's jobs build whatever it ships and upload each file as an
   Actions artifact named `release-asset-*`. Files that must record the
   artifacts, such as a Homebrew formula with `sha256` lines, are uploaded as
   the artifact `release-files`, a tree of repository paths.
3. The core creates a **draft** release for `vX.Y.Z` (no tag yet), attaches
   every `release-asset-*` file, commits `release-files` onto the release
   branch, and records the build in a `release-build.json` asset: the built
   commit, its tree, and the list of `release-files` paths.
4. It opens the pull request. Reviewers see the formula change in the diff.

After the merge, `release-publish.yml` tags the merge commit, finds the draft
by its tag name, updates its target, and hands it to the add-ons and
`finalize` as today.

### Why

Two reasons, one per side of the merge.

The pushes to `main` disappear. Everything that depended on the artifacts is in
the pull request, so nothing has to be written after the merge.

Publishing stops rebuilding. Converted repositories have had release pull
requests that were green followed by a publish run that failed, and mdmost's
own releases failed after the decision to release while building: v0.1.2's
bottle legs queued on a retired runner image, and v0.3.2's
`setup-homebrew@master` stopped resolving. With D26 a failure while building happens before the merge, where
closing the pull request cancels the release cleanly, and what publishes is the
bytes that were reviewed.

### The tree check

Publishing a pre-built artifact is only honest if the tagged commit is what was
built. The merge commit can differ: `main` may have moved after the build. So
publish compares the merge commit's tree with the built commit's tree and
refuses unless the only differences are the paths in `release-files`, which
were written after the build by construction. Refusing leaves the draft and no
tag; the remedy is to close the pull request and dispatch again.

### Stale drafts

A closed release pull request leaves its draft behind. Drafts are not public.
The next `Create release PR` for the same version deletes an existing draft for
that tag before creating its own.

### Scope

`release_build` is off by default and changes nothing for a repository that
does not set it. The existing publish blocks (`publish-source-tarball`,
`publish-crates-io`) work either way. A repository that sets it must provide
`release-build.yml`; `check` reports it missing as its own line.

## D27: the standard publishes to Gitea package registries

### The block

`publish-gitea-packages` joins `publish_blocks`. Configuration:

    "publish": ["publish-gitea-packages"],
    "gitea_packages": {
      "url": "https://gitea.oetiker.ch",
      "owner": "oposs",
      "debian": {"distribution": "stable", "component": "main"},
      "rpm": {"group": ""}
    }

- It uploads every release asset matching `*.deb` to
  `{url}/api/packages/{owner}/debian/pool/{distribution}/{component}/upload`
  and every `*.rpm` to `{url}/api/packages/{owner}/rpm/upload?sign=true`
  (`rpm/{group}/upload?sign=true` when a group is set).
- It fails when no asset matches. A chosen block that uploads nothing is the
  silent failure `finalize`'s asset assertion exists to catch.
- It fails before the first upload when `GITEA_PACKAGE_TOKEN` or
  `GITEA_PACKAGE_USER` is empty, naming the missing one, instead of reporting a
  bare 401.
- Gitea answers 409 for a version that already exists. A **Re-run failed jobs**
  after a partial upload meets that for the files that went up the first time,
  so 409 counts as success only when the stored file's SHA-256 (from Gitea's
  package API) equals the release asset's. A different file under the same
  version fails.
- It is in `finalize`'s generated `needs:`, like `publish-crates-io` (D21): a
  failed upload leaves the GitHub release a draft. A version public on GitHub
  but absent from apt and dnf is the inconsistency worth preventing.

The layout default is one channel for everything: distribution `stable`,
component `main`, no RPM group. A statically linked package runs on every
release of every distribution in its family, so per-release channels would
carry the same bytes several times. A project that links against system
libraries sets its own distribution names.

### Signing with Gitea's key

Gitea creates one PGP key pair per owner and keeps the private half on the
server. With it, it signs Debian `InRelease` and `Release.gpg`, RPM
`repomd.xml`, and, when uploaded with `?sign=true`, each `.rpm` (Gitea 1.22+,
go-gitea/gitea#27069). The `.repo` file Gitea generates sets `gpgcheck=1`, so
an unsigned `.rpm` would not install. `?sign=true` is therefore required.

No repository holds a signing key. A key of our own would make things worse:
dnf checks package signatures against the `gpgkey` Gitea's `.repo` names, which
is Gitea's key. What is accepted in exchange: Gitea has no key rotation, and
whoever controls the Gitea server controls the key.

### The credential, and why this reverses line 1149

Half of the refusal at line 1149 no longer holds: there is no GPG key to store
or rotate. The other half does. Uploading needs a token, and this is the first
stored credential in the standard.

D21 avoided a token for crates.io through Trusted Publishing, where the
registry accepts the job's GitHub OIDC identity. Gitea's package registry has
no such mechanism. A relay that verifies the OIDC token and uploads with a
server-held token was considered and not chosen: it is a service of our own,
security-critical, to write and run, where the token below is plain GitHub.

So the credential is kept as small as it can be:

- A dedicated Gitea user, member of the owner organisation only, in a team with
  package write permission and nothing else. A token's scope applies to every
  owner its user can reach, so a personal account's token would reach further.
- Token scope `write:package` only.
- Stored once, as the GitHub organisation secret `GITEA_PACKAGE_TOKEN` with the
  organisation variable `GITEA_PACKAGE_USER`. A repository under a personal
  GitHub account (mdmost is under `oetiker`) cannot see organisation secrets and
  carries its own copy as a repository secret and variable.
- Gitea tokens do not expire. Rotation is a manual step, done once for the
  organisation secret and once per personal-account copy.

A separate "publisher" repository that holds the token and uploads on behalf of
others does not reduce this: the releasing repository would need a credential
to trigger it, since `GITHUB_TOKEN` cannot start workflows in another
repository, and the release could no longer stay a draft while it waits.

### Anonymous reads without opening the server

The Gitea instance runs with `REQUIRE_SIGNIN_VIEW = true`, which covers the
whole server; package endpoints, including `repository.key`, answer 401 without
a login. Gitea has no setting that opens the package registry alone. Setting
`REQUIRE_SIGNIN_VIEW` to `false` or `expensive` would make every repository,
organisation and user marked public readable by anyone, including ones that are
marked public only because it never mattered.

The reverse proxy opens the package paths instead. For `GET` and `HEAD`
requests under `/api/packages/{owner}/debian/`, `/api/packages/{owner}/rpm/`
and `/api/packages/{owner}/rpm.repo` that carry no `Authorization` header, it
adds one with the token of a second dedicated user, scope `read:package`, in a
team with package read permission only. Every other path, and every request
that brings its own credentials (the upload's `PUT`), passes through unchanged.
The reader token lives only in the proxy's configuration. The concrete proxy
configuration is operational and is kept outside this public repository.

### What users type

    sudo curl -o /etc/apt/keyrings/gitea-oposs.asc https://gitea.oetiker.ch/api/packages/oposs/debian/repository.key
    echo "deb [signed-by=/etc/apt/keyrings/gitea-oposs.asc] https://gitea.oetiker.ch/api/packages/oposs/debian stable main" | sudo tee /etc/apt/sources.list.d/oposs.list
    sudo dnf config-manager --add-repo https://gitea.oetiker.ch/api/packages/oposs/rpm.repo

## What mdmost chooses

    {
      "ci": ["ci-man", "ci-rust-musl"],
      "ci_local": true,
      "release_build": true,
      "publish": ["publish-gitea-packages"],
      "rust": {"lint": ["mdmost"], "test": ["mdmost", "pulldown-latex"]},
      "gitea_packages": { ...as above... }
    }

plus the settled migrations that are not decisions: `## Unreleased` becomes
`## [Unreleased]`, the Makefile's `man` rule is replaced by
`include build/man.mk`, and `docs/man-deflist.lua` gives way to
`build/man-deflist.lua`. mdmost's `release.yml` is removed once
`release-build.yml` and the publish blocks cover what it did.

## Proof

Nothing here merges on reasoning alone. In `oetiker/mdmost`, on the conversion
branch:

- D24, D25: the assembled `ci.yml` with `ci-local.yml` goes green on a pull
  request, and a deliberately broken vendored test turns `ci-passed` red.
- D26, first and alone: a throwaway workflow builds a Homebrew bottle on
  `macos-14` from a local tap whose tarball URL is `file://`. If Homebrew
  refuses that, bottles cannot be built before the merge, and this section is
  revised before anything else is built on it.
- D26: a real mdmost release goes through `Create release PR`, the merge and
  publish, with no push to `main`, and `brew install oetiker/mdmost/mdmost`
  pours the bottle.
- D27: the same release lands in the registry, and `podman` containers of
  Debian, Ubuntu, Fedora and Rocky install mdmost anonymously with the lines
  above, `gpgcheck=1` active on dnf. A re-run of the Gitea job after success
  reports the 409s as matching and stays green.

## What is not decided here

- Whether other oposs repositories adopt `release_build` or
  `publish-gitea-packages`. Both are opt-in; nothing changes for a repository
  that does not name them.
- Moving mdmost to the `oposs` GitHub organisation. It would let mdmost use the
  organisation secret, and it would change the Homebrew tap URL and the
  formula's `root_url`.
