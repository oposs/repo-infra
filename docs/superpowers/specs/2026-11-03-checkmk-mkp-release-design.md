# Checkmk plugins: the MKP of the release

Date: 2026-11-03
Status: on the branch `checkmk-release-mkp`; the proof run with a
`cmk-oposs_*` repository is open
Decision: D37 (a release-build piece for Checkmk plugins; changes nothing in
the release flow of D28 and nothing in `ri-ci-checkmk-plugin` but its Python
version)

## Why

A Checkmk plugin ships as an MKP. Fourteen `oposs/cmk-oposs_*` repositories
release today with a hand-made `release.yml` started by `workflow_dispatch`:
it computes the version from the tags, rewrites `CHANGES.md`, pushes to `main`
and the tag, runs `oposs/mkp-builder@v2` with the version and attaches the
`.mkp`. Under D28 the release build runs before the merge and hands its files
to the publish as artifacts named `release-asset-*`; no piece built an MKP, so
`ri-ci-checkmk-plugin` covered the CI of such a repository but its release had
no path in the standard. The owner ruled on 2026-11-03 that the standard gets a
release piece for it.

## Decision

D37: `ri-release-mkp` builds the MKP of the release. Its interface is the one
of `ri-release-source-tarball`: `version` and `ref` from `release-build.yml`,
`repository` as every piece has it (D33), `contents: read`.

The job checks out `ref`, runs `oposs/mkp-builder@v2` with `version`, and
uploads the package as the artifact `release-asset-mkp`, which the caller
lists as `*.mkp` in `release_assets`. `.mkp-builder.ini` supplies everything
else the package carries: name, title, author, the Checkmk versions.

The piece finds the package itself rather than reading mkp-builder's
`package-file` output. mkp-builder sets that output to the first `*.mkp` a
recursive `find` returns, so a package committed to the repository could be
uploaded in place of the one just built. The piece takes the `*.mkp` files in
the source root, where mkp-builder writes, and refuses none, more than one, and
a name other than `<name>-<version>.mkp` with the release version.

A version the plugin carries in its own code, such as `__version__` in the
agent plugin, is a `version_files` entry of `.github/repo-infra.json`
(`references/onboarding.md`). The release pull request rewrites it, so the
commit the piece builds already holds the version; the piece does not edit the
checkout.

With this decision `ri-ci-checkmk-plugin` runs `cmk-lint` and `cmk-test` on
Python 3.12 instead of 3.11. Checkmk 2.3 runs plugin code on 3.12
(`PYTHON_VERSION = "3.12.13"` in its `package_versions.bzl`), and on 3.11 the
jobs passed a plugin importing `distutils`, `imp` or `asynchat`, which 3.12
removed, and refused syntax only 3.12 accepts.

## Rejected

- Reading `package-file`. See above: it can name a committed package.
- Passing `output-dir` to mkp-builder so the package lands in an empty folder.
  The stray committed package would still be in the repository and in the
  next CI package build; refusing it names the problem.
- Rewriting `__version__` in the piece, as the hand-made `release.yml` does
  with `sed`. That edit is not committed, so the tagged source would carry a
  different version than the package; `version_files` writes it into the
  release commit.

## Tests

`tests/test_release_mkp.py` checks the inputs, the permission, the version
passed to mkp-builder and the upload, and runs the step that locates the
package with bash: one package moves to the artifact folder; none, two, one
with another version and one with a blank in its name stop the job with their
message; a package in a subfolder is ignored. `tests/test_ci_pieces.py` checks
that both setup steps of `ri-ci-checkmk-plugin` name 3.12.

## Proof

Open: the release build of a `cmk-oposs_*` repository against
`@checkmk-release-mkp`.
