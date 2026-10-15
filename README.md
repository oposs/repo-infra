# repo-infra

A Claude Code plugin that teaches an AI how these repositories are structured,
built, tested, reviewed and released, and gives it a toolbox for doing so. The
toolbox is a set of pieces (reusable workflows named `ri-*.yml`, build files)
and a catalogue that says what each piece is for. A repository calls the
workflows from short callers (`ci.yml`, `release-build.yml`,
`release-publish.yml`, `release-pr.yml`, `changelog.yml`, `ci-local.yml`) with
`uses: oposs/repo-infra/.github/workflows/<piece>.yml@v2`; each release of
repo-infra moves `v2`, so fixes arrive without a pull request. Build files are
installed by `/repo-infra:apply`, which also migrates a repository that still
copies the workflows.

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

`check` reports every installed build file as `current`, `outdated`, `edited` or
`unknown`, reports the v1 layout and every call of a repo-infra workflow that
does not read `@v2`, checks the callers against the workflows they call, checks
`.github/repo-infra.json`, and lists the administration items (default branch,
ruleset, label, Actions setting). It never writes. `apply` migrates a v1
repository in one commit named "Migrate to the repo-infra v2 layout", replaces
outdated build files on a `repo-infra/apply` branch, prints what the callers
must change, and stops. `apply --item <piece>` installs one build file, and
`apply --item <name>` writes one repository setting through the GitHub API.

A repository not yet in the fold is onboarded from the skill, which brings it
up to the full shape of the standard. It reads the repository, runs the shape
review of `skills/repo-infra/references/project-shape.md` first and presents one
work plan, picks pieces from `skills/repo-infra/references/catalogue.md`, writes
the callers that call them, installs the build files with `apply --item`, does
the rest of the plan and reviews the shape again
(`skills/repo-infra/references/onboarding.md`).

## Testing

`make test` is the ordinary gate: sub-second, no podman required. Changes to
`skills/repo-infra/assets/pieces/container/container.mk` or
`skills/repo-infra/assets/pieces/container-m4/repo-infra-container.m4` also need `make
test-container`, which builds a real container and runs those assets against
it (needs podman, takes minutes). It is the same suite the required CI job runs.
