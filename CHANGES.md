# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
except that the first subsection is called `New` rather than `Added`. The release
workflow matches on `### New`; renaming it silently drops the section from the
release notes.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### New

### Changed

### Fixed
- The `ri-ci-man` job could fail with "The job has exceeded the maximum execution time of 10m0s" while it was still downloading packages from a slow Ubuntu mirror, so `ci-passed` failed although the manual was fine. The job now installs `pandoc`, `groff` and `man-db` without their recommended packages, so it no longer downloads ghostscript, imagemagick and their fonts. (#102)

## 2.5.0 - 2026-10-20
### New
- A Go program can now be released with the same seven archives as a Rust program: `ri-release-go-binaries` builds them under the same target names, so `ri-release-nfpm`, `ri-release-homebrew` and `mise use -g github:<owner>/<repo>` work for it unchanged. The optional `package` names the main package to build (default `.`), and `version_var`, for example `main.version`, puts the release version into the binary. `targets` and its exceptions work as in `ri-release-rust-binaries`.

## 2.4.0 - 2026-10-19
### New
- `.github/dependabot.yml` (`dependabot` v3) now asks for weekly dependency updates of the repository's own code, not only of the GitHub Actions: `cargo` for `ri-ci-rust` and `ri-ci-rust-musl`, `npm` for `ri-ci-node-pnpm`, `bun` for `ri-ci-node-bun`, `pip` for `ri-ci-python` and `gomod` for `ri-ci-go`, each with the `no-changelog` label. `apply` writes the entries for the CI pieces the callers call, and `check` reports the file `outdated` when the callers change. (#92)

### Fixed
- An onboarding pull request stayed blocked with every check green when classic branch protection on `main` required a check the onboarding replaced, such as `test`, and `check` reported only "branch-protection missing". `check` now reports classic protection as the conflict `classic-protection` and names every check it requires, and `apply --item classic-protection` removes it once the ruleset requires `ci-passed` and `changelog-updated`. With classic protection present, `apply --item required-checks` accepts the workflows on the pushed `repo-infra/apply` branch, so the ruleset can go on before the onboarding pull request merges. (#91)
- `apply --item actions-open-pr` refused with "wrote the setting and read back {'default_workflow_permissions': 'read', 'can_approve_pull_request_reviews': False}" although the setting had been written, because GitHub still answered with the old value. `actions-open-pr`, `delete-merged-branches` and `no-changelog-label` now read the setting back up to five times over eight seconds before they refuse. The refusal of `actions-open-pr` names an organisation policy only for a repository an organisation owns; for one a user owns it says the read-back may lag and a re-run is safe. (#93)

## 2.3.1 - 2026-10-16
### Fixed
- A workspace release on crates.io no longer stops at "timed out waiting for <crate> to be available in registry `crates-io`" with the remaining crates unpublished. `ri-publish-crates-io` waits a minute and publishes what crates.io does not have yet, up to four attempts, and waits five minutes when crates.io answers HTTP 429 (Too Many Requests). (#85)
- A release that adds a crate crates.io has never seen used to fail inside `cargo publish`, since Trusted Publishing cannot create a crate. `ri-publish-crates-io` now stops before uploading anything, names each new crate in "<crate> is not on crates.io yet", and says to publish once by hand, register the Trusted Publisher and re-run the failed jobs. (#86)
- `apply` run from a feature branch switched that worktree to `repo-infra/apply` without a word, so later commits landed on the wrong branch. It now refuses to start anywhere but the default branch or `repo-infra/apply`, with "this worktree is on <branch>" and the `git switch` to run, and prints "switched from main to repo-infra/apply" when it changes the branch. (#87)

## 2.3.0 - 2026-10-16
### New
- `ri-ci-claude-plugin` checks every `.claude-plugin/plugin.json` in the repository, so a plugin can live in a subdirectory such as `plugin/` and a marketplace entry with a `git-subdir` source installs that directory alone instead of the whole repository. Each message names the file it is about, and a repository without any `plugin.json` fails with "no tracked .claude-plugin/plugin.json in this repository". When the root has a `.claude-plugin/marketplace.json`, every entry that installs from this repository must point at a directory holding a `.claude-plugin/plugin.json`; entries for other repositories are not checked. (#82)

## 2.2.0 - 2026-10-16
### New
- Every merged release pull request left its `release/vX.Y.Z` branch behind. `check` now reports the GitHub setting "Automatically delete head branches" as the administration item `delete-merged-branches`, and `apply --item delete-merged-branches` switches it on.

## 2.1.0 - 2026-10-15
### New
- `ri-release-rust-binaries` takes `targets`, the target triples to build; without it the piece builds all seven as before. A name it does not build fails the run with "targets names <name>, which this piece does not build". A repository that builds fewer than the seven records exceptions in `.github/repo-infra.json`: `native-targets` always, `homebrew` for a missing mac or musl target, and `linux-packages` for a missing musl target.

### Changed
- The onboarding guidance now treats bringing a project up to its full shape as the job: more platforms, `.deb` and `.rpm` packages, a Homebrew formula, a manual, a README with badges and install snippets, a demo. The shape review runs before any caller is written and yields one work plan in which every item reads "do", with the few things the program cannot do or no piece covers asked apart; exceptions are for those and for what the owner rules out. The supported platforms are found by compiling for each target instead of from comments in the code, and the guidance names two traps: a root `Cargo.toml` that is also a workspace needs the `rust` key, and a target the release cannot skip is a gap in the standard.
- repo-infra's release gate builds mtuspy 0.2.2, the first mtuspy release on the v2 layout.

### Fixed
- `apply` committed on a `repo-infra/apply` branch left over from an earlier, merged run, so its changes sat on an old tree without the commits that came after. A merged `repo-infra/apply` branch now starts again from the current branch; one that has commits the current branch lacks, as after a squash merge, stops `apply` with a message that says to delete or rebase it.

## 2.0.1 - 2026-10-13
### Fixed
- repo-infra's release pull request could not be merged: the ruleset reported "2 of 2 required status checks are expected" although `ci-passed` and `changelog-updated` had passed. The release gate now builds mtuspy on a branch `gate/vX.Y.Z` of its own, deleted after the gate, instead of on the release branch.

## 2.0.0 - 2026-10-13
### New
- `/repo-infra:check` reports a workflow of the repository that pins an action at an older major than repo-infra's workflows or another workflow of the repository, for example `docs.yml` with `actions/upload-artifact@v4` where `build.yml` uses `v7`. Dependabot moves an action to one version in every workflow, so its pull request from `v4` would downgrade the files already on `v7`. The row reads `outdated` under `callers` and names the file, the action, both majors and where the newer pin is (#59).
- When a tag ruleset refuses to move the major tag (`moving_major_tag`), the publish run fails with "vN could not be moved to vX.Y.Z" and says the ruleset restricts updates on `v*`. `ri-publish-tag` moves the tag with the workflow's own token, so a ruleset that restricts only deletion lets the move through.
- Every CI and release build workflow takes a `repository` input, the repository to check out; it defaults to the calling repository. The Homebrew bottle and formula URLs name that repository. repo-infra's release gate uses it to build mtuspy.

### Changed
- Releases are titled `<repository name> vX.Y.Z` in every repository, for example `edaptor v1.8.0`, matching repositories that used that form before onboarding. Repositories whose releases carried the bare tag as title change pattern from their next release (#60).
- Repositories call repo-infra's workflows instead of copying them: every `uses:` reads `oposs/repo-infra/.github/workflows/<piece>.yml@v2`, and each release of repo-infra moves `v2`, so fixes arrive without a pull request. Run `/repo-infra:apply` once to migrate; repo-infra 1.x gets no further fixes.
- repo-infra's CI refuses a change to a workflow piece that would break callers of `v2`: a removed piece, input, secret or output, a changed input type, a newly required input or secret, or a wider permission. See RELEASING.md.
- The reusable workflows (`ri-*.yml`) live once, in `.github/workflows/` of repo-infra. The catalogue shows each one with the line consumers call it by, `uses: oposs/repo-infra/.github/workflows/<piece>.yml@v2`. `ri-ci-lib` and `ri-ci-repo-infra-selftest`, which test repo-infra itself, are no longer in the catalogue.
- The reusable workflows load the workflow library from the repo-infra commit they were called from. A repository that calls them needs no `.github/workflows/lib/` of its own.
- `ci-passed` reads its release-mode verdict from a new job, `release-verdict`, which calls `ri-release-verdict`. Copy both jobs from `assets/callers/ci-passed.yml`; `/repo-infra:check` reports a `ci.yml` without `release-verdict`, and `release-verdict` carries no release pull request skip. `ci-passed` fails with "release-verdict gave an unknown mode" when that job reports a mode other than `release` or `ordinary`, or none.
- `changelog.yml` is a short caller: its job `changelog` calls `ri-changelog`, and `changelog-updated` turns red when that job fails or is cancelled. Copy it from `assets/callers/changelog.yml`; `/repo-infra:check` reports a difference in its jobs or triggers and a repository without `changelog.yml`, and the `changelog` piece is no longer in the catalogue.
- Create release PR is a short `release-pr.yml` that calls `ri-release-prepare` and `ri-release-finish` from repo-infra and the repository's own `release-build.yml` and `ci.yml` between them. A repository may add jobs between prepare and finish; `/repo-infra:check` reports a `finish` that does not need all of them, and a repository without `release-pr.yml`. Copy it from `assets/callers/release-pr.yml`.
- `.github/workflows/lib/` is no longer installed in a repository, and `workflow-lib` is no longer in the catalogue.
- A GitHub Action's `ci.yml` calls its own `.github/workflows/action-test.yml` in a job `action-test`, next to `ri-ci-github-action`, which no longer calls it. `/repo-infra:check` reports a `ci.yml` that calls the piece without that job. The catalogue entry of `ri-ci-github-action` shows both jobs.
- `/repo-infra:check` expects every call of a repo-infra workflow to read `uses: oposs/repo-infra/.github/workflows/<piece>.yml@v2`, with each secret passed by name. It reports another ref or none, `secrets: inherit` on such a call, a file repo-infra does not ship, an input the workflow does not declare and a required input or secret left out, reading the workflows from the installed plugin. Calls of other repositories' workflows are no longer reported.
- `/repo-infra:check` reports copies of the workflows, `.github/workflows/lib/`, `ri-ci-lib.yml` and the old `changelog.yml` and `release-pr.yml` as the v1 layout, and says to run `apply`. A job that calls a copy through `./` is reported the same way.
- A release of repo-infra builds mtuspy with the release's own workflows before its pull request opens. When that build fails, Create release PR fails at "Build mtuspy with the release's pieces" and `v2` does not move.
- The catalogue's `gitea` job for `ri-publish-gitea` passes `GITEA_PACKAGE_TOKEN: ${{ secrets.GITEA_PACKAGE_TOKEN }}` instead of `secrets: inherit`. A repository in another organisation that copied the old job publishes with an empty token; name the secret there.
- `/repo-infra:apply` migrates a repository with the v1 layout in one commit on `repo-infra/apply`: it removes the copied workflows and `.github/workflows/lib/`, points every call at `@v2`, adds `release-verdict` and the new `ci-passed` to `ci.yml`, and writes the new `changelog.yml` and `release-pr.yml` over the old pieces. Each `secrets: inherit` on such a call becomes the secrets the workflow requires plus the optional ones the old workflows read, for example `GITEA_PACKAGE_TOKEN`.
- When the migration removes a copied workflow or library file that differs from every version repo-infra published, a file of the repository's own in `.github/workflows/lib/`, or a job of an old `release-pr.yml` or `changelog.yml` that the new one lacks, `/repo-infra:apply` names each under "The migration removed these local changes", in its output and in the commit message.
- `/repo-infra:apply` installs build files and never copies a workflow; `--item` with a workflow's name refuses with "is called, not installed" and the `uses:` line to add.
- The mtuspy example under `references/examples/mtuspy/` shows the v2 callers: `ci.yml`, `release-build.yml`, `release-publish.yml`, `changelog.yml` and `release-pr.yml`. `source.json` names the mtuspy release repo-infra's release gate builds.

### Fixed
- The release pull request showed "Approve workflows to run" until it merged. Create release PR now deletes the parked runs behind that banner for up to 60 seconds after it opens the pull request, and only warns when none appear or one cannot be deleted. Its `finish` job now needs `actions: write`, which the shipped `release-pr.yml` grants (#58).

## 1.1.2 - 2026-10-13
### New
- The skill carries mtuspy's callers, config, `nfpm.yaml` and formula under `references/examples/mtuspy/`, the example of a Rust program that publishes to every channel. Onboarding points a Rust program users install to it.

## 1.1.1 - 2026-10-12
### Changed
- The `man-pages` skill asks every manual for AUTHORS, REPORTING BUGS and COPYRIGHT, and for the repository URL at the top of SEE ALSO. AUTHORS lists the people and AI model families in the commit history, and COPYRIGHT copies the holder from `LICENSE`, which onboarding now asks about: a company or a person. `/repo-infra:check` reports a manual without these sections, an author missing from AUTHORS and a holder that differs from `LICENSE`.

## 1.1.0 - 2026-10-12
### New
- `ri-release-rust-binaries` builds the release archives of a Rust program for Linux (static, x86_64 and aarch64), macOS (Intel and Apple silicon), Windows (x86_64 and arm64) and illumos, each with the binary, the README, the licence and, except in the Windows zips, every man page. A package that builds a second binary besides `bin` fails the build instead of releasing without it. Install it with `apply --item ri-release-rust-binaries` (#53).
- `ri-release-nfpm` builds `.deb` and `.rpm` packages for amd64 and arm64 from the static Linux archives with nfpm 2.47.0 and an `nfpm.yaml` in the repository, and reads every package back before the release pull request opens. The config names the man pages with `.gz`, since the piece gzips them. Install it with `apply --item ri-release-nfpm` (#53).
- `ri-release-homebrew` bottles the formula for Apple silicon on macOS 14 and rewrites `Formula/<bin>.rb` on every release with the version, the four archive checksums and the bottle block. Install it with `apply --item ri-release-homebrew` (#53).
- `/repo-infra:check` reviews the project's shape after the script's report: which triggers apply (a command line, a terminal, a web interface, installed by users) and, for each rule, `met`, `gap`, `excepted` or `does not apply`. The review leaves the exit code of `check` alone. `references/project-shape.md` in the skill lists the rules, the README badges, one install snippet per channel and a Homebrew formula template (#57).
- `.github/repo-infra.json` accepts `exceptions`, which maps a rule id of the shape to the reason it does not apply. `check` reports a value that is not an object of non-empty reasons, and tells a repository that still has `skip` to rename it to `exceptions`. Onboarding reviews the shape once and records the agreed `exceptions`.

### Changed
- `/repo-infra:check` reports `workflow-lib` as outdated until `apply` installs v9, which `ri-release-nfpm` and `ri-release-homebrew` need (#53).
- Onboarding a Rust program that users install now suggests `ri-release-rust-binaries`, `ri-release-nfpm` with an `nfpm.yaml`, and `ri-release-homebrew` with `Formula/<bin>.rb` (#53).
- A repository that proves a new piece installed from a repo-infra branch may merge its conversion pull request before repo-infra releases the piece. Until the plugin is updated, `check` reports that piece as `unknown`.
- `/repo-infra:apply` starts with the script's report instead of `/repo-infra:check`, so an update runs no shape review.
- The install commands in the skill add the rpm repository with one `curl` for dnf4 and dnf5 instead of the two `dnf config-manager` variants, and the Debian commands also run `apt install`. The Homebrew commands gain a `brew trust` line, and the registry commands follow the `distribution`, `component` and `group` set in `gitea_packages` (#57).

### Fixed
- The catalogue and the header of `ri-release-source-tarball` named its artifact `release-asset-source-tarball`; the piece uploads `release-asset-source`. `apply` installs the corrected header as `ri-release-source-tarball` v2.

## 1.0.2 - 2026-10-08
### Fixed
- A pull request opened with `gh pr create --label no-changelog` could show `changelog-updated` failed with "This pull request adds nothing under '## [Unreleased]' in CHANGES.md", although it carried the label. The check now reads the labels when it runs, not when the pull request opened. `apply` installs the fix as `changelog` v6.

## 1.0.1 - 2026-10-07
### Changed
- `check` reports each job of `ci.yml` other than `ci-passed` that lacks the `if:` of `assets/callers/release-pr-skip.yml` in the skill. With that `if:` in place, approving the parked runs on a release pull request runs only `ci-passed` instead of building and testing everything a second time.

## 1.0.0 - 2026-10-04
### Changed
- `check` no longer stops with "the standard does not recognise this repository": it reports every installed piece as `current`, `outdated`, `edited` or `unknown`, checks the repository's own `ci.yml`, `release-build.yml` and `release-publish.yml` against the pieces they call, and lists the administration items. A repository picks its pieces from the catalogue in the skill and calls them from these files.
- The workflows repo-infra ships are now separate files named `ri-*.yml` that the repository calls; `ci.yml`, `release-build.yml` and `release-publish.yml` are no longer generated and belong to the repository. A repository on the generated files sees `unknown` for them in `check` until they are rewritten (see `references/onboarding.md` in the skill).
- `apply` replaces outdated pieces, installs missing core pieces and the pieces they need, and removes files a newer version no longer ships, one commit per piece named `Install <piece> vN from the repo-infra standard`. It then prints the upgrade notes of every version it crossed and what the callers must change, and stops.
- `apply` refuses to install any piece (`release-in-progress`) while a release pull request is open or the latest released version in `CHANGES.md` has no tag yet.
- Branch protection, the `no-changelog` label and the Actions setting are applied only when named with `apply --item`.
- A piece with a local edit that still carries the current version used to read `ok`; `check` now reads it `edited` and exits 1. It says how to get back to the published file: move the change into a caller, delete the file and run `apply --item <piece>`.
- `apply` no longer prints "already vN" for a piece whose file carries a local edit and claims the current or a newer version. It prints what `check` says about it: the way back to the published file, or "update the plugin" when the file is newer than the plugin.
- When `apply` stops for a hand merge or refuses, it prints the message (`NeedsMerge: ...`, exit status 3, or `refused: ...`, exit status 1) instead of a Python traceback.
- When a `gh` call fails or the plugin's files are damaged, `check` and `apply` print the message (`gh: ...` or `the plugin's asset store is broken ...`) and exit 1 instead of a Python traceback. `apply` refuses a misspelt piece name or a misplaced `--from` before it contacts GitHub.
- `apply` no longer appends ` sha256=` to the marker line of the files it writes. Files that carry it from v0.3.1 still read as the version they claim.
- Commits made by `apply` end with `Co-Authored-By: Claude <noreply@anthropic.com>` instead of naming a model version.
- `.github/repo-infra.json` no longer reads `ecosystems`, `ci`, `ci_local`, `publish`, `build`, `publish_local`, `release_build`, `release_build_local`, `skip` or `answers`; `check` asks for them to be removed.

### Fixed
- `check` reports a call that would fail at the start of a run: an input or secret the called workflow does not declare or requires, a missing workflow file, or a job that grants fewer token permissions than the workflow it calls needs.
- `check` reports a caller that would misbehave once it runs: a `ci-passed` job that differs from the shipped pattern, a `finalize` that does not need every other job, a `finalize` without `if: needs.publish.outputs.release_id != ''` (the Publish run turns red after every merge that releases nothing) or wired to the wrong outputs, a call to a workflow in another repository, and a call that does not hand `ref: ${{ inputs.ref }}` to a workflow taking it.
- `check` reports a `ci.yml` that does not run on `push` and `pull_request` to `main` or does not call `ri-release-pr-current`, and a `release-publish.yml` that does not run on `push` to `main` with `paths: [CHANGES.md]` alone, lacks the `release-publish` concurrency group, cancels a running publish or has a `workflow_dispatch` trigger.
- `check` reports an installed workflow piece that no workflow calls, such as `ri-ci-python.yml` left behind when its job was removed from `ci.yml`.
- `apply` replaces the files a repository got from repo-infra v0.2.0 (`changelog` v2, `release-pr` v3, `workflow-lib` v4, `container` v1) instead of stopping for a hand merge of each one; `check` reads them `outdated`. Copies of `changelog.yml` and `release-pr.yml` taken from v0.1.0 read `outdated` as well.

## 0.3.1 - 2026-10-02
### Fixed
- `apply` with the installed plugin no longer stops on every changed workflow file with "local edits present": files it writes end their `# repo-infra:` line in ` sha256=...`, which must not be edited, and an unedited file is upgraded in place. A file from an earlier version stops once, for the `apply` skill to check its git log for local edits; handed back without edits, it gets the suffix and is committed as `Install <item> from the repo-infra standard`. A file with local edits is committed as `Merge <item> from the repo-infra standard with local edits` and stops again at the next upgrade.
- `apply` keeps short lists in `.github/repo-infra.json` on one line, such as `"ci": ["ci-man", "ci-rust-musl"]`, instead of rewriting the file one value per line.

## 0.3.0 - 2026-10-02
### New
- **Create release PR** builds the release and runs the CI on the release branch before it opens the pull request, and writes the required checks itself, so the pull request can merge at once. The **Approve workflows to run** banner still appears on it, but nobody needs to approve those runs: publishing deletes them, and the next **Create release PR** deletes those of a closed release pull request.
- `.github/workflows/release-build.yml` is now installed and kept up to date by `apply` in every repository. It runs the build add-ons listed in `release_build`, and with `"release_build_local": true` also the project's own `.github/workflows/release-build-local.yml`; files such as a Homebrew formula change in the pull request, and publishing tags the commit that was built.
- The `release-source-tarball` build add-on attaches the `make dist` tarball, built before the merge. It replaces the `publish-source-tarball` publish add-on, and `apply` moves the setting.
- A Rust workspace can list which crates `ci-rust` lints and which it tests, in a `rust` key of `.github/repo-infra.json`; each crate gets its own check. A workspace where a plain `cargo test` would skip some crates now fails the `Rust workspace plan` check until the key says where their tests run.
- `"ci_local": true` makes the jobs in `.github/workflows/ci-local.yml` part of the required `ci-passed` check.
- The `publish-gitea-packages` add-on uploads a release's `.deb` and `.rpm` files to a Gitea package registry, which signs them; the release stays a draft until the upload succeeded.

### Changed
- The branch ruleset now requires a pull request to be up to date with `main` before it merges; behind pull requests need **Update branch** first, and `check` reports `required-checks` as outdated until `apply` writes the rule. A release pull request that `main` moved past cannot merge and shows a red `ci-passed`: "main moved after vX.Y.Z was built; close this pull request and dispatch Create release PR again".
- **Update branch** on a release pull request turns `ci-passed` and `changelog-updated` red with "the release branch changed after it was built (the Update branch button does this); close this pull request and dispatch Create release PR again".
- `Create release PR` no longer waits for the checks on `main`; it refuses only a check that already failed. It also refuses while a release pull request is open or while the latest release in `CHANGES.md` has no tag.
- Publish refuses to tag when `main` does not match the release that was built: "main at <sha> does not match the release built from <head>; merge a pull request that moves the vX.Y.Z entries in CHANGES.md back under [Unreleased], then dispatch Create release PR again".
- Publish refuses to tag when it finds no merged release pull request for the version: "vX.Y.Z: no merged release pull request from release/vX.Y.Z, so publish cannot compare main with the release that was built. Nothing was tagged."
- Re-running the publish workflow no longer fails on a crate an earlier attempt already uploaded, and both **Re-run failed jobs** and a whole-workflow re-run finish a stopped release.
- Publishing to crates.io uses the `Cargo.lock` of the release pull request as it is (`cargo publish --locked`) and no longer runs `cargo update --workspace` first. For a Rust repository whose `version_files` lacks the `Cargo.lock` entries, `check` reports `cargo-lock-version-files` and `apply` adds them.
- `apply` refuses with `release-in-progress` while a release pull request is open or the latest release in `CHANGES.md` has no tag. Merge and publish that release, or close it, then run `apply` again; `apply --item` still applies administration items and files outside the release workflows.
- The release build and the CI run get the repository's secrets. No repository secret may carry write access to the repository.
- `check` reports `ci-local.yml`, `action-test.yml` and `release-build-local.yml` as a conflict when they do not declare the input `ref` or do not check it out. It also reports `ci-local.yml` and `action-test.yml` when they upload an artifact named `release-asset-*` or `release-files` in any letter case, names the release build keeps for itself.
- `check` reports `container` as outdated; only a comment in `build/container.mk` changed.

### Fixed
- `apply` without `--item` no longer stops with "git commit -m Install ci-lib from the repo-infra standard ... failed" when a workflow file has more than one block to install, as `ci.yml` and `release-build.yml` do. The first item writes the whole file; each further block of that file is reported as "installed with" that item instead of getting a commit of its own.
- `changelog-updated` applies the changelog rules of `main`; a pull request that edits `.github/workflows/lib/changes.js` no longer decides its own verdict. The pull request that first installs the workflow library still uses its own copy, since `main` has none yet.
- When a git command that `apply` runs fails, the error now includes what git printed on standard output, such as "nothing to commit". Before, those messages ended after "failed:".
- When `apply` first writes `.github/repo-infra.json` for a Rust repository with a `Cargo.lock`, `version_files` now lists `Cargo.lock` too: one entry for the main crate and one for each workspace crate with `version.workspace = true`. Before, the release pull request left `Cargo.lock` at the old version unless someone added the entry by hand.
- `apply` works in a linked git worktree. It stopped there with `NotADirectoryError` when it installed the branch ruleset or prepared a merge of a locally edited file.
- The changelog check no longer fails with "CHANGES.md has no '## [Unreleased]' heading" on the pull request that introduces that heading. A pull request that removes the heading fails with a message naming it.

## 0.2.0 - 2026-09-28
### New
- The `ci-man` add-on (D23). A repository with its manual in `docs/manual.md`
  lists `ci-man` in the `ci` list of `.github/repo-infra.json`, and every pull
  request then builds the man page with `make man` and fails when the manual
  stops converting or roff reports a warning such as `table wider than line
  length minus indentation`. Choosing it installs `build/man.mk` and
  `build/man-deflist.lua`, which turns option lists written as
  ``- `--option`: text`` into proper man page entries, and `check` stops
  listing `man-pages` among its candidates.
- `make man` puts the page in the man section that `section:` in the manual's
  front matter names, so a daemon's manual with `section: 8` builds
  `man/<name>.8`, and `ci-man` checks pages of every section. A manual without
  a `section:` line stops `make man` with a message naming `docs/manual.md`.
- Two skills in the plugin: `writing-style` gives the house voice for READMEs,
  manuals, maintainer notes, changelog entries, code comments and commit
  messages, and `man-pages` covers how a man page is structured, built and
  shipped. They trigger on their own, without a repository check.
- The `ci-rust-musl` add-on (D22), and with it the first CI block a repository
  chooses rather than one detection finds. A Rust repository names it in a new
  `ci` list in `.github/repo-infra.json` and every pull request cross-builds a
  statically linked musl binary for `x86_64` and `aarch64`, then **asserts** the
  linkage -- `crt-static` is a hint the linker may ignore, and a binary that
  only runs on the machine that built it fails at the far end, on a host nobody
  is watching. It is opt-in because `Cargo.toml` does not say whether a
  repository ships a binary: a library crate has none to link. Once named it is
  a required check, joining `ci-passed`. See `references/conventions.md`.
- The `publish-crates-io` add-on (D21). A repository names it in its `publish`
  list and its releases go to crates.io with **no stored credential**: the job
  exchanges its GitHub OIDC identity for a short-lived token via
  `rust-lang/crates-io-auth-action`, so no `CRATES_IO_TOKEN` secret exists
  anywhere. One `cargo publish --workspace --locked` serves both the
  single-crate and the multi-crate case, in dependency order, replacing the
  hand-rolled publish-then-retry loop a workspace needs otherwise.
  Converting a crate that already publishes needs a new Trusted Publisher
  registered on crates.io first -- the pin names the workflow filename, and
  conversion renames it. See `references/conventions.md`.
- Repositories whose product is a GitHub Action are recognised. `action.yml`
  selects a `github-action` ecosystem, which validates the action manifest
  against every workflow that calls it and runs the project's own action test.
- A Python repository can declare test dependencies. `ci.yml`'s pytest job now
  installs `requirements-dev.txt` when the repository has one, the same way the
  Checkmk plugin job already did.
- repo-infra's own CI builds a real container and runs the autotools driver it
  ships against it, as a required check. The assets are the product, so a
  regression in them no longer merges.
- Autotools repositories can now build in a container end to end. `configure`
  and `make` outside the container drive podman; inside, they are plain
  autotools. A CI runner no longer probes a project's system dependencies.
  repo-infra ships the *shape* of the build environment (`build/container.mk`);
  the project keeps its Containerfile and what goes in it.
- `make test-dev TARGET=t/foo.t` runs one test file against the live working
  tree, without rebuilding the image.
- The plugin documents what to do when the standard has no answer for a
  repository's shape: question, prove, upstream, with a report that says so
  instead of a false "N items need attention" count.
- A publish add-on that attaches the `make dist` source tarball to a release. It is the first of spec 2's add-ons, and any autotools repository needs it before it can be converted without losing the tarball it publishes today.
- A CI block for Checkmk plugins: lint, tests and a throwaway package build. The Checkmk API a plugin imports is declared by the plugin, not by this block.
- The plugin reads a repository's ruleset, labels and workflow permissions.
- The plugin ships the release workflows as versioned, installable assets.
- The plugin can read and write asset version markers.
- The plugin detects a repository's ecosystems from file signals.
- The plugin assembles a repository's ci.yml from a frame plus one block per ecosystem.
- This repository's own .github/ is generated from the plugin's assets, and CI fails if the two differ.
- The plugin reports how far a repository has drifted, per asset and per CI block, and honours deliberate skips.
- /repo-infra:check reports drift as text or JSON.
- /repo-infra:apply installs missing assets on a branch, one commit per item.
- /repo-infra:apply creates the no-changelog label, sets workflow permissions and enables the ruleset, in that order.
- The plugin ships the repo-infra skill and the /repo-infra:check and /repo-infra:apply commands.
- CI blocks for rust and go.
- CI blocks for node, one for pnpm and one for bun.
- CI blocks for perl, one for autotools projects and one for Makefile.PL projects.

### Changed
- `check` reports `release-pr` and `changelog` as outdated until `apply`
  installs the new generation, whose only change is wording without em dashes.
  In the Actions log the first step of **Create release PR** is now called
  `Guard (right branch, green checks)`, and the report's first line reads
  `repo-infra check: <repo>`.
- The autotools CI block installs one fixed host toolchain and calls `make test`, rather than building natively against whatever the runner image happens to ship. A project that needs more than the toolchain declares it in its own Containerfile.
- The autotools release writes `VERSION` instead of rewriting `configure.ac`, which is where every autotools repository examined keeps its version.
- `check` now says when the standard does not recognise a repository at all, instead of reporting a count of missing items drawn from a repository kind it never identified.
- The release system is proven end to end: `v0.1.0` was cut by dispatching
  **Create release PR**, merging the pull request it opened, and letting the
  publish workflow tag and publish. The one manual step is the deliberate
  **Approve workflows to run** click on the release pull request, which exists so
  that no credential has to be stored; `RELEASING.md` explains why.

### Fixed
- `apply --item workflow-lib` refused every upgrade with `ships N files, and
  only a single-file asset can be merged or upgraded in place`, and `check`
  reported a partly upgraded library as a conflict (`files disagree`). It is now
  `outdated`, and `apply` upgrades the library file by file; a file with local
  edits stops the run before anything is written and is merged by hand.
- **Create release PR** wrote `### New` or `### Fixed` twice into the release
  notes when the `[Unreleased]` section carried a heading twice, as after
  merging two branches that each added the section skeleton. It now merges them
  into one subsection each; `workflow-lib` moves to v4 for this.
- Rewriting `.github/repo-infra.json` kept only `publish`, `build`, `skip`
  and `answers`, so a repository's `ci` and `publish_local` choices and any
  `_comment` were dropped from the file. Every key the rewrite does not compute
  is now kept as written. Nothing calls the rewrite yet, so no repository has
  lost a setting.
- Re-running "Create release PR" for a version whose branch still exists no
  longer fails with `Reference already exists`. It happened after a release PR
  was closed without deleting its branch, and after a run that committed before
  it could open the PR; the only way forward was deleting the branch by hand.
  The run now moves the existing branch to its new commit.
- A release can no longer be published with its artifacts missing. `finalize`
  flipped a release from draft to public on the strength of its `needs:` list
  alone, and that list is a generated line: a repository that had hand-added
  its own publish job to it -- the only way there was -- lost the edit at the
  next `apply`, and the revert did not fail. It simply stopped waiting. The
  release went public while the `.deb` was still building, or after that job
  had failed, and nothing anywhere went red; the first anyone knew was an
  operator downloading a release that had no package on it. Two changes, and
  both are needed. A repository's own publish job is now **declared**, in a new
  `publish_local` list in `.github/repo-infra.json`, so the `needs:` entry is
  generated and `apply` restores it instead of removing it. And `finalize` no
  longer trusts ordering at all: it lists the release's assets and asserts the
  ones the installed publish blocks say they attach, before it publishes
  anything. Ordering cannot report its own absence; an assertion cannot pass
  while being wrong. Missing assets now fail the job and leave the release a
  draft, which is the recoverable state. The matching logic is the new
  `assets.js` in the workflow library rather than text inside the `script:`
  block, so it is tested. `release-publish` is v3 and `workflow-lib` is v3:
  re-apply both, and if your repository hand-edits `finalize`'s `needs:`, move
  that job into `publish_local` and take the generated line.
- A failed release attempt no longer makes its commit permanently
  unreleasable. The release guard ignored only the current run's check runs,
  so the failed check run an aborted attempt leaves behind was read as a
  failing check by every later attempt -- and check runs cannot be deleted, so
  no retry on that commit could ever succeed. `oetiker/smalti` lost its whole
  first release to this. `release-pr` v2 gathers the ids through the new
  `checks.js:guardIgnoreIds`, which covers every run of the workflow on the
  commit; the logic moved out of the `script:` block because inline, nothing
  could test it.
- `apply` can enable required checks on a repository that already has a `main`
  ruleset. It could only create one, and GitHub rejects a duplicate name with
  422 -- so the repositories most likely to be converted, the protected ones,
  were the ones it could not finish.
- `apply` installs every file of a directory asset. It wrote only the first,
  so a fresh conversion installed one file of the workflow library and the
  next `check` reported `files disagree` on work that had just succeeded.

## 0.1.0 - 2026-08-19
### New
- `changes.js`: parse, roll and extract release notes from `CHANGES.md`, with the
  roller validating the file's shape before it writes. The previous implementations
  were single regexes that produced nothing at all on an unexpected shape, and
  "nothing" is indistinguishable from "no changes to release".
- `bump.js`: the generic version-file writer. Every write is located, rewritten and
  then read back and asserted, so a bump that does not take fails the release
  rather than tagging a repository whose files disagree with each other.
- `checks.js`: reads every check run on a commit rather than polling one named
  workflow, so the release guard keeps working when a repository names its CI
  something else. Zero checks counts as a failure, not a pass.
- `commit.js`: creates the release commit and branch through the Git Data API, so
  no workflow needs a git identity or push access to a branch.
- A changelog gate on every pull request. It compares the `[Unreleased]` block at
  base and head, so editing an old released section does not satisfy it. It is a
  required check, so `release/*` branches and the `no-changelog` label are the
  deliberate escape hatches. Both are job-level, so an exempt pull request skips
  the job and the required check goes green on its own.
- **Create release PR**: computes the next version from the tags, rolls
  `CHANGES.md`, sets every declared version file and opens a `release/vX.Y.Z` pull
  request. It refuses to run when no check has reported on the commit, because a
  release of untested code is exactly what the guard exists to prevent.
- **Publish release**: reads the released version back out of `CHANGES.md`,
  refuses to tag when any version file disagrees, creates an annotated tag and
  publishes the release. It exposes `version`, `tag` and `release_id` as job
  outputs, the seam that per-language publish add-ons will attach to.
- `RELEASING.md` documenting the two-step release and, more importantly, why each
  of its unusual parts is the way it is.

### Fixed
- The release guard waited for its own job. It polls every check run on the
  commit, and its own job is one of them, so it timed out after 15 minutes
  reporting `Still running: Prepare the release pull request`. `checkState` and
  `waitForChecks` now take `ignoreCheckRunIds`, and the guard passes its own
  run's job ids.
- The release workflows named their file-access object `io`, which is also the
  name `actions/github-script` injects into every `script:` block. The step died
  at parse time with `SyntaxError: Identifier 'io' has already been declared`,
  before running a line. It is now `fileIO`.
