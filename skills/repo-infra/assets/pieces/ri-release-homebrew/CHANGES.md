# ri-release-homebrew

Upgrade notes, newest first. Each section says what a caller or
.github/repo-infra.json must change to take that version.

## v1

First version. It needs workflow-lib v9, whose homebrew.js carries its formula steps. The formula follows the template in references/project-shape.md: each url line directly above its sha256 line, the four sha256 marker comments, and the BOTTLE markers. Remove any other job that writes release-files, and call the piece after ri-release-rust-binaries as the catalogue shows.
