# dependabot

Upgrade notes, newest first. Each section says what a caller or
.github/repo-infra.json must change to take that version.

## v4

No caller change. An ecosystem's entry can cover directories besides `/`:
list them under the `dependabot` key of `.github/repo-infra.json`, for example
`"dependabot": {"cargo": ["/tools/gen"]}`, and the entry reads `directories:`
with `/` first. Without the key every entry stays as v3 wrote it.

## v3

No caller change. The file gains one weekly entry for each ecosystem the
callers' CI pieces build, for example `cargo` for `ri-ci-rust`. Every entry
carries the labels `dependencies` and `no-changelog`.

## v2

No caller change. The file gained the header block.
