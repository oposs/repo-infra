---
title: MDMOST
section: 1
header: mdmost manual
footer: mdmost
date: 2026-08-17
---

# NAME

mdmost - full-screen terminal pager for a single Markdown document

# SYNOPSIS

**mdmost** \[*OPTIONS*\] \[*FILE*\]

# DESCRIPTION

**mdmost** parses a Markdown document once and draws it as styled Unicode: tables
get real borders and negotiated column widths, fenced code is syntax-highlighted,
and Mermaid diagrams are laid out as box art rather than shown as source.

Rendering is a pure function of the document, the width, the theme and the
options. No layout decision is taken at parse time, so resizing the terminal
discards the canvas and renders again rather than patching what is on screen.
That is why everything reflows, and why the same table is drawn dense in a wide
terminal and spaced in a narrow one.

With no *FILE*, the document is read from standard input; the keyboard is then
read from */dev/tty*, so `cat notes.md | mdmost` stays interactive. When standard
output is not a terminal, `--render-once` is implied, so `mdmost doc.md | cat`
produces plain text rather than escape sequences.

# OPTIONS

- **`--render-once`** — Render one frame to standard output and exit. Needs no terminal.
  Truecolour goes to a terminal and plain text goes anywhere else, which is what makes
  it usable for scripting and snapshotting.

- **`--width N`** — Render the whole document at this width instead of the terminal's.

- **`--body-width N`** — Cap the prose body at N columns and centre it; `0` for no cap.

- **`--no-body-width`** — Let the body use the full terminal width.

- **`--theme NAME`** — The theme to start in.

- **`--icons`** — Use Nerd Font glyphs even if none appears to be installed.

- **`--no-icons`** — Use plain Unicode instead of Nerd Font glyphs, at the same display
  width.

- **`--mouse`** — Capture the mouse: the wheel scrolls, the scrollbar drags, clicks jump
  in the contents pane, and dragging over the document copies the Markdown source behind
  it.

- **`--toc`** — Start with the table-of-contents pane open.

- **`--config PATH`** — Read configuration from this file instead of the default.

- **`--licenses`** — Print the licences of the bundled syntax definitions and exit.

- **`-h`, `--help`** — Print help and exit.

- **`-V`, `--version`** — Print the version and exit.

There is no `--color` flag. The truecolour decision is made from whether standard
output is a terminal, which is the same question `--render-once` already answers.

# KEYS

Bindings are remappable; see `[keys]` under **CONFIGURATION**. The in-app help
overlay is generated from the same live binding table as this list, so the two
cannot drift apart, and the status bar always names the keys you have actually
bound rather than the defaults.

## Moving

- **`j`, `Down`** — Scroll down one line.

- **`k`, `Up`** — Scroll up one line.

- **`d`, `Ctrl-d`** — Scroll down half a screen.

- **`u`, `Ctrl-u`** — Scroll up half a screen.

- **`space`, `Ctrl-f`, `PgDn`** — Scroll down one screen.

- **`b`, `Ctrl-b`, `PgUp`** — Scroll up one screen.

- **`g`, `Home`** — Go to the top, and back to the left edge.

- **`G`, `End`** — Go to the bottom of the document.

- **`%`** — Jump N percent into the document, as in `50%`.

- **`Left`, `Right`** — Scroll content that is wider than the terminal, such as a wide
  table or a long code line. Neither is ever reflowed or mangled to fit.

