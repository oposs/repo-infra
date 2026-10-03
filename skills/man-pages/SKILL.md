---
name: man-pages
description: Use when writing, restructuring or setting up a program's man page (docs/manual.md converted by pandoc to man/<name>.<section>), including section order, front matter, option lists, `make man`, shipping the page in a package, and a failing ci-man job such as "table wider than line length minus indentation". The voice of the manual comes from the writing-style skill.
---

# Man pages

A program's man page has one source, `docs/manual.md`. pandoc converts it to
roff at build time and `man/` is gitignored, so the page is a build artifact.
The `ri-ci-man` workflow proves on every pull request that the manual converts and that
roff can lay it out. GitHub renders the same file as the web version of the
manual.

## Front matter

```yaml
---
title: MYTOOL
section: 1
header: mytool manual
footer: mytool
date: 2026-09-23
---
```

`title` is the program name in capitals. `section` decides where the page
goes: the build writes `man/$(MAN_NAME).<section>`, and the Makefile has no
setting for it. Use `1` for a command a user runs and `8` for a daemon or an
administration tool. `make man` stops when the front matter has no `section:`.
`footer` carries no version, so a
release does not change the page. `date` is edited by hand when the manual
changes in substance. The build never sets it, so two builds of one source
produce one page.

## Section order

Level-1 headings follow `man-pages(7)` in this order. A section with nothing to
say is left out.

```text
NAME
SYNOPSIS
CONFIGURATION
DESCRIPTION
OPTIONS
EXIT STATUS
ENVIRONMENT
FILES
VERSIONS
STANDARDS
HISTORY
NOTES
CAVEATS
BUGS
EXAMPLES
SEE ALSO
```

A section the tool needs that the list lacks, for example KEYS, SIGNALS or
API, goes between OPTIONS and EXIT STATUS.

Level-1 headings are anchors. A README links to `docs/manual.md#options`, and
renaming the heading breaks that link. Treat a rename as a breaking change and
search the repository for the anchor before making one.

## Semantic newlines

Each sentence starts on a new line, and a long sentence breaks after a clause.
A diff then shows which sentence changed. Neither GitHub nor roff shows these
line breaks.

## Options and other term lists

Options, signals, keys and similar reference entries are a bullet list in which
every item opens with the term in a code span, followed directly by a colon:

```markdown
- `--listen <ip:port>`: Address and port to listen on.
- `-h, --help`: Print a usage summary and exit.
- `j, Down`: Scroll down one line.
- `SIGTERM`: Starts the drain.
```

`build/man-deflist.lua` turns such a list into a definition list with the term
in bold, so the page gets the hanging indent (`.TP`) man pages use for options,
while GitHub still renders a list. The filter converts a list only when every
item has this shape. Everything one item describes goes in one code span, both
the aliases of one option and two keys that share an entry. A space before the
colon, or two code spans such as `` `-h`, `--help` ``, does not match, and one
item that does not match leaves the whole list as bullets.

A Markdown table with a prose column does not fit a man page. roff warns
`table wider than line length minus indentation`, and `ri-ci-man` fails on that
warning. A table of short cells, such as a key and a one-word action, fits.

## Setting it up in a repository

1. Name the page and include the fragment:

   ```make
   MAN_NAME = mytool
   include build/man.mk
   ```

   The two lines may go anywhere in the Makefile. The fragment saves and
   restores `.DEFAULT_GOAL`, so a bare `make` still builds whatever the
   Makefile already builds by default, not the man page.

2. Ignore the generated page in `.gitignore`:

   ```text
   man/
   ```

3. Install the `man` and `man-lua` pieces and call `ri-ci-man` from `ci.yml`:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" apply --item man
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" apply --item man-lua
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" apply --item ri-ci-man
   ```

   They install `build/man.mk`, `build/man-deflist.lua` and
   `.github/workflows/ri-ci-man.yml`. Add the call to `ci.yml` and list its job
   in the `needs:` of `ci-passed`:

   ```yaml
   man:
     uses: ./.github/workflows/ri-ci-man.yml
     with:
       ref: ${{ inputs.ref }}
   ```

4. Packaging takes the page from the working tree after `make man`. For a
   `.deb` built by cargo-deb, the release job runs `make man` before
   `cargo deb`, and the assets list carries the page. The file name and the
   directory both follow `section`; a section 8 page is `man/mytool.8` in
   `usr/share/man/man8/`:

   ```toml
   [package.metadata.deb]
   assets = [
     ["target/release/mytool", "usr/bin/", "755"],
     ["man/mytool.1", "usr/share/man/man1/", "644"],
   ]
   ```

   A release tarball copies `man/mytool.1` next to the binary the same way.

5. Look at the page locally with `make man && man -l man/mytool.1`.

## Voice

The manual's voice is in the `writing-style` skill, section Manual. This skill
does not repeat it.
