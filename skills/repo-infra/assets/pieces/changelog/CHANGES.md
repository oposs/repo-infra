# changelog

Upgrade notes, newest first. Each section says what a caller or
.github/repo-infra.json must change to take that version.

## v6

No caller change. The check reads the pull request's labels when it runs,
not from the event, so a label added right after the pull request opened counts.

## v5

No caller change. The file gained the header block.
