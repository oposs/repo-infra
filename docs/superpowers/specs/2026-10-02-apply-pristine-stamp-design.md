# apply: a pristine stamp instead of the plugin's history (D29)

Status: proposed, 2026-10-02.

## Problem

On an upgrade, `apply` must decide for each installed file whether it is
still what `apply` wrote. If so, it overwrites it; if not, it stops with
`NeedsMerge`. Today it decides by looking the old generation up in the
plugin's own git history (`base_version_of`) and comparing bytes. That fails
in three ways, all seen on the mdmost upgrade to v0.3.0 (oetiker/mdmost#30):

1. The installed plugin (`~/.claude/plugins/cache/...`) is a copy without
   `.git`. The lookup finds nothing, so every changed file of every installed
   user ends in `NeedsMerge` with an empty base.
2. An assembled file (`ci.yml`, `release-publish.yml`, `release-build.yml`)
   is a frame plus one block per add-on. The lookup finds the frame alone, so
   every block shows up as a local edit, even from a git checkout.
3. Two texts can carry one marker version: PR #43 reworded a comment in
   `changelog.yml` and kept `v3`. The lookup takes the newer text as the base
   of a repository that has the older one. A squash merge of the plugin's own
   pull requests drops in-between generations from `main` the same way.

## Decision

`apply` settles the common case alone and hands the rest to the LLM running
the skill, with the material it needs. It does not try to prove every case.

### 1. The stamp

Every file `apply` writes from a rendered asset carries a stamp: the first
marker line of the file gets the suffix ` sha256=<16 hex digits>`, for
example `# repo-infra: ci v2 sha256=3f1c9a0b7d2e4f61`. The digits are the
first 16 of the SHA-256 of the file's text with that suffix removed. The
marker regex already allows trailing text, so `check` and every other marker
reader keep working unchanged.

- An assembled file has one stamp, on its first marker, covering the whole
  file, blocks included.
- A directory asset (`workflow-lib`) stamps each of its files.
- `apply --from` (a merge by hand) writes the file without a stamp. The text
  holds local edits, and a stamp would let the next upgrade overwrite them.

On an upgrade of an outdated file:

- stamp present and matching: overwrite with the new rendering, stamped.
- stamp missing or not matching: `NeedsMerge` (below).

A file at the current generation is not touched, stamp or not, as today.

The stamp answers "is this byte for byte what apply wrote?". It is not drift
detection, which D11 rejected a content hash for: `check` still compares
marker versions only, and an edited file at the current generation stays
`ok`.

### 2. `NeedsMerge` hands over material, not a base

`base_version_of` and the plugin-history lookup go away, and with them the
`{name}.base` file. `apply` writes, under `repo-infra/merge/` in the git dir:

- `{name}.new`: the new rendering (unstamped; `apply --from` decides).
- `{name}.current`: the file as it is now (the staleness guard, unchanged).
- `{name}.path`: which file the merge is for (unchanged).
- `{name}.log`: the target repository's history of that path,
  `git log --format='%h %ad %s' --date=short -- <path>`, newest first.

The `NeedsMerge` message names `.new`, `.current` and `.log`.

The `apply` skill text tells the LLM how to proceed:

- If every commit in the log since the file was first installed is an
  `apply` commit (`Install <item> from the repo-infra standard`, `Migrate to
  ...`), the file has no local edits: hand
  `.new` back unchanged with `--from`.
- Otherwise read the other commits (`git show <hash> -- <path>`) to see the
  local edits, carry them into `.new`, and hand the result back with
  `--from`. `git show <hash>:<path>` at the last `apply` commit before the
  edits is a base when one is needed.
- An `Install` commit made by `--from` holds merged text; the skill says so,
  and the commit subject says so too (section 3).

Files installed before the stamp existed take this path once. The next write
stamps them. There is no other code for the old format.

### 3. `--from` commits say so

`apply --from` commits with the subject `Merge <item> from the repo-infra
standard with local edits`, so the log in section 2 tells the two kinds of
commit apart.

### 4. A changed asset must change its version

A new file, `skills/repo-infra/assets/generations.json`, records for each
file under `assets/` that carries a marker its marker version and the SHA-256
of its text. A test fails when an asset's text changes and its marker version
does not ("bump the marker"), and when the version changes and the record does
not ("run make generations"). `make generations` rewrites the record. This
stops problem 3 at its source and needs no git history, so it runs in CI.

### 5. `.github/repo-infra.json` keeps short lists on one line

`config_text` writes an array or object on one line when it holds only
scalars and fits in 80 columns at its indent, otherwise one value per line.
mdmost#30 showed the migration turning `"ci": ["ci-man", "ci-rust-musl"]`
into four lines, and every other short list with it.

### 6. Tests run without the developer's git config

The autouse fixture in `tests/conftest.py` also sets
`GIT_CONFIG_GLOBAL=/dev/null` and `GIT_CONFIG_NOSYSTEM=1`, so no global
setting (identity, `init.defaultBranch`, commit signing) makes a test pass or
fail on one machine only. PR #44's red CI run came from such a test.

## Out of scope

- Shipping old generations inside the plugin. With the stamp and the log the
  LLM does not need them.
- A three-way merge done by `apply` itself.
- `check` reporting edited files.

## Tests

- A fresh install stamps the file; an upgrade of an unedited stamped file
  overwrites it without `NeedsMerge`, for a single file, an assembled file and
  a directory asset.
- An upgrade of an edited stamped file and of an unstamped file stops with
  `NeedsMerge` and writes `.new`, `.current`, `.path`, `.log`, no `.base`.
- `.log` lists the target repository's commits for the path.
- `--from` writes no stamp and commits with the `Merge ...` subject; the next
  upgrade of that file stops with `NeedsMerge`.
- `check` reports a stamped file at the current generation as `ok`, and an
  edited one too.
- The plugin installed without `.git` (tests copy the plugin tree without it)
  upgrades an unedited stamped file.
- `generations.json` test: changed text with the same version fails; a new
  version without a record fails.
- `config_text` keeps `["ci-man", "ci-rust-musl"]` on one line and breaks a
  list longer than 80 columns.

## Release

A bugfix release, v0.3.1. CHANGES.md under Fixed: upgrades with the installed
plugin no longer stop on every changed workflow file with "local edits
present"; `.github/repo-infra.json` keeps short lists on one line.
