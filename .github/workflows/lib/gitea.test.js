'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
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

// What `dpkg-deb --field <file> Package Version Architecture` prints, and the
// name GitHub lists the asset under: it turns every `~` into `.` (#129).
const control = (name, version, arch) => `Package: ${name}\nVersion: ${version}\nArchitecture: ${arch}\n`;
const github = (name) => name.replace(/~/g, '.');
function deb(name, version, arch = 'amd64') {
  const file = `${name}_${version}_${arch}.deb`;
  const v = g.debPackage(control(name, version, arch), github(file));
  assert.equal(v.ok, true, v.message);
  return v.pkg;
}

test('a deb is named from its control data, not from the asset name', () => {
  assert.deepEqual(
    g.debPackage(control('wg-wrangler', '0.5.0~bookworm', 'amd64'), 'wg-wrangler_0.5.0.bookworm_amd64.deb'),
    { ok: true, pkg: {
      kind: 'debian', name: 'wg-wrangler', version: '0.5.0~bookworm', arch: 'amd64',
      file: 'wg-wrangler_0.5.0~bookworm_amd64.deb', asset: 'wg-wrangler_0.5.0.bookworm_amd64.deb',
    } });
});

test('a pre-release deb keeps the ~ GitHub took out of the asset name', () => {
  const pkg = deb('mdmost', '1.0.0~rc.1-1', 'arm64');
  assert.equal(pkg.version, '1.0.0~rc.1-1');
  assert.equal(pkg.asset, 'mdmost_1.0.0.rc.1-1_arm64.deb');
});

test('control data without package, version or architecture is refused, naming the asset', () => {
  assert.deepEqual(g.debPackage('Package: x\nArchitecture: all\n', 'x.deb'),
    { ok: false, message: 'x.deb: the control data has no Version' });
  assert.deepEqual(g.debPackage('', 'y.deb'),
    { ok: false, message: 'y.deb: the control data has no Package, Version, Architecture' });
});

// Real packages built by nfpm 2.43.0: tool 1.0.0~rc.1-1 x86_64, and tool
// 0.5.0-1 aarch64 with epoch 2. rpm -qp reads them the same way.
const FIXTURES = path.join(__dirname, '../../../tests/fixtures/rpm');
function rpm(file) {
  const v = g.rpmPackage(fs.readFileSync(path.join(FIXTURES, file)), github(file));
  assert.equal(v.ok, true, v.message);
  return v.pkg;
}

test('an rpm is named from its header, not from the asset name', () => {
  assert.deepEqual(rpm('tool-1.0.0~rc.1-1.x86_64.rpm'), {
    kind: 'rpm', name: 'tool', version: '1.0.0~rc.1-1', arch: 'x86_64',
    file: 'tool-1.0.0~rc.1-1.x86_64.rpm', asset: 'tool-1.0.0.rc.1-1.x86_64.rpm',
  });
});

test('an rpm epoch leads the version as Gitea writes it', () => {
  // Gitea: version [epoch-]version-release, file name-version.arch.rpm.
  const pkg = rpm('tool-0.5.0-1.aarch64.rpm');
  assert.equal(pkg.version, '2-0.5.0-1');
  assert.equal(pkg.file, 'tool-2-0.5.0-1.aarch64.rpm');
});

test('a file that is not an rpm is refused, naming the asset', () => {
  assert.deepEqual(g.rpmPackage(Buffer.from('junk'), 'x.rpm'),
    { ok: false, message: 'x.rpm: not an rpm package (no readable header)' });
  const cut = fs.readFileSync(path.join(FIXTURES, 'tool-0.5.0-1.aarch64.rpm')).subarray(0, 300);
  assert.equal(g.rpmPackage(cut, 'cut.rpm').ok, false);
});

test('upload urls follow the Gitea API, rpm is always signed', () => {
  assert.equal(g.uploadUrl(CFG, deb('mdmost', '0.5.0-1')),
    'https://gitea.oetiker.ch/api/packages/oposs/debian/pool/stable/main/upload');
  assert.equal(g.uploadUrl(CFG, rpm('tool-1.0.0~rc.1-1.x86_64.rpm')),
    'https://gitea.oetiker.ch/api/packages/oposs/rpm/upload?sign=true');
  assert.equal(g.uploadUrl({ ...CFG, group: 'el9' }, rpm('tool-1.0.0~rc.1-1.x86_64.rpm')),
    'https://gitea.oetiker.ch/api/packages/oposs/rpm/el9/upload?sign=true');
});

// Gitea's documented groups include rocky/el9 and test/fc38; encoding the
// whole group sent them to rocky%2Fel9.
test('an rpm group with a slash keeps the slash and encodes each segment', () => {
  assert.equal(g.uploadUrl({ ...CFG, group: 'rocky/el9' }, rpm('tool-1.0.0~rc.1-1.x86_64.rpm')),
    'https://gitea.oetiker.ch/api/packages/oposs/rpm/rocky/el9/upload?sign=true');
  assert.equal(g.uploadUrl({ ...CFG, group: 'a b/el9' }, rpm('tool-1.0.0~rc.1-1.x86_64.rpm')),
    'https://gitea.oetiker.ch/api/packages/oposs/rpm/a%20b/el9/upload?sign=true');
});

test('the files url names type, package and version', () => {
  assert.equal(g.filesUrl(CFG, deb('mdmost', '1.0.0~rc.1-1')),
    'https://gitea.oetiker.ch/api/v1/packages/oposs/debian/mdmost/1.0.0~rc.1-1/files');
});

test('missing credentials are named, both of them', () => {
  assert.deepEqual(g.missingCredentials({}), ['GITEA_PACKAGE_TOKEN', 'GITEA_PACKAGE_USER']);
  assert.deepEqual(g.missingCredentials({ GITEA_PACKAGE_TOKEN: 't', GITEA_PACKAGE_USER: '' }),
    ['GITEA_PACKAGE_USER']);
  assert.deepEqual(g.missingCredentials({ GITEA_PACKAGE_TOKEN: 't', GITEA_PACKAGE_USER: 'u' }), []);
});

const DEB = deb('mdmost', '0.5.0-1');
const RPM = rpm('tool-1.0.0~rc.1-1.x86_64.rpm');

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

test('a 409 for a deb whose version has a ~ finds the file Gitea stored', () => {
  // Gitea lists the file under the control name; the asset name has a `.`.
  const pkg = deb('wg-wrangler', '0.5.0~bookworm');
  assert.equal(g.filesUrl(CFG, pkg),
    'https://gitea.oetiker.ch/api/v1/packages/oposs/debian/wg-wrangler/0.5.0~bookworm/files');
  const v = g.conflictVerdict(pkg, 'abc', [{ name: 'wg-wrangler_0.5.0~bookworm_amd64.deb', sha256: 'abc' }]);
  assert.equal(v.ok, true, v.message);
});

test('a 409 for an rpm whose version has a ~ finds the file Gitea stored', () => {
  assert.equal(g.filesUrl(CFG, RPM),
    'https://gitea.oetiker.ch/api/v1/packages/oposs/rpm/tool/1.0.0~rc.1-1/files');
  assert.equal(g.conflictVerdict(RPM, 'abc', [{ name: 'tool-1.0.0~rc.1-1.x86_64.rpm' }]).ok, true);
});

test('a 409 for an rpm matches by file name and says the content was not compared', () => {
  const v = g.conflictVerdict(RPM, 'abc', [{ name: RPM.file, sha256: 'signed' }]);
  assert.equal(v.ok, true);
  assert.match(v.message, /not compared/);
});

test('a 409 whose file Gitea does not list fails for either kind', () => {
  assert.equal(g.conflictVerdict(DEB, 'abc', []).ok, false);
  assert.equal(g.conflictVerdict(RPM, 'abc', [{ name: RPM.asset }]).ok, false);
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
  const pkg = { ...deb('wg-wrangler', '0.4.1~noble'), distribution: 'noble' };
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
  assert.equal(g.uploadUrl(WGCFG, rpm('tool-1.0.0~rc.1-1.x86_64.rpm')),
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
