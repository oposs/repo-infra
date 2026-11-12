'use strict';

// ri-release-distro-packages (D38), packing: one nfpm package for one
// distribution release and one architecture, built inside the release's
// own image from a stage that `make install DESTDIR=` filled. The leg script
// hands `pack` its environment and nothing else, so every refusal is a line
// in distro-pack.test.js. The file system and the commands go through `io`,
// which the tests replace.

const { byDistro } = require('./distro.js');
const {
  parsePackagers, expand, rfc3339, readBack,
} = require('./nfpm.js');

const PIECE = 'ri-release-distro-packages';
// The variables the piece sets. A packagers key that names one of them
// fails, so a config cannot shadow VERSION or DEPENDS.
const OWN = [
  'VERSION', 'SOURCE_DATE_EPOCH', 'MTIME', 'PACKAGER', 'STAGE', 'ARCH', 'DISTRO',
  'ID', 'VERSION_ID', 'CODENAME', 'DEPENDS', 'PKG_RELEASE',
];
const APK_ARCH = { amd64: 'x86_64', arm64: 'aarch64' };

// The lines of /etc/os-release as an object. Values may be quoted.
function parseOsRelease(text) {
  const result = {};
  for (const line of text.split('\n')) {
    const m = line.match(/^([A-Z_]+)=(.*)$/);
    if (m) result[m[1]] = m[2].replace(/^(["'])(.*)\1$/, '$2');
  }
  return result;
}

// The release in the table must be the release the image really is: a
// DISTRO=debian-13 leg run in a bookworm image would otherwise ship a
// package named for trixie that links against bookworm's libraries.
function checkRelease(release, osRelease, rpmDist) {
  let expected;
  let actual;
  if (release.family === 'deb') {
    expected = release.codename;
    actual = osRelease.VERSION_CODENAME;
  } else if (release.family === 'rpm') {
    // The tag comes from the image (rpm --eval %{dist}); without it there is
    // nothing to compare.
    if (rpmDist === undefined) return;
    expected = release.dist;
    actual = rpmDist.replace(/^\./, '');
  } else {
    expected = release.branch.replace(/^v/, '');
    actual = (osRelease.VERSION_ID || '').split('.').slice(0, 2).join('.');
  }
  if (actual !== expected) {
    throw new Error(`${release.distro} expects ${expected}, the image says ${actual}`);
  }
}

function packVariables({
  version, release, osRelease, depends, epoch, stage, arch, rpmDist,
}) {
  checkRelease(release, osRelease, rpmDist);
  const family = release.family;
  return {
    VERSION: family === 'deb' ? `${version}~${release.codename}` : version,
    SOURCE_DATE_EPOCH: epoch,
    MTIME: rfc3339(epoch),
    PACKAGER: family,
    STAGE: stage,
    ARCH: arch,
    DISTRO: release.distro,
    ID: osRelease.ID || '',
    VERSION_ID: osRelease.VERSION_ID || '',
    CODENAME: family === 'deb' ? release.codename : '',
    // JSON strings are valid YAML double-quoted scalars, so a quote or a
    // backslash in a dependency cannot break the flow sequence.
    DEPENDS: depends.map((d) => JSON.stringify(d)).join(', '),
    PKG_RELEASE: { deb: '1', rpm: `1.${release.dist}`, apk: '0' }[family],
  };
}

// The dependencies the finished package declares. A package built from an
// ELF stage that declares none was packed from a config without
// `depends: [${DEPENDS}]`, or the detection found nothing.
function readDepends(family, path, exec) {
  if (family === 'deb') {
    return exec('dpkg-deb', ['--field', path, 'Depends']).split(', ')
      .map((d) => d.trim()).filter(Boolean);
  }
  if (family === 'rpm') {
    return exec('rpm', ['-qp', '--requires', path]).split('\n')
      .map((d) => d.trim()).filter((d) => d && !d.startsWith('rpmlib('));
  }
  return exec('tar', ['--ignore-zeros', '-xzOf', path, '.PKGINFO']).split('\n')
    .map((l) => l.match(/^depend = (.*)$/)).filter(Boolean).map((m) => m[1].trim());
}

function nodeIo() {
  const fs = require('fs');
  const { execFileSync } = require('child_process');
  return {
    isFile: (path) => fs.existsSync(path) && fs.statSync(path).isFile(),
    read: (path) => fs.readFileSync(path, 'utf8'),
    write: (path, text) => fs.writeFileSync(path, text),
    mkdir: (path) => fs.mkdirSync(path, { recursive: true }),
    list: (path) => (fs.existsSync(path) ? fs.readdirSync(path).sort() : []),
    exec: (command, args, options = {}) => execFileSync(command, args, {
      encoding: 'utf8', stdio: ['ignore', 'pipe', 'inherit'], ...options,
    }),
  };
}

// Packs one package and returns the lines for the log. Run in the checkout:
// packages/ receives the package.
function pack(env, io = nodeIo()) {
  const release = byDistro(env.DISTRO);
  if (!release) throw new Error(`DISTRO ${env.DISTRO} is not a release this piece builds`);
  const family = release.family;
  const packagers = parsePackagers(env.PACKAGERS || '', ['deb', 'rpm', 'apk'], true, PIECE);
  // A caller that names only rpm extras still gets deb and apk legs.
  const extra = packagers[family] || {};
  const shadowed = Object.keys(extra).filter((key) => OWN.includes(key)).sort();
  if (shadowed.length > 0) {
    throw new Error(`packagers.${family} sets ${shadowed.join(', ')}, which ${PIECE} sets itself`);
  }
  if (family === 'rpm' && !env.RPM_DIST) {
    throw new Error(`RPM_DIST is empty; ${release.distro} needs the output of rpm --eval %{dist}`);
  }
  if (!io.isFile(env.CONFIG)) throw new Error(`${env.CONFIG} does not exist`);
  const template = io.read(env.CONFIG);
  const osRelease = parseOsRelease(io.read(env.OS_RELEASE));
  const depends = env.DEPENDS_FILE
    ? io.read(env.DEPENDS_FILE).split('\n').filter((l) => l !== '') : [];
  const epoch = io.exec('git', ['log', '-1', '--format=%ct', 'HEAD']).trim();
  const own = packVariables({
    version: env.VERSION, release, osRelease, depends, epoch, stage: env.STAGE,
    arch: env.ARCH, rpmDist: env.RPM_DIST,
  });
  const expanded = `${env.RUNNER_TEMP || '/tmp'}/nfpm-${env.DISTRO}-${env.ARCH}.yaml`;
  io.write(expanded, expand(template, { ...extra, ...own }, env.CONFIG));
  io.mkdir('packages');
  const before = new Set(io.list('packages'));
  // nfpm gets the piece's own variables and not the packagers values, so
  // {"deb": {"PATH": "x"}} cannot replace the PATH nfpm is found on.
  io.exec('nfpm', ['package', '--config', expanded, '--packager', family,
    '--target', 'packages'], { env: { ...env, ...own }, stdio: 'inherit' });
  const made = io.list('packages').filter((name) => !before.has(name));
  if (made.length !== 1) {
    throw new Error(`nfpm wrote ${made.length} files for ${env.DISTRO} ${env.ARCH}; one is expected`);
  }
  let file = made[0];
  const back = readBack(family, `packages/${file}`, io.exec);
  if (back.version !== own.VERSION && !back.version.startsWith(`${own.VERSION}-`)) {
    throw new Error(`${file} carries version ${back.version}, not ${own.VERSION}`);
  }
  if (back.files.length === 0) throw new Error(`${file} holds no files`);
  if (env.HAS_ELF === 'true' && readDepends(family, `packages/${file}`, io.exec).length === 0) {
    throw new Error(`${file} declares no dependencies although the stage holds ELF files `
      + '(HAS_ELF=true); the config needs depends: [${DEPENDS}]');
  }
  if (family === 'apk') {
    // nfpm names an apk <name>_<version>_<arch>.apk. Releases of one Alpine
    // line share the file name space of a Gitea branch, so the name carries
    // the Alpine release the way the Global Constraints define it.
    const m = file.match(/^(.+)_(.+-r0)_(x86_64|aarch64)\.apk$/);
    if (!m) throw new Error(`nfpm wrote ${file}, which is not <name>_<version>-r0_<arch>.apk`);
    const renamed = `${m[1]}-${m[2]}-alpine${release.branch.replace(/^v/, '')}-${m[3]}.apk`;
    io.exec('mv', [`packages/${file}`, `packages/${renamed}`]);
    file = renamed;
  }
  return [`${file}: version ${back.version}, ${back.files.length} files`];
}

module.exports = { packVariables, pack, parseOsRelease };
