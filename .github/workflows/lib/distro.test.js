'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { RELEASES, distroPlan, byDistro } = require('./distro.js');

test('all releases on both architectures when nothing is named', () => {
  const legs = distroPlan('').include;
  assert.equal(legs.length, RELEASES.length * 2);
  assert.deepEqual(legs.find((l) => l.distro === 'debian-13' && l.arch === 'arm64'),
    { distro: 'debian-13', image: 'docker.io/library/debian:13', family: 'deb',
      arch: 'arm64', os: 'ubuntu-24.04-arm' });
});

test('amd64 runs on the x86 runner, before arm64', () => {
  const legs = distroPlan('fedora').include;
  assert.deepEqual(legs.map((l) => [l.arch, l.os]),
    [['amd64', 'ubuntu-24.04'], ['arm64', 'ubuntu-24.04-arm']]);
});

test('a block scalar narrows like a space list', () => {
  assert.deepEqual(distroPlan('debian-13\nalmalinux-10\n').include.map((l) => l.distro),
    ['debian-13', 'debian-13', 'almalinux-10', 'almalinux-10']);
  assert.deepEqual(distroPlan('debian-13 almalinux-10').include.map((l) => l.distro),
    ['debian-13', 'debian-13', 'almalinux-10', 'almalinux-10']);
});

test('the order of include is the table order, not the order named', () => {
  assert.deepEqual(distroPlan('almalinux-10 debian-13').include.map((l) => l.distro),
    ['debian-13', 'debian-13', 'almalinux-10', 'almalinux-10']);
});

test('a name given twice builds once', () => {
  assert.equal(distroPlan('debian-13 debian-13').include.length, 2);
});

test('an unknown name fails and lists the known ones', () => {
  assert.throws(() => distroPlan('debian-11'),
    /distributions names debian-11, which this piece does not build; it builds debian-12 /);
});

test('only blanks fails, the empty string means all', () => {
  assert.throws(() => distroPlan(' \n '), /distributions names no release/);
  assert.ok(distroPlan('').include.length > 0);
});

test('every release has the field of its family and no other', () => {
  const field = { deb: 'codename', rpm: 'dist', apk: 'branch' };
  for (const r of RELEASES) {
    assert.ok(field[r.family], `${r.distro}: unknown family ${r.family}`);
    for (const [f, key] of Object.entries(field)) {
      if (f === r.family) assert.ok(r[key], `${r.distro} needs ${key}`);
      else assert.equal(r[key], undefined, `${r.distro} must not have ${key}`);
    }
    assert.match(r.image, /^docker\.io\/library\/[a-z]+:\d[\d.]*$/);
  }
});

test('the table holds the ten releases of D38 with unique ids', () => {
  assert.equal(new Set(RELEASES.map((r) => r.distro)).size, 10);
  assert.equal(RELEASES.filter((r) => r.family === 'apk').length, 2);
  assert.equal(RELEASES.filter((r) => r.distro === 'fedora').length, 1);
});

test('byDistro finds a release or returns undefined', () => {
  assert.equal(byDistro('debian-12').codename, 'bookworm');
  assert.equal(byDistro('nope'), undefined);
});
