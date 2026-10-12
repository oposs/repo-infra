# ri-release-rust-binaries

Upgrade notes, newest first. Each section says what a caller or
.github/repo-infra.json must change to take that version.

## v1

First version. Call it from release-build.yml as the catalogue shows, with `bin` naming the binary. It runs `make man`, so the repository carries the man pieces, and it builds seven archives that release_assets lists.
