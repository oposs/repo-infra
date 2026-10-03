# repo-infra

A Claude Code plugin that teaches an AI how these repositories are structured,
built, tested, reviewed and released, and gives it a toolbox for doing so. The
toolbox is a set of pieces (reusable workflows named `ri-*.yml`, the release
flow files, a workflow library, build fragments) that a repository copies 1:1,
and a catalogue that says what each piece is for. The repository owns the short
callers (`ci.yml`, `release-build.yml`, `release-publish.yml`, `ci-local.yml`)
that use them.

Design: [`docs/superpowers/specs/2026-10-02-pieces-and-callers-design.md`](docs/superpowers/specs/2026-10-02-pieces-and-callers-design.md)
(the original standard is in
[`2026-08-17-repo-infra-design.md`](docs/superpowers/specs/2026-08-17-repo-infra-design.md))

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

`check` reports every installed piece as `current`, `outdated`, `edited` or
`unknown`, checks the callers against the pieces they call, checks
`.github/repo-infra.json`, and lists the administration items (default branch,
ruleset, label, Actions setting). It never writes. `apply` replaces outdated
pieces on a `repo-infra/apply` branch, one commit each, prints the upgrade notes
and what the callers must change, and stops. `apply --item <piece>` installs one
piece, and `apply --item <name>` writes one repository setting through the
GitHub API.

A repository not yet in the fold is onboarded from the skill: it reads the
repository, picks pieces from `skills/repo-infra/references/catalogue.md`,
copies them with `apply --item` and writes the callers
(`skills/repo-infra/references/onboarding.md`).

## Testing

`make test` is the ordinary gate: sub-second, no podman required. Changes to
`skills/repo-infra/assets/pieces/container/container.mk` or
`skills/repo-infra/assets/pieces/container-m4/repo-infra-container.m4` also need `make
test-container`, which builds a real container and runs those assets against
it (needs podman, takes minutes). It is the same suite the required CI job runs.
