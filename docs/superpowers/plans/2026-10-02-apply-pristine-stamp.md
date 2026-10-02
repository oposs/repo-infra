# apply pristine stamp (D29) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `apply` decides "unedited, safe to overwrite" from a stamp it wrote itself, not from the plugin's git history, and hands every other case to the LLM with the file's history.

**Architecture:** `markers.py` gains three pure functions (`stamp`, `strip_stamp`, `pristine`). `apply.py` stamps every rendered file it writes and overwrites an outdated file only when `pristine()` is true; otherwise it writes `.new`, `.current`, `.path`, `.log` and raises `NeedsMerge`. The plugin-history lookup and the `plugin_root` parameter go away. Two unrelated small fixes ride along: compact JSON for `.github/repo-infra.json`, and test isolation from the developer's git config. A generations record stops asset text from changing under an unchanged marker.

**Tech Stack:** Python 3.11+ (stdlib only), pytest, GNU make.

**Spec:** `docs/superpowers/specs/2026-10-02-apply-pristine-stamp-design.md`

## Global Constraints

- Stamp format: the first marker line of the file ends in ` sha256=<16 lowercase hex digits>`; the digits are the first 16 of the SHA-256 (UTF-8) of the file text with that suffix removed.
- An assembled file has one stamp, on its first marker. A directory asset stamps each file.
- `apply --from` writes no stamp, and strips one if the handed-back text carries it.
- `--from` commit subject: `Merge <item> from the repo-infra standard with local edits`. Other item commits keep `Install <item> from the repo-infra standard`.
- Merge files under `repo-infra/merge/` in the git dir: `{name}.new`, `{name}.current`, `{name}.path`, `{name}.log`. No `{name}.base`.
- `.log` content: `git log --format='%h %ad %s' --date=short -- <path>` run in the target repository, newest first.
- `check` compares marker versions only; the stamp never makes a file `outdated` or `conflict`.
- No em dashes in any shipped text (`tests/test_no_em_dash.py`). English for code, comments and docs.
- Tests and builds use at most 4 cores. Run Python tests as `python3 -m pytest -q -m "not container" tests` (what `make test` runs).
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A checkout with CRLF line endings (`core.autocrlf=true`): the stamp no longer matches, and `apply` must stop with `NeedsMerge`, never overwrite. Pinned in Task 2.
2. The LLM hands back with `--from` a file that still carries a stamp (copied from an older install): `apply` strips it, so the next upgrade stops with `NeedsMerge` instead of overwriting the hand merge. Pinned in Task 2.
3. A freshly stamped file at the current generation: `check` reports `ok` with no "local edits" detail; the stamp itself is not an edit. Pinned in Task 2.
4. Someone deletes the stamp suffix or changes one digit by hand: treated as not pristine, `NeedsMerge`. Pinned in Task 1 and Task 2.
5. The target is not a git repository, or the path has no commits yet: `NeedsMerge` still happens and `.log` says why there is no history; no crash. Pinned in Task 2.

---

### Task 1: Stamp helpers in markers.py

**Files:**
- Modify: `skills/repo-infra/scripts/repo_infra/markers.py`
- Test: `tests/test_markers.py`

**Interfaces:**
- Produces: `stamp(text: str) -> str`, `strip_stamp(text: str) -> str`, `pristine(text: str) -> bool | None` (True: stamp matches; False: stamp present, text changed; None: no stamp or no marker).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_markers.py`)

```python
from repo_infra.markers import parse_markers, pristine, stamp, strip_stamp

ASSEMBLED = ("name: CI\n# repo-infra: ci v2\njobs:\n"
             "  # repo-infra: ci-rust v3\n  rust:\n    runs-on: x\n")


def test_stamp_goes_on_the_first_marker_only():
    stamped = stamp(ASSEMBLED)
    lines = stamped.splitlines()
    assert lines[1].startswith("# repo-infra: ci v2 sha256=")
    assert len(lines[1].rsplit("=", 1)[1]) == 16
    assert lines[3] == "  # repo-infra: ci-rust v3"


def test_a_stamped_file_still_parses_to_the_same_markers():
    assert parse_markers(stamp(ASSEMBLED)) == parse_markers(ASSEMBLED)


def test_strip_stamp_undoes_stamp():
    assert strip_stamp(stamp(ASSEMBLED)) == ASSEMBLED


def test_stamping_twice_gives_the_same_text():
    assert stamp(stamp(ASSEMBLED)) == stamp(ASSEMBLED)


def test_pristine_is_true_for_untouched_stamped_text():
    assert pristine(stamp(ASSEMBLED)) is True


def test_pristine_is_false_after_an_edit_anywhere():
    edited = stamp(ASSEMBLED).replace("runs-on: x", "runs-on: y")
    assert pristine(edited) is False


def test_pristine_is_false_when_a_digit_of_the_stamp_changes():
    stamped = stamp(ASSEMBLED)
    digit = stamped.index("sha256=") + len("sha256=")
    flipped = "0" if stamped[digit] != "0" else "1"
    assert pristine(stamped[:digit] + flipped + stamped[digit + 1:]) is False


def test_pristine_is_none_without_a_stamp():
    assert pristine(ASSEMBLED) is None


def test_pristine_is_none_without_a_marker():
    assert pristine("no marker here\n") is None


def test_stamp_keeps_trailing_prose_on_the_marker_line():
    text = "# repo-infra: ci v2 do not delete this line\nx\n"
    stamped = stamp(text)
    assert stamped.splitlines()[0].startswith("# repo-infra: ci v2 do not delete this line sha256=")
    assert pristine(stamped) is True


def test_stamp_works_for_each_comment_style():
    for comment in ("#", "//", "--", "dnl"):
        text = f"{comment} repo-infra: x v1\nbody\n"
        assert pristine(stamp(text)) is True


def test_crlf_text_is_never_pristine_after_conversion():
    lf = stamp("# repo-infra: ci v2\njobs:\n")
    assert pristine(lf.replace("\n", "\r\n")) is not True
```

- [ ] **Step 2: Run them, expect ImportError**

Run: `python3 -m pytest -q tests/test_markers.py`
Expected: FAIL, `ImportError: cannot import name 'pristine'`.

- [ ] **Step 3: Implement** (append to `markers.py`; add `import hashlib` at the top; also extend the module docstring by one paragraph: "The stamp (D29) is a different thing from a content hash for drift: it only answers whether a file is byte for byte what apply wrote, so apply may overwrite it. check never reads it.")

```python
# D29. Appended to the file's first marker line by apply, and nothing else.
_STAMP = re.compile(r" sha256=([0-9a-f]{16})$")


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _first_marker(lines):
    return next((i for i, line in enumerate(lines) if _MARKER.match(line)), None)


def strip_stamp(text):
    """`text` without the stamp on its first marker line, if it has one."""
    lines = text.split("\n")
    first = _first_marker(lines)
    if first is not None:
        lines[first] = _STAMP.sub("", lines[first])
    return "\n".join(lines)


def stamp(text):
    """`text` with its first marker line stamped with the digest of the rest."""
    bare = strip_stamp(text)
    lines = bare.split("\n")
    first = _first_marker(lines)
    if first is None:
        raise ValueError("no repo-infra marker to stamp")
    lines[first] = f"{lines[first]} sha256={_digest(bare)}"
    return "\n".join(lines)


def pristine(text):
    """True when the stamp matches the text, False when the text changed
    since it was stamped, None when there is no stamp to judge by."""
    lines = text.split("\n")
    first = _first_marker(lines)
    if first is None:
        return None
    found = _STAMP.search(lines[first])
    if found is None:
        return None
    return found.group(1) == _digest(strip_stamp(text))
```

Note for CRLF: after conversion the marker line ends in `\r`, so `_STAMP` (anchored at `$` after the digits) does not match and `pristine` returns None. That is the safe answer.

- [ ] **Step 4: Run the tests, expect PASS**

Run: `python3 -m pytest -q tests/test_markers.py`

- [ ] **Step 5: Commit**

```bash
git add skills/repo-infra/scripts/repo_infra/markers.py tests/test_markers.py
git commit -m "markers: stamp, strip_stamp and pristine (D29)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: apply decides by the stamp and hands over the history

**Files:**
- Modify: `skills/repo-infra/scripts/repo_infra/apply.py` (NeedsMerge, `apply_file_item`, `_prepare_merge`, `_apply_dir_asset`; delete `_asset_source`, `base_version_of`, `_dir_sources`, `_common_parts`; drop the `plugin_root` parameter)
- Modify: `skills/repo-infra/scripts/repo_infra/migrate.py:159` (stamp the replaced `release-pr.yml`)
- Modify: `skills/repo-infra/scripts/repo_infra/state.py:163` (compare without the stamp)
- Modify: `skills/repo-infra/scripts/repo_infra/cli.py:163,189` (stop passing `plugin_root`)
- Modify: `tests/test_apply_files.py`, `tests/test_cli.py`, `tests/test_migrate.py` and any other caller of `apply_file_item` (find them: `grep -rn "apply_file_item\|plugin_checkout\|base_version_of\|lib_plugin" tests`)
- Modify: `tests/conftest.py` (delete the `plugin_checkout` fixture and its `OLD`/`NEW` constants once nothing uses them)
- Test: `tests/test_apply_files.py`, `tests/test_state.py`

**Interfaces:**
- Consumes: `stamp`, `strip_stamp`, `pristine` from Task 1.
- Produces: `apply_file_item(repo_root, name, rendered, items, merged=None) -> list[str]`; `NeedsMerge(name, new, current, log, target)` with attributes `.name .new .current .log .target` (paths); merge files `{name}.new/.current/.path/.log`.

- [ ] **Step 1: Rewrite the tests in `tests/test_apply_files.py`**

Remove the `base_version_of` import and test, the `lib_plugin` fixture, and every `plugin_checkout`/`lib_plugin`/`tmp_path` argument passed as `plugin_root`. Tests that need `.log` need a real git repository; add this helper at the top:

```python
from repo_infra.markers import pristine, stamp, strip_stamp


def git_repo(path):
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)
    return path


def commit_all(path, message):
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=path, check=True, capture_output=True)
```

Replace the old single-file upgrade tests with:

```python
def test_a_missing_file_is_installed_stamped(tmp_path):
    written = apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "missing", "")])
    assert written == [".github/workflows/ci.yml"]
    text = (tmp_path / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert strip_stamp(text) == ASSET and pristine(text) is True


def test_an_unedited_stamped_file_is_upgraded_in_place(tmp_path):
    installed(tmp_path, stamp(OLD))
    written = apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")])
    assert written == [".github/workflows/ci.yml"]
    text = (tmp_path / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert strip_stamp(text) == ASSET and pristine(text) is True


def test_an_edited_stamped_file_hands_over_new_current_path_and_log(tmp_path):
    git_repo(tmp_path)
    installed(tmp_path, stamp(OLD))
    commit_all(tmp_path, "Install ci from the repo-infra standard")
    edited = stamp(OLD).replace("fmt:", "fmt:\n    timeout-minutes: 30")
    installed(tmp_path, edited)
    commit_all(tmp_path, "ci: longer timeout")
    with pytest.raises(NeedsMerge) as raised:
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")])
    scratch = tmp_path / ".git" / MERGE_DIR
    assert raised.value.new.read_text(encoding="utf-8") == ASSET
    assert raised.value.current.read_text(encoding="utf-8") == edited
    assert (scratch / "ci.path").read_text(encoding="utf-8") == ".github/workflows/ci.yml\n"
    log = raised.value.log.read_text(encoding="utf-8").splitlines()
    assert [line.split(" ", 2)[2] for line in log] == [
        "ci: longer timeout", "Install ci from the repo-infra standard"]
    assert not (scratch / "ci.base").exists()
    assert (tmp_path / ".github/workflows/ci.yml").read_text(encoding="utf-8") == edited


def test_an_unstamped_old_file_hands_over_the_merge(tmp_path):
    # Files installed before D29 carry no stamp; the LLM decides from the log.
    git_repo(tmp_path)
    installed(tmp_path, OLD)
    with pytest.raises(NeedsMerge):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")])
    assert (tmp_path / ".github/workflows/ci.yml").read_text(encoding="utf-8") == OLD


def test_a_crlf_checkout_is_never_overwritten(tmp_path):
    git_repo(tmp_path)
    installed(tmp_path, stamp(OLD).replace("\n", "\r\n"))
    with pytest.raises(NeedsMerge):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")])


def test_a_deleted_stamp_hands_over_the_merge(tmp_path):
    git_repo(tmp_path)
    installed(tmp_path, strip_stamp(stamp(OLD)))
    with pytest.raises(NeedsMerge):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")])


def test_without_git_history_the_log_says_so(tmp_path):
    (tmp_path / ".git").mkdir()
    installed(tmp_path, OLD)
    with pytest.raises(NeedsMerge) as raised:
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")])
    assert raised.value.log.read_text(encoding="utf-8").startswith("(no history:")


def test_a_merge_handed_back_is_written_without_a_stamp(tmp_path):
    git_repo(tmp_path)
    installed(tmp_path, OLD.replace("fmt:", "fmt:\n    timeout-minutes: 15"))
    with pytest.raises(NeedsMerge):
        apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")])
    merged = tmp_path / "merged.yml"
    # Carries a stamp copied from somewhere: apply must strip it.
    merged.write_text(stamp(ASSET.replace("fmt:", "fmt:\n    timeout-minutes: 30")),
                      encoding="utf-8")
    apply_file_item(tmp_path, "ci", RENDERED, [Item("ci", "outdated", "")], merged=str(merged))
    text = (tmp_path / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert pristine(text) is None
    assert "timeout-minutes: 30" in text
    for suffix in ("new", "current", "path", "log"):
        assert not (tmp_path / ".git" / MERGE_DIR / f"ci.{suffix}").exists()
```

Keep `test_a_merged_file_at_the_wrong_version_is_refused`, `test_a_merge_prepared_against_a_now_stale_target_is_refused`, `test_from_without_a_prior_refusal_is_refused`, `test_a_successful_from_write_removes_its_own_scratch_files_but_not_anothers` and `test_a_conflict_is_never_applied`; change only their calls (no `plugin_root`; create the refusal with an unstamped `OLD` plus `git_repo(tmp_path)` instead of `plugin_checkout`). In the scratch-cleanup test, the suffix list becomes `("new", "current", "path", "log")`.

Replace the directory-asset tests (`LIB_V1`/`LIB_V2` stay, the `lib_plugin` fixture goes):

```python
def stamped(files):
    return {name: stamp(text) for name, text in files.items()}


def upgrade(tmp_path, merged=None):
    return apply_file_item(tmp_path, "workflow-lib", RENDERED_V2,
                           [Item("workflow-lib", "outdated", "")], merged=merged)


def test_an_unedited_directory_asset_is_upgraded_file_by_file(tmp_path):
    install(tmp_path, stamped(LIB_V1))
    assert upgrade(tmp_path) == sorted(RENDERED_V2)
    for name, text in LIB_V2.items():
        assert strip_stamp(on_disk(tmp_path, name)) == text
        assert pristine(on_disk(tmp_path, name)) is True


def test_a_file_already_at_the_new_generation_keeps_its_local_edits(tmp_path):
    edited = LIB_V2["bump.js"] + "// local\n"
    install(tmp_path, {"bump.js": edited, "version.js": stamp(LIB_V1["version.js"])})
    assert upgrade(tmp_path) == [LIB_TARGET + "assets.js", LIB_TARGET + "version.js"]
    assert on_disk(tmp_path, "bump.js") == edited


def test_an_edited_old_file_stops_the_upgrade_before_anything_is_written(tmp_path):
    git_repo(tmp_path)
    install(tmp_path, {"bump.js": stamp(LIB_V1["bump.js"]) + "// local\n",
                       "version.js": stamp(LIB_V1["version.js"])})
    with pytest.raises(NeedsMerge):
        upgrade(tmp_path)
    assert on_disk(tmp_path, "version.js") == stamp(LIB_V1["version.js"])
    assert not (tmp_path / LIB_TARGET / "assets.js").exists()
```

Keep `test_a_merged_file_goes_back_to_the_file_the_merge_was_prepared_for` and `test_a_merge_for_a_directory_asset_needs_a_prepared_merge`, adapted the same way. Delete `test_without_the_plugin_history_an_old_file_counts_as_edited` (replaced by `test_an_unstamped_old_file_hands_over_the_merge`). In `test_a_missing_directory_asset_installs_every_file`, compare `strip_stamp(...)` to the text.

Add to `tests/test_state.py`:

```python
from repo_infra.markers import stamp
from repo_infra.state import classify_files


def test_a_stamped_file_at_the_current_generation_is_ok_without_local_edits(tmp_path):
    text = "name: CI\n# repo-infra: ci v2\njobs: {}\n"
    target = tmp_path / ".github/workflows/ci.yml"
    target.parent.mkdir(parents=True)
    target.write_text(stamp(text), encoding="utf-8")
    items = classify_files(tmp_path, {".github/workflows/ci.yml": text}, {"assets": {}})
    assert [(i.name, i.state, i.detail) for i in items] == [("ci", "ok", "")]


def test_an_edited_stamped_file_at_the_current_generation_reports_local_edits(tmp_path):
    text = "name: CI\n# repo-infra: ci v2\njobs: {}\n"
    target = tmp_path / ".github/workflows/ci.yml"
    target.parent.mkdir(parents=True)
    target.write_text(stamp(text) + "# mine\n", encoding="utf-8")
    items = classify_files(tmp_path, {".github/workflows/ci.yml": text}, {"assets": {}})
    assert [(i.state, i.detail) for i in items] == [("ok", "local edits")]
```

(If `_dir_asset_names` needs a different manifest shape, read it in `state.py:80` and pass the smallest manifest it accepts.)

- [ ] **Step 2: Run, expect failures**

Run: `python3 -m pytest -q tests/test_apply_files.py tests/test_state.py`
Expected: FAIL (`apply_file_item()` takes `plugin_root`; no stamps written).

- [ ] **Step 3: Implement in `apply.py`**

Module docstring, second paragraph, becomes: "There is exactly one thing this module refuses to do. A file that is not byte for byte what apply last wrote (D29: its stamp is missing or does not match) may carry local edits, and merging a new generation into those is judgement, not mechanism. It writes the new rendering, the current file and the file's git log out and raises NeedsMerge. The model merges; the script keeps the irreversible half."

```python
from .markers import parse_markers, pristine, stamp, strip_stamp


class NeedsMerge(Exception):
    def __init__(self, name, new, current, log, target):
        super().__init__(
            f"{name}: {target} is not what apply last wrote (no stamp, or edited "
            f"since). Read {current}, {new} and the file's history in {log}, "
            f"merge, then re-run with --item {name} --from <merged file>")
        self.name, self.new, self.current, self.log, self.target = (
            name, new, current, log, target)
```

`apply_file_item(repo_root, name, rendered, items, merged=None)`:
- in the `merged` branch, write `strip_stamp(text)` instead of `text`, and clean up `("new", "current", "path", "log")`;
- `if len(targets) > 1: return _apply_dir_asset(repo_root, name, targets, wanted)`;
- missing: `return [write_asset(repo_root, path, stamp(expected))]`;
- outdated:

```python
    installed = (pathlib.Path(repo_root) / path).read_text(encoding="utf-8")
    if pristine(installed):
        return [write_asset(repo_root, path, stamp(expected))]
    _prepare_merge(repo_root, name, path, expected, installed)
```

`_prepare_merge(repo_root, name, path, expected, installed)`:

```python
def _prepare_merge(repo_root, name, path, expected, installed):
    scratch = _scratch_dir(repo_root)
    scratch.mkdir(parents=True, exist_ok=True)
    new_path = scratch / f"{name}.new"
    new_path.write_text(expected, encoding="utf-8")
    current_path = scratch / f"{name}.current"
    # The snapshot of what is on disk right now, so a later --from can refuse
    # to overwrite a different edit that lands while the merge is prepared.
    current_path.write_text(installed, encoding="utf-8")
    # Which file the merge is for, so --from writes it back to that file even
    # when the asset ships several.
    (scratch / f"{name}.path").write_text(path + "\n", encoding="utf-8")
    # The history is what tells an edit from an older generation: a file only
    # apply commits touched has no local edits (commands/apply.md).
    try:
        log = git(repo_root, "log", "--format=%h %ad %s", "--date=short", "--", path)
    except ApplyError as error:
        log = f"(no history: {error})\n"
    log_path = scratch / f"{name}.log"
    log_path.write_text(log, encoding="utf-8")
    raise NeedsMerge(name, new_path, current_path, log_path, pathlib.Path(repo_root) / path)
```

`_apply_dir_asset(repo_root, name, targets, wanted)`: same loop as today, but a missing file appends `(path, stamp(expected))`, an outdated file appends `(path, stamp(expected))` when `pristine(installed)` is true, and otherwise calls `_prepare_merge(repo_root, name, path, expected, installed)`. Docstring: replace "byte for byte that generation from the plugin's own history" with "carries a matching stamp (D29)".

Delete `_asset_source`, `base_version_of`, `_dir_sources`, `_common_parts`.

In `migrate.py:159`: `write_asset(root, RELEASE_PR, stamp(rendered[RELEASE_PR]))`, importing `stamp` from `.markers`.

In `state.py:163`: `edited = strip_stamp(text) != expected_text`, importing `strip_stamp`.

In `cli.py`: delete `plugin_root = ASSETS.parent` (line 163) and drop the argument at line 189.

Update every other caller and test found by `grep -rn "apply_file_item\|plugin_checkout\|base_version_of\|lib_plugin\|\.base\b" tests skills`. Tests in `test_cli.py`/`test_migrate.py` that assert file contents after `apply` must compare `strip_stamp(...)` or check `pristine(...) is True`.

- [ ] **Step 4: Run the whole Python suite**

Run: `python3 -m pytest -q -m "not container" tests`
Expected: PASS. Then `uvx ruff check .`: clean.

- [ ] **Step 5: Commit**

```bash
git add -A skills/repo-infra/scripts tests
git commit -m "apply: decide by the stamp it wrote, not the plugin's history (D29)

The installed plugin is a copy without .git, so base_version_of found
nothing and every changed file of every installed user stopped with
NeedsMerge and an empty base (seen on oetiker/mdmost#30). It also
compared assembled files against their frame alone, and took the
newest of two texts that share a marker version.

apply now stamps each rendered file it writes and overwrites an
outdated file only when the stamp matches. Otherwise it hands over
.new, .current, .path and the file's git log as .log.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `--from` commits say so, and the skill text explains the log

**Files:**
- Modify: `skills/repo-infra/scripts/repo_infra/apply.py` (`commit_item`)
- Modify: `skills/repo-infra/scripts/repo_infra/cli.py:196`
- Modify: `commands/apply.md` (section "If it exits with `NeedsMerge`")
- Modify: `skills/repo-infra/SKILL.md` (point 2 of "The four things that will surprise you")
- Modify: `skills/repo-infra/references/conventions.md` (section "Markers record a generation, never a content hash")
- Test: `tests/test_apply_files.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `NeedsMerge` and merge files from Task 2.
- Produces: `commit_item(repo_root, name, paths, merged=False) -> str | None`.

- [ ] **Step 1: Failing tests**

In `tests/test_apply_files.py`:

```python
from repo_infra.apply import commit_item


def test_a_hand_merge_is_committed_under_its_own_subject(tmp_path):
    git_repo(tmp_path)
    installed(tmp_path, ASSET)
    commit_item(tmp_path, "ci", [".github/workflows/ci.yml"], merged=True)
    subject = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=tmp_path,
                             capture_output=True, text=True, check=True).stdout.strip()
    assert subject == "Merge ci from the repo-infra standard with local edits"


def test_an_install_keeps_the_install_subject(tmp_path):
    git_repo(tmp_path)
    installed(tmp_path, ASSET)
    commit_item(tmp_path, "ci", [".github/workflows/ci.yml"])
    subject = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=tmp_path,
                             capture_output=True, text=True, check=True).stdout.strip()
    assert subject == "Install ci from the repo-infra standard"
```

In `tests/test_cli.py`, add one end-to-end test next to the existing `apply` tests, using their fixtures: prepare a merge with `apply --item <x>` on an edited file, hand back the `.new` file with `--from`, and assert `git log -1 --format=%s` is `Merge <x> from the repo-infra standard with local edits`.

- [ ] **Step 2: Run, expect FAIL** (`commit_item() got an unexpected keyword argument 'merged'`).

Run: `python3 -m pytest -q tests/test_apply_files.py tests/test_cli.py`

- [ ] **Step 3: Implement**

```python
def commit_item(repo_root, name, paths, merged=False):
    """One commit per item, so any single item can be dropped at review.

    A hand merge gets its own subject: the next NeedsMerge hands the LLM the
    file's log, and an Install commit there means "no local edits" (D29).
    """
    if not paths:
        return None
    subject = (f"Merge {name} from the repo-infra standard with local edits" if merged
               else f"Install {name} from the repo-infra standard")
    git(repo_root, "add", *paths)
    git(repo_root, "commit", "-m", f"{subject}\n\n{TRAILER}")
    return git(repo_root, "rev-parse", "HEAD").strip()
```

`cli.py:196`: `commit_item(args.root, name, written, merged=bool(args.from_file))`.

Replace the `commands/apply.md` section "If it exits with `NeedsMerge`" with:

```markdown
## If it exits with `NeedsMerge`

The file it names is not what `apply` last wrote: it has no stamp (installed
before v0.3.1) or was edited since. `apply` wrote four files under
`repo-infra/merge/` in the git dir (the error prints their full paths):
`{name}.new` (the new rendering), `{name}.current` (the file now),
`{name}.path` (which file) and `{name}.log` (the file's `git log`, newest
first).

Read the log first.

- Every commit is `Install <item> from the repo-infra standard`, `Migrate to
  ...`, or a commit that brought a repo-infra file in by hand during a
  conversion: the file has no local edits. Hand `.new` back unchanged:
  `apply --item <name> --from <path to {name}.new>`.
- Any other commit, including `Merge <item> ... with local edits`, may carry
  an edit. Read it (`git show <hash> -- <path>`), carry the edit into a copy
  of `.new`, and hand that back with `--from`. When a base helps,
  `git show <hash>:<path>` at the last `Install` commit before the edit is
  one.

The merged file must carry the new marker version. For an asset that ships
several files, such as `workflow-lib`, the merge covers the one file the
error names, and nothing else is written until it is back. Run `apply` again
afterwards: it upgrades the remaining files, or names the next one. Never drop
a local edit: it is there for a reason, and the reason is usually not visible
in the diff.
```

`SKILL.md` point 2 becomes:

```markdown
2. **`apply` overwrites only what it wrote itself.** Each file it writes
   carries a stamp on its first marker line. A file without a matching stamp
   stops the run: `apply` writes `{name}.new`, `{name}.current`,
   `{name}.path` and `{name}.log` under `repo-infra/merge/` in the git dir
   and raises `NeedsMerge`. The log tells an edit from an older generation;
   `commands/apply.md` says how to read it. Hand the result back with
   `apply --item <name> --from <path>`. If the target changed since the
   refusal, the re-run refuses again rather than clobbering the newer edit.
```

Append to the conventions.md markers section:

```markdown
### The stamp (D29)

Every file `apply` writes from a rendered asset ends its first marker line in
` sha256=<16 hex digits>`, the start of the SHA-256 of the file without that
suffix. It answers one question: is this file byte for byte what `apply`
wrote? If so, an upgrade overwrites it. `check` never reads it, so the
argument above stands. A hand merge (`--from`) gets no stamp, so the next
upgrade stops at it again. This replaced looking the old generation up in the
plugin's git history, which an installed plugin does not have.
```

- [ ] **Step 4: Run** `python3 -m pytest -q -m "not container" tests` and `uvx ruff check .`; expect PASS (`test_no_em_dash.py` and `test_prose_skills.py` cover the new text).

- [ ] **Step 5: Commit**

```bash
git add -A skills commands tests
git commit -m "apply: a hand merge commits as Merge, and the skill reads the log

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: A changed asset must change its marker version

**Files:**
- Create: `tests/generations.py` (the scanner and `make generations` writer)
- Create: `skills/repo-infra/assets/generations.json`
- Create: `tests/test_generations.py`
- Modify: `Makefile` (target `generations`, add to `.PHONY`)

**Interfaces:**
- Produces: `generations.scan(assets_root) -> dict[str, tuple[int, str]]` (path relative to `assets/` -> (first marker version, full sha256 hex)); record format `{"<path>": {"<version>": "<sha256>"}}`, every version ever recorded kept.

- [ ] **Step 1: Failing test** `tests/test_generations.py`

```python
import json
import pathlib

import generations

ASSETS = pathlib.Path(__file__).resolve().parents[1] / "skills/repo-infra/assets"
RECORD = ASSETS / "generations.json"


def test_every_asset_text_is_recorded_under_its_marker_version():
    recorded = json.loads(RECORD.read_text(encoding="utf-8"))
    problems = []
    for path, (version, digest) in sorted(generations.scan(ASSETS).items()):
        known = recorded.get(path, {}).get(str(version))
        if known is None:
            problems.append(f"{path}: v{version} is not recorded; run make generations")
        elif known != digest:
            problems.append(f"{path}: the text changed but the marker still says "
                            f"v{version}; bump the marker, then run make generations")
    assert not problems, "\n".join(problems)


def test_record_refuses_to_overwrite_a_version(tmp_path):
    (tmp_path / "a.yml").write_text("# repo-infra: a v1\nx\n", encoding="utf-8")
    record = {"a.yml": {"1": "0" * 64}}
    try:
        generations.updated(record, generations.scan(tmp_path))
    except ValueError as error:
        assert "bump the marker" in str(error)
    else:
        raise AssertionError("an existing version was overwritten")


def test_record_adds_a_new_version_and_keeps_the_old(tmp_path):
    (tmp_path / "a.yml").write_text("# repo-infra: a v2\ny\n", encoding="utf-8")
    record = generations.updated({"a.yml": {"1": "0" * 64}}, generations.scan(tmp_path))
    assert set(record["a.yml"]) == {"1", "2"}
```

`tests/` is on `sys.path` for pytest (rootdir conftest); if `import generations` fails, add `pythonpath = tests skills/repo-infra/scripts` to `pytest.ini` after checking what it already sets.

- [ ] **Step 2: Run, expect FAIL** (`ModuleNotFoundError: generations`).

- [ ] **Step 3: Implement `tests/generations.py`**

```python
"""The text of every marked asset, recorded under its marker version.

A test fails when an asset's text changes and its marker version does not.
PR #43 reworded a comment in changelog.yml and kept v3, so two repositories
both at "v3" held different files. `make generations` records a new version
and refuses to change a recorded one.
"""

import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/repo-infra/scripts"))
from repo_infra.markers import parse_markers  # noqa: E402

ASSETS = pathlib.Path(__file__).resolve().parents[1] / "skills/repo-infra/assets"
RECORD = ASSETS / "generations.json"


def scan(assets_root):
    found = {}
    for path in sorted(pathlib.Path(assets_root).rglob("*")):
        if not path.is_file() or path.name == "generations.json":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        markers = parse_markers(text)
        if markers:
            found[str(path.relative_to(assets_root))] = (
                markers[0].version, hashlib.sha256(text.encode("utf-8")).hexdigest())
    return found


def updated(record, scanned):
    record = {path: dict(versions) for path, versions in record.items()}
    for path, (version, digest) in scanned.items():
        known = record.setdefault(path, {}).get(str(version))
        if known is not None and known != digest:
            raise ValueError(f"{path}: v{version} is recorded with other text; "
                             "bump the marker")
        record[path][str(version)] = digest
    return record


if __name__ == "__main__":
    current = json.loads(RECORD.read_text(encoding="utf-8")) if RECORD.is_file() else {}
    try:
        new = updated(current, scan(ASSETS))
    except ValueError as error:
        sys.exit(str(error))
    RECORD.write_text(json.dumps(new, indent=2, sort_keys=True) + "\n", encoding="utf-8")
```

Makefile (add `generations` to `.PHONY`):

```make
# D29: records each marked asset's text under its marker version. Run after
# bumping a marker; it refuses when the text changed and the marker did not.
generations:
	python3 tests/generations.py
```

Run `make generations` once to create `skills/repo-infra/assets/generations.json` (the first run records today's 30 files). Check that `manifest.json` validation or the plugin loader does not choke on the extra JSON file under `assets/` (`grep -rn "assets.*json\|rglob" skills/repo-infra/scripts`); `scan` already skips it.

- [ ] **Step 4: Run** `python3 -m pytest -q -m "not container" tests`; expect PASS.

- [ ] **Step 5: Commit**

```bash
git add Makefile tests/generations.py tests/test_generations.py skills/repo-infra/assets/generations.json pytest.ini
git commit -m "tests: an asset whose text changes must bump its marker

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: repo-infra.json keeps short lists on one line

**Files:**
- Modify: `skills/repo-infra/scripts/repo_infra/apply.py` (`config_text`)
- Test: `tests/test_apply_files.py` (next to the existing config tests)

**Interfaces:**
- Produces: `config_text(data, original=None) -> str`, same signature.

- [ ] **Step 1: Failing tests**

```python
from repo_infra.apply import config_text

MDMOST = {
    "ecosystems": ["rust"],
    "ci": ["ci-man", "ci-rust-musl"],
    "release_assets": ["mdmost-*-x86_64-unknown-linux-musl.tar.gz",
                       "mdmost-*-aarch64-unknown-linux-musl.tar.gz",
                       "mdmost_*_amd64.deb"],
    "rust": {"lint": ["mdmost"], "test": ["mdmost", "pulldown-latex"]},
    "debian": {"distribution": "stable", "component": "main"},
    "empty": [],
}


def test_short_scalar_lists_stay_on_one_line():
    text = config_text(MDMOST)
    assert '  "ecosystems": ["rust"],\n' in text
    assert '  "ci": ["ci-man", "ci-rust-musl"],\n' in text
    assert '  "debian": {"distribution": "stable", "component": "main"},\n' in text
    assert '  "empty": [],\n' in text


def test_a_list_wider_than_80_columns_breaks_one_value_per_line():
    text = config_text(MDMOST)
    assert '  "release_assets": [\n    "mdmost-*-x86_64-unknown-linux-musl.tar.gz",\n' in text


def test_a_nested_object_breaks_but_its_short_lists_do_not():
    text = config_text(MDMOST)
    assert '  "rust": {\n    "lint": ["mdmost"],\n    "test": ["mdmost", "pulldown-latex"]\n  },\n' in text


def test_the_text_reads_back_as_the_same_data():
    assert json.loads(config_text(MDMOST)) == MDMOST


def test_the_indent_of_the_original_is_kept():
    text = config_text({"a": {"b": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]}},
                       original='{\n    "a": 1\n}\n')
    assert text.startswith('{\n    "a": {\n        "b": [')
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement** (replace the `return json.dumps(...)` line of `config_text` with `return _compact(data, indent, 0) + newline`, and extend its docstring: "An array or object of scalars stays on one line when it fits in 80 columns; oetiker/mdmost#30 showed `"ci": ["ci-man", "ci-rust-musl"]` turned into four lines.")

```python
WIDTH = 80


def _compact(value, indent, level, prefix=0):
    unit = indent if isinstance(indent, str) else " " * indent
    if isinstance(value, (dict, list)) and value:
        items = list(value.values()) if isinstance(value, dict) else value
        one_line = json.dumps(value, separators=(", ", ": "))
        if (not any(isinstance(v, (dict, list)) for v in items)
                and len(unit) * level + prefix + len(one_line) + 1 <= WIDTH):
            return one_line
        inner = unit * (level + 1)
        if isinstance(value, dict):
            parts = []
            for key, item in value.items():
                head = json.dumps(key) + ": "
                parts.append(inner + head + _compact(item, indent, level + 1, len(head)))
            return "{\n" + ",\n".join(parts) + "\n" + unit * level + "}"
        parts = [inner + _compact(item, indent, level + 1) for item in value]
        return "[\n" + ",\n".join(parts) + "\n" + unit * level + "]"
    return json.dumps(value)
```

(`+ 1` counts the trailing comma.)

- [ ] **Step 4: Run** `python3 -m pytest -q -m "not container" tests`; expect PASS (existing config tests included).

- [ ] **Step 5: Commit**

```bash
git add skills/repo-infra/scripts/repo_infra/apply.py tests/test_apply_files.py
git commit -m "apply: keep short lists in repo-infra.json on one line

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Tests run without the developer's git config

**Files:**
- Modify: `tests/conftest.py` (`git_identity` fixture)

- [ ] **Step 1: Change the fixture**

```python
@pytest.fixture(autouse=True)
def git_identity(monkeypatch):
    """Run git as a fresh GitHub runner does: no global or system config, and
    an identity from the environment.

    The runner has no git identity and no host name git can build one from,
    so "git commit" fails there with "Author identity unknown". A developer
    machine guesses one, which hid six such tests until the PR #44 run. A
    global setting such as commit signing or init.defaultBranch would hide
    the next difference the same way.
    """
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.com")
```

- [ ] **Step 2: Run** `python3 -m pytest -q -m "not container" tests`. A test that now fails depended on the developer's config: fix the test (for example pass `-b main` to `git init`), never the fixture.

- [ ] **Step 3: Commit**

```bash
git add tests
git commit -m "tests: run git without the developer's global config

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: CHANGES and the full gate

**Files:**
- Modify: `CHANGES.md` (`## [Unreleased]`, `### Fixed`)

- [ ] **Step 1: Entries** (writing-style skill rules; no release header):

```markdown
- `apply` with the installed plugin no longer stops on every changed workflow file with "local edits present". Files it writes now carry a stamp, and an unedited file is upgraded in place. A file without a stamp, from earlier versions, stops once with its git history next to it, so the merge can tell an edit from an older version.
- `apply` keeps short lists in `.github/repo-infra.json` on one line, such as `"ci": ["ci-man", "ci-rust-musl"]`, instead of rewriting the file one value per line.
```

- [ ] **Step 2: Gate**

Run: `make check`
Expected: exit 0; note the Python and JS pass counts for the PR.

- [ ] **Step 3: Commit**

```bash
git add CHANGES.md
git commit -m "changelog: D29 stamp and compact repo-infra.json

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## After the plan (owner-gated, not tasks)

1. Push `fix/apply-pristine-stamp`, open the repo-infra PR, CI green, merge.
2. Dispatch **Create release PR** with `bugfix` (v0.3.1), merge the release PR, check the tag and the published release.
3. Run `Track plugin versions` in oposs/claude-plugins, then `claude plugin marketplace update oposs-plugins` and `claude plugin update repo-infra@oposs-plugins`.
4. Proof: `check` on mdmost with the installed v0.3.1 plugin reports everything `ok`.
