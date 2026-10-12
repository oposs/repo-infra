# ri-release-source-tarball

Upgrade notes, newest first. Each section says what a caller or
.github/repo-infra.json must change to take that version.

## v2

No caller change. The header names the artifact the piece uploads,
`release-asset-source`; v1 named it `release-asset-source-tarball`.

## v1

First version as a piece. It was the `release-source-tarball` job of the assembled release-build.yml. Call it as the catalogue shows.
