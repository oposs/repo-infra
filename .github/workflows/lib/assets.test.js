'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const assets = require('./assets.js');

// The release smtp-proxy-rs's publish-deb-container job produces.
const RELEASE = [
  'smtp-proxy-0.1.0-x86_64-unknown-linux-musl',
  'smtp-proxy_0.1.0-1_amd64.deb',
];
const EXPECTED = ['*.deb', 'smtp-proxy-*-x86_64-unknown-linux-musl'];

test('a complete release is missing nothing', () => {
  assert.deepEqual(assets.missingAssets(RELEASE, EXPECTED), []);
});

test('the empty release names every expectation', () => {
  // The defect this guard exists for: finalize ran before the add-on job had
  // uploaded anything, because its `needs:` had been reverted.
  assert.deepEqual(assets.missingAssets([], EXPECTED), EXPECTED);
});

test('a half-uploaded release is still a failure', () => {
  // finalize racing an add-on that is mid-upload. The binary is there and the
  // .deb is not, which is exactly the release an operator must never see.
  const half = ['smtp-proxy-0.1.0-x86_64-unknown-linux-musl'];
  assert.deepEqual(assets.missingAssets(half, EXPECTED), ['*.deb']);
});

test('expecting nothing passes on a release with no assets', () => {
  // publish-crates-io attaches nothing to the GitHub release on purpose.
  assert.deepEqual(assets.missingAssets([], []), []);
});

test('an unexpected extra asset is not a failure', () => {
  // A repository that attaches something by hand is not broken. A guard that
  // went red on it would train people to route around finalize.
  assert.deepEqual(assets.missingAssets([...RELEASE, 'SHA256SUMS'], EXPECTED), []);
});

test('the version is what the star absorbs', () => {
  // The reason patterns exist at all: a literal name would be the second place
  // the version is written down, and would go red on the next release.
  const next = ['smtp-proxy_9.9.9-1_amd64.deb'];
  assert.deepEqual(assets.missingAssets(next, ['*.deb']), []);
});

test('a pattern anchors at both ends', () => {
  assert.equal(assets.matches('foo.deb.txt', '*.deb'), false);
  assert.equal(assets.matches('notes-foo.deb', '*.deb'), true);
});

test('the rest of a pattern is literal, not a regular expression', () => {
  // `.` in `*.deb` must mean a dot. Without escaping, `*.deb` would match
  // `mydeb` and a release with no package at all would sail through.
  assert.equal(assets.matches('mydeb', '*.deb'), false);
  assert.equal(assets.matches('smtp-proxy+1.deb', '*+1.deb'), true);
});

test('several stars in one pattern all match', () => {
  assert.equal(assets.matches('smtp-proxy_1.2.3-1_amd64.deb', 'smtp-proxy_*_*.deb'), true);
});

test('missing patterns keep their declared order', () => {
  // The job message names them in the order the config declares, so the reader
  // can find the one that is wrong.
  assert.deepEqual(assets.missingAssets(['x'], ['a', 'b', 'c']), ['a', 'b', 'c']);
});

test('unfinishedAssets names every asset whose state is not uploaded', () => {
  assert.deepEqual(assets.unfinishedAssets([
    { name: 'a.deb', state: 'uploaded' },
    { name: 'b.deb', state: 'starter' },
    { name: 'c.deb', state: 'open' },
  ]), ['b.deb', 'c.deb']);
  assert.deepEqual(assets.unfinishedAssets(undefined), []);
});

test('absent arguments are not a crash', () => {
  // finalize passes whatever the API returned. An empty release must produce a
  // failing assertion, never a TypeError that reads like an infrastructure bug.
  assert.deepEqual(assets.missingAssets(undefined, ['*.deb']), ['*.deb']);
  assert.deepEqual(assets.missingAssets(RELEASE, undefined), []);
});

// The names GitHub gave these files on a draft release, 2026-11-07.
const PUBLISHED = {
  'a+b~c.txt': 'a+b.c.txt',
  'p~~q.txt': 'p.q.txt',
  'd..e.txt': 'd.e.txt',
  'f~.g.txt': 'f.g.txt',
  'h.~i.txt': 'h.i.txt',
  'j~-k.txt': 'j.-k.txt',
  'x_1.0-2+git3~rc1_amd64.deb': 'x_1.0-2+git3.rc1_amd64.deb',
};

test('publishedName gives the name GitHub lists the asset under', () => {
  for (const [built, listed] of Object.entries(PUBLISHED)) {
    assert.equal(assets.publishedName(built), listed, built);
  }
});

test('a pattern with ~ gives the same answer before the merge and after the tag (#137)', () => {
  // wg-wrangler v0.5.0: release-finish saw the built name, finalize the listed one.
  const pattern = 'wg-wrangler_*~bookworm_amd64.deb';
  assert.deepEqual(assets.missingAssets(['wg-wrangler_0.5.0~bookworm_amd64.deb'], [pattern]), []);
  assert.deepEqual(assets.missingAssets(['wg-wrangler_0.5.0.bookworm_amd64.deb'], [pattern]), []);
  // A pattern without the separator matches both forms too.
  for (const name of ['wg-wrangler_0.5.0~noble_amd64.deb', 'wg-wrangler_0.5.0.noble_amd64.deb']) {
    assert.equal(assets.matches(name, 'wg-wrangler_*noble_amd64.deb'), true, name);
  }
  // Still the whole name, and the other distribution does not count.
  assert.deepEqual(assets.missingAssets(['wg-wrangler_0.5.0.noble_amd64.deb'], [pattern]), [pattern]);
});

test('collidingAssets names built files GitHub would publish under one name', () => {
  assert.deepEqual(assets.collidingAssets(['x_1~rc1.deb', 'x_1.rc1.deb', 'y.tar.gz', 'a..b', 'a.b']),
    [['x_1~rc1.deb', 'x_1.rc1.deb'], ['a..b', 'a.b']]);
  assert.deepEqual(assets.collidingAssets(['x_1~rc1.deb', 'x_1~rc2.deb']), []);
  assert.deepEqual(assets.collidingAssets(undefined), []);
});
