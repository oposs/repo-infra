# repo-infra — the github-action ecosystem

Date: 2026-08-24
Extends: `2026-08-17-repo-infra-design.md` (the D-series)
Proved in: `oposs/mkp-builder#17`

This document adds one decision, D20, one ecosystem, one CI block, and one
revision of an existing block. It is the first case worked through the teach
path (`references/teaching-the-standard.md`) rather than improvised.

## The gap

`repo_infra check` in `oposs/mkp-builder` reported `detected nothing`. The
repository is a composite GitHub Action: `action.yml` plus a Python script, no
`pyproject.toml`, no test runner, no lock file. Every detection signal the
standard has is a *language's* signal, and this repository's product is not
written in a language — it is a manifest that GitHub itself executes.

The standard was **silent**, not in conflict. That is a gap in the standard, so
patching the repository or growing a variant asset was forbidden, and stage 1 of
the teach path — put the ruling to the user — applied.

## The ruling

> The GitHub action itself must bring some assets to test the action. repo-infra
> must know how to integrate this in an automated test for the action.

So the block executes the action, and repo-infra owns the *seam* rather than the
test. That settles the axis the question was about. What remained was the shape.

## D20 — the action repository brings the test; the standard brings the seam

**The seam is a reusable workflow at a fixed path.** repo-infra ships one
literal job:

    action-test:
      uses: ./.github/workflows/action-test.yml

and `.github/workflows/action-test.yml` is the project's own file, on the same
terms as the `Containerfile` under D17: documented, not shipped, not versioned,
not drift-checked. An action's real test is `uses: ./` with real inputs, and
repo-infra cannot know what inputs an action takes. It does not try. It knows a
path and a trigger, and nothing else.

**The path is fixed, not configurable.** A key in `.github/repo-infra.json`
would be one more thing per repository to get wrong, in exchange for not
renaming one file during a conversion. The rule deletes the question instead of
managing it. This also keeps the asset a literal file with no substitution
token, which the standard requires of every asset.

**A reusable workflow, not a project-owned composite action.** A composite
action collapses to one job on one runner, and `mkp-builder`'s test is four
independent jobs. A reusable workflow keeps them, keeps `uses: ./` at workflow
level where it is well defined, and reports each inner job as its own check
(`action-test / Test Input Validation`), so a failure names itself. The cost is
that a `uses:` job accepts no `runs-on`, `steps` or `timeout-minutes` — hence
the contract's requirement that the project sets its own timeouts.

**The block's other job is repo-infra's own.** `action-manifest` reads
`action.yml` and every workflow beside it, and fails on either half of a
mismatch between them:

- a workflow passing an input `action.yml` does not declare — GitHub prints
  `Unexpected input(s)` as a **warning**, drops the value, and carries on;
- a workflow omitting a `required: true` input — not enforced by the runner at
  all.

Both are silent, and a test that hits either is green while testing nothing.
This is not hypothetical: `mkp-builder`'s `test-with-all-inputs` job passed
`cmk-min-version` and `cmk-packaged-version` against an `action.yml` declaring
`version-min-required` and `version-packaged`. It had been green that way
across releases. The very first run of this job failed on exactly those two
lines.

**The manifest is `action.yml`.** GitHub also accepts `action.yaml`; the
standard does not. One shape per ecosystem, and a repository spelling it the
other way renames the file — the same terms as every other settled decision.

**Being an action is not a claim about a language.** The ecosystem stacks:
`action.yml` plus `pyproject.toml` assembles `ci-github-action` and `ci-python`
into one `ci.yml`, exactly as D2 intended.

**No version file.** Actions are tag-versioned, and a consumer pins `@v2`, so
`version_files` is empty and `moving_major_tag` carries the release semantics.

### The consequence for `check`

A missing `action-test.yml` is not a gap that degrades gracefully. GitHub
rejects a `uses:` that points at a file which does not exist, and it rejects the
*whole workflow* — so every job stops reporting and the required check hangs
Pending forever. `check` therefore reports it as its own item, in state
`conflict`: it needs attention, and there is nothing for `apply` to install,
because only a human can write that file.

`conflict` is load-bearing rather than cosmetic. `apply` is handed only
`missing` and `outdated` items, so a `conflict` can never be mistaken for
something the tool will fix on the next run.

### The revision D20 forced: ci-python v2

The validator is a script inside a shipped asset, so D19 says to test it by
**running** it, and running it needs PyYAML — which repo-infra's own CI did not
install, because `ci-python` installed `pytest` and nothing else.

Rather than special-case repo-infra, `ci-python` gains the step
`ci-checkmk-plugin` already had: install `requirements-dev.txt` if it exists.
What a suite needs to import is a toolchain concern and the project declares it
(D15); a repository without the file gets a no-op. This closes a gap that would
have blocked the next Python repository needing any test dependency at all.

## What was considered and rejected

- **Static validation only, no execution.** Cheap and universal, and it would
  have caught the `mkp-builder` defect. Rejected on the user's ruling: an action
  that is never run is not tested, and D19 says the same about assets.
- **`actionlint` instead of a purpose-built validator.** It does check local
  action inputs, and it is maintained by someone else, which is the better trade
  in principle. Rejected because it also runs shellcheck over every `run:` block
  on a runner that has shellcheck installed, so adopting it makes the required
  check fail on findings unrelated to the contract — a large behavioural change
  smuggled in as a dependency. Worth revisiting behind an explicit rule set.
- **A project-owned composite action as the seam.** See above: one job, one
  runner, and local `uses:` references inside a composite action are a known
  sharp edge.
- **Declaring the test path in `.github/repo-infra.json`.** A knob that manages
  variation the standard can simply remove.
- **Checking the seam's trigger in `check`.** `on: [workflow_call]` and nothing
  else is a real contract point, and a second trigger silently doubles every
  run. Verifying it means parsing YAML, and `repo_infra` has no runtime
  dependencies today. Left to the contract and to review; the presence check is
  implemented, the trigger check is not.

## What is not covered

- **A nested local action** (`uses: ./tools/thing`) is not checked against the
  root action's inputs — it is a different action with its own manifest. A
  repository shipping several actions gets validation for the root one only.
- **JavaScript and Docker actions** are untested by this work. Nothing in the
  block assumes composite, but `mkp-builder` is the only consumer so far, and
  provenance is not verification.
