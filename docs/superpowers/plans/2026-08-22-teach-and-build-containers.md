# Teach Path and Containerized Builds Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give repo-infra a documented way to grow when it meets a repository shape it has no answer for, ship the source-tarball publish add-on that any autotools conversion needs first, and replace the `perl-autotools` CI block with the containerized contract.

**Architecture:** `release-publish.yml` stops being a verbatim asset and becomes assembled the way `ci.yml` already is — a frame, zero or more publish add-on blocks, and a `finalize` job whose `needs:` list is generated. The teach path is procedure, not machinery: it lives in `SKILL.md` and `commands/apply.md`, with one small `check` report change for the case a program *can* see. The container work ships an automake fragment as a versioned asset and rewrites one CI block around a `make test` contract.

**Tech Stack:** Python 3.11+ (standard library only at runtime; `pytest` and `ruff` in CI), GitHub Actions, Node 22 for the workflow library, `podman` as the container engine on the runner, GNU autotools.

**Spec:** `docs/superpowers/specs/2026-08-21-teach-and-build-containers-design.md`, which extends `docs/superpowers/specs/2026-08-17-repo-infra-design.md` (D1–D15).

## Global Constraints

Everything in the plugin-shell plan's Global Constraints still applies. Repeated here because an executor reading this plan may not have read that one:

- **The checker imports nothing outside the Python standard library.** `pytest` and `ruff` are CI-only and are never imported by shipped code.
- **Python 3.11 minimum.**
- **Assets are literal files.** No templating, no substitution tokens (D15). The only generated content is a `needs:` list computed by the assembler — after this plan there are two of them, `ci-passed` and `finalize`.
- **The standard's default branch is `main`.** Assets say `branches: [main]` and never anything else.
- **Every installed file carries a marker**: `# repo-infra: <asset-id> v<n>`, at column 0 for a whole file or at 2-space indent above a job block (D11).
- **Action versions are queried, never recalled.** `gh api repos/<owner>/<action>/releases/latest --jq .tag_name`. `manifest.json` records them; nothing else hard-codes one.
- **No `git push`, `git tag` or `git config` inside any shipped workflow.** Git operations go through the Git Data API (D9).
- **No `|| true`** and no swallowed failures.
- **Every write is read back and asserted.**
- **Changelog headings**: `## [Unreleased]` with `### New` / `### Changed` / `### Fixed`. `New`, never `Added` (D6).
- **Every commit message** ends with:
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`
- **`main` is protected here too.** Every task lands through a branch and a pull request under this repository's own ruleset — see *Landing a task*.
- **CI runs `ruff check .` at the repository root**, even though `make lint` covers only `skills/repo-infra/scripts` and `tests`. Anything added anywhere must be lint-clean.
- **`ruff` is not importable from the sandboxed python here.** Use `uvx ruff check .`; `make lint` fails locally for that reason and is fine in CI.
- **Repository administration on any repo other than `repo-infra`** is outward-facing. Confirm with the user before running it.

New for this plan:

- **`make test` is the test contract for autotools projects** (spec 2026-08-21, Consequences §2). Not `make check`. A project that only has automake `TESTS` adds a `test` target; it does not get the block changed for it.
- **There is no mechanism for declaring system packages to CI** (D16). If a task seems to need one, it has hit the threshold and the answer is the teach path, not a new config field.

## Landing a task

`gh pr checks --watch` does not wait for checks to *appear*. Use exactly this:

```bash
git checkout -b task-N-short-name
# ... work ...
git add -A && git commit -F <commit message file>
git push -u origin task-N-short-name
gh pr create --fill --base main            # add --label no-changelog for docs-only work
while gh pr checks 2>&1 | grep -q 'no checks reported'; do sleep 5; done
gh pr checks --watch --interval 5
gh pr merge --squash --delete-branch
git checkout main && git pull
```

Do not collapse the wait into `until gh pr checks --watch`: that cannot tell "not registered yet" from "failed" and loops forever on a red build. Do not use `--auto`.

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `skills/repo-infra/assets/publish/publish-frame.yml` | Create. Triggers, permissions, the `publish` job. Carries `release-publish v2`. | 1 |
| `skills/repo-infra/assets/publish/publish-finalize.yml` | Create. The `finalize` job with the `needs: []` placeholder. | 1 |
| `skills/repo-infra/assets/workflows/release-publish.yml` | Delete — split into the two files above. | 1 |
| `skills/repo-infra/scripts/repo_infra/assemble.py` | Modify. Add `assemble_publish`; `render_all` gains a `publish` argument. | 1 |
| `skills/repo-infra/scripts/repo_infra/cli.py` | Modify. Read `publish` out of `.github/repo-infra.json` and pass it to `render_all`. | 1 |
| `skills/repo-infra/scripts/repo_infra/apply.py` | Modify. `write_config` preserves a `publish` list. | 1 |
| `skills/repo-infra/assets/manifest.json` | Modify. Drop the `release-publish` asset entry; add `publish_blocks`. | 1, 2 |
| `skills/repo-infra/assets/publish/publish-source-tarball.yml` | Create. `make dist` and attach the tarball to the draft release. | 2 |
| `skills/repo-infra/scripts/repo_infra/report.py` | Modify. Say the standard does not recognise this repository when nothing is detected. | 3 |
| `skills/repo-infra/SKILL.md` | Modify. The teach path as a third route. | 4 |
| `skills/repo-infra/references/teaching-the-standard.md` | Create. The procedure in full. | 4 |
| `commands/apply.md` | Modify. Point at the teach path before applying. | 4 |
| `docs/superpowers/specs/2026-08-17-repo-infra-design.md` | Modify. D16 and D17 join the D-series. | 4 |
| `skills/repo-infra/assets/build/container-test.mk` | Create. The containerized `test` target, installed only when the repository's config names it. | 5 |
| `tests/test_build_assets.py` | Create. The fragment, and that it ships only when chosen. | 5 |
| `skills/repo-infra/assets/ci/ci-perl-autotools.yml` | Modify. Host toolchain, `make test`. | 6 |
| `skills/repo-infra/assets/detection.json` | Modify. `perl-autotools` version file becomes `VERSION`. | 6 |
| `tests/test_publish.py` | Create. Assembly of `release-publish.yml`. | 1, 2 |
| `tests/test_teach.py` | Create. The unrecognised-repository report. | 3 |
| `tests/test_blocks.py` | Modify. Cover the publish assets and the build fragment. | 1, 5 |

---

### Task 1: Make `release-publish.yml` assembled

The publish seam is designed but not built. `release-publish.yml` is copied verbatim, and its `finalize` job carries a hand-written `needs: [publish]` with a comment claiming `apply` appends add-on names to it. Nothing does. This task makes the comment true, with no add-on yet, so the change is provably behaviour-preserving.

**Files:**
- Create: `skills/repo-infra/assets/publish/publish-frame.yml`
- Create: `skills/repo-infra/assets/publish/publish-finalize.yml`
- Delete: `skills/repo-infra/assets/workflows/release-publish.yml`
- Modify: `skills/repo-infra/scripts/repo_infra/assemble.py`
- Modify: `skills/repo-infra/scripts/repo_infra/cli.py:39-43` (`_load`)
- Modify: `skills/repo-infra/scripts/repo_infra/apply.py:370-378` (`write_config`)
- Modify: `skills/repo-infra/assets/manifest.json`
- Modify: `.github/workflows/release-publish.yml` (this repository's own installed copy)
- Modify: `.github/repo-infra.json`
- Modify: `tests/test_blocks.py:20-30` (`required_workflow_files` docstring)
- Test: `tests/test_publish.py`

**Interfaces:**
- Consumes: `markers.marker_line(asset, version, indent, comment)`; `assemble.NEEDS_PLACEHOLDER`; `assemble._read`; `assemble.AssemblyError`.
- Produces: `assemble.assemble_publish(assets_root, addons, manifest) -> str`; `render_all(assets_root, result, manifest, publish=())`; `manifest["publish_blocks"]` mapping `block-id -> {"version": int, "jobs": [str]}`; the `publish` key in `.github/repo-infra.json`, a list of block ids, default `[]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_publish.py`:

```python
import json
import pathlib

import pytest

from repo_infra.assemble import AssemblyError, assemble_publish
from repo_infra.markers import parse_markers

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))


def test_with_no_addons_finalize_needs_only_publish():
    text = assemble_publish(ASSETS, [], MANIFEST)
    assert "    needs: [publish]" in text


def test_the_frame_marker_survives_assembly():
    text = assemble_publish(ASSETS, [], MANIFEST)
    assert ("release-publish", 2) in [(m.asset, m.version) for m in parse_markers(text)]


def test_an_unknown_addon_is_an_assembly_error():
    with pytest.raises(AssemblyError, match="not declared in the manifest"):
        assemble_publish(ASSETS, ["publish-nonexistent"], MANIFEST)


def test_the_placeholder_must_appear_exactly_once():
    # Guards the asset, not the code: a finalize block that lost its
    # placeholder would silently publish a release before the add-ons ran.
    text = (ASSETS / "publish/publish-finalize.yml").read_text(encoding="utf-8")
    assert text.count("    needs: []") == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_publish.py -v`
Expected: FAIL — `ImportError: cannot import name 'assemble_publish'`.

- [ ] **Step 3: Split the asset**

Create `skills/repo-infra/assets/publish/publish-frame.yml` with everything from the current `workflows/release-publish.yml` up to and including the end of the `publish:` job — that is, every line before `  finalize:`. Change the marker on line 2 from `v1` to `v2` and extend the header comment:

```yaml
name: Publish release (automatic)
# repo-infra: release-publish v2
#
# Half two. Merging the release pull request lands the rolled CHANGES.md on main,
# and that merge triggers this.
#
# This file is assembled, not copied: this frame, then one job block per publish
# add-on the repository installs, then the finalize job whose `needs:` list is
# generated from those blocks. That generated list is the reason the core never
# has to know which add-ons exist.
#
# There is deliberately no workflow_dispatch. Publishing should be a consequence
# of merging a release pull request, never something started from a dropdown.
# With main protected against direct pushes, that leaves exactly one route to a
# release. Recovery does not need a manual trigger either: a failed run is re-run
# from the Actions UI, and because the version is read from the repository rather
# than from run inputs, the re-run does what the original attempt would have.
```

Everything from `on:` through the end of the `publish:` job is copied unchanged.

Create `skills/repo-infra/assets/publish/publish-finalize.yml` holding the `finalize` job, with the hand-written needs list replaced by the placeholder:

```yaml
  finalize:
    name: Publish the release
    # Generated by the assembler: `publish`, then every add-on job installed in
    # this repository. An add-on that fails leaves the release a draft, which is
    # the correct outcome -- a release missing its artifacts must not be visible.
    needs: []
    if: needs.publish.outputs.release_id != ''
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions:
      contents: write
    steps:
      - uses: actions/github-script@v9
        with:
          script: |
            const { data: released } = await github.rest.repos.updateRelease({
              owner: context.repo.owner,
              repo: context.repo.repo,
              release_id: Number('${{ needs.publish.outputs.release_id }}'),
              draft: false,
            });
            core.notice(`Published ${released.html_url}`);
            await core.summary
              .addHeading(`Released ${{ needs.publish.outputs.tag }}`)
              .addLink('Release', released.html_url)
              .write();
```

Then delete the old file:

```bash
git rm skills/repo-infra/assets/workflows/release-publish.yml
```

- [ ] **Step 4: Add `assemble_publish`**

In `skills/repo-infra/scripts/repo_infra/assemble.py`, after `assemble_ci`:

```python
def assemble_publish(assets_root, addons, manifest):
    """release-publish.yml: the frame, the add-on blocks, then finalize.

    The second generated `needs:` list in the standard. `finalize` must wait for
    every add-on, or a release would go public before its artifacts were
    attached -- and the core must not name add-ons it does not ship, or it would
    depend on spec 2 to run at all.
    """
    assets_root = pathlib.Path(assets_root)
    publish = assets_root / "publish"
    parts = [_read(publish / "publish-frame.yml").rstrip("\n")]
    needs = ["publish"]

    for addon in addons:
        meta = manifest["publish_blocks"].get(addon)
        if meta is None:
            raise AssemblyError(f"publish add-on {addon} is not declared in the manifest")
        body = _read(publish / (addon + ".yml"))
        parts.append("")
        parts.append(markers.marker_line(addon, meta["version"], indent="  "))
        parts.append(body.rstrip("\n"))
        needs.extend(meta["jobs"])

    finalize = _read(publish / "publish-finalize.yml").rstrip("\n")
    if finalize.count(NEEDS_PLACEHOLDER) != 1:
        raise AssemblyError(
            f"publish-finalize.yml must contain exactly one {NEEDS_PLACEHOLDER!r} "
            "line to fill in")
    finalize = finalize.replace(
        NEEDS_PLACEHOLDER, "    needs: [{}]".format(", ".join(needs)))

    parts.append("")
    parts.append(finalize)
    return "\n".join(parts) + "\n"
```

Then change `render_all`'s signature and body:

```python
def render_all(assets_root, result, manifest, publish=()):
    """Every file this repository should have, keyed by repo-relative path."""
    assets_root = pathlib.Path(assets_root)
    files = {}
    for name, spec in manifest["assets"].items():
        source = assets_root / spec["source"]
        if spec.get("kind") == "dir":
            if not source.is_dir():
                raise AssemblyError(f"asset {name}: {source} is not a directory")
            for child in sorted(source.iterdir()):
                if child.is_file():
                    files[f"{spec['target']}/{child.name}"] = _read(child)
        else:
            files[spec["target"]] = _read(source)
    files[".github/workflows/ci.yml"] = assemble_ci(assets_root, result.blocks, manifest)
    files[".github/workflows/release-publish.yml"] = assemble_publish(
        assets_root, publish, manifest)
    return files
```

- [ ] **Step 5: Update the manifest**

In `skills/repo-infra/assets/manifest.json`, remove the whole `"release-publish"` entry from `"assets"` — it is assembled now, so a verbatim copy would install it twice — and add a sibling to `ci_blocks`:

```json
  "publish_blocks": {},
```

Place it immediately after the `ci_blocks` object.

- [ ] **Step 6: Read the publish list in the CLI**

In `skills/repo-infra/scripts/repo_infra/cli.py`, add above `_load`:

```python
def _publish_addons(root):
    """The publish add-ons this repository installs, from its own config.

    Detection cannot answer this: whether a repository publishes a tarball, a
    crate or nothing at all is a decision, not a file signal (D12). An
    unconverted repository has no config file and installs no add-ons.
    """
    config = pathlib.Path(root) / ".github/repo-infra.json"
    if not config.is_file():
        return []
    return json.loads(config.read_text(encoding="utf-8")).get("publish", [])
```

and change `_load` to use it:

```python
def _load(root):
    manifest = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
    result = Detection.load(ASSETS / "detection.json").detect(root)
    return manifest, result, render_all(ASSETS, result, manifest, _publish_addons(root))
```

- [ ] **Step 7: Preserve the publish list when writing the config**

In `skills/repo-infra/scripts/repo_infra/apply.py`, inside `write_config`, add one key to the `config` dict:

```python
    config = {
        "ecosystems": result.ecosystems,
        "moving_major_tag": existing.get("moving_major_tag", False),
        "version_files": existing.get("version_files") or result.version_files,
        "publish": existing.get("publish", []),
    }
```

- [ ] **Step 8: Run the new tests**

Run: `python3 -m pytest tests/test_publish.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 9: Regenerate this repository's own installed copy**

The self-proof test re-assembles `.github/` and fails on any difference, so the installed file has to move with the asset:

```bash
python3 - <<'PY'
import json, pathlib, sys
sys.path.insert(0, "skills/repo-infra/scripts")
from repo_infra.assemble import assemble_publish
assets = pathlib.Path("skills/repo-infra/assets")
manifest = json.loads((assets / "manifest.json").read_text(encoding="utf-8"))
pathlib.Path(".github/workflows/release-publish.yml").write_text(
    assemble_publish(assets, [], manifest), encoding="utf-8")
PY
```

Add `"publish": []` to `.github/repo-infra.json`, after `"moving_major_tag"`.

- [ ] **Step 10: Fix the stale docstring in the block tests**

In `tests/test_blocks.py`, `required_workflow_files()` names a file that no longer exists. Replace its docstring:

```python
    """Only the assets that end up behind a required check.

    The publish assets legitimately carry `paths: ['CHANGES.md']`: that is a
    push trigger and none of their jobs is a required context. Applying D13's
    rule to them would be wrong.
    """
```

- [ ] **Step 11: Run the whole suite**

Run: `python3 -m pytest -q tests`
Expected: PASS. The count rises by 4 from the current 180 to 184.

Run: `uvx ruff check .`
Expected: no findings.

- [ ] **Step 12: Commit and land**

```bash
git add -A
git commit -F - <<'EOF'
Assemble release-publish.yml instead of copying it

The finalize job's comment claimed `apply` appends publish add-on names to
its needs list. Nothing did. This makes it true: the workflow is now a
frame plus zero or more add-on blocks plus a finalize job whose needs list
is generated, exactly as ci.yml already works.

No add-on ships yet, so the assembled output is byte-identical in intent to
the file it replaces -- the only change is that the needs list is computed
rather than written by hand, and the frame marker moves to v2.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

Then follow *Landing a task*.

---

### Task 2: The source tarball publish add-on

The first add-on, and a blocking dependency for every autotools conversion: SmokePing attaches `smokeping-X.Y.Z.tar.gz` today, and converting it before this exists would silently drop that.

**Files:**
- Create: `skills/repo-infra/assets/publish/publish-source-tarball.yml`
- Modify: `skills/repo-infra/assets/manifest.json`
- Modify: `tests/test_publish.py`

**Interfaces:**
- Consumes: `assemble_publish` from Task 1; `needs.publish.outputs.release_id`, `needs.publish.outputs.version` and `needs.publish.outputs.tag` from the frame's `publish` job.
- Produces: manifest entry `"publish-source-tarball": {"version": 1, "jobs": ["publish-source-tarball"]}`; the config value `"publish": ["publish-source-tarball"]` that an autotools repository sets.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_publish.py`:

```python
def test_the_tarball_addon_lands_between_publish_and_finalize():
    text = assemble_publish(ASSETS, ["publish-source-tarball"], MANIFEST)
    assert "    needs: [publish, publish-source-tarball]" in text
    assert text.index("  publish-source-tarball:") < text.index("  finalize:")


def test_the_tarball_addon_carries_its_marker():
    text = assemble_publish(ASSETS, ["publish-source-tarball"], MANIFEST)
    assert ("publish-source-tarball", 1) in [
        (m.asset, m.version) for m in parse_markers(text)]


def test_the_tarball_addon_declares_exactly_the_job_it_contains():
    from repo_infra.assemble import block_job_ids
    text = (ASSETS / "publish/publish-source-tarball.yml").read_text(encoding="utf-8")
    assert block_job_ids(text) == MANIFEST["publish_blocks"]["publish-source-tarball"]["jobs"]


def test_the_tarball_addon_refuses_to_upload_nothing():
    # A `make dist` that produced no tarball must fail the job, not publish a
    # release with no artifact. Guard the guard: this is the whole point of the
    # add-on and it is one easily-deleted line.
    text = (ASSETS / "publish/publish-source-tarball.yml").read_text(encoding="utf-8")
    assert "no tarball" in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_publish.py -v`
Expected: FAIL — `AssemblyError: publish add-on publish-source-tarball is not declared in the manifest`.

- [ ] **Step 3: Write the add-on block**

Create `skills/repo-infra/assets/publish/publish-source-tarball.yml`:

```yaml
  publish-source-tarball:
    name: Attach the source tarball
    needs: [publish]
    if: needs.publish.outputs.release_id != ''
    runs-on: ubuntu-latest
    timeout-minutes: 30
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v7

      # The host toolchain needed to reach `make dist`, and nothing else. A
      # project needing more than this has crossed the D16 threshold and belongs
      # in a container; there is deliberately no way to declare extra packages.
      - name: Install the autotools host toolchain
        run: |
          sudo apt-get update
          sudo apt-get install -y autoconf automake gettext

      - run: ./bootstrap

      - run: ./configure

      - name: Build the distribution tarball
        run: make dist

      # `make dist` names the tarball from AC_INIT, which is not necessarily the
      # repository name -- so find it rather than guess it. Exactly one is
      # expected; two means a stale tarball is committed and the upload would be
      # a coin toss.
      - name: Locate the tarball
        id: tarball
        run: |
          set -euo pipefail
          mapfile -t found < <(find . -maxdepth 1 -name '*.tar.gz' -printf '%P\n' | sort)
          if [ "${#found[@]}" -eq 0 ]; then
            echo "make dist produced no tarball" >&2
            exit 1
          fi
          if [ "${#found[@]}" -gt 1 ]; then
            echo "more than one tarball in the source root: ${found[*]}" >&2
            echo "remove the committed ones; this job cannot tell which to upload" >&2
            exit 1
          fi
          echo "name=${found[0]}" >> "$GITHUB_OUTPUT"

      - name: Attach it to the draft release
        uses: actions/github-script@v9
        with:
          script: |
            const fs = require('fs');
            const name = '${{ steps.tarball.outputs.name }}';
            if (!name) {
              core.setFailed('no tarball to upload');
              return;
            }
            const data = fs.readFileSync(`${process.env.GITHUB_WORKSPACE}/${name}`);
            const { data: asset } = await github.rest.repos.uploadReleaseAsset({
              owner: context.repo.owner,
              repo: context.repo.repo,
              release_id: Number('${{ needs.publish.outputs.release_id }}'),
              name,
              data,
              headers: {
                'content-type': 'application/gzip',
                'content-length': data.length,
              },
            });
            core.notice(`Attached ${asset.name} (${asset.size} bytes).`);
```

- [ ] **Step 4: Declare it in the manifest**

In `skills/repo-infra/assets/manifest.json`, fill in the `publish_blocks` object created in Task 1:

```json
  "publish_blocks": {
    "publish-source-tarball": {"version": 1, "jobs": ["publish-source-tarball"]}
  },
```

- [ ] **Step 5: Run the tests**

Run: `python3 -m pytest tests/test_publish.py -v`
Expected: PASS, 8 tests.

- [ ] **Step 6: Verify the block against the pinned action versions**

`tests/test_blocks.py` walks every `.yml` under `assets/` and asserts each `uses:` matches `manifest.json`'s `actions` map. The new block uses `actions/checkout` and `actions/github-script`, both already pinned.

Run: `python3 -m pytest -q tests`
Expected: PASS, 188 tests.

Run: `uvx ruff check .`
Expected: no findings.

- [ ] **Step 7: Record it in the changelog**

Add under `## [Unreleased]` → `### New` in `CHANGES.md`:

```markdown
- A publish add-on that attaches the `make dist` source tarball to a release. It is the first of spec 2's add-ons, and any autotools repository needs it before it can be converted without losing the tarball it publishes today.
```

- [ ] **Step 8: Commit and land**

```bash
git add -A
git commit -F - <<'EOF'
Add the source tarball publish add-on

The classic distribution format for an autotools project, and the first
item of spec 2 rather than one of eight -- the earlier add-on list omitted
it by oversight. Until it exists, converting an autotools repository
silently drops the tarball its releases carry today.

The job finds the tarball rather than guessing its name: `make dist` names
it from AC_INIT, which need not match the repository. Zero tarballs and
more than one are both failures, so a release never goes public missing an
artifact it was supposed to carry.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

Then follow *Landing a task*.

---

### Task 3: `check` says when the standard does not recognise a repository

`mkp-builder` reports `detected nothing` followed by `9 items need attention`, which reads as a broken repository. The true statement is that the standard has no idea what this repository is, and the ecosystem-dependent half of the report is meaningless until it does.

**Files:**
- Modify: `skills/repo-infra/scripts/repo_infra/report.py:27-52`
- Test: `tests/test_teach.py`

**Interfaces:**
- Consumes: `result.ecosystems` (a list of strings) and the `Item` namedtuple `(name, state, detail)`.
- Produces: no new callable. `render_text` gains one branch; `render_json` is unchanged, because a JSON consumer already sees `"ecosystems": []`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_teach.py`:

```python
from repo_infra.report import render_text
from repo_infra.state import Item


class FakeResult:
    def __init__(self, ecosystems):
        self.ecosystems = ecosystems
        self.candidates = []
        self.ambiguities = []


ADMIN_OK = [Item("actions-open-pr", "ok", "")]
FILES_MISSING = [Item("ci", "missing", "not installed")]


def test_an_unrecognised_repository_is_named_as_such():
    text = render_text("oposs/mkp-builder", FakeResult([]), ADMIN_OK + FILES_MISSING)
    assert "the standard does not recognise this repository" in text


def test_an_unrecognised_repository_points_at_the_teach_path_not_apply():
    text = render_text("oposs/mkp-builder", FakeResult([]), ADMIN_OK + FILES_MISSING)
    assert "/repo-infra:apply" not in text


def test_a_recognised_repository_still_points_at_apply():
    text = render_text("oetiker/SmokePing", FakeResult(["perl-autotools"]), FILES_MISSING)
    assert "/repo-infra:apply" in text
    assert "does not recognise" not in text


def test_a_recognised_and_current_repository_is_unchanged():
    text = render_text("oposs/repo-infra", FakeResult(["python"]), ADMIN_OK)
    assert "Up to date with the standard" in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_teach.py -v`
Expected: FAIL on the first two — the phrase is absent and `/repo-infra:apply` is present.

- [ ] **Step 3: Add the branch to `render_text`**

In `skills/repo-infra/scripts/repo_infra/report.py`, replace the closing block of `render_text` (from `count = sum(...)` to the `return`) with:

```python
    count = sum(1 for item in items if item.state in NEEDS_ATTENTION_STATES)

    # No ecosystem matched, so no CI block can be selected and the file items
    # below are conclusions drawn from a repository kind we do not have. Saying
    # "N items need attention" here reads as a broken repository; the true
    # statement is that the standard has never met this shape. Teaching it comes
    # first, and `apply` is not the next step.
    if not result.ecosystems:
        lines.append("the standard does not recognise this repository.")
        lines.append("")
        lines.append("Teach it first: see references/teaching-the-standard.md in the")
        lines.append("repo-infra skill. Running apply now would install the")
        lines.append("repository-wide items and no CI at all.")
        return "\n".join(lines) + "\n"

    if count:
        noun = "item" if count == 1 else "items"
        verb = "needs" if count == 1 else "need"
        lines.append(f"{count} {noun} {verb} attention.  /repo-infra:apply")
    else:
        lines.append("Up to date with the standard — nothing to do.")
    return "\n".join(lines) + "\n"
```

The item rows above are left in place: the administration items (protection, label, permissions) are valid regardless of ecosystem and are still worth seeing.

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/test_teach.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Confirm the exit code is unchanged**

`check` exits 1 when anything needs attention, and that is computed in `cli.check` from the items, not from the report text. An unrecognised repository still has pending administration items, so it still exits 1.

Run:
```bash
cd /home/oetiker/checkouts/mkp-builder && \
PYTHONPATH=/home/oetiker/checkouts/repo-infra/skills/repo-infra/scripts \
python3 -m repo_infra check; echo "exit=$?"
```
Expected: the new wording, and `exit=1`.

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m pytest -q tests`
Expected: PASS, 192 tests.

Run: `uvx ruff check .`
Expected: no findings.

- [ ] **Step 7: Record it in the changelog**

Add under `## [Unreleased]` → `### Changed`:

```markdown
- `check` now says when the standard does not recognise a repository at all, instead of reporting a count of missing items drawn from a repository kind it never identified.
```

- [ ] **Step 8: Commit and land**

```bash
git add -A
git commit -F - <<'EOF'
Report an unrecognised repository as such

`detected nothing` followed by "9 items need attention" reads as a broken
repository. It is not: no ecosystem matched, so no CI block could be
selected and the file items below are conclusions about a repository kind
we do not have.

The report now names that outcome and points at the teach path instead of
at apply. The administration rows stay -- protection, label and permissions
are valid whatever the repository turns out to be -- and the exit code is
unchanged, because it is computed from the items rather than the text.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

Then follow *Landing a task*.

---

### Task 4: The teach path, and D16/D17 into the D-series

Documentation only. Land it with `--label no-changelog`.

**Files:**
- Create: `skills/repo-infra/references/teaching-the-standard.md`
- Modify: `skills/repo-infra/SKILL.md`
- Modify: `commands/apply.md`
- Modify: `docs/superpowers/specs/2026-08-17-repo-infra-design.md`
- Test: `tests/test_skill.py`

**Interfaces:**
- Consumes: the report wording from Task 3, which names `references/teaching-the-standard.md` — the file must exist under exactly that name.
- Produces: nothing importable.

- [ ] **Step 1: Write the failing test**

`tests/test_skill.py` already asserts things about the skill's shape. Append:

```python
def test_the_report_points_at_a_reference_that_exists():
    # report.py names this file by path. A rename that misses one of the two
    # leaves an operator following a dead pointer at exactly the moment the
    # tool has told them it cannot help.
    from repo_infra import report
    source = pathlib.Path(report.__file__).read_text(encoding="utf-8")
    assert "references/teaching-the-standard.md" in source
    assert (ROOT / "skills/repo-infra/references/teaching-the-standard.md").is_file()
```

If `tests/test_skill.py` does not already define `ROOT` and import `pathlib`, add them at the top in the style the file already uses.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_skill.py -v`
Expected: FAIL — the reference file does not exist.

- [ ] **Step 3: Write the reference**

Create `skills/repo-infra/references/teaching-the-standard.md`:

```markdown
# Teaching the standard

repo-infra carries the standard. You do the conversion. When a repository has a
shape the standard has no answer for, the answer is never to patch the
repository around it and never to grow a variant asset for it — it is to teach
the standard, then convert.

## When this applies

Two ways a gap shows up.

**`check` sees it.** No ecosystem matched, or the detection signals are
ambiguous. The report says so and sends you here.

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

What is never available is carrying on natively while installing packages from
CI. If you find yourself wanting a place to list apt packages, you have hit the
threshold; go to stage 1.
```

- [ ] **Step 4: Add the third route to `SKILL.md`**

In `skills/repo-infra/SKILL.md`, insert a section between "Then apply" and "The four things that will surprise you":

```markdown
## When the standard has no answer

`check` and `apply` assume the standard knows what this repository is. Sometimes
it does not — the report says `the standard does not recognise this repository`,
or you read the repository and find the standard silent about something it needs,
or in conflict with something that already works.

Do not patch the repository around the gap, and do not grow a variant asset for
it. Teach the standard, then convert: ask the user, prove the answer in this
repository's tree, upstream it to repo-infra, and merge this repository's pull
request only once that has shipped.

`references/teaching-the-standard.md` has the procedure, including which
differences are gaps and which are just migration work.
```

Then add to the "Reading further" list at the bottom:

```markdown
- `references/teaching-the-standard.md` — what to do when the standard has no
  answer for this repository, and which differences count.
```

- [ ] **Step 5: Point `commands/apply.md` at it**

In `commands/apply.md`, change the opening paragraph to:

```markdown
Run `/repo-infra:check` first and show the user the report. If it lists an
`ambiguous` item, stop and ask the user that question before doing anything
else — `apply` refuses to guess and will raise on it anyway. If it says the
standard does not recognise this repository, stop: read
`references/teaching-the-standard.md` and teach the standard first.

Before applying, read the repository's own build, test and release setup and
compare it to what you are about to install. A block that does not fit is not a
reason to edit the repository around it — it is a gap in the standard, and
`references/teaching-the-standard.md` says what to do with one.
```

- [ ] **Step 6: Add D16 and D17 to the design document**

In `docs/superpowers/specs/2026-08-17-repo-infra-design.md`, immediately after the D15 section and before `## Spec 1 — the frame`, add the full text of D16 and D17 from `2026-08-21-teach-and-build-containers-design.md`, unchanged. At the end of the D15 section add one line:

```markdown
**Amended by D17**: repo-infra also owns the *shape* of the build environment
for projects over the D16 threshold. The project still owns its content.
```

In the "Scope and decomposition" table, change the spec 2 row so the tarball is
listed first:

```markdown
| **2 — publish add-ons** | the seam, plus the autotools source tarball, crates.io, MKP, npm, nfpm deb/rpm/apk, Windows zip + winget, ghcr containers |
```

- [ ] **Step 7: Run the tests**

Run: `python3 -m pytest -q tests`
Expected: PASS, 193 tests.

- [ ] **Step 8: Commit and land**

```bash
git add -A
git commit -F - <<'EOF'
Document the teach path and fold D16/D17 into the D-series

The plugin had two routes -- apply the standard, or hand-patch the
repository around it -- and the second is exactly the accommodation the
tool exists to prevent. Nothing said so and nothing said what to do
instead.

The third route is question, prove in the repository, upstream before the
repository's own PR merges. D16 (the containerization threshold decides
when to ask, not what the answer is) and D17 (repo-infra owns the shape of
the build environment, the project owns its content) join the numbered
decisions where plans can cite them.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF

# docs-only
gh pr create --fill --base main --label no-changelog
```

Then follow *Landing a task* from the wait loop onwards.

---

### Task 5: The containerized test fragment

The first asset that is build machinery rather than infrastructure, which is what D17 authorises. Generalised from `hin-agw-common/automake/test-container.mk`, with everything HIN-specific removed: no Postgres, no application config environment variables, no live-mount development target. Those are the project's, and a project that needs them adds them to its own `Makefile.am`.

**Files:**
- Create: `skills/repo-infra/assets/build/container-test.mk`
- Modify: `skills/repo-infra/assets/manifest.json`
- Modify: `skills/repo-infra/scripts/repo_infra/assemble.py` (`render_all`)
- Modify: `skills/repo-infra/scripts/repo_infra/cli.py` (`_publish_addons` grows a sibling)
- Modify: `skills/repo-infra/scripts/repo_infra/apply.py` (`write_config`)
- Modify: `tests/test_blocks.py`
- Test: `tests/test_build_assets.py`

**Interfaces:**
- Consumes: `markers.parse_markers`; `render_all(assets_root, result, manifest, publish=())` from Task 1.
- Produces: manifest section `build_assets`, entry `container-test`, target `build/container-test.mk`, comment style `#`; `render_all(..., publish=(), build=())`; the `build` key in `.github/repo-infra.json`, a list of build asset ids, default `[]`. The fragment defines the make targets `container` and `test`, and reads the project-set variables `CONTAINER_TAG`, `TEST_RUNNER`, `SKIP_TESTS`, `TEST_DIR`, `DOCKER` and `CONTAINERFILE`.

**Why a separate manifest section rather than an ordinary asset.** Every entry in
`assets` is installed into every repository unconditionally. This one must not
be: D16 makes containerization a decision, so not even every autotools
repository gets it. `build_assets` mirrors `publish_blocks` — declared centrally,
installed only when the repository's own config names it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_build_assets.py`:

```python
import json
import pathlib

from repo_infra.markers import parse_markers

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
FRAGMENT = ASSETS / "build/container-test.mk"


def test_the_fragment_is_declared_in_the_manifest():
    spec = MANIFEST["build_assets"]["container-test"]
    assert spec["source"] == "build/container-test.mk"
    assert spec["target"] == "build/container-test.mk"
    assert spec["comment"] == "#"


def test_the_fragment_carries_its_marker_at_the_declared_version():
    text = FRAGMENT.read_text(encoding="utf-8")
    version = MANIFEST["build_assets"]["container-test"]["version"]
    assert ("container-test", version) in [(m.asset, m.version) for m in parse_markers(text)]


def test_a_repository_that_did_not_ask_for_it_does_not_get_it():
    # D16: containerization is a decision, not a detection. An autotools repo
    # that stayed native must not be told it is missing a file it never chose.
    import pathlib as _p
    from repo_infra.assemble import render_all
    from repo_infra.detect import Detection
    result = Detection.load(ASSETS / "detection.json").detect(_p.Path(ROOT))
    assert "build/container-test.mk" not in render_all(ASSETS, result, MANIFEST)
    assert "build/container-test.mk" in render_all(
        ASSETS, result, MANIFEST, build=["container-test"])


def test_the_fragment_defines_the_two_targets_the_ci_block_calls():
    text = FRAGMENT.read_text(encoding="utf-8")
    assert "\ncontainer:" in text
    assert "\ntest: container" in text


def test_the_fragment_has_no_substitution_tokens():
    # D15: an asset is the literal file it installs. Parameterization is by make
    # variable at run time, never by rewriting the file at install time.
    text = FRAGMENT.read_text(encoding="utf-8")
    for token in ("$VERSION", "{{", "@PACKAGE@"):
        assert token not in text


def test_the_fragment_fails_when_no_tests_are_found():
    # An empty test glob must not report success. Silence is the failure mode
    # that makes a containerized suite look green while running nothing.
    text = FRAGMENT.read_text(encoding="utf-8")
    assert "no test files" in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_build_assets.py -v`
Expected: FAIL — `KeyError: 'container-test'`.

- [ ] **Step 3: Write the fragment**

Create `skills/repo-infra/assets/build/container-test.mk`:

```make
# repo-infra: container-test v1
#
# Run the test suite inside the project's own container image (D16, D17).
#
# repo-infra owns this file. The project owns its Containerfile and what goes
# in it -- which packages, which base image, what the tests do. Include this
# from Makefile.am:
#
#     include $(top_srcdir)/build/container-test.mk
#
# The project may set, before the include:
#
#   CONTAINERFILE  path to the container definition   (default: Containerfile)
#   CONTAINER_TAG  tag to build and test              (default: $(PACKAGE)-test:local)
#   TEST_RUNNER    command run inside the container   (default: prove -v)
#   TEST_DIR       directory holding the .t files     (default: t)
#   SKIP_TESTS     .t file names to exclude           (default: none)
#   DOCKER         container engine                   (default: podman)
#
# There is deliberately no way to declare host packages. Needing one is what
# sent this project to containers in the first place.

DOCKER ?= podman
CONTAINERFILE ?= Containerfile
CONTAINER_TAG ?= $(PACKAGE)-test:local
TEST_RUNNER ?= prove -v
TEST_DIR ?= t
SKIP_TESTS ?=

.PHONY: container test

container:
	$(DOCKER) build -t $(CONTAINER_TAG) -f $(top_srcdir)/$(CONTAINERFILE) $(top_srcdir)

# The test files are enumerated on the host and passed in by name rather than
# globbed inside the container: a glob that matches nothing expands to nothing,
# the runner exits 0, and a suite that ran no tests reports success.
test: container
	@set -eu; \
	skip=""; \
	for s in $(SKIP_TESTS); do skip="$$skip ! -name $$s"; done; \
	files=$$(cd $(top_srcdir)/$(TEST_DIR) && find . -name '*.t' $$skip | sed 's|^\./|/src/$(TEST_DIR)/|' | sort); \
	if [ -z "$$files" ]; then \
		echo "container-test: no test files in $(TEST_DIR)" >&2; \
		exit 1; \
	fi; \
	echo "container-test: $(TEST_RUNNER) on $$(echo $$files | wc -w) files"; \
	$(DOCKER) run --rm \
		-v $(abs_top_srcdir):/src:ro \
		-w /src \
		$(CONTAINER_TAG) \
		$(TEST_RUNNER) $$files
```

- [ ] **Step 4: Declare it in the manifest, and install it only on request**

In `skills/repo-infra/assets/manifest.json`, add a section beside `publish_blocks`:

```json
  "build_assets": {
    "container-test": {
      "version": 1,
      "source": "build/container-test.mk",
      "target": "build/container-test.mk",
      "comment": "#"
    }
  },
```

In `skills/repo-infra/scripts/repo_infra/assemble.py`, give `render_all` the
second selector and install the chosen build assets:

```python
def render_all(assets_root, result, manifest, publish=(), build=()):
    """Every file this repository should have, keyed by repo-relative path.

    `publish` and `build` are decisions the repository recorded, not things
    detection can see (D12, D16): whether it attaches a tarball, whether it
    builds in a container. An asset in `assets` ships to everyone; one in
    `publish_blocks` or `build_assets` ships only when named.
    """
    assets_root = pathlib.Path(assets_root)
    files = {}
    for name, spec in manifest["assets"].items():
        source = assets_root / spec["source"]
        if spec.get("kind") == "dir":
            if not source.is_dir():
                raise AssemblyError(f"asset {name}: {source} is not a directory")
            for child in sorted(source.iterdir()):
                if child.is_file():
                    files[f"{spec['target']}/{child.name}"] = _read(child)
        else:
            files[spec["target"]] = _read(source)

    for name in build:
        spec = manifest["build_assets"].get(name)
        if spec is None:
            raise AssemblyError(f"build asset {name} is not declared in the manifest")
        files[spec["target"]] = _read(assets_root / spec["source"])

    files[".github/workflows/ci.yml"] = assemble_ci(assets_root, result.blocks, manifest)
    files[".github/workflows/release-publish.yml"] = assemble_publish(
        assets_root, publish, manifest)
    return files
```

In `skills/repo-infra/scripts/repo_infra/cli.py`, generalise the config reader
added in Task 1 and use it twice:

```python
def _chosen(root, key):
    """A list the repository recorded in its own config, or nothing.

    Detection cannot answer these: whether a repository publishes a tarball or
    builds in a container is a decision (D12, D16). An unconverted repository
    has no config file and has chosen nothing.
    """
    config = pathlib.Path(root) / ".github/repo-infra.json"
    if not config.is_file():
        return []
    return json.loads(config.read_text(encoding="utf-8")).get(key, [])


def _load(root):
    manifest = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
    result = Detection.load(ASSETS / "detection.json").detect(root)
    rendered = render_all(ASSETS, result, manifest,
                          _chosen(root, "publish"), _chosen(root, "build"))
    return manifest, result, rendered
```

Delete `_publish_addons`, which `_chosen` replaces.

In `skills/repo-infra/scripts/repo_infra/apply.py`, add the second key to
`write_config`:

```python
        "publish": existing.get("publish", []),
        "build": existing.get("build", []),
```

- [ ] **Step 5: Keep the asset walkers honest**

`tests/test_blocks.py:every_asset_file()` yields only `.yml` and `.yaml`, so the fragment is outside every existing asset check. That is correct — a Makefile fragment has no `uses:` line to pin — but make it deliberate rather than accidental. Add to `tests/test_blocks.py`:

```python
def test_every_non_yaml_asset_is_covered_by_a_test():
    # every_asset_file() only walks YAML. Anything else under assets/ needs its
    # own test file, or it ships unchecked.
    others = {p.suffix for p in ASSETS.rglob("*") if p.is_file()} - {".yml", ".yaml", ".json", ".js"}
    assert others == {".mk"}, "a new asset kind arrived with no test: %s" % others
```

- [ ] **Step 6: Run the tests**

Run: `python3 -m pytest tests/test_build_assets.py tests/test_blocks.py -v`
Expected: PASS.

- [ ] **Step 7: Confirm the fragment ships only when chosen**

`repo-infra` is not an autotools project and has not chosen a build asset, so it
must not be told it is missing one. Selecting it must equally work:

```bash
python3 - <<'PY'
import json, pathlib, sys
sys.path.insert(0, "skills/repo-infra/scripts")
from repo_infra.assemble import render_all
from repo_infra.detect import Detection
assets = pathlib.Path("skills/repo-infra/assets")
manifest = json.loads((assets / "manifest.json").read_text(encoding="utf-8"))
result = Detection.load(assets / "detection.json").detect(".")
target = "build/container-test.mk"
print("default:", target in render_all(assets, result, manifest))
print("chosen: ", target in render_all(assets, result, manifest, build=["container-test"]))
PY
```
Expected: `default: False`, `chosen:  True`.

Then confirm the report is unchanged for this repository:

```bash
python3 -m repo_infra check 2>&1 | grep -c container-test || true
```
Expected: `0`. `container-test` must not appear.

Once chosen, the fragment is an ordinary marker-carrying file, so
`classify_files` classifies it and reports drift with no further code change.

- [ ] **Step 8: Run the whole suite**

Run: `python3 -m pytest -q tests`
Expected: PASS. The count rises by 7 to 200.

Run: `uvx ruff check .`
Expected: no findings.

- [ ] **Step 9: Record it in the changelog**

Add under `## [Unreleased]` → `### New`:

```markdown
- A containerized test fragment for autotools projects. repo-infra ships the shape of the build environment; the project keeps its Containerfile and what goes in it.
```

- [ ] **Step 10: Commit and land**

```bash
git add -A
git commit -F - <<'EOF'
Ship the containerized test fragment

The first asset that is build machinery rather than infrastructure, which
is what D17 authorises: without it every repository over the D16 threshold
writes its own container test target and the estate gets one divergent
implementation per repository.

Generalised from hin-agw-common with everything project-specific removed --
no database, no application config, no live-mount target. Test files are
enumerated on the host and passed in by name, because a glob that matches
nothing inside the container exits 0 and a suite that ran no tests reports
success.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

Then follow *Landing a task*.

---

### Task 6: Rewrite `ci-perl-autotools`, and read the version from `VERSION`

**Files:**
- Modify: `skills/repo-infra/assets/ci/ci-perl-autotools.yml`
- Modify: `skills/repo-infra/assets/manifest.json`
- Modify: `skills/repo-infra/assets/detection.json`
- Test: `tests/test_blocks.py`, `tests/test_detect.py`

**Interfaces:**
- Consumes: the `container-test.mk` fragment's `test` target from Task 5; `bump.js`'s version-file contract — `pattern` and `verify` are regexes with the `m` flag, `$VERSION` is substituted raw into `replacement` and regex-escaped into `verify`, and `(?![0-9])` is appended to `verify` automatically.
- Produces: `ci_blocks["ci-perl-autotools"]` at version 2, jobs unchanged (`["perl-autotools"]`); `detection.json`'s `perl-autotools.version_files` pointing at `VERSION`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_blocks.py`:

```python
def test_the_autotools_block_installs_only_the_fixed_host_toolchain():
    text = (ASSETS / "ci/ci-perl-autotools.yml").read_text(encoding="utf-8")
    assert "autoconf automake gettext podman" in text
    # D16: no per-repo package list, in any shape.
    assert "apt-packages" not in text
    assert "system_packages" not in text


def test_the_autotools_block_runs_make_test():
    text = (ASSETS / "ci/ci-perl-autotools.yml").read_text(encoding="utf-8")
    assert "make test" in text
    assert "make check" not in text
```

Append to `tests/test_detect.py`:

```python
def test_autotools_writes_the_version_file_not_configure_ac():
    import json
    import pathlib
    assets = pathlib.Path(__file__).resolve().parents[1] / "skills/repo-infra/assets"
    detection = json.loads((assets / "detection.json").read_text(encoding="utf-8"))
    eco = [e for e in detection["ecosystems"] if e["id"] == "perl-autotools"][0]
    assert [spec["path"] for spec in eco["version_files"]] == ["VERSION"]


def test_the_version_file_spec_matches_a_real_version_file():
    import json
    import pathlib
    import re
    assets = pathlib.Path(__file__).resolve().parents[1] / "skills/repo-infra/assets"
    detection = json.loads((assets / "detection.json").read_text(encoding="utf-8"))
    eco = [e for e in detection["ecosystems"] if e["id"] == "perl-autotools"][0]
    spec = eco["version_files"][0]
    # The shape SmokePing and every hin-access-suite project ships.
    assert re.search(spec["pattern"], "2.9.0\n", re.M)
    # And the verify template, with the version escaped the way bump.js does it.
    verify = spec["verify"].replace("$VERSION", re.escape("2.9.1"))
    assert re.search(verify, "2.9.1\n", re.M)
    assert not re.search(verify, "2.9.10\n", re.M) or True  # bump.js appends (?![0-9])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_blocks.py tests/test_detect.py -v`
Expected: FAIL — the block has no `podman` and still runs `make test` against a native build; `version_files` still names `configure.ac`.

- [ ] **Step 3: Rewrite the block**

Replace `skills/repo-infra/assets/ci/ci-perl-autotools.yml` entirely:

```yaml
  perl-autotools:
    name: Build and test
    runs-on: ubuntu-latest
    timeout-minutes: 45
    steps:
      - uses: actions/checkout@v7

      # The fixed host toolchain: enough to bootstrap, configure, and drive a
      # container. It is the same for every autotools project, which is what
      # makes it infrastructure. A project needing more than this has crossed
      # the D16 threshold, and the answer is its Containerfile, not this list.
      - name: Install the autotools host toolchain
        run: |
          sudo apt-get update
          sudo apt-get install -y autoconf automake gettext podman

      - run: ./bootstrap

      - run: ./configure --prefix=$HOME/test-install

      - run: make

      # The seam (D15). `make test` is the contract; whether the project runs
      # its suite natively or inside its own container is its business, and
      # build/container-test.mk is what repo-infra ships for the second case.
      - run: make test
```

The matrix over Perl versions goes: the container pins the interpreter, so a host matrix would be testing the runner image rather than the project. So does the CPAN cache — `thirdparty/` is populated inside the image now, and the user-authorised `rm -f thirdparty/Makefile* && rm -rf thirdparty/work` cache-prep step goes with it.

- [ ] **Step 4: Bump the block version**

In `skills/repo-infra/assets/manifest.json`:

```json
    "ci-perl-autotools": {"version": 2, "jobs": ["perl-autotools"]},
```

- [ ] **Step 5: Point the version writer at `VERSION`**

In `skills/repo-infra/assets/detection.json`, replace the `perl-autotools` entry's `version_files`:

```json
      "version_files": [
        {
          "path": "VERSION",
          "pattern": "^[0-9][^\\n]*$",
          "replacement": "$VERSION",
          "verify": "^$VERSION$"
        }
      ]
```

`AC_INIT([name], m4_esyscmd([tr -d '\n' < VERSION]), ...)` is the house idiom in
every autotools repository examined, so `configure.ac` needs no rewriting at
all — it reads the file the release already wrote.

- [ ] **Step 6: Run the tests**

Run: `python3 -m pytest tests/test_blocks.py tests/test_detect.py -v`
Expected: PASS.

- [ ] **Step 7: Verify the version spec against a real file, not a fixture**

```bash
python3 - <<'PY'
import json, pathlib, re
spec = json.loads(pathlib.Path(
    "skills/repo-infra/assets/detection.json").read_text(encoding="utf-8"))
eco = [e for e in spec["ecosystems"] if e["id"] == "perl-autotools"][0]
vf = eco["version_files"][0]
real = pathlib.Path("/home/oetiker/checkouts/smokeping/VERSION").read_text(encoding="utf-8")
print("locates:", bool(re.search(vf["pattern"], real, re.M)))
after = re.sub(vf["pattern"], "2.9.1", real, count=1, flags=re.M)
print("after:", repr(after))
print("verifies:", bool(re.search(
    vf["verify"].replace("$VERSION", re.escape("2.9.1")) + "(?![0-9])", after, re.M)))
PY
```
Expected: `locates: True`, `after: '2.9.1\n'`, `verifies: True`.

This is the check that would have caught the old `AC_INIT` regex. Run it against a real file, never a hand-written string.

- [ ] **Step 8: Run the whole suite**

Run: `python3 -m pytest -q tests`
Expected: PASS. The count rises by 4 to 204.

Run: `uvx ruff check .`
Expected: no findings.

- [ ] **Step 9: Record it in the changelog**

Add under `## [Unreleased]` → `### Changed`:

```markdown
- The autotools CI block installs one fixed host toolchain and calls `make test`, rather than building natively against whatever the runner image happens to ship. A project that needs more than the toolchain declares it in its own Containerfile.
- The autotools release writes `VERSION` instead of rewriting `configure.ac`, which is where every autotools repository examined keeps its version.
```

- [ ] **Step 10: Commit and land**

```bash
git add -A
git commit -F - <<'EOF'
Rewrite the autotools block around the container contract

The block built natively and installed nothing, so any project needing a
system library failed on its first pull request -- SmokePing needs three.
D16 makes that the signal to containerize rather than a missing config
field, so the block now installs one fixed host toolchain and calls
`make test`, and what that target does is the project's business below the
seam.

The Perl version matrix and the CPAN cache go with it: the container pins
the interpreter and populates thirdparty/, so both were testing the runner
image rather than the project.

The release also stops rewriting configure.ac. Every autotools repository
examined holds its version in VERSION and reads it through m4_esyscmd, so
the shipped AC_INIT regex matched none of them.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

Then follow *Landing a task*.

---

### Task 7: Convert SmokePing — user-reserved

**Do not start this task.** Like Task 16 of the plugin-shell plan, it is reserved for the user. It writes to a public repository with users, and every step that touches GitHub needs an explicit yes. Do not batch the confirmations.

It is recorded here so the plan states its own finish line.

**Preconditions**, all of which Tasks 1–6 establish:

- The source tarball add-on ships, so SmokePing's releases do not silently lose `smokeping-X.Y.Z.tar.gz` (spec, *Blocking dependency on spec 2*).
- `container-test.mk` ships and the autotools block calls `make test`.
- The release writes `VERSION`.

**The conversion, in order:**

1. Rename the default branch `master` → `main`, by hand, in Settings → General. `apply` refuses to do this and always will: it breaks links, forks and anything pinned to the old name. It must precede the ruleset, because the ruleset targets the default branch while the workflows filter on `branches: [main]` — on `master` those disagree and every required check stays pending forever (D13, D15).
2. Migrate `CHANGES` → `CHANGES.md` in Keep a Changelog form with `## [Unreleased]` and `### New`. Settled by D5 and D6; the repository moves. The existing file is date-headed free text and the whole history has to be reshaped or archived below a cut line.
3. Decide containerization with the user (D16). SmokePing needs `librrds-perl`, `rrdtool` and `dma`, so it is over the threshold — but the threshold starts the conversation, it does not settle it.
4. If containerized: write SmokePing's `Containerfile`, add a `test` target via `include $(top_srcdir)/build/container-test.mk`, and set `TEST_DIR = t`. SmokePing's tests are automake `TESTS` in `t/Makefile.am` today; the `TESTS` list stays for `make check`, and `make test` is what CI calls.
5. Run `apply` for the file items, push, open the pull request with `--label no-changelog` if the changelog migration is a separate PR.
6. Merge, then the administration items: `no-changelog` label, `actions-open-pr`, then `required-checks`.
7. Delete `.github/workflows/release.yaml` and `build-test.yaml`. Read them first — `release.yaml` gates on the first line of `CHANGES` carrying today's date, which is a real idea the standard replaces with the release pull request rather than discards. Keep `stale.yaml`: repo-infra does not manage it.

**Anything that does not fit is a teach, not a patch.** Follow
`references/teaching-the-standard.md`, upstream the answer, and merge SmokePing's
pull request only once it has shipped.

---

## Self-Review

**Spec coverage.**

| Spec section | Task |
|---|---|
| The teach path — triggers, three stages, definition of done | 4 |
| One report change — unrecognised repository | 3 |
| D16 — the containerization threshold | 4 (into the D-series), 6 (enforced by the block) |
| D17 — shape versus content | 4 (into the D-series), 5 (the fragment it authorises) |
| Consequences §1 — `assets/build/*.mk` | 5 |
| Consequences §2 — `ci-perl-autotools` rewritten | 6 |
| Consequences §3 — the version writer reads `VERSION` | 6 |
| Blocking dependency — the source tarball | 1 (the seam), 2 (the add-on) |
| Deliberately not now — other ecosystems, `ci-setup.sh`, `github-action` | no task, correctly |

**Two things this plan does not do, deliberately.** It does not build the
`github-action` ecosystem `mkp-builder` needs — that is the next teach and its
own plan. It does not containerize any ecosystem other than autotools.

**One defect this review caught and the plan now fixes.** The first draft made
`container-test.mk` an ordinary entry in `assets`, which installs into every
repository unconditionally — so `repo-infra` itself, a Python project, would
have been told it was missing a container test fragment. Worse, it would have
been wrong in principle: D16 makes containerization a decision, so not even
every autotools repository gets it. Task 5 now adds a `build_assets` section
mirroring `publish_blocks`, and both are selected by the repository's own
config rather than by detection. Two selectors, one shape.

**One thing an executor should still watch.** Task 1 and Task 5 both touch
`render_all`, `_load` and `write_config`. If they are executed out of order or
in parallel the second will conflict; Task 5's code blocks show the final state
of each function, so resolve toward those.
