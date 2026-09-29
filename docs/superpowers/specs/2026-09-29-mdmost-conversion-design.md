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
      "test": ["mdmost", "pulldown-latex"],
      "tested_elsewhere": ["syntect"]
    }

- `lint`: `rust-check` runs `cargo fmt --check -p <name>` and
  `cargo clippy --all-targets -p <name> --no-deps -- -D warnings` for each
  name. `--no-deps` is required, for the clippy-driver reason above.
- `test`: `rust-test` runs `cargo test -p <name>` for each name, as its own
  matrix leg, so a red leg names the crate that broke.
- `tested_elsewhere`: workspace members whose tests run outside `rust-test`,
  for example in D25's `ci-local.yml`. The standard runs nothing for them and
  cannot confirm that anything else does. The list is a written promise by the
  repository, which is its whole purpose: leaving a crate out of `test` becomes
  a decision someone wrote down.

`test` is required whenever the `rust` key is present.

The block stays literal. D20 settled that assets carry no substitution token,
and the only generated text so far is the aggregator's and `finalize`'s
`needs:` lists. So the lists are read at run time: a small `rust-plan` job
reads `.github/repo-infra.json`, runs `cargo metadata --no-deps`, and fails in
three cases, naming the crates involved:

- a listed name is not a workspace member (a renamed crate must not become a
  leg that tests nothing);
- a workspace member is in neither `test` nor `tested_elsewhere` (a newly
  vendored crate must not go untested without an error, which is the gap this
  decision exists to close);
- `lint` or `test` is present and empty, or `test` is missing (an empty
  matrix is a workflow error, and "no tests" is not a configuration the
  standard offers);
- the key is absent and `cargo metadata` reports `workspace_default_members`
  different from `workspace_members`. That is the case with a root `[package]`
  (bare `cargo test` runs the root package only) and with `default-members` in
  any workspace, and it is exactly the silent gap this decision closes. The
  field needs cargo 1.71 or later; `rust-toolchain@stable` is newer.

Otherwise it outputs the two lists. `rust-check` and `rust-test` take them as
`strategy.matrix.package: ${{ fromJSON(needs.rust-plan.outputs.lint) }}` and
`...outputs.test`. With the key absent where default members and members are
the same (a single crate, or a virtual workspace without `default-members`),
`rust-plan` outputs one empty entry and both jobs run today's workspace-wide
commands.

The last rule changes behaviour for Rust repositories already on the standard.
It reaches one only with the `apply` that installs this version of `ci-rust`,
so a repository that needs the key sees `ci-passed` go red on that upgrade pull
request, with a message naming the members, and adds the key there.

`rust-plan` is in the block's manifest `jobs` list beside `rust-check` and
`rust-test`, so it is in `ci-passed`'s generated `needs:`. This matters:
`ci-passed` fails only on a `failure` or `cancelled` need. If `rust-plan` fails,
both matrix jobs are skipped, and without `rust-plan` itself in the list
`ci-passed` would report green on a run whose Rust checks never ran.

`check` and `apply` never run cargo, so `repo_infra` keeps having no runtime
dependencies.

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

    "release_build": true,
    "release_files": ["Formula/mdmost.rb"],
    "release_assets": ["mdmost-*-x86_64-unknown-linux-musl.tar.gz", "..."]

`release_files` lists the repository paths the build may write back; see
step 3. An entry that is `CHANGES.md`, a `version_files` path,
`.github/repo-infra.json` or anything under `.github/` would reopen the channel
step 3 closes. `check` refuses such entries, and `finish` refuses them again at
run time after normalising the paths, since `finish` reads the list from the
dispatched `main`, whether or not anyone ran `check`. `release_assets` lists, as name patterns
where `*` stands for any run of characters, every file the release must carry.
It is declared independently of the build on purpose: a list the build
produced itself would shrink along with a build that drops a file.

A reusable workflow can only be called as a job, never as a step, so the
release workflow for these repositories has three jobs:

1. `prepare`: the guard, then two new refusals and a clean-up, then the roll,
   the bump and the commit of the release branch as today (including the Rust
   `cargo update` step). It outputs the version and the branch head.
   - It refuses while a release pull request is open, because a second
     dispatch would force-move that pull request's branch. A release pull
     request is an open pull request from a `release/*` branch of this same
     repository, opened by `github-actions[bot]`; a fork naming a branch
     `release/x` blocks nothing. The refusal names the blocking pull request.
   - It refuses while the latest release in `CHANGES.md` on `main` has no tag:
     `vX.Y.Z is in CHANGES.md on main but has no tag`. The message names the
     three ways out, which `RELEASING.md` repeats: **Re-run failed jobs** on its
     publish run; for a release that is already out under another tag, push
     `vX.Y.Z` by hand (the ruleset covers the branch, not tags); to abandon it,
     a pull request that moves its entries back under `[Unreleased]`. Without this, a dispatch while publish is running or has
     failed computes the same version again from the tags, and `roll`, which
     has no check for an existing version heading, writes a second
     `## X.Y.Z` into `CHANGES.md`.
   - It deletes stale drafts (below).
2. `build`: `uses: ./.github/workflows/release-build.yml` (the D20 seam again:
   project-owned, `workflow_call`, inputs `version` and `ref`), with
   `permissions: contents: read` and no secrets. Each file the project ships is
   uploaded as an Actions artifact named `release-asset-*`. Files that must
   record those artifacts, such as a Homebrew formula with `sha256` lines and a
   `version` line, are uploaded as the artifact `release-files`, a tree of
   repository paths. The `uses:` path resolves at the dispatched commit on
   `main`, not on the release branch.
3. `finish`: `needs: [prepare, build]`, with `contents: write`,
   `pull-requests: write` and `statuses: write`. It refuses any path in
   `release-files` that is not listed in `release_files`, and any file that is
   not valid UTF-8 text (the commit library writes strings). The read-only
   build job therefore cannot write `CHANGES.md`, `.github/repo-infra.json` or
   a version file through this channel. `finish` commits the files onto the
   release branch and creates a **draft** release for `vX.Y.Z` with no tag,
   with the `name`, `body` (the version's `CHANGES.md` section) and
   `make_latest` the publish frame sets today. It attaches every
   `release-asset-*` file and `release-build.json`, which records the new
   branch head and the names of the attached assets. Before attaching, it
   checks the artifacts against `release_assets` (below) and refuses a build
   that is missing a declared asset. It sets the commit status
   `release-built` on that head. Then it opens the pull request, so reviewers
   see the formula change in the diff. The commit lands before the pull
   request exists, so the one **Approve workflows to run** click still covers
   the pull request's checks.

A called workflow's jobs belong to the caller's run, so `finish` finds the
`release-asset-*` artifacts with `download-artifact` and a pattern.

### Two release workflow assets

A job with `uses: ./.github/workflows/release-build.yml` makes the whole
workflow invalid when that file does not exist, whatever the job's `if:`
says. One file cannot serve both kinds of repository. The manifest therefore
gets a second asset: `release-pr-build`, source
`workflows/release-pr-build.yml`, rendered to the same target
`.github/workflows/release-pr.yml` and chosen instead of `release-pr` when
`release_build` is set. Each carries its own marker and version, so `check`
compares a repository against the variant it uses. The shared logic stays in
`workflows/lib`, so the two files differ in job structure only.

A repository that turns `release_build` on or off carries the other variant's
marker. `check` would today read that as a file not managed by repo-infra
(`conflict`), and `apply`'s three-way merge has no base for it. So `check`
recognises the sibling marker as `outdated (variant switch)`, and `apply`
merges three ways with the sibling variant's source as the base. Replacing the
file whole would drop local edits, and a Rust repository carries one it must
keep: the `cargo update --workspace` step `release-pr.yml` documents in a
comment, whose absence is what shipped mdmost v0.1.1 with a stale
`Cargo.lock`. The
manifest's selection rule, not the order of its entries, decides which of the
two renders to the shared target.

### Tagging the built commit

After the merge, publish does not tag the merge commit. It tags the head
recorded in `release-build.json`: the commit whose tree was built, plus the
`finish` commit, which writes only declared `release_files` paths from the
build's own output. The tag therefore describes the release artifacts,
whatever else reached `main` while the pull request was open. The ruleset
leaves `strict_required_status_checks_policy` off on purpose, so `main` moving
under an open release pull request is the normal case. A tree comparison
against the merge commit, the first version of this section, would have
refused on every such release, after the merge, at a point where `CHANGES.md`
on `main` already carries the version and a new dispatch stops on an empty
`[Unreleased]`.

The tag is on `main`'s history when the pull request is merged with a merge
commit. After a squash or rebase merge the tagged commit is not an ancestor of
`main`. The tag keeps it reachable after the release branch is deleted, the
release is still correct, and the next version is still computed from it
(`release-pr.yml` reads all `v*` tags, not `main`'s history). `git describe` on
`main` no longer finds it. Publish emits a notice in that case, and
`RELEASING.md` recommends the merge commit for release pull requests. All
three methods stay allowed.

### The release-branch gate

One push can still separate the pull request from its build: a push to the
release branch after `finish`. The usual cause is the **Update branch** button,
which strict checks being off makes tempting and harmless on every other pull
request.

The changelog gate catches it before the merge, on release pull requests as
`prepare` defines them (same repository, opened by `github-actions[bot]`).
Any other `release/*` branch, such as a person's or a fork's, gets the ordinary
changelog rules and the label. Its token cannot see drafts
(GitHub lists them only to tokens with push access), so it does not read
`release-build.json`. It reads the commit status instead: on a `release/*`
head branch of a repository with `release_build` set (read from
`.github/repo-infra.json` at run time), `changelog-updated` fails unless the
pull request head carries the `release-built` status. A later push is a new
commit without that status. The failure says: `the release branch changed
after it was built (the Update branch button does this); close this pull
request and dispatch Create release PR again`. The job gains `statuses: read`,
and its `if:` changes so that `release/*` branches run this check instead of
being skipped. On those branches the `no-changelog` label is ignored: adding
it to a red release pull request is the natural reflex, and it would turn the
check green after an **Update branch**. The gate reads `release_build` from
the base commit, not from the pull request's merge checkout, and accepts the
status only when `github-actions[bot]` created it. Anyone who can push can set
a status of any name, and can equally fake `changelog-updated` itself, so this
guards against accidents, not against people with write access. For a
repository without `release_build`, `release/*` stays exempt as today.

### Publishing

The publish workflow starts on every push to `main` that touches
`CHANGES.md`, and most of those pushes are ordinary pull requests merged after
a release is complete. Today the tag's presence is the whole stop condition,
which also means a failure after the tag leaves a re-run with nothing to do.
With `release_build` set, the frame's `publish` job decides from the tag and
the releases together. Releases come from a paginated `listReleases`, since
`getReleaseByTag` answers 404 for a draft. A release matches when its
`tag_name` is `v<version>`. "The tag's commit" means the peeled commit: publish
creates annotated tags, so the ref points at a tag object, and publish follows
it (`git.getTag(...).object.sha`) and accepts a lightweight tag as well.

Once the tag exists, the tag is the record of what was built.
`release-build.json` is needed only before that, in case 3.

1. The tag exists, a published release matches, and it carries no
   `release-build.json`: the release is complete. Notice, no outputs, stop.
   This is the ordinary pull request case.
2. The tag exists and exactly one draft matches: an earlier attempt stopped
   after tagging. The head is the tag's commit, and the asset names come from
   `release_assets`. Update the draft's tag and target (idempotent), set a
   moving major tag if configured (idempotent), set the outputs, and continue.
3. The tag does not exist: validate, then create. Exactly one draft must
   match (none, or more than one, fails and names the count);
   `release-build.json` is downloaded through the API by asset id, since
   `browser_download_url` does not serve drafts, and must name a head; the head
   must exist and its `CHANGES.md` must name the version as its latest release.
   Only then is the tag object created with `object:` set to the head (the
   frame uses `context.sha` today) and the draft updated.
4. Anything else fails and says which state it found: a tag with no release
   at all (a draft deleted after tagging), a published release that still
   carries `release-build.json` (a draft published by hand in the UI, which
   skips every add-on), several matching drafts.

Every step after validation is safe to repeat, so **Re-run failed jobs** and a
whole-workflow re-run both finish a stopped release instead of skipping it.
`finish` creates the draft with `target_commitish` set to the head, so a draft
published by hand at least tags the built commit; case 4 then reports the
skipped add-ons.

`finalize` asserts `release_assets` alongside the assets its generated list
already expects, so a build that dropped a file does not publish; it reads the
patterns from `.github/repo-infra.json` at the tagged head, checked out with
an explicit `ref:` (it checks out the pushed commit today), which a re-run
reads the same way. It deletes `release-build.json` (an asset that is already
gone counts as success), and only then makes the release public. The values
publish needs from the file travel as job outputs, so nothing reads it after
this point, and the file is never public. Deleting it afterwards would also be
impossible on a repository with GitHub's immutable releases turned on.

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
merge. Two exceptions remain. D27's RPMs: Gitea signs them on upload, so the
bytes a dnf user installs differ from the release asset by that signature. And
`publish-crates-io` still builds after the merge, since `cargo publish`
packages and verifies the crate itself; it builds from the tagged head.

### The Homebrew window

The formula on `main` points at `releases/download/vX.Y.Z/...` from the
moment of the merge, and those URLs answer 404 until `finalize` makes the
release public. Normally that is the few minutes publish takes. Any publish
add-on that fails keeps the release a draft, and `brew install` fails for as
long as it stays one. This is accepted. The recovery is the one
`release-flow.md` already gives: **Re-run failed jobs** on the publish run.

### Stale drafts

A closed release pull request leaves its draft behind. Drafts are not public.
`prepare` deletes a draft when all three hold: it carries a
`release-build.json` asset (so a person or another tool made none of the
others), its tag does not exist, and its version is not the latest release in
`CHANGES.md` on `main` (that one belongs to a merged release that publish has
not finished, and the refusal above covers it). Pull request state plays no
part: `release/vX.Y.Z` is reused whenever a version is dispatched again, so
"the pull request from that branch" can be several, and the realistic way to
abandon a merged release, a pull request that moves its entries back under
`[Unreleased]`, is itself merged. The version does not matter either: a closed
pull request for 1.2.0 followed by a bugfix release 1.1.1 would otherwise
leave the 1.2.0 draft forever.

`finish` also deletes any draft for its own version that carries
`release-build.json` before it creates its own. `prepare` has passed both
refusals at that point, so such a draft belongs to an abandoned attempt, and
case 3's "exactly one draft" stays true.

### Scope

`release_build` is off by default and changes nothing for a repository that
does not set it, apart from the add-ons' explicit checkout ref, which names the
same commit as before. A repository that sets it must provide
`release-build.yml`; a missing one breaks the release workflow outright, so
`check` reports it as `conflict`.

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
  package name, `version-release` pair and architecture exists (Gitea's RPM
  version is that pair, not the upstream version alone), and the job says in
  its log that the content was not compared.
- It downloads the draft's assets through the API by asset id, with the
  publish workflow's `contents: write`; a token that cannot push cannot see a
  draft.
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
token to another package type. Forwarding the normalised `$uri` instead is
wrong too: it is percent-decoded and nginx does not re-encode it, so `%3F`
would reach Gitea as `?`. The proxy therefore keeps the bare `proxy_pass` and,
on these paths, answers 400 to any request path containing a `.` or `..`
segment, `//`, or a percent-encoded `/`, `.`, `?`, `#`, `\` or `%`. Other
encodings pass: apt sends `~` as `%7E`, and `~` is how cargo-deb writes a
pre-release version (`1.0.0~rc.1`). The release flow never produces one
(`version.js` accepts `X.Y.Z` only), so this matters for packages uploaded by
hand. Since nothing that changes the path's
meaning is left encoded, raw and normalised path select the same resource.

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
      "gitea_packages": { ...as above... }
    }

plus the settled migrations that are not decisions: `## Unreleased` becomes
`## [Unreleased]`, the Makefile's `man` rule is replaced by
`include build/man.mk`, and `docs/man-deflist.lua` gives way to
`build/man-deflist.lua`. `Formula/mdmost.rb` is part of `release-files`, not
of `version_files`: its `version` line and its `sha256` lines are written by
`release-build.yml` in one place. That file also checks the bottle rename
(`brew bottle` writes `mdmost--<version>`, the URL Homebrew fetches has one
dash); a `release_assets` pattern cannot, because `*` absorbs the extra dash.
mdmost's `release.yml` is removed once
`release-build.yml` and the publish blocks cover what it did.

## Proof

Nothing here merges on reasoning alone. In `oetiker/mdmost`, on the conversion
branch:

- D24, D25: the assembled `ci.yml` with `ci-local.yml` goes green on a pull
  request, and a deliberately broken vendored test turns `ci-passed` red.
- D24: a misspelt crate name in `rust.test`, and a workspace member removed
  from both `test` and `tested_elsewhere`, each turn `ci-passed` red.
- D26, first and alone: a throwaway workflow builds a Homebrew bottle on
  `macos-14` from a local tap whose tarball URL is `file://`. If Homebrew
  refuses that, bottles cannot be built before the merge, and this section is
  revised before anything else is built on it.
- D26: a real mdmost release goes through `Create release PR`, the merge and
  publish, with no push to `main`, and `brew install oetiker/mdmost/mdmost`
  pours the bottle. The release pull request needs exactly one **Approve
  workflows to run** click, the tag is on the recorded head, and
  `release-build.json` is gone from the public release.
- D26: clicking **Update branch** on a release pull request turns the
  changelog gate red with the re-dispatch message.
- D26: dispatching `Create release PR` while a release pull request is open is
  refused, and that pull request's draft survives.
- D26: a publish run that fails after the tag, and one that fails before
  `finalize`, both finish the release on **Re-run failed jobs**. An ordinary
  pull request merged afterwards leaves publish green with a notice.
- D26: dispatching `Create release PR` while a merged release is unpublished is
  refused, and `CHANGES.md` is unchanged.
- D26: turning `release_build` on in a repository at `release-pr` v3 shows
  `outdated (variant switch)` in `check`, and `apply` keeps the repository's
  `cargo update` step.
- D26: a build that drops a declared `release_assets` file is refused by
  `finish`.
- D26: a pull request merged into `main` while a release pull request is open
  does not stop the release.
- D27: the same release lands in the registry, and `podman` containers of
  Debian, Ubuntu, Fedora and Rocky install mdmost anonymously with the lines
  above, `gpgcheck=1` active on dnf. A re-run of the Gitea job after success
  reports the `.deb` 409 as matching by SHA-256 and the `.rpm` 409 as matching
  by name, version and architecture, and stays green.
- D27: through the proxy, an anonymous request for a path outside the owner's
  Debian and RPM registries still answers 401, and a request inside them with
  an encoded `..` or a `%2F` answers 400. A hand-uploaded test package with a
  `~` version installs through apt.

## What is not decided here

- Whether other oposs repositories adopt `release_build` or
  `publish-gitea-packages`. Both are opt-in; nothing changes for a repository
  that does not name them.
- Moving mdmost to the `oposs` GitHub organisation. It would let mdmost use the
  organisation secret, and it would change the Homebrew tap URL and the
  formula's `root_url`.
