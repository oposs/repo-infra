# repo-infra

A Claude Code plugin that brings a repository's release, protection, CI and
documentation infrastructure up to the current standard, and reports how far
behind it has drifted when the standard moves.

Design: [`docs/superpowers/specs/2026-08-17-repo-infra-design.md`](docs/superpowers/specs/2026-08-17-repo-infra-design.md)

## Install

In Claude Code:

```
/plugin marketplace add oposs/claude-plugins
/plugin install repo-infra@oposs-plugins
```

## Use

In the repository to bring up to the standard:

```
/repo-infra:check
/repo-infra:apply
```

`check` reports each item of the standard as `ok`, `missing`, `outdated` or
`conflict` and never writes. `apply` writes the file items on a
`repo-infra/apply` branch and the repository settings through the GitHub API.

## Testing

`make test` is the ordinary gate: sub-second, no podman required. Changes to
`skills/repo-infra/assets/build/container.mk` or
`skills/repo-infra/assets/m4/repo-infra-container.m4` also need `make
test-container`, which builds a real container and runs those assets against
it (needs podman, takes minutes). It is the same suite the required CI job runs.
