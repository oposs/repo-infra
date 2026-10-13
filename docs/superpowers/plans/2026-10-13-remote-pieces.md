# Remote pieces (D33) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consumers call repo-infra's `ri-*.yml` pieces remotely at `@v2` instead of carrying byte copies of them and of the workflow library; repo-infra 2.0.0 ships only that layout, gated by a build of mtuspy with the release's own pieces, and mtuspy is the first repository migrated to it.

**Architecture:** Every piece lives once in `.github/workflows/ri-<name>.yml` and loads the library from the commit it was itself loaded from (`job.workflow_repository`, `job.workflow_sha`). The two required checks stay inline in the consumer's callers and read the verdicts of two new pieces (`ri-release-verdict`, `ri-changelog`); `release-pr` splits into `ri-release-prepare` and `ri-release-finish` with the consumer's own build and CI between them. `check` reviews the remote calls against the interfaces of the installed plugin and reports the v1 layout; `apply` migrates a v1 repository in one pull request. A gate workflow builds mtuspy before `v2` moves, and a test refuses any interface change `v2` consumers would notice.

**Tech Stack:** Python 3.11 standard library (scripts), pytest + PyYAML (tests), Node.js with `node --test` (workflow library), GitHub Actions reusable workflows with `actions/github-script@v9`, `actions/create-github-app-token`, `gh` CLI for the owner steps.

**Spec:** `docs/superpowers/specs/2026-10-13-remote-pieces-design.md` (D33). Read it before Task 2. It builds on `2026-10-02-pieces-and-callers-design.md` (D30), `2026-10-01-one-release-flow-design.md` (D28), `2026-10-07-release-pr-skips-ci-design.md` (D31) and `2026-10-10-project-shape-design.md` (D32).

## Global Constraints

- No em dash (U+2014) in any shipped file (`tests/test_no_em_dash.py` scans `skills/`, `commands/`, `.claude-plugin/`, `.github/`, `README.md`, `RELEASING.md` and `CHANGES.md`), in this plan, in commit messages or in pull request text. Write "for example", never `e.g.`.
- No internal hostnames, IP addresses or bot logins in any file, commit message or pull request text. The repository is public. `github-actions[bot]` is GitHub's public login and stays where it already is.
- `CHANGES.md` uses `### New`, never `### Added`; the release workflow matches on `### New`. Entries follow the `repo-infra:writing-style` skill (load it before writing any entry, comment or commit message): lead with what the reader observes, at most three sentences, names the reader can act on, no release headers.
- Release-piece logic is JavaScript in the workflow library (`.github/workflows/lib/<name>.js` with `<name>.test.js`), called from `actions/github-script@v9`. Never Python in a piece. A step that only calls a tool stays shell.
- Inputs reach a step through `env:`, never as `${{ }}` inside `run:` or `script:` (P1 of the D32 plan).
- Never remove `if: always()` from `ci-passed`. The required checks are exactly `ci-passed` and `changelog-updated`; never rename either job id.
- Required workflows (`ci.yml`, `changelog.yml`) carry no `paths:` or `paths-ignore:` filter (D13).
- Feature pull requests squash. Release pull requests merge with a merge commit.
- Builds and tests use at most 4 cores: no `pytest -n` above 4, `make check` runs serially. Pass `timeout: 600000` to every long Bash call and never end a turn while a background shell runs.
- Temporary data goes to `/scratch/oetiker/claude-tmp/claude-1003/plan-d33/` (called `$S` below), never `/tmp`. Each Bash call starts with fresh shell state: every block sets the variables it uses.
- Never run `git grep` over the whole tree. Use `grep -rn` on the named directories.
- `make check` (ruff, pytest, node library tests) is green at the end of every repo-infra task, and every task leaves CI on the branch green: `ci-passed` and `changelog-updated` pass on a push of any task's commit. Each task therefore adds its own `CHANGES.md` entry under `## [Unreleased]`.
- Action majors in every piece match the manifest `actions` map (`actions/checkout@v7`, `actions/setup-node@v7`, `actions/github-script@v9`, `actions/download-artifact@v8`, `actions/upload-artifact@v7`).
- Every commit ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Pull request bodies end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- Outward-facing steps are marked **[outward]**. Merging pull requests in oposs/repo-infra is standing authority from the owner (the auto-mode classifier may still ask). Steps marked **[owner]** are done by the owner, or by the controller with the owner present; an engineer subagent never runs them.

## Decisions this plan takes where the spec is silent

- **P1. A remote piece's marker carries the major tag.** Every file in `.github/workflows/ri-*.yml` that the manifest lists starts with `# repo-infra: <name> v2`. Pieces stop having versions of their own: within `v2` the interface rules of the spec apply, and `v3` bumps every marker. `load_pieces` refuses a remote piece whose marker is not `v2`. The per-piece `CHANGES.md` upgrade notes of remote pieces are deleted; `CHANGES.md` at the root says what changed.
- **P2. The manifest entry of a remote piece** is `{"kind": "remote", "group": ..., "core": ...}` without `target`. Its file is `<plugin root>/.github/workflows/<name>.yml`, where the plugin root is `assets.parents[2]` (`skills/repo-infra/assets` lies three levels below it). A consumer calls it as `oposs/repo-infra/.github/workflows/<name>.yml@v2` (`pieces.HOME_REPO`, `pieces.MAJOR`).
- **P3. The home repository** is the one whose checkout contains `skills/repo-infra/assets/manifest.json` (`check.is_home(root)`). There the pieces are local files called through `./`, `.github/workflows/lib/` is the library, and the v1-layout findings do not apply. Everywhere else they do.
- **P4. Fragments keep the byte model; the `dir` kind stays in the code.** Nothing ships a directory piece after Task 5, but `load_pieces`, `check` and `apply` keep handling one, so the tests of that mechanism stay and no code is deleted for its own sake.
- **P5. Retired pieces.** `changelog`, `release-pr`, `workflow-lib` and `ri-ci-lib` leave the manifest. `check` reports a consumer file that still carries one of them (`.github/workflows/changelog.yml` or `release-pr.yml` with its marker, `.github/workflows/lib/`, `.github/workflows/ri-ci-lib.yml`) as the v1 layout, not as an unknown marker. repo-infra keeps `ri-ci-lib.yml` for itself, without a marker.
- **P6. `ri-release-verdict` has a third output, `message`,** so the inline `ci-passed` can print why a release pull request fails. `ri-changelog` fails its own job on a refused changelog and also sets `message`.
- **P7. `assets/callers/ci-passed.yml` holds two jobs,** `release-verdict` and `ci-passed`, in the consumer form (`@v2`). `assets/callers/changelog.yml` and `assets/callers/release-pr.yml` hold whole files. `check` compares jobs with the `uses:` of a repo-infra piece normalised (`./.github/workflows/<f>` and `oposs/repo-infra/.github/workflows/<f>@v2` compare equal), so repo-infra's own `./` callers match the patterns too.
- **P8. `ri-release-prepare` keeps everything today's `prepare` job does,** the guard and the refusals and clean-up included, and takes the release type as the input `release_type`.
- **P9. Other repositories' reusable workflows are not reviewed.** D30's finding "a workflow in another repository; copy the piece" goes. A call to `oposs/repo-infra/.github/workflows/<f>@<ref>` is reviewed: `<f>` must be a piece and `<ref>` must be `v2`.
- **P10. The gate's equality test also ignores `version`, `if:` and the `source` entry of `needs:`.** The gate reads `version` from `source.json` like `repository` and `ref`, every gate job needs the job `source` that reads it, and the example's CI jobs carry the D31 skip that a `workflow_dispatch` run does not need.
- **P11. The compatibility test runs in an inline job `v2-compat` of repo-infra's `ci.yml`,** which checks out with `fetch-depth: 0` so the tag `v2` is present. The ordinary pytest job has a shallow clone and skips the test; `v2-compat` sets `RI_V2_COMPAT=required`, which turns "no tag `v2`" into a failure once `CHANGES.md` records a 2.x release.
- **P12. The `repository` input goes on the pieces of the `ci` and `release-build` groups,** the ones that take `ref`. Publish pieces check out the default branch of the calling repository and take neither.

## Review Focus

1. The inline `ci-passed` must fail when the verdict job was skipped, failed or was cancelled, and in release mode when `ok` is not `true`; it must never pass because a needed job did not report. Test in Task 4 (`test_ci_passed_step_table`, the step's bash run with every combination).
2. `changelog-updated` must be red, not skipped-green, when the `changelog` job fails, and skipped only by the `no-changelog` label on a non-release branch. Test in Task 4 (`test_changelog_updated_step` and the `if:` assertion).
3. A consumer `uses:` naming a repo-infra piece at any ref other than exactly `v2` (`@main`, `@v2.0.0`, `@V2`, no ref) must be a `check` problem, and so must a remote call with `secrets: inherit`. Tests in Task 9.
4. `apply`'s migration of a `ci.yml` whose `ci-passed` is not the last job, which carries comments between jobs, or which has a job of its own between pieces, must replace only `ci-passed`, insert `release-verdict` once, and keep every other line. Test in Task 10.
5. The release gate must fail with one message, not hang, when the dispatch response carries no run id or the run does not finish within its timeout. Tests in Task 12 (`gate.test.js`).
6. A piece job that checks out the library before the source would lose `.repo-infra` to the source checkout's clean. Test in Task 3 (`test_the_library_checkout_follows_every_source_checkout`).

---

## File structure

repo-infra:

| File | Change | Responsibility |
|---|---|---|
| `.github/workflows/ri-*.yml` | move in from `skills/repo-infra/assets/pieces/ri-*/` (Task 2), change (Tasks 3 to 8) | every piece, once |
| `.github/workflows/ri-release-verdict.yml`, `ri-changelog.yml` | create (Task 4) | the two judges |
| `.github/workflows/ri-release-prepare.yml`, `ri-release-finish.yml` | create (Task 5) | release-pr split |
| `.github/workflows/lib/` | change (Tasks 4, 5, 8, 12) | the only copy of the library |
| `.github/workflows/lib/gate.js`, `gate.test.js` | create (Task 12) | dispatch the gate and wait |
| `.github/workflows/gate-mtuspy.yml` | create (Task 11) | the release gate |
| `.github/workflows/ci.yml`, `changelog.yml`, `release-pr.yml`, `release-publish.yml` | rewrite as callers (Tasks 4, 5, 8, 12, 13) | repo-infra's own callers, all through `./` |
| `skills/repo-infra/assets/pieces/` | shrink to fragments (Tasks 2, 4, 5) | `man`, `man-lua`, `container`, `container-m4`, `dependabot` |
| `skills/repo-infra/assets/callers/ci-passed.yml`, `changelog.yml`, `release-pr.yml` | rewrite, create (Tasks 4, 5) | the inline jobs and the two whole callers |
| `skills/repo-infra/assets/manifest.json`, `generations.json` | change (Tasks 2, 4, 5, 8) | remote entries, fragment history |
| `skills/repo-infra/scripts/repo_infra/pieces.py` | change (Task 2) | remote kind, plugin root |
| `skills/repo-infra/scripts/repo_infra/check.py` | change (Tasks 2, 9) | home, v1 layout, core calls |
| `skills/repo-infra/scripts/repo_infra/callers.py` | change (Tasks 4, 5, 6, 9) | remote calls, inline jobs, structure of release-pr |
| `skills/repo-infra/scripts/repo_infra/migrate.py` | create (Task 10) | text rewrites of the v1 to v2 migration |
| `skills/repo-infra/scripts/repo_infra/apply.py`, `cli.py` | change (Task 10) | never write pieces, migrate |
| `skills/repo-infra/scripts/repo_infra/catalogue.py`, `references/catalogue.md` | change (Task 2) | remote entries |
| `skills/repo-infra/references/examples/mtuspy/` | change (Task 11, 20) | v2 callers and `source.json` |
| `tests/piecekit.py` | change (Task 2) | fake plugin with remote pieces |
| `tests/generations.py` | change (Task 2) | skip remote pieces |
| `tests/v2compat.py`, `tests/test_v2_compat.py` | create (Task 13) | interface comparison with `v2` |
| `tests/test_gate.py` | create (Task 11) | gate equals the example |
| `RELEASING.md`, `skills/repo-infra/SKILL.md`, `references/*.md`, `commands/*.md`, `README.md` | change (Tasks 8, 14) | rollback, the remote model |
| `CHANGES.md` | every task | user-facing entries |

Work location: the worktree `/scratch/oetiker/claude-worktrees/repo-infra-release-pieces` (called `$RI` below). Tasks 2 to 14 commit on a new branch `feat/remote-pieces` cut from `spec/v2-remote-pieces`:

```bash
RI=/scratch/oetiker/claude-worktrees/repo-infra-release-pieces
git -C $RI switch -c feat/remote-pieces
mkdir -p /scratch/oetiker/claude-tmp/claude-1003/plan-d33
```

Every repo-infra test command runs from `$RI` with `PYTHONPATH` set by `pytest.ini`/`pyproject.toml` as today (`python3 -m pytest -q --basetemp=.pytest-tmp ...`).

---

# Phase A: the probe

### Task 1: [owner] [controller] Probe `./`, `$/`, `job.workflow_*`, `vars` and the dispatch response across repositories

Not an engineer task. GitHub does not document how `./` resolves inside a workflow called from another repository. This task also confirms the facts the design rests on, so a false one stops the work here instead of on the release.

**What to create** (ask the owner before each **[outward]** step):

1. **[outward] [owner]** A public repository `oetiker/ri-probe` (personal account, so the call crosses organisations exactly as mtuspy's does), with a repository variable `PROBE_VAR=consumer` and a repository secret `PROBE_SECRET=consumer-secret`.
2. **[outward]** In oposs/repo-infra a branch `probe/remote-call` from `main` with three files, pushed but never merged:

`.github/workflows/ri-probe-outer.yml`:

```yaml
name: Probe outer
on:
  workflow_call:
    secrets:
      probe-secret:
        required: false
permissions:
  contents: read
jobs:
  facts:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - env:
          WREPO: ${{ job.workflow_repository }}
          WSHA: ${{ job.workflow_sha }}
          GREPO: ${{ github.repository }}
          VAR: ${{ vars.PROBE_VAR }}
          HAS_SECRET: ${{ secrets.probe-secret != '' }}
        run: |
          echo "job.workflow_repository=$WREPO"
          echo "job.workflow_sha=$WSHA"
          echo "github.repository=$GREPO"
          echo "vars.PROBE_VAR=$VAR"
          echo "secret passed by name=$HAS_SECRET"
      - uses: actions/checkout@v7
        with:
          repository: ${{ job.workflow_repository }}
          ref: ${{ job.workflow_sha }}
          path: .repo-infra
          sparse-checkout: .github/workflows/lib
      - run: ls .repo-infra/.github/workflows/lib/release.js
  dot:
    uses: ./.github/workflows/ri-probe-inner.yml
  dollar:
    uses: $/.github/workflows/ri-probe-inner.yml
```

`.github/workflows/ri-probe-inner.yml`:

```yaml
name: Probe inner
on:
  workflow_call:
permissions:
  contents: read
jobs:
  where:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - run: echo "inner=repo-infra"
```

`.github/workflows/probe-dispatch.yml` (for the dispatch response):

```yaml
name: Probe dispatch
on:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  noop:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - run: echo dispatched
```

3. **[outward]** In `oetiker/ri-probe`, `.github/workflows/ri-probe-inner.yml` printing `inner=consumer` (same text as above with `consumer`), and `.github/workflows/probe.yml`:

```yaml
name: Probe
on:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  remote:
    uses: oposs/repo-infra/.github/workflows/ri-probe-outer.yml@probe/remote-call
    secrets:
      probe-secret: ${{ secrets.PROBE_SECRET }}
  inherit:
    uses: oposs/repo-infra/.github/workflows/ri-probe-outer.yml@probe/remote-call
    secrets: inherit
```

4. Run `gh workflow run probe.yml --repo oetiker/ri-probe` and read the logs (`gh run view --log`). Then, from the controller's shell, ask the dispatch API for run details:

```bash
gh api -X POST repos/oposs/repo-infra/actions/workflows/probe-dispatch.yml/dispatches \
  -f ref=probe/remote-call -F return_run_details=true
```

The workflow must exist on the default branch for that call, so expect a 404 here unless the owner agrees to merge `probe-dispatch.yml` to main for one run; if the 404 comes, ask the owner, or record the field name from GitHub's REST documentation for "Create a workflow dispatch event" instead.

**Record in `$S/probe.md`** (and in the controller's notes for later tasks):

| Question | Result that decides |
|---|---|
| `job.workflow_repository`, `job.workflow_sha` | Must print `oposs/repo-infra` and the head of `probe/remote-call`, and the sparse checkout must list `release.js`. **Anything else stops the plan**: the library cannot be loaded as Task 3 writes it. Report to the owner as a spec defect. |
| `dot` job | Prints `inner=repo-infra`: `./` resolves to the called workflow's repository. `inner=consumer`: it resolves to the caller's. Refused: `./` is not allowed in a called workflow. |
| `dollar` job | Runs and prints `inner=repo-infra`: `$/` is available for piece-to-piece calls. Refused or anything else: no piece calls another piece. |
| `inherit` job | Expected to be refused (different organisations). If it runs, note it; the plan still passes secrets by name. |
| `vars.PROBE_VAR` | Expected `consumer`. If empty, `ri-publish-gitea` cannot read `GITEA_PACKAGE_USER` remotely; Task 9's interface needs a `gitea-package-user` input, and the owner decides before Task 9. |
| dispatch response | The JSON field that holds the run id (expected `workflow_run_id`). Task 12's `gate.js` reads that field name. |

**Which tasks depend on it:**

- Task 3 (library loading) and everything after it need `job.workflow_*` to work as the spec says.
- Task 2 Step 6 writes the invariant test `test_no_piece_calls_through_dot_slash`: it holds whatever the `dot` result is, because no piece needs `./` once Task 6 removes `action-test.yml` from `ri-ci-github-action`. If `dot` printed `inner=repo-infra` and `dollar` worked, nothing changes either: the test documents that pieces do not call pieces.
- Task 12 reads the dispatch field name.
- Task 9 reads the `vars` result.

5. **[outward] [owner]** Afterwards delete the branch `probe/remote-call` and the repository `oetiker/ri-probe` (destructive: the owner confirms each).

---

# Phase B: repo-infra 2.0.0 on one branch

Every task below ends with `make check` green, a `CHANGES.md` entry, and one commit on `feat/remote-pieces`. Nothing is pushed before Task 15.

### Task 2: Pieces live once in `.github/workflows/`

The store reads remote pieces from the plugin root; the copies under `assets/pieces/ri-*` go. The library, `changelog` and `release-pr` stay byte pieces until Tasks 4 and 5.

**Files:**
- Move: `skills/repo-infra/assets/pieces/ri-<name>/ri-<name>.yml` to `.github/workflows/ri-<name>.yml`, for every `ri-*` piece except `ri-ci-lib`. Delete `skills/repo-infra/assets/pieces/ri-<name>/CHANGES.md` and the emptied folders. Delete `skills/repo-infra/assets/pieces/ri-ci-lib/`.
- Modify: `.github/workflows/ri-ci-lib.yml` (marker block out), `skills/repo-infra/assets/manifest.json`, `skills/repo-infra/assets/generations.json` (by `make generations`), `skills/repo-infra/scripts/repo_infra/pieces.py`, `check.py`, `catalogue.py`, `skills/repo-infra/references/catalogue.md` (by `make catalogue`), `tests/generations.py`, `tests/piecekit.py`
- Test: `tests/test_piece_model.py`, `tests/test_pieces.py`, `tests/test_catalogue.py`, `tests/test_check.py`, and the path fixes listed in Step 7

**Interfaces:**
- Produces: `pieces.HOME_REPO = "oposs/repo-infra"`, `pieces.MAJOR = "v2"`, `pieces.plugin_root(assets) -> pathlib.Path`, `pieces.source_path(name, spec, assets) -> pathlib.Path`; `Piece.kind == "remote"` for remote pieces, with `target == ".github/workflows/<name>.yml"`, `files == {target: text}`, `version == 2`; properties `Piece.remote -> bool`, `Piece.uses -> str` (`"oposs/repo-infra/.github/workflows/<name>.yml@v2"`), `Piece.workflow` true for file pieces under `.github/workflows/` and for remote pieces. `check.is_home(repo_root) -> bool`. `piecekit.make_assets(root, current, history=(), core=(), remote=None)` builds a fake plugin at `root` and returns `root / "skills/repo-infra/assets"`; `remote` maps a piece name to its text, written to `root/.github/workflows/<name>.yml`.

- [ ] **Step 1: Write the failing tests for the store** (append to `tests/test_piece_model.py`)

```python
def test_a_remote_piece_is_read_from_the_plugin_roots_workflows(tmp_path):
    text = workflow_piece("ri-r", 2)
    assets = make_assets(tmp_path, {}, remote={"ri-r": text})
    piece = pieces.load_pieces(assets)["ri-r"]
    assert piece.kind == "remote" and piece.remote and piece.workflow
    assert piece.target == ".github/workflows/ri-r.yml"
    assert piece.files == {".github/workflows/ri-r.yml": text}
    assert piece.version == 2
    assert piece.uses == "oposs/repo-infra/.github/workflows/ri-r.yml@v2"


def test_a_remote_piece_must_carry_the_major_tag(tmp_path):
    assets = make_assets(tmp_path, {}, remote={"ri-r": workflow_piece("ri-r", 1)})
    with pytest.raises(pieces.PieceError,
                       match=r"\.github/workflows/ri-r\.yml: a remote piece is v2"):
        pieces.load_pieces(assets)


def test_a_missing_remote_piece_names_its_path(tmp_path):
    assets = make_assets(tmp_path, {}, remote={"ri-r": workflow_piece("ri-r", 2)})
    (tmp_path / ".github/workflows/ri-r.yml").unlink()
    with pytest.raises(pieces.PieceError,
                       match=r"ri-r: \.github/workflows/ri-r\.yml is missing from the plugin"):
        pieces.load_pieces(assets)


def test_remote_pieces_have_no_published_bytes(tmp_path):
    assets = make_assets(tmp_path, {}, remote={"ri-r": workflow_piece("ri-r", 2)})
    assert pieces.load_published(assets) == {"ri-r": {}}
```

and to `tests/test_pieces.py`, replacing `test_changes_has_a_section_for_the_current_version` and `test_the_call_snippet_calls_this_piece_correctly`:

```python
BYTE = [p for p in ALL if not p.remote]
REMOTE = [p for p in ALL if p.remote]


@pytest.mark.parametrize("piece", BYTE, ids=ids)
def test_changes_has_a_section_for_the_current_version(piece):
    text = (ASSETS / "pieces" / piece.name / "CHANGES.md").read_text(encoding="utf-8")
    versions = [int(v) for v in re.findall(r"^## v(\d+)\s*$", text, re.MULTILINE)]
    assert piece.version in versions
    assert max(versions) == piece.version


@pytest.mark.parametrize("piece", REMOTE, ids=ids)
def test_a_remote_piece_has_no_copy_and_no_upgrade_notes(piece):
    assert not (ASSETS / "pieces" / piece.name).exists()


@pytest.mark.parametrize("piece", CALLED, ids=ids)
def test_the_call_snippet_calls_this_piece_correctly(piece):
    snippet = workflow.load(piece.header["Call"])
    assert len(snippet) == 1, "Call: holds exactly one job"
    (job_id, job), = snippet.items()
    assert job["uses"] == piece.uses
    file = pathlib.PurePosixPath(piece.target).name
    local = dict(job, uses=f"./.github/workflows/{file}")
    assert callers.call_problems(job_id, local, {file: doc_of(piece)}) == []


def test_every_ri_workflow_of_repo_infra_is_a_piece_or_home_only():
    root = ASSETS.parents[2]
    files = {p.name for p in (root / ".github/workflows").glob("ri-*.yml")}
    assert files == {f"{p.name}.yml" for p in REMOTE} | {"ri-ci-lib.yml"}


@pytest.mark.parametrize("piece", REMOTE, ids=ids)
def test_no_piece_calls_through_dot_slash(piece):
    """Task 1's probe: a piece never calls a workflow through ./ or $/."""
    for job_id, job in doc_of(piece)["jobs"].items():
        uses = str(job.get("uses", ""))
        assert not uses.startswith(("./", "$/")), f"{piece.name}: job {job_id}"
```

`CALLED` stays `[p for p in WORKFLOW_PIECES if p.group != "release"]`; `changelog` and `release-pr` are byte pieces with group `release` until Tasks 4 and 5.

- [ ] **Step 2: Run them to see them fail**

Run: `python3 -m pytest -q --basetemp=.pytest-tmp tests/test_piece_model.py tests/test_pieces.py`
Expected: FAIL with `TypeError: make_assets() got an unexpected keyword argument 'remote'` and missing `Piece.remote`.

- [ ] **Step 3: `pieces.py`**

Add below `ASSETS`:

```python
# D33: consumers call the pieces of this repository remotely, at the moving
# major tag. The pieces lie in .github/workflows/ of the plugin root, the
# only directory GitHub runs a reusable workflow from.
HOME_REPO = "oposs/repo-infra"
MAJOR = "v2"


def plugin_root(assets):
    """The repository root of the plugin: assets is skills/repo-infra/assets."""
    return pathlib.Path(assets).resolve().parents[2]
```

Extend `Piece`:

```python
    @property
    def remote(self):
        return self.kind == "remote"

    @property
    def workflow(self):
        return self.remote or (self.kind == "file"
                               and self.target.startswith(".github/workflows/"))

    @property
    def uses(self):
        """How a consumer calls a remote piece (D33)."""
        return f"{HOME_REPO}/{self.target}@{MAJOR}"
```

Replace `_source` and the file-reading part of `load_pieces`:

```python
def _source(name, spec):
    return f"pieces/{name}/{pathlib.PurePosixPath(spec['target']).name}"


def _remote_target(name):
    return f".github/workflows/{name}.yml"


def source_path(name, spec, assets):
    """Where the store keeps the piece: under assets, or for a remote piece
    in .github/workflows/ of the plugin root."""
    if spec.get("kind") == "remote":
        return plugin_root(assets) / _remote_target(name)
    return pathlib.Path(assets) / _source(name, spec)


def load_pieces(assets=ASSETS):
    assets = pathlib.Path(assets)
    found = {}
    for name, spec in _manifest(assets).get("pieces", {}).items():
        kind = spec.get("kind", "file")
        if kind == "remote":
            target = _remote_target(name)
            source = source_path(name, spec, assets)
            if not source.is_file():
                raise PieceError(f"{name}: {target} is missing from the plugin")
            text = source.read_text(encoding="utf-8")
            markers = parse_markers(text)
            if not markers or markers[0].asset != name:
                raise PieceError(f"{target}: the first marker must be `repo-infra: {name} "
                                 f"{MAJOR}`")
            if f"v{markers[0].version}" != MAJOR:
                raise PieceError(f"{target}: a remote piece is {MAJOR}, the major tag "
                                 f"consumers call; it says v{markers[0].version}")
            try:
                header = parse_header(text, "#")
            except PieceError as error:
                raise PieceError(f"{target}: {error}") from error
            found[name] = Piece(name, markers[0].version, target, kind,
                                spec.get("group", ""), bool(spec.get("core")),
                                {target: text}, header)
            continue
        # ... the existing file and dir branch, unchanged from `for key in ...` on
```

In `load_published`, skip remote pieces: `if spec.get("kind") == "remote": published[name] = {}; continue` as the first line of the loop.

- [ ] **Step 4: `tests/piecekit.py`**

Change `make_assets` so it builds a plugin root and returns its assets folder:

```python
def make_assets(root, current, history=(), core=(), remote=None):
    """A fake plugin under `root`: the store at skills/repo-infra/assets, which
    is returned, and the remote pieces in `remote` ({name: text}) at
    .github/workflows/<name>.yml, where load_pieces looks for them (D33).

    `current` maps a byte piece's name to its text (a file piece, installed at
    .github/workflows/<name>.yml) or to {file name: text} (a directory piece,
    installed at .github/workflows/<name>/). `history` lists
    (name, file name or None, text) published before the current ones."""
    plugin = pathlib.Path(root)
    root = plugin / "skills/repo-infra/assets"
    root.mkdir(parents=True)
    ...  # the existing body, unchanged, writing below `root`
    for name, text in (remote or {}).items():
        install(plugin, f".github/workflows/{name}.yml", text)
        spec = {"kind": "remote", "group": "ci"}
        if name in core:
            spec["core"] = True
        manifest["pieces"][name] = spec
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    ...
    return root
```

(Move the `manifest.json` write after the remote loop; `install` is defined below `make_assets` in the same module, which Python resolves at call time.)

Tests that pass a path and then use `tmp_path` for the repository keep working: `make_assets(tmp_path / "assets", ...)` makes the plugin at `tmp_path/assets`. A test that writes below the returned store by a path relative to `tmp_path` (not the return value) must use the return value instead; Step 7 lists them.

- [ ] **Step 5: Move the pieces**

```bash
RI=/scratch/oetiker/claude-worktrees/repo-infra-release-pieces
cd $RI
P=skills/repo-infra/assets/pieces
for d in $P/ri-*/; do
  n=$(basename "$d")
  [ "$n" = ri-ci-lib ] && continue
  git mv -f "$d/$n.yml" ".github/workflows/$n.yml"
  git rm -q "$d/CHANGES.md"
done
git rm -rq $P/ri-ci-lib
ls $P    # changelog container container-m4 dependabot man man-lua release-pr workflow-lib
```

The seven pieces repo-infra installed (`ri-ci-claude-plugin`, `ri-ci-python`, `ri-ci-repo-infra-selftest`, `ri-publish-finalize`, `ri-publish-tag`, `ri-release-pr-current` and their old copies) were byte-equal to the store (`test_self_check`), so `git mv -f` loses nothing; `git diff --stat HEAD -- .github/workflows` shows only the new files.

Set every moved marker to `v2` and every `Call:` snippet to the remote form:

```bash
cd /scratch/oetiker/claude-worktrees/repo-infra-release-pieces
for f in .github/workflows/ri-*.yml; do
  n=$(basename "$f" .yml)
  [ "$n" = ri-ci-lib ] && continue
  sed -i "1s|^# repo-infra: $n v[0-9]*\$|# repo-infra: $n v2|" "$f"
  sed -i "s|^#     uses: ./.github/workflows/$n.yml\$|#     uses: oposs/repo-infra/.github/workflows/$n.yml@v2|" "$f"
  head -1 "$f"
done
```

In `.github/workflows/ri-ci-lib.yml`, replace the header block (the marker line down to the blank line before `name:`) with:

```yaml
# The tests of the workflow library, run by repo-infra's own ci.yml. Not a
# piece since D33: consumers load the library from repo-infra's commit and
# carry no copy to test.
```

`ri-ci-repo-infra-selftest` stays a piece (its `Choose:` already says "Only in repo-infra itself").

- [ ] **Step 6: `manifest.json`**

Every moved piece becomes `{"kind": "remote", "group": <its group>}` plus `"core": true` where it had it; `ri-ci-lib` is deleted from `pieces`. For example:

```json
    "ri-release-pr-current": {
      "kind": "remote",
      "group": "ci",
      "core": true
    },
```

- [ ] **Step 7: Path fixes in the tests**

These read a piece from its old store path. Replace `ASSETS / "pieces/ri-<n>/ri-<n>.yml"` (or `ROOT / "skills/repo-infra/assets/pieces/ri-<n>/ri-<n>.yml"`) with `ROOT / ".github/workflows/ri-<n>.yml"`, defining `ROOT = pathlib.Path(__file__).resolve().parents[1]` where the file lacks it:

- `tests/test_ci_pieces.py` lines 103 to 105 (the three paths are relative to `ASSETS`; make them relative to `ROOT` as `.github/workflows/<n>.yml`)
- `tests/test_ci_rust.py:12`, `tests/test_ci_man.py:13`, `tests/test_release_nfpm.py:18`, `tests/test_github_action.py:18`, `tests/test_release_source_tarball.py:10`, `tests/test_release_mode.py` (`release_pr_current_job`), and every `PIECE =` in `tests/test_release_rust_binaries.py`, `tests/test_release_homebrew.py`, `tests/test_publish*.py`, `tests/test_ci_rust_musl.py` found by `grep -n 'pieces/ri-' tests/*.py`
- `tests/test_callers.py:946` (`test_the_mtuspy_example_callers_have_no_problem`): glob `ROOT / ".github/workflows"` for `ri-*.yml` instead of the store
- `tests/test_cli.py:47` and `tests/test_piece_model.py:99`: the fake `ri-x` there is a byte piece in `current`, so `assets / "pieces/ri-x/ri-x.yml"` stays valid; leave them
- `tests/test_catalogue.py:21`: the expected text stays `### ri-x v2\n\nInstalled at ...` (a byte piece)

A test that asserts a marker version of a moved piece (`grep -n 'ri-[a-z-]* v1' tests/*.py`) expects `v2`. `tests/test_release_nfpm.py:77` (`# Pieces: ri-release-rust-binaries, workflow-lib`) stays until Task 3.

- [ ] **Step 8: `tests/generations.py`**

In `piece_sources`, skip `spec.get("kind") == "remote"`. In `released_files`, skip `now` entries whose spec is remote (`if spec.get("kind") == "remote": continue` before `if name not in old`). Then drop the remote paths from the record and regenerate:

```bash
cd /scratch/oetiker/claude-worktrees/repo-infra-release-pieces
python3 - <<'EOF'
import json, pathlib
p = pathlib.Path("skills/repo-infra/assets/generations.json")
record = json.loads(p.read_text(encoding="utf-8"))
kept = {k: v for k, v in record.items() if not k.startswith("pieces/ri-")}
p.write_text(json.dumps(kept, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(len(record) - len(kept), "remote paths dropped")
EOF
make generations
git diff --stat skills/repo-infra/assets/generations.json
```

Expected: only deletions of `pieces/ri-*` paths. `make generations` re-adds nothing (released tags are read under the current manifest, which has no byte `ri-*` piece).

- [ ] **Step 9: `check.py`: home, remote pieces in `piece_items`, core pieces must be called**

```python
def is_home(repo_root):
    """True in repo-infra itself, the repository that ships the pieces (D33):
    its pieces are local and called through ./, and its library is the
    library."""
    return (pathlib.Path(repo_root) / "skills/repo-infra/assets/manifest.json").is_file()
```

In `piece_items`, compute states only for byte pieces (`{n: p for n, p in pieces.items() if not p.remote}`), and add:

```python
def core_call_items(docs, pieces):
    """A core remote piece is used by calling it (D33). Before D33 an absent
    core piece read missing and apply installed it."""
    return [Item("pieces", name, "missing",
                 f"no workflow calls it; every repository calls {piece.uses} "
                 "(see its Call: in the catalogue)")
            for name, piece in sorted(pieces.items())
            if piece.remote and piece.core
            and not callers.calls(docs, pathlib.PurePosixPath(piece.target).name)]
```

and append `core_call_items(docs, pieces)` in `run` after `piece_items`. `callers.calls` matches local calls only in this task; Task 9 widens it to remote calls. In `unknown_items`, a marker naming a remote piece is known (it is in `pieces`), so nothing changes there.

In `missing_dependencies`, skip names that are not in `states`.

- [ ] **Step 10: `catalogue.py`**

```python
def entry(piece):
    head = f"### {piece.name}" + ("" if piece.remote else f" v{piece.version}")
    where = (f"Called as `{piece.uses}`." if piece.remote
             else f"Installed at `{piece.target}`.")
    lines = [head, "", where, ""]
    ...
```

Rewrite `INTRO`:

```python
INTRO = """# Catalogue

Generated by `make catalogue` from the header block, the inputs and the
secrets of every piece. Do not edit it by hand.

A workflow piece is called, never copied (D33): its snippet is the job a
caller adds, with `uses: oposs/repo-infra/.github/workflows/<piece>.yml@v2`.
A job in `ci.yml` also carries the `if:` of `assets/callers/release-pr-skip.yml`
(D31), which no snippet shows. `apply --item <piece>` installs a build file
and commits it.
"""
```

and the `release` group title to `"Release flow: called from changelog.yml, ci.yml and release-pr.yml"`.

- [ ] **Step 11: Run the tests, regenerate, gate**

```bash
cd /scratch/oetiker/claude-worktrees/repo-infra-release-pieces
make catalogue
python3 -m pytest -q --basetemp=.pytest-tmp tests/test_piece_model.py tests/test_pieces.py \
  tests/test_catalogue.py tests/test_check.py tests/test_self_check.py tests/test_generations.py
make check
```

Expected: PASS. `test_self_check` passes: repo-infra calls every core remote piece it calls today through `./`, and `ri-ci-lib.yml` is a project-owned workflow called with `ref`.

- [ ] **Step 12: Changelog and commit**

Under `## [Unreleased]`, `### Changed`:

```markdown
- The reusable workflows (`ri-*.yml`) live once, in `.github/workflows/` of repo-infra. The catalogue shows each one with the line consumers call it by, `uses: oposs/repo-infra/.github/workflows/<piece>.yml@v2`. `ri-ci-lib` is no longer in the catalogue.
```

```bash
cd /scratch/oetiker/claude-worktrees/repo-infra-release-pieces
git add -A .github/workflows skills/repo-infra tests CHANGES.md
git commit -m "Keep every piece once, in .github/workflows (D33)

GitHub runs a reusable workflow only from .github/workflows/, so the
store reads the remote pieces there, from the plugin root, and the
copies under assets/pieces/ go with their upgrade notes. A remote piece
carries the major tag as its marker version. Fragments, changelog,
release-pr and the library keep the byte model for now; generations.json
drops the remote paths. ri-ci-lib leaves the catalogue: it tests a
library consumers will no longer carry.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Pieces load the library from their own commit

**Files:**
- Modify: `.github/workflows/ri-ci-rust.yml`, `ri-publish-finalize.yml`, `ri-publish-gitea.yml`, `ri-publish-tag.yml`, `ri-release-homebrew.yml`, `ri-release-nfpm.yml`, `ri-release-pr-current.yml` (every remote piece whose text contains `.github/workflows/lib`)
- Modify: the `Pieces:` header line of every remote piece that names `workflow-lib`
- Test: `tests/test_pieces.py`, and the harnesses in `tests/test_release_mode.py`, `tests/test_publish.py`, `tests/test_publish_build.py`, `tests/test_publish_gitea.py`, `tests/test_release_nfpm.py`, `tests/test_release_homebrew.py`, `tests/test_ci_rust.py` that copy the library into a fake workspace

**Interfaces:**
- Consumes: Task 1's result (`job.workflow_repository`, `job.workflow_sha` work across repositories).
- Produces: in every job that requires the library, the step `LIB_CHECKOUT` below, after every source checkout of that job and before its first `actions/github-script` step; scripts require `${process.env.GITHUB_WORKSPACE}/.repo-infra/.github/workflows/lib/<module>.js`. `tests/test_pieces.py` exports `LIB_CHECKOUT` (a dict) for later tasks.

The step, written the same way in every piece:

```yaml
      # The library of the commit this piece was loaded from (D33): repo-infra
      # at the release v2 points at, or the commit under test in repo-infra.
      - uses: actions/checkout@v7
        with:
          repository: ${{ job.workflow_repository }}
          ref: ${{ job.workflow_sha }}
          path: .repo-infra
          sparse-checkout: .github/workflows/lib
```

- [ ] **Step 1: Write the failing invariant tests** (append to `tests/test_pieces.py`)

```python
LIB_CHECKOUT = {
    "uses": "actions/checkout@v7",
    "with": {"repository": "${{ job.workflow_repository }}",
             "ref": "${{ job.workflow_sha }}",
             "path": ".repo-infra",
             "sparse-checkout": ".github/workflows/lib"}}
LIB_PATH = ".repo-infra/.github/workflows/lib/"


def _library_jobs(piece):
    return {job_id: job for job_id, job in doc_of(piece)["jobs"].items()
            if ".github/workflows/lib/" in str(job.get("steps", ""))}


@pytest.mark.parametrize("piece", REMOTE, ids=ids)
def test_a_piece_requires_the_library_only_from_its_own_commit(piece):
    text = piece.files[piece.target]
    for line in text.splitlines():
        if ".github/workflows/lib" in line and not line.lstrip().startswith("#"):
            assert (LIB_PATH in line or "sparse-checkout: .github/workflows/lib" in line), line


@pytest.mark.parametrize("piece", REMOTE, ids=ids)
def test_the_library_checkout_follows_every_source_checkout(piece):
    """actions/checkout cleans the workspace, so a source checkout after the
    library checkout would delete .repo-infra (D33)."""
    for job_id, job in _library_jobs(piece).items():
        steps = job["steps"]
        libs = [i for i, s in enumerate(steps) if s == LIB_CHECKOUT]
        assert len(libs) == 1, f"{job_id}: one library checkout"
        sources = [i for i, s in enumerate(steps)
                   if str(s.get("uses", "")).startswith("actions/checkout@") and s != LIB_CHECKOUT]
        scripts = [i for i, s in enumerate(steps)
                   if str(s.get("uses", "")).startswith("actions/github-script@")]
        assert all(i < libs[0] for i in sources), f"{job_id}: source checkout after the library"
        assert all(libs[0] < i for i in scripts), f"{job_id}: script before the library"


@pytest.mark.parametrize("piece", REMOTE, ids=ids)
def test_a_remote_piece_needs_no_workflow_lib_piece(piece):
    assert "workflow-lib" not in piece.needs
```

- [ ] **Step 2: Run them to see them fail**

Run: `python3 -m pytest -q --basetemp=.pytest-tmp tests/test_pieces.py -k "library or workflow_lib"`
Expected: FAIL for the seven pieces named under Files.

- [ ] **Step 3: Change the seven pieces**

In each, for every job whose steps require the library:

1. Insert `LIB_CHECKOUT` (the YAML above, with its comment) directly after the job's last `actions/checkout` step, or as the first step when the job has none.
2. Replace `${ws}/.github/workflows/lib` and `${process.env.GITHUB_WORKSPACE}/.github/workflows/lib` with `${process.env.GITHUB_WORKSPACE}/.repo-infra/.github/workflows/lib` (where the script defines `const ws = process.env.GITHUB_WORKSPACE`, write `${ws}/.repo-infra/.github/workflows/lib`).
3. Remove `workflow-lib` from the `# Pieces:` line; delete the line when nothing remains.

Read each job before editing for a step that reads the whole tree (`git status`, `git archive`, `tar` of `.`, `cargo package`). The jobs that require the library today (`rust-plan` of `ri-ci-rust`, the bottle and formula jobs of `ri-release-homebrew`, the package job of `ri-release-nfpm`, the publish jobs) have none on 2026-10-13; if one appears, move the library work into a job of its own, as the spec says, instead of adding `.repo-infra` to that tree.

`ri-ci-rust`'s `rust-plan` reads `.github/repo-infra.json` of the source checkout; that path stays `${ws}/.github/repo-infra.json`.

- [ ] **Step 4: Fix the harnesses**

Every test that copies the library into a fake workspace copies it to `ws / ".repo-infra/.github/workflows/lib"` instead of `ws / ".github/workflows/lib"` for the scripts of these seven pieces. Find them with `grep -n 'workflows/lib' tests/test_release_mode.py tests/test_publish*.py tests/test_release_nfpm.py tests/test_release_homebrew.py tests/test_ci_rust.py`. In `tests/test_release_mode.py`, `_workspace(tmp_path, base_too=False)` (used by `release_pr_current`) copies to `.repo-infra/...`; the `ci-passed` harness keeps its paths until Task 4. `tests/test_release_nfpm.py:62` asserts the new require path; `:77` asserts the header without `workflow-lib`.

- [ ] **Step 5: Run the tests**

Run: `python3 -m pytest -q --basetemp=.pytest-tmp tests/test_pieces.py tests/test_release_mode.py tests/test_publish.py tests/test_publish_build.py tests/test_publish_gitea.py tests/test_release_nfpm.py tests/test_release_homebrew.py tests/test_ci_rust.py`
Expected: PASS.

- [ ] **Step 6: Catalogue, gate, changelog, commit**

`make catalogue && make check` (timeout 600000). Expected: PASS; the catalogue loses `workflow-lib` under "Needs the pieces".

`CHANGES.md`, `### Changed`:

```markdown
- The reusable workflows load the workflow library from the repo-infra commit they were called from. A repository that calls them needs no `.github/workflows/lib/` of its own.
```

```bash
git add -A .github/workflows tests skills/repo-infra/references/catalogue.md CHANGES.md
git commit -m "Load the library from the piece's own commit (D33)

A piece runs in the consumer's repository, whose checkout holds the
consumer's files. Each job that requires the library now checks out
job.workflow_repository at job.workflow_sha into .repo-infra, sparse on
.github/workflows/lib, after its source checkout: actions/checkout
cleans the workspace and would delete .repo-infra otherwise. The probe
of Task 1 confirmed both fields across organisations.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The required checks stay inline and read two judges

`ri-release-verdict` and `ri-changelog` carry the library work; `ci-passed` and `changelog-updated` stay inline in the callers. The byte piece `changelog` retires in the same commit, because repo-infra's `changelog.yml` becomes a caller of `ri-changelog`.

**Files:**
- Create: `.github/workflows/ri-release-verdict.yml`, `.github/workflows/ri-changelog.yml`, `skills/repo-infra/assets/callers/changelog.yml`
- Modify: `skills/repo-infra/assets/callers/ci-passed.yml`, `skills/repo-infra/assets/callers/release-pr-skip.yml` (comment), `.github/workflows/ci.yml`, `.github/workflows/changelog.yml`, `.github/workflows/lib/release.js`, `.github/workflows/lib/release.test.js`, `skills/repo-infra/assets/pieces/workflow-lib/lib/release.js` and `release.test.js` (same text: the two copies stay equal until Task 5), `skills/repo-infra/assets/pieces/workflow-lib/CHANGES.md` (`## v10`), every `skills/repo-infra/assets/pieces/workflow-lib/lib/*.js` marker and `.github/workflows/lib/*.js` marker to v10, `skills/repo-infra/assets/manifest.json`, `skills/repo-infra/scripts/repo_infra/callers.py`, `skills/repo-infra/references/examples/repo-infra/ci.yml` (equal to `.github/workflows/ci.yml`)
- Delete: `skills/repo-infra/assets/pieces/changelog/`
- Test: `tests/test_release_mode.py`, `tests/test_changelog_gate.py`, `tests/test_callers.py`, `tests/piecekit.py` (`CI_PASSED`)

**Interfaces:**
- Produces: piece `ri-release-verdict` (group `release`, core): no inputs; outputs `mode` (`release` or `ordinary`), `ok` (`true` or `false`), `message`; job id `verdict`; permissions `contents: read`, `pull-requests: read`, `statuses: read`. Piece `ri-changelog` (group `release`, core): no inputs; output `message`; job id `changelog`; same permissions. Library: `release.verdictOutputs(github, { eventName, owner, repo, pr }) -> Promise<{ mode, ok, message }>`. `callers.normal_uses(uses) -> str` (the file name of a call to a repo-infra piece in either form, otherwise `uses` unchanged); `callers.VERDICT = "ri-release-verdict"`; `callers.changelog_problems(docs, assets) -> [(file, detail)]`.

- [ ] **Step 1: Failing library test** (append to `.github/workflows/lib/release.test.js`)

```js
test('verdictOutputs: ordinary on every event but a pull request from release/*', async () => {
  const never = { paginate: async () => { throw new Error('no API call expected'); } };
  for (const eventName of ['push', 'workflow_dispatch', 'workflow_call']) {
    assert.deepEqual(await verdictOutputs(never, { eventName, owner: 'o', repo: 'r', pr: null }),
      { mode: 'ordinary', ok: 'true', message: '' });
  }
  const pr = { head: { ref: 'fix/x', sha: 'h', repo: { full_name: 'o/r' } },
    user: { login: BOT }, base: { ref: 'main' } };
  assert.deepEqual(await verdictOutputs(never, { eventName: 'pull_request', owner: 'o', repo: 'r', pr }),
    { mode: 'ordinary', ok: 'true', message: '' });
});

test('verdictOutputs: a release pull request reports its verdict without throwing', async () => {
  const pr = { number: 7, head: { ref: 'release/v1.2.0', sha: 'h', repo: { full_name: 'o/r' } },
    user: { login: BOT }, base: { ref: 'main' } };
  const github = {
    paginate: async () => [{ context: 'release-built', state: 'success', creator: { login: BOT } }],
    rest: { repos: { listCommitStatusesForRef: 'statuses',
      compareCommitsWithBasehead: async () => ({ data: { behind_by: 2 } }) } },
  };
  const out = await verdictOutputs(github, { eventName: 'pull_request', owner: 'o', repo: 'r', pr });
  assert.equal(out.mode, 'release');
  assert.equal(out.ok, 'false');
  assert.match(out.message, /^main moved after v1\.2\.0 was built/);
});

test('verdictOutputs: someone else\'s release/x is ordinary', async () => {
  const pr = { head: { ref: 'release/x', sha: 'h', repo: { full_name: 'fork/r' } },
    user: { login: 'someone' }, base: { ref: 'main' } };
  const out = await verdictOutputs({}, { eventName: 'pull_request', owner: 'o', repo: 'r', pr });
  assert.deepEqual(out, { mode: 'ordinary', ok: 'true', message: '' });
});
```

Import `verdictOutputs` and `BOT` in the test file's `require` line the way the other names are imported. Run `node --test .github/workflows/lib/release.test.js`. Expected: FAIL, `verdictOutputs is not a function`.

- [ ] **Step 2: `verdictOutputs` in `release.js`** (both copies), exported:

```js
// D33: the outputs of ri-release-verdict, which the inline ci-passed reads.
// Only a pull request from a release/* branch asks the API; every other event
// is ordinary. An API error throws, which fails the verdict job, and ci-passed
// fails when that job did not succeed.
async function verdictOutputs(github, { eventName, owner, repo, pr }) {
  const ordinary = { mode: 'ordinary', ok: 'true', message: '' };
  if (eventName !== 'pull_request' || !pr || !pr.head.ref.startsWith('release/')) {
    return ordinary;
  }
  const verdict = await releaseModeVerdict(github, { owner, repo, pr });
  if (verdict === null) return ordinary;
  return { mode: 'release', ok: verdict.ok ? 'true' : 'false', message: verdict.message };
}
```

Bump workflow-lib to v10 in both copies (`sed -i '1s|^// repo-infra: workflow-lib v9$|// repo-infra: workflow-lib v10|'` over both `lib/*.js` sets) and add above `## v9` in `skills/repo-infra/assets/pieces/workflow-lib/CHANGES.md`:

```markdown
## v10

No caller or config change. release.js gains verdictOutputs, which ri-release-verdict runs.
```

Run `node --test .github/workflows/lib/*.test.js`. Expected: PASS.

- [ ] **Step 3: `.github/workflows/ri-release-verdict.yml`**

```yaml
# repo-infra: ri-release-verdict v2
#
# Purpose: Judge a release pull request for the inline ci-passed job (D28, D33).
# Choose: Always; ci.yml calls it and ci-passed reads its outputs.
# Supplies: The ci-passed job of assets/callers/ci-passed.yml, which needs this job.
# Produces: The outputs mode (release or ordinary), ok (true or false) and message.
# Call:
#   release-verdict:
#     uses: oposs/repo-infra/.github/workflows/ri-release-verdict.yml@v2
#     permissions:
#       contents: read
#       pull-requests: read
#       statuses: read
#
# It runs on every event and carries no D31 skip: on the release pull request
# that Create release PR opened, this verdict is what ci-passed decides on.
# On a pull request from a release/* branch that github-actions[bot] opened
# in this repository, mode is release and ok says whether the head is the
# built commit and not behind main. Everywhere else mode is ordinary. The
# library comes from repo-infra's commit, which a pull request in the
# calling repository cannot change.

name: Release verdict

on:
  workflow_call:
    outputs:
      mode:
        description: release on a release pull request, otherwise ordinary.
        value: ${{ jobs.verdict.outputs.mode }}
      ok:
        description: true unless a release pull request's build does not stand.
        value: ${{ jobs.verdict.outputs.ok }}
      message:
        description: Why a release pull request passes or fails; empty when ordinary.
        value: ${{ jobs.verdict.outputs.message }}

permissions:
  contents: read
  pull-requests: read
  statuses: read

jobs:
  verdict:
    name: Release verdict
    runs-on: ubuntu-latest
    timeout-minutes: 5
    outputs:
      mode: ${{ steps.verdict.outputs.mode }}
      ok: ${{ steps.verdict.outputs.ok }}
      message: ${{ steps.verdict.outputs.message }}
    steps:
      # The library of the commit this piece was loaded from (D33): repo-infra
      # at the release v2 points at, or the commit under test in repo-infra.
      - uses: actions/checkout@v7
        with:
          repository: ${{ job.workflow_repository }}
          ref: ${{ job.workflow_sha }}
          path: .repo-infra
          sparse-checkout: .github/workflows/lib

      - uses: actions/setup-node@v7
        with:
          node-version: 22

      - id: verdict
        name: Release mode
        uses: actions/github-script@v9
        with:
          script: |
            const releaseLib = require(
              `${process.env.GITHUB_WORKSPACE}/.repo-infra/.github/workflows/lib/release.js`);
            const { owner, repo } = context.repo;
            const out = await releaseLib.verdictOutputs(github, {
              eventName: context.eventName, owner, repo,
              pr: context.payload.pull_request || null,
            });
            for (const [key, value] of Object.entries(out)) core.setOutput(key, value);
            if (out.mode === 'release') core.notice(out.message);
```

Manifest entry: `"ri-release-verdict": {"kind": "remote", "group": "release", "core": true}`.

- [ ] **Step 4: `.github/workflows/ri-changelog.yml`**

The header:

```yaml
# repo-infra: ri-changelog v2
#
# Purpose: Judge a pull request's CHANGES.md for the inline changelog-updated job (D2, D6, D33).
# Choose: Always; changelog.yml calls it and changelog-updated reads its result.
# Supplies: CHANGES.md with an Unreleased section; the no-changelog label.
# Produces: The output message; the job fails when the changelog is refused.
# Call:
#   changelog:
#     if: >-
#       startsWith(github.head_ref, 'release/') ||
#       !contains(github.event.pull_request.labels.*.name, 'no-changelog')
#     uses: oposs/repo-infra/.github/workflows/ri-changelog.yml@v2
#     permissions:
#       contents: read
#       pull-requests: read
#       statuses: read
#
# A release pull request is opened by GITHUB_TOKEN, so its runs park until
# someone approves them. Nobody needs to (D28): Create release PR writes the
# changelog-updated check itself. This job exists for the case where someone
# approves them anyway, or presses Update branch, and then agrees with Create
# release PR.

name: Changelog

on:
  workflow_call:
    outputs:
      message:
        description: The verdict on CHANGES.md, or why a release pull request passes or fails.
        value: ${{ jobs.changelog.outputs.message }}

permissions:
  contents: read
  pull-requests: read
  statuses: read

jobs:
  changelog:
    name: Changelog verdict
    runs-on: ubuntu-latest
    timeout-minutes: 5
    outputs:
      message: ${{ steps.verdict.outputs.message }}
    steps:
      # (LIB_CHECKOUT with its comment, as in ri-release-verdict)
      - uses: actions/setup-node@v7
        with:
          node-version: 22
      - id: verdict
        uses: actions/github-script@v9
        with:
          script: |
            ...
```

The script is today's script of `.github/workflows/changelog.yml` (the `actions/github-script` step of `changelog-updated`) with these edits, and no others:

1. Replace the block from `const ws = process.env.GITHUB_WORKSPACE;` down to `|| require(\`${ws}/.github/workflows/lib/changes.js\`);` with

   ```js
   const lib = `${process.env.GITHUB_WORKSPACE}/.repo-infra/.github/workflows/lib`;
   const changes = require(`${lib}/changes.js`);
   ```

2. `require(\`${baseLib}/release.js\`)` becomes `require(\`${lib}/release.js\`)`.
3. Before each `core.setFailed(X)` add `core.setOutput('message', X);`, and before each `core.notice(X)` add `core.setOutput('message', X);`, so the inline job can print the verdict.

The base-commit loading goes: the library comes from repo-infra's commit (D33), which a pull request in the consumer cannot change, so the reason it existed (a pull request that edits `lib/changes.js` judged by its own rules) is gone for consumers. In repo-infra a pull request is judged by its own library, which the spec accepts.

Manifest entry: `"ri-changelog": {"kind": "remote", "group": "release", "core": true}`.

- [ ] **Step 5: `assets/callers/ci-passed.yml`** (whole file)

```yaml
# The release-verdict and ci-passed jobs of every ci.yml (D2, D30, D33). Copy
# both under `jobs:` word for word and fill in ci-passed's `needs:` with every
# other job of the file, release-verdict included. check compares them with
# this text, so a change here reaches every repository as a finding.
jobs:
  # D28 release mode, decided by repo-infra (D33). It runs on every event and
  # carries no D31 skip: on the release pull request Create release PR opened,
  # this verdict is what ci-passed decides on.
  release-verdict:
    uses: oposs/repo-infra/.github/workflows/ri-release-verdict.yml@v2
    permissions:
      contents: read
      pull-requests: read
      statuses: read

  # The single context the ruleset requires (spec D2). It exists so branch
  # protection can name one check that means "this repository's CI passed",
  # whatever this repository's jobs happen to be. Its needs: list names every
  # other job of ci.yml; check verifies it (D30). Copy the rest word for word.
  #
  # `if: always()` is load-bearing. Without it this job is *skipped* when a
  # dependency fails, and a skipped job reports Success -- so the required
  # check would go green on a red build. It fails open, silently, and looks
  # like it is working.
  #
  # A required check cannot be a called workflow's job: GitHub names that
  # `<caller job> / <called job>`, and a called workflow cannot read the
  # caller's needs. So this job stays here and reads release-verdict (D33).
  # On a release pull request the test results do not count: Create release
  # PR tested exactly the head that carries the release-built status.
  ci-passed:
    if: always()
    needs: [release-verdict]
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions:
      contents: read
    steps:
      - name: Judge the needed jobs
        env:
          VERDICT: ${{ needs.release-verdict.result }}
          MODE: ${{ needs.release-verdict.outputs.mode }}
          OK: ${{ needs.release-verdict.outputs.ok }}
          MESSAGE: ${{ needs.release-verdict.outputs.message }}
          FAILED: ${{ contains(needs.*.result, 'failure') || contains(needs.*.result, 'cancelled') }}
        run: |
          if [ "$VERDICT" != success ]; then
            echo "::error::release-verdict did not succeed ($VERDICT); no verdict, no green"
            exit 1
          fi
          if [ "$MODE" = release ]; then
            if [ "$OK" != true ]; then
              echo "::error::$MESSAGE"
              exit 1
            fi
            echo "::notice::$MESSAGE"
            exit 0
          fi
          if [ "$FAILED" = true ]; then
            echo "::error::a job this one needs failed or was cancelled"
            exit 1
          fi
```

`release-pr-skip.yml`'s comment: "Copy it onto each such job" becomes "Copy it onto every job of ci.yml except ci-passed and release-verdict"; its `if:` line is unchanged.

In `tests/piecekit.py`, write `CI_PASSED` as the literal text of the `ci-passed` job above (from `jobs:\n  ci-passed:\n    if: always()` to the last `fi`), and add a test in `tests/test_callers.py` that holds it equal to the shipped job:

```python
def test_the_fixture_ci_passed_is_the_shipped_one():
    shipped = workflow.load((ASSETS / "callers/ci-passed.yml").read_text(encoding="utf-8"))
    assert workflow.load(CI_PASSED)["jobs"]["ci-passed"] == shipped["jobs"]["ci-passed"]
```

(`ASSETS` there is `pathlib.Path(__file__).resolve().parents[1] / "skills/repo-infra/assets"`.)

- [ ] **Step 6: `assets/callers/changelog.yml`** (whole file)

```yaml
name: Changelog
# The changelog.yml of every repository (D2, D6, D33). Copy it word for word;
# check compares it with this text.
#
# Required, not advisory (spec D2). Being required is only safe because the
# escape hatch below is a JOB-level `if:`. A job skipped by a condition
# reports Success, while a WORKFLOW skipped by a paths/branches filter stays
# Pending forever and blocks the merge. Never add paths: or paths-ignore: to
# this workflow (spec D13).

on:
  pull_request:
    branches: [main]
    types: [opened, synchronize, reopened, labeled, unlabeled]

permissions:
  contents: read

jobs:
  # The no-changelog label is the deliberate escape hatch for typo and CI-only
  # changes. Without it every weekly dependabot PR is blocked, since the
  # check is required. release/* always runs: a release pull request is gated
  # on its build, and the label must not turn that red check green.
  changelog:
    if: >-
      startsWith(github.head_ref, 'release/') ||
      !contains(github.event.pull_request.labels.*.name, 'no-changelog')
    uses: oposs/repo-infra/.github/workflows/ri-changelog.yml@v2
    permissions:
      contents: read
      pull-requests: read
      statuses: read

  # No `name:`: the check context is the job id, `changelog-updated`, which is
  # what the ruleset requires. Renaming this job silently un-requires the check.
  #
  # The same label condition, joined with !cancelled(). Without it this job
  # is skipped when `changelog` fails, and a skipped required check counts as
  # passed. always() would also run it in a cancelled run and turn that red.
  changelog-updated:
    if: >-
      !cancelled() && (startsWith(github.head_ref, 'release/') ||
      !contains(github.event.pull_request.labels.*.name, 'no-changelog'))
    needs: changelog
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions:
      contents: read
    steps:
      - name: Read the changelog verdict
        env:
          RESULT: ${{ needs.changelog.result }}
          MESSAGE: ${{ needs.changelog.outputs.message }}
        run: |
          if [ "$RESULT" != success ]; then
            echo "::error::changelog did not pass ($RESULT): $MESSAGE"
            exit 1
          fi
          echo "::notice::$MESSAGE"
```

The folded `>-` scalar keeps the leading `!` out of YAML's tag syntax; check that `workflow.load` reads both `if:` values as the joined strings (`tests/test_workflow.py` covers folded scalars).

- [ ] **Step 7: repo-infra's own callers**

`.github/workflows/changelog.yml` becomes `assets/callers/changelog.yml` with one change: `uses: ./.github/workflows/ri-changelog.yml` (P7).

`.github/workflows/ci.yml`: insert the `release-verdict` job of `assets/callers/ci-passed.yml` before `ci-passed`, with `uses: ./.github/workflows/ri-release-verdict.yml`; replace the `ci-passed` job (with its comment block) by the pattern's, with `needs: [lib, plugin, python, selftest, release-pr-current, release-verdict]`. Copy the result to `skills/repo-infra/references/examples/repo-infra/ci.yml`.

Delete `skills/repo-infra/assets/pieces/changelog/` and its manifest entry. Run `make generations`: the `pieces/changelog/` paths leave the record (the manifest no longer ships the piece, so `vanished` reports them; delete them from `generations.json` as it says, then run again).

- [ ] **Step 8: `callers.py`**

```python
VERDICT = "ri-release-verdict"
_HOME_CALL = re.compile(r"^oposs/repo-infra/\.github/workflows/([^@]+)@(.*)$")


def normal_uses(uses):
    """The file of a call to a repo-infra piece in either form, so a pattern
    written for consumers (@v2) matches repo-infra's own ./ callers (D33)."""
    if not isinstance(uses, str):
        return uses
    match = _HOME_CALL.match(uses)
    if match:
        return match[1]
    return local_target(uses) or uses


def _normal_job(job):
    return {key: (normal_uses(value) if key == "uses" else value)
            for key, value in job.items() if key != "needs"}
```

In `closing_problems`, read both jobs of the pattern; for `ci.yml` compare `ci-passed` with `_normal_job` on both sides, and add: when `ci.yml` has no job whose `normal_uses(uses)` is `f"{VERDICT}.yml"`, report `(name, "ci.yml calls no ri-release-verdict; ci-passed has no release verdict to read. Copy release-verdict from assets/callers/ci-passed.yml in the repo-infra skill")`; when it has one whose job differs from the pattern's `release-verdict` under `_normal_job`, report `(name, "release-verdict differs from the pattern (assets/callers/ci-passed.yml in the repo-infra skill); copy it word for word")`.

In `release_skip_problems`, skip a job whose `normal_uses(job.get("uses"))` is `f"{VERDICT}.yml"`, and say so in the docstring: D33 exempts the verdict.

Add:

```python
def changelog_problems(docs, assets=ASSETS):
    """D33: changelog.yml is the pattern, word for word, apart from the form
    of the `uses:` line."""
    doc = docs.get("changelog.yml")
    if not isinstance(doc, dict):
        return []
    pattern = workflow.load(
        (pathlib.Path(assets) / "callers/changelog.yml").read_text(encoding="utf-8"))
    mine, wanted = jobs(doc), jobs(pattern)
    found = []
    for job_id, job in wanted.items():
        if job_id not in mine:
            found.append(("changelog.yml", f"has no {job_id} job; copy "
                                           "assets/callers/changelog.yml in the repo-infra "
                                           "skill word for word"))
        elif {**_normal_job(mine[job_id]), "needs": needs(mine[job_id])} != {
                **_normal_job(job), "needs": needs(job)}:
            found.append(("changelog.yml", f"{job_id} differs from the pattern "
                                           "(assets/callers/changelog.yml in the repo-infra "
                                           "skill); copy it word for word"))
    if doc.get("on") != pattern.get("on"):
        found.append(("changelog.yml", "its triggers differ from the pattern; the required "
                                       "check would not report on every pull request"))
    return found
```

and call it from `validate` with the others. `frame_problems` is unchanged.

- [ ] **Step 9: Port the tests**

`tests/test_release_mode.py`:

- `ci_passed_job()` reads `jobs["ci-passed"]` of the new pattern; add `verdict_job()` reading `jobs["release-verdict"]` and `verdict_piece()` reading `.github/workflows/ri-release-verdict.yml`.
- Replace `test_ci_passed_raises_only_what_release_mode_reads`, `test_release_mode_loads_the_library_from_the_base_commit`, `test_the_release_mode_steps_run_on_pull_requests_from_release_branches`, `test_an_api_error_in_release_mode_fails_the_step`, `test_the_failure_step_is_skipped_in_release_mode` and `test_ci_passed_reads_the_library_of_the_base_commit` with:

```python
def test_the_verdict_job_grants_what_the_piece_reads():
    assert verdict_job()["permissions"] == {
        "contents": "read", "pull-requests": "read", "statuses": "read"}
    assert verdict_job()["uses"] == "oposs/repo-infra/.github/workflows/ri-release-verdict.yml@v2"
    assert "if" not in verdict_job()


def test_ci_passed_needs_the_verdict_and_reads_nothing_else():
    job = ci_passed_job()
    assert job["if"] == "always()"
    assert job["needs"] == ["release-verdict"]
    assert job["permissions"] == {"contents": "read"}


def _judge(tmp_path, **env):
    step = ci_passed_job()["steps"][0]
    script = tmp_path / "judge.sh"
    script.write_text(step["run"], encoding="utf-8")
    full = {"PATH": os.environ["PATH"], "VERDICT": "success", "MODE": "ordinary", "OK": "true",
            "MESSAGE": "", "FAILED": "false", **env}
    return subprocess.run(["bash", "-e", str(script)], env=full, capture_output=True, text=True)


@pytest.mark.parametrize("env, passes", [
    ({}, True),
    ({"FAILED": "true"}, False),
    ({"VERDICT": "failure"}, False),
    ({"VERDICT": "skipped"}, False),
    ({"VERDICT": "cancelled"}, False),
    ({"MODE": "release", "OK": "true", "MESSAGE": "v1.2.0 built and current"}, True),
    ({"MODE": "release", "OK": "true", "FAILED": "true"}, True),
    ({"MODE": "release", "OK": "false", "MESSAGE": STALE}, False),
    ({"MODE": "release", "OK": ""}, False),
])
def test_ci_passed_step_table(tmp_path, env, passes):
    proc = _judge(tmp_path, **env)
    assert (proc.returncode == 0) is passes, proc.stdout
    if env.get("OK") == "false":
        assert f"::error::{STALE}" in proc.stdout
```

- The `ci_passed(...)` harness runs the verdict piece's script instead: `script = next(s for s in verdict_piece()["jobs"]["verdict"]["steps"] if s.get("id") == "verdict")["with"]["script"]`, the workspace holds the library at `.repo-infra/.github/workflows/lib`, and the fake `context` adds `eventName: 'pull_request'`. The four verdict tests (`a_built_current...`, `a_stale...`, `an_unbuilt...`, `someone_elses...`) then assert on `outputs` (`{"mode": "release", "ok": "true", "message": ...}` and so on) instead of `failures`: a refused release is `ok == "false"` with the message, and the step itself never fails. Add:

```python
def test_an_api_error_fails_the_verdict_step(tmp_path):
    out = ci_passed(tmp_path, statuses=BUILT, fail_compare=True)
    assert out["thrown"] == "Server Error"
```

`tests/test_changelog_gate.py`: `ASSET` becomes `ROOT / ".github/workflows/ri-changelog.yml"`, `job()` reads `jobs["changelog"]`, the workspace copies the library to `ws / ".repo-infra/.github/workflows/lib"`, and the harness's `core` also records `setOutput`. The tests of the base-commit fallback (`base_lib`, `base_lib_dir`, `sabotage_merge_changes`, the workflow-lib v4 case) are deleted with their reason: D33 loads the library from repo-infra's commit. Every remaining refusal test also asserts `outputs["message"]` equals the failure. Add:

```python
def callers_doc():
    return yaml.safe_load((ROOT / "skills/repo-infra/assets/callers/changelog.yml")
                          .read_text(encoding="utf-8"))


def test_changelog_updated_runs_unless_cancelled_and_reads_the_result():
    jobs = callers_doc()["jobs"]
    label = ("startsWith(github.head_ref, 'release/') || "
             "!contains(github.event.pull_request.labels.*.name, 'no-changelog')")
    assert " ".join(jobs["changelog"]["if"].split()) == label
    assert " ".join(jobs["changelog-updated"]["if"].split()) == f"!cancelled() && ({label})"
    assert jobs["changelog-updated"]["needs"] == "changelog"


@pytest.mark.parametrize("result, passes", [
    ("success", True), ("failure", False), ("cancelled", False), ("skipped", False)])
def test_changelog_updated_step(tmp_path, result, passes):
    run = callers_doc()["jobs"]["changelog-updated"]["steps"][0]["run"]
    script = tmp_path / "step.sh"
    script.write_text(run, encoding="utf-8")
    proc = subprocess.run(["bash", "-e", str(script)], capture_output=True, text=True,
                          env={"PATH": os.environ["PATH"], "RESULT": result,
                               "MESSAGE": "no entry under [Unreleased]"})
    assert (proc.returncode == 0) is passes
```

`tests/test_callers.py`: the fixtures' `CI` gets a `release-verdict` job only where a test needs the real store; for the fake stores, `closing_problems` is fed `assets` with the shipped `callers/ci-passed.yml` (piecekit copies it, see below), so add `release-verdict` to the fake `CI` text as

```python
VERDICT_JOB = ("  release-verdict:\n    uses: oposs/repo-infra/.github/workflows/"
               "ri-release-verdict.yml@v2\n    permissions:\n      contents: read\n"
               "      pull-requests: read\n      statuses: read\n")
```

and list it in `ci-passed`'s `needs`. piecekit writes `callers/ci-passed.yml` from the shipped file (`(ASSETS / "callers/ci-passed.yml").read_text(...)`) and `callers/changelog.yml` likewise, instead of its own `CI_PASSED` text. Add tests:

```python
def test_a_ci_yml_without_the_verdict_job_is_a_problem(tmp_path, store):
    ci = CI.replace(VERDICT_JOB, "").replace(", release-verdict]", "]")
    assert ("ci.yml", "problem", "ci.yml calls no ri-release-verdict; ci-passed has no "
            "release verdict to read. Copy release-verdict from assets/callers/ci-passed.yml "
            "in the repo-infra skill") in problems(tmp_path, store, ci=ci)


def test_the_verdict_job_needs_no_skip():
    doc = workflow.load("jobs:\n" + VERDICT_JOB)
    assert callers.release_skip_problems({"ci.yml": doc}) == []


def test_a_changelog_yml_with_a_dropped_not_cancelled_is_a_problem(tmp_path):
    pattern = (ASSETS / "callers/changelog.yml").read_text(encoding="utf-8")
    broken = pattern.replace("!cancelled() && (", "(")
    docs = {"changelog.yml": workflow.load(broken)}
    assert callers.changelog_problems(docs) == [(
        "changelog.yml", "changelog-updated differs from the pattern "
        "(assets/callers/changelog.yml in the repo-infra skill); copy it word for word")]


def test_this_repositorys_changelog_yml_matches_the_pattern():
    assert callers.changelog_problems({"changelog.yml": workflow.load(own("changelog.yml"))}) == []
```

`test_this_repositorys_ci_yml_skips_on_every_job_but_ci_passed` expects `set(jobs) - {"ci-passed", "release-verdict"}`.

- [ ] **Step 10: Run, regenerate, gate**

```bash
cd /scratch/oetiker/claude-worktrees/repo-infra-release-pieces
make generations && make catalogue
python3 -m pytest -q --basetemp=.pytest-tmp tests/test_release_mode.py tests/test_changelog_gate.py \
  tests/test_callers.py tests/test_pieces.py tests/test_self_check.py tests/test_catalogue.py
make check
```

Expected: PASS.

- [ ] **Step 11: Changelog and commit**

`### Changed`:

```markdown
- `ci-passed` reads its release-mode verdict from a new job, `release-verdict`, which calls `ri-release-verdict`. Copy both jobs from `assets/callers/ci-passed.yml`; `/repo-infra:check` reports a `ci.yml` without `release-verdict`, and `release-verdict` carries no release pull request skip.
- `changelog.yml` is a short caller: its job `changelog` calls `ri-changelog`, and `changelog-updated` turns red when that job fails or is skipped by an error. Copy it from `assets/callers/changelog.yml`; `/repo-infra:check` reports any difference.
```

```bash
git add -A .github skills/repo-infra tests CHANGES.md
git commit -m "Keep the required checks inline, judged by two pieces (D33)

The ruleset requires ci-passed and changelog-updated, and a job that
calls a reusable workflow reports as <caller job> / <called job>, so
both stay inline. ri-release-verdict and ri-changelog carry the library
work. ci-passed fails unless the verdict job succeeded, and in release
mode unless ok is true; changelog-updated joins the label condition with
!cancelled(), because a required job skipped after a failed need would
report success. The changelog piece retires: changelog.yml is a caller.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `release-pr` splits, and the library keeps one copy

`ri-release-prepare` and `ri-release-finish` carry the two jobs of today's `release-pr`; the consumer's `release-pr.yml` wires them around its own build and CI. With `release-pr` retired, no byte piece uses the library, so `workflow-lib` leaves the store in the same commit.

**Files:**
- Create: `.github/workflows/ri-release-prepare.yml`, `.github/workflows/ri-release-finish.yml`, `skills/repo-infra/assets/callers/release-pr.yml`
- Modify: `.github/workflows/release-pr.yml` (caller), every `.github/workflows/lib/*.js` (marker block out), `skills/repo-infra/assets/manifest.json`, `skills/repo-infra/scripts/repo_infra/callers.py`
- Delete: `skills/repo-infra/assets/pieces/release-pr/`, `skills/repo-infra/assets/pieces/workflow-lib/`
- Test: `tests/test_release_pr.py`, `tests/test_release_guard.py`, `tests/test_release_mode.py:test_each_term_of_the_skip_is_a_test_of_is_release_pr`, `tests/test_release_nfpm.py` (`LIB`), `tests/test_callers.py`, `tests/test_generations.py` (fixtures naming `release-pr` or `workflow-lib` stay: they test released history)

**Interfaces:**
- Produces: piece `ri-release-prepare` (group `release`, core): input `release_type` (string, required; `bugfix`, `feature` or `major`); outputs `version`, `date`, `head`, `base`; job id `prepare`; permissions `contents: write`, `pull-requests: read`, `checks: read`, `actions: write`. Piece `ri-release-finish` (group `release`, core): inputs `version`, `date`, `head`, `base` (strings, required); job id `finish`; permissions `contents: write`, `pull-requests: write`, `statuses: write`, `checks: write`. `callers.release_pr_problems(docs, pieces) -> [(file, detail)]`.

- [ ] **Step 1: Failing tests** (rewrite `tests/test_release_pr.py`)

```python
"""release-pr (D28, D33): prepare and finish are pieces; the caller wires the
repository's own build and CI between them."""

import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CALLER = ROOT / "skills/repo-infra/assets/callers/release-pr.yml"
PREPARE = ROOT / ".github/workflows/ri-release-prepare.yml"
FINISH_PIECE = ROOT / ".github/workflows/ri-release-finish.yml"
FINISH = "Commit the release files, draft the release, open the pull request"
REFUSE = "Refuse an open or unpublished release; delete stale drafts and parked runs"


def load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def caller():
    return load(CALLER)


def script(path, job, step_name):
    steps = load(path)["jobs"][job]["steps"]
    return next(s["with"]["script"] for s in steps if s.get("name") == step_name)


def test_the_caller_wires_four_jobs():
    jobs = caller()["jobs"]
    assert list(jobs) == ["prepare", "build", "test", "finish"]
    assert jobs["prepare"]["uses"] == (
        "oposs/repo-infra/.github/workflows/ri-release-prepare.yml@v2")
    assert jobs["finish"]["uses"] == (
        "oposs/repo-infra/.github/workflows/ri-release-finish.yml@v2")
    assert jobs["build"]["needs"] == "prepare" and jobs["test"]["needs"] == "prepare"
    assert jobs["finish"]["needs"] == ["prepare", "build", "test"]


def test_only_the_repositorys_own_workflows_inherit_secrets():
    jobs = caller()["jobs"]
    assert jobs["build"]["secrets"] == "inherit" and jobs["test"]["secrets"] == "inherit"
    assert "secrets" not in jobs["prepare"] and "secrets" not in jobs["finish"]


def test_the_caller_passes_prepares_outputs():
    jobs = caller()["jobs"]
    assert jobs["prepare"]["with"] == {"release_type": "${{ inputs.release_type }}"}
    assert jobs["build"]["with"] == {"version": "${{ needs.prepare.outputs.version }}",
                                     "ref": "${{ needs.prepare.outputs.head }}"}
    assert jobs["finish"]["with"] == {
        key: f"${{{{ needs.prepare.outputs.{key} }}}}"
        for key in ("version", "date", "head", "base")}


def test_permissions_per_job():
    wf = caller()
    assert wf["permissions"] == {"checks": "read", "actions": "read"}
    assert wf["jobs"]["prepare"]["permissions"] == {
        "contents": "write", "pull-requests": "read", "checks": "read", "actions": "write"}
    assert wf["jobs"]["build"]["permissions"] == {"contents": "read"}
    assert wf["jobs"]["test"]["permissions"] == {
        "contents": "read", "pull-requests": "read", "statuses": "read", "checks": "write"}
    assert wf["jobs"]["finish"]["permissions"] == {
        "contents": "write", "pull-requests": "write", "statuses": "write", "checks": "write"}


def test_prepare_takes_the_release_type_through_env():
    s = script(PREPARE, "prepare", "Compute the version and rewrite the files")
    assert "process.env.RELEASE_TYPE" in s
    assert "context.payload.inputs" not in s


def test_prepare_outputs_the_dispatched_main_commit_as_base():
    outputs = load(PREPARE)["jobs"]["prepare"]["outputs"]
    assert outputs["base"] == "${{ steps.commit.outputs.base }}"
    assert "core.setOutput('base', context.sha)" in script(
        PREPARE, "prepare", "Commit the release branch")


def test_finish_reads_its_inputs_through_env():
    s = script(FINISH_PIECE, "finish", FINISH)
    for name in ("VERSION", "DATE", "HEAD", "BASE"):
        assert f"process.env.{name}" in s
    assert "needs.prepare" not in s and "${{" not in s
```

Keep, adapted to the new paths (`script(PREPARE, "prepare", ...)`, `script(FINISH_PIECE, "finish", ...)`): `test_the_guard_does_not_wait`, `test_prepare_refuses_then_cleans_up_before_it_writes_anything`, `test_finish_checks_everything_before_it_creates_the_draft`, `test_finish_records_base_and_head_in_the_build_record`, `test_finish_opens_the_pull_request_before_it_judges_it_against_main`, `test_finish_downloads_both_artifact_kinds`, `test_the_rust_lockfile_note_survives` (on `PREPARE`). Delete `test_the_piece_carries_one_marker_naming_itself` (the remote markers are covered by `test_pieces.py`).

Run: `python3 -m pytest -q --basetemp=.pytest-tmp tests/test_release_pr.py`. Expected: FAIL, the files do not exist.

- [ ] **Step 2: `.github/workflows/ri-release-prepare.yml`**

```yaml
# repo-infra: ri-release-prepare v2
#
# Purpose: Prepare the release branch: guard, refusals, stale drafts and parked runs, roll CHANGES.md, set the version files (D28, D33).
# Choose: Always; release-pr.yml calls it.
# Supplies: version_files in .github/repo-infra.json; CHANGES.md with an Unreleased section.
# Produces: The outputs version, date, head (the release branch head) and base (the dispatched main commit).
# Call:
#   prepare:
#     uses: oposs/repo-infra/.github/workflows/ri-release-prepare.yml@v2
#     permissions:
#       contents: write
#       pull-requests: read
#       checks: read
#       actions: write
#     with:
#       release_type: ${{ inputs.release_type }}

name: Prepare the release branch

on:
  workflow_call:
    inputs:
      release_type:
        description: bugfix, feature or major.
        type: string
        required: true
    outputs:
      version:
        description: The version being released, without the v.
        value: ${{ jobs.prepare.outputs.version }}
      date:
        description: The release date written into CHANGES.md.
        value: ${{ jobs.prepare.outputs.date }}
      head:
        description: The head of the release branch.
        value: ${{ jobs.prepare.outputs.head }}
      base:
        description: The main commit the release was dispatched on.
        value: ${{ jobs.prepare.outputs.base }}

permissions:
  contents: write
  pull-requests: read
  checks: read
  actions: write

jobs:
  prepare:
    name: Prepare the release branch
    runs-on: ubuntu-latest
    timeout-minutes: 15
    outputs:
      version: ${{ steps.prepare.outputs.version }}
      date: ${{ steps.prepare.outputs.date }}
      head: ${{ steps.commit.outputs.head }}
      base: ${{ steps.commit.outputs.base }}
    steps:
      - uses: actions/checkout@v7

      # (LIB_CHECKOUT with its comment)

      - uses: actions/setup-node@v7
        with:
          node-version: 22

      # The four steps of today's release-pr.yml `prepare` job, from
      # "Guard (right branch, no failed check)" to "Commit the release branch",
      # copied with the edits listed below.
```

Copy the four steps (`.github/workflows/release-pr.yml`, job `prepare`, from `- name: Guard (right branch, no failed check)` to the end of `- name: Commit the release branch`), with the comment above the commit step, and edit:

1. Every `` `${process.env.GITHUB_WORKSPACE}/.github/workflows/lib` `` and `` `${ws}/.github/workflows/lib` `` becomes the `.repo-infra/.github/workflows/lib` form; `require(\`${ws}/.github/workflows/lib/commit.js\`)` becomes `require(\`${ws}/.repo-infra/.github/workflows/lib/commit.js\`)`.
2. The step "Compute the version and rewrite the files" gets `env: RELEASE_TYPE: ${{ inputs.release_type }}`, and `context.payload.inputs.release_type` becomes `process.env.RELEASE_TYPE`. Add the refusal before `versionLib.next`:

   ```js
   if (!['bugfix', 'feature', 'major'].includes(process.env.RELEASE_TYPE)) {
     core.setFailed(`release_type is ${process.env.RELEASE_TYPE}; it takes bugfix, feature or major.`);
     return;
   }
   ```
3. The step "Commit the release branch" gets `env: VERSION: ${{ steps.prepare.outputs.version }}`, and `const version = '${{ steps.prepare.outputs.version }}';` becomes `const version = process.env.VERSION;`.

`process.env.GITHUB_WORKFLOW_REF` in the guard names the caller's `release-pr.yml` in a called workflow, which is the workflow whose earlier attempts the guard must ignore; leave it.

- [ ] **Step 3: `.github/workflows/ri-release-finish.yml`**

```yaml
# repo-infra: ri-release-finish v2
#
# Purpose: Draft the release, mark the head, write the two required checks and open the release pull request (D28, D33).
# Choose: Always; release-pr.yml calls it after the build and the CI run.
# Supplies: release_assets and release_files in .github/repo-infra.json; the build's release-asset-* and release-files artifacts in the same run.
# Call:
#   finish:
#     needs: [prepare, build, test]
#     uses: oposs/repo-infra/.github/workflows/ri-release-finish.yml@v2
#     permissions:
#       contents: write
#       pull-requests: write
#       statuses: write
#       checks: write
#     with:
#       version: ${{ needs.prepare.outputs.version }}
#       date: ${{ needs.prepare.outputs.date }}
#       head: ${{ needs.prepare.outputs.head }}
#       base: ${{ needs.prepare.outputs.base }}

name: Finish the release

on:
  workflow_call:
    inputs:
      version:
        description: The version being released, from prepare.
        type: string
        required: true
      date:
        description: The release date, from prepare.
        type: string
        required: true
      head:
        description: The release branch head, from prepare.
        type: string
        required: true
      base:
        description: The dispatched main commit, from prepare.
        type: string
        required: true

permissions:
  contents: write
  pull-requests: write
  statuses: write
  checks: write

jobs:
  finish:
    name: Draft the release and open the pull request
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v7

      # (LIB_CHECKOUT with its comment)

      # (the two download-artifact steps and the github-script step of
      # today's `finish` job, copied with the edits below)
```

Edits to the script: the library paths as in Step 2; the step gets

```yaml
        env:
          VERSION: ${{ inputs.version }}
          DATE: ${{ inputs.date }}
          HEAD: ${{ inputs.head }}
          BASE: ${{ inputs.base }}
```

and the four `const` lines read `process.env.VERSION`, `process.env.DATE`, `process.env.HEAD` (as `prepared`) and `process.env.BASE`. The comment "A called workflow's jobs belong to this run" stays above the downloads: artifacts of the caller's `build` job are in the same run.

- [ ] **Step 4: `assets/callers/release-pr.yml`** (whole file)

Today's header comment of `release-pr.yml` minus the marker block, then:

```yaml
name: Create release PR
# The release-pr.yml of every repository (D28, D33). Copy it; a repository
# may add jobs between prepare and finish, and finish then needs them too.
# check reviews the structure: prepare and finish call repo-infra, build and
# test call this repository's own release-build.yml and ci.yml, and finish
# needs every other job.
#
# (the flow diagram and the paragraph on GITHUB_TOKEN from today's header)

on:
  workflow_dispatch:
    inputs:
      release_type:
        description: Release type
        required: true
        default: bugfix
        type: choice
        options:
          - bugfix
          - feature
          - major

concurrency:
  group: release
  cancel-in-progress: false

# Every job grants its own permissions; the workflow level stays read-only.
permissions:
  checks: read
  actions: read

jobs:
  prepare:
    uses: oposs/repo-infra/.github/workflows/ri-release-prepare.yml@v2
    permissions:
      contents: write
      pull-requests: read
      checks: read
      actions: write
    with:
      release_type: ${{ inputs.release_type }}

  # (today's comment above `build`)
  build:
    needs: prepare
    permissions:
      contents: read
    uses: ./.github/workflows/release-build.yml
    with:
      version: ${{ needs.prepare.outputs.version }}
      ref: ${{ needs.prepare.outputs.head }}
    secrets: inherit

  # (today's comment above `test`)
  test:
    needs: prepare
    permissions:
      contents: read
      pull-requests: read
      statuses: read
      checks: write
    uses: ./.github/workflows/ci.yml
    with:
      ref: ${{ needs.prepare.outputs.head }}
    secrets: inherit

  finish:
    needs: [prepare, build, test]
    uses: oposs/repo-infra/.github/workflows/ri-release-finish.yml@v2
    permissions:
      contents: write
      pull-requests: write
      statuses: write
      checks: write
    with:
      version: ${{ needs.prepare.outputs.version }}
      date: ${{ needs.prepare.outputs.date }}
      head: ${{ needs.prepare.outputs.head }}
      base: ${{ needs.prepare.outputs.base }}
```

repo-infra's `.github/workflows/release-pr.yml` becomes this file with `./.github/workflows/ri-release-prepare.yml` and `./.github/workflows/ri-release-finish.yml` (Task 12 adds the gate).

- [ ] **Step 5: One copy of the library**

```bash
cd /scratch/oetiker/claude-worktrees/repo-infra-release-pieces
diff -r skills/repo-infra/assets/pieces/workflow-lib/lib .github/workflows/lib   # no output
git rm -rq skills/repo-infra/assets/pieces/workflow-lib skills/repo-infra/assets/pieces/release-pr
python3 - <<'EOF'
import pathlib, re
for p in sorted(pathlib.Path(".github/workflows/lib").glob("*.js")):
    text = p.read_text(encoding="utf-8")
    # The marker and the header fields up to the first blank line: the
    # library is no longer a piece (D33).
    new = re.sub(r"\A// repo-infra: workflow-lib v\d+\n(?://.*\n)*\n", "", text, count=1)
    assert new != text, p
    p.write_text(new, encoding="utf-8")
EOF
grep -l 'repo-infra: workflow-lib' .github/workflows/lib/*.js   # prints nothing
```

Remove `workflow-lib` and `release-pr` from the manifest, run `make generations` and delete the `pieces/workflow-lib/` and `pieces/release-pr/` paths it reports as vanished, then run it again.

`tests/test_release_mode.py:test_each_term_of_the_skip_is_a_test_of_is_release_pr` reads `ROOT / ".github/workflows/lib/release.js"`; `tests/test_release_nfpm.py`'s `LIB` becomes `ROOT / ".github/workflows/lib"`. Add to `tests/test_pieces.py`:

```python
def test_the_library_is_one_copy_and_no_piece():
    root = ASSETS.parents[2]
    assert not (ASSETS / "pieces/workflow-lib").exists()
    for path in (root / ".github/workflows/lib").glob("*.js"):
        assert "repo-infra: workflow-lib" not in path.read_text(encoding="utf-8"), path.name
```

- [ ] **Step 6: `check` reviews `release-pr.yml` by structure**

```python
PREPARE, FINISH = "ri-release-prepare", "ri-release-finish"


def release_pr_problems(docs, pieces):
    """D33: release-pr.yml calls prepare and finish from repo-infra and the
    repository's own release-build.yml and ci.yml between them; finish needs
    every other job, so nothing a repository adds between them is skipped."""
    doc = docs.get("release-pr.yml")
    if not isinstance(doc, dict):
        return [("release-pr.yml", "not there; Create release PR is how a release starts. "
                                   "Copy assets/callers/release-pr.yml in the repo-infra skill")]
    all_jobs = jobs(doc)
    by_target = {}
    for job_id, job in all_jobs.items():
        by_target.setdefault(normal_uses(job.get("uses")), []).append(job_id)
    found = []
    for piece in (PREPARE, FINISH):
        if f"{piece}.yml" not in by_target:
            found.append(("release-pr.yml", f"calls no {piece}; copy "
                                            "assets/callers/release-pr.yml in the repo-infra "
                                            "skill"))
    for own in ("release-build.yml", "ci.yml"):
        if own not in by_target:
            found.append(("release-pr.yml", f"does not call {own}; the release pull request "
                                            "would open untested or unbuilt"))
    if found:
        return found
    prepare = by_target[f"{PREPARE}.yml"][0]
    finish = by_target[f"{FINISH}.yml"][0]
    for own in ("release-build.yml", "ci.yml"):
        for job_id in by_target[own]:
            if prepare not in needs(all_jobs[job_id]):
                found.append(("release-pr.yml", f"job {job_id} does not need {prepare}; it "
                                                "would build or test before the release "
                                                "branch exists"))
    missing = [j for j in all_jobs if j != finish and j not in needs(all_jobs[finish])]
    if missing:
        found.append(("release-pr.yml", f"{finish} does not need {', '.join(missing)}; it "
                                        "would open the pull request before they finished"))
    if not callers_event(doc, "workflow_dispatch"):
        found.append(("release-pr.yml", "has no workflow_dispatch trigger; nobody can start "
                                        "a release"))
    return found
```

where `callers_event(doc, event)` is `_event(doc, event)[0]`. Add `"release-pr.yml"` to `CORE_CALLERS` (`"Create release PR starts a release"`) and call `release_pr_problems` from `validate`; drop the `not there` branch of `release_pr_problems` since `CORE_CALLERS` reports the missing file (keep the function's first line `return []`).

Tests in `tests/test_callers.py`:

```python
RELEASE_PR = (ASSETS / "callers/release-pr.yml").read_text(encoding="utf-8")


def release_pr(text):
    return callers.release_pr_problems({"release-pr.yml": workflow.load(text)}, {})


def test_the_shipped_release_pr_has_no_problem():
    assert release_pr(RELEASE_PR) == []


def test_a_job_between_prepare_and_finish_that_finish_needs_is_fine():
    text = RELEASE_PR.replace(
        "  finish:\n    needs: [prepare, build, test]",
        "  gate:\n    needs: prepare\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - run: 'true'\n\n  finish:\n    needs: [prepare, build, test, gate]")
    assert release_pr(text) == []


def test_finish_that_does_not_need_an_added_job_is_a_problem():
    text = RELEASE_PR.replace(
        "  finish:\n", "  gate:\n    needs: prepare\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: 'true'\n\n  finish:\n")
    assert release_pr(text) == [("release-pr.yml", "finish does not need gate; it would "
                                 "open the pull request before they finished")]


def test_a_release_pr_without_ci_is_a_problem():
    text = RELEASE_PR.replace("uses: ./.github/workflows/ci.yml", "uses: ./.github/workflows/x.yml")
    assert ("release-pr.yml", "does not call ci.yml; the release pull request would open "
            "untested or unbuilt") in release_pr(text)


def test_this_repositorys_release_pr_has_no_problem():
    assert release_pr(own("release-pr.yml")) == []
```

- [ ] **Step 7: Run, regenerate, gate**

```bash
cd /scratch/oetiker/claude-worktrees/repo-infra-release-pieces
make generations && make catalogue
python3 -m pytest -q --basetemp=.pytest-tmp tests/test_release_pr.py tests/test_release_guard.py \
  tests/test_callers.py tests/test_pieces.py tests/test_self_check.py tests/test_release_mode.py \
  tests/test_release_nfpm.py tests/test_generations.py
make check
```

Expected: PASS. `make test-js` runs the library from `.github/workflows/lib/`, its only copy.

- [ ] **Step 8: Changelog and commit**

`### Changed`:

```markdown
- Create release PR is a short `release-pr.yml` that calls `ri-release-prepare` and `ri-release-finish` from repo-infra and the repository's own `release-build.yml` and `ci.yml` between them. A repository may add jobs between prepare and finish; `/repo-infra:check` reports a `finish` that does not need all of them. Copy it from `assets/callers/release-pr.yml`.
- `.github/workflows/lib/` is no longer installed in a repository; `/repo-infra:check` reports a copy as the v1 layout.
```

```bash
git add -A .github skills/repo-infra tests CHANGES.md
git commit -m "Split release-pr into prepare and finish pieces; one library (D33)

release-pr.yml passed secrets: inherit to the repository's own
release-build.yml and ci.yml, which a piece in oposs/repo-infra cannot
do for a repository of another organisation, and it could not know each
repository's permissions. The repository's release-pr.yml now wires
ri-release-prepare, its own build and CI, and ri-release-finish; check
reviews its structure, so repo-infra can add its gate. With release-pr
retired no byte piece needs the library: the copy in the store and the
markers of .github/workflows/lib go.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: `ri-ci-github-action` stops calling the consumer's `action-test.yml`

**Files:**
- Modify: `.github/workflows/ri-ci-github-action.yml`, `skills/repo-infra/scripts/repo_infra/callers.py`
- Test: `tests/test_github_action.py`, `tests/test_callers.py`

**Interfaces:**
- Produces: `ri-ci-github-action` has the jobs it has today minus `action-test`; `callers.action_test_problems(docs, pieces) -> [(file, detail)]`.

- [ ] **Step 1: Failing tests**

In `tests/test_github_action.py` (its `PIECE` already points at `.github/workflows/ri-ci-github-action.yml` since Task 2):

```python
def test_the_piece_calls_no_workflow_of_the_consumer():
    jobs = yaml.safe_load(PIECE.read_text(encoding="utf-8"))["jobs"]
    assert "action-test" not in jobs
    assert all("uses" not in job for job in jobs.values())


def test_the_call_snippet_passes_no_secrets():
    text = PIECE.read_text(encoding="utf-8")
    assert "secrets: inherit" not in text
```

In `tests/test_callers.py`:

```python
def test_a_ci_yml_that_calls_the_action_piece_must_call_action_test():
    ci = workflow.load(
        "jobs:\n  action:\n    uses: oposs/repo-infra/.github/workflows/"
        "ri-ci-github-action.yml@v2\n")
    assert callers.action_test_problems({"ci.yml": ci}) == [(
        "ci.yml", "ci.yml calls ri-ci-github-action and not ./.github/workflows/"
        "action-test.yml; the action's own test never runs. Add the job `action-test` "
        "from the catalogue entry of ri-ci-github-action")]


def test_a_ci_yml_that_calls_both_is_fine():
    ci = workflow.load(
        "jobs:\n  action:\n    uses: oposs/repo-infra/.github/workflows/"
        "ri-ci-github-action.yml@v2\n  action-test:\n"
        "    uses: ./.github/workflows/action-test.yml\n")
    assert callers.action_test_problems({"ci.yml": ci}) == []
```

Run them. Expected: FAIL.

- [ ] **Step 2: The piece**

Delete the job `action-test` and the comment block above it. The header becomes:

```yaml
# Supplies: action.yml, and .github/workflows/action-test.yml: the project's own test,
#   called from ci.yml with `ref` and `secrets: inherit` (D20, D33).
# Call:
#   action:
#     uses: oposs/repo-infra/.github/workflows/ri-ci-github-action.yml@v2
#     with:
#       ref: ${{ inputs.ref }}
#
# ci.yml also calls the project's own test, which stays in the repository:
#
#   action-test:
#     uses: ./.github/workflows/action-test.yml
#     with:
#       ref: ${{ inputs.ref }}
#     secrets: inherit
```

(The second snippet is a comment after the header block; the header parser stops at the blank `#` line, so `Call:` holds one job.)

- [ ] **Step 3: `callers.action_test_problems`**

```python
def action_test_problems(docs):
    """D33: a piece in oposs/repo-infra cannot call a workflow of the
    repository that calls it, so ci.yml calls action-test.yml itself."""
    ci = docs.get("ci.yml")
    if not isinstance(ci, dict):
        return []
    targets = {normal_uses(job.get("uses")) for job in jobs(ci).values()}
    if "ri-ci-github-action.yml" in targets and "action-test.yml" not in targets:
        return [("ci.yml", "ci.yml calls ri-ci-github-action and not ./.github/workflows/"
                           "action-test.yml; the action's own test never runs. Add the job "
                           "`action-test` from the catalogue entry of ri-ci-github-action")]
    return []
```

Called from `validate`. The `action-test.yml` the consumer calls keeps the D28 ref contract through `ref_contract_problems`, as today.

- [ ] **Step 4: Run, catalogue, gate, changelog, commit**

`make catalogue && python3 -m pytest -q --basetemp=.pytest-tmp tests/test_github_action.py tests/test_callers.py && make check`. Expected: PASS.

`### Changed`:

```markdown
- A GitHub Action's `ci.yml` calls its own `.github/workflows/action-test.yml` in a job `action-test`, next to `ri-ci-github-action`, which no longer calls it. `/repo-infra:check` reports a `ci.yml` that calls the piece without the test.
```

```bash
git add -A .github tests skills/repo-infra CHANGES.md
git commit -m "Let ci.yml call action-test.yml itself (D33)

ri-ci-github-action called the consumer's ./.github/workflows/action-test.yml
with secrets: inherit. Called from oposs/repo-infra, ./ does not name
the consumer's file (Task 1), and inherit does not cross organisations.
The piece keeps the manifest check; ci.yml calls the test.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: A `repository` input on every piece that checks out the source

**Files:**
- Modify: every `.github/workflows/ri-*.yml` of the groups `ci` and `release-build` (P12)
- Test: `tests/test_pieces.py`, `tests/test_release_homebrew.py`

**Interfaces:**
- Produces: on each such piece, the input

```yaml
      repository:
        description: The repository to check out; the calling repository unless set (D33).
        type: string
        required: false
        default: ${{ github.repository }}
```

Every `actions/checkout` of the source passes `repository: ${{ inputs.repository }}` and `ref: ${{ inputs.ref }}`. `ri-release-homebrew` builds the bottle `root-url` from `inputs.repository`.

- [ ] **Step 1: Failing tests** (append to `tests/test_pieces.py`)

```python
SOURCE = [p for p in REMOTE if p.group in ("ci", "release-build")]


@pytest.mark.parametrize("piece", SOURCE, ids=ids)
def test_a_source_piece_takes_repository_with_the_caller_as_default(piece):
    face = workflow.interface(doc_of(piece))
    assert face.inputs["repository"] == {
        "description": "The repository to check out; the calling repository unless set (D33).",
        "type": "string", "required": False, "default": "${{ github.repository }}"}


@pytest.mark.parametrize("piece", SOURCE, ids=ids)
def test_every_source_checkout_passes_repository_and_ref(piece):
    for job_id, job in doc_of(piece)["jobs"].items():
        for step in job.get("steps", []):
            if (str(step.get("uses", "")).startswith("actions/checkout@")
                    and step != LIB_CHECKOUT):
                assert step["with"]["repository"] == "${{ inputs.repository }}", job_id
                assert step["with"]["ref"] == "${{ inputs.ref }}", job_id


@pytest.mark.parametrize("piece", SOURCE, ids=ids)
def test_a_source_piece_names_no_repository_of_its_own(piece):
    text = piece.files[piece.target]
    code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    assert "GITHUB_REPOSITORY" not in code
    assert "github.repository" not in code.replace("default: ${{ github.repository }}", "")
    assert "context.repo" not in code
```

`workflow.interface` returns `default` as the raw string; check `tests/test_workflow.py` for how a `${{ }}` default reads and adjust the expected value to it.

Run. Expected: FAIL for every `ci` and `release-build` piece.

- [ ] **Step 2: Implement**

For each piece in `SOURCE`, add the input after `ref` and `repository: ${{ inputs.repository }}` to each source checkout (above its `ref:` line). Then:

```bash
cd /scratch/oetiker/claude-worktrees/repo-infra-release-pieces
grep -n 'GITHUB_REPOSITORY\|github\.repository\|context\.repo' \
  .github/workflows/ri-ci-*.yml .github/workflows/ri-release-*.yml | grep -v 'ri-release-prepare\|ri-release-finish\|ri-release-verdict\|ri-release-pr-current'
```

Each hit becomes the input. In `ri-release-homebrew.yml` the bottle step gets `REPOSITORY: ${{ inputs.repository }}` in its `env:` and

```yaml
            --root-url="https://github.com/$REPOSITORY/releases/download/v$VERSION" \
```

A `context.repo` in a `github-script` step of these pieces reads `process.env.REPOSITORY` (set in the step's `env:`) split at `/`. `ri-release-pr-current`, `ri-release-verdict`, `ri-changelog`, prepare and finish act on the calling repository by design and are in the `ci`/`release` groups only where they do: `ri-release-pr-current` is `ci` but checks out nothing it needs from another repository; exclude it from `SOURCE` explicitly (`p.name != "ri-release-pr-current"`) and say why in a comment: it marks the caller's own release pull requests.

- [ ] **Step 3: Test the homebrew url** (append to `tests/test_release_homebrew.py`)

```python
def test_the_bottle_root_url_names_the_repository_input():
    text = PIECE.read_text(encoding="utf-8")
    assert '--root-url="https://github.com/$REPOSITORY/releases/download/v$VERSION"' in text
    assert "REPOSITORY: ${{ inputs.repository }}" in text
```

- [ ] **Step 4: Run, catalogue, gate, changelog, commit**

`make catalogue && make check`. Expected: PASS.

`### New`:

```markdown
- Every CI and release build workflow takes a `repository` input, the repository to check out; it defaults to the calling repository. repo-infra's release gate uses it to build mtuspy.
```

```bash
git add -A .github tests skills/repo-infra/references/catalogue.md CHANGES.md
git commit -m "Give every source piece a repository input (D33)

The release gate runs mtuspy's CI and build pieces from repo-infra, so
the checkout and every URL a piece derives must name mtuspy, not the
repository the run belongs to. The input defaults to github.repository;
consumers leave it unset. ri-release-homebrew's bottle root-url reads it.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Moving `v2` with a GitHub App, and the rollback

**Files:**
- Modify: `.github/workflows/ri-publish-tag.yml`, `.github/workflows/lib/publish.js`, `.github/workflows/lib/publish.test.js`, `.github/workflows/release-publish.yml`, `.github/repo-infra.json`, `skills/repo-infra/references/examples/repo-infra/release-publish.yml` and `repo-infra.json` (equal to repo-infra's own), `skills/repo-infra/assets/manifest.json` (`actions`), `RELEASING.md`
- Test: `tests/test_publish.py`

**Interfaces:**
- Produces: `ri-publish-tag` secrets `app-id` and `app-private-key` (both `required: false`); job output `head` unchanged; a new step "Move the major tag" after "Tag and create the draft release". Library: `publish.majorTag(version) -> string` (`"v2"` for `"2.0.1"`), `publish.moveMajorTag(github, { owner, repo, version, tag, sha }) -> Promise<string>` (the notice text). Manifest `actions` gains `"actions/create-github-app-token": "<major>"`.

- [ ] **Step 1: Confirm the action's major**

```bash
gh api repos/actions/create-github-app-token/releases/latest --jq .tag_name
```

Use its major (for example `v2`) everywhere below as `<major>`.

- [ ] **Step 2: Failing library tests** (append to `.github/workflows/lib/publish.test.js`)

```js
test('majorTag: the major of a version', () => {
  assert.equal(majorTag('2.0.1'), 'v2');
  assert.equal(majorTag('10.3.0'), 'v10');
});

test('moveMajorTag updates the major tag to a new annotated tag', async () => {
  const calls = [];
  const github = { rest: { git: {
    createTag: async (a) => { calls.push(['createTag', a]); return { data: { sha: 't1' } }; },
    updateRef: async (a) => { calls.push(['updateRef', a]); return { data: {} }; },
    createRef: async () => { throw new Error('not expected'); },
  } } };
  const notice = await moveMajorTag(github, { owner: 'o', repo: 'r', version: '2.0.1', tag: 'v2.0.1', sha: 'c1' });
  assert.equal(notice, 'Moved v2 to v2.0.1.');
  assert.deepEqual(calls[0], ['createTag', { owner: 'o', repo: 'r', tag: 'v2',
    message: 'Update v2 to v2.0.1', object: 'c1', type: 'commit' }]);
  assert.deepEqual(calls[1], ['updateRef', { owner: 'o', repo: 'r', ref: 'tags/v2', sha: 't1', force: true }]);
});

test('moveMajorTag creates the major tag the first time', async () => {
  const calls = [];
  const github = { rest: { git: {
    createTag: async () => ({ data: { sha: 't1' } }),
    updateRef: async () => { const e = new Error('Reference does not exist'); e.status = 422; throw e; },
    createRef: async (a) => { calls.push(a); return { data: {} }; },
  } } };
  await moveMajorTag(github, { owner: 'o', repo: 'r', version: '2.0.0', tag: 'v2.0.0', sha: 'c1' });
  assert.deepEqual(calls, [{ owner: 'o', repo: 'r', ref: 'refs/tags/v2', sha: 't1' }]);
});

test('moveMajorTag names the ruleset when the move is refused', async () => {
  const github = { rest: { git: {
    createTag: async () => ({ data: { sha: 't1' } }),
    updateRef: async () => { const e = new Error('Repository rule violations found'); e.status = 422; throw e; },
    createRef: async () => { const e = new Error('Reference already exists'); e.status = 422; throw e; },
  } } };
  await assert.rejects(
    moveMajorTag(github, { owner: 'o', repo: 'r', version: '2.0.1', tag: 'v2.0.1', sha: 'c1' }),
    /v2 could not be moved to v2\.0\.1: Repository rule violations found\. A tag ruleset on v\* lets only its bypass list move it; pass app-id and app-private-key/);
});
```

Run `node --test .github/workflows/lib/publish.test.js`. Expected: FAIL.

- [ ] **Step 3: `publish.js`**

```js
function majorTag(version) {
  return `v${version.split('.')[0]}`;
}

// D33: moves the major tag consumers call, v2 for 2.0.1. The first release of
// a major creates it. A tag ruleset on v* (repo-infra has one) refuses the
// update unless the token belongs to its bypass list, the GitHub App.
async function moveMajorTag(github, { owner, repo, version, tag, sha }) {
  const major = majorTag(version);
  const { data: object } = await github.rest.git.createTag({
    owner, repo, tag: major, message: `Update ${major} to ${tag}`, object: sha, type: 'commit',
  });
  let updateError = null;
  try {
    await github.rest.git.updateRef({ owner, repo, ref: `tags/${major}`, sha: object.sha, force: true });
    return `Moved ${major} to ${tag}.`;
  } catch (error) {
    if (error.status !== 422) throw error;
    updateError = error;
  }
  try {
    await github.rest.git.createRef({ owner, repo, ref: `refs/tags/${major}`, sha: object.sha });
    return `Moved ${major} to ${tag}.`;
  } catch (error) {
    if (error.status !== 422) throw error;
    throw new Error(`${major} could not be moved to ${tag}: ${updateError.message}. A tag `
      + 'ruleset on v* lets only its bypass list move it; pass app-id and app-private-key '
      + 'to ri-publish-tag.');
  }
}
```

Export both.

- [ ] **Step 4: `ri-publish-tag.yml`**

Add under `on.workflow_call`:

```yaml
    secrets:
      app-id:
        description: A GitHub App's id; with app-private-key, the major tag is moved with the App's token, which a tag ruleset can let through.
        required: false
      app-private-key:
        description: The private key of the App named by app-id.
        required: false
```

In the job: `env: HAS_APP: ${{ secrets.app-id != '' && secrets.app-private-key != '' }}` (secrets cannot appear in a step's `if:`). In the script of "Tag and create the draft release", delete `moveMajor` and its call, and set the outputs as today. Add after that step:

```yaml
      # D33: an installation token lasts one hour, so it cannot be stored as
      # a secret, and a token handed over as a job output is redacted. It is
      # minted here, in the job that uses it.
      - id: app
        if: env.HAS_APP == 'true' && steps.publish.outputs.tag != ''
        uses: actions/create-github-app-token@<major>
        with:
          app-id: ${{ secrets.app-id }}
          private-key: ${{ secrets.app-private-key }}

      - name: Move the major tag
        if: steps.publish.outputs.tag != ''
        uses: actions/github-script@v9
        env:
          VERSION: ${{ steps.publish.outputs.version }}
          TAG: ${{ steps.publish.outputs.tag }}
          HEAD: ${{ steps.publish.outputs.head }}
        with:
          github-token: ${{ steps.app.outputs.token || github.token }}
          script: |
            const fs = require('fs');
            const ws = process.env.GITHUB_WORKSPACE;
            const config = JSON.parse(fs.readFileSync(`${ws}/.github/repo-infra.json`, 'utf8'));
            if (!config.moving_major_tag) return;
            const publishLib = require(`${ws}/.repo-infra/.github/workflows/lib/publish.js`);
            const { owner, repo } = context.repo;
            core.notice(await publishLib.moveMajorTag(github, {
              owner, repo, version: process.env.VERSION, tag: process.env.TAG,
              sha: process.env.HEAD,
            }));
```

On a run that publishes nothing the publish step returns before setting `tag`, so both steps skip, as `moveMajor` returned early before. A resumed run sets the outputs too (it repeated `moveMajor` before), so the move repeats harmlessly. Add `"actions/create-github-app-token": "<major>"` to the manifest `actions`; the Call: snippet of `ri-publish-tag` gains nothing (consumers pass no secret).

- [ ] **Step 5: repo-infra's caller and config**

`.github/workflows/release-publish.yml`, job `publish`:

```yaml
    secrets:
      app-id: ${{ secrets.RELEASE_APP_ID }}
      app-private-key: ${{ secrets.RELEASE_APP_PRIVATE_KEY }}
```

`.github/repo-infra.json`: `"moving_major_tag": true`. Copy both files to `skills/repo-infra/references/examples/repo-infra/`.

- [ ] **Step 6: Tests** (append to `tests/test_publish.py`)

```python
TAG_PIECE = ROOT / ".github/workflows/ri-publish-tag.yml"


def tag_job():
    return yaml.safe_load(TAG_PIECE.read_text(encoding="utf-8"))["jobs"]["publish"]


def test_the_major_tag_moves_with_the_app_token_when_one_is_passed():
    steps = tag_job()["steps"]
    names = [s.get("name") or s.get("id") or s.get("uses") for s in steps]
    assert names.index("Tag and create the draft release") < names.index("app") \
        < names.index("Move the major tag")
    move = next(s for s in steps if s.get("name") == "Move the major tag")
    assert move["with"]["github-token"] == "${{ steps.app.outputs.token || github.token }}"
    assert tag_job()["env"] == {
        "HAS_APP": "${{ secrets.app-id != '' && secrets.app-private-key != '' }}"}


def test_the_app_secrets_are_optional():
    face = workflow.interface(workflow.load(TAG_PIECE.read_text(encoding="utf-8")))
    assert {k: v["required"] for k, v in face.secrets.items()} == {
        "app-id": False, "app-private-key": False}


def test_repo_infra_moves_v2_with_its_app():
    publish = yaml.safe_load((ROOT / ".github/workflows/release-publish.yml")
                             .read_text(encoding="utf-8"))["jobs"]["publish"]
    assert publish["secrets"] == {
        "app-id": "${{ secrets.RELEASE_APP_ID }}",
        "app-private-key": "${{ secrets.RELEASE_APP_PRIVATE_KEY }}"}
    config = json.loads((ROOT / ".github/repo-infra.json").read_text(encoding="utf-8"))
    assert config["moving_major_tag"] is True
```

Any existing test in `tests/test_publish*.py` that ran the publish script and asserted the major tag move moves to the new step's script; `grep -n moveMajor tests/*.py` finds them.

- [ ] **Step 7: `RELEASING.md`**

Add a section after "When a release gets stuck":

```markdown
## The moving major tag v2

Repositories call repo-infra's workflows at `@v2`. Every release moves `v2`
to the release it publishes, with the token of the GitHub App in the
secrets `RELEASE_APP_ID` and `RELEASE_APP_PRIVATE_KEY`. A tag ruleset on
`v*` refuses every other update and every deletion; its bypass list holds
that App and the Repository admin role.

Before `v2` moves, Create release PR dispatches `gate-mtuspy.yml` on the
release branch, which builds mtuspy with the release's own workflows. The
release pull request does not open unless it succeeds.

### Rolling back a release

When a release breaks repositories that call it:

1. As a repository admin, point `v2` at the commit of the previous release
   tag:

   ```sh
   git fetch --tags origin
   git tag -f -a v2 -m "Roll v2 back to vX.Y.Z" vX.Y.Z^{commit}
   git push --force origin refs/tags/v2
   ```

2. Revert the defect on `main` and release again. The release moves `v2`
   forward to the fixed version.

Within `v2` a workflow may add an input with a default, an optional secret
or an output. Removing or renaming an input, secret, output or workflow,
changing an input's type, making an input or secret required, or asking
for more permissions waits for `v3`; `tests/test_v2_compat.py` refuses it.
```

- [ ] **Step 8: Run, gate, changelog, commit**

`make catalogue && node --test .github/workflows/lib/publish.test.js && make check`. Expected: PASS.

`### New`:

```markdown
- `ri-publish-tag` takes two optional secrets, `app-id` and `app-private-key`. When both are set it moves the major tag with the GitHub App's token, which a tag ruleset can let through; without them nothing changes. A refused move fails the run with "vN could not be moved to vX.Y.Z" and names the secrets.
```

```bash
git add -A .github skills/repo-infra tests RELEASING.md CHANGES.md
git commit -m "Move the major tag with a GitHub App token (D33)

repo-infra protects v* with a tag ruleset, so GITHUB_TOKEN cannot move
v2. ri-publish-tag mints an installation token in the same job when
app-id and app-private-key are passed: the token lasts an hour, so it
cannot be a stored secret, and a job output would be redacted. The move
is moveMajorTag in publish.js, tested; it names the ruleset when it is
refused. repo-infra sets moving_major_tag and passes its App.
RELEASING.md documents the rollback.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: `check` reviews remote calls and reports the v1 layout

**Files:**
- Modify: `skills/repo-infra/scripts/repo_infra/callers.py`, `skills/repo-infra/scripts/repo_infra/check.py`
- Test: `tests/test_callers.py`, `tests/test_check.py`, `tests/test_self_check.py`

**Interfaces:**
- Consumes: `pieces.HOME_REPO`, `pieces.MAJOR`, `Piece.remote`, `Piece.uses` (Task 2); `callers.normal_uses` (Task 4); `check.is_home` (Task 2).
- Produces: `callers.home_call(uses) -> (file, ref) | None`; `callers.target_doc(uses, docs, remote_docs) -> (file, doc) | (None, None)`; `callers.validate(docs, pieces, assets=ASSETS, home=False)`; `check.RETIRED`; `check.layout_items(repo_root, pieces) -> [Item]`.

Rules (spec, "check"):

| Finding | Where | Detail text |
|---|---|---|
| a call `oposs/repo-infra/.github/workflows/<f>@<ref>` with `<ref>` other than `v2` | consumer | `job <id> calls <uses>; call repo-infra's pieces at @v2, the tag every release moves (D33)` |
| such a call naming a file that is not a remote piece | consumer and home | `job <id> calls <uses>, which is not a piece of repo-infra` |
| a remote call in repo-infra itself | home | `job <id> calls <uses>; repo-infra calls its own pieces through ./ so a pull request runs the pieces it changes (D33)` |
| a local call `./.github/workflows/<f>` where `<f>` is a remote piece | consumer | `job <id> calls <uses>, a copy of the piece (v1 layout); call <piece.uses> and run apply to migrate (D33)` |
| `secrets: inherit` on a remote call | consumer | `job <id> passes secrets: inherit to <uses>; GitHub does not pass inherited secrets to a workflow of another organisation. Pass each secret by name` |
| an input the piece does not declare, a required input or a `required: true` secret missing | consumer | as `call_problems` says today, with the piece's interface from the installed plugin |
| a local `.github/workflows/<name>.yml` of a remote piece | consumer | `pieces` row `<name>`, state `outdated`: `.github/workflows/<name>.yml is a copy (v1 layout); repositories call <uses>. Run apply to migrate (D33)` |
| `.github/workflows/lib/` | consumer | `pieces` row `workflow-lib`, state `outdated`: `.github/workflows/lib/ is a copy of the library (v1 layout); the pieces load it from repo-infra. Run apply to migrate (D33)` |
| `.github/workflows/changelog.yml` or `release-pr.yml` whose first marker names `changelog` or `release-pr`, `.github/workflows/ri-ci-lib.yml` | consumer | `pieces` row of that name, state `outdated`: `<path> is the v1 <name> piece; it is a caller now. Run apply to migrate (D33)` |

- [ ] **Step 1: Failing tests** in `tests/test_callers.py`

```python
from repo_infra.pieces import load_pieces as load_real

REAL = load_real()
V2 = "oposs/repo-infra/.github/workflows/{}.yml@v2"


def consumer(ci_jobs, files=None):
    """A consumer whose ci.yml holds `ci_jobs` (text under jobs:), validated
    against the real pieces."""
    text = ("on:\n  push:\n    branches: [main]\n  pull_request:\n    branches: [main]\n"
            "  workflow_call:\n    inputs:\n      ref:\n        description: x\n"
            "        type: string\n        required: false\n        default: ''\n"
            "permissions:\n  contents: read\njobs:\n" + ci_jobs)
    docs = {"ci.yml": workflow.load(text), **(files or {})}
    return [i.detail for i in callers.validate(docs, REAL) if i.name == "ci.yml"]


def job(uses, extra=""):
    return (f"  rust:\n    {SKIP_IF}\n    uses: {uses}\n    with:\n"
            f"      ref: ${{{{ inputs.ref }}}}\n{extra}")


@pytest.mark.parametrize("ref", ["main", "v2.0.0", "V2", "v1"])
def test_a_piece_called_at_another_ref_is_a_problem(ref):
    uses = f"oposs/repo-infra/.github/workflows/ri-ci-rust.yml@{ref}"
    assert (f"job rust calls {uses}; call repo-infra's pieces at @v2, the tag every "
            "release moves (D33)") in consumer(job(uses))


def test_a_piece_called_at_v2_is_fine():
    assert not [d for d in consumer(job(V2.format("ri-ci-rust"))) if "job rust" in d]


def test_a_call_to_a_file_that_is_no_piece_is_a_problem():
    uses = V2.format("ri-nothing")
    assert f"job rust calls {uses}, which is not a piece of repo-infra" in consumer(job(uses))


def test_a_local_call_to_a_remote_piece_is_the_v1_layout():
    found = consumer(job("./.github/workflows/ri-ci-rust.yml"))
    assert ("job rust calls ./.github/workflows/ri-ci-rust.yml, a copy of the piece (v1 "
            f"layout); call {V2.format('ri-ci-rust')} and run apply to migrate (D33)") in found


def test_inherit_on_a_remote_call_is_a_problem():
    found = consumer(job(V2.format("ri-ci-rust"), "    secrets: inherit\n"))
    assert (f"job rust passes secrets: inherit to {V2.format('ri-ci-rust')}; GitHub does not "
            "pass inherited secrets to a workflow of another organisation. Pass each secret "
            "by name") in found


def test_an_input_the_remote_piece_lacks_is_a_problem():
    found = consumer(job(V2.format("ri-ci-rust"), "      nonsense: 1\n"))
    assert ("job rust calls ri-ci-rust.yml with the input nonsense, which ri-ci-rust.yml "
            "does not declare") in found


def test_a_remote_call_in_repo_infra_itself_is_a_problem():
    text = own("ci.yml").replace("uses: ./.github/workflows/ri-ci-python.yml",
                                 "uses: " + V2.format("ri-ci-python"))
    docs = callers.read_workflows(ROOT)
    docs["ci.yml"] = workflow.load(text)
    found = [i.detail for i in callers.validate(docs, REAL, home=True)]
    assert (f"job python calls {V2.format('ri-ci-python')}; repo-infra calls its own pieces "
            "through ./ so a pull request runs the pieces it changes (D33)") in found


def test_permissions_of_a_remote_call_are_checked_against_the_piece():
    text = job(V2.format("ri-release-pr-current")).replace("  rust:", "  current:")
    found = consumer(text)
    assert any(d.startswith("job current declares no permissions;")
               or "needs checks: write" in d for d in found)
```

`ROOT` is the repository root (`REPO` in this file already; use it). `own(name)` exists in the file.

In `tests/test_check.py`:

```python
from repo_infra.check import layout_items
from repo_infra.pieces import load_pieces as load_real


def test_a_copied_piece_and_the_library_are_the_v1_layout(tmp_path):
    install(tmp_path, ".github/workflows/ri-ci-rust.yml", "# repo-infra: ri-ci-rust v1\n")
    install(tmp_path, ".github/workflows/lib/release.js", "// repo-infra: workflow-lib v9\n")
    install(tmp_path, ".github/workflows/changelog.yml", "name: Changelog\n# repo-infra: changelog v6\n")
    found = {(i.name, i.state): i.detail for i in layout_items(tmp_path, load_real())}
    assert found[("ri-ci-rust", "outdated")] == (
        ".github/workflows/ri-ci-rust.yml is a copy (v1 layout); repositories call "
        "oposs/repo-infra/.github/workflows/ri-ci-rust.yml@v2. Run apply to migrate (D33)")
    assert found[("workflow-lib", "outdated")].startswith(
        ".github/workflows/lib/ is a copy of the library (v1 layout)")
    assert found[("changelog", "outdated")] == (
        ".github/workflows/changelog.yml is the v1 changelog piece; it is a caller now. "
        "Run apply to migrate (D33)")


def test_a_v2_changelog_caller_is_not_the_v1_layout(tmp_path):
    install(tmp_path, ".github/workflows/changelog.yml",
            (ASSETS / "callers/changelog.yml").read_text(encoding="utf-8"))
    assert layout_items(tmp_path, load_real()) == []


def test_repo_infra_itself_has_no_v1_layout():
    root = pathlib.Path(__file__).resolve().parents[1]
    assert check.is_home(root)
    assert [i for i in check.run(root, CONFORMING) if "v1 layout" in i.detail
            or "v1 " in i.detail] == []


def test_the_retired_markers_are_not_reported_as_unknown(tmp_path):
    install(tmp_path, ".github/workflows/release-pr.yml",
            "name: Create release PR\n# repo-infra: release-pr v6\n")
    assert [i for i in check.unknown_items(tmp_path, load_real())] == []
```

(`ASSETS` in `tests/test_check.py` is the real assets folder; define it next to the imports if missing. `CONFORMING` exists in the file.)

Run: `python3 -m pytest -q --basetemp=.pytest-tmp tests/test_callers.py tests/test_check.py`. Expected: FAIL.

- [ ] **Step 2: `callers.py`**

```python
from .pieces import ASSETS, HOME_REPO, MAJOR

_HOME_CALL = re.compile(r"^" + re.escape(HOME_REPO) + r"/\.github/workflows/([^@\s]+)(?:@(\S*))?$")


def home_call(uses):
    """(file, ref) for a call to a workflow of repo-infra, else None. A call
    without @ref is returned with ref None; GitHub refuses it."""
    if not isinstance(uses, str):
        return None
    match = _HOME_CALL.match(uses.strip())
    return (match[1], match[2]) if match else None


def target_doc(uses, docs, remote_docs):
    """The called file and its workflow: a local file, or a remote piece read
    from the installed plugin (D33)."""
    local = local_target(uses)
    if local is not None:
        return local, docs.get(local)
    called = home_call(uses)
    if called is not None:
        return called[0], remote_docs.get(called[0])
    return None, None
```

Replace Task 4's `normal_uses` body with one that uses `home_call`. `calls(docs, target)` matches `normal_uses(job.get("uses")) == target`, so a remote call counts as calling the piece's file; `core_call_items` (Task 2) then sees consumer calls.

`call_problems(job_id, job, docs)` takes the already-resolved `(called, target)`: change its signature to `call_problems(job_id, job, called, target, remote=False)` and update its two callers (`validate`, `tests/test_pieces.py`'s `test_the_call_snippet_calls_this_piece_correctly`, which passes `file, doc_of(piece)`). When `remote` is true and `job.get("secrets") == "inherit"`, return the inherit problem instead of skipping the secrets check, then check required secrets as for a dict.

`needed(name, docs)` and `permission_problems(docs)` resolve a call through `target_doc(job.get("uses"), docs, remote_docs)`; add a `remote_docs` parameter (default `{}`) to both and pass it through `needed`'s recursion. `ref_passing_problems(docs)` likewise takes `remote_docs` and uses `target_doc`.

In `validate(docs, pieces, assets=ASSETS, home=False)`:

```python
    remote_docs = {pathlib.PurePosixPath(p.target).name: workflow.load(p.files[p.target])
                   for p in pieces.values() if p.remote}
    remote_files = set(remote_docs)
    ...
    for name, doc in docs.items():
        for job_id, job in jobs(doc).items():
            uses = job.get("uses")
            called = home_call(uses)
            if called is not None:
                file, ref = called
                if home:
                    items.append(Item("callers", name, "problem",
                                      f"job {job_id} calls {uses}; repo-infra calls its own "
                                      "pieces through ./ so a pull request runs the pieces it "
                                      "changes (D33)"))
                elif file not in remote_files:
                    items.append(Item("callers", name, "problem",
                                      f"job {job_id} calls {uses}, which is not a piece of "
                                      "repo-infra"))
                    continue
                elif ref != MAJOR:
                    items.append(Item("callers", name, "problem",
                                      f"job {job_id} calls {uses}; call repo-infra's pieces at "
                                      f"@{MAJOR}, the tag every release moves (D33)"))
                items += [Item("callers", name, "problem", p) for p in call_problems(
                    job_id, job, file, remote_docs.get(file), remote=True)]
            elif local_target(uses):
                file = local_target(uses)
                if not home and file in remote_files:
                    piece = next(p for p in pieces.values()
                                 if p.remote and p.target.endswith("/" + file))
                    items.append(Item("callers", name, "problem",
                                      f"job {job_id} calls {uses}, a copy of the piece (v1 "
                                      f"layout); call {piece.uses} and run apply to migrate "
                                      "(D33)"))
                    continue
                items += [Item("callers", name, "problem", p)
                          for p in call_problems(job_id, job, file, docs.get(file))]
```

The old `_REMOTE` branch ("every workflow stays local (D30)") is deleted (P9). The "installed and no workflow calls it" rule keeps `piece_files` of byte workflow pieces only (none ship after Task 5; the fake stores still have them). Pass `remote_docs` to `permission_problems`, `ref_passing_problems` and `needed`. `catalogue.entry` calls `callers.needed(file, {file: doc})`, which still works.

- [ ] **Step 3: `check.py`**

```python
# D33: pieces that left the store, and how a consumer's copy of each is found.
RETIRED = {"changelog": ".github/workflows/changelog.yml",
           "release-pr": ".github/workflows/release-pr.yml",
           "ri-ci-lib": ".github/workflows/ri-ci-lib.yml"}


def layout_items(repo_root, pieces):
    """The files of the v1 layout (D30) in a consumer (D33)."""
    root = pathlib.Path(repo_root)
    items = []
    for name, piece in sorted(pieces.items()):
        if piece.remote and (root / piece.target).is_file():
            items.append(Item("pieces", name, "outdated",
                              f"{piece.target} is a copy (v1 layout); repositories call "
                              f"{piece.uses}. Run apply to migrate (D33)"))
    if (root / ".github/workflows/lib").is_dir():
        items.append(Item("pieces", "workflow-lib", "outdated",
                          ".github/workflows/lib/ is a copy of the library (v1 layout); the "
                          "pieces load it from repo-infra. Run apply to migrate (D33)"))
    for name, path in RETIRED.items():
        target = root / path
        if not target.is_file():
            continue
        markers = parse_markers(target.read_text(encoding="utf-8", errors="replace"))
        if name == "ri-ci-lib" or (markers and markers[0].asset == name):
            items.append(Item("pieces", name, "outdated",
                              f"{path} is the v1 {name} piece; it is a caller now. Run apply "
                              "to migrate (D33)"))
    return items
```

For `ri-ci-lib` say "it is gone" instead of "a caller now": write the detail as `f"{path} is the v1 {name} piece; " + ("repositories no longer test a library of their own" if name == "ri-ci-lib" else "it is a caller now") + ". Run apply to migrate (D33)"`, and adjust nothing else.

`unknown_items` skips a marker whose asset is in `RETIRED` or is `workflow-lib`. `run`:

```python
def run(repo_root, facts, assets=ASSETS):
    pieces = load_pieces(assets)
    docs = callers.read_workflows(repo_root)
    home = is_home(repo_root)
    return (piece_items(repo_root, pieces, load_published(assets))
            + ([] if home else layout_items(repo_root, pieces))
            + core_call_items(docs, pieces)
            + callers.validate(docs, pieces, assets, home=home)
            + config_items(repo_root, docs)
            + path_filter_items(docs)
            + classify_remote(facts))
```

`cli.apply_command` calls `callers.validate(docs, pieces, ASSETS, home=checking.is_home(args.root))`.

- [ ] **Step 4: The mtuspy example test**

`tests/test_callers.py:test_the_mtuspy_example_callers_have_no_problem` reads the example's callers alone (no copied pieces) and validates with `home=False`; it stays red until Task 11 writes the v2 example. Mark it `@pytest.mark.xfail(strict=True, reason="the v2 example arrives in Task 11")` in this task; Task 11 removes the mark.

- [ ] **Step 5: Run, gate, changelog, commit**

`python3 -m pytest -q --basetemp=.pytest-tmp tests/test_callers.py tests/test_check.py tests/test_self_check.py tests/test_permissions.py tests/test_cli.py && make check`. Expected: PASS.

Task 1's `vars` result: if `vars.PROBE_VAR` came back empty, stop here and ask the owner how `ri-publish-gitea` gets `GITEA_PACKAGE_USER` before going on.

`### Changed`:

```markdown
- `/repo-infra:check` expects every call of a repo-infra workflow to read `uses: oposs/repo-infra/.github/workflows/<piece>.yml@v2`, with each secret passed by name. It reports another ref, `secrets: inherit` on such a call, an input the workflow does not declare and a required input or secret left out, reading the workflows from the installed plugin.
- `/repo-infra:check` reports copies of the workflows, `.github/workflows/lib/`, and the old `changelog.yml` and `release-pr.yml` as the v1 layout, and says to run `apply`.
```

```bash
git add -A skills/repo-infra tests CHANGES.md
git commit -m "Review remote calls and report the v1 layout in check (D33)

A consumer calls each piece at oposs/repo-infra/.github/workflows/
<piece>.yml@v2; check reads the interfaces from the pieces in the
installed plugin and holds each call to them, the ref to v2, and the
secrets to named ones, since inherit does not cross organisations.
Copied pieces, the library and the v1 changelog and release-pr files
are findings that send the repository to apply. repo-infra itself is
recognised by its asset store and calls its pieces through ./.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: `apply` writes callers and fragments, never pieces, and migrates v1

**Files:**
- Create: `skills/repo-infra/scripts/repo_infra/migrate.py`, `tests/test_migrate.py`
- Modify: `skills/repo-infra/scripts/repo_infra/cli.py`, `skills/repo-infra/scripts/repo_infra/apply.py`
- Test: `tests/test_apply_pieces.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `check.layout_items`, `check.RETIRED`, `check.is_home` (Task 9); `Piece.remote`, `Piece.uses`; `assets/callers/ci-passed.yml`, `changelog.yml`, `release-pr.yml`.
- Produces: `migrate.rewrite_uses(text, remote_files) -> str`; `migrate.name_secrets(text, secrets_of) -> str` where `secrets_of` maps a piece file name to the list of secret names its interface declares; `migrate.job_block(text, job_id) -> (start, end) | None` (line indices, the job's own comment lines above it included); `migrate.drop_job(text, job_id) -> str`; `migrate.set_ci_passed(text, pattern_text) -> str`; `migrate.migrate(repo_root, pieces, assets) -> list[str]` (paths written or removed); `apply.MIGRATE_SUBJECT = "Migrate to the repo-infra v2 layout"`.

`migrate(repo_root, pieces, assets)`:

1. Removes every `.github/workflows/<file>` that is a remote piece, `.github/workflows/ri-ci-lib.yml`, and `.github/workflows/lib/`.
2. Writes `.github/workflows/changelog.yml` and `.github/workflows/release-pr.yml` from `assets/callers/`.
3. In every other `.github/workflows/*.yml`: `rewrite_uses`, then `name_secrets`.
4. In `ci.yml`: drops the job that calls `ri-ci-lib` (and its id from every `needs:`), replaces `ci-passed` and inserts `release-verdict` (`set_ci_passed`), and when the file calls `ri-ci-github-action` without `action-test.yml`, appends an `action-test` job before `ci-passed`.

- [ ] **Step 1: Failing tests** `tests/test_migrate.py`

```python
"""apply's migration from the v1 layout (D30) to remote pieces (D33)."""

import pathlib

from piecekit import SKIP_IF

from repo_infra import callers, migrate, workflow
from repo_infra.pieces import load_pieces

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
V2 = "oposs/repo-infra/.github/workflows/{}.yml@v2"
REMOTE = {f"{p.name}.yml" for p in load_pieces().values() if p.remote}

V1_CI = (ROOT / "skills/repo-infra/references/examples/mtuspy/ci.yml").read_text(encoding="utf-8")


def test_rewrite_uses_turns_local_piece_calls_remote_and_keeps_the_rest():
    text = ("jobs:\n  a:\n    uses: ./.github/workflows/ri-ci-rust.yml\n"
            "  b:\n    uses: './.github/workflows/ri-ci-man.yml'\n"
            "  c:\n    uses: ./.github/workflows/action-test.yml\n"
            "  # uses: ./.github/workflows/ri-ci-rust.yml in a comment stays\n")
    out = migrate.rewrite_uses(text, REMOTE)
    assert f"    uses: {V2.format('ri-ci-rust')}\n" in out
    assert f"    uses: {V2.format('ri-ci-man')}\n" in out
    assert "    uses: ./.github/workflows/action-test.yml\n" in out
    assert "  # uses: ./.github/workflows/ri-ci-rust.yml in a comment stays\n" in out


def test_name_secrets_replaces_inherit_on_remote_calls_only():
    text = (f"jobs:\n  gitea:\n    uses: {V2.format('ri-publish-gitea')}\n"
            "    secrets: inherit\n"
            "  build:\n    uses: ./.github/workflows/release-build.yml\n    secrets: inherit\n")
    out = migrate.name_secrets(text, {"ri-publish-gitea.yml": ["GITEA_PACKAGE_TOKEN"]})
    assert ("    secrets:\n      GITEA_PACKAGE_TOKEN: ${{ secrets.GITEA_PACKAGE_TOKEN }}\n"
            in out)
    assert "  build:\n    uses: ./.github/workflows/release-build.yml\n    secrets: inherit\n" in out


def test_name_secrets_drops_inherit_when_the_piece_declares_none():
    text = f"jobs:\n  rust:\n    uses: {V2.format('ri-ci-rust')}\n    secrets: inherit\n"
    assert migrate.name_secrets(text, {"ri-ci-rust.yml": []}) == (
        f"jobs:\n  rust:\n    uses: {V2.format('ri-ci-rust')}\n")


def test_job_block_includes_the_jobs_own_comments_and_stops_at_the_next_job():
    text = "jobs:\n  a:\n    run: x\n\n  # about b\n  b:\n    run: y\n  c:\n    run: z\n"
    start, end = migrate.job_block(text, "b")
    assert text.splitlines()[start:end] == ["  # about b", "  b:", "    run: y"]


def test_set_ci_passed_replaces_only_ci_passed_and_inserts_the_verdict_once():
    pattern = (ASSETS / "callers/ci-passed.yml").read_text(encoding="utf-8")
    text = ("jobs:\n  a:\n    run: x\n\n  ci-passed:\n    if: always()\n    needs: [a, b]\n"
            "    runs-on: ubuntu-latest\n    steps:\n      - run: old\n\n"
            "  # mine, after ci-passed\n  b:\n    run: y\n")
    out = migrate.set_ci_passed(text, pattern)
    doc = workflow.load(out)
    assert list(callers.jobs(doc)) == ["a", "release-verdict", "ci-passed", "b"]
    assert callers.needs(callers.jobs(doc)["ci-passed"]) == ["a", "b", "release-verdict"]
    assert "  # mine, after ci-passed\n  b:\n    run: y\n" in out
    assert "run: old" not in out
    assert migrate.set_ci_passed(out, pattern) == out


def test_the_mtuspy_v1_ci_migrates_to_a_ci_check_accepts():
    pattern = (ASSETS / "callers/ci-passed.yml").read_text(encoding="utf-8")
    out = migrate.set_ci_passed(migrate.drop_job(migrate.rewrite_uses(V1_CI, REMOTE), "lib"),
                                pattern)
    doc = workflow.load(out)
    assert "lib" not in callers.jobs(doc)
    found = [i.detail for i in callers.validate({"ci.yml": doc}, load_pieces())
             if i.name == "ci.yml"]
    assert found == []
```

`V1_CI` is the mtuspy example as it is before Task 11 (v1). Task 11 rewrites the example; this test then reads a frozen copy: in this task copy the file to `tests/fixtures/v1/mtuspy-ci.yml` and read that instead.

Run: `python3 -m pytest -q --basetemp=.pytest-tmp tests/test_migrate.py`. Expected: FAIL, no module `migrate`.

- [ ] **Step 2: `migrate.py`**

```python
"""apply's migration from the v1 layout (copied pieces, D30) to remote pieces
(D33): text rewrites that keep every line they do not need to change, so
the pull request shows exactly the migration.
"""

import json
import pathlib
import re
import shutil

from . import callers, workflow
from .pieces import HOME_REPO, MAJOR

WORKFLOWS = ".github/workflows"
_LOCAL = re.compile(r"^(?P<lead>[ \t]*(?:-[ \t]+)?uses:[ \t]*)(?P<q>['\"]?)\./\.github/"
                    r"workflows/(?P<file>[^\s'\"#]+)(?P=q)(?P<tail>[ \t]*(?:#.*)?)$")
_JOB = re.compile(r"^  ([A-Za-z_][\w-]*):\s*(?:#.*)?$")


def rewrite_uses(text, remote_files):
    out = []
    for line in text.split("\n"):
        match = _LOCAL.match(line)
        if match and match["file"] in remote_files:
            line = (f"{match['lead']}{HOME_REPO}/{WORKFLOWS}/{match['file']}@{MAJOR}"
                    f"{match['tail']}")
        out.append(line)
    return "\n".join(out)


def _jobs_start(lines):
    return next((i + 1 for i, line in enumerate(lines) if line.rstrip() == "jobs:"), None)


def job_block(text, job_id):
    """(start, end) line indices of job `job_id` under `jobs:`, with the
    comment lines directly above it, or None."""
    lines = text.split("\n")
    first = _jobs_start(lines)
    if first is None:
        return None
    key = next((i for i in range(first, len(lines))
                if (m := _JOB.match(lines[i])) and m[1] == job_id), None)
    if key is None:
        return None
    start = key
    while start - 1 >= first and lines[start - 1].startswith("  #"):
        start -= 1
    end = key + 1
    while end < len(lines) and not (_JOB.match(lines[end]) or lines[end].startswith("  #")
                                    or (lines[end] and not lines[end].startswith(" "))):
        end += 1
    while end > key + 1 and lines[end - 1].strip() == "":
        end -= 1
    return start, end


def _remove_from_needs(text, job_id):
    def edit(match):
        names = [n.strip() for n in match[2].split(",") if n.strip() and n.strip() != job_id]
        return f"{match[1]}[{', '.join(names)}]"
    text = re.sub(r"^(\s+needs:\s*)\[([^\]]*)\]", edit, text, flags=re.M)
    return re.sub(rf"^(\s+)needs:\s*{re.escape(job_id)}\s*\n", "", text, flags=re.M)


def drop_job(text, job_id):
    block = job_block(text, job_id)
    if block is None:
        return text
    lines = text.split("\n")
    start, end = block
    while end < len(lines) and lines[end].strip() == "":
        end += 1
    return _remove_from_needs("\n".join(lines[:start] + lines[end:]), job_id)


def name_secrets(text, secrets_of):
    lines = text.split("\n")
    out, current = [], None
    for line in lines:
        job = _JOB.match(line)
        if job:
            current = None
        uses = re.match(r"^    uses:\s*(\S+)", line)
        if uses:
            called = callers.home_call(uses[1])
            current = called[0] if called else None
        if current is not None and line.strip() == "secrets: inherit" and line.startswith("    s"):
            names = secrets_of.get(current, [])
            if names:
                out.append("    secrets:")
                out += [f"      {n}: ${{{{ secrets.{n} }}}}" for n in names]
            continue
        out.append(line)
    return "\n".join(out)


def _pattern_blocks(pattern_text):
    lines = pattern_text.split("\n")
    blocks = {}
    for job_id in ("release-verdict", "ci-passed"):
        start, end = job_block(pattern_text, job_id)
        blocks[job_id] = lines[start:end]
    return blocks


def set_ci_passed(text, pattern_text):
    """ci-passed as the pattern has it, needing every other job, with
    release-verdict directly above it. Idempotent."""
    blocks = _pattern_blocks(pattern_text)
    text = drop_job(text, "release-verdict")
    lines = text.split("\n")
    block = job_block(text, "ci-passed")
    doc = workflow.load(text)
    others = [j for j in callers.jobs(doc) if j not in ("ci-passed", "release-verdict")]
    passed = [line if not line.startswith("    needs:")
              else f"    needs: [{', '.join(others + ['release-verdict'])}]"
              for line in blocks["ci-passed"]]
    new = blocks["release-verdict"] + [""] + passed
    if block is None:
        return text.rstrip("\n") + "\n\n" + "\n".join(new) + "\n"
    start, end = block
    return "\n".join(lines[:start] + new + lines[end:])


def migrate(repo_root, pieces, assets):
    root = pathlib.Path(repo_root)
    folder = root / WORKFLOWS
    remote = {pathlib.PurePosixPath(p.target).name: p for p in pieces.values() if p.remote}
    touched = []
    for file in sorted(set(remote) | {"ri-ci-lib.yml"}):
        if (folder / file).is_file():
            (folder / file).unlink()
            touched.append(f"{WORKFLOWS}/{file}")
    if (folder / "lib").is_dir():
        touched += [f"{WORKFLOWS}/lib/{p.name}" for p in sorted((folder / "lib").iterdir())]
        shutil.rmtree(folder / "lib")
    callers_dir = pathlib.Path(assets) / "callers"
    for name in ("changelog.yml", "release-pr.yml"):
        (folder / name).write_text((callers_dir / name).read_text(encoding="utf-8"),
                                   encoding="utf-8")
        touched.append(f"{WORKFLOWS}/{name}")
    secrets_of = {file: list(workflow.interface(workflow.load(p.files[p.target])).secrets)
                  for file, p in remote.items()}
    pattern = (callers_dir / "ci-passed.yml").read_text(encoding="utf-8")
    for path in sorted(folder.glob("*.yml")):
        if path.name in ("changelog.yml", "release-pr.yml"):
            continue
        text = path.read_text(encoding="utf-8")
        new = name_secrets(rewrite_uses(text, set(remote)), secrets_of)
        if path.name == "ci.yml":
            doc = workflow.load(new)
            lib = [j for j, job in callers.jobs(doc).items()
                   if callers.normal_uses(job.get("uses")) == "ri-ci-lib.yml"]
            for job_id in lib:
                new = drop_job(new, job_id)
            targets = {callers.normal_uses(j.get("uses"))
                       for j in callers.jobs(workflow.load(new)).values()}
            if "ri-ci-github-action.yml" in targets and "action-test.yml" not in targets:
                new = _add_action_test(new)
            new = set_ci_passed(new, pattern)
        if new != text:
            path.write_text(new, encoding="utf-8")
            touched.append(f"{WORKFLOWS}/{path.name}")
    return touched
```

`_add_action_test(text)` inserts, directly above the `ci-passed` block (or at the end when there is none):

```python
ACTION_TEST = """  action-test:
    {skip}
    uses: ./.github/workflows/action-test.yml
    with:
      ref: ${{{{ inputs.ref }}}}
    secrets: inherit
"""
```

with `skip` the `if:` line of `assets/callers/release-pr-skip.yml`, and adds a test for it in `tests/test_migrate.py` (a v1 `ci.yml` calling `ri-ci-github-action` comes out with exactly one `action-test` job that `callers.action_test_problems` accepts).

The test `migrate.set_ci_passed(out, pattern) == out` holds `set_ci_passed` idempotent: it drops an existing `release-verdict` before inserting the pattern's.

- [ ] **Step 3: `apply` and `cli`**

In `cli.apply_command`:

- `--item <name>` for a remote piece refuses: `ApplyError(f"{name} is called, not installed (D33): add its Call: from the catalogue to a caller, as `uses: {piece.uses}`")`.
- Before `_pending`, when `not checking.is_home(args.root)` and `checking.layout_items(args.root, pieces)` is not empty: after the release-in-progress check and `ensure_branch`, run `migrate.migrate(args.root, pieces, ASSETS)`, then `apply.commit_paths(args.root, written, f"{MIGRATE_SUBJECT}\n\n{MIGRATE_BODY}")` and print `migrated to the v2 layout: <n> files`. `MIGRATE_BODY`:

```python
MIGRATE_SUBJECT = "Migrate to the repo-infra v2 layout"
MIGRATE_BODY = ("Pieces are called at oposs/repo-infra/.github/workflows/<piece>.yml@v2 "
                "instead of copied (D33): the copies and .github/workflows/lib/ go, every "
                "call names the piece remotely and passes its secrets by name, ci.yml gets "
                "release-verdict and the v2 ci-passed, and changelog.yml and release-pr.yml "
                "are the v2 callers.")
```

- `_pending` and `_states` cover byte pieces only (`{n: p for n, p in pieces.items() if not p.remote}`).

In `apply.py`, generalise `commit_piece` with a sibling:

```python
def commit_paths(repo_root, paths, message):
    git(repo_root, "add", "--all", "--", *paths)
    git(repo_root, "commit", "-m", f"{message}\n\n{TRAILER}", "--", *paths)
    return git(repo_root, "rev-parse", "HEAD").strip()
```

`git add --all -- <removed path>` stages the deletion.

Tests in `tests/test_cli.py` (the existing ones run `cli.main` against a git repository and a fake store; copy that setup):

```python
def test_apply_migrates_a_v1_repository_in_one_commit(tmp_path, monkeypatch, git_repo):
    """A v1 repository with a copied piece, the library and the v1 ci.yml."""
    ...
```

Build the repository from `tests/fixtures/v1/` (Step 1's mtuspy `ci.yml` plus a copied `.github/workflows/ri-ci-rust.yml` and `.github/workflows/lib/release.js`), run `cli.main(["apply", "--root", str(repo), "--repo", "o/r"])` with `read_facts` patched to `CONFORMING_FACTS` (and `release_prs=()`, `tags` holding the latest release, as the existing apply tests do), and assert: exit 0; one new commit whose subject is `Migrate to the repo-infra v2 layout`; no `.github/workflows/ri-*.yml` and no `.github/workflows/lib` left; `changelog.yml` and `release-pr.yml` equal the shipped callers; and `checking.layout_items(repo, load_pieces()) == []`.

```python
def test_apply_item_refuses_a_remote_piece(tmp_path, monkeypatch):
    code = cli.main(["apply", "--root", str(tmp_path), "--repo", "o/r", "--item", "ri-ci-rust"])
    assert code == 1
```

with `capsys` asserting `refused: ri-ci-rust is called, not installed (D33)` at the start of stderr.

- [ ] **Step 4: Run, gate, changelog, commit**

`python3 -m pytest -q --basetemp=.pytest-tmp tests/test_migrate.py tests/test_cli.py tests/test_apply_pieces.py && make check`. Expected: PASS.

`### Changed`:

```markdown
- `/repo-infra:apply` installs build files and never copies a workflow. On a repository with the v1 layout it migrates in one commit on `repo-infra/apply`: it removes the copied workflows and `.github/workflows/lib/`, points every call at `@v2` with its secrets passed by name, adds `release-verdict` and the new `ci-passed` to `ci.yml`, and writes the new `changelog.yml` and `release-pr.yml`. The repository's CI on that pull request is the test.
```

```bash
git add -A skills/repo-infra tests CHANGES.md
git commit -m "Migrate a v1 repository with apply in one commit (D33)

migrate.py rewrites the callers as text, so the pull request shows
only the migration: local calls of pieces become @v2 calls, inherit on
them becomes named secrets from the piece's interface, ci-passed is
replaced in place with release-verdict above it, the ri-ci-lib job
goes, and changelog.yml and release-pr.yml are written from the
callers in the store. apply refuses --item for a remote piece.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: The mtuspy example on v2, its source record, and the gate workflow

**Files:**
- Modify: `skills/repo-infra/references/examples/mtuspy/ci.yml`, `release-build.yml`, `release-publish.yml`
- Create: `skills/repo-infra/references/examples/mtuspy/changelog.yml`, `release-pr.yml`, `source.json`; `.github/workflows/gate-mtuspy.yml`; `tests/test_gate.py`
- Test: `tests/test_callers.py` (remove the xfail of Task 9), `tests/test_skill.py`

**Interfaces:**
- Produces: `source.json` = `{"repository": "oetiker/mtuspy", "ref": "v0.2.1", "version": "0.2.1"}`; the gate's jobs `source`, `rust`, `rust-musl`, `man`, `binaries`, `packages`, `homebrew`; `source`'s outputs `repository`, `ref`, `version`.

- [ ] **Step 1: The example callers, written by hand**

Confirm the tag exists: `gh api repos/oetiker/mtuspy/git/ref/tags/v0.2.1 --jq .object.sha` (read-only). If it does not, ask the controller which released mtuspy tag to record.

`ci.yml`: the v1 example with the `lib` job gone, every `uses: ./.github/workflows/ri-<n>.yml` written `uses: oposs/repo-infra/.github/workflows/ri-<n>.yml@v2`, the `release-verdict` and `ci-passed` jobs of `assets/callers/ci-passed.yml` in place of the old `ci-passed`, and `needs: [rust, rust-musl, man, smoke-test, release-pr-current, release-verdict]`. `release-build.yml` and `release-publish.yml`: the `uses:` lines in the remote form; in `release-publish.yml` the `gitea` job's `secrets: inherit` becomes

```yaml
    secrets:
      GITEA_PACKAGE_TOKEN: ${{ secrets.GITEA_PACKAGE_TOKEN }}
```

`changelog.yml` and `release-pr.yml`: copies of `assets/callers/`. Check them with the migration: `migrate.migrate` on a copy of the v1 example produces the same five files (Task 10's test of the mtuspy ci.yml already compares `ci.yml`; add the same for `release-publish.yml`).

`source.json`:

```json
{
  "repository": "oetiker/mtuspy",
  "ref": "v0.2.1",
  "version": "0.2.1"
}
```

Remove the `xfail` mark from `test_the_mtuspy_example_callers_have_no_problem` and extend its parameters to `["ci.yml", "release-build.yml", "release-publish.yml", "changelog.yml", "release-pr.yml"]`. In `tests/test_skill.py:test_mtuspy_is_the_example_of_a_project_with_its_full_shape`, add `"changelog.yml"`, `"release-pr.yml"`, `"source.json"` to the names.

- [ ] **Step 2: Failing test** `tests/test_gate.py`

```python
"""The release gate (D33) runs mtuspy's CI and release-build jobs as the
example calls them, with the pieces of the commit under test."""

import json
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
GATE = ROOT / ".github/workflows/gate-mtuspy.yml"
EXAMPLE = ROOT / "skills/repo-infra/references/examples/mtuspy"
CI_JOBS = ("rust", "rust-musl", "man")
BUILD_JOBS = ("binaries", "packages", "homebrew")
FROM_SOURCE = {"repository": "${{ needs.source.outputs.repository }}",
               "ref": "${{ needs.source.outputs.ref }}",
               "version": "${{ needs.source.outputs.version }}"}


def load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def gate():
    return load(GATE)


def _needs(job):
    value = job.get("needs", [])
    return [value] if isinstance(value, str) else list(value)


def normal(job, remote):
    """A job without what the gate and the example must differ in (P10):
    repository, ref, version, if:, the source need, and the form of uses:."""
    out = {k: v for k, v in job.items() if k not in ("if", "needs", "with", "uses")}
    uses = job["uses"]
    prefix = "oposs/repo-infra/.github/workflows/" if remote else "./.github/workflows/"
    assert uses.startswith(prefix), uses
    out["uses"] = uses[len(prefix):].removesuffix("@v2")
    out["with"] = {k: v for k, v in job.get("with", {}).items()
                   if k not in ("repository", "ref", "version")}
    out["needs"] = sorted(n for n in _needs(job) if n != "source")
    return out


def test_the_gate_runs_exactly_the_six_jobs_and_the_source_reader():
    assert set(gate()["jobs"]) == {"source", *CI_JOBS, *BUILD_JOBS}


def test_each_gate_job_equals_the_example_job():
    jobs = gate()["jobs"]
    example = {**load(EXAMPLE / "ci.yml")["jobs"], **load(EXAMPLE / "release-build.yml")["jobs"]}
    for job_id in (*CI_JOBS, *BUILD_JOBS):
        assert normal(jobs[job_id], remote=False) == normal(example[job_id], remote=True), job_id


def test_each_gate_job_reads_the_source_record():
    jobs = gate()["jobs"]
    for job_id in (*CI_JOBS, *BUILD_JOBS):
        assert "source" in _needs(jobs[job_id]), job_id
        given = jobs[job_id]["with"]
        assert given["repository"] == FROM_SOURCE["repository"], job_id
        assert given["ref"] == FROM_SOURCE["ref"], job_id
        if job_id in BUILD_JOBS:
            assert given["version"] == FROM_SOURCE["version"], job_id


def test_the_gate_is_dispatched_only_and_needs_no_secret():
    doc = gate()
    assert list(doc.get("on", doc.get(True))) == ["workflow_dispatch"]
    assert doc.get("on", doc.get(True))["workflow_dispatch"] in (None, {})
    assert "secrets" not in GATE.read_text(encoding="utf-8")
    assert doc["permissions"] == {"contents": "read"}


def test_the_source_record_names_a_tag_and_its_version():
    record = json.loads((EXAMPLE / "source.json").read_text(encoding="utf-8"))
    assert set(record) == {"repository", "ref", "version"}
    assert record["ref"] == f"v{record['version']}"
```

Run it. Expected: FAIL, no `gate-mtuspy.yml`.

- [ ] **Step 3: `.github/workflows/gate-mtuspy.yml`**

```yaml
name: Gate (mtuspy)

# The release gate (D33). Create release PR dispatches it on the release
# branch and waits for it; the release pull request does not open unless it
# succeeds. It runs mtuspy's CI and release-build jobs through ./, so the
# pieces and the library of the dispatched commit build the mtuspy release
# recorded in references/examples/mtuspy/source.json. Its artifacts stay in
# this run and never reach the release. It runs no publish piece and needs
# no secret. tests/test_gate.py holds its jobs equal to the example's.
on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  source:
    name: Read the source record
    runs-on: ubuntu-latest
    timeout-minutes: 5
    outputs:
      repository: ${{ steps.read.outputs.repository }}
      ref: ${{ steps.read.outputs.ref }}
      version: ${{ steps.read.outputs.version }}
    steps:
      - uses: actions/checkout@v7
        with:
          sparse-checkout: skills/repo-infra/references/examples/mtuspy

      - id: read
        run: |
          f=skills/repo-infra/references/examples/mtuspy/source.json
          for key in repository ref version; do
            value=$(jq -er ".$key" "$f")
            echo "$key=$value" >> "$GITHUB_OUTPUT"
          done
```

followed by the six jobs, each the example job with `needs:` gaining `source`, `uses: ./.github/workflows/ri-<n>.yml`, no `if:`, and `with:` holding `repository: ${{ needs.source.outputs.repository }}`, `ref: ${{ needs.source.outputs.ref }}` and, for the build jobs, `version: ${{ needs.source.outputs.version }}`, plus the example's other inputs unchanged. For example:

```yaml
  packages:
    needs: [source, binaries]
    uses: ./.github/workflows/ri-release-nfpm.yml
    with:
      version: ${{ needs.source.outputs.version }}
      repository: ${{ needs.source.outputs.repository }}
      ref: ${{ needs.source.outputs.ref }}
      config: nfpm.yaml
      packagers: '{"deb": {}, "rpm": {}}'
      archives: x86_64-unknown-linux-musl aarch64-unknown-linux-musl
```

`check` on repo-infra sees `gate-mtuspy.yml` as a project-owned workflow: its calls are local, take `ref` from the source job, and the ref contract (`ref_passing_problems`) applies only to `ci.yml` and `release-build.yml`. Run `tests/test_self_check.py` to confirm.

- [ ] **Step 4: Run, gate, changelog, commit**

`python3 -m pytest -q --basetemp=.pytest-tmp tests/test_gate.py tests/test_callers.py tests/test_skill.py tests/test_self_check.py && make check`. Expected: PASS.

`### Changed`:

```markdown
- The mtuspy example under `references/examples/mtuspy/` shows the v2 callers: `ci.yml`, `release-build.yml`, `release-publish.yml`, `changelog.yml` and `release-pr.yml`. `source.json` names the mtuspy release repo-infra's release gate builds.
```

```bash
git add -A .github skills/repo-infra tests CHANGES.md
git commit -m "Add the mtuspy release gate and the v2 example (D33)

gate-mtuspy.yml runs mtuspy's three CI and three release-build jobs
through ./ on a dispatched ref, with repository, ref and version read
from references/examples/mtuspy/source.json, so a release of repo-infra
builds a real consumer with its own pieces before v2 moves. The example
callers are hand-written in the v2 form, and test_gate.py holds the
gate's jobs equal to them apart from the fields that must differ.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Create release PR waits for the gate

**Files:**
- Create: `.github/workflows/lib/gate.js`, `.github/workflows/lib/gate.test.js`
- Modify: `.github/workflows/release-pr.yml` (repo-infra's own)
- Test: `tests/test_release_pr.py`

**Interfaces:**
- Consumes: Task 1's dispatch field name (written `RUN_ID_FIELD` below; expected `workflow_run_id`).
- Produces: `gate.dispatch(github, { owner, repo, workflow, ref }) -> Promise<number>`; `gate.waitForRun(github, { owner, repo, runId, sleep, now, timeoutMs, intervalMs }) -> Promise<{ conclusion, html_url }>`; `gate.runGate(github, { owner, repo, workflow, ref, sleep, now, timeoutMs, intervalMs }) -> Promise<{ ok, message }>`.

- [ ] **Step 1: Failing test** `.github/workflows/lib/gate.test.js`

```js
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { dispatch, waitForRun, runGate } = require('./gate.js');

const clock = () => {
  let t = 0;
  return { now: () => t, sleep: async (ms) => { t += ms; } };
};

const api = ({ dispatched = { workflow_run_id: 42 }, runs = [] } = {}) => {
  const calls = [];
  let i = 0;
  return {
    calls,
    request: async (route, args) => { calls.push([route, args]); return { data: dispatched }; },
    rest: { actions: { getWorkflowRun: async (args) => {
      calls.push(['getWorkflowRun', args]);
      const run = runs[Math.min(i, runs.length - 1)];
      i += 1;
      return { data: run };
    } } },
  };
};

test('dispatch asks for the run details and returns the run id', async () => {
  const github = api();
  assert.equal(await dispatch(github, { owner: 'o', repo: 'r', workflow: 'gate-mtuspy.yml', ref: 'release/v2.0.0' }), 42);
  assert.deepEqual(github.calls[0], ['POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches',
    { owner: 'o', repo: 'r', workflow_id: 'gate-mtuspy.yml', ref: 'release/v2.0.0', return_run_details: true }]);
});

test('dispatch without a run id in the answer fails naming the workflow', async () => {
  const github = api({ dispatched: {} });
  await assert.rejects(dispatch(github, { owner: 'o', repo: 'r', workflow: 'gate-mtuspy.yml', ref: 'x' }),
    /gate-mtuspy\.yml was dispatched on x, but GitHub returned no run id/);
});

test('waitForRun polls until the run completes', async () => {
  const github = api({ runs: [{ status: 'queued' }, { status: 'in_progress' },
    { status: 'completed', conclusion: 'success', html_url: 'u' }] });
  const c = clock();
  const run = await waitForRun(github, { owner: 'o', repo: 'r', runId: 42, ...c, timeoutMs: 10000, intervalMs: 1000 });
  assert.deepEqual(run, { conclusion: 'success', html_url: 'u' });
  assert.equal(c.now(), 2000);
});

test('waitForRun gives up at the timeout', async () => {
  const github = api({ runs: [{ status: 'in_progress', html_url: 'u' }] });
  const c = clock();
  await assert.rejects(waitForRun(github, { owner: 'o', repo: 'r', runId: 42, ...c, timeoutMs: 5000, intervalMs: 1000 }),
    /run 42 did not finish within 5 s: u/);
});

test('runGate passes only on success', async () => {
  for (const [conclusion, ok] of [['success', true], ['failure', false], ['cancelled', false], ['timed_out', false]]) {
    const github = api({ runs: [{ status: 'completed', conclusion, html_url: 'u' }] });
    const out = await runGate(github, { owner: 'o', repo: 'r', workflow: 'gate-mtuspy.yml', ref: 'release/v2.0.0', ...clock(), timeoutMs: 1000, intervalMs: 10 });
    assert.equal(out.ok, ok, conclusion);
    assert.match(out.message, new RegExp(`gate-mtuspy\\.yml on release/v2\\.0\\.0: ${conclusion}, u`));
  }
});

test('runGate turns a timeout into a failed verdict, not a hang', async () => {
  const github = api({ runs: [{ status: 'queued', html_url: 'u' }] });
  const out = await runGate(github, { owner: 'o', repo: 'r', workflow: 'gate-mtuspy.yml', ref: 'r1', ...clock(), timeoutMs: 100, intervalMs: 10 });
  assert.equal(out.ok, false);
  assert.match(out.message, /did not finish within/);
});
```

Run `node --test .github/workflows/lib/gate.test.js`. Expected: FAIL, no `gate.js`.

- [ ] **Step 2: `gate.js`**

```js
'use strict';

// D33: Create release PR dispatches the release gate (gate-mtuspy.yml) on the
// release branch and waits for it. The dispatch API returns the run id when
// asked for run details (since February 2026); without it there is no run to
// wait for, which fails the gate. Everything external is an argument, so the
// tests need no network and no real time.

const RUN_ID_FIELD = 'workflow_run_id';

async function dispatch(github, { owner, repo, workflow, ref }) {
  const { data } = await github.request(
    'POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches',
    { owner, repo, workflow_id: workflow, ref, return_run_details: true },
  );
  const id = data && data[RUN_ID_FIELD];
  if (!id) {
    throw new Error(`${workflow} was dispatched on ${ref}, but GitHub returned no run id `
      + `(${RUN_ID_FIELD}); there is no run to wait for.`);
  }
  return id;
}

async function waitForRun(github, {
  owner, repo, runId, sleep, now, timeoutMs, intervalMs,
}) {
  const start = now();
  for (;;) {
    const { data: run } = await github.rest.actions.getWorkflowRun({ owner, repo, run_id: runId });
    if (run.status === 'completed') return { conclusion: run.conclusion, html_url: run.html_url };
    if (now() - start + intervalMs > timeoutMs) {
      throw new Error(`run ${runId} did not finish within ${Math.round(timeoutMs / 1000)} s: `
        + `${run.html_url}`);
    }
    await sleep(intervalMs);
  }
}

async function runGate(github, {
  owner, repo, workflow, ref, sleep, now, timeoutMs, intervalMs,
}) {
  try {
    const runId = await dispatch(github, { owner, repo, workflow, ref });
    const run = await waitForRun(github, {
      owner, repo, runId, sleep, now, timeoutMs, intervalMs,
    });
    return { ok: run.conclusion === 'success',
      message: `${workflow} on ${ref}: ${run.conclusion}, ${run.html_url}` };
  } catch (error) {
    return { ok: false, message: error.message };
  }
}

module.exports = { RUN_ID_FIELD, dispatch, waitForRun, runGate };
```

Put Task 1's field name into `RUN_ID_FIELD` and the test's `api()` default. Check `waitForRun`'s timeout arithmetic against the tests: with `timeoutMs: 5000, intervalMs: 1000` it sleeps four times and throws on the fifth poll; adjust the condition until `waitForRun gives up at the timeout` passes and `waitForRun polls until the run completes` ends at 2000 ms.

- [ ] **Step 3: The gate job in repo-infra's `release-pr.yml`**

Between `test` and `finish`:

```yaml
  # D33: a release of repo-infra builds mtuspy with its own pieces before the
  # pull request opens, so v2 never moves to pieces that break a consumer.
  # It dispatches gate-mtuspy.yml on the release branch, a run of its own,
  # so the gate's artifacts never reach this run's draft. Only this job
  # holds actions: write; consumers' build jobs never do.
  gate:
    name: Build mtuspy with the release's pieces
    needs: prepare
    runs-on: ubuntu-latest
    timeout-minutes: 120
    permissions:
      contents: read
      actions: write
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ needs.prepare.outputs.head }}
          sparse-checkout: .github/workflows/lib

      - uses: actions/setup-node@v7
        with:
          node-version: 22

      - name: Dispatch the gate and wait for it
        uses: actions/github-script@v9
        env:
          BRANCH: release/v${{ needs.prepare.outputs.version }}
        with:
          script: |
            const gate = require(`${process.env.GITHUB_WORKSPACE}/.github/workflows/lib/gate.js`);
            const { owner, repo } = context.repo;
            const verdict = await gate.runGate(github, {
              owner, repo, workflow: 'gate-mtuspy.yml', ref: process.env.BRANCH,
              sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
              now: () => Date.now(), timeoutMs: 110 * 60 * 1000, intervalMs: 30 * 1000,
            });
            if (!verdict.ok) {
              core.setFailed(verdict.message);
              return;
            }
            core.notice(verdict.message);
```

`finish` needs `[prepare, build, test, gate]`. The workflow-level `permissions:` stays `checks: read, actions: read`.

- [ ] **Step 4: Tests** (append to `tests/test_release_pr.py`)

```python
OWN = ROOT / ".github/workflows/release-pr.yml"


def test_repo_infra_gates_its_release_on_mtuspy():
    jobs = load(OWN)["jobs"]
    assert list(jobs) == ["prepare", "build", "test", "gate", "finish"]
    assert jobs["gate"]["needs"] == "prepare"
    assert jobs["gate"]["permissions"] == {"contents": "read", "actions": "write"}
    assert jobs["finish"]["needs"] == ["prepare", "build", "test", "gate"]
    script = jobs["gate"]["steps"][-1]["with"]["script"]
    assert "workflow: 'gate-mtuspy.yml'" in script and "process.env.BRANCH" in script


def test_no_other_job_of_the_release_flow_may_write_actions():
    caller_jobs = caller()["jobs"]
    assert all(job["permissions"].get("actions") != "write"
               for job_id, job in caller_jobs.items() if job_id != "prepare")
```

- [ ] **Step 5: Run, gate, changelog, commit**

`node --test .github/workflows/lib/gate.test.js && python3 -m pytest -q --basetemp=.pytest-tmp tests/test_release_pr.py tests/test_callers.py tests/test_self_check.py && make check`. Expected: PASS.

`### Changed`:

```markdown
- A release of repo-infra builds mtuspy with the release's own workflows before its pull request opens. When that build fails, Create release PR fails at "Build mtuspy with the release's pieces" and `v2` does not move.
```

```bash
git add -A .github tests CHANGES.md
git commit -m "Wait for the mtuspy gate before opening the release PR (D33)

The gate job dispatches gate-mtuspy.yml on the release branch with
return_run_details, so it gets the run id from the dispatch itself, and
polls that run for up to 110 minutes; finish needs it. gate.js holds the
logic with the clock and the API as arguments, so a dispatch without a
run id and a run that never finishes fail with one message in the tests.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: The compatibility test against `v2`

**Files:**
- Create: `tests/v2compat.py`, `tests/test_v2_compat.py`
- Modify: `.github/workflows/ci.yml` (inline job `v2-compat`), `skills/repo-infra/references/examples/repo-infra/ci.yml`

**Interfaces:**
- Produces: `v2compat.interface_problems(name, old_doc, new_doc) -> list[str]`; `v2compat.permission_problems(name, old_doc, new_doc) -> list[str]`; `v2compat.problems(old: {name: doc}, new: {name: doc}) -> list[str]`.

Rules (spec, "Compatibility within v2"): no piece removed; no input, secret or output removed; no input's `type` changed; no input or secret newly required; a new input has `required: false` and a `default`; a new secret is `required: false`; no `permissions:` block (workflow level, an old job's, or a new job's) grants a scope above what the old file granted at that level, and the union over the file (`callers.needed`) does not grow.

- [ ] **Step 1: Failing comparator tests** `tests/test_v2_compat.py` (first part)

```python
"""D33: within v2 a piece keeps its interface and its permissions."""

import json
import os
import pathlib
import re
import subprocess

import pytest
from v2compat import problems

from repo_infra import workflow
from repo_infra.pieces import load_pieces

ROOT = pathlib.Path(__file__).resolve().parents[1]

BASE = """on:
  workflow_call:
    inputs:
      ref:
        description: x
        type: string
        required: false
        default: ''
    secrets:
      token:
        description: x
        required: false
    outputs:
      out:
        description: x
        value: ${{ jobs.a.outputs.out }}
permissions:
  contents: read
jobs:
  a:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - run: 'true'
"""


def cmp(new, old=BASE):
    return problems({"ri-x": workflow.load(old)}, {"ri-x": workflow.load(new)})


def test_the_same_piece_has_no_problem():
    assert cmp(BASE) == []


def test_a_removed_piece_is_a_problem():
    assert problems({"ri-x": workflow.load(BASE)}, {}) == ["ri-x: removed within v2"]


@pytest.mark.parametrize("edit, problem", [
    (lambda t: t.replace("      ref:\n        description: x\n        type: string\n"
                         "        required: false\n        default: ''\n", ""),
     "ri-x: input ref removed"),
    (lambda t: t.replace("type: string", "type: boolean"),
     "ri-x: input ref changed its type from string to boolean"),
    (lambda t: t.replace("        required: false\n        default: ''\n",
                         "        required: true\n"),
     "ri-x: input ref became required"),
    (lambda t: t.replace("      token:\n        description: x\n        required: false\n",
                         "      token:\n        description: x\n        required: true\n"),
     "ri-x: secret token became required"),
    (lambda t: t.replace("    secrets:\n      token:\n        description: x\n"
                         "        required: false\n", ""),
     "ri-x: secret token removed"),
    (lambda t: t.replace("    outputs:\n      out:\n        description: x\n"
                         "        value: ${{ jobs.a.outputs.out }}\n", ""),
     "ri-x: output out removed"),
    (lambda t: t.replace("    inputs:\n", "    inputs:\n      new:\n        description: x\n"
                         "        type: string\n        required: true\n"),
     "ri-x: new input new must be optional with a default"),
    (lambda t: t.replace("    inputs:\n", "    inputs:\n      new:\n        description: x\n"
                         "        type: string\n        required: false\n"),
     "ri-x: new input new must be optional with a default"),
    (lambda t: t.replace("    secrets:\n", "    secrets:\n      key:\n        description: x\n"
                         "        required: true\n"),
     "ri-x: new secret key must be optional"),
    (lambda t: t.replace("permissions:\n  contents: read\njobs:",
                         "permissions:\n  contents: write\njobs:"),
     "ri-x: the workflow-level permissions grant contents: write, above contents: read"),
    (lambda t: t.replace("    permissions:\n      contents: read\n",
                         "    permissions:\n      contents: read\n      checks: write\n"),
     "ri-x: job a asks for checks: write, above what it asked for in v2"),
    (lambda t: t + "  b:\n    runs-on: ubuntu-latest\n    permissions:\n"
                   "      pull-requests: write\n    steps:\n      - run: 'true'\n",
     "ri-x: new job b asks for pull-requests: write, beyond what the piece asked for in v2"),
])
def test_a_change_v2_consumers_would_notice_is_a_problem(edit, problem):
    assert problem in cmp(edit(BASE))


@pytest.mark.parametrize("edit", [
    lambda t: t.replace("    inputs:\n", "    inputs:\n      new:\n        description: x\n"
                        "        type: string\n        required: false\n        default: ''\n"),
    lambda t: t.replace("    secrets:\n", "    secrets:\n      key:\n        description: x\n"
                        "        required: false\n"),
    lambda t: t.replace("    outputs:\n", "    outputs:\n      more:\n        description: x\n"
                        "        value: ${{ jobs.a.outputs.more }}\n"),
    lambda t: t.replace("    permissions:\n      contents: read\n", "    permissions:\n"
                        "      contents: none\n"),
])
def test_a_change_v2_allows_is_fine(edit):
    assert cmp(edit(BASE)) == []
```

- [ ] **Step 2: `tests/v2compat.py`**

```python
"""What v2 consumers notice (D33): the comparison test_v2_compat.py runs
between the pieces of the commit v2 points at and the pieces now."""

from repo_infra import callers, workflow

_NAMES = {0: "none", 1: "read", 2: "write"}


def _over(have, had):
    return {s: l for s, l in have.items() if l > had.get(s, 0)}


def _text(levels):
    return ", ".join(f"{s}: {_NAMES[l]}" for s, l in sorted(levels.items()))


def interface_problems(name, old, new):
    before, after = workflow.interface(old), workflow.interface(new)
    found = []
    for key, spec in before.inputs.items():
        now = after.inputs.get(key)
        if now is None:
            found.append(f"{name}: input {key} removed")
            continue
        if now["type"] != spec["type"]:
            found.append(f"{name}: input {key} changed its type from {spec['type']} to "
                         f"{now['type']}")
        if now["required"] and not spec["required"]:
            found.append(f"{name}: input {key} became required")
    for key, spec in after.inputs.items():
        if key not in before.inputs and (spec["required"] or spec["default"] is None):
            found.append(f"{name}: new input {key} must be optional with a default")
    for key, spec in before.secrets.items():
        now = after.secrets.get(key)
        if now is None:
            found.append(f"{name}: secret {key} removed")
        elif now["required"] and not spec["required"]:
            found.append(f"{name}: secret {key} became required")
    for key, spec in after.secrets.items():
        if key not in before.secrets and spec["required"]:
            found.append(f"{name}: new secret {key} must be optional")
    for key in before.outputs:
        if key not in after.outputs:
            found.append(f"{name}: output {key} removed")
    return found


def permission_problems(name, old, new):
    found = []
    top_old = callers.grant(old.get("permissions")) or {}
    top_new = callers.grant(new.get("permissions")) or {}
    over = _over(top_new, top_old)
    if over:
        found.append(f"{name}: the workflow-level permissions grant {_text(over)}, above "
                     f"{_text(top_old) or 'nothing'}")
    old_jobs, new_jobs = callers.jobs(old), callers.jobs(new)
    union_old = callers.needed(name, {name: old})
    for job_id, job in new_jobs.items():
        mine = callers.grant(job.get("permissions"))
        if mine is None:
            continue
        if job_id in old_jobs:
            had = callers.grant(old_jobs[job_id].get("permissions")) or top_old
            over = _over(mine, had)
            if over:
                found.append(f"{name}: job {job_id} asks for {_text(over)}, above what it "
                             "asked for in v2")
        else:
            over = _over(mine, union_old)
            if over:
                found.append(f"{name}: new job {job_id} asks for {_text(over)}, beyond what "
                             "the piece asked for in v2")
    return found


def problems(old, new):
    found = []
    for name, doc in sorted(old.items()):
        if name not in new:
            found.append(f"{name}: removed within v2")
            continue
        found += interface_problems(name, doc, new[name])
        found += permission_problems(name, doc, new[name])
    return found
```

`workflow.interface` reports a missing `default` as `None` (check in `workflow.py:_table`; adjust the `default is None` test to whatever it returns for an absent key). Run the comparator tests until they pass.

- [ ] **Step 3: The test against the tag** (second part of `tests/test_v2_compat.py`)

```python
def _git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def _released_major():
    text = (ROOT / "CHANGES.md").read_text(encoding="utf-8")
    match = re.search(r"^## (\d+)\.\d+\.\d+ - ", text, re.MULTILINE)
    return int(match[1]) if match else 0


@pytest.fixture
def v2():
    found = _git("rev-parse", "--verify", "--quiet", "refs/tags/v2^{commit}")
    if found.returncode != 0:
        if os.environ.get("RI_V2_COMPAT") == "required" and _released_major() >= 2:
            pytest.fail("CHANGES.md records a 2.x release and this checkout has no tag v2; "
                        "the v2-compat job must fetch it")
        pytest.skip("no tag v2 in this checkout (shallow clone, or before 2.0.0)")
    return found.stdout.strip()


def test_the_pieces_keep_what_v2_consumers_call(v2):
    manifest = json.loads(_git("show", f"{v2}:skills/repo-infra/assets/manifest.json").stdout)
    old = {}
    for name, spec in manifest["pieces"].items():
        if spec.get("kind") == "remote":
            old[name] = workflow.load(_git("show", f"{v2}:.github/workflows/{name}.yml").stdout)
    new = {name: workflow.load(p.files[p.target]) for name, p in load_pieces().items()
           if p.remote}
    assert problems(old, new) == []
```

- [ ] **Step 4: The CI job** in `.github/workflows/ci.yml` (and the example copy), before `release-verdict`:

```yaml
  # D33: within v2 a piece keeps its interface and its permissions. The tag
  # v2 is only in a full clone, so this job fetches the history; the pytest
  # job's shallow clone skips the test.
  v2-compat:
    if: ${{ !(github.event_name == 'pull_request' && startsWith(github.head_ref, 'release/') && github.event.pull_request.head.repo.full_name == github.repository && github.event.pull_request.user.login == 'github-actions[bot]') }}
    name: Interfaces stay within v2
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ inputs.ref }}
          fetch-depth: 0

      - uses: actions/setup-python@v7
        with:
          python-version: '3.11'

      - run: pip install pytest -r requirements-dev.txt

      - run: python3 -m pytest -q tests/test_v2_compat.py
        env:
          RI_V2_COMPAT: required
```

`ci-passed`'s `needs` gains `v2-compat`.

- [ ] **Step 5: Run, gate, changelog, commit**

`python3 -m pytest -q --basetemp=.pytest-tmp tests/test_v2_compat.py tests/test_callers.py tests/test_self_check.py && make check`. Expected: PASS, the tag test skipped locally unless a `v2` tag exists.

No `CHANGES.md` entry of its own: the rule is announced in Task 8's `RELEASING.md` and in Task 14's entry. Commit with the `no-changelog` reasoning in the message only if the branch already carries entries (it does).

```bash
git add -A .github tests skills/repo-infra/references/examples/repo-infra/ci.yml
git commit -m "Refuse interface changes v2 consumers would notice (D33)

Every consumer runs every release of v2, so test_v2_compat.py compares
each remote piece with the commit v2 points at: no removed piece, input,
secret or output, no changed type, nothing newly required, new inputs
optional with a default, and no permissions block above v2's. The tag
is only in a full clone, so a job of its own fetches the history, and it
fails rather than skips once CHANGES.md records a 2.x release.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: The skill describes the remote model

**Files:**
- Modify: `skills/repo-infra/SKILL.md` (at most 120 lines, `tests/test_skill.py:test_the_skill_stays_short`), `skills/repo-infra/references/onboarding.md`, `release-flow.md`, `conventions.md`, `teaching-the-standard.md` (where it says pieces are copied), `commands/check.md`, `commands/apply.md`, `README.md`, `CHANGES.md`
- Test: `tests/test_skill.py`

- [ ] **Step 1: Failing tests** (append to `tests/test_skill.py`)

```python
def test_the_skill_says_pieces_are_called_at_v2_not_copied():
    text = flat(ROOT / "skills/repo-infra/SKILL.md")
    assert "oposs/repo-infra/.github/workflows/<piece>.yml@v2" in text
    for ref in ("onboarding.md", "release-flow.md", "conventions.md"):
        body = flat(REFS / ref)
        assert "copied 1:1" not in body and "byte for byte" not in body, ref


def test_onboarding_and_apply_name_the_migration():
    assert "v1 layout" in flat(REFS / "onboarding.md")
    assert "Migrate to the repo-infra v2 layout" in flat(ROOT / "commands/apply.md")


def test_release_flow_names_the_two_judges_and_the_split():
    text = flat(REFS / "release-flow.md")
    for name in ("ri-release-verdict", "ri-changelog", "ri-release-prepare",
                 "ri-release-finish", "release-verdict"):
        assert f"`{name}`" in text, name
```

(`ROOT`, `REFS` and `flat` exist in `tests/test_skill.py`.) Run them. Expected: FAIL.

- [ ] **Step 2: Rewrite the passages**

Find them with `grep -rn 'copied\|1:1\|byte for byte\|workflow-lib\|\.github/workflows/lib\|apply --item ri-' skills/repo-infra/SKILL.md skills/repo-infra/references commands README.md` and rewrite each in the house style (writing-style skill, no em dash):

- `SKILL.md`: the model in three sentences: workflows are called at `uses: oposs/repo-infra/.github/workflows/<piece>.yml@v2`; build files (`build/man.mk`, `build/man-deflist.lua`, `build/container.mk`, `m4/repo-infra-container.m4`, `.github/dependabot.yml`) are installed by `apply`; `check` reviews both.
- `onboarding.md`: a new repository copies the five callers from `references/examples/mtuspy/` (or `assets/callers/`) and calls pieces from the catalogue; a repository with the v1 layout runs `apply`, which migrates it in one pull request.
- `release-flow.md`: `release-pr.yml` wires `ri-release-prepare`, the repository's build and CI, and `ri-release-finish`; `ci-passed` reads `release-verdict` (`ri-release-verdict`); `changelog-updated` reads `ri-changelog`; repo-infra's own release waits for the mtuspy gate and moves `v2`.
- `conventions.md`: secrets are passed by name to repo-infra workflows; `secrets: inherit` only to the repository's own `release-build.yml`, `ci.yml` and `action-test.yml`.
- `commands/check.md`: the v1 layout findings and the `@v2` rule. `commands/apply.md`: `apply` migrates a v1 repository first, in a commit named "Migrate to the repo-infra v2 layout", and `--item` installs build files only.
- `README.md`: one paragraph on calling the workflows at `@v2`.

- [ ] **Step 3: The headline changelog entry**, first under `### Changed`:

```markdown
- Repositories call repo-infra's workflows instead of copying them: every `uses:` reads `oposs/repo-infra/.github/workflows/<piece>.yml@v2`, and each release of repo-infra moves `v2`, so fixes arrive without a pull request. Run `/repo-infra:apply` once to migrate; repo-infra 1.x gets no further fixes.
```

- [ ] **Step 4: Gate and commit**

`python3 -m pytest -q --basetemp=.pytest-tmp tests/test_skill.py tests/test_no_em_dash.py tests/test_prose_skills.py && make check`. Expected: PASS.

```bash
git add -A skills/repo-infra commands README.md CHANGES.md tests/test_skill.py
git commit -m "Describe the remote pieces in the skill (D33)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: [outward] Pull request, CI, merge

Controller task.

- [ ] **Step 1: Full local gate**

```bash
cd /scratch/oetiker/claude-worktrees/repo-infra-release-pieces
make check
systemd-run --user --scope -p MemoryMax=4G -- make test-container
```

(timeouts 600000). Expected: PASS.

- [ ] **Step 2: [outward] Push and open the pull request**

```bash
S=/scratch/oetiker/claude-tmp/claude-1003/plan-d33
cat > $S/pr.md <<'EOF'
Repositories call repo-infra's workflows at `@v2` instead of copying them (D33, `docs/superpowers/specs/2026-10-13-remote-pieces-design.md`).

- every piece lives once in `.github/workflows/`, and loads the library from its own commit
- `ci-passed` and `changelog-updated` stay inline and read `ri-release-verdict` and `ri-changelog`
- `release-pr` splits into `ri-release-prepare` and `ri-release-finish`
- `check` reviews the remote calls and reports the v1 layout; `apply` migrates it in one commit
- `gate-mtuspy.yml` builds mtuspy with the release's own pieces before `v2` moves; `tests/test_v2_compat.py` refuses interface changes within `v2`

Before the 2.0.0 release: dispatch the gate on main, create the release App, its secrets and the tag ruleset (plan Tasks 16 and 17).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
git push -u origin feat/remote-pieces
gh pr create --base main --title "Remote pieces at @v2 (D33)" --body-file $S/pr.md
gh pr checks --watch
```

Expected: `ci-passed` and `changelog-updated` green. This pull request's own run is the first in which `ri-release-verdict` and `ri-changelog` run through `./`.

- [ ] **Step 3: [outward] Merge** (squash; standing authority). The plan file and the spec merge with it.

---

# Phase C: owner steps, the release, mtuspy

### Task 16: [owner] The release App, its secrets and the tag ruleset

Done by the owner; the controller prepares the commands and reads back each result.

1. **[owner]** Create a GitHub App owned by the `oposs` organisation, name for example `repo-infra-release`, with repository permission **Contents: Read and write** and nothing else, no webhook. Install it on `oposs/repo-infra` only. Generate a private key.
2. **[owner]** Repository secrets on oposs/repo-infra: `RELEASE_APP_ID` (the App id) and `RELEASE_APP_PRIVATE_KEY` (the PEM file's content).
3. **[owner]** The tag ruleset. The controller writes `$S/ruleset-tags.json` with the App id filled in:

```json
{
  "name": "Protect release tags",
  "target": "tag",
  "enforcement": "active",
  "conditions": {"ref_name": {"include": ["refs/tags/v*"], "exclude": []}},
  "rules": [{"type": "update"}, {"type": "deletion"}],
  "bypass_actors": [
    {"actor_type": "Integration", "actor_id": <APP_ID>, "bypass_mode": "always"},
    {"actor_type": "RepositoryRole", "actor_id": 5, "bypass_mode": "always"}
  ]
}
```

and the owner runs `gh api -X POST repos/oposs/repo-infra/rulesets --input $S/ruleset-tags.json`. Read back: `gh api repos/oposs/repo-infra/rulesets --jq '.[] | select(.target=="tag")'` shows the ruleset `active`, both rules and both bypass actors. (`actor_id` 5 is the Repository admin role.)

`$S/ruleset-tags.json` holds no secret, but delete it after use (owner confirms).

### Task 17: [controller] Dispatch the gate on main until it is green

- [ ] `gh workflow run gate-mtuspy.yml --repo oposs/repo-infra --ref main`, then `gh run watch` on the run (`gh run list --workflow gate-mtuspy.yml --limit 1`).
- [ ] When it fails, the fix is an ordinary feature pull request (branch from `main`, a test that pins the failure where one can, a `CHANGES.md` entry, squash merge), then dispatch again. Expected failure points: a piece that still reads `github.repository` (Task 7), a checkout of the private parts of mtuspy (mtuspy is public; if a step needs a token it does not have, stop and ask the owner), a lib path.
- [ ] Done when one run on `main` is green. Record its URL for the release pull request.

### Task 18: [owner] Release 2.0.0, see `v2`, pin the marketplace

1. **[owner]** Dispatch Create release PR on oposs/repo-infra with `major`. Expected: the `gate` job dispatches `gate-mtuspy.yml` on `release/v2.0.0`, waits, and passes; the release pull request opens with `ci-passed` and `changelog-updated` green.
2. **[owner]** Merge the release pull request with a merge commit. The publish run tags `v2.0.0`, and "Move the major tag" creates `v2` (the first release of the major is a creation, which the ruleset allows; later releases update it with the App token).
3. Read back: `gh api repos/oposs/repo-infra/git/ref/tags/v2` exists, and its tag object points at the commit of `v2.0.0`.
4. **[owner]** In `oposs/claude-plugins`, the repo-infra entry of the marketplace gets `"ref": "v2"` in its `source`. Commit and push there (owner).
5. Verify the installed plugin carries the pieces: update the plugin (`/plugin` in Claude Code), then `ls ~/.claude/plugins/cache/oposs-plugins/repo-infra/2.0.0/.github/workflows/ri-ci-rust.yml`. If `.github/` is missing from the cache, `check` fails with "the plugin's asset store is broken"; report it to the owner as a spec defect (the spec assumes the installed plugin holds the pieces) before migrating anything.
6. The next ordinary release (2.0.1 or later) is the first that moves `v2` with the App. Watch that publish run's "Move the major tag" step once.

### Task 19: [controller] [owner] Migrate mtuspy and release it

1. Worktree: `git -C /home/oetiker/checkouts/mtuspy fetch origin && git -C /home/oetiker/checkouts/mtuspy worktree add /scratch/oetiker/claude-worktrees/mtuspy-v2 -b repo-infra/apply origin/main` (delete a stale local `repo-infra/apply` first, with the owner, as in the D32 plan's P13). Do not touch the working tree of `/home/oetiker/checkouts/mtuspy`.
2. Run `apply` from the installed 2.0.0 plugin: `PYTHONPATH=~/.claude/plugins/cache/oposs-plugins/repo-infra/2.0.0/skills/repo-infra/scripts python3 -m repo_infra apply --root /scratch/oetiker/claude-worktrees/mtuspy-v2 --repo oetiker/mtuspy`. Expected: one commit "Migrate to the repo-infra v2 layout".
3. Compare with the example: `diff` each of `ci.yml`, `release-build.yml`, `release-publish.yml`, `changelog.yml`, `release-pr.yml` against `references/examples/mtuspy/`. Expected: no difference. A difference is either a defect of `migrate.py` (fix it in repo-infra with a test, release, run again) or of the example (fix the example and the gate together).
4. `check` exits 0 on the worktree.
5. **[outward]** Push `repo-infra/apply`, open the pull request with a `CHANGES.md` entry in mtuspy ("Builds and releases run on repo-infra's shared workflows at `@v2`; the copies under `.github/workflows/` are gone."), watch its CI: this run is the test of the migration.
6. **[owner]** Merge (mtuspy merges need the owner). **[owner]** Dispatch mtuspy's Create release PR (`bugfix`), merge the release pull request. Record the new tag (for example `v0.2.2`).

### Task 20: The source record follows mtuspy

Engineer task, on a branch from `main`.

**Files:**
- Modify: `skills/repo-infra/references/examples/mtuspy/source.json`, `CHANGES.md`
- Test: `tests/test_gate.py` (unchanged; it holds `ref == "v" + version`)

- [ ] **Step 1:** Set `ref` and `version` to the release of Task 19 (for example `"ref": "v0.2.2"`, `"version": "0.2.2"`).
- [ ] **Step 2:** `python3 -m pytest -q --basetemp=.pytest-tmp tests/test_gate.py && make check`. Expected: PASS.
- [ ] **Step 3:** `### Changed`: `` - repo-infra's release gate builds mtuspy 0.2.2, the first mtuspy release on the v2 layout. ``
- [ ] **Step 4:** Commit (`Gate on mtuspy 0.2.2, its first v2 release (D33)` with the trailer), **[outward]** push, pull request, CI green, squash merge. **[controller]** Dispatch `gate-mtuspy.yml` on `main` once and confirm it is green.

---

## Self-review

Spec section to task:

| Spec section | Task |
|---|---|
| Why, Decisions | 2 to 14 together; v1 freeze in 9, 10, 14 |
| Layout in repo-infra | 2 (pieces), 5 (library, release-pr), 4 (changelog), 2 (`ri-ci-lib`), 4 and 5 (repo-infra's callers through `./`) |
| Loading the library | 1 (probe), 3 |
| A source input on every piece | 7 (P12 for the publish pieces) |
| Required checks stay inline | 4 |
| release-pr splits | 5; `ri-ci-github-action` in 6; the probe of `./` and `$/` in 1 |
| Secrets | 9 (check), 10 (apply), 8 (`ri-publish-tag`'s optional secrets) |
| The release gate | 11 (workflow, example, `source.json`, equality test), 12 (gate job), 17, 18 |
| Compatibility within v2 | 13 |
| The tag | 8 (`moving_major_tag`, App token, RELEASING.md), 16 (App, ruleset) |
| check | 9 (remote calls, v1 layout, interfaces from the plugin), 4 (inline jobs), 5 (release-pr structure), 18 (marketplace `ref`) |
| apply | 10 |
| Order of work | 1; 2 to 15; 16 to 17; 18; 19; 20 |

Spec defects and gaps the plan works around, for the owner:

1. "repo-infra's `ci.yml` calls `ri-changelog`": `changelog-updated` lives in `changelog.yml`, so `ri-changelog` is called from `changelog.yml` (Task 4).
2. The gate's equality test must also ignore `version`, `if:` and the `source` need (P10).
3. "Every piece that checks out the source already takes `ref`" is not true of the publish pieces; they get no `repository` input (P12).
4. The spec assumes the installed plugin contains `.github/workflows/`; Task 18 Step 5 verifies it before any migration.
5. `ri-release-verdict` needs a `message` output for `ci-passed` to say why (P6).
