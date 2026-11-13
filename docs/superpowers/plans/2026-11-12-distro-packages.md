# Linux packages per distribution (D38) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A remote piece `ri-release-distro-packages` that builds, tests and packages a program once per distribution release inside an image of that release, and a `ri-publish-gitea` that routes those packages to their per-release Gitea repositories.

**Architecture:** As in `ri-release-nfpm`, the logic lives in `.github/workflows/lib/` and the workflow only hands it environment variables. Planning and packing are JavaScript with injected `io` (unit tested with `node --test`). What runs inside containers is POSIX shell, tested under podman with the `container` pytest marker. The piece prepares a base image per release (EPEL/CRB, detector tools), builds the project's `Containerfile` on it with `--build-arg BASE=<prepared tag> --target build-deps`, runs the build contract, detects dependencies, packs with the pinned nfpm and install-tests in the prepared image without tools.

**Tech Stack:** GitHub Actions reusable workflows, Node 20 (`actions/github-script@v9`), POSIX sh, docker on the runner, podman locally, nfpm 2.47.0, pytest.

**Spec:** [docs/superpowers/specs/2026-11-12-distro-packages-design.md](../specs/2026-11-12-distro-packages-design.md)

## Global Constraints

- Header line `# repo-infra: ri-release-distro-packages v2`; never bump it for an optional input.
- No em dash in any shipped text (`tests/test_no_em_dash.py`); prose follows `repo-infra:writing-style`.
- The v2 interface of existing pieces is frozen: only optional inputs, secrets and outputs may be added.
- repo-infra is public: no internal host names in code, tests or fixtures (`gitea.oetiker.ch` already appears in tests and stays).
- nfpm pinned to `2.47.0` with its SHA-256, the same pin as `ri-release-nfpm`; one constant, not two.
- Runners: amd64 `ubuntu-24.04`, arm64 `ubuntu-24.04-arm`.
- Standard list (spec): `debian-12`, `debian-13`, `ubuntu-22.04`, `ubuntu-24.04`, `ubuntu-26.04`, `almalinux-9`, `almalinux-10`, `fedora` (newest released), `alpine` (two newest stable; names `alpine-3.NN`).
- Build contract in `/src/<directory>`: autotools only when `configure.ac` exists (`./bootstrap`, `./configure --disable-container`), then `make`, `make check`, `make install DESTDIR=/stage`.
- nfpm variables set by the piece: `VERSION`, `SOURCE_DATE_EPOCH`, `MTIME`, `PACKAGER`, `STAGE`, `ARCH`, `DISTRO`, `ID`, `VERSION_ID`, `CODENAME`, `DEPENDS`, `PKG_RELEASE`.
- Version forms: deb `VERSION=<v>~<codename>`, `PKG_RELEASE=1`; rpm `VERSION=<v>`, `PKG_RELEASE=1.<dist>`; apk `VERSION=<v>`, `PKG_RELEASE=0`.
- apk file name after packing: `<name>-<v>-r0-alpine<major.minor>-<arch>.apk` (`x86_64`, `aarch64`).
- Artifacts: `release-asset-packages-<distro>-<amd64|arm64>`.
- Gitea paths: deb `debian/pool/<codename>/<component>/upload`; rpm `rpm/<dist>/upload` or `rpm/<group>/<dist>/upload`; apk `alpine/v<major.minor>/main`.
- Local test runs: at most 4 cores, and container tests under `systemd-run --user --scope -p MemoryMax=4G --`.

## Review Focus

1. A project whose package has no ELF file (a data or pure-Perl package): `DEPENDS` is empty, `depends: [${DEPENDS}]` must expand to `[]` and the read-back must not demand dependencies. Test in Task 3.
2. A release image that drifted from the table (Fedora rolled, an Ubuntu codename the table spells differently): the leg must fail with both values named, not package under a wrong codename. Test in Task 4.
3. `distributions` written as a YAML block scalar, one name per line, as callers already do for `targets`: must parse like a space list. Test in Task 1.
4. A `.deb` uploaded through GitHub's renaming (`~` becomes `.`, #129) must still route to its codename: routing reads the version from the package header, not the asset name. Test in Task 6.
5. A `make install` that writes nothing to `/stage`: fail the leg with "make install wrote nothing under /stage", not an empty package. Test in Task 4.

---

### Task 1: The release table and the matrix

**Files:**
- Create: `.github/workflows/lib/distro.js`
- Test: `.github/workflows/lib/distro.test.js`

**Interfaces:**
- Produces: `RELEASES`, an array of `{ distro, image, family, codename, dist, branch }`; `family` is `deb`, `rpm` or `apk`; `codename` only for deb, `dist` only for rpm (`el9`, `el10`, `fc<N>`), `branch` only for apk (`v3.NN`).
- Produces: `distroPlan(text: string) -> { include: Leg[] }`, `Leg = { distro, image, family, arch, os }`, `arch` in `amd64|arm64`, `os` `ubuntu-24.04` or `ubuntu-24.04-arm`. Empty text means all releases.
- Produces: `byDistro(name) -> Release | undefined`, used by Tasks 3, 4 and 6.

- [ ] **Step 1: Pin the table.** Images are `docker.io/library/<name>:<tag>` with tags `12`, `13`, `22.04`, `24.04`, `26.04`, `9`, `10`, a numbered Fedora tag and two numbered Alpine tags. Read the newest released Fedora and the two newest Alpine releases from the registry on the day of the work (`skopeo list-tags docker://docker.io/library/fedora`, same for `alpine`), and the codenames from each image's `/etc/os-release` (`podman run --rm <image> cat /etc/os-release`). Write numbers, never `latest`.

- [ ] **Step 2: Write the failing tests** in `distro.test.js`:

```js
test('all releases on both architectures when nothing is named', () => {
  const legs = distroPlan('').include;
  assert.equal(legs.length, RELEASES.length * 2);
  assert.deepEqual(legs.find((l) => l.distro === 'debian-13' && l.arch === 'arm64'),
    { distro: 'debian-13', image: 'docker.io/library/debian:13', family: 'deb',
      arch: 'arm64', os: 'ubuntu-24.04-arm' });
});
test('a block scalar narrows like a space list', () => {
  assert.deepEqual(distroPlan('debian-13\nalmalinux-10\n').include.map((l) => l.distro),
    ['debian-13', 'debian-13', 'almalinux-10', 'almalinux-10']);
});
test('an unknown name fails and lists the known ones', () => {
  assert.throws(() => distroPlan('debian-11'),
    /distributions names debian-11, which this piece does not build; it builds debian-12 /);
});
test('only blanks fails', () => {
  assert.throws(() => distroPlan(' \n '), /distributions names no release/);
});
test('every release has the field of its family and no other', () => { /* codename|dist|branch */ });
```

- [ ] **Step 3: Run** `node --test .github/workflows/lib/distro.test.js`. Expected: FAIL, `Cannot find module './distro.js'`.
- [ ] **Step 4: Implement** `distroPlan` and `byDistro`; `' '` and `'\n'` both split. The order of `include` is the table order, amd64 before arm64.
- [ ] **Step 5: Run** the same command. Expected: PASS.
- [ ] **Step 6: Commit** `lib/distro.js: the releases of D38 and their matrix`.

### Task 2: The prepared base image and the dependency detector

**Files:**
- Create: `.github/workflows/lib/distro-base.Containerfile`
- Create: `.github/workflows/lib/distro-deps.sh`
- Test: `tests/test_distro_deps.py` (marker `container`)
- Create: `tests/fixtures/distro-hello/` (`hello.c` linking zlib, `Makefile` with `all`, `check` running `./hello`, `install` to `$(DESTDIR)/usr/bin`, `nfpm.yaml`, `Containerfile` per the spec's contract with the three families)

**Interfaces:**
- Produces: `distro-base.Containerfile` with `ARG IMAGE`, stage `repos` (`FROM ${IMAGE}`; on AlmaLinux `dnf install -y epel-release` and `crb enable`; nothing elsewhere) and stage `tools` (`FROM repos`; deb `dpkg-dev`, rpm `rpm-build`, apk `pax-utils`). Branches on `ID` and `ID_LIKE` from `/etc/os-release`.
- Produces: `distro-deps.sh <family> <stage-dir>`, printing one dependency per line, sorted and unique, exit 0 with no output when the stage holds no ELF file. deb: `dpkg-shlibdeps -O` over every ELF file, split on `, ` (the `-O` output, `shlibs:Depends=` stripped). rpm: `/usr/lib/rpm/rpmdeps --requires` over every ELF file, `rpmlib(` entries dropped. apk: `scanelf --needed --nobanner --format '%n'` split on `,`, each as `so:<soname>`, sonames the stage itself provides dropped. Perl: when the stage holds a `.so` under a path containing `/perl`, add deb `perlapi-<$Config{version}>`, rpm `perl(:MODULE_COMPAT_<$Config{version}>)`, apk `perl~<major.minor>`.

- [ ] **Step 1: Write the failing container tests.** A fixture builds `hello` in the `tools` image of `debian:13`, `almalinux:10` and the newer Alpine, installs it into a temporary stage and runs the detector:

```python
@pytest.mark.container
@pytest.mark.parametrize("distro,expect", [
    ("debian-13", r"^libc6 \(>= [0-9.]+\)$"),
    ("almalinux-10", r"^libz\.so\.1\(\)\(64bit\)$"),
    ("alpine-3.NN", r"^so:libz\.so\.1$"),
])
def test_the_detector_names_zlib(distro, expect, built_stage): ...
def test_a_stage_without_elf_prints_nothing(...): ...
def test_a_perl_xs_object_adds_the_perl_api_on_debian(...):  # matches ^perlapi-5\.\d+\.\d+$
def test_epel_is_enabled_in_the_almalinux_repos_stage(...):  # dnf repolist shows epel and crb
```

- [ ] **Step 2: Run** `systemd-run --user --scope -p MemoryMax=4G -- python -m pytest -m container tests/test_distro_deps.py`. Expected: FAIL, the Containerfile does not exist.
- [ ] **Step 3: Write** `distro-base.Containerfile` and `distro-deps.sh` as in Interfaces; ELF files found by their first four bytes (`\177ELF`), not by `file`, which minimal images lack.
- [ ] **Step 4: Run** the same command. Expected: PASS for all four.
- [ ] **Step 5: Commit** `lib: prepared base image and dependency detector for D38`.

### Task 3: Packing with nfpm

**Files:**
- Modify: `.github/workflows/lib/nfpm.js` (export `expand`, `rfc3339`, `readBack`, `NFPM_VERSION`, `NFPM_SHA256`; `readBack` learns `apk`; `parsePackagers(text, allowed = ['deb', 'rpm'])`)
- Create: `.github/workflows/lib/distro-pack.js`
- Test: `.github/workflows/lib/distro-pack.test.js`; `nfpm.test.js` stays green unchanged

**Interfaces:**
- Consumes: `byDistro` (Task 1).
- Produces: `packVariables({ version, release, osRelease, depends, epoch, stage, arch }) -> object` with the twelve names of the Global Constraints; `osRelease` is the parsed `/etc/os-release`; `depends` an array.
- Produces: `pack(env, io) -> string[]` (lines to log). Reads `VERSION`, `DISTRO`, `ARCH`, `CONFIG`, `STAGE`, `PACKAGERS`, `OS_RELEASE` (file), `DEPENDS_FILE`; writes exactly one package into `packages/`; for apk renames it to the Global Constraints form; throws on a read-back whose version is wrong, which holds no files, or whose dependency list is empty while `HAS_ELF=true`.

- [ ] **Step 1: Write the failing tests** with the fake `io` of `nfpm.test.js`:

```js
test('deb gets the codename in the version and release 1', () => {
  const v = packVariables({ version: '1.4.0', release: byDistro('debian-13'),
    osRelease: { ID: 'debian', VERSION_ID: '13', VERSION_CODENAME: 'trixie' },
    depends: ['libc6 (>= 2.36)', 'zlib1g (>= 1:1.2.0)'], epoch: '1700000000', stage: '/s', arch: 'amd64' });
  assert.equal(v.VERSION, '1.4.0~trixie');
  assert.equal(v.PKG_RELEASE, '1');
  assert.equal(v.DEPENDS, '"libc6 (>= 2.36)", "zlib1g (>= 1:1.2.0)"');
  assert.equal(v.CODENAME, 'trixie');
});
test('rpm puts the dist tag in the release', () => { /* almalinux-9: VERSION '1.4.0', PKG_RELEASE '1.el9', CODENAME '' */ });
test('no dependencies expand to an empty flow sequence', () => {
  assert.equal(expand('depends: [${DEPENDS}]\n', packVariables({ ..., depends: [] }), 'c'), 'depends: []\n');
});
test('a double quote in a dependency is escaped', () => { /* JSON.stringify per item */ });
test('the release must match the image', () => {
  /* debian-13 with VERSION_CODENAME bookworm throws /debian-13 expects trixie, the image says bookworm/ */
});
test('apk is renamed with the Alpine release', () => { /* lectover_1.4.0-r0_x86_64.apk -> lectover-1.4.0-r0-alpine3.NN-x86_64.apk */ });
test('an ELF package without dependencies fails the read-back', () => {});
```

- [ ] **Step 2: Run** `node --test .github/workflows/lib/distro-pack.test.js`. Expected: FAIL, module not found.
- [ ] **Step 3: Implement.** apk read-back: `tar --ignore-zeros -xzOf <file> .PKGINFO`, fields `pkgver` and `depend`, and `tar --ignore-zeros -tzf` for the file list. The release check compares `codename` (deb), `rpm --eval %{dist}` passed in as `RPM_DIST` (rpm) and `VERSION_ID` major.minor (apk) with the table and names both values.
- [ ] **Step 4: Run** `make test-js`. Expected: PASS, the 309 tests of `main` plus the new ones, no failure.
- [ ] **Step 5: Commit** `lib/distro-pack.js: nfpm packages per release (D38)`.

### Task 4: One leg, end to end

**Files:**
- Create: `.github/workflows/lib/distro-leg.sh`
- Test: `tests/test_distro_leg.py` (marker `container`), fixture from Task 2

**Interfaces:**
- Consumes: Task 2 files, `pack` (Task 3), `byDistro` (Task 1).
- Produces: `distro-leg.sh` reading `ENGINE` (`docker` or `podman`), `IMAGE`, `DISTRO`, `ARCH`, `VERSION`, `DIRECTORY`, `CONFIG` (default `nfpm.yaml`), `PACKAGERS`, `LIB` (the repo-infra lib folder); writes `packages/<one file>`. Steps: build `repos` and `tools` from `distro-base.Containerfile` (`--build-arg IMAGE`), build the project's `Containerfile` with `--build-arg BASE=<tools tag> --target build-deps` and no context; run the build contract with the checkout at `/src` and a fresh `/stage` volume; run `distro-deps.sh` and copy out `/etc/os-release` and, on rpm, `rpm --eval %{dist}`; run `node -e` on `pack`; install the package in the `repos` image (`apt-get install -y ./x.deb`, `dnf install -y ./x.rpm`, `apk add --allow-untrusted ./x.apk`).

- [ ] **Step 1: Write the failing tests:**

```python
@pytest.mark.container
@pytest.mark.parametrize("distro", ["debian-13", "almalinux-10", "alpine-3.NN"])
def test_a_leg_builds_checks_packs_and_installs_the_fixture(distro, tmp_path): ...
def test_a_failing_make_check_fails_the_leg(tmp_path):         # fixture with CHECK_FAIL=1
def test_make_install_writing_nothing_fails_the_leg(tmp_path): # message "make install wrote nothing under /stage"
def test_a_drifted_image_fails_with_both_codenames(tmp_path):  # IMAGE debian:12 with DISTRO debian-13
```

- [ ] **Step 2: Run** `systemd-run --user --scope -p MemoryMax=4G -- python -m pytest -m container tests/test_distro_leg.py`. Expected: FAIL, the script does not exist.
- [ ] **Step 3: Write** `distro-leg.sh` (`set -eu`, POSIX sh). The `chown` handback and the git `safe.directory` handling follow `build/container-make.mk`; read it before writing.
- [ ] **Step 4: Run** the same command. Expected: PASS. Also prove, once by hand, that `--target build-deps` with no context skips a later stage holding `COPY . /src` under podman, and note the result in the commit message.
- [ ] **Step 5: Commit** `lib/distro-leg.sh: one D38 leg from image to installed package`.

### Task 5: The piece

**Files:**
- Create: `.github/workflows/ri-release-distro-packages.yml`
- Modify: `skills/repo-infra/assets/manifest.json` (`"ri-release-distro-packages": {"kind": "remote", "group": "release-build"}`)
- Modify: `skills/repo-infra/references/catalogue.md` and the generations, via `make catalogue generations`
- Test: `tests/test_release_distro_packages.py`

**Interfaces:**
- Consumes: Tasks 1 to 4.
- Produces: inputs `version` (required), `ref` (required), `repository`, `submodules` (`'false'`), `directory` (`.`), `config` (`nfpm.yaml`), `packagers` (`'{}'` means one packager, the family's), `distributions` (`''`). Jobs: `plan` (`distroPlan`), `man` (only when `<directory>/build/man.mk` exists; the same job as `ri-release-rust-binaries`, artifact `man-pages`), `packages` (matrix from `plan`, `fail-fast: false`, `timeout-minutes: 120`, `ENGINE=docker`), `collect` (downloads `release-asset-packages-*` and fails unless every leg of the plan has one file).

- [ ] **Step 1: Write the failing tests** in the style of `tests/test_release_nfpm.py`:

```python
def test_the_header_names_the_piece_v2(): ...
def test_nfpm_is_the_pin_of_ri_release_nfpm(): ...      # same NFPM_VERSION and NFPM_SHA256
def test_the_matrix_comes_from_the_plan_and_does_not_fail_fast(): ...
def test_every_input_reaches_the_library_through_env(): ...
def test_the_artifact_name_carries_distro_and_arch(): ...
def test_collect_needs_packages_and_checks_the_plan(): ...
def test_permissions_are_contents_read(): ...
```

- [ ] **Step 2: Run** `python -m pytest tests/test_release_distro_packages.py`. Expected: FAIL.
- [ ] **Step 3: Write** the workflow. The header's `Choose:` line: "The program links system libraries, so one static build cannot serve every distribution (D38)." `Pieces:` names `man, man-lua` as optional only if the existing header grammar allows it; otherwise none. Then `make catalogue generations`.
- [ ] **Step 4: Run** `make test`, `make test-js`, `make lint`. Expected: all pass; `make test` reports the count of `main` plus the new tests.
- [ ] **Step 5: Commit** `ri-release-distro-packages: Linux packages built per distribution (D38)`.

### Task 6: Routing in ri-publish-gitea

**Files:**
- Modify: `.github/workflows/lib/gitea.js`, `.github/workflows/ri-publish-gitea.yml` (header `Purpose:` names `.apk`)
- Test: `.github/workflows/lib/gitea.test.js`, a deb and an rpm fixture under `tests/fixtures/` built by nfpm with a codename and a dist tag, and an apk fixture

**Interfaces:**
- Consumes: `RELEASES` (Task 1) for the known codenames, dist tags and branches.
- Produces: `debianDistribution(cfg, file, version)`: the map wins; otherwise a version with `~<known codename>` gives that codename; otherwise `cfg.distribution`. `rpmGroup(cfg, release)`: a release ending `.<known dist>` gives `<dist>` or `<group>/<dist>`; otherwise `cfg.group`. `apkPackage(buf, asset) -> { ok, kind: 'alpine', name, version, branch }` from `.PKGINFO` and the `-alpine<maj.min>-` part of the name; `uploadUrl` for `kind: 'alpine'` gives `${base}/alpine/${branch}/main`.

- [ ] **Step 1: Write the failing tests:**

```js
test('a deb built for trixie goes to trixie without a map', () => {
  assert.deepEqual(g.debianDistribution(CFG, 'x_1.4.0.trixie-1_amd64.deb', '1.4.0~trixie-1'),
    { ok: true, distribution: 'trixie' });
});
test('the map still wins over the codename', () => {});
test('a static deb without a codename stays in debian.distribution', () => {});
test('an el9 rpm goes to the el9 group, under rpm.group when set', () => {
  assert.equal(g.uploadUrl({ ...CFG, group: 'rocky' }, rpmPkg('1.el9')),
    'https://gitea.oetiker.ch/api/packages/oposs/rpm/rocky/el9/upload?sign=true');
});
test('an apk goes to its Alpine branch', () => {
  assert.equal(g.uploadUrl(CFG, apk), 'https://gitea.oetiker.ch/api/packages/oposs/alpine/v3.NN/main');
});
```

- [ ] **Step 2: Run** `node --test .github/workflows/lib/gitea.test.js`. Expected: FAIL on the new tests.
- [ ] **Step 3: Implement.** Routing reads the version from the package header, never from the asset name (GitHub renames `~`, #129). Requires PR #159 merged first (per-segment group encoding).
- [ ] **Step 4: Run** `make test-js`. Expected: PASS.
- [ ] **Step 5: Commit** `ri-publish-gitea: route per-release deb, rpm and apk packages (D38)`.

### Task 7: The references and the changelog

**Files:**
- Modify: `skills/repo-infra/references/project-shape.md` (`linux-packages` "Met by"; the exceptions table row for musl targets applies only without this piece; a `distributions` pairing paragraph next to D34's; install snippets for rpm per dist tag, AlmaLinux EPEL/CRB, Alpine with `alpine/key`)
- Modify: `skills/repo-infra/references/conventions.md` (the two Containerfile points: `ARG BASE` with default and stage `build-deps`; one `RUN` branching on `/etc/os-release`)
- Modify: `docs/superpowers/specs/2026-08-21-teach-and-build-containers-design.md` (one line under D16: release builds over the threshold use D38)
- Modify: `CHANGES.md` under `### New`
- Test: `tests/test_project_shape.py` stays green; `tests/test_no_em_dash.py`

- [ ] **Step 1: Write** the texts with `repo-infra:writing-style` loaded. The CHANGES entry, at most three sentences, leads with what a project owner can now do: ship `.deb`, `.rpm` and `.apk` for each listed release of a program that links system libraries, with `make check` run on every release, and names `ri-release-distro-packages` and `distributions`. A second entry for `ri-publish-gitea`: packages for a release go to that release's apt distribution, rpm group or Alpine branch.
- [ ] **Step 2: Run** `make test`. Expected: PASS.
- [ ] **Step 3: Commit** `references: linux-packages per distribution (D38)`.

### Task 8: The proof on GitHub

**Files:**
- Create: `.github/workflows/gate-distro-packages.yml` (`workflow_dispatch` only, `contents: read`, calls `./.github/workflows/ri-release-distro-packages.yml` with `repository: ${{ github.repository }}`, `ref: ${{ github.sha }}`, `directory: tests/fixtures/distro-hello`, `version: 0.0.0`)
- Test: `tests/test_release_distro_packages.py` gains `test_the_gate_calls_the_piece_on_the_fixture`

- [ ] **Step 1: Write** the test and the gate; run `make test`. Expected: PASS.
- [ ] **Step 2: Push** the branch and run `gh workflow run gate-distro-packages.yml --ref <branch>`. Expected: 20 green legs and a green `collect`. A red leg is a bug in Tasks 2 to 4 or in the fixture's `Containerfile`; fix it there with a test, not in the gate.
- [ ] **Step 3: Record** the run id in the PR body. Commit `gate-distro-packages: prove D38 on the fixture`.

## After this plan

Not part of this branch; each is its own PR once this one is released: lectover's migration, wg-wrangler's migration, #150 (homebrew from the archives that exist), the closing comment on #149 and #148 (public, ask first).
