'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { byDistro } = require('./distro.js');
const { expand, readBack } = require('./nfpm.js');
const { packVariables, pack } = require('./distro-pack.js');

const base = {
  version: '1.4.0', epoch: '1700000000', stage: '/s', arch: 'amd64',
};
const DEB13 = 'ID=debian\nVERSION_ID="13"\nVERSION_CODENAME=trixie\n';
const ALMA9 = 'ID="almalinux"\nVERSION_ID="9.5"\n';
const ALPINE = 'ID=alpine\nVERSION_ID=3.24.0\n';

test('deb gets the codename in the version and release 1', () => {
  const v = packVariables({
    ...base,
    release: byDistro('debian-13'),
    osRelease: { ID: 'debian', VERSION_ID: '13', VERSION_CODENAME: 'trixie' },
    depends: ['libc6 (>= 2.36)', 'zlib1g (>= 1:1.2.0)'],
  });
  assert.equal(v.VERSION, '1.4.0~trixie');
  assert.equal(v.PKG_RELEASE, '1');
  assert.equal(v.DEPENDS, '"libc6 (>= 2.36)", "zlib1g (>= 1:1.2.0)"');
  assert.equal(v.CODENAME, 'trixie');
  assert.equal(v.DISTRO, 'debian-13');
  assert.equal(v.ID, 'debian');
  assert.equal(v.VERSION_ID, '13');
  assert.equal(v.PACKAGER, 'deb');
  assert.equal(v.ARCH, 'amd64');
  assert.equal(v.STAGE, '/s');
  assert.equal(v.SOURCE_DATE_EPOCH, '1700000000');
  assert.equal(v.MTIME, '2023-11-14T22:13:20Z');
  assert.equal(Object.keys(v).length, 12);
});

test('rpm puts the dist tag in the release', () => {
  const v = packVariables({
    ...base,
    release: byDistro('almalinux-9'),
    osRelease: { ID: 'almalinux', VERSION_ID: '9.5' },
    depends: [],
  });
  assert.equal(v.VERSION, '1.4.0');
  assert.equal(v.PKG_RELEASE, '1.el9');
  assert.equal(v.CODENAME, '');
});

test('apk has release 0 and the plain version', () => {
  const v = packVariables({
    ...base,
    release: byDistro('alpine-3.24'),
    osRelease: { ID: 'alpine', VERSION_ID: '3.24.0' },
    depends: ['so:libz.so.1'],
  });
  assert.equal(v.VERSION, '1.4.0');
  assert.equal(v.PKG_RELEASE, '0');
  assert.equal(v.CODENAME, '');
});

test('no dependencies expand to an empty flow sequence', () => {
  const v = packVariables({
    ...base, release: byDistro('debian-13'), osRelease: { ID: 'debian', VERSION_ID: '13', VERSION_CODENAME: 'trixie' }, depends: [],
  });
  assert.equal(expand('depends: [${DEPENDS}]\n', v, 'c'), 'depends: []\n');
});

test('a double quote in a dependency is escaped', () => {
  const v = packVariables({
    ...base, release: byDistro('debian-13'), osRelease: { ID: 'debian', VERSION_ID: '13', VERSION_CODENAME: 'trixie' }, depends: ['a"b'],
  });
  assert.equal(v.DEPENDS, '"a\\"b"');
});

test('the release must match the image', () => {
  assert.throws(() => packVariables({
    ...base,
    release: byDistro('debian-13'),
    osRelease: { ID: 'debian', VERSION_ID: '12', VERSION_CODENAME: 'bookworm' },
    depends: [],
  }), /debian-13 expects trixie, the image says bookworm/);
  assert.throws(() => packVariables({
    ...base,
    release: byDistro('alpine-3.24'),
    osRelease: { ID: 'alpine', VERSION_ID: '3.23.2' },
    depends: [],
  }), /alpine-3.24 expects 3.24, the image says 3.23/);
});

const CONFIG = [
  'name: lectover',
  'version: "${VERSION}"',
  'release: "${PKG_RELEASE}"',
  'depends: [${DEPENDS}]',
  'contents:',
  '  - src: ${STAGE}/bin/lectover',
  '',
].join('\n');

// Stand-ins for git, nfpm and the read-back tools. `back` shapes what the
// package claims to hold.
function fakeIo({
  osRelease = DEB13, depends = 'libc6 (>= 2.36)\n', config = CONFIG, back = {}, twin = false,
} = {}) {
  const files = {
    'cfg.yaml': config, '/os-release': osRelease, '/deps': depends,
  };
  const dirs = new Map();
  const written = new Map();
  const calls = [];
  const add = (dir, entry) => {
    if (!dirs.has(dir)) dirs.set(dir, new Set());
    if (entry !== undefined) dirs.get(dir).add(entry);
  };
  const io = {
    isFile: (path) => Object.hasOwn(files, path),
    read: (path) => files[path],
    write: (path, text) => written.set(path, text),
    mkdir: (path) => add(path),
    list: (path) => [...(dirs.get(path) || [])].sort(),
    exec: (command, args, options) => {
      calls.push({ command, args, env: options && options.env });
      if (command === 'git') return '1700000000\n';
      if (command === 'nfpm') {
        const { PACKAGER, ARCH, VERSION, PKG_RELEASE } = options.env;
        const apkArch = ARCH === 'amd64' ? 'x86_64' : 'aarch64';
        const file = {
          deb: `lectover_${VERSION}-${PKG_RELEASE}_${ARCH}.deb`,
          rpm: `lectover-${VERSION}-${PKG_RELEASE}.${apkArch}.rpm`,
          apk: `lectover_${VERSION}-r${PKG_RELEASE}_${apkArch}.apk`,
        }[PACKAGER];
        add('packages', file);
        if (twin) add('packages', `other-${file}`);
        return null;
      }
      if (command === 'mv') {
        const [from, to] = args;
        dirs.get('packages').delete(from.replace('packages/', ''));
        add('packages', to.replace('packages/', ''));
        return '';
      }
      if (command === 'dpkg-deb' && args[0] === '--field') {
        return args[2] === 'Depends'
          ? `${back.depends === undefined ? 'libc6 (>= 2.36)' : back.depends}\n`
          : `${back.version || '1.4.0~trixie-1'}\n`;
      }
      if (command === 'dpkg-deb') return 'drwxr-xr-x root/root 0 ./usr/\n-rwxr-xr-x root/root 1 ./usr/bin/lectover';
      if (command === 'rpm' && args[1] === '--queryformat') return back.version || '1.4.0';
      if (command === 'rpm' && args[1] === '--requires') {
        return (back.depends === undefined ? 'libc.so.6()(64bit)\nrpmlib(CompressedFileNames) <= 3.0.4-1' : back.depends);
      }
      if (command === 'rpm') return back.files === undefined ? '/usr/bin/lectover' : back.files;
      if (command === 'tar' && args.includes('.PKGINFO')) {
        return `pkgname = lectover\npkgver = ${back.version || '1.4.0-r0'}\n`
          + (back.depends === undefined ? 'depend = so:libc.musl-x86_64.so.1\n' : back.depends);
      }
      if (command === 'tar') {
        return back.files === undefined ? '.PKGINFO\n.SIGN.RSA.x\nusr/\nusr/bin/lectover\n' : back.files;
      }
      throw new Error(`unexpected command ${command}`);
    },
  };
  return { io, written, calls, dirs };
}

function env(overrides = {}) {
  return {
    VERSION: '1.4.0', DISTRO: 'debian-13', ARCH: 'amd64', CONFIG: 'cfg.yaml', STAGE: '/stage',
    PACKAGERS: '', OS_RELEASE: '/os-release', DEPENDS_FILE: '/deps', HAS_ELF: 'true',
    RUNNER_TEMP: '/t', ...overrides,
  };
}

test('a deb is packed, filled in and read back', () => {
  const { io, written, calls } = fakeIo();
  const lines = pack(env(), io);
  assert.deepEqual(lines, ['lectover_1.4.0~trixie-1_amd64.deb: version 1.4.0~trixie-1, 1 files']);
  const cfg = [...written.values()][0];
  assert.match(cfg, /version: "1.4.0~trixie"/);
  assert.match(cfg, /depends: \["libc6 \(>= 2.36\)"\]/);
  assert.match(cfg, /src: \/stage\/bin\/lectover/);
  const run = calls.find((c) => c.command === 'nfpm');
  assert.equal(run.env.PACKAGER, 'deb');
  assert.deepEqual(run.args.slice(0, 2), ['package', '--config']);
  assert.ok(run.args.includes('deb'));
});

test('a rpm needs the dist the image reports', () => {
  const { io } = fakeIo({ osRelease: ALMA9 });
  const e = env({ DISTRO: 'almalinux-9', RPM_DIST: '.el9' });
  assert.deepEqual(pack(e, io), ['lectover-1.4.0-1.el9.x86_64.rpm: version 1.4.0, 1 files']);
  assert.throws(() => pack({ ...e, RPM_DIST: '.el10' }, fakeIo({ osRelease: ALMA9 }).io),
    /almalinux-9 expects el9, the image says el10/);
  assert.throws(() => pack({ ...e, RPM_DIST: undefined }, fakeIo({ osRelease: ALMA9 }).io),
    /RPM_DIST/);
});

test('apk is renamed with the Alpine release', () => {
  const { io, dirs } = fakeIo({ osRelease: ALPINE });
  const lines = pack(env({ DISTRO: 'alpine-3.24' }), io);
  assert.deepEqual([...dirs.get('packages')], ['lectover-1.4.0-r0-alpine3.24-x86_64.apk']);
  assert.deepEqual(lines, ['lectover-1.4.0-r0-alpine3.24-x86_64.apk: version 1.4.0-r0, 1 files']);
});

test('apk on arm64 is named aarch64', () => {
  const { io, dirs } = fakeIo({ osRelease: ALPINE });
  pack(env({ DISTRO: 'alpine-3.24', ARCH: 'arm64' }), io);
  assert.deepEqual([...dirs.get('packages')], ['lectover-1.4.0-r0-alpine3.24-aarch64.apk']);
});

test('PACKAGERS adds variables for the release family only', () => {
  const cfg = `${CONFIG}# \${EXTRA}\n`;
  const e = env({ PACKAGERS: '{"deb": {"EXTRA": "one"}, "rpm": {"EXTRA": "two"}}' });
  const { io, written } = fakeIo({ config: cfg });
  pack(e, io);
  assert.match([...written.values()][0], /# one/);
});

test('PACKAGERS may not shadow a variable of the piece', () => {
  assert.throws(() => pack(env({ PACKAGERS: '{"deb": {"DEPENDS": "x"}}' }), fakeIo().io),
    /packagers\.deb sets DEPENDS/);
  assert.throws(() => pack(env({ PACKAGERS: '{"deb": {"ID": "x"}}' }), fakeIo().io),
    /packagers\.deb sets ID/);
  assert.throws(() => pack(env({ PACKAGERS: '{"zip": {}}' }), fakeIo().io),
    /packagers names zip/);
});

test('an unknown name in the config fails before nfpm runs', () => {
  const { io, calls } = fakeIo({ config: '${NOPE}\n' });
  assert.throws(() => pack(env(), io), /\$\{NOPE\}/);
  assert.equal(calls.filter((c) => c.command === 'nfpm').length, 0);
});

test('a missing config fails', () => {
  assert.throws(() => pack(env({ CONFIG: 'x.yaml' }), fakeIo().io), /x\.yaml does not exist/);
});

test('an unknown DISTRO fails', () => {
  assert.throws(() => pack(env({ DISTRO: 'gentoo' }), fakeIo().io), /gentoo/);
});

test('two files from nfpm fail the run', () => {
  assert.throws(() => pack(env(), fakeIo({ twin: true }).io),
    /nfpm wrote 2 files for debian-13 amd64/);
});

test('a wrong version fails the read-back', () => {
  assert.throws(() => pack(env(), fakeIo({ back: { version: '9.9.9-1' } }).io),
    /carries version 9\.9\.9-1, not 1\.4\.0~trixie/);
});

test('a package without files fails the read-back', () => {
  const { io } = fakeIo({ osRelease: ALMA9, back: { files: '' } });
  assert.throws(() => pack(env({ DISTRO: 'almalinux-9', RPM_DIST: '.el9' }), io), /holds no files/);
});

test('an ELF package without dependencies fails the read-back', () => {
  const { io } = fakeIo({ depends: '', back: { depends: '' } });
  assert.throws(() => pack(env(), io), /no dependencies.*HAS_ELF/);
});

test('a package without ELF files may have no dependencies', () => {
  const { io } = fakeIo({ depends: '', back: { depends: '' } });
  assert.equal(pack(env({ HAS_ELF: 'false' }), io).length, 1);
});

test('rpmlib requires do not count as dependencies', () => {
  const { io } = fakeIo({
    osRelease: ALMA9, depends: '', back: { depends: 'rpmlib(CompressedFileNames) <= 3.0.4-1' },
  });
  assert.throws(() => pack(env({ DISTRO: 'almalinux-9', RPM_DIST: '.el9' }), io), /HAS_ELF/);
});

test('empty PACKAGERS and {} both build the release family alone', () => {
  for (const packagers of ['', '{}']) {
    assert.equal(pack(env({ PACKAGERS: packagers }), fakeIo().io).length, 1);
  }
});

test('an apk read-back reports version and files from the tar listing', () => {
  const { io } = fakeIo();
  const back = readBack('apk', 'p.apk', io.exec);
  assert.deepEqual(back, { version: '1.4.0-r0', files: ['usr/bin/lectover'] });
});
