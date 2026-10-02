# workflow-lib

Upgrade notes, newest first. Each section says what a caller or
.github/repo-infra.json must change to take that version.

## v8

No caller or config change. A comment in publish.js no longer names the removed key `release_build`; every file carries the new marker.

## v7

No caller change. release.js gained the header block; every file carries the new marker.
