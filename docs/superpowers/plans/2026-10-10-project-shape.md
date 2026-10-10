# Project shape (D32) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** repo-infra states what a released project contains, reviews it in `/repo-infra:check`, and ships three release pieces for Rust programs, proven in mtuspy before they are upstreamed; mtuspy becomes the reference example.

**Architecture:** Phase A adds `references/project-shape.md`, the `exceptions` config key and the shape review to the commands, and can be released alone. Phase B proves the three release workflows as local files in mtuspy against a baseline run of its unchanged build, and releases mtuspy through them. Phase C copies the proven files into repo-infra as `ri-release-rust-binaries`, `ri-release-nfpm` and `ri-release-homebrew`, with tests that run their steps. Phase D puts mtuspy on the pieces with its full shape and records it under `references/examples/mtuspy/`. Phase E lists the later conversions.

**Tech Stack:** Python 3.11 standard library (scripts), pytest + PyYAML (tests), GitHub Actions reusable workflows, bash and awk in workflow steps, nfpm 2.47.0, cross 0.2.5, Homebrew, podman for container tests, ansidrama for the demo.

**Spec:** `docs/superpowers/specs/2026-10-10-project-shape-design.md`. Read it before Task 1. Every section of it maps to a task below (see "Self-review" at the end).

## Global Constraints

- Scripts under `skills/repo-infra/scripts/repo_infra/` use the Python standard library only. Tests may use PyYAML.
- "The LLM judges the shape; the script measures pieces." No script detects the kind of project, judges a README or interprets the exceptions.
- "Every rule applies unless an exception says why not." Exceptions live in `.github/repo-infra.json`, one reason per rule id.
- The script "accepts the key and reports a `problem` when the value is not an object whose values are non-empty strings. It does not know the rule ids."
- "The script's exit code stays the result of the script."
- "A piece's v1 holds only what its proving consumer runs." No `extra_paths`, no `prepare`, no `check`, no `skip_targets`, no `man` input in any v1.
- "The archive is the contract between the release pieces. Only the binaries piece knows the language."
- In all three pieces, `<bin>` is the `bin` input; "the owner and repository in every URL come from `github.repository`".
- nfpm is pinned to `2.47.0` with SHA256 `0660ca602b2d2d2ae4781a06c692b3eeb9d437ffea05b831d76e41f4a3188783` (`nfpm_2.47.0_Linux_x86_64.tar.gz`, checked against goreleaser's `checksums.txt` and a download on 2026-10-10; Smalti's Makefile pins the same pair). cross stays at `0.2.5`, as in `ri-ci-rust-musl`.
- Package file names stay `<bin>_<version>-1_<arch>.deb` and `<bin>-<version>-1.<arch>.rpm`, so `release_assets` does not change.
- Action versions in every piece match the manifest `actions` map (`actions/checkout@v7`, `actions/upload-artifact@v7`, `actions/download-artifact@v8`). `dtolnay/rust-toolchain@stable` and `Homebrew/actions/setup-homebrew@main` stay branch references.
- No em dash in any shipped file (`tests/test_no_em_dash.py`), in this plan or in any file written for mtuspy. Write "for example", never `e.g.`. Load the `writing-style` skill before writing prose, comments, CHANGES entries or commit messages.
- `make check` (ruff, pytest, node lib tests) is green at the end of every repo-infra task. Builds and tests use at most 4 cores: `cargo build -j4`, no `pytest -n` above 4. `make test-container` runs under `systemd-run --user --scope -p MemoryMax=4G -- ...`. Pass `timeout: 600000` to every long command.
- Containers run with `podman`, never docker. Temporary data goes to `/scratch/oetiker/claude-tmp/claude-1003/project-shape/` (called `$S` below), never `/tmp`.
- Every commit ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Pull request bodies end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- Outward-facing steps are marked **[outward]**. The owner has authorised mtuspy releases for this work. Merging pull requests in oposs/repo-infra is standing authority from the owner (subject to the auto-mode classifier, which may still ask). Every merge in mtuspy, every repo-infra release, and everything in another repository (settings or variables anywhere) is marked **[ask the owner]** and waits for the owner's OK in this session.

## Decisions this plan takes where the spec is silent

The executor implements these. The owner may veto one before Task 1.

- **P1. The local copies in mtuspy are named without the `ri-` prefix** (`release-rust-binaries.yml`, `release-nfpm.yml`, `release-homebrew.yml`). With the piece's own file name and no marker, `apply --item` in Phase D would find an `edited` file and stop for a hand merge.
- **P2. Each local copy opens with a two-line comment where the piece will carry its marker and header.** Phase C replaces exactly those two lines; every other byte is the proven one, and a test step compares them.
- **P3. Shell inputs reach scripts through `env:`, never as `${{ }}` inside `run:`.** The tests then run the shipped step text with plain environment variables, and an input cannot inject shell.
- **P4. The nfpm step is Python (`shell: python3 -I {0}`).** It parses the `packagers` JSON, refuses a shadowing key, expands `${VAR}` across the whole config, runs nfpm and reads every package back. `-I` keeps a `json.py` in the checkout from being imported. The expansion covers comments too, so a config comment never writes a dollar-brace name.
- **P5. The man pages travel as the artifact `man-pages`.** It is not `release-asset-*`, so the release does not attach it.
- **P6. The Homebrew trust guard reads the major version** (`brew --version`) instead of `brew trust ... || true`, so a failing `brew trust` on Homebrew 6 fails the leg.
- **P7. The local-tap rewrite of the formula is one awk program** that writes the formula through `-v out=`, so its `::error::` lines reach the log on stdout.
- **P8. The comparison of packages uses `facts.sh`** (Task 5), which writes file modes and paths, the control fields and the postinst of one package. Version, sizes and dates are left out, so cargo-deb's 0.1.3 packages and nfpm's 0.0.0 packages compare. `tests/fixtures/nfpm/` keeps the baseline facts and the accepted differences.
- **P9. `project-shape.md` names the new pieces only once they ship** (Task 12). Released alone in Phase A, it names no piece that does not exist.
- **P10. mtuspy's `GITEA_PACKAGE_USER` must become a repository variable.** Today it is a repository *secret* (`gh api repos/oetiker/mtuspy/actions/secrets` lists `GITEA_PACKAGE_TOKEN` and `GITEA_PACKAGE_USER`; `.../actions/variables` lists none), and `ri-publish-gitea` reads `vars.GITEA_PACKAGE_USER`. The first publish would fail with the missing-credential message. Task 8 sets the variable, with the owner.

## Review Focus

1. A formula whose mac `url` line is separated from its `sha256` line (a blank line, a comment, a reordered block) must fail the bottle leg naming the marker; it must not let `brew` fetch the GitHub url, which answers 404 before the release exists. Test in Task 11.
2. A malformed `packagers` input (not JSON, `{"deb": "x"}`, a key other than deb or rpm) must fail the packaging job with one `::error::` line naming the input, not a traceback. Test in Task 10.
3. A `release-asset-<target>` artifact holding no archive or two, or an archive whose root is not one folder, must fail naming the archive instead of packaging the wrong files. Test in Task 10.
4. A formula still carrying the previous release's bottle block must come out with this release's `root_url` and bottles only. Test in Task 11.
5. An `exceptions` value with a whitespace-only reason must be a `problem` like an empty one. Test in Task 1.

---

## File structure

repo-infra:

| File | Change | Responsibility |
|---|---|---|
| `skills/repo-infra/references/project-shape.md` | create (Task 2), amend (Task 12) | triggers, rules, exceptions, badges, install snippets, archive layout, formula template |
| `skills/repo-infra/scripts/repo_infra/check.py` | modify (Task 1) | accept `exceptions`, rename message for `skip` |
| `commands/check.md`, `commands/apply.md` | modify (Task 3) | the shape review; apply starts with the script |
| `skills/repo-infra/SKILL.md`, `references/onboarding.md`, `references/release-flow.md`, `references/conventions.md` | modify (Task 3) | "run the script until it exits 0", onboarding review step, pointer to the snippets, amended config rule, D32 |
| `skills/repo-infra/assets/pieces/ri-release-rust-binaries/` | create (Task 9) | the binaries piece |
| `skills/repo-infra/assets/pieces/ri-release-nfpm/` | create (Task 10) | the packaging piece |
| `skills/repo-infra/assets/pieces/ri-release-homebrew/` | create (Task 11) | the bottles and formula piece |
| `skills/repo-infra/assets/manifest.json`, `generations.json`, `references/catalogue.md` | modify (Tasks 9 to 11) | registration |
| `skills/repo-infra/references/examples/mtuspy/` | create (Task 16) | the reference example |
| `tests/test_check.py`, `tests/test_skill.py` | modify | config and wording tests |
| `tests/test_project_shape.py` | create (Task 2) | rule structure, snippets, template |
| `tests/test_release_rust_binaries.py`, `tests/test_release_nfpm.py`, `tests/test_release_homebrew.py` | create (Tasks 9 to 11) | run the pieces' steps |
| `tests/fixtures/nfpm/`, `tests/fixtures/homebrew/` | create (Tasks 10, 11) | config, scripts, baseline facts, recorded bottle json |
| `CHANGES.md` | modify (Tasks 4, 12, 16) | user-facing entries |

mtuspy (`oetiker/mtuspy`):

| File | Change |
|---|---|
| `.github/workflows/proof.yml` | create (Task 5), delete (Task 8) |
| `.github/workflows/release-rust-binaries.yml`, `release-nfpm.yml`, `release-homebrew.yml` | create (Task 6), replaced by the `ri-` pieces (Task 13) |
| `.github/workflows/release-build.yml` | rewrite as a caller (Task 6), point at the pieces (Task 13) |
| `nfpm.yaml` | create (Task 6) |
| `Cargo.toml` | drop `[package.metadata.deb]` and `[package.metadata.generate-rpm]` (Task 6) |
| `Formula/mtuspy.rb` | template install lines (Task 14) |
| `demo/mtuspy.toml`, `docs/demo/mtuspy.webp`, `Makefile`, `README.md`, `CHANGES.md` | demo and shape gaps (Task 14) |

Work locations:

- repo-infra: a worktree on a new branch `feat/project-shape` from `spec/project-shape` (use superpowers:using-git-worktrees; the hook puts it under `/scratch/oetiker/claude-worktrees/`). Phase C works on a new branch `feat/release-pieces` from `main` after Phase A has merged.
- mtuspy: `/home/oetiker/checkouts/mtuspy` is on `main` with an uncommitted change to `mise.toml` that belongs to the owner. Do not touch that checkout's working tree; add worktrees:
  `git -C /home/oetiker/checkouts/mtuspy fetch origin` and
  `git -C /home/oetiker/checkouts/mtuspy worktree add /scratch/oetiker/claude-worktrees/mtuspy-release-pieces -b proof/release-pieces origin/main`.
- `$S` is `/scratch/oetiker/claude-tmp/claude-1003/project-shape`; create it with `mkdir -p`.

---

# Phase A: the shape in repo-infra (releasable alone)

### Task 1: The `exceptions` key and the `skip` rename

**Files:**
- Modify: `skills/repo-infra/scripts/repo_infra/check.py:26-30` (KEYS, OBSOLETE) and `config_items` (`:189-239`)
- Test: `tests/test_check.py`

**Interfaces:**
- Produces: `check.KEYS` includes `"exceptions"`; `check.OBSOLETE` no longer includes `"skip"`; `check.RENAMED = {"skip": "exceptions"}`; rows `Item("config", "exceptions", "problem", ...)` and `Item("config", "skip", "problem", ...)` with the exact details below.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_check.py`, after `test_gitea_packages_without_url_or_owner_is_a_problem`)

```python
EXCEPTIONS_PROBLEM = ("exceptions", "problem",
                      "exceptions must be an object that maps each rule id of "
                      "references/project-shape.md to a non-empty reason")


def test_exceptions_that_map_rule_ids_to_reasons_are_accepted(tmp_path):
    assert config(tmp_path, {"version_files": VERSIONS,
                             "exceptions": {"homebrew": "a service that needs root"}}) == []


def test_an_empty_exceptions_object_is_accepted(tmp_path):
    assert config(tmp_path, {"version_files": VERSIONS, "exceptions": {}}) == []


@pytest.mark.parametrize("value", [
    [], "homebrew", 1, None, {"homebrew": ""}, {"homebrew": "   "}, {"homebrew": 1},
    {"homebrew": None}, {"homebrew": ["a reason"]},
])
def test_exceptions_that_are_not_an_object_of_reasons_are_a_problem(tmp_path, value):
    found = config(tmp_path, {"version_files": VERSIONS, "exceptions": value})
    assert found == [EXCEPTIONS_PROBLEM]


def test_skip_is_told_to_become_exceptions(tmp_path):
    found = config(tmp_path, {"version_files": VERSIONS, "skip": {"ci-man": True}})
    assert found == [("skip", "problem",
                      "skip is now exceptions (D32): rename the key, and rewrite each of "
                      "its keys as a rule id of references/project-shape.md with the reason "
                      "the rule does not apply")]
```

- [ ] **Step 2: Run them to see them fail**

Run: `python3 -m pytest -q --basetemp=.pytest-tmp tests/test_check.py -k "exceptions or skip"`
Expected: FAIL. `exceptions` reads as "not a key repo-infra reads", `skip` as "no longer read".

- [ ] **Step 3: Implement**

In `check.py`, replace the two tuples:

```python
# What the borrowed release machinery reads (release-pr.yml, lib/*.js), and
# the exceptions the shape review reads (D32).
KEYS = ("version_files", "release_assets", "release_files", "gitea_packages",
        "moving_major_tag", "rust", "exceptions")
OBSOLETE = ("ecosystems", "ci", "ci_local", "publish", "build", "publish_local",
            "release_build", "release_build_local", "answers")
# D30 removed `skip`; D32 gave its purpose to `exceptions`, keyed by rule id.
RENAMED = {"skip": "exceptions"}
```

Add below `refused_release_files`:

```python
def _reasons(value):
    """True for an object whose every value is a non-empty reason (D32)."""
    return isinstance(value, dict) and all(
        isinstance(reason, str) and reason.strip() for reason in value.values())
```

In `config_items`, exclude the renamed key from the unknown keys and report both new rows right after the `strange` block:

```python
    strange = [key for key in config
               if key not in KEYS and key not in OBSOLETE and key not in RENAMED
               and not key.startswith("_")]
    if strange:
        items.append(Item("config", "repo-infra.json", "problem",
                          f"{', '.join(strange)}: not a key repo-infra reads"))
    if "skip" in config:
        items.append(Item("config", "skip", "problem",
                          "skip is now exceptions (D32): rename the key, and rewrite each "
                          "of its keys as a rule id of references/project-shape.md with "
                          "the reason the rule does not apply"))
    if "exceptions" in config and not _reasons(config["exceptions"]):
        items.append(Item("config", "exceptions", "problem",
                          "exceptions must be an object that maps each rule id of "
                          "references/project-shape.md to a non-empty reason"))
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest -q --basetemp=.pytest-tmp tests/test_check.py`
Expected: PASS, including the unchanged `test_obsolete_and_unknown_keys_are_problems`.

- [ ] **Step 5: Gate and commit**

Run: `make check` (timeout 600000). Expected: PASS.

```bash
git add skills/repo-infra/scripts/repo_infra/check.py tests/test_check.py
git commit -m "Accept exceptions in repo-infra.json and rename skip (D32)

The shape review reads exceptions, one reason per rule id. check only
checks the shape of the value: it does not know the rule ids. A
repository that still carries skip, which D30 removed, is told to rename
it instead of reading that the key is no longer read.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `references/project-shape.md`

**Files:**
- Create: `skills/repo-infra/references/project-shape.md`
- Test: `tests/test_project_shape.py`

**Interfaces:**
- Produces: the sections `## Triggers`, `## Rules` (each rule a `### \`id\`` heading with the lines `Trigger:`, `Requires:`, `Verify:`, `Met by:` in that order), `## Exceptions`, `## Badges`, `## Install snippets`, `## Archive layout`, `## Formula template` (one ```ruby block with the placeholders `<Class>`, `<one-line description>`, `<owner>`, `<repo>`, `<SPDX license>`, `<bin>`). Task 11's tests read the formula template from this file; Task 12 amends the `Met by` lines.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_project_shape.py
"""references/project-shape.md (D32): every rule complete, every id once, and
the snippets other files rely on."""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHAPE = ROOT / "skills/repo-infra/references/project-shape.md"
RULES = {"readme-current", "badges", "install-text", "writing-style", "man-page", "demo",
         "screenshot", "native-targets", "source-archive", "linux-packages", "homebrew"}
FIELDS = ("Trigger:", "Requires:", "Verify:", "Met by:")


def text():
    return SHAPE.read_text(encoding="utf-8")


def section(title):
    return text().split(f"\n## {title}\n", 1)[1].split("\n## ", 1)[0]


def fenced(title, language):
    return re.findall(rf"```{language}\n(.*?)```", section(title), re.S)


def triggers():
    return re.findall(r"^- `([a-z][a-z ]*)`:", section("Triggers"), re.M)


def rules():
    parts = re.split(r"^### ", section("Rules"), flags=re.M)[1:]
    return [(part.splitlines()[0], part) for part in parts]


def test_every_rule_heading_is_one_id():
    for heading, _ in rules():
        assert re.fullmatch(r"`[a-z][a-z0-9-]*`", heading), heading


def test_the_rule_ids_are_unique_and_complete():
    ids = [heading.strip("`") for heading, _ in rules()]
    assert len(ids) == len(set(ids))
    assert set(ids) == RULES


def test_every_rule_states_each_field_once_in_order():
    for heading, body in rules():
        starts = [line.split(":", 1)[0] + ":" for line in body.splitlines()
                  if line.startswith(FIELDS)]
        assert starts == list(FIELDS), heading


def test_every_rule_names_a_trigger_the_file_defines():
    known = set(triggers())
    assert known == {"every project", "has a command line", "runs in a terminal",
                     "has a web or graphical interface", "is installed by users"}
    for heading, body in rules():
        trigger = re.search(r"^Trigger: (.+)\.$", body, re.M).group(1)
        assert trigger in known, f"{heading}: {trigger}"


def test_the_badges_link_the_ci_workflow_and_the_latest_release():
    (block,) = fenced("Badges", "markdown")
    assert "https://github.com/<owner>/<repo>/actions/workflows/ci.yml/badge.svg" in block
    assert "https://img.shields.io/github/v/release/<owner>/<repo>" in block
    assert "https://github.com/<owner>/<repo>/releases/latest" in block


def test_the_install_snippets_settle_the_differences_of_issue_57():
    blocks = "\n".join(fenced("Install snippets", "sh"))
    assert "sudo install -d -m 0755 /etc/apt/keyrings" in blocks
    assert "/etc/apt/keyrings/gitea-<gitea-owner>.asc" in blocks
    assert "-o /etc/yum.repos.d/<gitea-owner>.repo" in blocks
    assert "config-manager" not in blocks
    assert "brew trust --formula <owner>/<name>/<name>" in blocks
    assert "mise use -g github:<owner>/<name>" in blocks


def test_the_formula_template_carries_every_marker_and_installs_every_man_page():
    (ruby,) = fenced("Formula template", "ruby")
    for marker in ("# mac-arm", "# mac-x86", "# linux-x86", "# linux-arm",
                   "# BOTTLE-START", "# BOTTLE-END"):
        assert ruby.count(marker) == 1, marker
    lines = ruby.splitlines()
    shas = [i for i, line in enumerate(lines) if re.search(r'sha256 "0{64}" # ', line)]
    assert len(shas) == 4
    for i in shas:
        assert lines[i - 1].strip().startswith(
            'url "https://github.com/<owner>/<repo>/releases/download/v#{version}/<bin>-#{version}-')
    assert ('Dir["man/*.[1-9]"].each { |page| (man/"man#{page[-1]}").install page }'
            in ruby)


def test_the_prose_follows_the_house_style():
    prose = re.sub(r"```.*?```", "", text(), flags=re.S)
    assert "e.g." not in prose
    for heading in re.findall(r"^#{2,6} (.+)$", prose, re.M):
        later = [w for w in heading.split()[1:] if not w.startswith("`")]
        assert all(not w[0].isupper() for w in later), heading
```

- [ ] **Step 2: Run it to see it fail**

Run: `python3 -m pytest -q --basetemp=.pytest-tmp tests/test_project_shape.py`
Expected: FAIL with `FileNotFoundError` for `project-shape.md`.

- [ ] **Step 3: Write `skills/repo-infra/references/project-shape.md`** with exactly this content:

````markdown
# Project shape

What a released project contains (D32). A base applies to every repository;
every other rule is attached to a trigger that describes the project. A
repository matches as many triggers as apply to it: SmokePing, for example, has
a command line, has a web interface, and is a program users install that runs
on an interpreter.

The script reads none of this. You decide which triggers apply, read the
README, the manual, the demo and the release build, and report.
`commands/check.md` has the steps of the review; onboarding runs it once
(`references/onboarding.md`).

## Triggers

Triggers name what users receive, not how the code is written.

- `every project`: Every repository.
- `has a command line`: The program takes arguments, for example through clap,
  argparse or Getopt::Long.
- `runs in a terminal`: A command line tool or a full-screen terminal program.
- `has a web or graphical interface`: A browser or desktop interface.
- `is installed by users`: A program, a daemon or data such as a font,
  delivered on its own. A library, a plugin or a GitHub Action that another
  tool loads is not installed by users and owes no packages.

## Rules

Every rule applies to a project its trigger matches, unless `exceptions` in
`.github/repo-infra.json` names the rule with a reason. A rule is met by its
result, whatever builds it: packages, bottles and archives on the release meet
their rule also when the repository's own workflow builds them. A piece named
under "Met by" is the standard way, and the `pieces` section of the script's
report shows whether it is used.

### `readme-current`

Trigger: every project.

Requires: The README describes the project as it is now.

Verify: Compare the README with `docs/manual.md` or the argument definitions in
the source, with the channels in `release_assets` and `gitea_packages`, and
with the supported platforms. Report features that are missing, options that
no longer exist and channels that are not mentioned.

Met by: A README with nothing to report.

### `badges`

Trigger: every project.

Requires: The top of the README shows the CI badge, linked to the workflow, and
the version badge, linked to the latest release. Other badges may follow.

Verify: Both badges stand between the title and the first paragraph and name
this repository.

Met by: The snippet under "Badges".

### `install-text`

Trigger: every project.

Requires: A project that publishes to any channel has one install section with
the canonical snippet for each channel it publishes to.

Verify: Fill in the snippets under "Install snippets" from `gitea_packages`,
the package names in `release_assets` and the repository, and compare. Report
a channel the release publishes and the README omits, a snippet that differs
from the canonical one, and a channel the README names that the release does
not publish.

Met by: The snippets under "Install snippets". A project that publishes to no
channel meets it without an install section.

### `writing-style`

Trigger: every project.

Requires: The README, `docs/manual.md`, the rest of `docs/` and the unreleased
section of `CHANGES.md` follow the `writing-style` skill.

Verify: Load the `writing-style` skill and report each violation with its file,
the quoted text and the rule. For a large documentation site, read the README
and the manual in full, sample the rest, and say that you sampled.

Met by: Text with no violation.

### `man-page`

Trigger: has a command line.

Requires: `docs/manual.md`, built by the `man` pieces and checked by
`ri-ci-man`.

Verify: `docs/manual.md` exists and names the options the program has, the
Makefile sets `MAN_NAME` and includes `build/man.mk`, and `ci.yml` calls
`ri-ci-man`. Onboarding asks for the manual; it does not wait for the file to
exist.

Met by: The setup in the `man-pages` skill.

### `demo`

Trigger: runs in a terminal.

Requires: An ansidrama script `demo/<name>.toml`, the rendered
`docs/demo/<name>.webp` near the top of the README, and a `make demo` target
that renders it. The WebP is committed and regenerated by hand.

Verify: The three exist and the README shows the WebP before its first
section. Read the script and report commands or screens that no longer exist.

Met by: A recording made with ansidrama (https://github.com/oetiker/ansidrama).
CI does not render the demo.

### `screenshot`

Trigger: has a web or graphical interface.

Requires: A current image of the interface near the top of the README.

Verify: The image exists and shows no screen or control the interface no
longer has.

Met by: A committed image under `docs/`.

### `native-targets`

Trigger: is installed by users.

Requires: For a Rust program, archives for `x86_64-unknown-linux-musl`,
`aarch64-unknown-linux-musl`, `x86_64-apple-darwin`, `aarch64-apple-darwin`,
`x86_64-pc-windows-msvc`, `aarch64-pc-windows-msvc` and
`x86_64-unknown-illumos`, named `<name>-<version>-<target>.tar.gz` (`.zip` for
Windows), with the layout under "Archive layout". A program in another
compiled language has no `native-targets` rule until a binaries piece exists
for it; the review says so instead of reporting a gap.

Verify: `release_assets` lists the seven archives and the latest release
carries them.

Met by: The seven archives. mise's `github:` backend picks an asset by these
names, so `mise use -g github:<owner>/<name>` works without further setup.

### `source-archive`

Trigger: is installed by users.

Requires: For a program that runs on an interpreter, the source archive of the
release.

Verify: `release_assets` lists the archive and the latest release carries it.

Met by: For autotools, `ri-release-source-tarball`.

### `linux-packages`

Trigger: is installed by users.

Requires: `.deb` and `.rpm` packages, published to the Gitea registry by
`ri-publish-gitea`.

Verify: `release_assets` lists both kinds, the latest release carries them,
`release-publish.yml` calls `ri-publish-gitea`, and `gitea_packages` names the
registry.

Met by:

- a Rust program: amd64 and arm64 packages built from the musl archives;
- an interpreted program that bundles native modules (SmokePing's
  `thirdparty/` compiles XS modules such as `FCGI` and `Socket6`): packages per
  architecture;
- an interpreted program or data that depends only on distribution packages:
  `noarch` packages, as Smalti builds them.

### `homebrew`

Trigger: is installed by users.

Requires: `Formula/<name>.rb` in the repository, which is its own tap.

Verify: The formula exists, `release_files` lists it, its version is the
latest release and no `sha256` line is all zeros.

Met by: For a Rust program, bottles and a formula rewritten on each release
from the template under "Formula template". For an interpreted program, a
formula that builds from the source archive.

No piece builds the interpreted variants of `linux-packages` and `homebrew`
beyond what `ri-release-source-tarball` covers. The SmokePing onboarding proves
the rest first.

## Exceptions

`.github/repo-infra.json` maps a rule id to the reason the rule does not apply:

```json
"exceptions": {
  "homebrew": "a service that needs root and a web server; brew is the wrong channel"
}
```

The script reports a value that is not an object of non-empty strings. It does
not know the rule ids. The review reports an exception whose id matches no
rule, and a gap that has no exception.

A piece input that drops a requirement is allowed only together with the
exceptions for every rule it weakens, and the review checks the pairing. No
piece has such an input yet; the spec of the first one names its pairing. A
skipped target, for example, weakens `native-targets`; a skipped darwin target
also weakens `homebrew`, and a skipped musl target also `homebrew` and
`linux-packages`.

## Badges

```markdown
[![CI](https://github.com/<owner>/<repo>/actions/workflows/ci.yml/badge.svg)](https://github.com/<owner>/<repo>/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/<owner>/<repo>)](https://github.com/<owner>/<repo>/releases/latest)
```

## Install snippets

One snippet per channel. `<owner>` and `<name>` are the GitHub repository and
the formula, `<deb-name>` and `<rpm-name>` the package names (Smalti publishes
`fonts-smalti` and `smalti-fonts`), `<gitea-url>` and `<gitea-owner>` come from
`gitea_packages`.

Debian and Ubuntu:

```sh
sudo install -d -m 0755 /etc/apt/keyrings
sudo curl -fsSL -o /etc/apt/keyrings/gitea-<gitea-owner>.asc <gitea-url>/api/packages/<gitea-owner>/debian/repository.key
echo "deb [signed-by=/etc/apt/keyrings/gitea-<gitea-owner>.asc] <gitea-url>/api/packages/<gitea-owner>/debian stable main" | sudo tee /etc/apt/sources.list.d/<gitea-owner>.list
sudo apt update && sudo apt install <deb-name>
```

Fedora, RHEL, Rocky and Alma, with dnf4 and dnf5 alike:

```sh
sudo curl -fsSL -o /etc/yum.repos.d/<gitea-owner>.repo <gitea-url>/api/packages/<gitea-owner>/rpm.repo
sudo dnf install <rpm-name>
```

Homebrew:

```sh
brew tap <owner>/<name> https://github.com/<owner>/<name>
brew trust --formula <owner>/<name>/<name>
brew install <name>
```

`brew trust` exists from Homebrew 6 on; skip it on older versions.

mise:

```sh
mise use -g github:<owner>/<name>
```

Direct download: a link to `https://github.com/<owner>/<name>/releases/latest`.

## Archive layout

```
<bin>-<version>-<target>.tar.gz
  <bin>/<bin>
  <bin>/man/<every page in man/>
  <bin>/README.md
  <bin>/LICENSE
```

`man/` holds whatever `make man` produced: `build/man.mk` takes the section
from the manual's front matter, so a daemon ships `man/<page>.8`. The Windows
`.zip` has the same layout without `man/`.

## Formula template

The release build rewrites the `version` line, the four `sha256` lines found by
their marker comments, and the block between `# BOTTLE-START` and
`# BOTTLE-END`. Each `url` line stands directly above its `sha256` line. The
formula belongs to the repository: it decides what else is installed, such as
`examples/`.

```ruby
# Homebrew formula for <bin>. This repository is its own tap.
#
# The release build rewrites the version line, the four sha256 lines by their
# marker comments and the bottle block between the BOTTLE markers. Keep the
# markers, and keep each url line directly above its sha256 line.
class <Class> < Formula
  desc "<one-line description>"
  homepage "https://github.com/<owner>/<repo>"
  version "0.0.0"
  license "<SPDX license>"

  # BOTTLE-START
  # BOTTLE-END

  on_macos do
    on_arm do
      url "https://github.com/<owner>/<repo>/releases/download/v#{version}/<bin>-#{version}-aarch64-apple-darwin.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000" # mac-arm
    end
    on_intel do
      url "https://github.com/<owner>/<repo>/releases/download/v#{version}/<bin>-#{version}-x86_64-apple-darwin.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000" # mac-x86
    end
  end

  on_linux do
    on_intel do
      url "https://github.com/<owner>/<repo>/releases/download/v#{version}/<bin>-#{version}-x86_64-unknown-linux-musl.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000" # linux-x86
    end
    on_arm do
      url "https://github.com/<owner>/<repo>/releases/download/v#{version}/<bin>-#{version}-aarch64-unknown-linux-musl.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000" # linux-arm
    end
  end

  def install
    bin.install "<bin>"
    Dir["man/*.[1-9]"].each { |page| (man/"man#{page[-1]}").install page }
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/<bin> --version")
  end
end
```
````

- [ ] **Step 4: Run the tests and the prose checks**

Run: `python3 -m pytest -q --basetemp=.pytest-tmp tests/test_project_shape.py tests/test_no_em_dash.py`
Expected: PASS. Then `grep -c $'\u2014' skills/repo-infra/references/project-shape.md` prints `0`.

- [ ] **Step 5: Commit**

```bash
git add skills/repo-infra/references/project-shape.md tests/test_project_shape.py
git commit -m "Add the project shape reference (D32)

One rule per id, each with its trigger, what it requires, how the review
verifies it and what meets it. The install snippets settle the apt key
name, the keyring directory and the dnf command that differed across
mdmost, edaptor and mtuspy (#57).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The shape review in the commands, and the script loops

**Files:**
- Modify: `commands/check.md`, `commands/apply.md`, `skills/repo-infra/SKILL.md`, `skills/repo-infra/references/onboarding.md`, `skills/repo-infra/references/release-flow.md:308-320`, `skills/repo-infra/references/conventions.md:70-80`
- Test: `tests/test_skill.py`

**Interfaces:**
- Consumes: `references/project-shape.md` (Task 2), the `exceptions` key (Task 1).

- [ ] **Step 1: Write the failing tests** in `tests/test_skill.py`

Add `"project-shape.md"` to the tuple in `test_the_references_the_skill_names_exist`, so it reads:

```python
    for name in ("catalogue.md", "onboarding.md", "conventions.md", "release-flow.md",
                 "teaching-the-standard.md", "project-shape.md", "examples/repo-infra"):
```

Append:

```python
def flat(path):
    return " ".join(path.read_text(encoding="utf-8").split())


def test_the_loops_run_the_script_and_only_the_command_reviews_the_shape():
    for path in (SKILL, ROOT / "commands/apply.md", REFS / "onboarding.md"):
        text = flat(path)
        assert "`check` until it exits 0" not in text, path.name
        assert "the script until it exits 0" in text, path.name
    apply = flat(ROOT / "commands/apply.md")
    assert "Run `/repo-infra:check` first" not in apply
    assert "Run the script first" in apply


def test_check_runs_the_shape_review_apart_from_the_exit_code():
    text = flat(ROOT / "commands/check.md")
    assert "references/project-shape.md" in text
    assert "does not change the exit code" in text
    for state in ("`met`", "`gap`", "`excepted`"):
        assert state in text


def test_onboarding_reviews_the_shape_once_and_release_flow_points_at_the_snippets():
    assert "project-shape.md" in flat(REFS / "onboarding.md")
    release = flat(REFS / "release-flow.md")
    assert "config-manager" not in release
    assert "references/project-shape.md" in release


def test_conventions_names_exceptions_and_the_skip_rename():
    text = flat(REFS / "conventions.md")
    assert "`exceptions`" in text
    assert "rename it to `exceptions`" in text
```

Run: `python3 -m pytest -q --basetemp=.pytest-tmp tests/test_skill.py`
Expected: FAIL in the five new or changed tests.

- [ ] **Step 2: `commands/check.md`**

Replace the first line of the body, `Run the checker and read the report to the user:`, with:

```markdown
The command has two parts: the script's report and the shape review. Run the
script and read its report to the user:
```

Replace the last paragraph (`` `check` exits 1 when any row needs attention ... trust it over guessing from the text. ``) with:

```markdown
The script exits 1 when any row needs attention and 0 otherwise. That exit
code is the result of the script, so trust it over guessing from the text.

## The shape review

After the report, review what the project contains. The review is a separate
part of the report and does not change the exit code.

1. Read `references/project-shape.md` in the skill.
2. State which triggers apply, each with its evidence, for example "has a
   command line: `src/main.rs` parses arguments with clap".
3. Give every rule of those triggers one state: `met`, `gap` with what is
   missing, or `excepted` with the reason recorded under `exceptions` in
   `.github/repo-infra.json`.
4. List the exceptions whose id matches no rule, and the piece inputs that lack
   their paired exceptions.

Report a gap; do not close it from here. Onboarding agrees with the owner which
gaps a run closes (`references/onboarding.md`).
```

- [ ] **Step 3: `commands/apply.md`**

Replace the first paragraph (`Run `/repo-infra:check` first and show the user the report. ... copies each piece.`) with:

````markdown
Run the script first and show the user the report:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" check
```

If a piece reads `edited`, ask the user before acting on it. If the repository
has no pieces yet, it is an onboarding: follow `references/onboarding.md` in the
skill, where `apply --item <piece>` copies each piece and the shape review runs
once. An update runs no shape review; `/repo-infra:check` does.
````

Replace `Then you change the callers and the config from the notes and findings, and run`/`` `check` until it exits 0.`` with:

```markdown
Then you change the callers and the config from the notes and findings, and run
the script until it exits 0.
```

- [ ] **Step 4: `SKILL.md`, at most 120 lines** (it has 120 now; `test_the_skill_stays_short` holds the cap)

Replace lines 28-33 (the **Onboarding** paragraph, six lines) with these four:

```markdown
**Onboarding** a repository: read it, map each need to a piece, copy the pieces
with `apply --item <piece>`, write the callers, run the script until it exits 0,
then review the shape once. `references/onboarding.md` has the procedure, and
`references/project-shape.md` what a released project contains.
```

Replace lines 44-45 with:

```markdown
You then change the callers and the config from those notes and run the script
until it exits 0. `/repo-infra:check` and `/repo-infra:apply` walk through it.
```

After the D30 line (line 78) add:

```markdown
- D32: a project has a shape, with exceptions. `references/project-shape.md`
```

Replace the two-line catalogue bullet of "Reading further" (lines 110-111) with one line, and add the shape bullet after the onboarding bullet:

```markdown
- `references/catalogue.md`: every piece, its inputs and a caller snippet.
- `references/onboarding.md`: the procedure for a repository not yet in the fold.
- `references/project-shape.md`: what a released project contains, by trigger.
```

Run: `wc -l skills/repo-infra/SKILL.md`. Expected: `120` or fewer.

- [ ] **Step 5: `references/onboarding.md`**

Step 5 of "The procedure" becomes:

```markdown
5. **Run the script until it exits 0.** It reads the callers against the pieces
   they call, so a misspelt input or a missing `needs:` entry shows up before
   the first run on GitHub does.
6. **Review the shape once.** Run the shape review of `commands/check.md`
   against `references/project-shape.md`, then agree with the owner which gaps
   this run closes and which become `exceptions` in `.github/repo-infra.json`,
   each with its reason.
```

The old step 6 (**Open the pull request ...**) becomes step 7, text unchanged.

In "Candidates a repository's files suggest but do not decide", replace the `docs/manual.md` bullet with:

```markdown
- `docs/manual.md` suggests `ri-ci-man`, with the `man` and `man-lua` pieces
  and `MAN_NAME` plus `include build/man.mk` in the Makefile (the `man-pages`
  skill has the rest). A program with a command line and no manual gets one:
  ask for it (`man-page` in `references/project-shape.md`).
```

- [ ] **Step 6: `references/release-flow.md`**

Replace everything from `What users type on Debian and Ubuntu:` through the dnf4 line `    sudo dnf config-manager --add-repo https://gitea.oetiker.ch/api/packages/oposs/rpm.repo` (lines 308-320) with:

```markdown
What users type to install from the registry is under "Install snippets" in
`references/project-shape.md`.
```

- [ ] **Step 7: `references/conventions.md`**

Replace the first paragraph of "`.github/repo-infra.json` holds what a caller cannot say" with:

```markdown
The file keeps what the release machinery (`release-pr.yml`, `lib/*.js`) reads,
what cannot be seen in a caller, and the `exceptions` the shape review reads
(D32, which amends D30 here). Nothing writes it: it is hand-edited, and `check`
and `apply` only read it. `check` reports a key it does not read as a
`problem`, and the keys of the old assembler (`ecosystems`, `ci`, `publish`,
`build`, `release_build`, `answers` and the three that ended in `_local`) as
`problem` too, so a migrated repository is told to remove them (D30). The
callers state the same facts directly. D30 also removed `skip`; a repository
that still has it is told to rename it to `exceptions` and to rewrite its keys
as rule ids.
```

Add after the `rust` bullet of the key list:

```markdown
- `exceptions`: one reason per rule id of `references/project-shape.md`, for a
  rule that does not apply to this repository (D32). `check` reports a value
  that is not an object of non-empty strings; only the shape review reads the
  ids and the reasons.
```

- [ ] **Step 7b: The example config documents nothing new.** `references/examples/repo-infra/repo-infra.json` is repo-infra's own file (`tests/test_self_check.py` compares them); leave both without `exceptions`.

- [ ] **Step 8: Run the tests and the gate**

Run: `make check` (timeout 600000). Expected: PASS. Then `grep -c $'\u2014' commands/*.md skills/repo-infra/SKILL.md skills/repo-infra/references/*.md` prints `0` for every file.

- [ ] **Step 9: Commit**

```bash
git add commands skills/repo-infra/SKILL.md skills/repo-infra/references tests/test_skill.py
git commit -m "Review the project shape in /repo-infra:check (D32)

The command reports the script and then the shape: which triggers apply,
and for each rule met, gap or excepted. The exit code stays the
script's. apply and the onboarding loop run the script, not the command,
so an update repeats no review; onboarding reviews the shape once and
agrees the gaps with the owner. release-flow.md points at the canonical
install snippets instead of carrying its own dnf commands.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Changelog, pull request and the optional release of Phase A

**Files:**
- Modify: `CHANGES.md`

- [ ] **Step 1: Changelog entries** under `## [Unreleased]`:

```markdown
### New
- `/repo-infra:check` reviews the project's shape after the script's report: which triggers apply (a command line, a terminal, a web interface, installed by users) and, for each rule, `met`, `gap` or `excepted`. `references/project-shape.md` in the skill lists the rules, the README badges, one install snippet per channel and a Homebrew formula template (#57).
- `.github/repo-infra.json` accepts `exceptions`, which maps a rule id of the shape to the reason it does not apply. `check` reports a value that is not an object of non-empty reasons, and tells a repository that still has `skip` to rename it to `exceptions`.

### Changed
- `/repo-infra:apply` starts with the script's report instead of `/repo-infra:check`, so an update runs no shape review.
- The registry install commands in the skill name the apt key `gitea-<owner>.asc`, create `/etc/apt/keyrings` first, and add the rpm repository with one `curl` that works for dnf4 and dnf5 (#57).
```

Run: `python3 -m pytest -q --basetemp=.pytest-tmp tests/test_no_em_dash.py` and `make check`. Expected: PASS.

```bash
git add CHANGES.md
git commit -m "Changelog for the project shape (D32)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: [outward] [ask the owner] Push and open the pull request**

```bash
git push -u origin feat/project-shape
gh pr create --base main --title "Project shape (D32)" --body-file $S/pr-phase-a.md
```

The body names the spec, lists the decisions P1 to P10 of this plan that apply later, says that Phase A ships no piece, and ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`. The pull request carries changelog entries, so it needs no `no-changelog` label.

- [ ] **Step 3: Watch the checks:** `gh pr checks --watch`. Expected: `ci-passed` and `changelog-updated` green.

- [ ] **Step 4: [outward] [ask the owner] Merge**, and ask whether to release Phase A alone (dispatch Create release PR on `oposs/repo-infra` with `feature`, then merge the release pull request) or to release it together with Phase C (Task 12).

---
# Phase B: the proof in mtuspy and its first release

Facts this phase starts from, read on 2026-10-10: mtuspy's latest release is
v0.1.3 (2026-02-13) with seven archives and nothing else. Its
`release-build.yml` (cargo-deb, cargo-generate-rpm, bottles, formula rewrite)
was added on 2026-10-07 and has never run. `Formula/mtuspy.rb` holds four
all-zero `sha256` lines. v0.1.3's own release workflow built illumos with
`crt-static` through cross and published the archive, so the baseline run is
expected to build all seven targets.

### Task 5: Proof branch and the baseline run

**Files (mtuspy):**
- Create: `.github/workflows/proof.yml`

**Interfaces:**
- Produces: `$S/baseline/` (every artifact of the baseline run), `$S/baseline-facts/` (archive listings and package facts), `$S/facts.sh`, `$S/collect.sh`, `$S/factsdiff.py`, and the run id in `$S/baseline-run-id`. Tasks 7, 10 and 11 read them.

- [ ] **Step 1: Worktree and scratch directory**

```bash
mkdir -p /scratch/oetiker/claude-tmp/claude-1003/project-shape
export S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
git -C /home/oetiker/checkouts/mtuspy fetch origin
git -C /home/oetiker/checkouts/mtuspy worktree add /scratch/oetiker/claude-worktrees/mtuspy-release-pieces -b proof/release-pieces origin/main
cd /scratch/oetiker/claude-worktrees/mtuspy-release-pieces
```

- [ ] **Step 2: Write `.github/workflows/proof.yml`**

```yaml
name: Proof of the release build

# Temporary (repo-infra D32). Runs release-build.yml on the head of this pull
# request as version 0.0.0, so a release build can be compared with the next
# one before anything is released. It creates no tag, no release and no
# release branch. Removed before the branch merges.
on:
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  build:
    uses: ./.github/workflows/release-build.yml
    with:
      version: 0.0.0
      ref: ${{ github.event.pull_request.head.sha }}
```

- [ ] **Step 3: [outward] Commit, push and open a draft pull request with the label at creation**

```bash
git add .github/workflows/proof.yml
git commit -m "Run the release build on this branch as 0.0.0 (temporary)

The proof of repo-infra D32: the first run builds with the release build
as it is, the baseline the rewritten build is compared with.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push -u origin proof/release-pieces
gh pr create -R oetiker/mtuspy --draft --base main --head proof/release-pieces \
  --label no-changelog --title "Release build as three workflows, packages by nfpm" \
  --body-file $S/pr-mtuspy-proof.md
```

The body says: this branch proves the release pieces of repo-infra D32; `proof.yml` builds each push as version 0.0.0 and is removed before the merge; no user-visible change, hence `no-changelog`. It ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

- [ ] **Step 4: Wait for the baseline run**

```bash
gh run list -R oetiker/mtuspy --workflow proof.yml --branch proof/release-pieces --limit 1 --json databaseId --jq '.[0].databaseId' > $S/baseline-run-id
gh run watch "$(cat $S/baseline-run-id)" -R oetiker/mtuspy --exit-status
```

Expected: green, with jobs `build / Build <target>` for seven targets, `build / Bottle on macos-14`, `build / Bottle on macos-15-intel` and `build / Rewrite the formula`. If any job fails, stop and report the job and its log excerpt to the owner: a failing baseline leg is a finding about mtuspy's current build (for example the illumos `crt-static` the spec names), and the owner decides whether the baseline is taken from a run with that one line fixed.

- [ ] **Step 5: Download the baseline**

```bash
gh run download "$(cat $S/baseline-run-id)" -R oetiker/mtuspy -D $S/baseline
ls $S/baseline
```

Expected folders: `release-asset-<target>` for the seven targets (the two musl folders also hold the cargo-deb `.deb` and the cargo-generate-rpm `.rpm`, named after Cargo.toml's version 0.1.3), `release-asset-bottle-macos-14`, `release-asset-bottle-macos-15-intel`, `bottle-json-macos-14`, `bottle-json-macos-15-intel`, `release-files`.

- [ ] **Step 6: Write the comparison tools to `$S`**

`$S/facts.sh`:

```sh
#!/bin/sh
# facts.sh <package> <directory>: the comparable facts of one .deb or .rpm,
# written as three text files: files (mode and path), control (the fields a
# user sees) and postinst. Sizes, dates and the version are left out, so a
# cargo-deb package of 0.1.3 and an nfpm package of 0.0.0 compare.
set -eu
export LC_ALL=C
package=$1
out=$2
mkdir -p "$out"
case $package in
*.deb)
  dpkg-deb --fsys-tarfile "$package" | tar -tvf - \
    | awk '$1 !~ /^d/ { path = $NF; sub(/^\./, "", path); print $1, path }' | sort > "$out/files"
  dpkg-deb --field "$package" Package Architecture Section Priority Maintainer \
    Depends Recommends Description > "$out/control"
  dpkg-deb --ctrl-tarfile "$package" | tar -xOf - ./postinst > "$out/postinst"
  ;;
*.rpm)
  rpm -qp --queryformat '[%{FILEMODES:perms} %{FILENAMES}\n]' "$package" | sort > "$out/files"
  rpm -qp --queryformat 'Name: %{NAME}\nArch: %{ARCH}\nLicense: %{LICENSE}\nSummary: %{SUMMARY}\n' \
    "$package" > "$out/control"
  rpm -qp --recommends "$package" | sed 's/^/Recommends: /' >> "$out/control"
  rpm -qp --requires "$package" | sed -n '/^rpmlib(/!s/^/Requires: /p' >> "$out/control"
  rpm -qp --queryformat '%{POSTIN}\n' "$package" > "$out/postinst"
  ;;
*)
  echo "facts.sh: $package is neither .deb nor .rpm" >&2
  exit 1
  ;;
esac
```

`$S/collect.sh`:

```sh
#!/bin/sh
# collect.sh <directory> <out>: facts.sh for every package under <directory>,
# one folder per kind and architecture (deb-amd64, rpm-x86_64, ...).
set -eu
here=$(dirname "$0")
find "$1" -name '*.deb' -o -name '*.rpm' | sort | while read -r package; do
  name=$(basename "$package")
  case $name in
  *.deb) key=deb-${name##*_}; key=${key%.deb} ;;
  *.rpm) key=${name%.rpm}; key=rpm-${key##*.} ;;
  esac
  sh "$here/facts.sh" "$package" "$2/$key"
done
```

`$S/factsdiff.py` (Task 10 commits the same function as `tests/nfpm_facts.py`):

```python
"""factsdiff.py <baseline> <actual>: the differences between two trees of
facts.sh output, one unified diff per file, without dates."""

import difflib
import pathlib
import sys


def facts_diff(baseline, actual):
    baseline, actual = pathlib.Path(baseline), pathlib.Path(actual)
    names = sorted({p.relative_to(root).as_posix()
                    for root in (baseline, actual) for p in root.rglob("*") if p.is_file()})
    lines = []
    for name in names:
        old = (baseline / name).read_text(encoding="utf-8").splitlines() \
            if (baseline / name).is_file() else []
        new = (actual / name).read_text(encoding="utf-8").splitlines() \
            if (actual / name).is_file() else []
        lines += difflib.unified_diff(old, new, f"baseline/{name}", f"nfpm/{name}", lineterm="")
    return "".join(line + "\n" for line in lines)


if __name__ == "__main__":
    sys.stdout.write(facts_diff(sys.argv[1], sys.argv[2]))
```

- [ ] **Step 7: Record the baseline facts**

```bash
mkdir -p $S/baseline-facts/archives
for archive in $S/baseline/release-asset-*/*.tar.gz; do
  tar -tzf "$archive" | LC_ALL=C sort > "$S/baseline-facts/archives/$(basename "$archive").list"
done
for archive in $S/baseline/release-asset-*/*.zip; do
  python3 -I -c 'import sys, zipfile; print("\n".join(sorted(zipfile.ZipFile(sys.argv[1]).namelist())))' "$archive" \
    > "$S/baseline-facts/archives/$(basename "$archive").list"
done
podman run --rm -v $S:/s:Z docker.io/library/ubuntu:24.04 bash -euc '
  apt-get update -qq && apt-get install -y -qq rpm >/dev/null
  sh /s/collect.sh /s/baseline /s/baseline-facts/packages'
mkdir -p $S/baseline-facts/bottles
cp $S/baseline/bottle-json-*/*.bottle.json $S/baseline-facts/bottles/
cp $S/baseline/release-files/Formula/mtuspy.rb $S/baseline-facts/mtuspy.rb
ls -R $S/baseline-facts
```

Expected: one `.list` per archive (each tar listing holds `mtuspy/`, `mtuspy/mtuspy`, `mtuspy/man/`, `mtuspy/man/mtuspy.1`, `mtuspy/README.md`, `mtuspy/LICENSE`; each zip listing the same without `man/`), `packages/deb-amd64`, `deb-arm64`, `rpm-x86_64`, `rpm-aarch64`, each with `files`, `control` and `postinst`, two bottle json files, and the rewritten formula with non-zero `sha256` lines and a bottle block whose `root_url` ends in `/v0.0.0`.

- [ ] **Step 8: Record edaptor v1.8.0 as the second reference**

```bash
gh release download v1.8.0 -R oposs/edaptor -p '*.deb' -p '*.rpm' -D $S/edaptor
podman run --rm -v $S:/s:Z docker.io/library/ubuntu:24.04 bash -euc '
  apt-get update -qq && apt-get install -y -qq rpm >/dev/null
  sh /s/collect.sh /s/edaptor /s/edaptor-facts'
```

Expected: `$S/edaptor-facts/{deb-amd64,deb-arm64,rpm-x86_64,rpm-aarch64}`. Read them next to the mtuspy baseline: they show which control fields and doc files a cargo-deb release that published green carries.

---

### Task 6: The release build as three local workflows, and `nfpm.yaml`

**Files (mtuspy, on `proof/release-pieces`):**
- Create: `.github/workflows/release-rust-binaries.yml`, `.github/workflows/release-nfpm.yml`, `.github/workflows/release-homebrew.yml`, `nfpm.yaml`
- Rewrite: `.github/workflows/release-build.yml`
- Modify: `Cargo.toml` (delete `[package.metadata.deb]` and `[package.metadata.generate-rpm]`)

**Interfaces:**
- Produces: the three files Task 9, 10 and 11 copy into repo-infra. Each opens with a two-line comment (decision P2); everything from the blank line after it to the end is the bytes the pieces will ship.
- Inputs: `release-rust-binaries.yml(version, ref, bin)`, `release-nfpm.yml(version, ref, config, packagers, archives)`, `release-homebrew.yml(version, ref, bin)`. Artifacts: `man-pages`, `release-asset-<target>`, `release-asset-packages`, `release-asset-bottle-<os>`, `bottle-json-<os>`, `release-files`.

- [ ] **Step 1: `.github/workflows/release-rust-binaries.yml`**

```yaml
# Local copy of the release piece ri-release-rust-binaries, proven here before
# repo-infra ships it (D32). `apply --item ri-release-rust-binaries` replaces it.

name: Build the Rust release archives

on:
  workflow_call:
    inputs:
      version:
        description: The version the release builds, from release-build.yml.
        type: string
        required: true
      ref:
        description: The release branch commit to build, from release-build.yml (D28).
        type: string
        required: true
      bin:
        description: The binary to build; the archives and their top folder are named after it.
        type: string
        required: true

permissions:
  contents: read

jobs:
  man:
    name: Build the man pages
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ inputs.ref }}

      # The pages are built once, with the pandoc ri-ci-man checks them with,
      # and every archive of the release carries the same files. mtuspy's
      # single-file build ran pandoc from brew on macOS and from apt on Linux,
      # so one release would have shipped pages from two pandoc versions.
      - name: Install pandoc
        run: |
          sudo apt-get update
          sudo apt-get install -y pandoc

      - name: Build the man pages
        run: make man

      - uses: actions/upload-artifact@v7
        with:
          name: man-pages
          path: man/
          if-no-files-found: error

  binaries:
    name: Build ${{ matrix.target }}
    needs: man
    runs-on: ${{ matrix.os }}
    timeout-minutes: 60
    strategy:
      # One target failing must not cancel the others: which target broke is
      # the answer, and fail-fast throws the rest of it away.
      fail-fast: false
      matrix:
        include:
          - target: x86_64-unknown-linux-musl
            os: ubuntu-latest
            cross: true
            static: true
          - target: aarch64-unknown-linux-musl
            os: ubuntu-latest
            cross: true
            static: true
          # illumos has no static C library, so the binary links the base
          # system's libraries. mtuspy's single-file build passed crt-static
          # here too.
          - target: x86_64-unknown-illumos
            os: ubuntu-latest
            cross: true
          - target: x86_64-apple-darwin
            os: macos-latest
          - target: aarch64-apple-darwin
            os: macos-14
          - target: x86_64-pc-windows-msvc
            os: windows-latest
            windows: true
          - target: aarch64-pc-windows-msvc
            os: windows-latest
            windows: true
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ inputs.ref }}

      - uses: dtolnay/rust-toolchain@stable
        with:
          targets: ${{ matrix.target }}

      - name: Fetch the man pages
        if: ${{ !matrix.windows }}
        uses: actions/download-artifact@v8
        with:
          name: man-pages
          path: man

      # Pinned to a released version, as in ri-ci-rust-musl: a cross build is
      # not rehearsed locally, so it must not rest on a moving dependency.
      - name: Install cross
        if: ${{ matrix.cross }}
        run: cargo install cross --version 0.2.5 --locked

      - name: Build
        shell: bash
        env:
          BIN: ${{ inputs.bin }}
          TARGET: ${{ matrix.target }}
          CROSS: ${{ matrix.cross }}
          STATIC: ${{ matrix.static }}
        run: |
          set -euo pipefail
          if [ "$STATIC" = true ]; then
            export RUSTFLAGS="-C target-feature=+crt-static"
          fi
          if [ "$CROSS" = true ]; then
            cross build --release --bin "$BIN" --target "$TARGET"
          else
            cargo build --release --bin "$BIN" --target "$TARGET"
          fi

      # The archive layout is the contract the packaging and Homebrew pieces
      # read (D32): <bin>/<bin>, <bin>/man/<every page>, README.md, LICENSE.
      - name: Pack the archive
        if: ${{ !matrix.windows }}
        shell: bash
        env:
          BIN: ${{ inputs.bin }}
          VERSION: ${{ inputs.version }}
          TARGET: ${{ matrix.target }}
        run: |
          set -euo pipefail
          shopt -s nullglob
          pages=(man/*.[1-9]*)
          if [ ${#pages[@]} -eq 0 ]; then
            echo "::error::no man page under man/; the man job uploads what make man built"
            exit 1
          fi
          mkdir -p dist "staging/$BIN/man"
          cp "target/$TARGET/release/$BIN" "staging/$BIN/"
          cp "${pages[@]}" "staging/$BIN/man/"
          cp README.md LICENSE "staging/$BIN/"
          tar -czf "dist/$BIN-$VERSION-$TARGET.tar.gz" -C staging "$BIN"

      # The same layout without man/. Compress-Archive, because the Windows
      # runner has no zip (mtuspy 0.1.2).
      - name: Pack the zip
        if: ${{ matrix.windows }}
        shell: pwsh
        env:
          BIN: ${{ inputs.bin }}
          VERSION: ${{ inputs.version }}
          TARGET: ${{ matrix.target }}
        run: |
          New-Item -ItemType Directory -Force -Path dist, "staging/${env:BIN}" | Out-Null
          Copy-Item "target/${env:TARGET}/release/${env:BIN}.exe" "staging/${env:BIN}/"
          Copy-Item README.md, LICENSE "staging/${env:BIN}/"
          Compress-Archive -Path "staging/${env:BIN}" -DestinationPath "dist/${env:BIN}-${env:VERSION}-${env:TARGET}.zip"

      - uses: actions/upload-artifact@v7
        with:
          name: release-asset-${{ matrix.target }}
          path: dist/*
          if-no-files-found: error
```

- [ ] **Step 2: `.github/workflows/release-nfpm.yml`**

```yaml
# Local copy of the release piece ri-release-nfpm, proven here before
# repo-infra ships it (D32). `apply --item ri-release-nfpm` replaces it.

name: Build the Linux packages

on:
  workflow_call:
    inputs:
      version:
        description: The version the release builds, from release-build.yml.
        type: string
        required: true
      ref:
        description: The release branch commit to build, from release-build.yml (D28).
        type: string
        required: true
      config:
        description: Path of the nfpm configuration in the repository, for example nfpm.yaml.
        type: string
        required: true
      packagers:
        description: JSON object with one key per packager, deb or rpm, each value an object of further variable names and their values for that packager.
        type: string
        required: true
      archives:
        description: Space-separated targets whose release-asset-<target> archive is unpacked and packaged, for example x86_64-unknown-linux-musl aarch64-unknown-linux-musl.
        type: string
        required: true

permissions:
  contents: read

jobs:
  packages:
    name: Build the deb and rpm packages
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ inputs.ref }}

      # Each archive lands in archives/release-asset-<target>/.
      - uses: actions/download-artifact@v8
        with:
          pattern: release-asset-*
          path: archives

      - name: Install nfpm
        env:
          NFPM_VERSION: 2.47.0
          NFPM_SHA256: 0660ca602b2d2d2ae4781a06c692b3eeb9d437ffea05b831d76e41f4a3188783
        run: |
          set -euo pipefail
          tarball="nfpm_${NFPM_VERSION}_Linux_x86_64.tar.gz"
          curl -fsSL -o "$RUNNER_TEMP/$tarball" \
            "https://github.com/goreleaser/nfpm/releases/download/v${NFPM_VERSION}/$tarball"
          echo "$NFPM_SHA256  $RUNNER_TEMP/$tarball" | sha256sum -c -
          mkdir -p "$RUNNER_TEMP/nfpm"
          tar -xzf "$RUNNER_TEMP/$tarball" -C "$RUNNER_TEMP/nfpm" nfpm
          echo "$RUNNER_TEMP/nfpm" >> "$GITHUB_PATH"

      # dpkg-deb is on the runner; rpm reads the .rpm back.
      - name: Install rpm
        run: |
          sudo apt-get update
          sudo apt-get install -y rpm

      - name: Build and read back the packages
        shell: python3 -I {0}
        env:
          VERSION: ${{ inputs.version }}
          CONFIG: ${{ inputs.config }}
          PACKAGERS: ${{ inputs.packagers }}
          ARCHIVES: ${{ inputs.archives }}
        run: |
          import datetime
          import json
          import os
          import pathlib
          import re
          import subprocess
          import sys
          import tarfile

          OWN = ("VERSION", "SOURCE_DATE_EPOCH", "MTIME", "PACKAGER", "TARGET", "STAGE", "ARCH")
          # nfpm translates amd64 and arm64 into x86_64 and aarch64 for rpm.
          ARCH = {"x86_64-unknown-linux-musl": "amd64", "aarch64-unknown-linux-musl": "arm64"}
          # The file names ri-publish-gitea accepts. DEB and RPM in lib/gitea.js
          # hold the same patterns; change both.
          DEB = re.compile(r"^([a-z0-9][a-z0-9+.-]*)_([^_/]+)_([a-z0-9]+)\.deb$")
          RPM = re.compile(r"^(.+)-([^-/]+)-([^-/]+)\.([A-Za-z0-9_]+)\.rpm$")
          VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


          def fail(message):
              print(f"::error::{message}", flush=True)
              sys.exit(1)


          def output(*args):
              return subprocess.run(args, check=True, capture_output=True, text=True).stdout


          version = os.environ["VERSION"]
          config = pathlib.Path(os.environ["CONFIG"])
          temp = pathlib.Path(os.environ["RUNNER_TEMP"])
          try:
              packagers = json.loads(os.environ["PACKAGERS"])
          except json.JSONDecodeError as error:
              fail(f"packagers is not JSON: {error}")
          if not (isinstance(packagers, dict) and packagers and all(
                  isinstance(extra, dict) and all(isinstance(v, str) for v in extra.values())
                  for extra in packagers.values())):
              fail('packagers must be a JSON object such as {"deb": {}, "rpm": {"NAME": "value"}}: '
                   "one key per packager, each mapping variable names to strings")
          unknown = sorted(set(packagers) - {"deb", "rpm"})
          if unknown:
              fail(f"packagers names {', '.join(unknown)}; this workflow builds deb and rpm")
          for packager, extra in packagers.items():
              shadowed = sorted(set(extra) & set(OWN))
              if shadowed:
                  fail(f"packagers.{packager} sets {', '.join(shadowed)}, which this workflow "
                       "sets itself")
          targets = os.environ["ARCHIVES"].split()
          if not targets:
              fail("archives names no target")
          for target in targets:
              if target not in ARCH:
                  fail(f"no package architecture is known for {target}; archives takes "
                       + " and ".join(ARCH))
          if not config.is_file():
              fail(f"{config} does not exist")
          template = config.read_text(encoding="utf-8")

          # nfpm 2.47.0 ignores SOURCE_DATE_EPOCH, so MTIME carries the same
          # instant for the config's mtime: field.
          epoch = output("git", "log", "-1", "--format=%ct", "HEAD").strip()
          mtime = datetime.datetime.fromtimestamp(int(epoch), datetime.timezone.utc)
          mtime = mtime.strftime("%Y-%m-%dT%H:%M:%SZ")

          out = pathlib.Path("packages")
          out.mkdir()
          for target in targets:
              found = sorted(pathlib.Path("archives", f"release-asset-{target}").glob("*.tar.gz"))
              if len(found) != 1:
                  fail(f"release-asset-{target} holds {len(found)} .tar.gz files; one is expected")
              unpacked = temp / "stage" / target
              unpacked.mkdir(parents=True)
              with tarfile.open(found[0]) as tar:
                  tar.extractall(unpacked, filter="data")
              tops = list(unpacked.iterdir())
              if len(tops) != 1 or not tops[0].is_dir():
                  fail(f"{found[0].name} must hold one folder, the <bin>/ of the archive layout")
              for packager, extra in packagers.items():
                  values = {"VERSION": version, "SOURCE_DATE_EPOCH": epoch, "MTIME": mtime,
                            "PACKAGER": packager, "TARGET": target, "STAGE": str(tops[0]),
                            "ARCH": ARCH[target], **extra}
                  # nfpm expands only top-level scalars, not the src: and dst:
                  # paths under contents:, so every ${VAR} is replaced here.
                  unset = sorted({name for name in VAR.findall(template) if name not in values})
                  if unset:
                      fail(f"{config} uses " + ", ".join("${" + n + "}" for n in unset)
                           + ", which neither this workflow nor packagers sets")
                  expanded = temp / f"nfpm-{target}-{packager}.yaml"
                  expanded.write_text(VAR.sub(lambda m: values[m.group(1)], template),
                                      encoding="utf-8")
                  before = set(out.iterdir())
                  subprocess.run(["nfpm", "package", "--config", str(expanded),
                                  "--packager", packager, "--target", str(out)],
                                 check=True, env={**os.environ, **values})
                  made = sorted(set(out.iterdir()) - before)
                  if len(made) != 1:
                      fail(f"nfpm wrote {len(made)} files for {target} {packager}; one is expected")
                  package = made[0]
                  if packager == "deb":
                      if not DEB.match(package.name):
                          fail(f"{package.name} is not name_version_arch.deb, the name "
                               "ri-publish-gitea uploads")
                      got = output("dpkg-deb", "--field", str(package), "Version").strip()
                      files = [line for line in output("dpkg-deb", "--contents", str(package))
                               .splitlines() if not line.startswith("d")]
                  else:
                      if not RPM.match(package.name):
                          fail(f"{package.name} is not name-version-release.arch.rpm, the name "
                               "ri-publish-gitea uploads")
                      got = output("rpm", "-qp", "--queryformat", "%{VERSION}", str(package)).strip()
                      files = [line for line in output("rpm", "-qlp", str(package)).splitlines()
                               if line.startswith("/")]
                  if got != version and not got.startswith(version + "-"):
                      fail(f"{package.name} carries version {got}, not {version}")
                  if not files:
                      fail(f"{package.name} holds no files")
                  print(f"{package.name}: version {got}, {len(files)} files", flush=True)

      - uses: actions/upload-artifact@v7
        with:
          name: release-asset-packages
          path: packages/
          if-no-files-found: error
```

- [ ] **Step 3: `.github/workflows/release-homebrew.yml`**

```yaml
# Local copy of the release piece ri-release-homebrew, proven here before
# repo-infra ships it (D32). `apply --item ri-release-homebrew` replaces it.

name: Build the Homebrew bottles and formula

on:
  workflow_call:
    inputs:
      version:
        description: The version the release builds, from release-build.yml.
        type: string
        required: true
      ref:
        description: The release branch commit to build, from release-build.yml (D28).
        type: string
        required: true
      bin:
        description: The binary; the formula is Formula/<bin>.rb and the archives are named after it.
        type: string
        required: true

permissions:
  contents: read

jobs:
  # Nothing is compiled here, but a formula without a bottle is a source build
  # to Homebrew, and a source build refuses to install on a Mac whose Command
  # Line Tools are older than its macOS. The bottle skips that check.
  bottles:
    name: Bottle on ${{ matrix.os }}
    runs-on: ${{ matrix.os }}
    timeout-minutes: 40
    # Only the Intel leg may fail quietly: a missing Intel bottle is a slow
    # install, a broken arm64 bottle is a defect. continue-on-error does
    # nothing for a leg that never starts: mdmost v0.1.2 shipped with an empty
    # bottle block because a retired runner label left a leg queued until
    # GitHub cancelled it after 24 hours. The labels are kept current by hand,
    # and a release build stuck in `queued` is the symptom.
    continue-on-error: ${{ matrix.optional || false }}
    strategy:
      fail-fast: false
      matrix:
        include:
          # The oldest image per architecture: Homebrew lets a bottle serve a
          # newer macOS, never an older one. macos-15-intel is the last Intel
          # image GitHub offers, and its bottle serves Sequoia and later only.
          - os: macos-14
          - os: macos-15-intel
            optional: true
    env:
      HOMEBREW_NO_AUTO_UPDATE: 1
      HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK: 1
      BIN: ${{ inputs.bin }}
      VERSION: ${{ inputs.version }}
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ inputs.ref }}

      - uses: actions/download-artifact@v8
        with:
          pattern: release-asset-*-apple-darwin
          path: dist
          merge-multiple: true

      # `@main`: Homebrew/actions tags are dated, and `@master` stopped
      # resolving when the branch was renamed (mdmost v0.3.2).
      - uses: Homebrew/actions/setup-homebrew@main

      # The release does not exist yet, so each url line directly above a mac
      # sha256 line is pointed at the archive this run built. A url line
      # anywhere else would leave brew fetching a GitHub url that answers 404.
      - name: Point the formula at the built archives
        run: |
          set -euo pipefail
          formula="Formula/$BIN.rb"
          arm="$PWD/dist/$BIN-$VERSION-aarch64-apple-darwin.tar.gz"
          x86="$PWD/dist/$BIN-$VERSION-x86_64-apple-darwin.tar.gz"
          for archive in "$arm" "$x86"; do
            [ -f "$archive" ] || { echo "::error::$archive was not built"; exit 1; }
          done
          awk -v out="$RUNNER_TEMP/local-formula.rb" -v version="$VERSION" \
              -v arm="file://$arm" -v x86="file://$x86" \
              -v sha_arm="$(shasum -a 256 "$arm" | cut -d' ' -f1)" \
              -v sha_x86="$(shasum -a 256 "$x86" | cut -d' ' -f1)" '
            function flush() { if (have) print held > out; have = 0 }
            /# BOTTLE-START/ { flush(); print > out; skip = 1; next }
            /# BOTTLE-END/ { skip = 0 }
            skip { next }
            /^  version "/ { $0 = "  version \"" version "\"" }
            /sha256 "[0-9a-f]*" # mac-(arm|x86)[[:space:]]*$/ {
              which = ($0 ~ /# mac-arm/) ? "arm" : "x86"
              seen[which]++
              if (!have || held !~ /^[[:space:]]*url "/) {
                printf "::error::no url line directly above the # mac-%s sha256 line\n", which
                bad = 1
              } else {
                indent = held
                sub(/[^[:space:]].*$/, "", indent)
                held = indent "url \"" (which == "arm" ? arm : x86) "\""
              }
              sub(/sha256 "[0-9a-f]*"/, "sha256 \"" (which == "arm" ? sha_arm : sha_x86) "\"")
            }
            { flush(); held = $0; have = 1 }
            END {
              flush()
              if (seen["arm"] != 1 || seen["x86"] != 1) {
                print "::error::the formula needs one # mac-arm and one # mac-x86 sha256 line"
                bad = 1
              }
              exit bad
            }
          ' "$formula"

      # Homebrew 6 loads a formula from a third-party tap only once the tap is
      # trusted; Homebrew 5 has no `brew trust`.
      - name: Local tap
        run: |
          set -euo pipefail
          brew tap-new --no-git "local/$BIN"
          cp "$RUNNER_TEMP/local-formula.rb" "$(brew --repository)/Library/Taps/local/homebrew-$BIN/Formula/$BIN.rb"
          major=$(brew --version | sed -n '1s/^Homebrew \([0-9][0-9]*\).*/\1/p')
          if [ "${major:-0}" -ge 6 ]; then
            brew trust --formula "local/$BIN/$BIN"
          fi

      - name: Build the bottle
        run: |
          set -euo pipefail
          brew install --build-bottle "local/$BIN/$BIN"
          brew bottle --json --no-rebuild \
            --root-url="https://github.com/$GITHUB_REPOSITORY/releases/download/v$VERSION" \
            "local/$BIN/$BIN"

      # `brew bottle` writes name--version.tag.bottle.tar.gz, with two dashes,
      # the name GitHub Packages wants. A plain root_url is fetched with one
      # dash. The json records both names, so the rename reads them from it.
      - name: Rename the bottles
        run: |
          set -euo pipefail
          shopt -s nullglob
          jsons=(./*.bottle.json)
          [ ${#jsons[@]} -gt 0 ] || { echo "::error::brew bottle wrote no json"; exit 1; }
          mkdir -p bottle
          for json in "${jsons[@]}"; do
            while IFS=$'\t' read -r local_name upload_name; do
              mv "$local_name" "bottle/$upload_name"
            done < <(jq -r '.[].bottle.tags[] | "\(.local_filename)\t\(.filename)"' "$json")
            cp "$json" bottle/
          done
          ls -la bottle

      - uses: actions/upload-artifact@v7
        with:
          name: release-asset-bottle-${{ matrix.os }}
          path: bottle/*.bottle.tar.gz
          if-no-files-found: error

      - uses: actions/upload-artifact@v7
        with:
          name: bottle-json-${{ matrix.os }}
          path: bottle/*.bottle.json
          if-no-files-found: error

  formula:
    name: Rewrite the formula
    needs: bottles
    # One architecture's bottle is worth publishing alone; zero fails below.
    if: ${{ !cancelled() }}
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ inputs.ref }}

      - uses: actions/download-artifact@v8
        with:
          pattern: release-asset-*
          path: artifacts
          merge-multiple: true

      - uses: actions/download-artifact@v8
        with:
          pattern: bottle-json-*
          path: bottles
          merge-multiple: true

      - name: Rewrite the formula
        env:
          BIN: ${{ inputs.bin }}
          VERSION: ${{ inputs.version }}
        run: |
          set -euo pipefail
          formula="Formula/$BIN.rb"
          [ -f "$formula" ] || { echo "::error::$formula does not exist"; exit 1; }
          grep -q '^  version "' "$formula" || { echo "::error::$formula has no version line"; exit 1; }
          for marker in mac-arm mac-x86 linux-x86 linux-arm; do
            grep -Eq "sha256 \"[0-9a-f]*\" # $marker[[:space:]]*\$" "$formula" \
              || { echo "::error::the marker # $marker is gone from $formula"; exit 1; }
          done
          for marker in BOTTLE-START BOTTLE-END; do
            grep -q "# $marker" "$formula" \
              || { echo "::error::the marker # $marker is gone from $formula"; exit 1; }
          done
          sha() {
            local archive="artifacts/$BIN-$VERSION-$1.tar.gz"
            [ -f "$archive" ] || { echo "::error::$archive was not built" >&2; return 1; }
            sha256sum "$archive" | cut -d' ' -f1
          }
          mac_arm=$(sha aarch64-apple-darwin)
          mac_x86=$(sha x86_64-apple-darwin)
          linux_x86=$(sha x86_64-unknown-linux-musl)
          linux_arm=$(sha aarch64-unknown-linux-musl)
          sed -i \
            -e "s/^  version \".*\"/  version \"$VERSION\"/" \
            -e "s|sha256 \"[0-9a-f]*\" # mac-arm|sha256 \"$mac_arm\" # mac-arm|" \
            -e "s|sha256 \"[0-9a-f]*\" # mac-x86|sha256 \"$mac_x86\" # mac-x86|" \
            -e "s|sha256 \"[0-9a-f]*\" # linux-x86|sha256 \"$linux_x86\" # linux-x86|" \
            -e "s|sha256 \"[0-9a-f]*\" # linux-arm|sha256 \"$linux_arm\" # linux-arm|" \
            "$formula"

          # The formula arrives carrying the previous release's bottle block.
          # Left alone, it would publish a root_url pointing at the previous
          # tag under this version: mdmost v0.3.2 did, and every brew install
          # met a 404. Zero bottles fails for the same reason.
          shopt -s nullglob
          jsons=(bottles/*.bottle.json)
          [ ${#jsons[@]} -gt 0 ] || { echo "::error::no bottles were built"; exit 1; }
          for json in "${jsons[@]}"; do
            while read -r name; do
              [ -f "artifacts/$name" ] \
                || { echo "::error::bottle $name was not built under that name"; exit 1; }
            done < <(jq -r '.[].bottle.tags[].filename' "$json")
          done

          # Generated, not patched: which architectures produced a bottle is
          # known only now, and a sha256 line for a bottle that was never
          # built sends Homebrew after a file that does not exist.
          {
            echo "  # BOTTLE-START"
            echo "  bottle do"
            echo "    root_url \"https://github.com/$GITHUB_REPOSITORY/releases/download/v$VERSION\""
            for json in "${jsons[@]}"; do
              # `cellar` sits on the bottle and `brew bottle` copies it onto
              # each tag; the tag's own value wins.
              jq -r '.[].bottle as $b | $b.tags | to_entries[]
                     | "    sha256 cellar: :\(.value.cellar // $b.cellar), \(.key): \"\(.value.sha256)\""' "$json"
            done
            echo "  end"
            echo "  # BOTTLE-END"
          } > "$RUNNER_TEMP/bottle-block.txt"
          cat "$RUNNER_TEMP/bottle-block.txt"
          # The block replaces the old range in place, so a second run writes
          # the same lines.
          awk -v block="$RUNNER_TEMP/bottle-block.txt" '
            /# BOTTLE-START/ { while ((getline line < block) > 0) print line; inside = 1; next }
            /# BOTTLE-END/ { inside = 0; next }
            !inside
          ' "$formula" > "$RUNNER_TEMP/formula.rb"
          mv "$RUNNER_TEMP/formula.rb" "$formula"

          mkdir -p "release-files/Formula"
          cp "$formula" "release-files/Formula/$BIN.rb"
          cat "$formula"

      - uses: actions/upload-artifact@v7
        with:
          name: release-files
          path: release-files/
          if-no-files-found: error
```

- [ ] **Step 4: Rewrite `.github/workflows/release-build.yml`** as a caller

```yaml
name: Release build

# Called by Create release PR on the release branch before the pull request
# exists (D28). The three workflows it calls are local copies of the release
# pieces repo-infra is about to ship (D32): the archives, the deb and rpm
# packages built from the musl archives, and the bottles with the rewritten
# Formula/mtuspy.rb. Read-only: nothing here writes the repository.
on:
  workflow_call:
    inputs:
      version:
        description: The version being released.
        type: string
        required: true
      ref:
        description: The release branch head to build.
        type: string
        required: true

permissions:
  contents: read

jobs:
  binaries:
    uses: ./.github/workflows/release-rust-binaries.yml
    with:
      version: ${{ inputs.version }}
      ref: ${{ inputs.ref }}
      bin: mtuspy

  packages:
    needs: binaries
    uses: ./.github/workflows/release-nfpm.yml
    with:
      version: ${{ inputs.version }}
      ref: ${{ inputs.ref }}
      config: nfpm.yaml
      packagers: '{"deb": {}, "rpm": {}}'
      archives: x86_64-unknown-linux-musl aarch64-unknown-linux-musl

  homebrew:
    needs: binaries
    uses: ./.github/workflows/release-homebrew.yml
    with:
      version: ${{ inputs.version }}
      ref: ${{ inputs.ref }}
      bin: mtuspy
```

The `release-version` echo job of the old file goes; nothing reads it.

- [ ] **Step 5: `nfpm.yaml`**, translated from the two Cargo.toml tables as the spec maps them (`extended-description` becomes the body of `description` under the Cargo `description` line; `section`, `priority`, `maintainer`; `recommends` per packager; `license-file` becomes `copyright` on deb and `LICENSE` on rpm; the two scripts; no `auto-req`)

```yaml
# The .deb and .rpm of mtuspy, built by .github/workflows/release-nfpm.yml from
# the musl archives. The workflow fills in VERSION, MTIME and ARCH, and STAGE,
# the unpacked mtuspy/ folder of one archive, before nfpm reads this file.
# Write no dollar-brace name in a comment either: the workflow fills in the
# whole file and stops at a name it does not know. nfpm adds no automatic
# requirements, so the static binary depends on nothing, as auto-req = "no"
# made sure under cargo-generate-rpm.
name: mtuspy
arch: "${ARCH}"
platform: linux
version: "${VERSION}"
release: "1"
# nfpm 2.47.0 ignores SOURCE_DATE_EPOCH, so the timestamp is set here.
mtime: "${MTIME}"
section: net
priority: optional
maintainer: Tobias Oetiker <tobi@oetiker.ch>
license: MIT
description: |
  Path MTU discovery tool using native ICMP with Don't Fragment bit
  Discovers the Path MTU to a network host. It sends ICMP echo requests with
  the Don't Fragment bit set and finds the largest packet that gets through
  with a binary search. A single static binary.
contents:
  - src: ${STAGE}/mtuspy
    dst: /usr/bin/mtuspy
    file_info:
      mode: 0755
  - src: ${STAGE}/man/mtuspy.1
    dst: /usr/share/man/man1/mtuspy.1
    file_info:
      mode: 0644
  - src: ${STAGE}/README.md
    dst: /usr/share/doc/mtuspy/README.md
    file_info:
      mode: 0644
  - src: ${STAGE}/LICENSE
    dst: /usr/share/doc/mtuspy/copyright
    packager: deb
    file_info:
      mode: 0644
  - src: ${STAGE}/LICENSE
    dst: /usr/share/doc/mtuspy/LICENSE
    packager: rpm
    type: doc
    file_info:
      mode: 0644
overrides:
  deb:
    # setcap comes from libcap2-bin; the postinst skips it when it is missing.
    recommends:
      - libcap2-bin
    scripts:
      postinstall: pkg/debian/postinst
  rpm:
    # libcap carries setcap on Fedora and RHEL.
    recommends:
      - libcap
    scripts:
      postinstall: pkg/rpm/post-install.sh
```

- [ ] **Step 6: `Cargo.toml`.** Delete from the line `[package.metadata.deb]` through the closing `]` of the `[package.metadata.generate-rpm]` assets, and the blank line after it, so `[dependencies]` is followed by a blank line and `[profile.release]`.

- [ ] **Step 7: Check locally**

```bash
cd /scratch/oetiker/claude-worktrees/mtuspy-release-pieces
grep -c $'\u2014' .github/workflows/*.yml nfpm.yaml        # 0 for every file
python3 /home/oetiker/checkouts/repo-infra/skills/repo-infra/scripts/repo_infra check
```

Expected: no em dash; the script's `callers` section reports no `problem` for `release-build.yml` and the three workflows it calls (the `pieces` and `administration` rows are what they were on `main`). Then dry-run the packaging step on fake archives with the pinned nfpm in a container, as Task 10's container test will:

```bash
mkdir -p $S/dry && cd $S/dry && rm -rf repo temp stage nfpm && mkdir temp nfpm
mkdir repo && cp -r /scratch/oetiker/claude-worktrees/mtuspy-release-pieces/nfpm.yaml /scratch/oetiker/claude-worktrees/mtuspy-release-pieces/pkg repo/
( cd repo && git init -q && git add -A && git commit -qm dry )
mkdir -p stage/mtuspy/man && printf '#!/bin/sh\n' > stage/mtuspy/mtuspy && chmod 755 stage/mtuspy/mtuspy
echo '.TH MTUSPY 1' > stage/mtuspy/man/mtuspy.1 && echo readme > stage/mtuspy/README.md && echo license > stage/mtuspy/LICENSE
for t in x86_64-unknown-linux-musl aarch64-unknown-linux-musl; do
  mkdir -p repo/archives/release-asset-$t && tar -czf repo/archives/release-asset-$t/mtuspy-0.0.0-$t.tar.gz -C stage mtuspy
done
gh release download v2.47.0 -R goreleaser/nfpm -p nfpm_2.47.0_Linux_x86_64.tar.gz -D nfpm
echo "0660ca602b2d2d2ae4781a06c692b3eeb9d437ffea05b831d76e41f4a3188783  nfpm/nfpm_2.47.0_Linux_x86_64.tar.gz" | sha256sum -c -
tar -xzf nfpm/nfpm_2.47.0_Linux_x86_64.tar.gz -C nfpm nfpm
python3 -c 'import sys, yaml; d = yaml.safe_load(open(sys.argv[1])); print(next(s for s in d["jobs"]["packages"]["steps"] if s.get("name") == "Build and read back the packages")["run"])' \
  /scratch/oetiker/claude-worktrees/mtuspy-release-pieces/.github/workflows/release-nfpm.yml > step.py
podman run --rm -v $S/dry:/w:Z -w /w/repo -e PATH=/w/nfpm:/usr/bin:/bin -e RUNNER_TEMP=/w/temp \
  -e VERSION=0.0.0 -e CONFIG=nfpm.yaml -e 'PACKAGERS={"deb": {}, "rpm": {}}' \
  -e 'ARCHIVES=x86_64-unknown-linux-musl aarch64-unknown-linux-musl' docker.io/library/ubuntu:24.04 bash -euc '
  apt-get update -qq && apt-get install -y -qq rpm python3 git >/dev/null
  python3 -I /w/step.py'
```

Expected: four lines `mtuspy_0.0.0-1_amd64.deb: version 0.0.0-1, 4 files`, `mtuspy-0.0.0-1.x86_64.rpm: version 0.0.0, 4 files` and the arm64/aarch64 pair. (A dry run on 2026-10-10 of the deb half on the host gave exactly the deb lines; the rpm half has not run anywhere yet.)

- [ ] **Step 8: [outward] Commit and push**

```bash
cd /scratch/oetiker/claude-worktrees/mtuspy-release-pieces
git add .github/workflows nfpm.yaml Cargo.toml
git commit -m "Split the release build into three workflows; packages by nfpm

The archives, the packages and the Homebrew bottles each get a workflow
shaped like the release pieces repo-infra is about to ship (D32), called
from release-build.yml. The man page is built once on Linux and passed
to every leg, so a release no longer ships pages from two pandoc
versions. illumos no longer asks for crt-static, which it does not have.
The packages are built by nfpm from the musl archives instead of by
cargo-deb and cargo-generate-rpm from target/, so Cargo.toml loses its
two package tables to nfpm.yaml.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
```

---

### Task 7: The proof run, compared with the baseline

**Interfaces:**
- Consumes: `$S/baseline-facts/` (Task 5).
- Produces: `$S/proof/` (artifacts), `$S/proof-facts/`, `$S/accepted.diff` (the package differences the owner accepted). Task 10 commits `$S/baseline-facts/packages` and `$S/accepted.diff`; Task 11 commits the bottle json files.

- [ ] **Step 1: Wait for the proof run**

```bash
gh run list -R oetiker/mtuspy --workflow proof.yml --branch proof/release-pieces --limit 1 --json databaseId,headSha
gh run watch <databaseId> -R oetiker/mtuspy --exit-status
echo <databaseId> > $S/proof-run-id
```

Expected: green, with jobs `build / binaries / Build the man pages`, seven `build / binaries / Build <target>`, `build / packages / Build the deb and rpm packages`, two `build / homebrew / Bottle on <os>` and `build / homebrew / Rewrite the formula`. A failure is fixed on this branch and pushed again; every fix is a change to a file the pieces will copy, so note it in the commit message.

- [ ] **Step 2: Download and collect**

```bash
gh run download "$(cat $S/proof-run-id)" -R oetiker/mtuspy -D $S/proof
mkdir -p $S/proof-facts/archives
for archive in $S/proof/release-asset-*/*.tar.gz; do
  tar -tzf "$archive" | LC_ALL=C sort > "$S/proof-facts/archives/$(basename "$archive").list"
done
for archive in $S/proof/release-asset-*/*.zip; do
  python3 -I -c 'import sys, zipfile; print("\n".join(sorted(zipfile.ZipFile(sys.argv[1]).namelist())))' "$archive" \
    > "$S/proof-facts/archives/$(basename "$archive").list"
done
podman run --rm -v $S:/s:Z docker.io/library/ubuntu:24.04 bash -euc '
  apt-get update -qq && apt-get install -y -qq rpm >/dev/null
  sh /s/collect.sh /s/proof/release-asset-packages /s/proof-facts/packages'
```

- [ ] **Step 3: Compare archive names and layout**

```bash
diff <(ls $S/baseline-facts/archives) <(ls $S/proof-facts/archives)
diff -r $S/baseline-facts/archives $S/proof-facts/archives
```

Expected: no output. The seven archive names and their file lists are the same.

- [ ] **Step 4: Compare the packages**

```bash
ls $S/proof/release-asset-packages
python3 -I $S/factsdiff.py $S/baseline-facts/packages $S/proof-facts/packages | tee $S/accepted.diff
```

Expected file names: `mtuspy_0.0.0-1_amd64.deb`, `mtuspy_0.0.0-1_arm64.deb`, `mtuspy-0.0.0-1.x86_64.rpm`, `mtuspy-0.0.0-1.aarch64.rpm` (the baseline's carry 0.1.3, the version cargo-deb took from Cargo.toml). The diff must show the same file paths and modes, the same `Package`, `Architecture`, `Section`, `Priority`, `Maintainer`, `Recommends` and `Description` on deb, the same rpm `Name`, `Arch`, `License`, `Summary` and `Recommends`, and the same postinst text. Read every remaining line of the diff next to `$S/edaptor-facts`, and write one sentence per difference saying why it is right (for example a doc file cargo-deb adds on its own) or fix `nfpm.yaml` and push again. **[ask the owner]** Show the owner the diff and the sentences; the accepted diff becomes the fixture of Task 10.

- [ ] **Step 5: Compare the formula and the bottles**

```bash
diff $S/baseline-facts/mtuspy.rb $S/proof/release-files/Formula/mtuspy.rb
ls $S/baseline/release-asset-bottle-*/ $S/proof/release-asset-bottle-*/
```

Expected: the formula differs only in the four archive `sha256` values and the bottle `sha256` values (both builds are separate compilations); the version line, the `root_url` and the bottle tags are the same. The bottle file names are the same.

- [ ] **Step 6: Keep the recorded bottle json for Task 11**

```bash
mkdir -p $S/fixtures/homebrew
cp $S/baseline/bottle-json-macos-14/*.bottle.json $S/baseline/bottle-json-macos-15-intel/*.bottle.json $S/fixtures/homebrew/
jq . $S/fixtures/homebrew/*.bottle.json | head -40
```

Expected: two files, one with the tag `arm64_sonoma`, one with the Intel tag of macOS 15, each with `filename`, `local_filename`, `sha256` and a `cellar` on the bottle or the tag.

---

### Task 8: Merge, the registry variable, the release, and every channel

- [ ] **Step 1: [outward] Drop `proof.yml`**

```bash
cd /scratch/oetiker/claude-worktrees/mtuspy-release-pieces
git rm .github/workflows/proof.yml
git commit -m "Drop the temporary proof workflow

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
gh pr ready -R oetiker/mtuspy proof/release-pieces
gh pr checks -R oetiker/mtuspy proof/release-pieces --watch
```

Expected: `ci-passed` green and `changelog-updated` skipped by the label.

- [ ] **Step 2: [outward] [ask the owner] Merge the pull request**

```bash
gh pr merge -R oetiker/mtuspy proof/release-pieces --merge
```

- [ ] **Step 3: [outward] [ask the owner] The registry user as a variable** (decision P10). The owner gives the Gitea user name (it is stored only as a secret today and cannot be read back).

```bash
gh variable set GITEA_PACKAGE_USER -R oetiker/mtuspy --body '<the user name the owner gives>'
gh api repos/oetiker/mtuspy/actions/variables --jq '.variables[].name'
```

Expected: `GITEA_PACKAGE_USER`. Ask the owner separately whether to delete the secret of the same name (`gh secret delete GITEA_PACKAGE_USER -R oetiker/mtuspy`); nothing reads it.

- [ ] **Step 4: [outward] Release mtuspy** (authorised by the owner for this work)

```bash
gh workflow run release-pr.yml -R oetiker/mtuspy --ref main -f release_type=feature
gh run list -R oetiker/mtuspy --workflow release-pr.yml --limit 1
gh run watch <id> -R oetiker/mtuspy --exit-status
gh pr list -R oetiker/mtuspy --head release/v0.2.0
gh release view v0.2.0 -R oetiker/mtuspy --json isDraft,assets --jq '.isDraft, .assets[].name'
```

Expected: version 0.2.0 (`CHANGES.md` has `### New` entries; the latest tag is v0.1.3). The draft carries the seven archives, `mtuspy_0.2.0-1_amd64.deb`, `mtuspy_0.2.0-1_arm64.deb`, `mtuspy-0.2.0-1.x86_64.rpm`, `mtuspy-0.2.0-1.aarch64.rpm`, `mtuspy-0.2.0.arm64_sonoma.bottle.tar.gz` and the Intel bottle when that leg built, plus `release-build.json`; the release pull request changes `CHANGES.md`, `Cargo.toml`, `Cargo.lock` and `Formula/mtuspy.rb`.

- [ ] **Step 5: [outward] [ask the owner] Merge the release pull request**, then watch the publish:

```bash
gh pr merge -R oetiker/mtuspy release/v0.2.0 --merge
gh run list -R oetiker/mtuspy --workflow release-publish.yml --limit 1
gh run watch <id> -R oetiker/mtuspy --exit-status
gh release view v0.2.0 -R oetiker/mtuspy --json isDraft --jq .isDraft
```

Expected: `publish`, `gitea` and `finalize` green; `false`.

- [ ] **Step 6: Install from every channel and run `mtuspy --version`**

GitHub release:

```bash
mkdir -p $S/install/github && cd $S/install/github
gh release download v0.2.0 -R oetiker/mtuspy -p 'mtuspy-0.2.0-x86_64-unknown-linux-musl.tar.gz'
tar -xzf mtuspy-0.2.0-x86_64-unknown-linux-musl.tar.gz && ./mtuspy/mtuspy --version && ls mtuspy/man
```

Expected: `mtuspy 0.2.0 (<build date>)` and `mtuspy.1`.

Gitea apt, the README snippet with `-y` added:

```bash
podman run --rm docker.io/library/debian:trixie bash -euxc '
  apt-get update -qq && apt-get install -y -qq sudo curl ca-certificates >/dev/null
  sudo install -d -m 0755 /etc/apt/keyrings
  sudo curl -fsSL -o /etc/apt/keyrings/gitea-oposs.asc https://gitea.oetiker.ch/api/packages/oposs/debian/repository.key
  echo "deb [signed-by=/etc/apt/keyrings/gitea-oposs.asc] https://gitea.oetiker.ch/api/packages/oposs/debian stable main" | sudo tee /etc/apt/sources.list.d/oposs.list
  sudo apt update && sudo apt install -y mtuspy
  mtuspy --version'
```

Gitea rpm, on dnf5 and on dnf4:

```bash
for image in docker.io/library/fedora:latest docker.io/library/rockylinux:9; do
  podman run --rm "$image" bash -euxc '
    dnf install -y -q sudo
    sudo curl -fsSL -o /etc/yum.repos.d/oposs.repo https://gitea.oetiker.ch/api/packages/oposs/rpm.repo
    sudo dnf install -y mtuspy
    mtuspy --version'
done
```

Homebrew on Linux (the formula installs the musl archive there). Check the image's Homebrew version first and run `brew trust` only on 6 or later; the image name `docker.io/homebrew/brew` is to be confirmed with `podman search homebrew/brew` before use:

```bash
podman run --rm docker.io/homebrew/brew:latest bash -euxc '
  brew --version
  brew tap oetiker/mtuspy https://github.com/oetiker/mtuspy
  if [ "$(brew --version | sed -n "1s/^Homebrew \([0-9][0-9]*\).*/\1/p")" -ge 6 ]; then brew trust --formula oetiker/mtuspy/mtuspy; fi
  brew install mtuspy
  mtuspy --version'
```

Homebrew on macOS: **[ask the owner]** to run on a Mac `brew tap oetiker/mtuspy https://github.com/oetiker/mtuspy`, `brew trust --formula oetiker/mtuspy/mtuspy`, `brew install mtuspy`, `mtuspy --version`, and to confirm that brew poured the bottle (`Pouring mtuspy-0.2.0.arm64_sonoma.bottle.tar.gz` on Apple silicon).

mise, isolated from the owner's own configuration:

```bash
export MISE_DATA_DIR=$S/mise/data MISE_CACHE_DIR=$S/mise/cache MISE_STATE_DIR=$S/mise/state \
  MISE_CONFIG_DIR=$S/mise/config MISE_GLOBAL_CONFIG_FILE=$S/mise/config/config.toml
mise use -g github:oetiker/mtuspy
mise exec github:oetiker/mtuspy -- mtuspy --version
```

Expected in every case: `mtuspy 0.2.0 (<build date>)`. A channel that fails is reported to the owner with the command and its output before Phase C starts: Phase C copies only what has published to every channel.

---
# Phase C: the three pieces in repo-infra

Work on a new branch `feat/release-pieces` from `main` (after Phase A merged), in a worktree. Each task copies one file from mtuspy's `main` at the merge of Task 8, replaces its first two lines (decision P2) with the marker and header below, and changes nothing else. `M=/home/oetiker/checkouts/mtuspy`; run `git -C $M fetch origin` first.

The copy step, the same for each piece (`<local>` and `<piece>` per task):

```bash
mkdir -p skills/repo-infra/assets/pieces/<piece>
git -C $M show origin/main:.github/workflows/<local>.yml > $S/<local>.yml
python3 -I - $S/<local>.yml $S/<piece>.header skills/repo-infra/assets/pieces/<piece>/<piece>.yml <<'EOF'
import sys
local, header, target = sys.argv[1:]
lines = open(local, encoding="utf-8").read().split("\n")
assert lines[0].startswith("# Local copy of the release piece"), lines[0]
assert lines[1].startswith("# repo-infra ships it (D32)") and lines[2] == "", lines[1:3]
body = "\n".join(lines[2:])
open(target, "w", encoding="utf-8").write(open(header, encoding="utf-8").read().rstrip("\n") + "\n" + body)
EOF
tail -n +3 $S/<local>.yml | cmp - <(sed -n '/^$/,$p' skills/repo-infra/assets/pieces/<piece>/<piece>.yml)
```

Expected: `cmp` prints nothing. The `.header` file holds the header block of the task, ending with the last `Call:` line.

Each task registers its piece in `skills/repo-infra/assets/manifest.json` under `pieces`, after `ri-release-source-tarball`:

```json
"<piece>": {
  "target": ".github/workflows/<piece>.yml",
  "group": "release-build"
}
```

and ends with `make generations`, `make catalogue` and `make check`.

### Task 9: `ri-release-rust-binaries`

**Files:**
- Create: `skills/repo-infra/assets/pieces/ri-release-rust-binaries/ri-release-rust-binaries.yml`, `.../CHANGES.md`
- Modify: `skills/repo-infra/assets/manifest.json`, `skills/repo-infra/assets/generations.json` (by `make generations`), `skills/repo-infra/references/catalogue.md` (by `make catalogue`)
- Test: `tests/test_release_rust_binaries.py`

**Interfaces:**
- Consumes: mtuspy's `.github/workflows/release-rust-binaries.yml` (Task 6, as merged in Task 8).
- Produces: the piece `ri-release-rust-binaries` with inputs `version`, `ref`, `bin`; jobs `man`, `binaries`; artifacts `man-pages`, `release-asset-<target>`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_release_rust_binaries.py
"""ri-release-rust-binaries (D32): the seven archives of a Rust program. The
build and the packing step run here on a fake target tree."""

import os
import pathlib
import subprocess
import tarfile

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIECE = (ROOT / "skills/repo-infra/assets/pieces/ri-release-rust-binaries/"
         "ri-release-rust-binaries.yml")
SHAPE = ROOT / "skills/repo-infra/references/project-shape.md"
TARGETS = ["x86_64-unknown-linux-musl", "aarch64-unknown-linux-musl", "x86_64-apple-darwin",
           "aarch64-apple-darwin", "x86_64-pc-windows-msvc", "aarch64-pc-windows-msvc",
           "x86_64-unknown-illumos"]


def doc():
    return yaml.safe_load(PIECE.read_text(encoding="utf-8"))


def step(job, name):
    return next(s for s in doc()["jobs"][job]["steps"] if s.get("name") == name)


def legs():
    return doc()["jobs"]["binaries"]["strategy"]["matrix"]["include"]


def test_the_matrix_builds_the_seven_native_targets_of_the_shape():
    assert sorted(leg["target"] for leg in legs()) == sorted(TARGETS)
    shape = SHAPE.read_text(encoding="utf-8")
    assert all(f"`{target}`" in shape for target in TARGETS)


def test_one_target_failing_does_not_cancel_the_others():
    assert doc()["jobs"]["binaries"]["strategy"]["fail-fast"] is False


def test_only_the_musl_legs_ask_for_a_static_crt():
    assert sorted(leg["target"] for leg in legs() if leg.get("static")) == [
        "aarch64-unknown-linux-musl", "x86_64-unknown-linux-musl"]


def test_linux_and_illumos_build_with_cross_pinned_by_version():
    assert sorted(leg["target"] for leg in legs() if leg.get("cross")) == [
        "aarch64-unknown-linux-musl", "x86_64-unknown-illumos", "x86_64-unknown-linux-musl"]
    assert step("binaries", "Install cross")["run"].strip() == (
        "cargo install cross --version 0.2.5 --locked")


def test_the_man_pages_are_built_once_on_linux_and_fetched_by_every_leg_but_windows():
    jobs = doc()["jobs"]
    assert jobs["binaries"]["needs"] == "man"
    assert jobs["man"]["runs-on"] == "ubuntu-latest"
    runs = [s.get("run", "") for s in jobs["man"]["steps"]]
    assert any("apt-get install -y pandoc" in r for r in runs)
    assert "make man" in [r.strip() for r in runs]
    assert jobs["man"]["steps"][-1]["with"]["name"] == "man-pages"
    fetch = step("binaries", "Fetch the man pages")
    assert fetch["with"] == {"name": "man-pages", "path": "man"}
    assert fetch["if"] == "${{ !matrix.windows }}"
    every_run = [s.get("run", "") for job in jobs.values() for s in job["steps"]]
    assert not any("brew install pandoc" in r for r in every_run)


def _stub(directory, name):
    path = directory / name
    path.write_text('#!/bin/sh\necho "%s $* RUSTFLAGS=${RUSTFLAGS-unset}"\n' % name)
    path.chmod(0o755)


@pytest.mark.parametrize("leg", legs(), ids=lambda leg: leg["target"])
def test_the_build_names_the_binary_and_sets_crt_static_only_on_a_static_leg(tmp_path, leg):
    stubs = tmp_path / "bin"
    stubs.mkdir()
    _stub(stubs, "cargo")
    _stub(stubs, "cross")
    env = {"PATH": f"{stubs}:/usr/bin:/bin", "BIN": "tool", "TARGET": leg["target"],
           "CROSS": "true" if leg.get("cross") else "",
           "STATIC": "true" if leg.get("static") else ""}
    done = subprocess.run(["bash", "-c", step("binaries", "Build")["run"]], env=env,
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    tool = "cross" if leg.get("cross") else "cargo"
    flags = "-C target-feature=+crt-static" if leg.get("static") else "unset"
    assert done.stdout.strip() == (
        f"{tool} build --release --bin tool --target {leg['target']} RUSTFLAGS={flags}")


def pack(tmp_path, pages):
    work = tmp_path / "src"
    release = work / "target/x86_64-unknown-linux-musl/release"
    release.mkdir(parents=True)
    (release / "tool").write_text("#!/bin/sh\n")
    (release / "tool").chmod(0o755)
    (work / "README.md").write_text("readme\n")
    (work / "LICENSE").write_text("license\n")
    (work / "man").mkdir()
    for page in pages:
        (work / "man" / page).write_text(".TH X\n")
    env = {"PATH": "/usr/bin:/bin", "BIN": "tool", "VERSION": "1.2.3",
           "TARGET": "x86_64-unknown-linux-musl"}
    return work, subprocess.run(["bash", "-c", step("binaries", "Pack the archive")["run"]],
                                cwd=work, env=env, capture_output=True, text=True)


def test_the_archive_holds_the_binary_every_man_page_the_readme_and_the_license(tmp_path):
    work, done = pack(tmp_path, ["tool.1", "toold.8"])
    assert done.returncode == 0, done.stdout + done.stderr
    archive = work / "dist/tool-1.2.3-x86_64-unknown-linux-musl.tar.gz"
    assert sorted(p.name for p in (work / "dist").iterdir()) == [archive.name]
    with tarfile.open(archive) as tar:
        members = {m.name: m for m in tar.getmembers()}
    assert sorted(n for n, m in members.items() if m.isfile()) == [
        "tool/LICENSE", "tool/README.md", "tool/man/tool.1", "tool/man/toold.8", "tool/tool"]
    assert members["tool/tool"].mode & 0o111


def test_an_archive_without_a_man_page_fails(tmp_path):
    _, done = pack(tmp_path, [])
    assert done.returncode == 1
    assert "no man page under man/" in done.stdout


def test_the_windows_zip_has_the_same_layout_without_man():
    zip_step = step("binaries", "Pack the zip")
    assert zip_step["shell"] == "pwsh" and zip_step["if"] == "${{ matrix.windows }}"
    run = zip_step["run"]
    assert "target/${env:TARGET}/release/${env:BIN}.exe" in run
    assert "Copy-Item README.md, LICENSE" in run
    assert "man/" not in run
    assert "dist/${env:BIN}-${env:VERSION}-${env:TARGET}.zip" in run


def test_every_leg_uploads_its_archive_as_a_release_asset():
    upload = doc()["jobs"]["binaries"]["steps"][-1]
    assert upload["with"] == {"name": "release-asset-${{ matrix.target }}", "path": "dist/*",
                              "if-no-files-found": "error"}
```

Run: `python3 -m pytest -q --basetemp=.pytest-tmp tests/test_release_rust_binaries.py`. Expected: FAIL, the piece does not exist.

- [ ] **Step 2: The header** `$S/ri-release-rust-binaries.header`

```yaml
# repo-infra: ri-release-rust-binaries v1
#
# Purpose: Build the release archives of a Rust program for the seven native targets (D32).
# Choose: The project is a Rust program users install (native-targets in references/project-shape.md).
# Supplies: Cargo.toml with the binary `bin`, README.md, LICENSE, and `make man` writing man/.
# Pieces: man, man-lua
# Produces: The artifacts release-asset-<target>, each holding <bin>-<version>-<target>.tar.gz (.zip on Windows); list all seven in release_assets.
# Call:
#   binaries:
#     uses: ./.github/workflows/ri-release-rust-binaries.yml
#     with:
#       version: ${{ inputs.version }}
#       ref: ${{ inputs.ref }}
#       bin: mytool
```

- [ ] **Step 3: Copy the file** with the copy step above (`<local>` = `release-rust-binaries`, `<piece>` = `ri-release-rust-binaries`), write `skills/repo-infra/assets/pieces/ri-release-rust-binaries/CHANGES.md`:

```markdown
# ri-release-rust-binaries

Upgrade notes, newest first. Each section says what a caller or
.github/repo-infra.json must change to take that version.

## v1

First version, proven as mtuspy's release-rust-binaries.yml. Call it from release-build.yml as the catalogue shows, with `bin` naming the binary. It runs `make man`, so the repository carries the man pieces, and it builds seven archives that release_assets lists.
```

and add the manifest entry.

- [ ] **Step 4: Register and test**

Run: `make generations && make catalogue && python3 -m pytest -q --basetemp=.pytest-tmp tests/test_release_rust_binaries.py tests/test_pieces.py tests/test_catalogue.py tests/test_generations.py`
Expected: PASS. `test_pieces.py` checks the marker, the descriptions, the timeouts, the action pins, the `Call:` snippet and the `ref` contract of the new piece.

- [ ] **Step 5: Gate and commit**

Run: `make check` (timeout 600000). Expected: PASS.

```bash
git add skills/repo-infra/assets tests/test_release_rust_binaries.py skills/repo-infra/references/catalogue.md
git commit -m "Add ri-release-rust-binaries v1 (D32)

Copied from mtuspy's release-rust-binaries.yml, which built and
published mtuspy 0.2.0, with only the marker and the header changed. It
builds the seven native targets, the man pages once on Linux, and packs
each archive by the layout the packaging and Homebrew pieces read.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: `ri-release-nfpm`

**Files:**
- Create: `skills/repo-infra/assets/pieces/ri-release-nfpm/ri-release-nfpm.yml`, `.../CHANGES.md`
- Create: `tests/nfpm_facts.py`, `tests/test_release_nfpm.py`
- Create: `tests/fixtures/nfpm/repo/nfpm.yaml`, `tests/fixtures/nfpm/repo/pkg/debian/postinst` (mode 755), `tests/fixtures/nfpm/repo/pkg/rpm/post-install.sh`, `tests/fixtures/nfpm/facts.sh`, `tests/fixtures/nfpm/collect.sh`, `tests/fixtures/nfpm/baseline/{deb-amd64,deb-arm64,rpm-x86_64,rpm-aarch64}/{files,control,postinst}`, `tests/fixtures/nfpm/accepted.diff`
- Modify: `manifest.json`, `generations.json`, `catalogue.md`

**Interfaces:**
- Consumes: mtuspy's `release-nfpm.yml`, `nfpm.yaml`, `pkg/` (Task 6), `$S/baseline-facts/packages`, `$S/accepted.diff`, `$S/facts.sh`, `$S/collect.sh` (Tasks 5 and 7).
- Produces: the piece `ri-release-nfpm` with inputs `version`, `ref`, `config`, `packagers`, `archives`; artifact `release-asset-packages`; `nfpm_facts.facts_diff(baseline, actual) -> str`.

- [ ] **Step 1: Fixtures**

```bash
mkdir -p tests/fixtures/nfpm/repo
git -C $M show origin/main:nfpm.yaml > tests/fixtures/nfpm/repo/nfpm.yaml
mkdir -p tests/fixtures/nfpm/repo/pkg/debian tests/fixtures/nfpm/repo/pkg/rpm
git -C $M show origin/main:pkg/debian/postinst > tests/fixtures/nfpm/repo/pkg/debian/postinst
chmod 755 tests/fixtures/nfpm/repo/pkg/debian/postinst
git -C $M show origin/main:pkg/rpm/post-install.sh > tests/fixtures/nfpm/repo/pkg/rpm/post-install.sh
cp $S/facts.sh $S/collect.sh tests/fixtures/nfpm/
cp -r $S/baseline-facts/packages tests/fixtures/nfpm/baseline
cp $S/accepted.diff tests/fixtures/nfpm/accepted.diff
```

`tests/nfpm_facts.py` holds `facts_diff` exactly as `$S/factsdiff.py` (Task 5, Step 6), without the `__main__` block.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_release_nfpm.py
"""ri-release-nfpm (D32): the packaging step, run on fake archives. The input
checks run on the host and stop before nfpm; the packages are built in a
podman container with the pinned nfpm and compared with mtuspy's baseline
packages (tests/fixtures/nfpm/)."""

import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import tarfile
import urllib.request

import pytest
import yaml
from nfpm_facts import facts_diff

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIECE = ROOT / "skills/repo-infra/assets/pieces/ri-release-nfpm/ri-release-nfpm.yml"
GITEA = ROOT / "skills/repo-infra/assets/pieces/workflow-lib/lib/gitea.js"
FIXTURE = ROOT / "tests/fixtures/nfpm"
TARGETS = ["x86_64-unknown-linux-musl", "aarch64-unknown-linux-musl"]
BOTH = '{"deb": {}, "rpm": {}}'
IMAGE = "localhost/repo-infra-nfpm-test"
CONTAINERFILE = ("FROM docker.io/library/ubuntu:24.04\n"
                 "RUN apt-get update && apt-get install -y --no-install-recommends "
                 "rpm python3 git && rm -rf /var/lib/apt/lists/*\n")


def steps():
    doc = yaml.safe_load(PIECE.read_text(encoding="utf-8"))
    return {s.get("name"): s for s in doc["jobs"]["packages"]["steps"]}


def build_step():
    return steps()["Build and read back the packages"]["run"]


def checkout(tmp_path, config=None, archives=TARGETS, flat=False, extra=False):
    """A checkout with mtuspy's nfpm.yaml and scripts, one commit, and the
    archives as download-artifact leaves them."""
    work = tmp_path / "repo"
    shutil.copytree(FIXTURE / "repo", work)
    if config is not None:
        (work / "nfpm.yaml").write_text(config)
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "fixture"]):
        subprocess.run(["git", *args], cwd=work, check=True)
    stage = tmp_path / "stage" / "mtuspy"
    (stage / "man").mkdir(parents=True)
    (stage / "mtuspy").write_text("#!/bin/sh\necho mtuspy\n")
    (stage / "mtuspy").chmod(0o755)
    (stage / "man" / "mtuspy.1").write_text(".TH MTUSPY 1\n")
    (stage / "README.md").write_text("readme\n")
    (stage / "LICENSE").write_text("license\n")
    for target in archives:
        folder = work / "archives" / f"release-asset-{target}"
        folder.mkdir(parents=True)
        names = [f"mtuspy-0.0.0-{target}.tar.gz"] + (["second.tar.gz"] if extra else [])
        for name in names:
            with tarfile.open(folder / name, "w:gz") as tar:
                if flat:
                    tar.add(stage / "mtuspy", arcname="mtuspy")
                    tar.add(stage / "README.md", arcname="README.md")
                else:
                    tar.add(stage, arcname="mtuspy")
    (tmp_path / "temp").mkdir()
    return work


def on_host(tmp_path, work, packagers=BOTH, archives=" ".join(TARGETS), nfpm_writes="x"):
    """The step with a stand-in nfpm that writes `nfpm_writes` into --target."""
    stubs = tmp_path / "bin"
    stubs.mkdir(exist_ok=True)
    (stubs / "nfpm").write_text(
        '#!/bin/sh\nwhile [ $# -gt 0 ]; do [ "$1" = --target ] && dir=$2; shift; done\n'
        ': > "$dir/$NFPM_WRITES"\n')
    (stubs / "nfpm").chmod(0o755)
    script = tmp_path / "step.py"
    script.write_text(build_step())
    env = {**os.environ, "PATH": f"{stubs}:{os.environ['PATH']}",
           "RUNNER_TEMP": str(tmp_path / "temp"), "VERSION": "0.0.0", "CONFIG": "nfpm.yaml",
           "PACKAGERS": packagers, "ARCHIVES": archives, "NFPM_WRITES": nfpm_writes}
    return subprocess.run(["python3", "-I", str(script)], cwd=work, env=env,
                          capture_output=True, text=True)


def test_nfpm_is_pinned_by_version_and_sha256():
    install = steps()["Install nfpm"]
    assert install["env"] == {
        "NFPM_VERSION": "2.47.0",
        "NFPM_SHA256": "0660ca602b2d2d2ae4781a06c692b3eeb9d437ffea05b831d76e41f4a3188783"}
    assert "sha256sum -c -" in install["run"]


def test_the_name_patterns_are_the_ones_ri_publish_gitea_uploads():
    js, py = GITEA.read_text(encoding="utf-8"), build_step()
    for kind in ("DEB", "RPM"):
        js_pattern = re.search(rf"^const {kind} = /(.+)/;$", js, re.M).group(1)
        py_pattern = re.search(rf'^{kind} = re\.compile\(r"(.+)"\)$', py, re.M).group(1)
        assert js_pattern == py_pattern, kind


@pytest.mark.parametrize("packagers,message", [
    ("{deb}", "packagers is not JSON"),
    ('{"deb": "x"}', "packagers must be a JSON object"),
    ("{}", "packagers must be a JSON object"),
    ('{"deb": {"NAME": 1}}', "packagers must be a JSON object"),
    ('{"apk": {}}', "packagers names apk"),
    ('{"deb": {"VERSION": "9"}}', "packagers.deb sets VERSION, which this workflow sets itself"),
    ('{"rpm": {"STAGE": "/", "ARCH": "noarch"}}', "packagers.rpm sets ARCH, STAGE"),
])
def test_a_bad_packagers_input_fails_naming_it(tmp_path, packagers, message):
    done = on_host(tmp_path, checkout(tmp_path), packagers=packagers)
    assert done.returncode == 1
    assert message in done.stdout
    assert "Traceback" not in done.stderr


@pytest.mark.parametrize("archives,message", [
    ("", "archives names no target"),
    ("x86_64-unknown-illumos", "no package architecture is known for x86_64-unknown-illumos"),
])
def test_an_archives_input_without_a_known_target_fails(tmp_path, archives, message):
    done = on_host(tmp_path, checkout(tmp_path), archives=archives)
    assert done.returncode == 1 and message in done.stdout


def test_a_missing_archive_fails(tmp_path):
    done = on_host(tmp_path, checkout(tmp_path, archives=TARGETS[:1]))
    assert done.returncode == 1
    assert "release-asset-aarch64-unknown-linux-musl holds 0 .tar.gz files" in done.stdout


def test_two_archives_in_one_artifact_fail(tmp_path):
    done = on_host(tmp_path, checkout(tmp_path, extra=True))
    assert done.returncode == 1 and "holds 2 .tar.gz files" in done.stdout


def test_an_archive_without_one_top_folder_fails(tmp_path):
    done = on_host(tmp_path, checkout(tmp_path, flat=True))
    assert done.returncode == 1 and "must hold one folder" in done.stdout


def test_a_variable_nobody_sets_fails(tmp_path):
    config = (FIXTURE / "repo/nfpm.yaml").read_text() + "homepage: ${HOMEPAGE}\n"
    done = on_host(tmp_path, checkout(tmp_path, config=config))
    assert done.returncode == 1
    assert "uses ${HOMEPAGE}, which neither this workflow nor packagers sets" in done.stdout


def test_a_package_name_gitea_refuses_fails(tmp_path):
    done = on_host(tmp_path, checkout(tmp_path), packagers='{"deb": {}}',
                   nfpm_writes="Mtuspy_0.0.0-1_amd64.deb")
    assert done.returncode == 1
    assert "Mtuspy_0.0.0-1_amd64.deb is not name_version_arch.deb" in done.stdout


@pytest.fixture(scope="session")
def nfpm(tmp_path_factory):
    env = steps()["Install nfpm"]["env"]
    name = f"nfpm_{env['NFPM_VERSION']}_Linux_x86_64.tar.gz"
    url = f"https://github.com/goreleaser/nfpm/releases/download/v{env['NFPM_VERSION']}/{name}"
    data = urllib.request.urlopen(url, timeout=120).read()
    assert hashlib.sha256(data).hexdigest() == env["NFPM_SHA256"]
    folder = tmp_path_factory.mktemp("nfpm")
    (folder / name).write_bytes(data)
    with tarfile.open(folder / name) as tar:
        tar.extract("nfpm", folder, filter="data")
    return folder


@pytest.fixture(scope="session")
def image(tmp_path_factory):
    if shutil.which("podman") is None:
        pytest.skip("podman is not installed")
    context = tmp_path_factory.mktemp("nfpm-image")
    (context / "Containerfile").write_text(CONTAINERFILE)
    subprocess.run(["podman", "build", "-q", "-t", IMAGE, str(context)], check=True,
                   capture_output=True, timeout=900)
    return IMAGE


@pytest.mark.container
def test_the_packages_match_the_baseline_but_for_the_accepted_differences(
        tmp_path, image, nfpm):
    work = checkout(tmp_path)
    (tmp_path / "step.py").write_text(build_step())
    done = subprocess.run(
        ["podman", "run", "--rm", "-v", f"{tmp_path}:/w:Z", "-v", f"{nfpm}:/opt/nfpm:ro",
         "-w", "/w/repo", "-e", "PATH=/opt/nfpm:/usr/bin:/bin", "-e", "RUNNER_TEMP=/w/temp",
         "-e", "VERSION=0.0.0", "-e", "CONFIG=nfpm.yaml", "-e", f"PACKAGERS={BOTH}",
         "-e", f"ARCHIVES={' '.join(TARGETS)}", image, "python3", "-I", "/w/step.py"],
        capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stdout + done.stderr
    assert sorted(p.name for p in (work / "packages").iterdir()) == [
        "mtuspy-0.0.0-1.aarch64.rpm", "mtuspy-0.0.0-1.x86_64.rpm",
        "mtuspy_0.0.0-1_amd64.deb", "mtuspy_0.0.0-1_arm64.deb"]
    subprocess.run(["podman", "run", "--rm", "-v", f"{tmp_path}:/w:Z", "-v", f"{FIXTURE}:/f:ro",
                    image, "sh", "/f/collect.sh", "/w/repo/packages", "/w/facts"],
                   check=True, capture_output=True, timeout=600)
    assert facts_diff(FIXTURE / "baseline", tmp_path / "facts") == (
        FIXTURE / "accepted.diff").read_text(encoding="utf-8")
```

Run: `python3 -m pytest -q --basetemp=.pytest-tmp tests/test_release_nfpm.py`. Expected: FAIL, the piece does not exist.

- [ ] **Step 3: The header** `$S/ri-release-nfpm.header`

```yaml
# repo-infra: ri-release-nfpm v1
#
# Purpose: Build .deb and .rpm packages with nfpm from the musl archives, and read each back (D32).
# Choose: The project is a Rust program users install on Linux (linux-packages in references/project-shape.md).
# Supplies: An nfpm config whose contents take their sources from STAGE; every dollar-brace name in it is set by the piece or by packagers.
# Pieces: ri-release-rust-binaries
# Produces: The artifact release-asset-packages, <bin>_<version>-1_<arch>.deb and <bin>-<version>-1.<arch>.rpm; list them in release_assets.
# Call:
#   packages:
#     needs: binaries
#     uses: ./.github/workflows/ri-release-nfpm.yml
#     with:
#       version: ${{ inputs.version }}
#       ref: ${{ inputs.ref }}
#       config: nfpm.yaml
#       packagers: '{"deb": {}, "rpm": {}}'
#       archives: x86_64-unknown-linux-musl aarch64-unknown-linux-musl
```

- [ ] **Step 4: Copy the file** (`<local>` = `release-nfpm`, `<piece>` = `ri-release-nfpm`), write `CHANGES.md`:

```markdown
# ri-release-nfpm

Upgrade notes, newest first. Each section says what a caller or
.github/repo-infra.json must change to take that version.

## v1

First version, proven as mtuspy's release-nfpm.yml. Move the package tables of Cargo.toml into an nfpm config whose contents take their sources from STAGE, and call the piece after ri-release-rust-binaries as the catalogue shows. The file names stay those of cargo-deb and cargo-generate-rpm, so release_assets does not change.
```

and add the manifest entry.

- [ ] **Step 5: Register and test**

Run: `make generations && make catalogue && python3 -m pytest -q --basetemp=.pytest-tmp tests/test_release_nfpm.py tests/test_pieces.py tests/test_catalogue.py`
Expected: PASS (the container test is deselected here).

Run: `systemd-run --user --scope -p MemoryMax=4G -- python3 -m pytest --basetemp=.pytest-tmp -m container -v tests/test_release_nfpm.py` (timeout 600000).
Expected: PASS. It fails when the packages differ from the baseline by anything the owner did not accept in Task 7.

- [ ] **Step 6: Gate and commit**

Run: `make check` (timeout 600000). Expected: PASS.

```bash
git add skills/repo-infra/assets skills/repo-infra/references/catalogue.md tests/nfpm_facts.py tests/test_release_nfpm.py tests/fixtures/nfpm
git commit -m "Add ri-release-nfpm v1 (D32)

Copied from mtuspy's release-nfpm.yml, which built the packages of
mtuspy 0.2.0, with only the marker and the header changed. v1 has the
archives mode only. The container test builds the packages with the
pinned nfpm and compares them with the cargo-deb and cargo-generate-rpm
packages of mtuspy's baseline run; the accepted differences are the
fixture.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: `ri-release-homebrew`

**Files:**
- Create: `skills/repo-infra/assets/pieces/ri-release-homebrew/ri-release-homebrew.yml`, `.../CHANGES.md`
- Create: `tests/test_release_homebrew.py`, `tests/fixtures/homebrew/*.bottle.json` (from `$S/fixtures/homebrew/`, Task 7 Step 6)
- Modify: `manifest.json`, `generations.json`, `catalogue.md`

**Interfaces:**
- Consumes: mtuspy's `release-homebrew.yml`; the formula template of `references/project-shape.md` (Task 2).
- Produces: the piece `ri-release-homebrew` with inputs `version`, `ref`, `bin`; jobs `bottles`, `formula`; artifacts `release-asset-bottle-<os>`, `bottle-json-<os>`, `release-files`.

- [ ] **Step 1: Fixture:** `mkdir -p tests/fixtures/homebrew && cp $S/fixtures/homebrew/*.bottle.json tests/fixtures/homebrew/`

- [ ] **Step 2: Write the failing test**

```python
# tests/test_release_homebrew.py
"""ri-release-homebrew (D32): the local-tap rewrite, the bottle rename and the
formula rewrite, run on the formula template of references/project-shape.md
with fake archives and the bottle json of mtuspy's baseline run."""

import hashlib
import json
import pathlib
import re
import shutil
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIECE = ROOT / "skills/repo-infra/assets/pieces/ri-release-homebrew/ri-release-homebrew.yml"
SHAPE = ROOT / "skills/repo-infra/references/project-shape.md"
JSONS = sorted((ROOT / "tests/fixtures/homebrew").glob("*.bottle.json"))
BIN, VERSION, REPO = "mtuspy", "0.0.0", "oetiker/mtuspy"
MARKERS = {"mac-arm": "aarch64-apple-darwin", "mac-x86": "x86_64-apple-darwin",
           "linux-x86": "x86_64-unknown-linux-musl", "linux-arm": "aarch64-unknown-linux-musl"}


@pytest.fixture(autouse=True)
def tools(require):
    require("jq", "shasum", "sha256sum", "awk")


def doc():
    return yaml.safe_load(PIECE.read_text(encoding="utf-8"))


def script(job, name):
    return next(s for s in doc()["jobs"][job]["steps"] if s.get("name") == name)["run"]


def template():
    section = SHAPE.read_text(encoding="utf-8").split("\n## Formula template\n", 1)[1]
    ruby = re.search(r"```ruby\n(.*?)```", section, re.S).group(1)
    for placeholder, value in {"<Class>": "Mtuspy", "<one-line description>": "Path MTU",
                               "<owner>": "oetiker", "<repo>": "mtuspy",
                               "<SPDX license>": "MIT", "<bin>": BIN}.items():
        ruby = ruby.replace(placeholder, value)
    assert not re.search(r"<[A-Za-z -]+>", ruby), "a placeholder is left"
    return ruby


def tags(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return {tag: entry for formula in data.values()
            for tag, entry in formula["bottle"]["tags"].items()}


def tree(tmp_path, formula=None):
    work = tmp_path / "work"
    (work / "Formula").mkdir(parents=True)
    (work / "Formula" / f"{BIN}.rb").write_text(template() if formula is None else formula)
    for folder in ("dist", "artifacts", "bottles"):
        (work / folder).mkdir()
    shas = {}
    for target in MARKERS.values():
        data = f"{BIN} archive for {target}\n".encode()
        name = f"{BIN}-{VERSION}-{target}.tar.gz"
        (work / "artifacts" / name).write_bytes(data)
        if target.endswith("apple-darwin"):
            (work / "dist" / name).write_bytes(data)
        shas[target] = hashlib.sha256(data).hexdigest()
    (tmp_path / "temp").mkdir()
    return work, shas


def run(tmp_path, work, job, name):
    env = {"PATH": "/usr/bin:/bin", "BIN": BIN, "VERSION": VERSION,
           "GITHUB_REPOSITORY": REPO, "RUNNER_TEMP": str(tmp_path / "temp")}
    return subprocess.run(["bash", "-c", script(job, name)], cwd=work, env=env,
                          capture_output=True, text=True)


def add_bottles(work, jsons, built=True):
    for path in jsons:
        shutil.copy(path, work / "bottles" / path.name)
        if built:
            for entry in tags(path).values():
                (work / "artifacts" / entry["filename"]).write_bytes(b"bottle")


def formula(work):
    return (work / "Formula" / f"{BIN}.rb").read_text()


def block(text):
    return text.split("  # BOTTLE-START\n", 1)[1].split("  # BOTTLE-END", 1)[0]


def test_the_fixture_holds_both_recorded_bottles():
    assert len(JSONS) == 2
    assert "arm64_sonoma" in {tag for path in JSONS for tag in tags(path)}


def test_the_bottle_legs_and_the_formula_condition():
    jobs = doc()["jobs"]
    assert jobs["bottles"]["strategy"]["matrix"]["include"] == [
        {"os": "macos-14"}, {"os": "macos-15-intel", "optional": True}]
    assert jobs["bottles"]["continue-on-error"] == "${{ matrix.optional || false }}"
    assert jobs["formula"]["needs"] == "bottles"
    assert jobs["formula"]["if"] == "${{ !cancelled() }}"


def test_brew_trust_runs_on_homebrew_6_and_a_failure_is_not_swallowed():
    tap = script("bottles", "Local tap")
    assert '-ge 6 ]' in tap and "brew trust --formula" in tap and "|| true" not in tap


def test_the_root_url_comes_from_the_repository_of_the_run():
    text = PIECE.read_text(encoding="utf-8")
    assert text.count("https://github.com/$GITHUB_REPOSITORY/releases/download/v$VERSION") == 2
    assert "oetiker" not in text


def test_the_local_tap_points_the_mac_urls_at_the_built_archives(tmp_path):
    work, shas = tree(tmp_path)
    done = run(tmp_path, work, "bottles", "Point the formula at the built archives")
    assert done.returncode == 0, done.stdout + done.stderr
    local = (tmp_path / "temp/local-formula.rb").read_text()
    for marker in ("mac-arm", "mac-x86"):
        target = MARKERS[marker]
        assert f'url "file://{work}/dist/{BIN}-{VERSION}-{target}.tar.gz"' in local
        assert f'sha256 "{shas[target]}" # {marker}' in local
    assert local.count("/releases/download/v#{version}/") == 2
    assert f'  version "{VERSION}"' in local
    assert "  # BOTTLE-START\n  # BOTTLE-END" in local


@pytest.mark.parametrize("damage", ["deleted", "blank line", "comment"])
def test_a_mac_sha256_line_without_its_url_line_directly_above_fails(tmp_path, damage):
    lines = template().splitlines(keepends=True)
    i = next(n for n, line in enumerate(lines) if line.rstrip().endswith("# mac-x86"))
    if damage == "deleted":
        del lines[i - 1]
    else:
        lines.insert(i, "\n" if damage == "blank line" else "      # the Intel archive\n")
    work, _ = tree(tmp_path, "".join(lines))
    done = run(tmp_path, work, "bottles", "Point the formula at the built archives")
    assert done.returncode == 1
    assert "no url line directly above the # mac-x86 sha256 line" in done.stdout


def test_a_missing_mac_archive_fails_the_local_tap(tmp_path):
    work, _ = tree(tmp_path)
    (work / "dist" / f"{BIN}-{VERSION}-x86_64-apple-darwin.tar.gz").unlink()
    done = run(tmp_path, work, "bottles", "Point the formula at the built archives")
    assert done.returncode == 1 and "was not built" in done.stdout


def test_the_bottles_get_the_names_their_json_records(tmp_path):
    work, _ = tree(tmp_path)
    for path in JSONS:
        shutil.copy(path, work / path.name)
        for entry in tags(path).values():
            (work / entry["local_filename"]).write_bytes(b"bottle")
    done = run(tmp_path, work, "bottles", "Rename the bottles")
    assert done.returncode == 0, done.stdout + done.stderr
    expected = [e["filename"] for p in JSONS for e in tags(p).values()] + [p.name for p in JSONS]
    assert sorted(p.name for p in (work / "bottle").iterdir()) == sorted(expected)


def test_two_bottles_give_the_version_the_four_checksums_and_both_bottles(tmp_path):
    work, shas = tree(tmp_path)
    add_bottles(work, JSONS)
    done = run(tmp_path, work, "formula", "Rewrite the formula")
    assert done.returncode == 0, done.stdout + done.stderr
    text = formula(work)
    assert f'  version "{VERSION}"' in text
    for marker, target in MARKERS.items():
        assert f'sha256 "{shas[target]}" # {marker}' in text
    inside = block(text)
    assert f'root_url "https://github.com/{REPO}/releases/download/v{VERSION}"' in inside
    for path in JSONS:
        for tag, entry in tags(path).items():
            assert f'{tag}: "{entry["sha256"]}"' in inside
    assert (work / "release-files/Formula" / f"{BIN}.rb").read_text() == text


def test_the_optional_bottle_missing_still_publishes_the_other(tmp_path):
    work, _ = tree(tmp_path)
    arm = [p for p in JSONS if "arm64_sonoma" in tags(p)]
    add_bottles(work, arm)
    done = run(tmp_path, work, "formula", "Rewrite the formula")
    assert done.returncode == 0, done.stdout + done.stderr
    assert block(formula(work)).count("sha256 cellar:") == len(tags(arm[0]))


def test_zero_bottles_fail(tmp_path):
    work, _ = tree(tmp_path)
    done = run(tmp_path, work, "formula", "Rewrite the formula")
    assert done.returncode == 1 and "no bottles were built" in done.stdout


def test_a_bottle_missing_under_its_recorded_name_fails(tmp_path):
    work, _ = tree(tmp_path)
    add_bottles(work, JSONS, built=False)
    done = run(tmp_path, work, "formula", "Rewrite the formula")
    assert done.returncode == 1 and "was not built under that name" in done.stdout


@pytest.mark.parametrize("marker", ["mac-arm", "mac-x86", "linux-x86", "linux-arm",
                                    "BOTTLE-START", "BOTTLE-END"])
def test_a_missing_marker_fails(tmp_path, marker):
    work, _ = tree(tmp_path, template().replace(f" # {marker}", ""))
    add_bottles(work, JSONS)
    done = run(tmp_path, work, "formula", "Rewrite the formula")
    assert done.returncode == 1 and f"the marker # {marker} is gone" in done.stdout


def test_a_second_run_changes_nothing(tmp_path):
    work, _ = tree(tmp_path)
    add_bottles(work, JSONS)
    assert run(tmp_path, work, "formula", "Rewrite the formula").returncode == 0
    first = formula(work)
    assert run(tmp_path, work, "formula", "Rewrite the formula").returncode == 0
    assert formula(work) == first


def test_the_previous_release_block_is_replaced_whole(tmp_path):
    old = ('  # BOTTLE-START\n  bottle do\n'
           '    root_url "https://github.com/oetiker/mtuspy/releases/download/v9.9.9"\n'
           '    sha256 cellar: :any_skip_relocation, old_tag: "' + "1" * 64 + '"\n'
           '  end\n  # BOTTLE-END')
    work, _ = tree(tmp_path, template().replace("  # BOTTLE-START\n  # BOTTLE-END", old))
    add_bottles(work, JSONS)
    assert run(tmp_path, work, "formula", "Rewrite the formula").returncode == 0
    inside = block(formula(work))
    assert "v9.9.9" not in inside and "old_tag" not in inside
```

Run: `python3 -m pytest -q --basetemp=.pytest-tmp tests/test_release_homebrew.py`. Expected: FAIL, the piece does not exist.

- [ ] **Step 3: The header** `$S/ri-release-homebrew.header`

```yaml
# repo-infra: ri-release-homebrew v1
#
# Purpose: Bottle the formula on macOS and rewrite Formula/<bin>.rb for the release (D32).
# Choose: The project is a Rust program users install with Homebrew (homebrew in references/project-shape.md).
# Supplies: Formula/<bin>.rb from the template in references/project-shape.md, listed in release_files.
# Pieces: ri-release-rust-binaries
# Produces: The artifacts release-asset-bottle-<os> (list the arm64 bottle in release_assets) and release-files with the formula; no other job may write release-files.
# Call:
#   homebrew:
#     needs: binaries
#     uses: ./.github/workflows/ri-release-homebrew.yml
#     with:
#       version: ${{ inputs.version }}
#       ref: ${{ inputs.ref }}
#       bin: mytool
```

- [ ] **Step 4: Copy the file** (`<local>` = `release-homebrew`, `<piece>` = `ri-release-homebrew`), write `CHANGES.md`:

```markdown
# ri-release-homebrew

Upgrade notes, newest first. Each section says what a caller or
.github/repo-infra.json must change to take that version.

## v1

First version, proven as mtuspy's release-homebrew.yml. The formula follows the template in references/project-shape.md: each url line directly above its sha256 line, the four sha256 marker comments, and the BOTTLE markers. Remove any other job that writes release-files, and call the piece after ri-release-rust-binaries as the catalogue shows.
```

and add the manifest entry.

- [ ] **Step 5: Register, test, gate, commit**

Run: `make generations && make catalogue && make check` (timeout 600000). Expected: PASS.

```bash
git add skills/repo-infra/assets skills/repo-infra/references/catalogue.md tests/test_release_homebrew.py tests/fixtures/homebrew
git commit -m "Add ri-release-homebrew v1 (D32)

Copied from mtuspy's release-homebrew.yml, which bottled and rewrote the
formula of mtuspy 0.2.0, with only the marker and the header changed.
The tests run the local-tap rewrite, the rename and the formula rewrite
on the formula template of project-shape.md with the bottle json of
mtuspy's baseline run.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Name the pieces in the shape, changelog, and the repo-infra release

**Files:**
- Modify: `skills/repo-infra/references/project-shape.md`, `skills/repo-infra/references/onboarding.md`, `CHANGES.md`
- Test: `tests/test_project_shape.py`

- [ ] **Step 1: Failing test** (append to `tests/test_project_shape.py`)

```python
def test_the_rust_rules_name_the_release_pieces():
    bodies = {heading.strip("`"): body for heading, body in rules()}
    assert "`ri-release-rust-binaries`" in bodies["native-targets"]
    assert "`ri-release-nfpm`" in bodies["linux-packages"]
    assert "`ri-release-homebrew`" in bodies["homebrew"]
    assert "`ri-release-homebrew` rewrites" in section("Formula template")
```

Run it. Expected: FAIL.

- [ ] **Step 2: Amend `project-shape.md`**

- `native-targets`, Met by: `Met by: \`ri-release-rust-binaries\`. mise's \`github:\` backend picks an asset by these names, so \`mise use -g github:<owner>/<name>\` works without further setup.`
- `linux-packages`, first bullet: `- a Rust program: amd64 and arm64 packages built from the musl archives by \`ri-release-nfpm\`;`
- `homebrew`, Met by: `Met by: For a Rust program, \`ri-release-homebrew\`, which bottles the formula and rewrites it on each release from the template under "Formula template". For an interpreted program, a formula that builds from the source archive.`
- `## Formula template`, first sentence: `\`ri-release-homebrew\` rewrites the \`version\` line, ...` (the rest unchanged).

In `onboarding.md`, "Candidates a repository's files suggest but do not decide", add:

```markdown
- `Cargo.toml` with a binary users install suggests `ri-release-rust-binaries`,
  `ri-release-nfpm` with an `nfpm.yaml`, and `ri-release-homebrew` with
  `Formula/<bin>.rb` from the template in `references/project-shape.md`.
```

- [ ] **Step 3: Changelog** under `## [Unreleased]`, `### New`:

```markdown
- `ri-release-rust-binaries` builds the release archives of a Rust program for Linux (static, x86_64 and aarch64), macOS (Intel and Apple silicon), Windows (x86_64 and arm64) and illumos, each with the binary, every man page, the README and the licence. Install it with `apply --item ri-release-rust-binaries` (#53).
- `ri-release-nfpm` builds `.deb` and `.rpm` packages for amd64 and arm64 from the static Linux archives with nfpm 2.47.0 and an `nfpm.yaml` in the repository, and reads every package back before the release pull request opens (#53).
- `ri-release-homebrew` bottles the formula on macOS 14 and on macOS 15 Intel and rewrites `Formula/<bin>.rb` on every release with the version, the four archive checksums and the bottle block (#53).
```

- [ ] **Step 4: Gate and commit**

Run: `make check` and `systemd-run --user --scope -p MemoryMax=4G -- make test-container` (timeouts 600000). Expected: PASS.

```bash
git add skills/repo-infra/references tests/test_project_shape.py CHANGES.md
git commit -m "Name the release pieces in the project shape (D32)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: [outward] [ask the owner] Push, pull request, merge**

```bash
git push -u origin feat/release-pieces
gh pr create --base main --title "Release pieces for Rust programs (D32)" --body-file $S/pr-phase-c.md
gh pr checks --watch
```

The body lists the three pieces, the mtuspy run ids of the baseline and the proof, the accepted package differences, and ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`. Merge after the owner's OK.

- [ ] **Step 6: [outward] [ask the owner] Release repo-infra**: dispatch Create release PR on `oposs/repo-infra` with `feature`, watch it, merge the release pull request after the owner's OK, and record the tag in `$S/repo-infra-tag`.

---
# Phase D: mtuspy on the pieces, with its full shape

Run the script from the released repo-infra, not from a working branch:

```bash
git -C /home/oetiker/checkouts/repo-infra fetch --tags origin
git -C /home/oetiker/checkouts/repo-infra worktree add /scratch/oetiker/claude-worktrees/repo-infra-release "$(cat $S/repo-infra-tag)"
RI=/scratch/oetiker/claude-worktrees/repo-infra-release/skills/repo-infra/scripts/repo_infra
git -C /home/oetiker/checkouts/mtuspy fetch origin
git -C /home/oetiker/checkouts/mtuspy worktree add /scratch/oetiker/claude-worktrees/mtuspy-shape -b repo-infra/apply origin/main
cd /scratch/oetiker/claude-worktrees/mtuspy-shape
```

### Task 13: Install the pieces in place of the local copies

**Files (mtuspy):**
- Create (by `apply`): `.github/workflows/ri-release-rust-binaries.yml`, `ri-release-nfpm.yml`, `ri-release-homebrew.yml`
- Delete: `.github/workflows/release-rust-binaries.yml`, `release-nfpm.yml`, `release-homebrew.yml`
- Modify: `.github/workflows/release-build.yml`

- [ ] **Step 1: Install the pieces**

```bash
python3 $RI apply --item ri-release-rust-binaries
python3 $RI apply --item ri-release-nfpm
python3 $RI apply --item ri-release-homebrew
git log --oneline -3
```

Expected: three commits `Install <piece> v1 from the repo-infra standard`.

- [ ] **Step 2: The bodies are the proven ones**

```bash
for p in rust-binaries nfpm homebrew; do
  tail -n +3 .github/workflows/release-$p.yml | cmp - <(sed -n '/^$/,$p' .github/workflows/ri-release-$p.yml)
done
```

Expected: no output.

- [ ] **Step 3: Point the caller at the pieces and drop the copies.** In `release-build.yml`, change the three `uses:` lines to `./.github/workflows/ri-release-rust-binaries.yml`, `ri-release-nfpm.yml` and `ri-release-homebrew.yml`, and the comment's second sentence to `The three pieces it calls build the archives, the deb and rpm packages from the musl archives, and the bottles with the rewritten Formula/mtuspy.rb (repo-infra D32).` Then:

```bash
git rm .github/workflows/release-rust-binaries.yml .github/workflows/release-nfpm.yml .github/workflows/release-homebrew.yml
git add .github/workflows/release-build.yml
git commit -m "Build the release through the repo-infra release pieces

The three local workflows were the proof of the pieces; repo-infra now
ships them byte for byte under their ri- names.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
python3 $RI check; echo "exit $?"
```

Expected: `exit 0`, with the three new pieces `current`.

---

### Task 14: Close the shape gaps

**Files (mtuspy):** `demo/mtuspy.toml`, `docs/demo/mtuspy.webp`, `Makefile`, `README.md`, `Formula/mtuspy.rb`, `CHANGES.md`

- [ ] **Step 1: Run the shape review** as `commands/check.md` of the released plugin says, against `references/project-shape.md`, and write the result to `$S/mtuspy-shape.md` (scratch only, not committed). The triggers that apply: every project; has a command line (`src/main.rs` parses arguments with clap); runs in a terminal; is installed by users (a Rust program). Expected gaps, read on 2026-10-10: `demo` (no `demo/`), `install-text` (no mise route; the apt and rpm blocks differ from the canonical snippets), `writing-style` (the review lists them). Expected `met`: `badges`, `man-page`, `native-targets`, `linux-packages`, `homebrew` (after Task 8). **[ask the owner]** Show the review and agree which gaps this run closes and which become `exceptions`.

- [ ] **Step 2: The demo script** `demo/mtuspy.toml` (ansidrama v0.5.1; build it from `/home/oetiker/checkouts/ansidrama` with `cargo build --release -j4` if `ansidrama` is not on the PATH, and put its release directory on the PATH)

```toml
# The README demo: mtuspy finds the path MTU to a public host.
# `make demo` renders it into docs/demo/mtuspy.webp; `out` is relative to
# this file. The WebP is committed and regenerated by hand.
launch     = "PS1='$ ' bash --norc --noprofile -i"
cols       = 80
rows       = 24
font       = "smalti"
font_px    = 16
card_font_px     = 48
card_subtitle_px = 32
out        = "../docs/demo/mtuspy.webp"
env        = { COLORTERM = "truecolor" }
startup_ms = 1500
quit_keys  = ["C-d"]

[chrome]
style   = "macos"
title   = "mtuspy"
padding = 12

[[scene]]
card    = { text = "mtuspy", fg = "#fef9c3" }
hold_cs = 150

[[scene]]
text    = "mtuspy --max 1500 1.1.1.1"
hold_cs = 40

[[scene]]
keys     = ["Enter"]
await    = "Path MTU:"
await_ms = 30000
hold_cs  = 400
```

The recording runs on the owner's machine and needs an unprivileged ICMP socket (`net.ipv4.ping_group_range` covering the user) and a route to 1.1.1.1; whether both hold is to be seen on the first `make demo`.

- [ ] **Step 3: `make demo`.** In the Makefile, add `demo` to `.PHONY`, add to the help list `@echo "  make demo        Record docs/demo/mtuspy.webp (needs ansidrama)"`, and add:

```make
# The README demo, docs/demo/mtuspy.webp, recorded by ansidrama from
# demo/mtuspy.toml. cargo metadata names the target directory, because
# CARGO_TARGET_DIR may move it out of the checkout.
demo:
	cargo build --release
	cd demo && PATH="$$(cargo metadata --format-version 1 --no-deps | jq -r .target_directory)/release:$$PATH" ansidrama record mtuspy.toml
```

Run: `make demo` (timeout 600000). Expected: `docs/demo/mtuspy.webp` exists. **[ask the owner]** to look at the WebP before it is committed.

- [ ] **Step 4: README.** Below the description line and above `## Overview`, add:

```markdown
![mtuspy finds the path MTU to 1.1.1.1](docs/demo/mtuspy.webp)
```

Replace everything from `## Installation` up to `### Building from Source` with:

````markdown
## Installation

### Debian, Ubuntu

```sh
sudo install -d -m 0755 /etc/apt/keyrings
sudo curl -fsSL -o /etc/apt/keyrings/gitea-oposs.asc https://gitea.oetiker.ch/api/packages/oposs/debian/repository.key
echo "deb [signed-by=/etc/apt/keyrings/gitea-oposs.asc] https://gitea.oetiker.ch/api/packages/oposs/debian stable main" | sudo tee /etc/apt/sources.list.d/oposs.list
sudo apt update && sudo apt install mtuspy
```

### Fedora, RHEL, Rocky, Alma

```sh
sudo curl -fsSL -o /etc/yum.repos.d/oposs.repo https://gitea.oetiker.ch/api/packages/oposs/rpm.repo
sudo dnf install mtuspy
```

The `.deb` and `.rpm` packages grant `cap_net_raw` to `/usr/bin/mtuspy`, so it runs without sudo.

### Homebrew (macOS, Linux)

```sh
brew tap oetiker/mtuspy https://github.com/oetiker/mtuspy
brew trust --formula oetiker/mtuspy/mtuspy
brew install mtuspy
```

`brew trust` exists from Homebrew 6 on; skip it on older versions.

### mise

```sh
mise use -g github:oetiker/mtuspy
```

### Other systems

The [releases page](https://github.com/oetiker/mtuspy/releases/latest) has archives for Linux (static musl), macOS, Windows and illumos.
The Linux, macOS and illumos archives carry the man page beside the binary:

```bash
tar xzf mtuspy-*-x86_64-unknown-linux-musl.tar.gz
sudo install -Dm755 mtuspy/mtuspy       /usr/local/bin/mtuspy
sudo install -Dm644 mtuspy/man/mtuspy.1 /usr/local/share/man/man1/mtuspy.1
```

See [Permissions](#permissions) for running it without sudo.

````

Then fix each `writing-style` finding the owner agreed to in Step 1, one edit per finding. The quoted program output under "Example Output" carries an em dash because mtuspy prints one (its banner line `mtuspy <em dash> Path MTU discovery for ...` reads that way in the program's output); **[ask the owner]** whether the program's banner changes (a code change with its own CHANGES entry) or the README keeps the real output.

- [ ] **Step 5: The formula follows the template.** In `Formula/mtuspy.rb`, replace the comment block above `class Mtuspy` with the template's comment (with `<bin>` as `mtuspy`), drop the comment lines between `license` and `# BOTTLE-START` that name `release-build.yml`, and make `def install`:

```ruby
  def install
    bin.install "mtuspy"
    Dir["man/*.[1-9]"].each { |page| (man/"man#{page[-1]}").install page }
  end
```

Keep the `version`, `sha256` and bottle lines as Task 8's release wrote them.

- [ ] **Step 6: CHANGES.md** under `## [Unreleased]`:

```markdown
### Changed

- The README opens with a recording of mtuspy finding a path MTU, and its install section lists mise beside apt, dnf and Homebrew.
```

- [ ] **Step 7: [outward] Commit, push, open the pull request**

```bash
grep -c $'\u2014' demo/mtuspy.toml Makefile Formula/mtuspy.rb CHANGES.md   # 0 each
git add demo docs/demo Makefile README.md Formula/mtuspy.rb CHANGES.md
git commit -m "Close the project shape: demo, install routes, formula template

The shape review of repo-infra D32 reported no demo, no mise route and
install blocks that differed from the canonical snippets. The formula
installs every man page of the archive into its section, as the template
does.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push -u origin repo-infra/apply
gh pr create -R oetiker/mtuspy --base main --head repo-infra/apply --title "Release through the repo-infra pieces; project shape" --body-file $S/pr-mtuspy-shape.md
gh pr checks -R oetiker/mtuspy repo-infra/apply --watch
```

Expected: `ci-passed` and `changelog-updated` green.

- [ ] **Step 8: [outward] [ask the owner] Merge.**

---

### Task 15: The first release through the pieces

- [ ] **Step 1: [outward] Release** (authorised): `gh workflow run release-pr.yml -R oetiker/mtuspy --ref main -f release_type=bugfix`, watch it as in Task 8 Step 4. Expected: version 0.2.1, the draft carries the same set of assets as 0.2.0 under 0.2.1, and the run's jobs read `build / binaries / ...`, `build / packages / ...`, `build / homebrew / ...` from the `ri-` pieces.
- [ ] **Step 2: [outward] [ask the owner] Merge the release pull request** and watch the publish as in Task 8 Step 5.
- [ ] **Step 3: Repeat Task 8 Step 6** with 0.2.1. Expected: `mtuspy 0.2.1 (<build date>)` from every channel.

---

### Task 16: Record mtuspy as the reference example

**Files (repo-infra, new branch `docs/mtuspy-example` from `main`):**
- Create: `skills/repo-infra/references/examples/mtuspy/{ci.yml,release-build.yml,release-publish.yml,repo-infra.json,nfpm.yaml,mtuspy.rb}`
- Modify: `skills/repo-infra/references/onboarding.md`, `skills/repo-infra/references/project-shape.md`, `CHANGES.md`
- Test: `tests/test_skill.py`

- [ ] **Step 1: Failing test** (append to `tests/test_skill.py`)

```python
def test_mtuspy_is_the_example_of_a_project_with_its_full_shape():
    example = REFS / "examples/mtuspy"
    for name in ("ci.yml", "release-build.yml", "release-publish.yml", "repo-infra.json",
                 "nfpm.yaml", "mtuspy.rb"):
        assert (example / name).is_file(), name
    assert "references/examples/mtuspy/" in flat(REFS / "onboarding.md")
    assert "references/examples/mtuspy/" in flat(REFS / "project-shape.md")
```

- [ ] **Step 2: Copy the files** from mtuspy at the tag of Task 15:

```bash
T=v0.2.1; M=/home/oetiker/checkouts/mtuspy; E=skills/repo-infra/references/examples/mtuspy
git -C $M fetch --tags origin && mkdir -p $E
for f in ci.yml release-build.yml release-publish.yml; do git -C $M show $T:.github/workflows/$f > $E/$f; done
git -C $M show $T:.github/repo-infra.json > $E/repo-infra.json
git -C $M show $T:nfpm.yaml > $E/nfpm.yaml
git -C $M show $T:Formula/mtuspy.rb > $E/mtuspy.rb
grep -c $'\u2014' $E/*    # 0 each
```

- [ ] **Step 3: Pointers.** In `onboarding.md` step 4, after "starting from the closest example in `references/examples/repo-infra/`", add: "or, for a Rust program users install, `references/examples/mtuspy/`". In `project-shape.md`, add to the opening section: "`references/examples/mtuspy/` holds the callers, the config, the nfpm config and the formula of a Rust program with its full shape." Changelog under `### New`: "The skill carries mtuspy's callers, config, `nfpm.yaml` and formula under `references/examples/mtuspy/`, the example of a Rust program that publishes to every channel."

- [ ] **Step 4: Gate, commit, [outward] [ask the owner] pull request and merge.** `make check`; commit `Record mtuspy as the example of the project shape (D32)` with the attribution line; push, open the pull request, merge after the owner's OK. It ships with the next repo-infra release.

---

# Phase E: later conversions (each its own plan, one repository per run, each with the owner's OK)

- **edaptor**: converts to the three pieces and brings `extra_paths` to `ri-release-rust-binaries` as v2 (edaptor packs `examples/`), proven in edaptor's tree first. Its spec names the input; its formula already installs `examples/`.
- **Smalti**: converts to `ri-release-nfpm` and brings the `prepare` mode as v2 (a make target stages the files, nfpm runs once per packager without archives). How Smalti checks its packages is settled then against its Makefile: `check-packages` depends on `packages` and rebuilds under `build/`, and the Makefile passes `PKG_VERSION` and `PKG_MTIME` to nfpm.
- **mdmost**: converts to the three pieces; its `install-text` drops the apt key name `oposs.asc` for `gitea-oposs.asc`; no release until the owner says so.
- Issues: #53 and #57 close with Phase C and Phase A; #59 stays separate; #56 stays open and gains weight (three more workflow files per Rust program in the Actions list).

---

## Self-review

**Spec coverage.** Why: context only. Decisions: shape with triggers (Task 2), triggers by what users receive (Task 2, "Triggers"), LLM judges and script measures (Tasks 1 and 3: the script checks only the value shape), exceptions (Tasks 1 to 3), amendment of D30 and the `skip` message (Tasks 1, 3), shape review in the command only and apply starting with the script (Task 3), archive as contract (Tasks 6, 9, 10), met by result (Task 2 "Rules" paragraph), proven before upstreamed (Phases B then C), v1 only what mtuspy runs (Global Constraints, Tasks 6, 9 to 11). The shape, every rule (Task 2, test of ids). Exceptions and pairing (Task 2 "Exceptions", Task 3 check.md step 4). The shape review (Task 3). Install snippets and the release-flow pointer (Tasks 2, 3). Pieces: binaries (Tasks 6, 9), nfpm with the variable table, shadowing, read-back, Gitea name shapes and the mtuspy mapping (Tasks 6, 10), homebrew with url rewrite, rename, formula rewrite, root_url and outputs (Tasks 6, 11), formula template with the man install line (Task 2). Proof and conversion steps 1 to 5 (Tasks 5 to 8, 9 to 12, 13 to 16). Testing section (Tasks 1, 2, 9, 10, 11). Order of work (Phases A to E). Closes (Phase E). Out of scope: nothing planned for it.

**Placeholder scan.** Values that only exist later are named as outputs of an earlier step: `$S/accepted.diff` (Task 7), the bottle json (Task 7), the repo-infra tag (Task 12), the Gitea user name (the owner, Task 8). No step says "add tests" without code.

**Names across tasks.** Local files `release-rust-binaries.yml`, `release-nfpm.yml`, `release-homebrew.yml` (Tasks 6, 9 to 11, 13); pieces `ri-release-rust-binaries`, `ri-release-nfpm`, `ri-release-homebrew`; step names `Build`, `Pack the archive`, `Pack the zip`, `Fetch the man pages`, `Install cross`, `Install nfpm`, `Build and read back the packages`, `Point the formula at the built archives`, `Local tap`, `Rename the bottles`, `Rewrite the formula` (workflows in Task 6, tests in Tasks 9 to 11); artifacts `man-pages`, `release-asset-<target>`, `release-asset-packages`, `release-asset-bottle-<os>`, `bottle-json-<os>`, `release-files`; `facts_diff` in `$S/factsdiff.py` and `tests/nfpm_facts.py`.

**Review Focus.** 1: `test_a_mac_sha256_line_without_its_url_line_directly_above_fails` (Task 11). 2: `test_a_bad_packagers_input_fails_naming_it` (Task 10). 3: `test_a_missing_archive_fails`, `test_two_archives_in_one_artifact_fail`, `test_an_archive_without_one_top_folder_fails` (Task 10). 4: `test_the_previous_release_block_is_replaced_whole` (Task 11). 5: `test_exceptions_that_are_not_an_object_of_reasons_are_a_problem` with `"   "` (Task 1).

**Facts not verified read-only, each settled by a named step.** The exact cargo-deb and cargo-generate-rpm facts of mtuspy (Task 5, the baseline run); the rpm half of the packaging step and nfpm's rpm translation of amd64 and arm64 (Task 6 Step 7, Task 7); the shape of `brew bottle --json` (Task 7 Step 6); whether `macos-15-intel` still schedules (Task 5 Step 4); the Homebrew major version on the runners (the guard handles 5 and 6); the Gitea user name (the owner, Task 8); the name of the Homebrew container image (Task 8 Step 6); the ICMP permission for the demo recording (Task 14 Step 2).
