# Project shape (D32) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** repo-infra states what a released project contains, reviews it in `/repo-infra:check`, and ships three release pieces for Rust programs, proven in mtuspy before they are released; mtuspy becomes the reference example.

**Architecture:** Phase A adds `references/project-shape.md`, the `exceptions` config key and the shape review to the commands, and can be released alone. Phase B writes `ri-release-rust-binaries`, `ri-release-nfpm` and `ri-release-homebrew` in repo-infra on a branch, with their logic in workflow-lib v9 (`lib/nfpm.js`, `lib/homebrew.js`) and tests, and does not release them. Phase C takes a baseline run of mtuspy's unchanged build, installs the pieces in mtuspy with `apply` from that branch, compares the proof run with the baseline, and releases mtuspy 0.2.0 through them. Phase D releases repo-infra, checks mtuspy against the release, gives mtuspy its full shape and records it under `references/examples/mtuspy/`. Phase E lists the later conversions.

**Tech Stack:** Python 3.11 standard library (scripts), pytest + PyYAML (tests), Node.js with `node --test` (workflow-lib modules), GitHub Actions reusable workflows with `actions/github-script@v9`, bash in workflow steps that call tools, nfpm 2.47.0, cross 0.2.5, Homebrew, podman for container tests, ansidrama for the demo.

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
- A release piece runs its logic in JavaScript through `actions/github-script@v9`, with the code in `skills/repo-infra/assets/pieces/workflow-lib/lib/<name>.js` and its `<name>.test.js` run by `node --test` in `make check` (decision P2). A step that only calls a tool stays shell. Python appears in a piece only for a Python project.
- nfpm is pinned to `2.47.0` with SHA256 `0660ca602b2d2d2ae4781a06c692b3eeb9d437ffea05b831d76e41f4a3188783` (`nfpm_2.47.0_Linux_x86_64.tar.gz`, checked against goreleaser's `checksums.txt` and a download on 2026-10-10; Smalti's Makefile pins the same pair). cross stays at `0.2.5`, as in `ri-ci-rust-musl`.
- Package file names stay `<bin>_<version>-1_<arch>.deb` and `<bin>-<version>-1.<arch>.rpm`, so `release_assets` does not change.
- Action versions in every piece match the manifest `actions` map (`actions/checkout@v7`, `actions/upload-artifact@v7`, `actions/download-artifact@v8`, `actions/github-script@v9`). `dtolnay/rust-toolchain@stable` and `Homebrew/actions/setup-homebrew@main` stay branch references.
- No em dash in any shipped file (`tests/test_no_em_dash.py`), in this plan or in any file written for mtuspy. Write "for example", never `e.g.`. Load the `writing-style` skill before writing prose, comments, CHANGES entries or commit messages.
- `make check` (ruff, pytest, node lib tests) is green at the end of every repo-infra task. Builds and tests use at most 4 cores: `cargo build -j4`, no `pytest -n` above 4. `make test-container` runs under `systemd-run --user --scope -p MemoryMax=4G -- ...`. Pass `timeout: 600000` to every long command.
- Containers run with `podman`, never docker, and every `podman run` runs under `systemd-run --user --scope -p MemoryMax=2G --`. Temporary data goes to `/scratch/oetiker/claude-tmp/claude-1003/project-shape/` (called `$S` below), never `/tmp`.
- Each Bash call starts with fresh shell state, and a subagent's working directory resets between calls. Every block from Task 5 on therefore sets the variables it uses (`S`, `M`, `RIB`, `RI`) and passes `PYTHONPATH` inline, and a block that works in an mtuspy worktree starts with `cd` to it.
- Every commit ends with a `Co-Authored-By: Claude <model> <noreply@anthropic.com>` line naming the model that wrote it. Pull request bodies end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- Outward-facing steps are marked **[outward]**. The owner has authorised mtuspy releases for this work, and with them pushing the mtuspy branches `repo-infra/apply` and `project-shape` and opening or readying their pull requests. Merging pull requests in oposs/repo-infra is standing authority from the owner (subject to the auto-mode classifier, which may still ask). Every merge in mtuspy, every repo-infra release, and every setting, variable, secret or branch deletion in mtuspy or another repository is marked **[ask the owner]** and waits for the owner's OK in this session.

## Decisions this plan takes where the spec is silent

The executor implements these. The owner vetoed P1, P2 and P4 of the earlier draft. P1 and P2 kept hand-made local copies of the pieces in mtuspy under other names; mtuspy gets no special treatment and installs the pieces with `apply` from the unreleased repo-infra branch instead (P11). P4 wrote the nfpm step in Python; the logic of every release piece is JavaScript in workflow-lib instead (P2, P3, P7). The other decisions are renumbered.

- **P1. Inputs reach a step through `env:`, never as `${{ }}` inside `run:` or `script:`.** The tests then run the shipped step text with plain environment variables, and an input cannot inject shell or JavaScript.
- **P2. The logic of a release piece is JavaScript in workflow-lib.** `lib/nfpm.js` and `lib/homebrew.js` hold it, `nfpm.test.js` and `homebrew.test.js` test it, and the pieces call it through `actions/github-script@v9` as `ri-ci-rust` calls `rust-plan.js`. Every refusal is an `Error` with a one-line message, and the step hands `error.message` to `core.setFailed`: one `::error::` line, no stack trace. The file system and the commands go through an `io` argument the tests replace, so the library tests need no nfpm, rpm, dpkg-deb, brew or temporary directory, and they run in every repository's `ri-ci-lib` job, which runs `node --test .github/workflows/lib/*.test.js`. A step that only calls a tool (cargo, cross, tar, Compress-Archive, brew, apt-get, curl, make) stays shell.
- **P3. The two modules ship as workflow-lib v9.** Every file of the library carries the new marker (`load_pieces` refuses a directory piece whose files claim different versions), `CHANGES.md` gets a `## v9` section, repo-infra's own `.github/workflows/lib/` gets the same files (`tests/test_self_check.py` requires them current, and `make test-js` runs from there), and `make generations` and `make catalogue` run. `ri-release-nfpm` and `ri-release-homebrew` name `workflow-lib` under `Pieces`, and their `## v1` notes say they need v9; `check` sees only whether a needed piece is present, not its version. homebrew.js joins v9 in Task 8 without a second bump, because v9 is not released yet.
- **P4. The package names are checked with `parsePackageFile` from `lib/gitea.js`.** The names `ri-publish-gitea` uploads are then written down once, and the earlier test that compared a Python copy of the two patterns with the JavaScript ones goes.
- **P5. The man pages travel as the artifact `man-pages`.** It is not `release-asset-*`, so the release does not attach it.
- **P6. The Homebrew trust guard reads the major version** (`brew --version`) instead of `brew trust ... || true`, so a failing `brew trust` on Homebrew 6 fails the leg.
- **P7. The three formula steps are `lib/homebrew.js`, not awk, sed and jq.** The local-tap rewrite (a url line directly above each mac marker), the bottle rename and the formula rewrite with its generated bottle block are logic, so P2 applies. It also closes a gap of the awk version: the bottle legs run the BSD awk of macOS, while the tests ran GNU awk on Linux, so the tested program was not the shipped one; node is the same on both. And it quotes a `cellar` that is a path (`cellar: "/opt/homebrew/Cellar"`), which the jq line wrote as an invalid Ruby symbol; a static Rust binary gets `:any_skip_relocation` and never met it. `Local tap` and `Build the bottle` stay shell: they call brew.
- **P8. The comparison of packages uses `facts.sh`** (Task 10), which writes file modes and paths, the control fields and the postinst of one package. Version, sizes and dates are left out, so cargo-deb's 0.1.3 packages and nfpm's 0.0.0 packages compare. `facts.sh`, `collect.sh` and `factsdiff.py` are tools of the proof and the tests, not steps of a piece, so they stay shell and Python. `tests/fixtures/nfpm/` keeps the baseline facts and the accepted differences (Task 13).
- **P9. `project-shape.md` names the new pieces on the pieces branch** (Task 9), which merges and is released with them. Released alone in Phase A, it names no piece that does not exist.
- **P10. mtuspy's `GITEA_PACKAGE_USER` must become a repository variable.** Today it is a repository *secret* (`gh api repos/oetiker/mtuspy/actions/secrets` lists `GITEA_PACKAGE_TOKEN` and `GITEA_PACKAGE_USER`; `.../actions/variables` lists none), and `ri-publish-gitea` reads `vars.GITEA_PACKAGE_USER`. The first publish would fail with the missing-credential message. Task 14 sets the variable, with the owner.
- **P11. mtuspy proves the pieces from the unreleased repo-infra branch.** It installs them with `apply --item`, run with `PYTHONPATH` pointing at the scripts of the `feat/release-pieces` worktree, so it carries the real markers and headers like any repository. A fix the proof forces keeps the version (v1 of a piece, v9 of workflow-lib), because nothing carrying it has been released: the superseded entry leaves `generations.json` and mtuspy installs the piece again ("When the proof forces a fix", Task 12). From Task 14 Step 1 until the release in Task 15 no piece byte changes, so mtuspy 0.2.0 carries exactly the bytes repo-infra releases; Task 16 checks it against the release.
- **P12. The data of the mtuspy runs joins the repo-infra tests after the proof** (Task 13): the baseline package facts, the accepted differences and the recorded `brew bottle --json` files. They live under `tests/`, outside every piece, so adding them changes no piece byte and asks nothing of mtuspy. Until then the library tests use the json shape `brew bottle` documents, and the container test checks names and read-back only.
- **P13. mtuspy's proof branch is `repo-infra/apply`, the branch `apply` commits to.** `apply` switches to that branch when another one is checked out, creating it from the current commit, so a proof branch with another name would lose the install commits to a second branch. The `repo-infra/apply` of mtuspy's merged pull request #2 still exists locally and on GitHub (`ffb9b3a`), so `worktree add -b repo-infra/apply` would fail and `apply` would check out that stale branch; Task 10 deletes it first, with the owner.

## Review Focus

1. A formula whose mac `url` line is separated from its `sha256` line (a blank line, a comment, a reordered block) must fail the bottle leg naming the marker; it must not let `brew` fetch the GitHub url, which answers 404 before the release exists. Test in Task 8 (`homebrew.test.js`).
2. A malformed `packagers` input (not JSON, `{"deb": "x"}`, a key other than deb or rpm) must fail the packaging job with one `::error::` line naming the input, not a stack trace. Tests in Task 6 (`nfpm.test.js`: each message names `packagers` and holds no line break) and Task 7 (the step hands `error.message` to `core.setFailed`, and the container run prints exactly one `::error::` line).
3. A `release-asset-<target>` artifact holding no archive or two, or an archive whose root is not one folder, must fail naming the archive instead of packaging the wrong files. Test in Task 6.
4. A formula still carrying the previous release's bottle block must come out with this release's `root_url` and bottles only. Test in Task 8.
5. An `exceptions` value with a whitespace-only reason must be a `problem` like an empty one. Test in Task 1.
6. mtuspy must release with exactly the piece bytes repo-infra releases. Gate in Task 14 Step 1 and Task 15 Step 1, proof in Task 16.

---

## File structure

repo-infra:

| File | Change | Responsibility |
|---|---|---|
| `skills/repo-infra/references/project-shape.md` | create (Task 2), amend (Task 9) | triggers, rules, exceptions, badges, install snippets, archive layout, formula template |
| `skills/repo-infra/scripts/repo_infra/check.py` | modify (Task 1) | accept `exceptions`, rename message for `skip` |
| `commands/check.md`, `commands/apply.md` | modify (Task 3) | the shape review; apply starts with the script |
| `skills/repo-infra/SKILL.md`, `references/onboarding.md`, `references/release-flow.md`, `references/conventions.md` | modify (Task 3; onboarding also Tasks 9, 19) | "run the script until it exits 0", onboarding review step, pointer to the snippets, amended config rule, D32 |
| `skills/repo-infra/assets/pieces/ri-release-rust-binaries/` | create (Task 5) | the binaries piece |
| `skills/repo-infra/assets/pieces/workflow-lib/lib/nfpm.js`, `nfpm.test.js` | create (Task 6) | the packaging logic |
| `skills/repo-infra/assets/pieces/workflow-lib/lib/*.js`, `workflow-lib/CHANGES.md` | modify (Tasks 6, 8) | marker v9, purpose, upgrade note |
| `skills/repo-infra/assets/pieces/ri-release-nfpm/` | create (Task 7) | the packaging piece |
| `skills/repo-infra/assets/pieces/workflow-lib/lib/homebrew.js`, `homebrew.test.js` | create (Task 8) | the three formula steps |
| `skills/repo-infra/assets/pieces/ri-release-homebrew/` | create (Task 8) | the bottles and formula piece |
| `.github/workflows/lib/` | modify (Tasks 6, 8) | repo-infra's own copy of workflow-lib |
| `skills/repo-infra/assets/manifest.json`, `generations.json`, `references/catalogue.md` | modify (Tasks 5 to 8) | registration |
| `skills/repo-infra/references/examples/mtuspy/` | create (Task 19) | the reference example |
| `tests/test_check.py`, `tests/test_skill.py` | modify | config and wording tests |
| `tests/test_project_shape.py` | create (Task 2), amend (Task 9) | rule structure, snippets, template |
| `tests/test_release_rust_binaries.py`, `tests/test_release_nfpm.py`, `tests/test_release_homebrew.py` | create (Tasks 5, 7, 8), amend (Task 13) | the pieces' structure, their calls into the library, the container run |
| `tests/fixtures/nfpm/repo/` | create (Task 7) | mtuspy's nfpm config and scripts |
| `tests/nfpm_facts.py`, `tests/fixtures/nfpm/` (facts tools, baseline, accepted diff), `tests/fixtures/homebrew/` | create (Task 13) | the data of the mtuspy runs |
| `CHANGES.md` | modify (Tasks 4, 9, 19) | user-facing entries |

mtuspy (`oetiker/mtuspy`):

| File | Change |
|---|---|
| `.github/workflows/proof.yml` | create (Task 10), delete (Task 14) |
| `.github/workflows/lib/` | workflow-lib v8 to v9, by `apply` (Task 11) |
| `.github/workflows/ri-release-rust-binaries.yml`, `ri-release-nfpm.yml`, `ri-release-homebrew.yml` | create, by `apply` (Task 11) |
| `.github/workflows/release-build.yml` | rewrite as a caller of the pieces (Task 11) |
| `nfpm.yaml` | create from `tests/fixtures/nfpm/repo/nfpm.yaml` of repo-infra (Task 11) |
| `Cargo.toml` | drop `[package.metadata.deb]` and `[package.metadata.generate-rpm]` (Task 11) |
| `Formula/mtuspy.rb` | template comment and install lines (Task 17) |
| `demo/mtuspy.toml`, `docs/demo/mtuspy.webp`, `Makefile`, `README.md`, `CHANGES.md` | demo and shape gaps (Task 17) |

Work locations:

- repo-infra, Phase A: a worktree on a new branch `feat/project-shape` from `spec/project-shape` (use superpowers:using-git-worktrees; the hook puts it under `/scratch/oetiker/claude-worktrees/`).
- repo-infra, Phases B and C: after Phase A has merged (Task 4 Step 4), `git -C /home/oetiker/checkouts/repo-infra fetch origin` and `git -C /home/oetiker/checkouts/repo-infra worktree add /scratch/oetiker/claude-worktrees/repo-infra-release-pieces -b feat/release-pieces origin/main`, called `$RIB` below. It starts from `main` after Phase A because Task 8 tests against the formula template of `project-shape.md` and Task 9 amends that file. The branch stays unreleased until Task 15; mtuspy runs `apply` from it in Tasks 11 and 12.
- mtuspy: `/home/oetiker/checkouts/mtuspy` (`$M`) is on `main` with an uncommitted change to `mise.toml` that belongs to the owner. Do not touch that checkout's working tree. Task 10 adds the worktree `/scratch/oetiker/claude-worktrees/mtuspy-release-pieces` on `repo-infra/apply` (decision P13), Task 16 the worktree `/scratch/oetiker/claude-worktrees/mtuspy-shape` on `project-shape`.
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
- Produces: the sections `## Triggers`, `## Rules` (each rule a `### \`id\`` heading with the lines `Trigger:`, `Requires:`, `Verify:`, `Met by:` in that order), `## Exceptions`, `## Badges`, `## Install snippets`, `## Archive layout`, `## Formula template` (one ```ruby block with the placeholders `<Class>`, `<one-line description>`, `<owner>`, `<repo>`, `<SPDX license>`, `<bin>`). Task 8's tests read the formula template from this file; Task 9 amends the `Met by` lines.

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

The body names the spec, lists the decisions P1 to P13 of this plan that apply later, says that Phase A ships no piece, and ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`. The pull request carries changelog entries, so it needs no `no-changelog` label.

- [ ] **Step 3: Watch the checks:** `gh pr checks --watch`. Expected: `ci-passed` and `changelog-updated` green.

- [ ] **Step 4: [outward] [ask the owner] Merge**, and ask whether to release Phase A alone (dispatch Create release PR on `oposs/repo-infra` with `feature`, then merge the release pull request) or to release it together with the release pieces (Task 15).

---
# Phase B: the three pieces in repo-infra, on a branch, not released

Work in `$RIB`, the worktree of `feat/release-pieces` (see "Work locations"),
which branches from `main` after Phase A has merged. Every task ends with
`make check` green and a commit on that branch. Nothing is pushed before
Task 9, nothing merges before Task 15, and nothing is released before Task 15.
The pieces reach mtuspy in Phase C through `apply`, run from this worktree
(decision P11).

Each piece is registered in `skills/repo-infra/assets/manifest.json` under
`pieces`, after `ri-release-source-tarball`:

```json
"<piece>": {
  "target": ".github/workflows/<piece>.yml",
  "group": "release-build"
}
```

A task that adds or changes an asset ends with `make generations`,
`make catalogue` and `make check`.

### Task 5: `ri-release-rust-binaries`

**Files:**
- Create: `skills/repo-infra/assets/pieces/ri-release-rust-binaries/ri-release-rust-binaries.yml`, `.../CHANGES.md`
- Modify: `skills/repo-infra/assets/manifest.json`, `skills/repo-infra/assets/generations.json` (by `make generations`), `skills/repo-infra/references/catalogue.md` (by `make catalogue`)
- Test: `tests/test_release_rust_binaries.py`

**Interfaces:**
- Produces: the piece `ri-release-rust-binaries` with inputs `version`, `ref`, `bin`; jobs `man`, `binaries`; artifacts `man-pages`, `release-asset-<target>`. Its steps only call tools (make, cargo, cross, tar, Compress-Archive), so it has no library module (decision P2).

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

- [ ] **Step 2: Write the piece** `skills/repo-infra/assets/pieces/ri-release-rust-binaries/ri-release-rust-binaries.yml` with exactly this content:

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

- [ ] **Step 3: `CHANGES.md`** in the piece's folder:

```markdown
# ri-release-rust-binaries

Upgrade notes, newest first. Each section says what a caller or
.github/repo-infra.json must change to take that version.

## v1

First version. Call it from release-build.yml as the catalogue shows, with `bin` naming the binary. It runs `make man`, so the repository carries the man pieces, and it builds seven archives that release_assets lists.
```

Add the manifest entry.

- [ ] **Step 4: Register and test**

Run: `make generations && make catalogue && python3 -m pytest -q --basetemp=.pytest-tmp tests/test_release_rust_binaries.py tests/test_pieces.py tests/test_catalogue.py tests/test_generations.py`
Expected: PASS. `test_pieces.py` checks the marker, the descriptions, the timeouts, the action pins, the `Call:` snippet and the `ref` contract of the new piece.

- [ ] **Step 5: Gate and commit**

Run: `make check` (timeout 600000). Expected: PASS.

```bash
git add skills/repo-infra/assets tests/test_release_rust_binaries.py skills/repo-infra/references/catalogue.md
git commit -m "Add ri-release-rust-binaries v1 (D32)

It builds the seven native targets, the man pages once on Linux, and
packs each archive by the layout the packaging and Homebrew pieces read.
The build of mdmost, edaptor and mtuspy is its source; mtuspy proves it
before it is released.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: `lib/nfpm.js` and workflow-lib v9

**Files:**
- Create: `skills/repo-infra/assets/pieces/workflow-lib/lib/nfpm.js`, `.../lib/nfpm.test.js`
- Modify: every other file of `skills/repo-infra/assets/pieces/workflow-lib/lib/` (the marker), `.../lib/release.js` (also the `Purpose` line), `skills/repo-infra/assets/pieces/workflow-lib/CHANGES.md`
- Modify: `.github/workflows/lib/` (repo-infra's own copy of the library), `skills/repo-infra/assets/generations.json`, `skills/repo-infra/references/catalogue.md`

**Interfaces:**
- Consumes: `parsePackageFile` from `lib/gitea.js` (decision P4).
- Produces: `nfpm.run(env, io)`, which returns one log line per package and throws an `Error` with a one-line message on every refusal; `parsePackagers`, `parseTargets`, `expand`, `rfc3339`, `checkName` for the tests. `env` carries `VERSION`, `CONFIG`, `PACKAGERS`, `ARCHIVES` and `RUNNER_TEMP`; `io` defaults to the file system and `child_process`. workflow-lib is v9 (decision P3).

- [ ] **Step 1: Write the failing test** `skills/repo-infra/assets/pieces/workflow-lib/lib/nfpm.test.js`

```js
// repo-infra: workflow-lib v9
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const nfpm = require('./nfpm.js');

const TARGETS = 'x86_64-unknown-linux-musl aarch64-unknown-linux-musl';
const BOTH = '{"deb": {}, "rpm": {}}';
// Shaped like mtuspy's nfpm.yaml: names in a comment, in top-level scalars
// and in the contents paths nfpm itself does not expand.
const CONFIG = [
  '# Filled in by ri-release-nfpm: VERSION, MTIME, ARCH and STAGE.',
  'name: tool',
  'arch: "${ARCH}"',
  'version: "${VERSION}"',
  'mtime: "${MTIME}"',
  'contents:',
  '  - src: ${STAGE}/tool',
  '    dst: /usr/bin/tool',
  '',
].join('\n');
const ARCH = { 'x86_64-unknown-linux-musl': ['amd64', 'x86_64'],
  'aarch64-unknown-linux-musl': ['arm64', 'aarch64'] };

// A checkout as download-artifact leaves it, and stand-ins for git, tar,
// nfpm, dpkg-deb and rpm. `archives` maps a target to the file names in its
// artifact; `tops` is what one archive unpacks to; `name` and `version`
// shape what the stand-in nfpm writes and what the read-back reports.
function fakeIo({
  config = CONFIG, archives, tops = ['tool'], name, version = (v) => v, files = 2,
} = {}) {
  const dirs = new Map();
  const written = new Map();
  const calls = [];
  const add = (dir, entry) => {
    if (!dirs.has(dir)) dirs.set(dir, new Set());
    if (entry !== undefined) dirs.get(dir).add(entry);
  };
  const folders = archives || Object.fromEntries(
    TARGETS.split(' ').map((t) => [t, [`tool-1.2.3-${t}.tar.gz`]]));
  for (const [target, names] of Object.entries(folders)) {
    for (const n of names) add(`archives/release-asset-${target}`, n);
  }
  const io = {
    isFile: (path) => path === 'nfpm.yaml' && config !== null,
    isDir: (path) => /\/stage\/[^/]+\/tool$/.test(path),
    read: () => config,
    write: (path, text) => written.set(path, text),
    mkdir: (path) => add(path),
    list: (path) => [...(dirs.get(path) || [])].sort(),
    exec: (command, args, options) => {
      calls.push({ command, args, env: options && options.env });
      if (command === 'git') return '1700000000\n';
      if (command === 'tar') {
        for (const top of tops) add(args[3], top);
        return '';
      }
      if (command === 'nfpm') {
        const { PACKAGER, ARCH: arch, VERSION } = options.env;
        const rpmArch = Object.values(ARCH).find((pair) => pair[0] === arch)[1];
        const file = name ? name(PACKAGER, arch)
          : PACKAGER === 'deb' ? `tool_${VERSION}-1_${arch}.deb`
            : `tool-${VERSION}-1.${rpmArch}.rpm`;
        add('packages', file);
        return null;
      }
      if (command === 'dpkg-deb' && args[0] === '--field') return `${version('1.2.3-1')}\n`;
      if (command === 'dpkg-deb') {
        return ['drwxr-xr-x root/root 0 ./usr/',
          ...Array.from({ length: files }, (_, i) => `-rwxr-xr-x root/root 1 ./usr/bin/f${i}`),
        ].join('\n');
      }
      if (command === 'rpm' && args[1] === '--queryformat') return version('1.2.3');
      if (command === 'rpm') {
        return Array.from({ length: files }, (_, i) => `/usr/bin/f${i}`).join('\n');
      }
      throw new Error(`unexpected command ${command}`);
    },
  };
  return { io, written, calls };
}

function env(overrides = {}) {
  return { VERSION: '1.2.3', CONFIG: 'nfpm.yaml', PACKAGERS: BOTH, ARCHIVES: TARGETS,
    RUNNER_TEMP: '/t', ...overrides };
}

// The step hands error.message to core.setFailed, which prints one
// ::error:: line. A message with a line break or a stack frame would print a
// trace instead of naming the input.
function refusal(fn, expected) {
  assert.throws(fn, (error) => {
    assert.match(error.message, expected);
    assert.doesNotMatch(error.message, /\n/);
    return true;
  });
}

test('four packages are built and each is read back', () => {
  const { io, calls } = fakeIo();
  assert.deepEqual(nfpm.run(env(), io), [
    'tool_1.2.3-1_amd64.deb: version 1.2.3-1, 2 files',
    'tool-1.2.3-1.x86_64.rpm: version 1.2.3, 2 files',
    'tool_1.2.3-1_arm64.deb: version 1.2.3-1, 2 files',
    'tool-1.2.3-1.aarch64.rpm: version 1.2.3, 2 files',
  ]);
  const runs = calls.filter((c) => c.command === 'nfpm');
  assert.deepEqual(runs.map((c) => [c.env.PACKAGER, c.env.ARCH, c.env.TARGET]), [
    ['deb', 'amd64', 'x86_64-unknown-linux-musl'],
    ['rpm', 'amd64', 'x86_64-unknown-linux-musl'],
    ['deb', 'arm64', 'aarch64-unknown-linux-musl'],
    ['rpm', 'arm64', 'aarch64-unknown-linux-musl'],
  ]);
  assert.equal(runs[0].env.SOURCE_DATE_EPOCH, '1700000000');
  assert.equal(runs[0].env.MTIME, '2023-11-14T22:13:20Z');
  assert.equal(runs[0].env.STAGE, '/t/stage/x86_64-unknown-linux-musl/tool');
});

test('every name in the config is filled in, comments and contents paths too', () => {
  const { io, written } = fakeIo();
  nfpm.run(env(), io);
  const text = written.get('/t/nfpm-x86_64-unknown-linux-musl-deb.yaml');
  assert.doesNotMatch(text, /\$\{/);
  assert.match(text, /^arch: "amd64"$/m);
  assert.match(text, /^mtime: "2023-11-14T22:13:20Z"$/m);
  assert.match(text, /src: \/t\/stage\/x86_64-unknown-linux-musl\/tool\/tool$/m);
});

test('a packagers value reaches the config of its packager only', () => {
  const config = `${CONFIG}homepage: \${HOMEPAGE}\n`;
  const { io, written } = fakeIo({ config });
  nfpm.run(env({ PACKAGERS: '{"deb": {"HOMEPAGE": "https://d"}, "rpm": {"HOMEPAGE": "https://r"}}' }), io);
  assert.match(written.get('/t/nfpm-x86_64-unknown-linux-musl-deb.yaml'), /homepage: https:\/\/d$/m);
  assert.match(written.get('/t/nfpm-x86_64-unknown-linux-musl-rpm.yaml'), /homepage: https:\/\/r$/m);
});

for (const [packagers, expected] of [
  ['{deb}', /^packagers is not JSON: /],
  ['{"deb": "x"}', /^packagers must be a JSON object/],
  ['{}', /^packagers must be a JSON object/],
  ['[]', /^packagers must be a JSON object/],
  ['{"deb": {"NAME": 1}}', /^packagers must be a JSON object/],
  ['{"apk": {}}', /^packagers names apk; ri-release-nfpm builds deb and rpm$/],
  ['{"deb": {"VERSION": "9"}}', /^packagers\.deb sets VERSION, which ri-release-nfpm sets itself$/],
  ['{"rpm": {"STAGE": "/", "ARCH": "noarch"}}', /^packagers\.rpm sets ARCH, STAGE, /],
]) {
  test(`packagers ${packagers} fails with one line naming the input`, () => {
    const { io, calls } = fakeIo();
    refusal(() => nfpm.run(env({ PACKAGERS: packagers }), io), expected);
    assert.deepEqual(calls, [], 'nothing runs before the inputs are checked');
  });
}

for (const [archives, expected] of [
  ['', /^archives names no target$/],
  ['x86_64-unknown-illumos', /^no package architecture is known for x86_64-unknown-illumos; archives takes x86_64-unknown-linux-musl and aarch64-unknown-linux-musl$/],
  ['toString', /^no package architecture is known for toString;/],
]) {
  test(`archives "${archives}" fails`, () => {
    refusal(() => nfpm.run(env({ ARCHIVES: archives }), fakeIo().io), expected);
  });
}

test('a missing config fails naming it', () => {
  refusal(() => nfpm.run(env(), fakeIo({ config: null }).io), /^nfpm\.yaml does not exist$/);
});

test('a missing archive fails naming its artifact', () => {
  const { io } = fakeIo({ archives: { 'x86_64-unknown-linux-musl': ['tool-1.2.3-x86_64-unknown-linux-musl.tar.gz'] } });
  refusal(() => nfpm.run(env(), io),
    /^release-asset-aarch64-unknown-linux-musl holds 0 \.tar\.gz files; one is expected$/);
});

test('two archives in one artifact fail', () => {
  const { io } = fakeIo({ archives: {
    'x86_64-unknown-linux-musl': ['a.tar.gz', 'b.tar.gz'],
    'aarch64-unknown-linux-musl': ['c.tar.gz'] } });
  refusal(() => nfpm.run(env(), io), /^release-asset-x86_64-unknown-linux-musl holds 2 /);
});

test('an archive without one top folder fails', () => {
  refusal(() => nfpm.run(env(), fakeIo({ tops: ['tool', 'README.md'] }).io),
    /^tool-1\.2\.3-x86_64-unknown-linux-musl\.tar\.gz must hold one folder, the <bin>\/ of the archive layout$/);
});

test('a name nobody sets fails before nfpm runs', () => {
  const { io, calls } = fakeIo({ config: `${CONFIG}homepage: \${HOMEPAGE}\n# \${LATER}\n` });
  refusal(() => nfpm.run(env(), io),
    /^nfpm\.yaml uses \$\{HOMEPAGE\}, \$\{LATER\}, which neither ri-release-nfpm nor packagers sets$/);
  assert.equal(calls.filter((c) => c.command === 'nfpm').length, 0);
});

test('a package name ri-publish-gitea refuses fails', () => {
  const { io } = fakeIo({ name: (p, arch) => (p === 'deb' ? `Tool_1.2.3-1_${arch}.deb` : 'x.rpm') });
  refusal(() => nfpm.run(env({ PACKAGERS: '{"deb": {}}' }), io),
    /^Tool_1\.2\.3-1_amd64\.deb is not name_version_arch\.deb, the name ri-publish-gitea uploads$/);
  refusal(() => nfpm.run(env({ PACKAGERS: '{"rpm": {}}' }), fakeIo({ name: () => 'tool.rpm' }).io),
    /^tool\.rpm is not name-version-release\.arch\.rpm/);
});

test('a package carrying another version fails', () => {
  const { io } = fakeIo({ version: () => '0.1.3' });
  refusal(() => nfpm.run(env(), io), /^tool_1\.2\.3-1_amd64\.deb carries version 0\.1\.3, not 1\.2\.3$/);
});

test('a package holding no files fails', () => {
  refusal(() => nfpm.run(env(), fakeIo({ files: 0 }).io), /^tool_1\.2\.3-1_amd64\.deb holds no files$/);
});

test('a packagers value fills in the config but stays out of the environment of nfpm', () => {
  const { io, calls, written } = fakeIo({ config: `${CONFIG}# \${PATH}\n` });
  nfpm.run(env({ PACKAGERS: '{"deb": {"PATH": "x"}}', PATH: '/usr/bin' }), io);
  assert.match(written.get('/t/nfpm-x86_64-unknown-linux-musl-deb.yaml'), /^# x$/m);
  for (const call of calls.filter((c) => c.command === 'nfpm')) {
    assert.equal(call.env.PATH, '/usr/bin');
  }
});

test('rfc3339 drops the milliseconds', () => {
  assert.equal(nfpm.rfc3339('0'), '1970-01-01T00:00:00Z');
});
```

Run: `node --test skills/repo-infra/assets/pieces/workflow-lib/lib/nfpm.test.js`
Expected: FAIL with `Cannot find module './nfpm.js'`.

- [ ] **Step 2: Write `skills/repo-infra/assets/pieces/workflow-lib/lib/nfpm.js`**

```js
// repo-infra: workflow-lib v9
'use strict';

// ri-release-nfpm (D32): .deb and .rpm packages built by nfpm from the
// unpacked release archives, each read back before the release pull request
// opens. The step in ri-release-nfpm.yml hands `run` its environment and
// nothing else, so every input check and every refusal is a line in
// nfpm.test.js. The file system and the commands go through `io`, which the
// tests replace.

const { parsePackageFile } = require('./gitea.js');

// The variables the piece sets for every nfpm run. A packagers key that
// names one of them fails, so a config cannot shadow VERSION or ARCH.
const OWN = ['VERSION', 'SOURCE_DATE_EPOCH', 'MTIME', 'PACKAGER', 'TARGET', 'STAGE', 'ARCH'];
// nfpm translates amd64 and arm64 into x86_64 and aarch64 for rpm.
const ARCH = {
  'x86_64-unknown-linux-musl': 'amd64',
  'aarch64-unknown-linux-musl': 'arm64',
};
const NAME = /\$\{([A-Za-z_][A-Za-z0-9_]*)\}/g;

function isObject(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function parsePackagers(text) {
  let packagers;
  try {
    packagers = JSON.parse(text);
  } catch (error) {
    throw new Error(`packagers is not JSON: ${error.message}`);
  }
  const valid = isObject(packagers) && Object.keys(packagers).length > 0
    && Object.values(packagers).every((extra) => isObject(extra)
      && Object.values(extra).every((value) => typeof value === 'string'));
  if (!valid) {
    throw new Error('packagers must be a JSON object such as '
      + '{"deb": {}, "rpm": {"NAME": "value"}}: one key per packager, '
      + 'each mapping variable names to strings');
  }
  const unknown = Object.keys(packagers).filter((p) => p !== 'deb' && p !== 'rpm').sort();
  if (unknown.length > 0) {
    throw new Error(`packagers names ${unknown.join(', ')}; ri-release-nfpm builds deb and rpm`);
  }
  for (const [packager, extra] of Object.entries(packagers)) {
    const shadowed = Object.keys(extra).filter((key) => OWN.includes(key)).sort();
    if (shadowed.length > 0) {
      throw new Error(`packagers.${packager} sets ${shadowed.join(', ')}, `
        + 'which ri-release-nfpm sets itself');
    }
  }
  return packagers;
}

function parseTargets(text) {
  const targets = (text || '').split(/\s+/).filter(Boolean);
  if (targets.length === 0) throw new Error('archives names no target');
  for (const target of targets) {
    if (!Object.hasOwn(ARCH, target)) {
      throw new Error(`no package architecture is known for ${target}; archives takes `
        + Object.keys(ARCH).join(' and '));
    }
  }
  return targets;
}

// nfpm expands only top-level scalars, not the src: and dst: paths under
// contents:, so every ${NAME} in the file is replaced here, comments
// included. A name nobody sets stops the build instead of reaching nfpm as
// an empty string.
function expand(template, values, config) {
  const unset = [...new Set([...template.matchAll(NAME)].map((m) => m[1]))]
    .filter((name) => !Object.hasOwn(values, name)).sort();
  if (unset.length > 0) {
    throw new Error(`${config} uses ${unset.map((name) => `\${${name}}`).join(', ')}, `
      + 'which neither ri-release-nfpm nor packagers sets');
  }
  return template.replace(NAME, (_, name) => values[name]);
}

// nfpm 2.47.0 ignores SOURCE_DATE_EPOCH, so MTIME carries the same instant
// for the config's mtime: field.
function rfc3339(epoch) {
  return new Date(Number(epoch) * 1000).toISOString().replace(/\.\d{3}Z$/, 'Z');
}

function variables({ version, epoch, packager, target, stage, extra }) {
  return {
    VERSION: version, SOURCE_DATE_EPOCH: epoch, MTIME: rfc3339(epoch), PACKAGER: packager,
    TARGET: target, STAGE: stage, ARCH: ARCH[target], ...extra,
  };
}

// The names ri-publish-gitea uploads; parsePackageFile in gitea.js is the
// one place they are written down.
function checkName(packager, file) {
  const parsed = parsePackageFile(file);
  if (packager === 'deb' && (!parsed || parsed.kind !== 'debian')) {
    throw new Error(`${file} is not name_version_arch.deb, the name ri-publish-gitea uploads`);
  }
  if (packager === 'rpm' && (!parsed || parsed.kind !== 'rpm')) {
    throw new Error(`${file} is not name-version-release.arch.rpm, `
      + 'the name ri-publish-gitea uploads');
  }
}

function readBack(packager, path, exec) {
  if (packager === 'deb') {
    return {
      version: exec('dpkg-deb', ['--field', path, 'Version']).trim(),
      files: exec('dpkg-deb', ['--contents', path]).split('\n')
        .filter((line) => line && !line.startsWith('d')),
    };
  }
  return {
    version: exec('rpm', ['-qp', '--queryformat', '%{VERSION}', path]).trim(),
    files: exec('rpm', ['-qlp', path]).split('\n').filter((line) => line.startsWith('/')),
  };
}

function nodeIo() {
  const fs = require('fs');
  const { execFileSync } = require('child_process');
  const stat = (path) => (fs.existsSync(path) ? fs.statSync(path) : null);
  return {
    isFile: (path) => Boolean(stat(path) && stat(path).isFile()),
    isDir: (path) => Boolean(stat(path) && stat(path).isDirectory()),
    read: (path) => fs.readFileSync(path, 'utf8'),
    write: (path, text) => fs.writeFileSync(path, text),
    mkdir: (path) => fs.mkdirSync(path, { recursive: true }),
    list: (path) => (fs.existsSync(path) ? fs.readdirSync(path).sort() : []),
    exec: (command, args, options = {}) => execFileSync(command, args, {
      encoding: 'utf8', stdio: ['ignore', 'pipe', 'inherit'], ...options,
    }),
  };
}

// Builds every package and returns one line per package for the log. Run
// in the checkout: archives/release-asset-<target>/ holds what
// download-artifact fetched, and packages/ receives the packages.
function run(env, io = nodeIo()) {
  const version = env.VERSION;
  const config = env.CONFIG;
  const temp = env.RUNNER_TEMP;
  const packagers = parsePackagers(env.PACKAGERS);
  const targets = parseTargets(env.ARCHIVES);
  if (!io.isFile(config)) throw new Error(`${config} does not exist`);
  const template = io.read(config);
  const epoch = io.exec('git', ['log', '-1', '--format=%ct', 'HEAD']).trim();
  io.mkdir('packages');
  const lines = [];
  for (const target of targets) {
    const folder = `archives/release-asset-${target}`;
    const found = io.list(folder).filter((name) => name.endsWith('.tar.gz'));
    if (found.length !== 1) {
      throw new Error(`release-asset-${target} holds ${found.length} .tar.gz files; `
        + 'one is expected');
    }
    const unpacked = `${temp}/stage/${target}`;
    io.mkdir(unpacked);
    io.exec('tar', ['-xzf', `${folder}/${found[0]}`, '-C', unpacked, '--no-same-owner']);
    const tops = io.list(unpacked);
    if (tops.length !== 1 || !io.isDir(`${unpacked}/${tops[0]}`)) {
      throw new Error(`${found[0]} must hold one folder, the <bin>/ of the archive layout`);
    }
    for (const [packager, extra] of Object.entries(packagers)) {
      const values = variables({
        version, epoch, packager, target, stage: `${unpacked}/${tops[0]}`, extra,
      });
      const expanded = `${temp}/nfpm-${target}-${packager}.yaml`;
      io.write(expanded, expand(template, values, config));
      const before = new Set(io.list('packages'));
      // The config is filled in already. nfpm gets the piece's own variables
      // and not the packagers values: {"deb": {"PATH": "x"}} would otherwise
      // replace the PATH nfpm is found on.
      const own = Object.fromEntries(OWN.map((name) => [name, values[name]]));
      io.exec('nfpm', ['package', '--config', expanded, '--packager', packager,
        '--target', 'packages'], { env: { ...env, ...own }, stdio: 'inherit' });
      const made = io.list('packages').filter((name) => !before.has(name));
      if (made.length !== 1) {
        throw new Error(`nfpm wrote ${made.length} files for ${target} ${packager}; `
          + 'one is expected');
      }
      const file = made[0];
      checkName(packager, file);
      const back = readBack(packager, `packages/${file}`, io.exec);
      if (back.version !== version && !back.version.startsWith(`${version}-`)) {
        throw new Error(`${file} carries version ${back.version}, not ${version}`);
      }
      if (back.files.length === 0) throw new Error(`${file} holds no files`);
      lines.push(`${file}: version ${back.version}, ${back.files.length} files`);
    }
  }
  return lines;
}

module.exports = { parsePackagers, parseTargets, expand, rfc3339, checkName, run };
```

- [ ] **Step 3: Run the test**

Run: `node --test skills/repo-infra/assets/pieces/workflow-lib/lib/nfpm.test.js`
Expected: PASS, 24 tests. (Both files ran green on 2026-10-11 with node 25; the module uses only `fs`, `child_process` and `Object.hasOwn`, which node 20 in Debian trixie has too.)

- [ ] **Step 4: workflow-lib v9**

```bash
L=skills/repo-infra/assets/pieces/workflow-lib/lib
sed -i '1s|^// repo-infra: workflow-lib v8$|// repo-infra: workflow-lib v9|' $L/*.js
grep -L '^// repo-infra: workflow-lib v9$' $L/*.js    # prints nothing
```

In `$L/release.js`, the `Purpose` line becomes:

```js
// Purpose: The JavaScript the release flow, the publish pieces and the release build pieces run (D8, D32).
```

In `skills/repo-infra/assets/pieces/workflow-lib/CHANGES.md`, above `## v8`:

```markdown
## v9

No caller or config change. nfpm.js carries the logic of ri-release-nfpm, which needs this version; every file carries the new marker.
```

Copy the library into repo-infra's own installation, which `tests/test_self_check.py` holds current and `make test-js` runs:

```bash
cp $L/*.js .github/workflows/lib/
diff -r $L .github/workflows/lib    # no output
```

- [ ] **Step 5: Record, test, gate**

Run: `make generations && make catalogue && make check` (timeout 600000).
Expected: PASS. `git diff skills/repo-infra/assets/generations.json` adds a `"9"` entry to every file of `pieces/workflow-lib/lib/` and the new `pieces/workflow-lib/lib/nfpm.js` and `nfpm.test.js` entries, and changes no recorded digest. `catalogue.md` reads `### workflow-lib v9` with the new purpose. `make test-js` runs `nfpm.test.js` from `.github/workflows/lib/`.

- [ ] **Step 6: Commit**

```bash
git add skills/repo-infra/assets .github/workflows/lib skills/repo-infra/references/catalogue.md
git commit -m "Add the packaging logic of ri-release-nfpm as workflow-lib v9 (D32)

nfpm.js checks the packagers and archives inputs, unpacks each musl
archive, fills in every dollar-brace name of the nfpm config (nfpm itself
expands only top-level scalars), runs nfpm once per packager and reads
every package back. Every refusal is an Error with a one-line message,
which the piece hands to core.setFailed, so a malformed input prints one
::error:: line instead of a stack trace. The file system and the commands
go through an io argument, so nfpm.test.js needs no nfpm, rpm or dpkg-deb
and runs in every repository's ri-ci-lib job. The package names are
checked with parsePackageFile from gitea.js, the names ri-publish-gitea
uploads.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: `ri-release-nfpm`

**Files:**
- Create: `skills/repo-infra/assets/pieces/ri-release-nfpm/ri-release-nfpm.yml`, `.../CHANGES.md`
- Create: `tests/test_release_nfpm.py`, `tests/fixtures/nfpm/repo/nfpm.yaml`, `tests/fixtures/nfpm/repo/pkg/debian/postinst` (mode 755), `tests/fixtures/nfpm/repo/pkg/rpm/post-install.sh`
- Modify: `manifest.json`, `generations.json`, `catalogue.md`

**Interfaces:**
- Consumes: `nfpm.run` (Task 6); mtuspy's `pkg/debian/postinst` and `pkg/rpm/post-install.sh` as they are on its `main`, read with `git show`.
- Produces: the piece `ri-release-nfpm` with inputs `version`, `ref`, `config`, `packagers`, `archives`; artifact `release-asset-packages`. `tests/fixtures/nfpm/repo/nfpm.yaml` is the nfpm config mtuspy copies in Task 11.

- [ ] **Step 1: Fixtures**

`tests/fixtures/nfpm/repo/nfpm.yaml`, translated from mtuspy's two Cargo.toml tables as the spec maps them (`extended-description` becomes the body of `description` under the Cargo `description` line; `section`, `priority`, `maintainer`; `recommends` per packager; `license-file` becomes `copyright` on deb and `LICENSE` on rpm; the two scripts; no `auto-req`):

```yaml
# The .deb and .rpm of mtuspy, built by .github/workflows/ri-release-nfpm.yml
# from the musl archives. The piece fills in VERSION, MTIME and ARCH, and
# STAGE, the unpacked mtuspy/ folder of one archive, before nfpm reads this
# file. Write no dollar-brace name in a comment either: the piece fills in
# the whole file and stops at a name it does not know. nfpm adds no automatic
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

The scripts, from mtuspy:

```bash
M=/home/oetiker/checkouts/mtuspy
git -C $M fetch origin
mkdir -p tests/fixtures/nfpm/repo/pkg/debian tests/fixtures/nfpm/repo/pkg/rpm
git -C $M show origin/main:pkg/debian/postinst > tests/fixtures/nfpm/repo/pkg/debian/postinst
chmod 755 tests/fixtures/nfpm/repo/pkg/debian/postinst
git -C $M show origin/main:pkg/rpm/post-install.sh > tests/fixtures/nfpm/repo/pkg/rpm/post-install.sh
sed -i 's/cargo-generate-rpm writes no %caps,/nfpm.yaml asks for no %caps,/' tests/fixtures/nfpm/repo/pkg/rpm/post-install.sh
grep -c 'nfpm.yaml asks for no %caps,' tests/fixtures/nfpm/repo/pkg/rpm/post-install.sh    # 1
grep -c $'\u2014' tests/fixtures/nfpm/repo/nfpm.yaml    # 0
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_release_nfpm.py
"""ri-release-nfpm (D32). lib/nfpm.js holds the packaging logic and
nfpm.test.js its cases. Here: the piece's call into the library, and, in a
podman container, the pinned nfpm building mtuspy-shaped packages from fake
archives through that library."""

import hashlib
import pathlib
import shutil
import subprocess
import tarfile
import urllib.request

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIECE = ROOT / "skills/repo-infra/assets/pieces/ri-release-nfpm/ri-release-nfpm.yml"
LIB = ROOT / "skills/repo-infra/assets/pieces/workflow-lib/lib"
FIXTURE = ROOT / "tests/fixtures/nfpm"
TARGETS = ["x86_64-unknown-linux-musl", "aarch64-unknown-linux-musl"]
BOTH = '{"deb": {}, "rpm": {}}'
IMAGE = "localhost/repo-infra-nfpm-test"
CONTAINERFILE = ("FROM docker.io/library/debian:trixie\n"
                 "RUN apt-get update && apt-get install -y --no-install-recommends "
                 "rpm git nodejs && rm -rf /var/lib/apt/lists/*\n")
# The step's script with console in place of core: core.setFailed prints its
# message as one ::error:: line and fails the step.
RUNNER = ("const { run } = require('/w/lib/nfpm.js');\n"
          "try {\n"
          "  for (const line of run(process.env)) console.log(line);\n"
          "} catch (error) {\n"
          "  console.log(`::error::${error.message}`);\n"
          "  process.exitCode = 1;\n"
          "}\n")


def doc():
    return yaml.safe_load(PIECE.read_text(encoding="utf-8"))


def steps():
    return {s.get("name"): s for s in doc()["jobs"]["packages"]["steps"]}


def build_step():
    return steps()["Build and read back the packages"]


def test_nfpm_is_pinned_by_version_and_sha256():
    install = steps()["Install nfpm"]
    assert install["env"] == {
        "NFPM_VERSION": "2.47.0",
        "NFPM_SHA256": "0660ca602b2d2d2ae4781a06c692b3eeb9d437ffea05b831d76e41f4a3188783"}
    assert "sha256sum -c -" in install["run"]


def test_the_build_step_runs_the_library_and_fails_with_its_message():
    step = build_step()
    assert step["uses"] == "actions/github-script@v9"
    script = step["with"]["script"]
    assert "require(`${process.env.GITHUB_WORKSPACE}/.github/workflows/lib/nfpm.js`)" in script
    assert "run(process.env)" in script
    assert "core.setFailed(error.message)" in script


def test_the_inputs_reach_the_library_through_env():
    step = build_step()
    assert step["env"] == {"VERSION": "${{ inputs.version }}", "CONFIG": "${{ inputs.config }}",
                           "PACKAGERS": "${{ inputs.packagers }}",
                           "ARCHIVES": "${{ inputs.archives }}"}
    assert "${{" not in step["with"]["script"]


def test_the_piece_names_the_library_it_runs():
    header = PIECE.read_text(encoding="utf-8").split("\n\n", 1)[0]
    assert "# Pieces: ri-release-rust-binaries, workflow-lib" in header
    assert (LIB / "nfpm.js").is_file() and (LIB / "nfpm.test.js").is_file()


def test_the_archives_and_packages_are_where_the_library_looks():
    packages = doc()["jobs"]["packages"]["steps"]
    download = next(s for s in packages if s.get("uses") == "actions/download-artifact@v8")
    assert download["with"] == {"pattern": "release-asset-*", "path": "archives"}
    assert packages[-1]["with"] == {"name": "release-asset-packages", "path": "packages/",
                                    "if-no-files-found": "error"}


def checkout(tmp_path):
    """A checkout with mtuspy's nfpm.yaml and scripts and one commit, the
    archives as download-artifact leaves them, the library and the runner."""
    work = tmp_path / "repo"
    shutil.copytree(FIXTURE / "repo", work)
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.name=test", "-c", "user.email=test@example.org",
                  "commit", "-qm", "fixture"]):
        subprocess.run(["git", *args], cwd=work, check=True)
    stage = tmp_path / "stage" / "mtuspy"
    (stage / "man").mkdir(parents=True)
    (stage / "mtuspy").write_text("#!/bin/sh\necho mtuspy\n")
    (stage / "mtuspy").chmod(0o755)
    (stage / "man" / "mtuspy.1").write_text(".TH MTUSPY 1\n")
    (stage / "README.md").write_text("readme\n")
    (stage / "LICENSE").write_text("license\n")
    for target in TARGETS:
        folder = work / "archives" / f"release-asset-{target}"
        folder.mkdir(parents=True)
        with tarfile.open(folder / f"mtuspy-0.0.0-{target}.tar.gz", "w:gz") as tar:
            tar.add(stage, arcname="mtuspy")
    (tmp_path / "temp").mkdir()
    shutil.copytree(LIB, tmp_path / "lib")
    (tmp_path / "runner.js").write_text(RUNNER)
    return work


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


def in_container(tmp_path, image, nfpm, packagers=BOTH):
    return subprocess.run(
        ["podman", "run", "--rm", "-v", f"{tmp_path}:/w:Z", "-v", f"{nfpm}:/opt/nfpm:ro",
         "-w", "/w/repo", "-e", "PATH=/opt/nfpm:/usr/bin:/bin", "-e", "RUNNER_TEMP=/w/temp",
         "-e", "VERSION=0.0.0", "-e", "CONFIG=nfpm.yaml", "-e", f"PACKAGERS={packagers}",
         "-e", f"ARCHIVES={' '.join(TARGETS)}", image, "node", "/w/runner.js"],
        capture_output=True, text=True, timeout=600)


@pytest.mark.container
def test_the_pinned_nfpm_builds_the_four_packages_and_reads_them_back(tmp_path, image, nfpm):
    work = checkout(tmp_path)
    done = in_container(tmp_path, image, nfpm)
    assert done.returncode == 0, done.stdout + done.stderr
    assert sorted(p.name for p in (work / "packages").iterdir()) == [
        "mtuspy-0.0.0-1.aarch64.rpm", "mtuspy-0.0.0-1.x86_64.rpm",
        "mtuspy_0.0.0-1_amd64.deb", "mtuspy_0.0.0-1_arm64.deb"]
    assert [line for line in done.stdout.splitlines() if ": version " in line] == [
        "mtuspy_0.0.0-1_amd64.deb: version 0.0.0-1, 4 files",
        "mtuspy-0.0.0-1.x86_64.rpm: version 0.0.0, 4 files",
        "mtuspy_0.0.0-1_arm64.deb: version 0.0.0-1, 4 files",
        "mtuspy-0.0.0-1.aarch64.rpm: version 0.0.0, 4 files"]


@pytest.mark.container
def test_a_bad_packagers_input_prints_one_error_line(tmp_path, image, nfpm):
    checkout(tmp_path)
    done = in_container(tmp_path, image, nfpm, packagers='{"deb": "x"}')
    assert done.returncode == 1
    assert done.stdout.splitlines() == [
        '::error::packagers must be a JSON object such as {"deb": {}, "rpm": {"NAME": "value"}}: '
        "one key per packager, each mapping variable names to strings"]
    assert "    at " not in done.stdout + done.stderr
```

Run: `python3 -m pytest -q --basetemp=.pytest-tmp tests/test_release_nfpm.py`. Expected: FAIL, the piece does not exist.

- [ ] **Step 3: Write the piece** `skills/repo-infra/assets/pieces/ri-release-nfpm/ri-release-nfpm.yml` with exactly this content:

```yaml
# repo-infra: ri-release-nfpm v1
#
# Purpose: Build .deb and .rpm packages with nfpm from the musl archives, and read each back (D32).
# Choose: The project is a Rust program users install on Linux (linux-packages in references/project-shape.md).
# Supplies: An nfpm config whose contents take their sources from STAGE; every dollar-brace name in it is set by the piece or by packagers.
# Pieces: ri-release-rust-binaries, workflow-lib
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

      # lib/nfpm.js checks the inputs, unpacks each archive, fills in the
      # config, runs nfpm once per packager and reads every package back.
      # A refusal is one ::error:: line naming what is wrong.
      - name: Build and read back the packages
        uses: actions/github-script@v9
        env:
          VERSION: ${{ inputs.version }}
          CONFIG: ${{ inputs.config }}
          PACKAGERS: ${{ inputs.packagers }}
          ARCHIVES: ${{ inputs.archives }}
        with:
          script: |
            const { run } = require(`${process.env.GITHUB_WORKSPACE}/.github/workflows/lib/nfpm.js`);
            try {
              for (const line of run(process.env)) core.info(line);
            } catch (error) {
              core.setFailed(error.message);
            }

      - uses: actions/upload-artifact@v7
        with:
          name: release-asset-packages
          path: packages/
          if-no-files-found: error
```

- [ ] **Step 4: `CHANGES.md`** in the piece's folder:

```markdown
# ri-release-nfpm

Upgrade notes, newest first. Each section says what a caller or
.github/repo-infra.json must change to take that version.

## v1

First version. It needs workflow-lib v9, whose nfpm.js carries its logic. Move the package tables of Cargo.toml into an nfpm config whose contents take their sources from STAGE, and call the piece after ri-release-rust-binaries as the catalogue shows. The file names stay those of cargo-deb and cargo-generate-rpm, so release_assets does not change.
```

Add the manifest entry.

- [ ] **Step 5: Register and test**

Run: `make generations && make catalogue && python3 -m pytest -q --basetemp=.pytest-tmp tests/test_release_nfpm.py tests/test_pieces.py tests/test_catalogue.py`
Expected: PASS (the container tests are deselected here).

Run: `systemd-run --user --scope -p MemoryMax=4G -- python3 -m pytest --basetemp=.pytest-tmp -m container -v tests/test_release_nfpm.py` (timeout 600000).
Expected: PASS. This is the first run of the rpm half anywhere (there is no `rpm` on this host); a difference in the file counts or the rpm names is a finding about nfpm's rpm output, fixed in `nfpm.js` or the fixture config before the commit, with the reason in the commit message.

- [ ] **Step 6: Gate and commit**

Run: `make check` (timeout 600000). Expected: PASS.

```bash
git add skills/repo-infra/assets skills/repo-infra/references/catalogue.md tests/test_release_nfpm.py tests/fixtures/nfpm
git commit -m "Add ri-release-nfpm v1 (D32)

The piece installs the pinned nfpm and rpm and hands its inputs to
lib/nfpm.js through env. v1 has the archives mode only. The container
test runs the library with node in Debian with the pinned nfpm on fake
archives and mtuspy's package config, and checks that a malformed
packagers input prints one ::error:: line.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: `lib/homebrew.js` and `ri-release-homebrew`

**Files:**
- Create: `skills/repo-infra/assets/pieces/workflow-lib/lib/homebrew.js`, `.../lib/homebrew.test.js` (both at workflow-lib v9, which is not released yet, so no second bump)
- Create: `skills/repo-infra/assets/pieces/ri-release-homebrew/ri-release-homebrew.yml`, `.../CHANGES.md`, `tests/test_release_homebrew.py`
- Modify: `skills/repo-infra/assets/pieces/workflow-lib/CHANGES.md` (the v9 note), `.github/workflows/lib/`, `manifest.json`, `generations.json`, `catalogue.md`

**Interfaces:**
- Consumes: the formula template of `references/project-shape.md` (Task 2).
- Produces: `homebrew.pointAtArchives(env, io)`, `homebrew.renameBottles(io)`, `homebrew.rewriteFormula(env, io)`, each throwing an `Error` with a one-line message on a refusal; `localFormula`, `bottleFiles`, `bottleBlock`, `releaseFormula` and `MARKERS` for the tests. The piece `ri-release-homebrew` with inputs `version`, `ref`, `bin`; jobs `bottles`, `formula`; artifacts `release-asset-bottle-<os>`, `bottle-json-<os>`, `release-files`.

- [ ] **Step 1: Write the failing library test** `skills/repo-infra/assets/pieces/workflow-lib/lib/homebrew.test.js`

```js
// repo-infra: workflow-lib v9
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('crypto');
const brew = require('./homebrew.js');

// The formula template of references/project-shape.md with its placeholders
// filled in; tests/test_release_homebrew.py holds the two to the same text.
const FORMULA = `# Homebrew formula for tool. This repository is its own tap.
#
# The release build rewrites the version line, the four sha256 lines by their
# marker comments and the bottle block between the BOTTLE markers. Keep the
# markers, and keep each url line directly above its sha256 line.
class Tool < Formula
  desc "A tool"
  homepage "https://github.com/owner/tool"
  version "0.0.0"
  license "MIT"

  # BOTTLE-START
  # BOTTLE-END

  on_macos do
    on_arm do
      url "https://github.com/owner/tool/releases/download/v#{version}/tool-#{version}-aarch64-apple-darwin.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000" # mac-arm
    end
    on_intel do
      url "https://github.com/owner/tool/releases/download/v#{version}/tool-#{version}-x86_64-apple-darwin.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000" # mac-x86
    end
  end

  on_linux do
    on_intel do
      url "https://github.com/owner/tool/releases/download/v#{version}/tool-#{version}-x86_64-unknown-linux-musl.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000" # linux-x86
    end
    on_arm do
      url "https://github.com/owner/tool/releases/download/v#{version}/tool-#{version}-aarch64-unknown-linux-musl.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000" # linux-arm
    end
  end

  def install
    bin.install "tool"
    Dir["man/*.[1-9]"].each { |page| (man/"man#{page[-1]}").install page }
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/tool --version")
  end
end
`;
const ENV = { BIN: 'tool', VERSION: '1.2.3', GITHUB_REPOSITORY: 'owner/tool', RUNNER_TEMP: '/t' };

// The shape `brew bottle --json --no-rebuild` writes: one entry per formula,
// the cellar on the bottle, the two file names on each tag.
function bottleJson(tag, sha, cellar) {
  const entry = { filename: `tool-1.2.3.${tag}.bottle.tar.gz`,
    local_filename: `tool--1.2.3.${tag}.bottle.tar.gz`, sha256: sha };
  if (cellar) entry.cellar = cellar;
  return { 'local/tool/tool': { formula: { name: 'tool', pkg_version: '1.2.3' },
    bottle: { cellar: 'any_skip_relocation', rebuild: 0, tags: { [tag]: entry } } } };
}
const ARM = bottleJson('arm64_sonoma', 'a'.repeat(64));
const INTEL = bottleJson('sequoia', 'b'.repeat(64));

function digest(text) {
  return crypto.createHash('sha256').update(text).digest('hex');
}

// A checkout as the bottle and formula jobs see it: `files` maps a path,
// relative to /w, to its text.
function fakeIo(files) {
  const store = new Map(Object.entries(files));
  return {
    store,
    cwd: () => '/w',
    isFile: (path) => store.has(path.replace(/^\/w\//, '')),
    read: (path) => store.get(path.replace(/^\/w\//, '')),
    write: (path, text) => store.set(path.replace(/^\/w\//, ''), text),
    mkdir: () => {},
    list: (dir) => [...store.keys()]
      .filter((p) => (dir === '.' ? !p.includes('/') : p.startsWith(`${dir}/`)))
      .map((p) => (dir === '.' ? p : p.slice(dir.length + 1)))
      .filter((p) => !p.includes('/')).sort(),
    rename: (from, to) => { store.set(to, store.get(from)); store.delete(from); },
    copy: (from, to) => store.set(to, store.get(from)),
    sha256: (path) => digest(store.get(path.replace(/^\/w\//, ''))),
  };
}

function archives(prefix, targets = Object.values(brew.MARKERS)) {
  return Object.fromEntries(targets.map((t) => [`${prefix}/tool-1.2.3-${t}.tar.gz`, `archive ${t}`]));
}

function formulaJob({ formula = FORMULA, jsons = [ARM, INTEL], built = true } = {}) {
  const files = { 'Formula/tool.rb': formula, ...archives('artifacts') };
  jsons.forEach((json, i) => {
    files[`bottles/${i}.bottle.json`] = JSON.stringify(json);
    if (built) for (const { to } of brew.bottleFiles(json)) files[`artifacts/${to}`] = 'bottle';
  });
  return fakeIo(files);
}

function block(text) {
  return text.split('  # BOTTLE-START\n')[1].split('  # BOTTLE-END')[0];
}

function refusal(fn, expected) {
  assert.throws(fn, (error) => {
    assert.match(error.message, expected);
    assert.doesNotMatch(error.message, /\n/);
    return true;
  });
}

test('the local tap points the mac urls at the built archives', () => {
  const io = fakeIo({ 'Formula/tool.rb': FORMULA,
    ...archives('dist', ['aarch64-apple-darwin', 'x86_64-apple-darwin']) });
  assert.equal(brew.pointAtArchives(ENV, io), '/t/local-formula.rb');
  const local = io.store.get('/t/local-formula.rb');
  for (const [marker, target] of [['mac-arm', 'aarch64-apple-darwin'], ['mac-x86', 'x86_64-apple-darwin']]) {
    assert.ok(local.includes(`      url "file:///w/dist/tool-1.2.3-${target}.tar.gz"\n`
      + `      sha256 "${digest(`archive ${target}`)}" # ${marker}\n`), marker);
  }
  assert.equal(local.split('/releases/download/v#{version}/').length - 1, 2, 'the linux urls stay');
  assert.match(local, /^ {2}version "1\.2\.3"$/m);
  assert.ok(local.includes('  # BOTTLE-START\n  # BOTTLE-END\n'));
});

for (const damage of ['deleted', 'blank line', 'comment']) {
  test(`a mac sha256 line without its url line directly above fails (${damage})`, () => {
    const lines = FORMULA.split('\n');
    const i = lines.findIndex((line) => line.endsWith('# mac-x86'));
    if (damage === 'deleted') lines.splice(i - 1, 1);
    else lines.splice(i, 0, damage === 'blank line' ? '' : '      # the Intel archive');
    const io = fakeIo({ 'Formula/tool.rb': lines.join('\n'),
      ...archives('dist', ['aarch64-apple-darwin', 'x86_64-apple-darwin']) });
    refusal(() => brew.pointAtArchives(ENV, io),
      /^no url line directly above the # mac-x86 sha256 line$/);
  });
}

test('a missing mac archive fails the local tap', () => {
  const io = fakeIo({ 'Formula/tool.rb': FORMULA, ...archives('dist', ['aarch64-apple-darwin']) });
  refusal(() => brew.pointAtArchives(ENV, io),
    /^\/w\/dist\/tool-1\.2\.3-x86_64-apple-darwin\.tar\.gz was not built$/);
});

test('a missing formula fails naming it', () => {
  refusal(() => brew.pointAtArchives(ENV, fakeIo({})), /^Formula\/tool\.rb does not exist$/);
});

test('the bottles get the names their json records', () => {
  const io = fakeIo({ 'arm.bottle.json': JSON.stringify(ARM), 'intel.bottle.json': JSON.stringify(INTEL),
    'tool--1.2.3.arm64_sonoma.bottle.tar.gz': 'a', 'tool--1.2.3.sequoia.bottle.tar.gz': 'b' });
  assert.deepEqual(brew.renameBottles(io),
    ['tool-1.2.3.arm64_sonoma.bottle.tar.gz', 'tool-1.2.3.sequoia.bottle.tar.gz']);
  assert.deepEqual(io.list('bottle'), ['arm.bottle.json', 'intel.bottle.json',
    'tool-1.2.3.arm64_sonoma.bottle.tar.gz', 'tool-1.2.3.sequoia.bottle.tar.gz']);
});

test('no bottle json fails the rename', () => {
  refusal(() => brew.renameBottles(fakeIo({})), /^brew bottle wrote no json$/);
});

test('two bottles give the version, the four checksums and both bottles', () => {
  const io = formulaJob();
  const text = brew.rewriteFormula(ENV, io);
  assert.match(text, /^ {2}version "1\.2\.3"$/m);
  for (const [marker, target] of Object.entries(brew.MARKERS)) {
    assert.ok(text.includes(`sha256 "${digest(`archive ${target}`)}" # ${marker}\n`), marker);
  }
  assert.equal(block(text), [
    '  bottle do',
    '    root_url "https://github.com/owner/tool/releases/download/v1.2.3"',
    `    sha256 cellar: :any_skip_relocation, arm64_sonoma: "${'a'.repeat(64)}"`,
    `    sha256 cellar: :any_skip_relocation, sequoia: "${'b'.repeat(64)}"`,
    '  end', ''].join('\n'));
  assert.equal(io.store.get('Formula/tool.rb'), text);
  assert.equal(io.store.get('release-files/Formula/tool.rb'), text);
});

test('the cellar of a tag wins, and a Cellar path is quoted', () => {
  const lines = brew.bottleBlock([bottleJson('sonoma', 'c'.repeat(64), '/opt/homebrew/Cellar')],
    { repository: 'owner/tool', version: '1.2.3' });
  assert.equal(lines[2], `    sha256 cellar: "/opt/homebrew/Cellar", sonoma: "${'c'.repeat(64)}"`);
});

test('a bottle json without a cellar fails naming the tag', () => {
  const json = bottleJson('sonoma', 'c'.repeat(64));
  delete json['local/tool/tool'].bottle.cellar;
  refusal(() => brew.bottleBlock([json], { repository: 'owner/tool', version: '1.2.3' }),
    /^the bottle json of sonoma names no cellar$/);
});

test('the optional bottle missing still publishes the other', () => {
  const text = brew.rewriteFormula(ENV, formulaJob({ jsons: [ARM] }));
  assert.equal(block(text).split('sha256 cellar:').length - 1, 1);
});

test('zero bottles fail', () => {
  refusal(() => brew.rewriteFormula(ENV, formulaJob({ jsons: [] })), /^no bottles were built$/);
});

test('a bottle missing under its recorded name fails', () => {
  refusal(() => brew.rewriteFormula(ENV, formulaJob({ built: false })),
    /^bottle tool-1\.2\.3\.arm64_sonoma\.bottle\.tar\.gz was not built under that name$/);
});

test('a missing archive fails the formula job', () => {
  const io = formulaJob();
  io.store.delete('artifacts/tool-1.2.3-aarch64-unknown-linux-musl.tar.gz');
  refusal(() => brew.rewriteFormula(ENV, io),
    /^artifacts\/tool-1\.2\.3-aarch64-unknown-linux-musl\.tar\.gz was not built$/);
});

for (const marker of ['mac-arm', 'mac-x86', 'linux-x86', 'linux-arm', 'BOTTLE-START', 'BOTTLE-END']) {
  test(`a missing marker # ${marker} fails`, () => {
    const io = formulaJob({ formula: FORMULA.replace(` # ${marker}`, '') });
    refusal(() => brew.rewriteFormula(ENV, io),
      new RegExp(`^the marker # ${marker} is gone from Formula/tool\\.rb$`));
  });
}

test('a formula without a version line fails', () => {
  const io = formulaJob({ formula: FORMULA.replace('  version "0.0.0"\n', '') });
  refusal(() => brew.rewriteFormula(ENV, io), /^Formula\/tool\.rb has no version line$/);
});

test('a second run changes nothing', () => {
  const io = formulaJob();
  const first = brew.rewriteFormula(ENV, io);
  assert.equal(brew.rewriteFormula(ENV, io), first);
});

test('the previous release block is replaced whole', () => {
  const old = '  # BOTTLE-START\n  bottle do\n'
    + '    root_url "https://github.com/owner/tool/releases/download/v9.9.9"\n'
    + `    sha256 cellar: :any_skip_relocation, old_tag: "${'1'.repeat(64)}"\n`
    + '  end\n  # BOTTLE-END';
  const formula = FORMULA.replace('  # BOTTLE-START\n  # BOTTLE-END', old);
  const inside = block(brew.rewriteFormula(ENV, formulaJob({ formula })));
  assert.doesNotMatch(inside, /v9\.9\.9|old_tag/);
  assert.match(inside, /root_url "https:\/\/github\.com\/owner\/tool\/releases\/download\/v1\.2\.3"/);
});
```

`FORMULA` is the template of `references/project-shape.md` with `Tool`, `A tool`, `owner`, `tool`, `MIT` and `tool` for its placeholders; Step 4 holds the two to the same text. `bottleJson` has the shape `brew bottle --json --no-rebuild` writes; Task 13 checks the json recorded in mtuspy's baseline run against the same keys.

Run: `node --test skills/repo-infra/assets/pieces/workflow-lib/lib/homebrew.test.js`
Expected: FAIL with `Cannot find module './homebrew.js'`.

- [ ] **Step 2: Write `skills/repo-infra/assets/pieces/workflow-lib/lib/homebrew.js`**

```js
// repo-infra: workflow-lib v9
'use strict';

// ri-release-homebrew (D32): the three formula steps around the bottle
// build. The formula follows the template in references/project-shape.md: a
// url line directly above each of the four sha256 lines marked # mac-arm,
// # mac-x86, # linux-x86 and # linux-arm, and the bottle block between
// # BOTTLE-START and # BOTTLE-END. The steps in ri-release-homebrew.yml hand
// these functions their environment and nothing else. The file system goes
// through `io`, which the tests replace.

const MARKERS = {
  'mac-arm': 'aarch64-apple-darwin',
  'mac-x86': 'x86_64-apple-darwin',
  'linux-x86': 'x86_64-unknown-linux-musl',
  'linux-arm': 'aarch64-unknown-linux-musl',
};
const VERSION_LINE = /^ {2}version ".*"$/m;
const SHA = /sha256 "[0-9a-f]*"/;

function shaLines(lines, marker) {
  const pattern = new RegExp(`${SHA.source} # ${marker}\\s*$`);
  return lines.flatMap((line, i) => (pattern.test(line) ? [i] : []));
}

function setVersion(text, version) {
  return text.replace(VERSION_LINE, `  version "${version}"`);
}

// The lines between the two BOTTLE markers are replaced in place, so a
// second run writes the same file.
function withBlock(text, inner, formula) {
  const lines = text.split('\n');
  const start = lines.findIndex((line) => line.includes('# BOTTLE-START'));
  const end = lines.findIndex((line) => line.includes('# BOTTLE-END'));
  for (const [marker, at] of [['BOTTLE-START', start], ['BOTTLE-END', end]]) {
    if (at < 0) throw new Error(`the marker # ${marker} is gone from ${formula}`);
  }
  if (end < start) throw new Error(`# BOTTLE-END stands above # BOTTLE-START in ${formula}`);
  return [...lines.slice(0, start + 1), ...inner, ...lines.slice(end)].join('\n');
}

// The release does not exist yet, so the local tap points each mac url line
// at the archive this run built. A url line anywhere but directly above its
// sha256 line would be left alone, and brew would fetch a GitHub url that
// answers 404.
function localFormula(text, { formula, version, archives }) {
  const lines = text.split('\n');
  const problems = [];
  for (const marker of ['mac-arm', 'mac-x86']) {
    const found = shaLines(lines, marker);
    if (found.length !== 1) {
      problems.push(`${formula} needs one # ${marker} sha256 line, not ${found.length}`);
      continue;
    }
    const i = found[0];
    if (i === 0 || !/^\s*url "/.test(lines[i - 1])) {
      problems.push(`no url line directly above the # ${marker} sha256 line`);
      continue;
    }
    const indent = lines[i - 1].match(/^\s*/)[0];
    lines[i - 1] = `${indent}url "${archives[marker].url}"`;
    lines[i] = lines[i].replace(SHA, `sha256 "${archives[marker].sha}"`);
  }
  if (problems.length > 0) throw new Error(problems.join('; '));
  return withBlock(setVersion(lines.join('\n'), version), [], formula);
}

// `brew bottle` writes name--version.tag.bottle.tar.gz, with two dashes, the
// name GitHub Packages wants. A plain root_url is fetched with one dash. The
// json records both names.
function bottleFiles(json) {
  return Object.values(json).flatMap((entry) => Object.values(entry.bottle.tags)
    .map((tag) => ({ from: tag.local_filename, to: tag.filename })));
}

// `cellar` sits on the bottle and `brew bottle` copies it onto each tag; the
// tag's own value wins. A relocatable bottle names a symbol such as
// any_skip_relocation, a fixed one the Cellar path, which Ruby needs quoted.
function cellar(value) {
  return value.startsWith('/') ? `"${value}"` : `:${value}`;
}

// Generated, not patched: which architectures produced a bottle is known
// only now, and a sha256 line for a bottle that was never built sends
// Homebrew after a file that does not exist.
function bottleBlock(jsons, { repository, version }) {
  const lines = ['  bottle do',
    `    root_url "https://github.com/${repository}/releases/download/v${version}"`];
  for (const json of jsons) {
    for (const { bottle } of Object.values(json)) {
      for (const [tag, entry] of Object.entries(bottle.tags)) {
        const value = entry.cellar || bottle.cellar;
        if (!value) throw new Error(`the bottle json of ${tag} names no cellar`);
        lines.push(`    sha256 cellar: ${cellar(value)}, `
          + `${tag}: "${entry.sha256}"`);
      }
    }
  }
  lines.push('  end');
  return lines;
}

// The formula arrives carrying the previous release's bottle block. Left
// alone, it would publish a root_url pointing at the previous tag under
// this version: mdmost v0.3.2 did, and every brew install met a 404. Zero
// bottles fails for the same reason.
function releaseFormula(text, { formula, version, shas, jsons, built, repository }) {
  if (!VERSION_LINE.test(text)) throw new Error(`${formula} has no version line`);
  const lines = text.split('\n');
  for (const marker of Object.keys(MARKERS)) {
    const found = shaLines(lines, marker);
    if (found.length === 0) throw new Error(`the marker # ${marker} is gone from ${formula}`);
    if (found.length > 1) {
      throw new Error(`the marker # ${marker} stands on ${found.length} lines of ${formula}`);
    }
    lines[found[0]] = lines[found[0]].replace(SHA, `sha256 "${shas[marker]}"`);
  }
  const rewritten = withBlock(setVersion(lines.join('\n'), version), [], formula);
  if (jsons.length === 0) throw new Error('no bottles were built');
  for (const { to } of jsons.flatMap(bottleFiles)) {
    if (!built.includes(to)) throw new Error(`bottle ${to} was not built under that name`);
  }
  return withBlock(rewritten, bottleBlock(jsons, { repository, version }), formula);
}

function nodeIo() {
  const fs = require('fs');
  const crypto = require('crypto');
  return {
    cwd: () => process.cwd(),
    isFile: (path) => fs.existsSync(path) && fs.statSync(path).isFile(),
    read: (path) => fs.readFileSync(path, 'utf8'),
    write: (path, text) => fs.writeFileSync(path, text),
    mkdir: (path) => fs.mkdirSync(path, { recursive: true }),
    list: (path) => (fs.existsSync(path) ? fs.readdirSync(path).sort() : []),
    rename: (from, to) => fs.renameSync(from, to),
    copy: (from, to) => fs.copyFileSync(from, to),
    sha256: (path) => crypto.createHash('sha256').update(fs.readFileSync(path)).digest('hex'),
  };
}

function formulaOf(env, io) {
  const formula = `Formula/${env.BIN}.rb`;
  if (!io.isFile(formula)) throw new Error(`${formula} does not exist`);
  return formula;
}

// Bottle leg, before `brew install --build-bottle`: the formula of the local
// tap, written to $RUNNER_TEMP/local-formula.rb. dist/ holds the two mac
// archives.
function pointAtArchives(env, io = nodeIo()) {
  const formula = formulaOf(env, io);
  const archives = {};
  for (const marker of ['mac-arm', 'mac-x86']) {
    const path = `${io.cwd()}/dist/${env.BIN}-${env.VERSION}-${MARKERS[marker]}.tar.gz`;
    if (!io.isFile(path)) throw new Error(`${path} was not built`);
    archives[marker] = { url: `file://${path}`, sha: io.sha256(path) };
  }
  const out = `${env.RUNNER_TEMP}/local-formula.rb`;
  io.write(out, localFormula(io.read(formula), { formula, version: env.VERSION, archives }));
  return out;
}

// Bottle leg, after `brew bottle --json`: bottle/ receives each bottle under
// the name its json records, and the json.
function renameBottles(io = nodeIo()) {
  const jsons = io.list('.').filter((name) => name.endsWith('.bottle.json'));
  if (jsons.length === 0) throw new Error('brew bottle wrote no json');
  io.mkdir('bottle');
  const moved = [];
  for (const name of jsons) {
    for (const { from, to } of bottleFiles(JSON.parse(io.read(name)))) {
      io.rename(from, `bottle/${to}`);
      moved.push(to);
    }
    io.copy(name, `bottle/${name}`);
  }
  return moved;
}

// Formula job: artifacts/ holds every release asset, bottles/ the json of
// every bottle leg that finished. Writes the formula in place and as
// release-files/Formula/<bin>.rb, and returns it for the log.
function rewriteFormula(env, io = nodeIo()) {
  const formula = formulaOf(env, io);
  const shas = {};
  for (const [marker, target] of Object.entries(MARKERS)) {
    const archive = `artifacts/${env.BIN}-${env.VERSION}-${target}.tar.gz`;
    if (!io.isFile(archive)) throw new Error(`${archive} was not built`);
    shas[marker] = io.sha256(archive);
  }
  const jsons = io.list('bottles').filter((name) => name.endsWith('.bottle.json'))
    .map((name) => JSON.parse(io.read(`bottles/${name}`)));
  const text = releaseFormula(io.read(formula), {
    formula, version: env.VERSION, shas, jsons, built: io.list('artifacts'),
    repository: env.GITHUB_REPOSITORY,
  });
  io.write(formula, text);
  io.mkdir('release-files/Formula');
  io.write(`release-files/Formula/${env.BIN}.rb`, text);
  return text;
}

module.exports = {
  MARKERS, localFormula, bottleFiles, bottleBlock, releaseFormula,
  pointAtArchives, renameBottles, rewriteFormula,
};
```

Run: `node --test skills/repo-infra/assets/pieces/workflow-lib/lib/homebrew.test.js`
Expected: PASS, 24 tests (green on 2026-10-11 with node 25).

The v9 note in `skills/repo-infra/assets/pieces/workflow-lib/CHANGES.md` becomes:

```markdown
## v9

No caller or config change. nfpm.js and homebrew.js carry the logic of ri-release-nfpm and ri-release-homebrew, which need this version; every file carries the new marker.
```

```bash
cp skills/repo-infra/assets/pieces/workflow-lib/lib/*.js .github/workflows/lib/
diff -r skills/repo-infra/assets/pieces/workflow-lib/lib .github/workflows/lib    # no output
```

- [ ] **Step 3: Write the failing piece test**

```python
# tests/test_release_homebrew.py
"""ri-release-homebrew (D32). lib/homebrew.js holds the three formula steps
and homebrew.test.js their cases. Here: the jobs, the piece's calls into the
library, and that the formula the library tests use is the template the
shape reference publishes."""

import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIECE = ROOT / "skills/repo-infra/assets/pieces/ri-release-homebrew/ri-release-homebrew.yml"
LIB = ROOT / "skills/repo-infra/assets/pieces/workflow-lib/lib"
SHAPE = ROOT / "skills/repo-infra/references/project-shape.md"
FILLED = {"<Class>": "Tool", "<one-line description>": "A tool", "<owner>": "owner",
          "<repo>": "tool", "<SPDX license>": "MIT", "<bin>": "tool"}
LIBRARY = "require(`${process.env.GITHUB_WORKSPACE}/.github/workflows/lib/homebrew.js`)"


def doc():
    return yaml.safe_load(PIECE.read_text(encoding="utf-8"))


def step(job, name):
    return next(s for s in doc()["jobs"][job]["steps"] if s.get("name") == name)


def test_the_bottle_legs_and_the_formula_condition():
    jobs = doc()["jobs"]
    assert jobs["bottles"]["strategy"]["matrix"]["include"] == [
        {"os": "macos-14"}, {"os": "macos-15-intel", "optional": True}]
    assert jobs["bottles"]["continue-on-error"] == "${{ matrix.optional || false }}"
    assert jobs["formula"]["needs"] == "bottles"
    assert jobs["formula"]["if"] == "${{ !cancelled() }}"


def test_brew_trust_runs_on_homebrew_6_and_a_failure_is_not_swallowed():
    tap = step("bottles", "Local tap")["run"]
    assert '-ge 6 ]' in tap and "brew trust --formula" in tap and "|| true" not in tap


def test_the_root_url_comes_from_the_repository_of_the_run():
    text = PIECE.read_text(encoding="utf-8")
    lib = (LIB / "homebrew.js").read_text(encoding="utf-8")
    assert '--root-url="https://github.com/$GITHUB_REPOSITORY/releases/download/v$VERSION"' in text
    assert "https://github.com/${repository}/releases/download/v${version}" in lib
    assert "oetiker" not in text and "oetiker" not in lib


@pytest.mark.parametrize("job,name,call", [
    ("bottles", "Point the formula at the built archives", "pointAtArchives(process.env)"),
    ("bottles", "Rename the bottles", "renameBottles()"),
    ("formula", "Rewrite the formula", "rewriteFormula(process.env)"),
])
def test_each_formula_step_runs_the_library_and_fails_with_its_message(job, name, call):
    found = step(job, name)
    assert found["uses"] == "actions/github-script@v9"
    script = found["with"]["script"]
    assert LIBRARY in script and call in script
    assert "core.setFailed(error.message)" in script
    assert "${{" not in script


def test_no_formula_logic_is_left_in_shell():
    runs = [s.get("run", "") for job in doc()["jobs"].values() for s in job["steps"]]
    for tool in ("awk ", "jq ", "sed -i", "sha256sum", "shasum"):
        assert not any(tool in run for run in runs), tool


def test_the_piece_names_the_library_it_runs():
    header = PIECE.read_text(encoding="utf-8").split("\n\n", 1)[0]
    assert "# Pieces: ri-release-rust-binaries, workflow-lib" in header


def test_the_library_tests_use_the_template_of_the_shape_reference():
    section = SHAPE.read_text(encoding="utf-8").split("\n## Formula template\n", 1)[1]
    ruby = re.search(r"```ruby\n(.*?)```", section, re.S).group(1)
    for placeholder, value in FILLED.items():
        ruby = ruby.replace(placeholder, value)
    tests = (LIB / "homebrew.test.js").read_text(encoding="utf-8")
    assert re.search(r"const FORMULA = `(.*?)`;\n", tests, re.S).group(1) == ruby
```

Run: `python3 -m pytest -q --basetemp=.pytest-tmp tests/test_release_homebrew.py`. Expected: FAIL, the piece does not exist. (`test_the_library_tests_use_the_template_of_the_shape_reference` passes already: the template text of Task 2 and `FORMULA` were compared on 2026-10-11.)

- [ ] **Step 4: Write the piece** `skills/repo-infra/assets/pieces/ri-release-homebrew/ri-release-homebrew.yml` with exactly this content:

```yaml
# repo-infra: ri-release-homebrew v1
#
# Purpose: Bottle the formula on macOS and rewrite Formula/<bin>.rb for the release (D32).
# Choose: The project is a Rust program users install with Homebrew (homebrew in references/project-shape.md).
# Supplies: Formula/<bin>.rb from the template in references/project-shape.md, listed in release_files.
# Pieces: ri-release-rust-binaries, workflow-lib
# Produces: The artifacts release-asset-bottle-<os> (list the arm64 bottle in release_assets) and release-files with the formula; no other job may write release-files.
# Call:
#   homebrew:
#     needs: binaries
#     uses: ./.github/workflows/ri-release-homebrew.yml
#     with:
#       version: ${{ inputs.version }}
#       ref: ${{ inputs.ref }}
#       bin: mytool

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

      # The release does not exist yet, so the local tap reads a formula whose
      # mac url lines point at the archives this run built (lib/homebrew.js).
      # A url line anywhere but directly above its sha256 line fails here;
      # left alone, brew would fetch a GitHub url that answers 404.
      - name: Point the formula at the built archives
        uses: actions/github-script@v9
        with:
          script: |
            const { pointAtArchives } = require(`${process.env.GITHUB_WORKSPACE}/.github/workflows/lib/homebrew.js`);
            try {
              core.info(`The local tap reads ${pointAtArchives(process.env)}`);
            } catch (error) {
              core.setFailed(error.message);
            }

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

      # `brew bottle` writes name--version.tag.bottle.tar.gz; the release
      # carries the name its json records (lib/homebrew.js).
      - name: Rename the bottles
        uses: actions/github-script@v9
        with:
          script: |
            const { renameBottles } = require(`${process.env.GITHUB_WORKSPACE}/.github/workflows/lib/homebrew.js`);
            try {
              for (const name of renameBottles()) core.info(`bottle/${name}`);
            } catch (error) {
              core.setFailed(error.message);
            }

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

      # The version, the four archive checksums and a bottle block generated
      # from the bottles that were built (lib/homebrew.js). The result is the
      # formula in place and release-files/Formula/<bin>.rb.
      - name: Rewrite the formula
        uses: actions/github-script@v9
        env:
          BIN: ${{ inputs.bin }}
          VERSION: ${{ inputs.version }}
        with:
          script: |
            const { rewriteFormula } = require(`${process.env.GITHUB_WORKSPACE}/.github/workflows/lib/homebrew.js`);
            try {
              core.info(rewriteFormula(process.env));
            } catch (error) {
              core.setFailed(error.message);
            }

      - uses: actions/upload-artifact@v7
        with:
          name: release-files
          path: release-files/
          if-no-files-found: error
```

- [ ] **Step 5: `CHANGES.md`** in the piece's folder:

```markdown
# ri-release-homebrew

Upgrade notes, newest first. Each section says what a caller or
.github/repo-infra.json must change to take that version.

## v1

First version. It needs workflow-lib v9, whose homebrew.js carries its formula steps. The formula follows the template in references/project-shape.md: each url line directly above its sha256 line, the four sha256 marker comments, and the BOTTLE markers. Remove any other job that writes release-files, and call the piece after ri-release-rust-binaries as the catalogue shows.
```

Add the manifest entry.

- [ ] **Step 6: Register, test, gate, commit**

Run: `make generations && make catalogue && make check` (timeout 600000). Expected: PASS; `generations.json` gains `pieces/workflow-lib/lib/homebrew.js` and `homebrew.test.js` at `"9"` and the piece at `"1"`, and changes no recorded digest.

```bash
git add skills/repo-infra/assets .github/workflows/lib skills/repo-infra/references/catalogue.md tests/test_release_homebrew.py
git commit -m "Add ri-release-homebrew v1 with its formula steps in workflow-lib (D32)

The local-tap rewrite, the bottle rename and the formula rewrite are
homebrew.js in workflow-lib v9 instead of awk, sed and jq. The bottle
legs run the BSD awk of macOS, while a test on Linux runs GNU awk, so the
tested program was not the shipped one; node is the same on both. A
cellar that is a path is now quoted, as Ruby needs it. The piece keeps
the bottle legs, the trust guard and the brew calls as shell.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Name the pieces in the shape, changelog, and the pull request

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

- [ ] **Step 2: Amend `project-shape.md`** (decision P9)

- `native-targets`, Met by: `Met by: \`ri-release-rust-binaries\`. mise's \`github:\` backend picks an asset by these names, so \`mise use -g github:<owner>/<repo>\` works without further setup.`
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

and under `### Changed`:

```markdown
- `/repo-infra:check` reports `workflow-lib` as outdated until `apply` installs v9, which `ri-release-nfpm` and `ri-release-homebrew` need.
```

- [ ] **Step 4: Gate and commit**

Run: `make check` and `systemd-run --user --scope -p MemoryMax=4G -- make test-container` (timeouts 600000). Expected: PASS.

```bash
git add skills/repo-infra/references tests/test_project_shape.py CHANGES.md
git commit -m "Name the release pieces in the project shape (D32)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: [outward] Push and open a draft pull request**

```bash
S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
cat > $S/pr-pieces.md <<'EOF'
Three release pieces for Rust programs (D32, #53): `ri-release-rust-binaries`, `ri-release-nfpm` and `ri-release-homebrew`. Their logic is in workflow-lib v9 (`lib/nfpm.js`, `lib/homebrew.js`), tested with `node --test`.

mtuspy proves them from this branch before it merges (Tasks 10 to 14 of `docs/superpowers/plans/2026-10-10-project-shape.md`), so the pull request stays a draft until then.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
git push -u origin feat/release-pieces
gh pr create --draft --base main --title "Release pieces for Rust programs (D32)" --body-file $S/pr-pieces.md
gh pr checks --watch
```

Expected: `ci-passed` and `changelog-updated` green. The pull request does not merge here; Task 15 merges it.

---
# Phase C: the proof in mtuspy and its first release

Facts this phase starts from, read on 2026-10-10: mtuspy's latest release is
v0.1.3 (2026-02-13) with seven archives and nothing else. Its
`release-build.yml` (cargo-deb, cargo-generate-rpm, bottles, formula rewrite)
was added on 2026-10-07 and has never run. `Formula/mtuspy.rb` holds four
all-zero `sha256` lines and already follows the template's structure (the four
markers, each `url` directly above its `sha256`, the BOTTLE markers). mtuspy
carries workflow-lib v8. v0.1.3's own release workflow built illumos with
`crt-static` through cross and published the archive, so the baseline run is
expected to build all seven targets.

`RIB=/scratch/oetiker/claude-worktrees/repo-infra-release-pieces` (Phase B),
`M=/home/oetiker/checkouts/mtuspy`.

### Task 10: Proof branch and the baseline run

**Files (mtuspy):**
- Create: `.github/workflows/proof.yml`

**Interfaces:**
- Produces: `$S/baseline/` (every artifact of the baseline run), `$S/baseline-facts/` (archive listings and package facts), `$S/facts.sh`, `$S/collect.sh`, `$S/factsdiff.py`, and the run id in `$S/baseline-run-id`. Tasks 12 and 13 read them.

- [ ] **Step 1: Scratch directory and the stale `repo-infra/apply` branch** (decision P13)

```bash
M=/home/oetiker/checkouts/mtuspy
mkdir -p /scratch/oetiker/claude-tmp/claude-1003/project-shape
export S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
git -C $M fetch origin
git -C $M log --oneline -1 repo-infra/apply
git -C $M ls-remote --heads origin repo-infra/apply
git -C $M merge-base --is-ancestor repo-infra/apply origin/main && echo merged
```

Expected on 2026-10-11: both the local and the remote branch at `ffb9b3a`, merged into `main` by pull request #2. **[outward] [ask the owner]** Delete both, so `apply` and the worktree below start a fresh branch:

```bash
M=/home/oetiker/checkouts/mtuspy
git -C $M branch -d repo-infra/apply
git -C $M push origin --delete repo-infra/apply
```

`branch -d` refuses a branch that is not merged. Then the worktree:

```bash
M=/home/oetiker/checkouts/mtuspy
git -C $M worktree add /scratch/oetiker/claude-worktrees/mtuspy-release-pieces -b repo-infra/apply origin/main
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

- [ ] **Step 3: [outward] Commit, push and open a draft pull request**

```bash
S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
cd /scratch/oetiker/claude-worktrees/mtuspy-release-pieces
git add .github/workflows/proof.yml
git commit -m "Run the release build on this branch as 0.0.0 (temporary)

The proof of repo-infra D32: the first run builds with the release build
as it is, the baseline the build through the release pieces is compared
with.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
cat > $S/pr-mtuspy-proof.md <<'EOF'
Builds the release through the release pieces of repo-infra D32, installed by `apply` from repo-infra's unreleased branch `feat/release-pieces`. The `.deb` and `.rpm` packages are built by nfpm from the musl archives instead of by cargo-deb and cargo-generate-rpm.

`proof.yml` builds each push as version 0.0.0 and creates no tag, no release and no release branch. Its first run is the baseline of the unchanged build. It is removed before the merge.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
git push -u origin repo-infra/apply
gh pr create -R oetiker/mtuspy --draft --base main --head repo-infra/apply \
  --title "Release build through the repo-infra release pieces" \
  --body-file $S/pr-mtuspy-proof.md
```

The pull request carries no `no-changelog` label: Task 11 adds the `CHANGES.md` entry, and `changelog-updated` is red until then.

- [ ] **Step 4: Wait for the baseline run**

Wait for the run of the pushed commit, not for the newest run of the branch. A foreground `sleep` is blocked in Claude Code, so run the loop with Monitor or in the background:

```bash
S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
cd /scratch/oetiker/claude-worktrees/mtuspy-release-pieces
sha=$(git rev-parse HEAD)
until id=$(gh run list -R oetiker/mtuspy --workflow proof.yml --commit "$sha" --json databaseId --jq '.[0].databaseId') && [ -n "$id" ]; do sleep 15; done
echo "$id" > $S/baseline-run-id
gh run watch "$id" -R oetiker/mtuspy --exit-status
```

Expected: green, with jobs `build / Build <target>` for seven targets, `build / Bottle on macos-14`, `build / Bottle on macos-15-intel` and `build / Rewrite the formula`. If any job fails, stop and report the job and its log excerpt to the owner: a failing baseline leg is a finding about mtuspy's current build (for example the illumos `crt-static` the spec names), and the owner decides whether the baseline is taken from a run with that one line fixed.

- [ ] **Step 5: Download the baseline**

```bash
S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
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

`$S/factsdiff.py` (Task 13 commits the same function as `tests/nfpm_facts.py`):

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
S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
mkdir -p $S/baseline-facts/archives
for archive in $S/baseline/release-asset-*/*.tar.gz; do
  case $archive in *bottle*) continue ;; esac
  tar -tzf "$archive" | LC_ALL=C sort > "$S/baseline-facts/archives/$(basename "$archive").list"
done
for archive in $S/baseline/release-asset-*/*.zip; do
  python3 -I -c 'import sys, zipfile; print("\n".join(sorted(zipfile.ZipFile(sys.argv[1]).namelist())))' "$archive" \
    > "$S/baseline-facts/archives/$(basename "$archive").list"
done
systemd-run --user --scope -p MemoryMax=2G -- podman run --rm -v $S:/s:Z docker.io/library/ubuntu:24.04 bash -euc '
  apt-get update -qq && apt-get install -y -qq rpm >/dev/null
  sh /s/collect.sh /s/baseline /s/baseline-facts/packages'
mkdir -p $S/baseline-facts/bottles
cp $S/baseline/bottle-json-*/*.bottle.json $S/baseline-facts/bottles/
cp $S/baseline/release-files/Formula/mtuspy.rb $S/baseline-facts/mtuspy.rb
ls -R $S/baseline-facts
```

Expected: one `.list` per archive, the bottles left out (each tar listing holds `mtuspy/`, `mtuspy/mtuspy`, `mtuspy/man/`, `mtuspy/man/mtuspy.1`, `mtuspy/README.md`, `mtuspy/LICENSE`; each zip listing the same without `man/`), `packages/deb-amd64`, `deb-arm64`, `rpm-x86_64`, `rpm-aarch64`, each with `files`, `control` and `postinst`, two bottle json files, and the rewritten formula with non-zero `sha256` lines and a bottle block whose `root_url` ends in `/v0.0.0`.

- [ ] **Step 8: Record edaptor v1.8.0 as the second reference**

```bash
S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
gh release download v1.8.0 -R oposs/edaptor -p '*.deb' -p '*.rpm' -D $S/edaptor
systemd-run --user --scope -p MemoryMax=2G -- podman run --rm -v $S:/s:Z docker.io/library/ubuntu:24.04 bash -euc '
  apt-get update -qq && apt-get install -y -qq rpm >/dev/null
  sh /s/collect.sh /s/edaptor /s/edaptor-facts'
```

Expected: `$S/edaptor-facts/{deb-amd64,deb-arm64,rpm-x86_64,rpm-aarch64}`. Read them next to the mtuspy baseline: they show which control fields and doc files a cargo-deb release that published green carries.

---

### Task 11: Install the pieces in mtuspy

**Files (mtuspy, on `repo-infra/apply`):**
- By `apply`: `.github/workflows/lib/` (workflow-lib v8 to v9), `.github/workflows/changelog.yml` (v5 to v6), `.github/workflows/ri-release-rust-binaries.yml`, `ri-release-nfpm.yml`, `ri-release-homebrew.yml`
- Rewrite: `.github/workflows/release-build.yml`
- Create: `nfpm.yaml`
- Modify: `Cargo.toml` (delete `[package.metadata.deb]` and `[package.metadata.generate-rpm]`), `pkg/rpm/post-install.sh` (one comment line), `CHANGES.md`

**Interfaces:**
- Consumes: the pieces, `tests/fixtures/nfpm/repo/nfpm.yaml` and `tests/fixtures/nfpm/repo/pkg/rpm/post-install.sh` at the head of `feat/release-pieces` (Tasks 5 to 9).
- Produces: the build `proof.yml` runs in Task 12.

- [ ] **Step 1: Install the pieces with `apply` from the repo-infra branch** (decision P11)

```bash
S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
RIB=/scratch/oetiker/claude-worktrees/repo-infra-release-pieces
cd /scratch/oetiker/claude-worktrees/mtuspy-release-pieces
git -C $RIB status --short                          # empty: nothing uncommitted
git -C $RIB log --oneline -1 | tee $S/pieces-commit
for item in workflow-lib changelog ri-release-rust-binaries ri-release-nfpm ri-release-homebrew; do
  PYTHONPATH=$RIB/skills/repo-infra/scripts python3 -m repo_infra apply --item "$item" || break
done
git log --oneline -6
```

Expected: `installed workflow-lib v9` followed by the v9 upgrade note, `installed changelog v6` with its upgrade notes (mtuspy carries v5; v6 fixes the `no-changelog` label handling), `installed ri-release-rust-binaries v1`, `installed ri-release-nfpm v1`, `installed ri-release-homebrew v1`, and five commits `Install <piece> vN from the repo-infra standard` on `repo-infra/apply`. The closing findings concern the callers, which Step 2 rewrites.

- [ ] **Step 2: Rewrite `.github/workflows/release-build.yml`** as a caller

```yaml
name: Release build

# Called by Create release PR on the release branch before the pull request
# exists (D28). The three repo-infra release pieces it calls build the
# archives, the deb and rpm packages from the musl archives, and the bottles
# with the rewritten Formula/mtuspy.rb (D32). Read-only: nothing here writes
# the repository.
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
    uses: ./.github/workflows/ri-release-rust-binaries.yml
    with:
      version: ${{ inputs.version }}
      ref: ${{ inputs.ref }}
      bin: mtuspy

  packages:
    needs: binaries
    uses: ./.github/workflows/ri-release-nfpm.yml
    with:
      version: ${{ inputs.version }}
      ref: ${{ inputs.ref }}
      config: nfpm.yaml
      packagers: '{"deb": {}, "rpm": {}}'
      archives: x86_64-unknown-linux-musl aarch64-unknown-linux-musl

  homebrew:
    needs: binaries
    uses: ./.github/workflows/ri-release-homebrew.yml
    with:
      version: ${{ inputs.version }}
      ref: ${{ inputs.ref }}
      bin: mtuspy
```

The `release-version` echo job of the old file goes; nothing reads it.

- [ ] **Step 3: `nfpm.yaml`**, the config the container test of Task 7 builds with:

```bash
RIB=/scratch/oetiker/claude-worktrees/repo-infra-release-pieces
cd /scratch/oetiker/claude-worktrees/mtuspy-release-pieces
cp $RIB/tests/fixtures/nfpm/repo/nfpm.yaml nfpm.yaml
cmp nfpm.yaml $RIB/tests/fixtures/nfpm/repo/nfpm.yaml
```

- [ ] **Step 4: `Cargo.toml`.** Delete from the line `[package.metadata.deb]` through the closing `]` of the `[package.metadata.generate-rpm]` assets, and the blank line after it, so `[dependencies]` is followed by a blank line and `[profile.release]`.

- [ ] **Step 4b: The rpm script names its builder.** Its first comment says `cargo-generate-rpm writes no %caps`; nfpm builds the rpm from now on. Task 7 made the same change in the fixture, so the two files are equal:

```bash
cd /scratch/oetiker/claude-worktrees/mtuspy-release-pieces
RIB=/scratch/oetiker/claude-worktrees/repo-infra-release-pieces
cp $RIB/tests/fixtures/nfpm/repo/pkg/rpm/post-install.sh pkg/rpm/post-install.sh
git diff --stat pkg/rpm/post-install.sh    # one line changed
```

The accepted package diff of Task 12 shows this line in the rpm postinst.

- [ ] **Step 4c: `CHANGES.md`**, under `## [Unreleased]`, `### Changed`:

```markdown
- The illumos binary links the system C library instead of a static one.
- The `.deb` and `.rpm` packages are built by nfpm from the static Linux release archives, so they carry the same binary and man page as the archives.
```

- [ ] **Step 5: Check locally**

```bash
RIB=/scratch/oetiker/claude-worktrees/repo-infra-release-pieces
cd /scratch/oetiker/claude-worktrees/mtuspy-release-pieces
grep -c $'\u2014' .github/workflows/release-build.yml nfpm.yaml    # 0 for each
PYTHONPATH=$RIB/skills/repo-infra/scripts python3 -m repo_infra check; echo "exit $?"
```

Expected: no em dash; in the `pieces` section `workflow-lib` v9, `changelog` v6 and the three `ri-release-*` v1 read `current`; the `callers` section reports no `problem` for `release-build.yml` and the three pieces it calls. The `administration` rows are what they were on `main`.

- [ ] **Step 6: [outward] Commit and push**

```bash
cd /scratch/oetiker/claude-worktrees/mtuspy-release-pieces
git add .github/workflows/release-build.yml nfpm.yaml Cargo.toml pkg/rpm/post-install.sh CHANGES.md
git commit -m "Build the release through the repo-infra release pieces

release-build.yml calls ri-release-rust-binaries, ri-release-nfpm and
ri-release-homebrew, installed by apply from the unreleased repo-infra
branch that this pull request proves (D32). The man page is built once
on Linux and passed to every leg, so a release no longer ships pages
from two pandoc versions. illumos no longer asks for crt-static, which it
does not have. The packages are built by nfpm from the musl archives
instead of by cargo-deb and cargo-generate-rpm from target/, so
Cargo.toml loses its two package tables to nfpm.yaml, and the comment
of the rpm script no longer names cargo-generate-rpm.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
```

---

### Task 12: The proof run, compared with the baseline

**Interfaces:**
- Consumes: `$S/baseline-facts/` (Task 10).
- Produces: `$S/proof/` (artifacts), `$S/proof-facts/`, `$S/accepted.diff` (the package differences the owner accepted), `$S/fixtures/homebrew/`. Task 13 commits the last two and `$S/baseline-facts/packages`.

- [ ] **Step 1: Wait for the proof run**

As in Task 10 Step 4, wait for the run of the pushed commit:

```bash
S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
cd /scratch/oetiker/claude-worktrees/mtuspy-release-pieces
sha=$(git rev-parse HEAD)
until id=$(gh run list -R oetiker/mtuspy --workflow proof.yml --commit "$sha" --json databaseId --jq '.[0].databaseId') && [ -n "$id" ]; do sleep 15; done
echo "$id" > $S/proof-run-id
gh run watch "$id" -R oetiker/mtuspy --exit-status
```

Expected: green, with jobs `build / binaries / Build the man pages`, seven `build / binaries / Build <target>`, `build / packages / Build the deb and rpm packages`, two `build / homebrew / Bottle on <os>` and `build / homebrew / Rewrite the formula`. A failure goes through "When the proof forces a fix" below.

- [ ] **Step 2: Download and collect**

```bash
S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
gh run download "$(cat $S/proof-run-id)" -R oetiker/mtuspy -D $S/proof
mkdir -p $S/proof-facts/archives
for archive in $S/proof/release-asset-*/*.tar.gz; do
  case $archive in *bottle*) continue ;; esac
  tar -tzf "$archive" | LC_ALL=C sort > "$S/proof-facts/archives/$(basename "$archive").list"
done
for archive in $S/proof/release-asset-*/*.zip; do
  python3 -I -c 'import sys, zipfile; print("\n".join(sorted(zipfile.ZipFile(sys.argv[1]).namelist())))' "$archive" \
    > "$S/proof-facts/archives/$(basename "$archive").list"
done
systemd-run --user --scope -p MemoryMax=2G -- podman run --rm -v $S:/s:Z docker.io/library/ubuntu:24.04 bash -euc '
  apt-get update -qq && apt-get install -y -qq rpm >/dev/null
  sh /s/collect.sh /s/proof/release-asset-packages /s/proof-facts/packages'
```

- [ ] **Step 3: Compare archive names and layout**

```bash
S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
diff <(ls $S/baseline-facts/archives) <(ls $S/proof-facts/archives)
diff -r $S/baseline-facts/archives $S/proof-facts/archives
```

Expected: no output. The seven archive names and their file lists are the same.

- [ ] **Step 4: Compare the packages**

```bash
S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
ls $S/proof/release-asset-packages
python3 -I $S/factsdiff.py $S/baseline-facts/packages $S/proof-facts/packages | tee $S/accepted.diff
```

Expected file names: `mtuspy_0.0.0-1_amd64.deb`, `mtuspy_0.0.0-1_arm64.deb`, `mtuspy-0.0.0-1.x86_64.rpm`, `mtuspy-0.0.0-1.aarch64.rpm` (the baseline's carry 0.1.3, the version cargo-deb took from Cargo.toml). The diff must show the same file paths and modes, the same `Package`, `Architecture`, `Section`, `Priority`, `Maintainer`, `Recommends` and `Description` on deb, the same rpm `Name`, `Arch`, `License`, `Summary` and `Recommends`, and the same postinst text. Read every remaining line of the diff next to `$S/edaptor-facts`, and write one sentence per difference saying why it is right (for example a doc file cargo-deb adds on its own) or fix `nfpm.yaml` in mtuspy and the same lines in `$RIB/tests/fixtures/nfpm/repo/nfpm.yaml`, and push both. **[ask the owner]** Show the owner the diff and the sentences; the accepted diff becomes the fixture of Task 13.

- [ ] **Step 5: Compare the formula and the bottles**

```bash
S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
diff $S/baseline-facts/mtuspy.rb $S/proof/release-files/Formula/mtuspy.rb
ls $S/baseline/release-asset-bottle-*/ $S/proof/release-asset-bottle-*/
```

Expected: the formula differs only in the four archive `sha256` values and the bottle `sha256` values (both builds are separate compilations); the version line, the `root_url` and the bottle tags are the same. The bottle file names are the same.

- [ ] **Step 6: Keep the recorded bottle json for Task 13**

```bash
S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
mkdir -p $S/fixtures/homebrew
cp $S/baseline/bottle-json-macos-14/*.bottle.json $S/baseline/bottle-json-macos-15-intel/*.bottle.json $S/fixtures/homebrew/
jq . $S/fixtures/homebrew/*.bottle.json | head -40
```

Expected: two files, one with the tag `arm64_sonoma`, one with the Intel tag of macOS 15, each with `filename`, `local_filename`, `sha256` and a `cellar` on the bottle or the tag.

#### When the proof forces a fix

A red job or a difference the owner does not accept is fixed in repo-infra, never in mtuspy: mtuspy runs the pieces as published (D30). Nothing that carries the piece's version has been released, so the version stays (v1 for a piece, v9 for workflow-lib) and the superseded bytes leave the record. `check` and `apply` compare a file's bytes, with only the v0.3.1 ` sha256=` stamp removed (`check.unstamped`), against every digest in `generations.json`; `make generations` refuses a version recorded with other text ("v1 is recorded with other text; bump the marker"). So:

1. In `$RIB`, change the piece or the library module and its tests, and keep the marker. If a file under `lib/` changed, copy it to `.github/workflows/lib/` as in Task 6 Step 4.
2. Drop the superseded record of each changed file. The path is relative to `skills/repo-infra/assets`, for example `pieces/ri-release-nfpm/ri-release-nfpm.yml` with `1`, or `pieces/workflow-lib/lib/nfpm.js` with `9`:

   ```bash
   python3 - pieces/workflow-lib/lib/nfpm.js 9 <<'EOF'
   import json, pathlib, sys
   path = pathlib.Path("skills/repo-infra/assets/generations.json")
   record = json.loads(path.read_text(encoding="utf-8"))
   del record[sys.argv[1]][sys.argv[2]]
   if not record[sys.argv[1]]:
       del record[sys.argv[1]]
   path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
   EOF
   ```

   Removing a version a release tag carries does not get through: `make generations` reads the tags, adds the released bytes back and refuses the conflict ("recorded with other text than a release shipped").
3. Run `make generations && make catalogue && make check`, and the container test for a change to nfpm (timeouts 600000). Commit on `feat/release-pieces` with the cause in the message, and **[outward]** push.
4. In the mtuspy worktree, `check` now reads the changed piece as `edited` ("claims v1, the current version, but matches no published version"), and `apply` writes no file that claims the current version. Remove the changed files and install again:

   ```bash
   S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
   RIB=/scratch/oetiker/claude-worktrees/repo-infra-release-pieces
   cd /scratch/oetiker/claude-worktrees/mtuspy-release-pieces
   rm .github/workflows/lib/nfpm.js          # each changed file of the piece
   PYTHONPATH=$RIB/skills/repo-infra/scripts python3 -m repo_infra apply --item workflow-lib
   PYTHONPATH=$RIB/skills/repo-infra/scripts python3 -m repo_infra check | grep -E 'workflow-lib|ri-release-'
   git -C $RIB log --oneline -1 | tee $S/pieces-commit
   ```

   Expected: `installed workflow-lib v9`, a commit `Install workflow-lib v9 from the repo-infra standard`, and the four rows `current`.
5. **[outward]** Push; `proof.yml` runs again. Repeat this task from Step 1.

The fix after the last one is what mtuspy releases: Task 14 Step 1 checks that the installed bytes equal the head of `feat/release-pieces`.

---

### Task 13: The proof's data in the repo-infra tests

**Files (repo-infra, in `$RIB`):**
- Create: `tests/nfpm_facts.py`, `tests/fixtures/nfpm/facts.sh`, `tests/fixtures/nfpm/collect.sh`, `tests/fixtures/nfpm/baseline/{deb-amd64,deb-arm64,rpm-x86_64,rpm-aarch64}/{files,control,postinst}`, `tests/fixtures/nfpm/accepted.diff`, `tests/fixtures/homebrew/*.bottle.json`
- Modify: `tests/test_release_nfpm.py`, `tests/test_release_homebrew.py`

**Interfaces:**
- Consumes: `$S/facts.sh`, `$S/collect.sh`, `$S/factsdiff.py`, `$S/baseline-facts/packages` (Task 10), `$S/accepted.diff`, `$S/fixtures/homebrew/` (Task 12).
- Produces: `nfpm_facts.facts_diff(baseline, actual) -> str`. Nothing under `skills/` changes (decision P12), so mtuspy installs nothing again.

- [ ] **Step 1: Fixtures**

```bash
S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
RIB=/scratch/oetiker/claude-worktrees/repo-infra-release-pieces
cd $RIB
cp $S/facts.sh $S/collect.sh tests/fixtures/nfpm/
cp -r $S/baseline-facts/packages tests/fixtures/nfpm/baseline
cp $S/accepted.diff tests/fixtures/nfpm/accepted.diff
mkdir -p tests/fixtures/homebrew && cp $S/fixtures/homebrew/*.bottle.json tests/fixtures/homebrew/
```

`tests/nfpm_facts.py` holds `facts_diff` exactly as `$S/factsdiff.py` (Task 10, Step 6), without the `__main__` block.

- [ ] **Step 2: The tests**

Append to `tests/test_release_nfpm.py`, and add `from nfpm_facts import facts_diff` to its imports:

```python
@pytest.mark.container
def test_the_packages_match_the_baseline_but_for_the_accepted_differences(
        tmp_path, image, nfpm):
    checkout(tmp_path)
    done = in_container(tmp_path, image, nfpm)
    assert done.returncode == 0, done.stdout + done.stderr
    subprocess.run(["podman", "run", "--rm", "-v", f"{tmp_path}:/w:Z", "-v", f"{FIXTURE}:/f:ro",
                    image, "sh", "/f/collect.sh", "/w/repo/packages", "/w/facts"],
                   check=True, capture_output=True, timeout=600)
    assert facts_diff(FIXTURE / "baseline", tmp_path / "facts") == (
        FIXTURE / "accepted.diff").read_text(encoding="utf-8")
```

Append to `tests/test_release_homebrew.py`, and add `import json` to its imports:

```python
JSONS = sorted((ROOT / "tests/fixtures/homebrew").glob("*.bottle.json"))


def test_the_recorded_bottle_json_has_the_keys_the_library_reads():
    """The json mtuspy's baseline run recorded, against the keys homebrew.js
    reads and homebrew.test.js fakes."""
    assert len(JSONS) == 2
    tags = set()
    for path in JSONS:
        for entry in json.loads(path.read_text(encoding="utf-8")).values():
            bottle = entry["bottle"]
            for tag, data in bottle["tags"].items():
                assert {"filename", "local_filename", "sha256"} <= set(data), tag
                assert data.get("cellar") or bottle.get("cellar"), tag
                tags.add(tag)
    assert "arm64_sonoma" in tags
```

Run: `python3 -m pytest -q --basetemp=.pytest-tmp tests/test_release_nfpm.py tests/test_release_homebrew.py` and `systemd-run --user --scope -p MemoryMax=4G -- python3 -m pytest --basetemp=.pytest-tmp -m container -v tests/test_release_nfpm.py` (timeout 600000).
Expected: PASS. The container test fails when the packages differ from the baseline by anything the owner did not accept in Task 12.

- [ ] **Step 3: Gate, commit, push**

Run: `make check` (timeout 600000). Expected: PASS. Then `git diff --stat "$(cut -d' ' -f1 $S/pieces-commit)" -- skills` prints nothing: no piece byte changed since mtuspy installed them.

```bash
cd /scratch/oetiker/claude-worktrees/repo-infra-release-pieces
git add tests
git commit -m "Compare ri-release-nfpm with mtuspy's cargo-deb packages (D32)

The container test now compares the file list, the control fields and
the postinst of the four packages with those of mtuspy's baseline run,
built by cargo-deb and cargo-generate-rpm; the differences the owner
accepted are the fixture. The bottle json of the same run checks the
keys homebrew.js reads.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
```

(**[outward]**: the push.)

---

### Task 14: Merge, the registry variable, the release, and every channel

- [ ] **Step 1: The bytes mtuspy carries are the head of `feat/release-pieces`** (decision P11)

```bash
S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
RIB=/scratch/oetiker/claude-worktrees/repo-infra-release-pieces
cd /scratch/oetiker/claude-worktrees/mtuspy-release-pieces
git -C $RIB status --short                     # empty
git -C $RIB fetch origin && git -C $RIB status -sb | head -1    # not behind or ahead of origin
PYTHONPATH=$RIB/skills/repo-infra/scripts python3 -m repo_infra check | grep -E 'workflow-lib|ri-release-'
for p in ri-release-rust-binaries ri-release-nfpm ri-release-homebrew; do
  cmp .github/workflows/$p.yml $RIB/skills/repo-infra/assets/pieces/$p/$p.yml
done
diff -r .github/workflows/lib $RIB/skills/repo-infra/assets/pieces/workflow-lib/lib
git -C $RIB log --oneline -1 | tee $S/frozen-commit
```

Expected: the four rows `current`, and `cmp` and `diff` print nothing. From here until Task 15 releases repo-infra, no file under `skills/repo-infra/assets/pieces/` changes on `feat/release-pieces`. A change that cannot wait goes through "When the proof forces a fix" (Task 12) and this step again.

- [ ] **Step 2: [outward] Drop `proof.yml`**

```bash
cd /scratch/oetiker/claude-worktrees/mtuspy-release-pieces
git rm .github/workflows/proof.yml
git commit -m "Drop the temporary proof workflow

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
gh pr ready -R oetiker/mtuspy repo-infra/apply
gh pr checks -R oetiker/mtuspy repo-infra/apply --watch
```

Expected: `ci-passed` and `changelog-updated` green.

- [ ] **Step 3: [outward] [ask the owner] Merge the pull request**

```bash
gh pr merge -R oetiker/mtuspy repo-infra/apply --merge
```

- [ ] **Step 4: [outward] [ask the owner] The registry user as a variable** (decision P10). The owner gives the Gitea user name (it is stored only as a secret today and cannot be read back).

```bash
gh variable set GITEA_PACKAGE_USER -R oetiker/mtuspy --body '<the user name the owner gives>'
gh api repos/oetiker/mtuspy/actions/variables --jq '.variables[].name'
```

Expected: `GITEA_PACKAGE_USER`. Ask the owner separately whether to delete the secret of the same name (`gh secret delete GITEA_PACKAGE_USER -R oetiker/mtuspy`); nothing reads it.

- [ ] **Step 5: [outward] Release mtuspy** (authorised by the owner for this work)

```bash
gh workflow run release-pr.yml -R oetiker/mtuspy --ref main -f release_type=feature
gh run list -R oetiker/mtuspy --workflow release-pr.yml --limit 1
gh run watch <id> -R oetiker/mtuspy --exit-status
gh pr list -R oetiker/mtuspy --head release/v0.2.0
gh release view v0.2.0 -R oetiker/mtuspy --json isDraft,assets --jq '.isDraft, .assets[].name'
```

Expected: version 0.2.0 (`CHANGES.md` has `### New` entries; the latest tag is v0.1.3). The draft carries the seven archives, `mtuspy_0.2.0-1_amd64.deb`, `mtuspy_0.2.0-1_arm64.deb`, `mtuspy-0.2.0-1.x86_64.rpm`, `mtuspy-0.2.0-1.aarch64.rpm`, `mtuspy-0.2.0.arm64_sonoma.bottle.tar.gz` and the Intel bottle when that leg built, plus `release-build.json`; the release pull request changes `CHANGES.md`, `Cargo.toml`, `Cargo.lock` and `Formula/mtuspy.rb`.

- [ ] **Step 6: [outward] [ask the owner] Merge the release pull request**, then watch the publish:

```bash
gh pr merge -R oetiker/mtuspy release/v0.2.0 --merge
gh run list -R oetiker/mtuspy --workflow release-publish.yml --limit 1
gh run watch <id> -R oetiker/mtuspy --exit-status
gh release view v0.2.0 -R oetiker/mtuspy --json isDraft --jq .isDraft
```

Expected: `publish`, `gitea` and `finalize` green; `false`.

- [ ] **Step 7: Install from every channel and run `mtuspy --version`**

GitHub release:

```bash
S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
mkdir -p $S/install/github && cd $S/install/github
gh release download v0.2.0 -R oetiker/mtuspy -p 'mtuspy-0.2.0-x86_64-unknown-linux-musl.tar.gz'
tar -xzf mtuspy-0.2.0-x86_64-unknown-linux-musl.tar.gz && ./mtuspy/mtuspy --version && ls mtuspy/man
```

Expected: `mtuspy 0.2.0 (<build date>)` and `mtuspy.1`.

Gitea apt, the README snippet with `-y` added:

```bash
systemd-run --user --scope -p MemoryMax=2G -- podman run --rm docker.io/library/debian:trixie bash -euxc '
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
  systemd-run --user --scope -p MemoryMax=2G -- podman run --rm "$image" bash -euxc '
    dnf install -y -q sudo
    sudo curl -fsSL -o /etc/yum.repos.d/oposs.repo https://gitea.oetiker.ch/api/packages/oposs/rpm.repo
    sudo dnf install -y mtuspy
    mtuspy --version'
done
```

Homebrew on Linux (the formula installs the musl archive there). Check the image's Homebrew version first and run `brew trust` only on 6 or later; the image name `docker.io/homebrew/brew` is to be confirmed with `podman search homebrew/brew` before use:

```bash
systemd-run --user --scope -p MemoryMax=2G -- podman run --rm docker.io/homebrew/brew:latest bash -euxc '
  brew --version
  brew tap oetiker/mtuspy https://github.com/oetiker/mtuspy
  if [ "$(brew --version | sed -n "1s/^Homebrew \([0-9][0-9]*\).*/\1/p")" -ge 6 ]; then brew trust --formula oetiker/mtuspy/mtuspy; fi
  brew install mtuspy
  mtuspy --version'
```

Homebrew on macOS: **[ask the owner]** to run on a Mac `brew tap oetiker/mtuspy https://github.com/oetiker/mtuspy`, `brew trust --formula oetiker/mtuspy/mtuspy`, `brew install mtuspy`, `mtuspy --version`, and to confirm that brew poured the bottle (`Pouring mtuspy-0.2.0.arm64_sonoma.bottle.tar.gz` on Apple silicon).

mise, isolated from the owner's own configuration:

```bash
S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
export MISE_DATA_DIR=$S/mise/data MISE_CACHE_DIR=$S/mise/cache MISE_STATE_DIR=$S/mise/state \
  MISE_CONFIG_DIR=$S/mise/config MISE_GLOBAL_CONFIG_FILE=$S/mise/config/config.toml
mise use -g github:oetiker/mtuspy
mise exec github:oetiker/mtuspy -- mtuspy --version
```

Expected in every case: `mtuspy 0.2.0 (<build date>)`. A channel that fails is reported to the owner with the command and its output before Task 15: repo-infra releases only pieces that have published to every channel.

---
# Phase D: the repo-infra release and mtuspy's full shape

### Task 15: Merge and release repo-infra

- [ ] **Step 1: The freeze held**

```bash
S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
RIB=/scratch/oetiker/claude-worktrees/repo-infra-release-pieces
git -C $RIB fetch origin
git -C $RIB diff --stat "$(cut -d' ' -f1 $S/frozen-commit)" origin/feat/release-pieces -- skills/repo-infra/assets/pieces
```

Expected: no output. Otherwise mtuspy 0.2.0 carries other bytes than the release would: run "When the proof forces a fix" for each changed file on a new mtuspy branch first, and come back here.

- [ ] **Step 2: [outward] Ready the pull request and merge it** (merging in oposs/repo-infra is standing authority)

```bash
S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
RIB=/scratch/oetiker/claude-worktrees/repo-infra-release-pieces
cd $RIB
gh pr ready feat/release-pieces
gh pr edit feat/release-pieces --body-file $S/pr-pieces.md
gh pr checks feat/release-pieces --watch
gh pr merge feat/release-pieces --merge
```

The body gains the mtuspy run ids of the baseline and the proof, the accepted package differences and the link to mtuspy v0.2.0. Expected: `ci-passed` and `changelog-updated` green, then merged.

- [ ] **Step 3: [outward] [ask the owner] Release repo-infra**: dispatch Create release PR on `oposs/repo-infra` with `feature` (`gh workflow run release-pr.yml -R oposs/repo-infra --ref main -f release_type=feature`), watch it, merge the release pull request after the owner's OK, watch the publish, and record the tag in `$S/repo-infra-tag`. If Phase A was not released alone (Task 4 Step 4), this release carries it too.

---

### Task 16: mtuspy against the released plugin

Run the script from the released repo-infra, not from a working branch:

```bash
S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
M=/home/oetiker/checkouts/mtuspy
git -C /home/oetiker/checkouts/repo-infra fetch --tags origin
git -C /home/oetiker/checkouts/repo-infra worktree add --detach /scratch/oetiker/claude-worktrees/repo-infra-release "$(cat $S/repo-infra-tag)"
RI=/scratch/oetiker/claude-worktrees/repo-infra-release/skills/repo-infra/scripts/repo_infra
git -C $M fetch origin
git -C $M worktree add /scratch/oetiker/claude-worktrees/mtuspy-shape -b project-shape origin/main
cd /scratch/oetiker/claude-worktrees/mtuspy-shape
python3 $RI check; echo "exit $?"
```

Expected: `workflow-lib` v9, `ri-release-rust-binaries`, `ri-release-nfpm` and `ri-release-homebrew` v1 read `current`, and no piece reads `edited` or `outdated`: the released plugin asks mtuspy to change no piece. A piece that reads `edited` means repo-infra released other bytes than mtuspy carries; stop and report it to the owner. The remedy is step 4 of "When the proof forces a fix" with `$RI` in place of the branch, on this branch, before Task 17.

---

### Task 17: Close the shape gaps

**Files (mtuspy):** `demo/mtuspy.toml`, `docs/demo/mtuspy.webp`, `Makefile`, `README.md`, `Formula/mtuspy.rb`, `CHANGES.md`

- [ ] **Step 1: Run the shape review** as `commands/check.md` of the released plugin says, against `references/project-shape.md`, and write the result to `$S/mtuspy-shape.md` (scratch only, not committed). The triggers that apply: every project; has a command line (`src/main.rs` parses arguments with clap); runs in a terminal; is installed by users (a Rust program). Expected gaps, read on 2026-10-10: `demo` (no `demo/`), `install-text` (no mise route; the apt and rpm blocks differ from the canonical snippets), `writing-style` (the review lists them). Expected `met`: `badges`, `man-page`, `native-targets`, `linux-packages`, `homebrew` (after Task 14). **[ask the owner]** Show the review and agree which gaps this run closes and which become `exceptions`.

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

Run: `CARGO_BUILD_JOBS=4 make demo` (timeout 600000). Expected: `docs/demo/mtuspy.webp` exists. **[ask the owner]** to look at the WebP before it is committed.

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

Keep the `version`, `sha256` and bottle lines as Task 14's release wrote them.

- [ ] **Step 6: CHANGES.md** under `## [Unreleased]`:

```markdown
### Changed

- The README opens with a recording of mtuspy finding a path MTU, and its install section lists mise beside apt, dnf and Homebrew.
```

- [ ] **Step 7: [outward] Commit, push, open the pull request**

```bash
S=/scratch/oetiker/claude-tmp/claude-1003/project-shape
cd /scratch/oetiker/claude-worktrees/mtuspy-shape
grep -c $'\u2014' demo/mtuspy.toml Makefile Formula/mtuspy.rb CHANGES.md   # 0 each
git add demo docs/demo Makefile README.md Formula/mtuspy.rb CHANGES.md
git commit -m "Close the project shape: demo, install routes, formula template

The shape review of repo-infra D32 reported no demo, no mise route and
install blocks that differed from the canonical snippets. The formula
installs every man page of the archive into its section, as the template
does.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
cat > $S/pr-mtuspy-shape.md <<'EOF'
Closes the gaps the project shape review of repo-infra D32 reported: a recording of mtuspy at the top of the README, an install section with the canonical apt, dnf, Homebrew and mise snippets, and a formula that follows the repo-infra template and installs every man page.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
git push -u origin project-shape
gh pr create -R oetiker/mtuspy --base main --head project-shape --title "Project shape: demo, install routes, formula template" --body-file $S/pr-mtuspy-shape.md
gh pr checks -R oetiker/mtuspy project-shape --watch
```

Expected: `ci-passed` and `changelog-updated` green.

- [ ] **Step 8: [outward] [ask the owner] Merge.**

---

### Task 18: The second release

- [ ] **Step 1: [outward] Release** (authorised): `gh workflow run release-pr.yml -R oetiker/mtuspy --ref main -f release_type=bugfix`, watch it as in Task 14 Step 5. Expected: version 0.2.1, and the draft carries the same set of assets as 0.2.0 under 0.2.1.
- [ ] **Step 2: [outward] [ask the owner] Merge the release pull request** and watch the publish as in Task 14 Step 6.
- [ ] **Step 3: Repeat Task 14 Step 7** with 0.2.1. Expected: `mtuspy 0.2.1 (<build date>)` from every channel, and on Linux Homebrew the man page under `share/man/man1`, installed by the template's `Dir["man/*.[1-9]"]` line.

---

### Task 19: Record mtuspy as the reference example

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

- [ ] **Step 2: Copy the files** from mtuspy at the tag of Task 18:

```bash
M=/home/oetiker/checkouts/mtuspy
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
- Issues: #57 closes with Phase A, #53 with the repo-infra release of Task 15; #59 stays separate; #56 stays open and gains weight (three more workflow files per Rust program in the Actions list).

---

## Self-review

**Spec coverage.** Why: context only. Decisions: shape with triggers (Task 2), triggers by what users receive (Task 2, "Triggers"), LLM judges and script measures (Tasks 1 and 3: the script checks only the value shape), exceptions (Tasks 1 to 3), amendment of D30 and the `skip` message (Tasks 1, 3), shape review in the command only and apply starting with the script (Task 3), archive as contract (Tasks 5, 6, 8), met by result (Task 2 "Rules" paragraph), proven in a consumer before released (Phase C before Task 15), v1 only what mtuspy runs (Global Constraints, Tasks 5 to 8). The shape, every rule (Task 2, test of ids). Exceptions and pairing (Task 2 "Exceptions", Task 3 check.md step 4). The shape review (Task 3). Install snippets and the release-flow pointer (Tasks 2, 3). Pieces: binaries (Task 5), nfpm with the variable table, shadowing, read-back, Gitea name shapes and the mtuspy mapping (Tasks 6, 7, 11), homebrew with url rewrite, rename, formula rewrite, root_url and outputs (Task 8), formula template with the man install line (Task 2). Proof and conversion steps 1 to 6 (Tasks 5 to 9, 10 to 12, 14, 15 and 16, 17 to 19). Testing section (Tasks 1, 2, 5 to 8, 13). Order of work (Phases A to E). Closes (Phase E). Out of scope: nothing planned for it.

**Placeholder scan.** Values that only exist later are named as outputs of an earlier step: `$S/accepted.diff` and the bottle json (Task 12), `$S/pieces-commit` (Task 11), `$S/frozen-commit` (Task 14), the repo-infra tag (Task 15), the Gitea user name (the owner, Task 14). No step says "add tests" without code.

**Names across tasks.** Pieces `ri-release-rust-binaries`, `ri-release-nfpm`, `ri-release-homebrew` (Tasks 5, 7, 8, 11); library modules `lib/nfpm.js` with `run`, `lib/homebrew.js` with `pointAtArchives`, `renameBottles`, `rewriteFormula` (Tasks 6, 8, called from the pieces in Tasks 7, 8); step names `Build`, `Pack the archive`, `Pack the zip`, `Fetch the man pages`, `Install cross`, `Install nfpm`, `Build and read back the packages`, `Point the formula at the built archives`, `Local tap`, `Rename the bottles`, `Rewrite the formula` (pieces and their tests in Tasks 5, 7, 8); artifacts `man-pages`, `release-asset-<target>`, `release-asset-packages`, `release-asset-bottle-<os>`, `bottle-json-<os>`, `release-files`; `facts_diff` in `$S/factsdiff.py` and `tests/nfpm_facts.py`; branches `feat/release-pieces` (repo-infra, `$RIB`), `repo-infra/apply` and `project-shape` (mtuspy).

**Review Focus.** 1: `a mac sha256 line without its url line directly above fails` (Task 8, `homebrew.test.js`). 2: the `packagers ... fails with one line naming the input` cases (Task 6, `nfpm.test.js`), `test_the_build_step_runs_the_library_and_fails_with_its_message` and `test_a_bad_packagers_input_prints_one_error_line` (Task 7). 3: `a missing archive fails naming its artifact`, `two archives in one artifact fail`, `an archive without one top folder fails` (Task 6). 4: `the previous release block is replaced whole` (Task 8). 5: `test_exceptions_that_are_not_an_object_of_reasons_are_a_problem` with `"   "` (Task 1). 6: Task 14 Step 1 and Task 16.

**Facts not verified read-only, each settled by a named step.** The exact cargo-deb and cargo-generate-rpm facts of mtuspy (Task 10, the baseline run); the rpm half of the packaging and nfpm's rpm translation of amd64 and arm64 (Task 7 Step 5, Task 12); the shape of `brew bottle --json` (Task 12 Step 6, Task 13); whether `macos-15-intel` still schedules (Task 10 Step 4); the Homebrew major version on the runners (the guard handles 5 and 6); `actions/github-script@v9` on the macOS bottle runners (Task 12 Step 1); the Gitea user name (the owner, Task 14); the name of the Homebrew container image (Task 14 Step 7); the ICMP permission for the demo recording (Task 17 Step 2).
