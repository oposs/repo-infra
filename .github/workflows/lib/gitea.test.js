'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const g = require('./gitea.js');

const CONFIG = { gitea_packages: { url: 'https://gitea.oetiker.ch/', owner: 'oposs' } };
const CFG = g.packageConfig(CONFIG);

test('the default layout is one channel', () => {
  assert.deepEqual(CFG, {
    url: 'https://gitea.oetiker.ch', owner: 'oposs',
    distribution: 'stable', distributions: {}, component: 'main', group: '',
  });
});

test('a config without url or owner is refused', () => {
  assert.throws(() => g.packageConfig({}), /gitea_packages/);
  assert.throws(() => g.packageConfig({ gitea_packages: { url: 'https://x' } }), /owner/);
});

test('cargo-deb and cargo-generate-rpm names parse', () => {
  assert.deepEqual(g.parsePackageFile('mdmost_0.5.0-1_amd64.deb'), {
    kind: 'debian', name: 'mdmost', version: '0.5.0-1', arch: 'amd64',
    file: 'mdmost_0.5.0-1_amd64.deb',
  });
  assert.deepEqual(g.parsePackageFile('smtp-proxy-0.1.0-1.aarch64.rpm'), {
    kind: 'rpm', name: 'smtp-proxy', version: '0.1.0-1', arch: 'aarch64',
    file: 'smtp-proxy-0.1.0-1.aarch64.rpm',
  });
});

test('a pre-release deb version with ~ parses', () => {
  assert.equal(g.parsePackageFile('mdmost_1.0.0~rc.1-1_arm64.deb').version, '1.0.0~rc.1-1');
});

test('anything else is not a package', () => {
  for (const name of ['mdmost-0.5.0-x86_64-unknown-linux-musl.tar.gz', 'release-build.json',
    'mdmost.deb', 'x.rpm']) {
    assert.equal(g.parsePackageFile(name), null, name);
  }
});

test('upload urls follow the Gitea API, rpm is always signed', () => {
  assert.equal(g.uploadUrl(CFG, g.parsePackageFile('mdmost_0.5.0-1_amd64.deb')),
    'https://gitea.oetiker.ch/api/packages/oposs/debian/pool/stable/main/upload');
  assert.equal(g.uploadUrl(CFG, g.parsePackageFile('mdmost-0.5.0-1.x86_64.rpm')),
    'https://gitea.oetiker.ch/api/packages/oposs/rpm/upload?sign=true');
  assert.equal(g.uploadUrl({ ...CFG, group: 'el9' }, g.parsePackageFile('mdmost-0.5.0-1.x86_64.rpm')),
    'https://gitea.oetiker.ch/api/packages/oposs/rpm/el9/upload?sign=true');
});

test('the files url names type, package and version', () => {
  assert.equal(g.filesUrl(CFG, g.parsePackageFile('mdmost_1.0.0~rc.1-1_amd64.deb')),
    'https://gitea.oetiker.ch/api/v1/packages/oposs/debian/mdmost/1.0.0~rc.1-1/files');
});

test('missing credentials are named, both of them', () => {
  assert.deepEqual(g.missingCredentials({}), ['GITEA_PACKAGE_TOKEN', 'GITEA_PACKAGE_USER']);
  assert.deepEqual(g.missingCredentials({ GITEA_PACKAGE_TOKEN: 't', GITEA_PACKAGE_USER: '' }),
    ['GITEA_PACKAGE_USER']);
  assert.deepEqual(g.missingCredentials({ GITEA_PACKAGE_TOKEN: 't', GITEA_PACKAGE_USER: 'u' }), []);
});

const DEB = g.parsePackageFile('mdmost_0.5.0-1_amd64.deb');
const RPM = g.parsePackageFile('mdmost-0.5.0-1.x86_64.rpm');

test('a 409 for a deb with the same SHA-256 is success', () => {
  const v = g.conflictVerdict(DEB, 'abc', [{ name: DEB.file, sha256: 'abc' }]);
  assert.equal(v.ok, true);
  assert.match(v.message, /SHA-256/);
});

test('a 409 for a different deb under the same version fails', () => {
  const v = g.conflictVerdict(DEB, 'abc', [{ name: DEB.file, sha256: 'def' }]);
  assert.equal(v.ok, false);
  assert.match(v.message, /different/);
});

test('a 409 for an rpm matches by file name and says the content was not compared', () => {
  const v = g.conflictVerdict(RPM, 'abc', [{ name: RPM.file, sha256: 'signed' }]);
  assert.equal(v.ok, true);
  assert.match(v.message, /not compared/);
});

test('a 409 whose file Gitea does not list fails for either kind', () => {
  assert.equal(g.conflictVerdict(DEB, 'abc', []).ok, false);
  assert.equal(g.conflictVerdict(RPM, 'abc', [{ name: 'mdmost-0.5.0-1.aarch64.rpm' }]).ok, false);
});

const WG = {
  gitea_packages: {
    url: 'https://gitea.oetiker.ch', owner: 'oposs',
    debian: {
      component: 'main',
      distributions: {
        'wg-wrangler_*~noble_*.deb': 'noble',
        'wg-wrangler_*~jammy_*.deb': 'jammy',
        'wg-wrangler_*~trixie_*.deb': 'trixie',
      },
    },
  },
};
const WGCFG = g.packageConfig(WG);

test('globs know * and ? and match the whole name', () => {
  assert.equal(g.globMatches('wg-wrangler_*~noble_*.deb', 'wg-wrangler_0.4.1~noble_amd64.deb'), true);
  assert.equal(g.globMatches('*~noble_*.deb', 'x_0.4.1~noble_amd64.deb.sig'), false);
  assert.equal(g.globMatches('noble', 'x_0.4.1~noble_amd64.deb'), false);
  assert.equal(g.globMatches('x_1.?_amd64.deb', 'x_1.2_amd64.deb'), true);
  assert.equal(g.globMatches('x_1.?_amd64.deb', 'x_1.23_amd64.deb'), false);
  // Every other character is literal, the dot included.
  assert.equal(g.globMatches('x_1.2_amd64.deb', 'x_1x2_amd64.deb'), false);
  assert.equal(g.globMatches('x+(1)_[a]_amd64.deb', 'x+(1)_[a]_amd64.deb'), true);
});

test('a deb matching one glob goes to that distribution', () => {
  const file = 'wg-wrangler_0.4.1~noble_amd64.deb';
  assert.deepEqual(g.debianDistribution(WGCFG, file), { ok: true, distribution: 'noble' });
  const pkg = { ...g.parsePackageFile(file), distribution: 'noble' };
  assert.equal(g.uploadUrl(WGCFG, pkg),
    'https://gitea.oetiker.ch/api/packages/oposs/debian/pool/noble/main/upload');
});

test('without a map every deb goes to debian.distribution', () => {
  assert.deepEqual(g.debianDistribution(CFG, 'mdmost_0.5.0-1_amd64.deb'),
    { ok: true, distribution: 'stable' });
  const own = g.packageConfig({ gitea_packages: {
    url: 'https://x', owner: 'o', debian: { distribution: 'bookworm', distributions: {} } } });
  assert.deepEqual(g.debianDistribution(own, 'mdmost_0.5.0-1_amd64.deb'),
    { ok: true, distribution: 'bookworm' });
});

test('with a map a deb no glob matches is refused, naming the file', () => {
  const v = g.debianDistribution(WGCFG, 'wg-wrangler_0.4.1~bookworm_amd64.deb');
  assert.equal(v.ok, false);
  assert.equal(v.message, 'wg-wrangler_0.4.1~bookworm_amd64.deb: no glob in '
    + '"gitea_packages.debian.distributions" matches it');
});

test('a deb several globs match is refused, naming file and globs', () => {
  const cfg = g.packageConfig({ gitea_packages: { url: 'https://x', owner: 'o', debian: {
    distributions: { '*~noble_*.deb': 'noble', 'wg-wrangler_*.deb': 'stable' } } } });
  const v = g.debianDistribution(cfg, 'wg-wrangler_0.4.1~noble_amd64.deb');
  assert.equal(v.ok, false);
  assert.equal(v.message, 'wg-wrangler_0.4.1~noble_amd64.deb: several globs in '
    + '"gitea_packages.debian.distributions" match it (*~noble_*.deb, wg-wrangler_*.deb)');
});

test('a malformed distributions map is refused with the key named', () => {
  const bad = (distributions) => () => g.packageConfig({ gitea_packages: {
    url: 'https://x', owner: 'o', debian: { distributions } } });
  for (const shape of [null, [], 'noble', 3]) {
    assert.throws(bad(shape), /"gitea_packages\.debian\.distributions" must be an object/,
      JSON.stringify(shape));
  }
  assert.throws(bad({ '': 'noble' }), /has an empty glob/);
  assert.throws(bad({ '*.deb': '' }), /"\*\.deb" must name a distribution/);
  assert.throws(bad({ '*.deb': 7 }), /"\*\.deb" must name a distribution/);
  assert.throws(bad({ '*.deb': 'noble main' }), /Gitea refuses/);
  assert.throws(bad({ '*.deb': '-noble' }), /Gitea refuses/);
});

test('rpm ignores the distribution map', () => {
  assert.equal(g.uploadUrl(WGCFG, g.parsePackageFile('wg-wrangler-0.4.1-1.x86_64.rpm')),
    'https://gitea.oetiker.ch/api/packages/oposs/rpm/upload?sign=true');
});

test('a 409 for a deb whose name Gitea lists in several distributions', () => {
  const pkg = { ...DEB, distribution: 'noble' };
  assert.equal(g.conflictVerdict(pkg, 'abc', [
    { name: DEB.file, sha256: 'abc' }, { name: DEB.file, sha256: 'abc' }]).ok, true);
  const v = g.conflictVerdict(pkg, 'abc', [
    { name: DEB.file, sha256: 'abc' }, { name: DEB.file, sha256: 'def' }]);
  assert.equal(v.ok, false);
  assert.match(v.message, /2 files of this name .* in noble$/);
});

// fetchOnce stands in for fetch: a TypeError('fetch failed') with a cause is
// what undici throws when the connection drops.
function netError(code) {
  return new TypeError('fetch failed', { cause: Object.assign(new Error(code), { code }) });
}
const noWait = () => Promise.resolve();

test('a network error is retried once and the second answer is returned', async () => {
  const calls = [];
  const answers = [() => { throw netError('UND_ERR_SOCKET'); }, () => ({ ok: true, status: 201 })];
  const res = await g.fetchRetry(async (url, init) => { calls.push([url, init]); return answers[calls.length - 1](); },
    'https://g/x', { method: 'PUT' }, 'a.deb', { sleep: noWait });
  assert.equal(res.status, 201);
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[1], ['https://g/x', { method: 'PUT' }]);
});

test('an HTTP answer, even an error, is not retried', async () => {
  let n = 0;
  const res = await g.fetchRetry(async () => { n += 1; return { ok: false, status: 500 }; },
    'https://g/x', {}, 'a.deb', { sleep: noWait });
  assert.equal(res.status, 500);
  assert.equal(n, 1);
});

test('a second network error fails naming the file and the cause', async () => {
  let n = 0;
  await assert.rejects(
    g.fetchRetry(async () => { n += 1; throw netError('ETIMEDOUT'); }, 'https://g/x', {}, 'edaptor_1.9.0-1_amd64.deb', { sleep: noWait }),
    (err) => {
      assert.match(err.message, /^edaptor_1\.9\.0-1_amd64\.deb: /);
      assert.match(err.message, /ETIMEDOUT/);
      assert.match(err.message, /2 attempts/);
      return true;
    });
  assert.equal(n, 2);
});

test('the wait between the attempts is the one given', async () => {
  const waits = [];
  const answers = [() => { throw netError('ECONNRESET'); }, () => ({ ok: true, status: 201 })];
  let n = 0;
  await g.fetchRetry(async () => answers[n++](), 'https://g/x', {}, 'a.rpm',
    { sleep: (ms) => { waits.push(ms); return Promise.resolve(); }, waitMs: 1234 });
  assert.deepEqual(waits, [1234]);
});
