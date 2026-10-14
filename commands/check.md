---
description: Report how far this repository has drifted from the infrastructure standard
---

The command has two parts: the script's report and the shape review. Run the
script and read its report to the user:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" check
```

The report has four sections.

- `pieces`: every installed build file, by its bytes against the published
  versions, the core build files that are missing, and the files of the v1
  layout (below). A core workflow piece that no workflow calls reads `missing`:
  every repository calls it, and the finding names the `uses:` line.
- `callers`: `ci.yml`, `release-build.yml`, `release-publish.yml` and the
  workflows they call, checked against the pieces they call (inputs, secrets,
  `needs:` lists, the `if:` and `with:` of `finalize`, token permissions,
  `ref`), the triggers and concurrency group of `ci.yml` and
  `release-publish.yml`, and the calls of repo-infra workflows (below). A
  workflow its reader cannot follow (flow mappings, anchors, text that is not
  UTF-8) is reported only when it is one of those three, is called by a
  workflow or by such a reported file, or carries a piece marker. Any other
  such workflow is skipped. Each workflow of the repository that is not a
  piece is also compared with the action pins of the pieces and of the
  repository's other workflows: one that pins an action at an older major than
  any of them (`actions/upload-artifact@v4` against `v7`) reads `outdated` and
  names where the newer pin is, because dependabot would raise every workflow
  to one version and downgrade the files already past it. SHA and branch pins
  are not compared.
- `config`: `.github/repo-infra.json`.
- `administration`: the default branch, the ruleset, the label and the Actions
  setting, read from GitHub.

Every call of a repo-infra workflow must read
`uses: oposs/repo-infra/.github/workflows/<piece>.yml@v2`, with each secret passed
by name. `check` reports another ref (`@main`, `@v2.0.0`) or none, `secrets:
inherit` on such a call, a file repo-infra does not ship, an input the workflow
does not declare, and a required input or secret left out. It reads the workflows
from the installed plugin. Calls of other repositories' workflows are not
reviewed. repo-infra itself calls its pieces through `./`.

The v1 layout is reported in `pieces` as `outdated`, each finding saying to run
apply: a copy of a workflow piece (`ri-*.yml`), `.github/workflows/lib/`,
`ri-ci-lib.yml`, and the old `changelog.yml` and `release-pr.yml` that still
carry a piece marker. A job that calls a copy through `./` is a finding in
`callers`. Tell the user to run `/repo-infra:apply`, which migrates in one
commit; do not edit the copies.

A build file is in one of these states:

- `current`: the latest version, unedited.
- `outdated`: an older published version, unedited. `apply` replaces it.
- `edited`: the bytes match no published version. When the marker claims an
  older version or none, `apply` stops with the files for a hand merge. When it
  claims a newer version, the plugin is out of date. When it claims the current
  version, as every finished merge leaves it, `apply` leaves the file alone: move
  the change into a caller, delete the file and run `apply --item <piece>`, which
  installs the published file again.
- `unknown`: the marker names a piece repo-infra does not ship.
- `missing`: a piece every repository carries, or one an installed piece needs,
  is not installed.

Callers rows read `missing`, `outdated`, `problem` or `conflict`, config rows
`missing`, `problem` or `conflict`; administration
rows read `ok`, `missing`, `outdated` or `conflict`.

Report the output as it is. Do not summarise a `conflict` into "needs updating":
that state says what breaks. Do not act on an `edited` piece before asking the
user: the edit may be deliberate, and moving it into a caller is a decision for
them. A repository that has no pieces yet gets onboarded: `references/onboarding.md`
in the skill has the procedure.

The script exits 1 when any row needs attention and 0 otherwise. That exit
code is the result of the script, so trust it over guessing from the text.

## The shape review

After the report, review what the project contains. The review is a separate
part of the report and does not change the exit code.

1. Read `references/project-shape.md` in the skill.
2. State which triggers apply, each with its evidence, for example "has a
   command line: `src/main.rs` parses arguments with clap".
3. Give every rule of those triggers one state: `met`, `gap` with what is
   missing, `excepted` with the reason recorded under `exceptions` in
   `.github/repo-infra.json`, or `does not apply` with the kind of program its
   `Requires:` names, which needs no exception.
4. List the exceptions whose id matches no rule, and the piece inputs that lack
   their paired exceptions. Today that is `targets` of
   `ri-release-rust-binaries`, paired by the table under "Exceptions" in
   `references/project-shape.md` (D34).

Report a gap; do not close it from here. Onboarding runs this review before it
writes anything and turns every gap into an item of its work plan
(`references/onboarding.md`).
