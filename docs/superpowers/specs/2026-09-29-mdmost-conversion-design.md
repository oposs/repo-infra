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
- `test`: `rust-test` runs `cargo test -p <name>` for each name, as its own
  matrix leg, so a red leg names the crate that broke.

The block stays literal. D20 settled that assets carry no substitution token,
and the only generated text so far is the aggregator's and `finalize`'s
`needs:` lists. So the lists are read at run time, not rendered: a small
`rust-plan` job reads `.github/repo-infra.json`, checks every name against
`cargo metadata --no-deps` and fails naming any that is not a workspace member
(a renamed crate must not become a leg that tests nothing), and outputs the two
lists. `rust-check` and `rust-test` take them as
`strategy.matrix.package: ${{ fromJSON(needs.rust-plan.outputs.lint) }}` and
`...outputs.test`. With the key absent, `rust-plan` outputs one empty entry and
both jobs run today's workspace-wide commands. `check` and `apply` never run
cargo, so `repo_infra` keeps having no runtime dependencies.

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
cannot. A missing `ci-local.yml` makes the whole of `ci.yml` invalid, so
`check` reports it as `conflict`, as D20 does for `action-test.yml`.

One addition to the contract: `ci-passed` counts a skipped need as green, and a
reusable workflow whose every job is skipped by a job-level `if:` reports
`ci-local` as skipped. `ci-local.yml` therefore keeps its conditions inside
steps, never on a job, the same rule `conventions.md` gives for required
workflows and `paths` filters.

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

`release-pr.yml` becomes three jobs, because a reusable workflow can only be
called as a job, never as a step:

1. `prepare`: guard, roll, bump and commit the release branch, as the single
   job does today. It outputs the version and the branch head.
2. `build`: `uses: ./.github/workflows/release-build.yml` (the D20 seam again:
   project-owned, `workflow_call`, inputs `version` and `ref`), with
   `permissions: contents: read` and no secrets. Project build code never holds
   the token that can push branches and open pull requests. Each file the
   project ships is uploaded as an Actions artifact named `release-asset-*`.
   Files that must record those artifacts, such as a Homebrew formula with
   `sha256` lines and a `version` line, are uploaded as the artifact
   `release-files`, a tree of repository paths. The `uses:` path resolves at
   the dispatched commit on `main`, not on the release branch.
3. `finish`: `needs: build`. It commits `release-files` onto the release
   branch, creates a **draft** release for `vX.Y.Z` with no tag, attaches every
   `release-asset-*` file, and attaches `release-build.json`: the head commit
   after the `release-files` commit, and the names of the attached assets. Then
   it opens the pull request, so reviewers see the formula change in the diff.
   The commit lands before the pull request exists, so the one **Approve
   workflows to run** click still covers the pull request's checks.

A called workflow's jobs belong to the caller's run, so `finish` finds the
`release-asset-*` artifacts with `download-artifact` and a pattern.

### Tagging the built commit

After the merge, `release-publish.yml` does not tag the merge commit. It tags
the head recorded in `release-build.json`. That commit is exactly what was
built, so the tag describes the release artifacts by construction, whatever
else reached `main` while the pull request was open. The ruleset leaves
`strict_required_status_checks_policy` off on purpose, so `main` moving under
an open release pull request is the normal case. A tree
comparison against the merge commit, the first version of this section, would
have refused on every such release, after the merge, at a point where
`CHANGES.md` on `main` already carries the version and a new dispatch stops on
an empty `[Unreleased]`.

The tag is on `main`'s history when the pull request is merged with a merge
commit. After a squash or rebase merge the tagged commit is not an ancestor of
`main`. The release is still correct and the next version is still computed
from it (`release-pr.yml` reads all `v*` tags, not `main`'s history), but
`git describe` on `main` no longer finds it. Publish emits a notice in that
case, and `RELEASING.md` recommends the merge commit for release pull requests.
All three methods stay allowed.

One push can still separate the pull request from its build: a push to the
release branch after `finish`, for example a wording fix. The changelog gate
job, on a `release/*` head branch of a `release_build` repository, reads
`release-build.json` from the draft and fails unless the pull request head is
the recorded head: `the release branch changed after it was built; close this
pull request and dispatch Create release PR again`. This runs before the
merge, where that remedy works.

### Finding the draft

`getReleaseByTag` answers 404 for a draft, and GitHub allows several drafts
with one tag name. Publish pages through `listReleases` and takes the drafts
whose `tag_name` is the version. None, or more than one, fails the job and
names the count. Draft assets are downloaded through the API by asset id,
because `browser_download_url` does not serve drafts. With `release_build`
set, the frame's publish job updates that draft (tag, target) instead of
creating a new one, as it does today for every other repository.

`finalize` asserts the names listed in `release-build.json` alongside the
assets its generated list already expects, so a build that silently drops a
file does not publish. It deletes `release-build.json` from the release before
making it public.

### Why

Two reasons, one per side of the merge.

The pushes to `main` disappear. Everything that depended on the artifacts is in
the pull request, so nothing has to be written after the merge.

Publishing stops rebuilding. Converted repositories have had release pull
requests that were green followed by a publish run that failed, and mdmost's
own releases failed after the decision to release while building: v0.1.2's
bottle legs queued on a retired runner image, and v0.3.2's
`setup-homebrew@master` stopped resolving. With D26 a failure while building
happens before the merge, where closing the pull request cancels the release
cleanly. Publish uploads the files that were built and attached before the
merge. (D27's RPMs are the one exception: Gitea signs them on upload, so the
bytes a dnf user installs differ from the release asset by that signature.)

### The Homebrew window

The formula on `main` points at `releases/download/vX.Y.Z/...` from the
moment of the merge, and those URLs answer 404 until `finalize` makes the
release public. Normally that is the few minutes publish takes. Any publish
add-on that fails keeps the release a draft, and `brew install` fails for as
long as it stays one. This is accepted. The recovery is the one
`release-flow.md` already gives: **Re-run failed jobs** on the publish run.

### Stale drafts

A closed release pull request leaves its draft behind. Drafts are not public.
`prepare` deletes every draft whose tag does not exist as a git tag, not only
one for the version it is about to build: a closed pull request for 1.2.0
followed by a bugfix release 1.1.1 would otherwise leave the 1.2.0 draft
forever.

### Scope

`release_build` is off by default and changes nothing for a repository that
does not set it. The existing publish blocks (`publish-source-tarball`,
`publish-crates-io`) work either way. A repository that sets it must provide
`release-build.yml`; a missing one breaks `release-pr.yml` outright, so `check`
reports it as `conflict`.

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
  after a partial upload meets that for the files that went up the first time.
  For a `.deb`, 409 counts as success only when the stored file's SHA-256 (from
  Gitea's package API) equals the release asset's; a different file under the
  same version fails. For an `.rpm` that comparison cannot work: with
  `?sign=true` Gitea stores the signed file, whose SHA-256 never equals the
  unsigned asset's. There, 409 counts as success when a file with the same
  package name, version and architecture exists, and the job says in its log
  that the content was not compared.
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

The proxy matches its `location` against the normalised path but, with a bare
`proxy_pass`, forwards the raw one. A request such as
`/api/packages/oposs/debian/%2e%2e/generic/...` would then carry the reader
token to another package type. The proxy therefore forwards the normalised
`$uri` and refuses a request path containing `..` or an encoded dot.

Opening the paths makes every Debian and RPM package of the owner public,
including future ones from any repository. Something that must stay private is
published under another owner.

### What users type

Debian and Ubuntu (`/etc/apt/keyrings` is standard from Debian 12 and
Ubuntu 22.04 on; the first line creates it on older releases):

    sudo install -d -m 0755 /etc/apt/keyrings
    sudo curl -o /etc/apt/keyrings/gitea-oposs.asc https://gitea.oetiker.ch/api/packages/oposs/debian/repository.key
    echo "deb [signed-by=/etc/apt/keyrings/gitea-oposs.asc] https://gitea.oetiker.ch/api/packages/oposs/debian stable main" | sudo tee /etc/apt/sources.list.d/oposs.list

Fedora 41 and later (dnf5):

    sudo dnf config-manager addrepo --from-repofile=https://gitea.oetiker.ch/api/packages/oposs/rpm.repo

RHEL, Rocky and Alma, and Fedora before 41 (dnf4):

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
`build/man-deflist.lua`. `Formula/mdmost.rb` is part of `release-files`, not
of `version_files`: its `version` line and its `sha256` lines are written by
`release-build.yml` in one place. mdmost's `release.yml` is removed once
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
  pours the bottle. The release pull request needs exactly one **Approve
  workflows to run** click, the tag is on the recorded head, and
  `release-build.json` is gone from the public release.
- D26: a push to a release branch after `finish` turns the changelog gate red
  with the re-dispatch message.
- D26: a pull request merged into `main` while a release pull request is open
  does not stop the release.
- D27: the same release lands in the registry, and `podman` containers of
  Debian, Ubuntu, Fedora and Rocky install mdmost anonymously with the lines
  above, `gpgcheck=1` active on dnf. A re-run of the Gitea job after success
  reports the `.deb` 409 as matching by SHA-256 and the `.rpm` 409 as matching
  by name, version and architecture, and stays green.
- D27: through the proxy, an anonymous request for a path outside the owner's
  Debian and RPM registries, including one with an encoded `..`, still answers
  401.

## What is not decided here

- Whether other oposs repositories adopt `release_build` or
  `publish-gitea-packages`. Both are opt-in; nothing changes for a repository
  that does not name them.
- Moving mdmost to the `oposs` GitHub organisation. It would let mdmost use the
  organisation secret, and it would change the Homebrew tap URL and the
  formula's `root_url`.
