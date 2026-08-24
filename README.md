# repo-infra

A Claude Code plugin that brings a repository's release, protection, CI and
documentation infrastructure up to the current standard — and reports how far
behind it has drifted when the standard moves.

Design: [`docs/superpowers/specs/2026-08-17-repo-infra-design.md`](docs/superpowers/specs/2026-08-17-repo-infra-design.md)

## Status

Under construction. The release core is being built and proven here first; the
plugin that installs it elsewhere comes next.

## Testing

`make test` is the ordinary gate: sub-second, no podman required. Changes to
`skills/repo-infra/assets/build/container.mk` or
`skills/repo-infra/assets/m4/repo-infra-container.m4` also need `make
test-container`, which builds a real container and runs those assets against
it (needs podman, takes minutes) — the same suite the required CI job runs.
