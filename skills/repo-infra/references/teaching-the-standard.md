# Teaching the standard

repo-infra carries the standard. You do the conversion. When a repository has a
shape the standard has no answer for, the answer is never to patch the
repository around it and never to grow a variant asset for it — it is to teach
the standard, then convert.

## When this applies

Two ways a gap shows up.

**`check` sees it.** No ecosystem matched at all. The report says so and sends
you here. An *ambiguous* detection signal is not this: it is a question about
this repository, not a gap in the standard, and it is answered by recording the
answer in the repository's own `.github/repo-infra.json` (see
`references/conventions.md`), never by a pull request against repo-infra.

**You see it.** Before applying anything, read the repository's real build, test
and release setup and compare it to what you are about to install. A gap is one
of two things:

- the standard is **silent** — it has no rule for something this repository
  needs;
- the standard **conflicts** — adopting it would break something that currently
  works.

A repository that merely differs from a settled decision is not a gap. D1
(`main`), D5 and D6 (`CHANGES.md` and its format) and every other numbered
decision are settled: the repository migrates, and you do not ask. Ask only when
a settled decision conflicts *severely*, and say why that one is not routine.

## The three stages

**1. Question.** Put it to the user: what the standard does not cover, what this
repository does instead, what the options are. This is a ruling about the
standard, not about this repository. Do not decide it yourself and do not
present it as "may I add X".

**2. Prove.** Work the answer out in the repository's own tree and get it green
in CI. Nothing is upstreamed on reasoning alone. A thing copied from a
repository where it works is a hypothesis until it runs against a real consumer
— this project has already paid for that lesson once.

**3. Upstream.** The proven answer becomes a pull request against repo-infra,
sized to the change:

| Change | What must exist |
|---|---|
| A block fix — a wrong cache directory, a mistyped target | Changed asset + a test |
| A new seam, a new ecosystem, a new rule | Numbered decision in the design doc + asset + test |

The repository's own conversion pull request merges **after** that has shipped
and the plugin has been updated. So no repository carries a shape the standard
does not have, and nothing is standardised that has not been shown to run.

## The threshold you will hit most often

D16: a project builds natively while it needs nothing beyond the runner's
default image plus its ecosystem toolchain. The moment it needs an extra system
package, the standard can no longer build it — and that starts a conversation,
it does not decide the outcome. Containerizing is the expected answer, but the
project dropping the dependency is a real alternative, and so is something
nobody has thought of.

If containerizing is the answer, what repo-infra ships for it is the
`container-test` build asset (`build/container-test.mk`, defining `container:`
and `test:`) -- installed by naming it in the repository's own `build` list in
`.github/repo-infra.json` (`references/conventions.md`). Nothing installs it
automatically; it is a decision, not a detection.

What is never available is carrying on natively while installing packages from
CI. If you find yourself wanting a place to list apt packages, you have hit the
threshold; go to stage 1.
