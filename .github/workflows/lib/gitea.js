'use strict';

// publish-gitea-packages (D27): which release assets are packages, where
// Gitea wants them, and what a 409 on a re-run means.

const zlib = require('zlib');
const { ROUTED } = require('./distro.js');

const CONFIG = '.github/repo-infra.json';
// What Gitea accepts as a distribution or component in the upload path.
const SYMBOL = /^[a-zA-Z0-9][a-zA-Z0-9.~+_-]*$/;

// debian.distributions maps file-name globs to apt distributions, so a
// project that builds one .deb per Debian or Ubuntu release puts each into
// its own distribution.
function distributionMap(debian) {
  const map = debian.distributions;
  if (map === undefined) return {};
  const where = `${CONFIG}: "gitea_packages.debian.distributions"`;
  if (!map || typeof map !== 'object' || Array.isArray(map)) {
    throw new Error(`${where} must be an object of file-name globs and distribution names`);
  }
  for (const [glob, dist] of Object.entries(map)) {
    if (glob === '') {
      throw new Error(`${where} has an empty glob`);
    }
    if (typeof dist !== 'string' || dist === '') {
      throw new Error(`${where}: "${glob}" must name a distribution (a non-empty string)`);
    }
    if (!SYMBOL.test(dist)) {
      throw new Error(`${where}: "${glob}" names the distribution "${dist}", which Gitea `
        + 'refuses; use letters, digits and . ~ + _ - only, starting with a letter or digit');
    }
  }
  return { ...map };
}

function packageConfig(config) {
  const c = (config || {}).gitea_packages;
  if (!c || !c.url) {
    throw new Error(`${CONFIG}: "gitea_packages" needs a "url"`);
  }
  if (!c.owner) {
    throw new Error(`${CONFIG}: "gitea_packages" needs an "owner"`);
  }
  const debian = c.debian || {};
  return {
    url: c.url.replace(/\/+$/, ''),
    owner: c.owner,
    distribution: debian.distribution || 'stable',
    distributions: distributionMap(debian),
    component: debian.component || 'main',
    group: (c.rpm && c.rpm.group) || '',
  };
}

// A glob knows `*` and `?` and matches the whole name.
function globMatches(glob, name) {
  const re = glob.replace(/[.+^${}()|[\]\\]/g, '\\$&')
    .replace(/\*/g, '.*').replace(/\?/g, '.');
  return new RegExp(`^${re}$`, 's').test(name);
}

// The codename a deb version names: ri-release-distro-packages builds
// <v>~<codename>-1, so a version with ~trixie belongs to trixie. A word that
// only starts like a codename (~trixiefoo) or a pre-release (~rc.1) is none.
function versionCodename(version) {
  const text = String(version || '');
  const known = ROUTED.filter((r) => r.codename).map((r) => r.codename);
  return known.find((c) => new RegExp(`~${c}(?![A-Za-z0-9])`).test(text)) || null;
}

// The distribution a .deb goes to. The map wins. A file the map does not
// cover takes the codename in its version, and without one goes to
// debian.distribution -- except with a map, where a file nothing claims is
// an error when it names no codename either, and several matching globs are
// always an error: falling back would put a package built for one release
// into the channel of another. The version comes from the control data
// because GitHub renames `~` in asset names (#129).
function debianDistribution(cfg, file, version) {
  const globs = Object.keys(cfg.distributions || {});
  const codename = versionCodename(version);
  if (globs.length === 0) return { ok: true, distribution: codename || cfg.distribution };
  const hits = globs.filter((glob) => globMatches(glob, file));
  if (hits.length === 1) return { ok: true, distribution: cfg.distributions[hits[0]] };
  if (hits.length === 0) {
    if (codename) return { ok: true, distribution: codename };
    return {
      ok: false,
      message: `${file}: no glob in "gitea_packages.debian.distributions" matches it`,
    };
  }
  return {
    ok: false,
    message: `${file}: several globs in "gitea_packages.debian.distributions" match it (`
      + `${hits.join(', ')})`,
  };
}

// The rpm group for a release such as 1.el9: <dist>, or <group>/<dist> under
// rpm.group, when the release ends in a dist tag the piece builds. Any other
// release keeps cfg.group, so an rpm without a tag goes where it always did.
function rpmGroup(cfg, release) {
  const tag = /\.([a-z]+[0-9]+)$/.exec(String(release || ''));
  const dist = tag && ROUTED.some((r) => r.dist === tag[1]) ? tag[1] : null;
  if (!dist) return cfg.group;
  return cfg.group ? `${cfg.group}/${dist}` : dist;
}

// GitHub renames release assets: `~` becomes `.`, so a .deb built as
// x_0.5.0~bookworm_amd64.deb is listed as x_0.5.0.bookworm_amd64.deb (#129).
// The asset name therefore cannot give the version back. Gitea takes name,
// version and architecture from the control data and names the stored file
// name_version_arch.deb, so a .deb is described by its control data, read
// with `dpkg-deb --field <file> Package Version Architecture`.
function debPackage(control, asset) {
  const fields = {};
  for (const line of String(control).split('\n')) {
    const m = /^([A-Za-z][A-Za-z0-9-]*):\s*(.*?)\s*$/.exec(line);
    if (m) fields[m[1]] = m[2];
  }
  const missing = ['Package', 'Version', 'Architecture'].filter((k) => !fields[k]);
  if (missing.length > 0) {
    return { ok: false, message: `${asset}: the control data has no ${missing.join(', ')}` };
  }
  const { Package: name, Version: version, Architecture: arch } = fields;
  return {
    ok: true,
    pkg: { kind: 'debian', name, version, arch, file: `${name}_${version}_${arch}.deb`, asset },
  };
}

// An .rpm has the same problem as a .deb: GitHub lists
// tool-1.0.0~rc.1-1.x86_64.rpm as tool-1.0.0.rc.1-1.x86_64.rpm. Gitea reads
// name, epoch, version, release and architecture from the package header,
// sets the version to [epoch-]version-release and names the stored file
// name-version.arch.rpm. The header is not compressed, so it is read here
// rather than with rpm, which the runner lacks.
const RPM_TAG = { 1000: 'name', 1001: 'version', 1002: 'release', 1003: 'epoch', 1022: 'arch' };

// One header structure at `at`: magic, reserved, entry count, store size,
// then 16-byte entries (tag, type, offset, count) and the store.
function rpmHeader(buf, at) {
  if (buf.length < at + 16 || buf.readUInt32BE(at) !== 0x8eade801) return null;
  const count = buf.readUInt32BE(at + 8);
  const size = buf.readUInt32BE(at + 12);
  const store = at + 16 + count * 16;
  if (buf.length < store + size) return null;
  const tags = {};
  for (let i = 0; i < count; i += 1) {
    const e = at + 16 + i * 16;
    const key = RPM_TAG[buf.readUInt32BE(e)];
    if (!key) continue;
    const type = buf.readUInt32BE(e + 4);
    const off = store + buf.readUInt32BE(e + 8);
    if (type === 4) {
      tags[key] = String(buf.readUInt32BE(off));
    } else if (type === 6 || type === 9) {
      const nul = buf.indexOf(0, off);
      tags[key] = buf.toString('utf8', off, nul < 0 ? store + size : nul);
    }
  }
  return { tags, end: store + size };
}

function rpmPackage(buf, asset) {
  const bad = { ok: false, message: `${asset}: not an rpm package (no readable header)` };
  // A 96-byte lead, then the signature header padded to 8 bytes, then the
  // header that describes the package.
  if (buf.length < 96 || buf.readUInt32BE(0) !== 0xedabeedb) return bad;
  const sig = rpmHeader(buf, 96);
  if (!sig) return bad;
  const main = rpmHeader(buf, sig.end + ((8 - (sig.end % 8)) % 8));
  if (!main) return bad;
  const t = main.tags;
  const missing = ['name', 'version', 'release', 'arch'].filter((k) => !t[k]);
  if (missing.length > 0) {
    return { ok: false, message: `${asset}: the rpm header has no ${missing.join(', ')}` };
  }
  const version = `${t.epoch && t.epoch !== '0' ? `${t.epoch}-` : ''}${t.version}-${t.release}`;
  return {
    ok: true,
    pkg: { kind: 'rpm', name: t.name, version, release: t.release, arch: t.arch,
      file: `${t.name}-${version}.${t.arch}.rpm`, asset },
  };
}

// An .apk is two or three gzip streams, each a tar: the signature, the
// control part with .PKGINFO, then the files. gunzip joins the streams;
// the tar reader skips the zero blocks that end each one. Gitea reads name,
// version and arch from .PKGINFO. The Alpine branch is not in the package:
// ri-release-distro-packages puts it in the file name as -alpine<major.minor>-.
function pkginfoOf(buf) {
  let tar;
  try {
    tar = zlib.gunzipSync(buf);
  } catch (err) {
    return null;
  }
  let at = 0;
  while (at + 512 <= tar.length) {
    const name = tar.toString('utf8', at, at + 100).replace(/\0.*$/s, '');
    const size = parseInt(tar.toString('utf8', at + 124, at + 136).replace(/\0.*$/s, '').trim() || '0', 8);
    if (name === '' || Number.isNaN(size)) {
      at += 512;
      continue;
    }
    if (name === '.PKGINFO') return tar.toString('utf8', at + 512, at + 512 + size);
    at += 512 + Math.ceil(size / 512) * 512;
  }
  return null;
}

// An .apk is an Alpine package only when the piece named it so; an Android
// app is an .apk too, and a release may carry one.
function isAlpineApk(name) {
  return /\.apk$/.test(name) && /-alpine\d+\.\d+-/.test(name);
}

function apkPackage(buf, asset) {
  const info = pkginfoOf(buf);
  if (info === null) {
    return { ok: false, message: `${asset}: not an apk package (no readable .PKGINFO)` };
  }
  const fields = {};
  for (const line of info.split('\n')) {
    const m = /^(pkgname|pkgver|arch) = (.*?)\s*$/.exec(line);
    if (m) fields[m[1]] = m[2];
  }
  const missing = ['pkgname', 'pkgver', 'arch'].filter((k) => !fields[k]);
  if (missing.length > 0) {
    return { ok: false, message: `${asset}: .PKGINFO has no ${missing.join(', ')}` };
  }
  const tag = /-alpine(\d+\.\d+)-/.exec(asset);
  if (!tag) {
    return {
      ok: false,
      message: `${asset}: the file name has no -alpine<major.minor>- part, so the `
        + 'Alpine branch it belongs to is unknown',
    };
  }
  const { pkgname: name, pkgver: version, arch } = fields;
  return {
    ok: true,
    pkg: { kind: 'alpine', name, version, arch, branch: `v${tag[1]}`,
      file: `${name}-${version}.apk`, asset },
  };
}

const seg = encodeURIComponent;

function uploadUrl(cfg, pkg) {
  const base = `${cfg.url}/api/packages/${seg(cfg.owner)}`;
  if (pkg.kind === 'debian') {
    return `${base}/debian/pool/${seg(pkg.distribution || cfg.distribution)}/${seg(cfg.component)}/upload`;
  }
  if (pkg.kind === 'alpine') {
    return `${base}/alpine/${seg(pkg.branch)}/main`;
  }
  // Gitea's generated .repo sets gpgcheck=1, so an unsigned rpm would not
  // install. Gitea signs with its per-owner key. A group may hold a slash
  // (Gitea documents rocky/el9), so each segment is encoded on its own;
  // encoding the whole group sent rocky/el9 to rocky%2Fel9.
  const rpmPath = rpmGroup(cfg, pkg.release);
  const group = rpmPath ? `/${rpmPath.split('/').map(seg).join('/')}` : '';
  return `${base}/rpm${group}/upload?sign=true`;
}

function filesUrl(cfg, pkg) {
  // `~` is unreserved; encodeURIComponent leaves it alone.
  return `${cfg.url}/api/v1/packages/${seg(cfg.owner)}/${pkg.kind}/`
    + `${seg(pkg.name)}/${seg(pkg.version)}/files`;
}

function missingCredentials(env) {
  return ['GITEA_PACKAGE_TOKEN', 'GITEA_PACKAGE_USER'].filter((k) => !env[k]);
}

// Gitea answers 409 for a version it already has. On a re-run after a partial
// upload that is the file that went up the first time -- or a different file
// under the same version, which must fail.
function conflictVerdict(pkg, assetSha256, files) {
  const stored = (files || []).filter((f) => f.name === pkg.file);
  if (stored.length === 0) {
    return { ok: false, message: `${pkg.file}: Gitea answered 409 but lists no such file` };
  }
  if (pkg.kind === 'alpine') {
    // The stored name has no architecture, so the x86_64 and the aarch64
    // build of one version share it, and the listing holds both. This asset
    // is there when any copy has its SHA-256.
    if (stored.some((f) => f.sha256 === assetSha256)) {
      return { ok: true, message: `${pkg.file}: already uploaded, SHA-256 matches` };
    }
    return {
      ok: false,
      message: `${pkg.file}: Gitea holds ${stored.length} file(s) of this name, none of them `
        + `this asset (${pkg.arch}, ${pkg.branch})`,
    };
  }
  if (pkg.kind === 'debian') {
    // Gitea keeps one file per distribution and component under a version,
    // and its file listing does not say which is which. A file name listed
    // more than once is accepted only when every copy is this asset.
    if (stored.every((f) => f.sha256 === assetSha256)) {
      return { ok: true, message: `${pkg.file}: already uploaded, SHA-256 matches` };
    }
    if (stored.length > 1) {
      return {
        ok: false,
        message: `${pkg.file}: Gitea holds ${stored.length} files of this name in `
          + 'different distributions or components, not all of them this asset, and its '
          + `listing does not say which one is in ${pkg.distribution || pkg.branch}`,
      };
    }
    return { ok: false, message: `${pkg.file}: Gitea holds a different file under this version` };
  }
  // With ?sign=true Gitea stores the signed file, whose SHA-256 never equals
  // the unsigned asset's.
  return {
    ok: true,
    message: `${pkg.file}: already uploaded; name, version-release and architecture `
      + 'match; the content was not compared (Gitea stores the signed file)',
  };
}

// fetch for one package file. A network error (fetch throws; Gitea gave no
// HTTP answer) is retried once after waitMs: on 2026-11-02 a slow Gitea
// dropped a .deb upload with "TypeError: fetch failed" and nothing else.
// Retrying a PUT is safe: when the first attempt stored the file, Gitea
// answers 409 and conflictVerdict compares it. An HTTP answer, error or not,
// is returned as it is. The second network error throws, naming the file and
// the cause.
async function fetchRetry(fetchFn, url, init, file, { attempts = 2, waitMs = 10000, sleep } = {}) {
  const wait = sleep || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  let last;
  for (let i = 1; i <= attempts; i += 1) {
    try {
      return await fetchFn(url, init);
    } catch (err) {
      last = err;
      if (i < attempts) await wait(waitMs);
    }
  }
  const cause = last && last.cause ? `: ${last.cause.code || last.cause.message || last.cause}` : '';
  throw new Error(`${file}: no answer from ${new URL(url).host} after ${attempts} attempts `
    + `(${last && last.message}${cause})`);
}

module.exports = {
  packageConfig, globMatches, debianDistribution, rpmGroup, debPackage, rpmPackage, apkPackage, isAlpineApk, uploadUrl, filesUrl, missingCredentials, conflictVerdict,
  fetchRetry,
};
