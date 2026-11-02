'use strict';

// publish-gitea-packages (D27): which release assets are packages, where
// Gitea wants them, and what a 409 on a re-run means.

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

// The distribution a .deb goes to. Without a map every .deb goes to
// debian.distribution. With a map, a file no glob or several globs match is
// an error: falling back would put a package built for one release into the
// channel of another.
function debianDistribution(cfg, file) {
  const globs = Object.keys(cfg.distributions || {});
  if (globs.length === 0) return { ok: true, distribution: cfg.distribution };
  const hits = globs.filter((glob) => globMatches(glob, file));
  if (hits.length === 1) return { ok: true, distribution: cfg.distributions[hits[0]] };
  if (hits.length === 0) {
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

// name_version_arch.deb (cargo-deb) and name-version-release.arch.rpm
// (cargo-generate-rpm). Gitea's RPM version is the version-release pair.
const DEB = /^([a-z0-9][a-z0-9+.-]*)_([^_/]+)_([a-z0-9]+)\.deb$/;
const RPM = /^(.+)-([^-/]+)-([^-/]+)\.([A-Za-z0-9_]+)\.rpm$/;

function parsePackageFile(file) {
  let m = DEB.exec(file);
  if (m) return { kind: 'debian', name: m[1], version: m[2], arch: m[3], file };
  m = RPM.exec(file);
  if (m) return { kind: 'rpm', name: m[1], version: `${m[2]}-${m[3]}`, arch: m[4], file };
  return null;
}

const seg = encodeURIComponent;

function uploadUrl(cfg, pkg) {
  const base = `${cfg.url}/api/packages/${seg(cfg.owner)}`;
  if (pkg.kind === 'debian') {
    return `${base}/debian/pool/${seg(pkg.distribution || cfg.distribution)}/${seg(cfg.component)}/upload`;
  }
  // Gitea's generated .repo sets gpgcheck=1, so an unsigned rpm would not
  // install. Gitea signs with its per-owner key.
  return `${base}/rpm${cfg.group ? `/${seg(cfg.group)}` : ''}/upload?sign=true`;
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
          + `listing does not say which one is in ${pkg.distribution}`,
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

module.exports = {
  packageConfig, globMatches, debianDistribution, parsePackageFile, uploadUrl, filesUrl, missingCredentials, conflictVerdict,
};
