# ri-release-nfpm

Upgrade notes, newest first. Each section says what a caller or
.github/repo-infra.json must change to take that version.

## v1

First version. It needs workflow-lib v9, whose nfpm.js carries its logic. Move the package tables of Cargo.toml into an nfpm config whose contents take their sources from STAGE and name the man pages with .gz, since the piece gzips them. The piece sets VERSION, SOURCE_DATE_EPOCH, MTIME, PACKAGER, TARGET, STAGE and ARCH; the packagers input sets any other dollar-brace name. Call the piece after ri-release-rust-binaries as the catalogue shows. The file names stay those of cargo-deb and cargo-generate-rpm, so release_assets does not change.
