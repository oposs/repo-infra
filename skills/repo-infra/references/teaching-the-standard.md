# Teaching the standard

repo-infra carries the standard. You do the conversion. When a repository has a
need no piece fits, the answer is never to patch the repository around it and
never to grow a variant of a piece for it. The answer is to teach the standard,
then convert.

## When this applies

The trigger is "no piece fits". While mapping the repository's needs to the
catalogue (`references/onboarding.md`), one need has no piece, or the only piece
that comes close would have to be edited. That is a gap. A question about this
repository, such as which of two lockfiles is authoritative, is not: it is
answered with the user and recorded in the callers, never by a pull request
against repo-infra.

A gap is one of two things:

- the standard is **silent**: no piece does something this repository needs;
- the standard **conflicts**: adopting a piece would break something that
  currently works.

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
repository where it works is a hypothesis until it runs against a real consumer.
This project has already paid for that lesson once.

**3. Upstream.** The proven answer becomes a pull request against repo-infra,
sized to the change:

| Change | What must exist |
|---|---|
| A fix to a piece (a wrong cache directory, a mistyped target) | The changed piece at a new version, its `## vN` section in the piece's `CHANGES.md`, `make generations`, `make catalogue` and a test |
| A new piece, a new rule | Numbered decision in the design doc, plus everything a new piece needs (below) |

A new piece needs:

- a folder under `skills/repo-infra/assets/pieces/<name>/` holding the file;
- the marker `# repo-infra: <name> v1` on the first comment line;
- the header block after the marker: `Purpose`, `Choose` and `Supplies`;
  `Pieces` naming the pieces it needs (the only way `apply` knows to install
  them with it); `Produces` for the assets it makes; and `Call`, the caller job,
  for every workflow a caller calls;
- a `CHANGES.md` in that folder with a `## v1` section: the upgrade notes `apply`
  prints, saying what a caller or the config must change;
- an entry in `assets/manifest.json` giving the install path, the group and
  whether every repository carries it;
- `make generations`, which records the hash of the new version, and `make
  catalogue`, which regenerates `references/catalogue.md`;
- tests that run the steps of the piece, because nothing is standardised that
  has not been shown to run.

The repository's own conversion pull request merges **after** that has shipped
and the plugin has been updated. So no repository carries a shape the standard
does not have, and nothing is standardised that has not been shown to run.

## The threshold you will hit most often

D16: a project builds natively while it needs nothing beyond the runner's
default image plus its ecosystem toolchain. The moment it needs an extra system
package, the standard can no longer build it, and that starts a conversation,
it does not decide the outcome. Containerizing is the expected answer, but the
project dropping the dependency is a real alternative, and so is something
nobody has thought of.

If containerizing is the answer, what repo-infra ships for it is a pair of
pieces: `container-m4` (`m4/repo-infra-container.m4`, the `--disable-container`
switch) and `container` (`build/container.mk`, the driver targets). Install them
with `apply --item container-m4` and `apply --item container`, and write the
`Containerfile` the contract in `references/conventions.md` describes. Nothing
installs them automatically; it is a decision.

What is never available is carrying on natively while installing packages from
CI. If you find yourself wanting a place to list apt packages, you have hit the
threshold; go to stage 1.
