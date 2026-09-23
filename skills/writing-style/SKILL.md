---
name: writing-style
description: House style for any words that go into a repo file. Load it before drafting, editing, shortening or rewriting such text, even when the request looks small or is mostly about a code fix. Typical requests are a changelog or CHANGES.md entry for a fix or feature; a bloated README or install section trimmed down to the commands; a docs/manual.md that should read like a man page instead of a sales pitch, full of "simply", "ideal for", "you can" and self-praise; rationale moved into maintainer notes; a commit message or a code comment that explains why; em dashes, rhetorical contrasts and a generic AI tone removed. Not for questions about how code, CI or regexes behave when no prose is being written.
---

# Writing style

The prose in a repository has several readers, and each kind of text serves a
different one. A manual answers what a program does; a code comment answers why
the code is the way it is. Find the kind of text first, apply its section, and
apply the rules for every kind on top.

## Rules for every kind

- No em dashes, anywhere: not in prose, not in lists, not in examples. Use a
  full stop, a comma, a colon or parentheses.
- Option and term lists put the term in a code span followed by a colon:

  ```markdown
  - `--listen <ip:port>`: Address and port to listen on.
  - `-h, --help`: Print help and exit.
  - `SIGTERM`: Starts the drain.
  ```

  Several names for one thing share a single code span, as `-h, --help` does.
  The man page build turns a list into option paragraphs only when every item
  opens with one code span directly followed by the colon; a single item
  written `` `-h`, `--help`: `` leaves the whole list as plain bullets.

- No emoji in headings.
- No rhetorical contrast used for emphasis, such as "this is a pager, not a
  viewer". Say what the thing is.
- No lists of three made for rhythm. A list has as many items as there are
  things to say.
- Write "for example", never `e.g.`.
- Singular "they" for a person whose gender is unknown.
- Subsection headings are in sentence case ("Layout rules").

## Manual

`docs/manual.md` is a reference page. `man-pages(7)` and `groff_man_style(7)`
are its authorities, and its reader wants to know what the program does.

- Present tense and third person. No "you", no "we".
- Facts only: what the program does, what it accepts, what it prints.
- No rationale. A sentence that explains why a design is the way it is moves
  to `docs/maintainer-notes.md`.
- No self-praise ("so the two cannot drift apart") and no justification
  clauses ("which is what makes it usable for scripting").
- Headings are noun phrases: "Layout rules" instead of "Rules worth knowing",
  "Symptoms of missing glyphs" instead of "What goes wrong without it".
- The `man-pages` skill covers structure and the build.

### Before and after

From the mdmost manual, commit `fef7f53`. Before:

```markdown
**mdmost** parses a Markdown document once and draws it as styled Unicode: tables
get real borders and negotiated column widths, fenced code is syntax-highlighted,
and Mermaid diagrams are laid out as box art rather than shown as source.

Bindings are remappable; see `[keys]` under **CONFIGURATION**. The in-app help
overlay is generated from the same live binding table as this list, so the two
cannot drift apart, and the status bar always names the keys you have actually
bound rather than the defaults.
```

After:

```markdown
**mdmost** renders one Markdown document in the terminal. Tables get borders and
negotiated column widths, fenced code is syntax-highlighted, and Mermaid diagrams
are drawn as box art instead of shown as source.

Bindings are remappable; see `[keys]` under **CONFIGURATION**. The help overlay
and the status bar name the bindings in effect rather than the defaults.
```

"Parses a Markdown document once" describes the implementation and is gone.
"So the two cannot drift apart" praises the build and is gone. "The keys you
have actually bound" became a third-person statement.

## README

The README keeps its own voice, and second person is fine there.

- No self-congratulation.
- An install section is the commands to run, with at most a sentence per
  route. Why a step is needed, and how older versions of a tool behave, goes
  to maintainer notes.

## Maintainer notes

`docs/maintainer-notes.md` carries the rationale the manual and the README
leave out. Rationale cut from either moves here and is never deleted, so a
later change to a default is a decision rather than an accident. Explanation
belongs here, and it follows the rule for code comments below.

## Changelog entries

Readers of `CHANGES.md` are users and administrators. They do not know the
implementation language, and implementation detail is lost on them.

- Lead with what the reader observed. Name the thing they saw: text on a
  screen, a field showing the wrong value, errors filling a log, a service that
  stopped answering. If the defect produced output the reader could see, quote
  it.
- Three sentences at most. An entry that needs more is two entries, split by
  effect. Two entries with one cause and one effect become one.
- Keep names the reader can act on: issue tags, service names, journal tags,
  config keys, UI field labels, version pins. Drop names that exist only in the
  source, such as functions, modules and frameworks the reader never types.
- Cover every behaviour change, including a second place that changed along
  with the headline one.
- The cause analysis belongs in the commit message. The entry gives the effect.
- An issue tag goes at the end, in round brackets: `(#2)`, `(AGW4#333)`.
- The most important entry comes first.
- No release headers; the release workflow writes them.

## Code comments and commit messages

Here the reader is a developer asking why. Every explanation names the concrete
thing that went wrong: the version, the file, the symptom.

```sh
# And no || true. Swallowing the failure is what turned a broken step into a broken
# release: v0.1.1 was tagged with Cargo.toml at 0.1.1 and Cargo.lock still at 0.1.0, and
# the publish failed 6 minutes later.
```

A comment that says "for robustness" or "to be safe" names nothing, and the
next reader cannot tell whether it still applies.
