'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const changes = require('./changes.js');

const EMPTY = [
  '# Changelog',
  '',
  'Preamble that must survive.',
  '',
  '## [Unreleased]',
  '',
  '### New',
  '',
  '### Changed',
  '',
  '### Fixed',
  '',
].join('\n');

const FILLED = [
  '# Changelog',
  '',
  'Preamble that must survive.',
  '',
  '## [Unreleased]',
  '',
  '### New',
  '- a new thing',
  '',
  '### Changed',
  '',
  '### Fixed',
  '- a fixed thing',
  '',
  '## 1.2.3 - 2026-08-01',
  '### New',
  '- an older thing',
  '',
  '## 1.2.2 - 2026-07-01',
  '### Fixed',
  '- an even older thing',
  '',
].join('\n');

test('unreleasedBlock returns the block without its heading', () => {
  assert.match(changes.unreleasedBlock(FILLED), /a new thing/);
  assert.doesNotMatch(changes.unreleasedBlock(FILLED), /Unreleased/);
  assert.doesNotMatch(changes.unreleasedBlock(FILLED), /an older thing/);
});

test('unreleasedBlock fails loudly on the wrong heading style', () => {
  const wrong = EMPTY.replace('## [Unreleased]', '## Unreleased');
  assert.throws(() => changes.unreleasedBlock(wrong), /no '## \[Unreleased\]' heading/);
});

test('isEmpty is true for a skeleton and false once something is added', () => {
  assert.equal(changes.isEmpty(changes.unreleasedBlock(EMPTY)), true);
  assert.equal(changes.isEmpty(changes.unreleasedBlock(FILLED)), false);
});

test('roll refuses to release an empty Unreleased section', () => {
  assert.throws(() => changes.roll(EMPTY, '1.3.0', '2026-08-17'), /nothing to release/);
});

test('roll moves the content into a dated section', () => {
  const out = changes.roll(FILLED, '1.3.0', '2026-08-17');
  assert.match(out, /^## 1\.3\.0 - 2026-08-17$/m);
  assert.match(out, /## 1\.3\.0 - 2026-08-17\n\n### New\n\n- a new thing/);
});

test('roll drops subsections that had no entries', () => {
  const out = changes.roll(FILLED, '1.3.0', '2026-08-17');
  const section = changes.notesFor(out, '1.3.0');
  assert.match(section, /### New/);
  assert.match(section, /### Fixed/);
  assert.doesNotMatch(section, /### Changed/);
});

test('roll leaves a fresh empty Unreleased skeleton behind', () => {
  const out = changes.roll(FILLED, '1.3.0', '2026-08-17');
  assert.equal(changes.isEmpty(changes.unreleasedBlock(out)), true);
  assert.match(out, /## \[Unreleased\]\n\n### New\n\n### Changed\n\n### Fixed/);
});

test('roll preserves the preamble and every earlier release', () => {
  const out = changes.roll(FILLED, '1.3.0', '2026-08-17');
  assert.match(out, /Preamble that must survive/);
  assert.match(out, /## 1\.2\.3 - 2026-08-01/);
  assert.match(out, /## 1\.2\.2 - 2026-07-01/);
});

test('roll merges subsections that share a heading, in order', () => {
  // Two branches that each add a skeleton merge into one Unreleased block
  // with every heading twice. The release notes must list each heading once.
  const twice = [
    '## [Unreleased]',
    '',
    '### New',
    '- newer feature',
    '',
    '### Fixed',
    '- newer fix',
    '',
    '### New',
    '- older feature',
    '',
    '### Changed',
    '- a change',
    '',
    '### Fixed',
    '- older fix',
    '',
    '## 1.2.3 - 2026-08-01',
    '### Fixed',
    '- released',
    '',
  ].join('\n');
  const out = changes.roll(twice, '1.3.0', '2026-08-17');
  const released = out.split('## 1.3.0 - 2026-08-17')[1].split('## 1.2.3')[0];
  assert.equal(released.match(/### New/g).length, 1);
  assert.equal(released.match(/### Fixed/g).length, 1);
  assert.match(released, /### New\n\n- newer feature\n- older feature\n/);
  assert.match(released, /### Fixed\n\n- newer fix\n- older fix\n/);
  assert.ok(released.indexOf('### New') < released.indexOf('### Fixed'));
});

test('roll writes the released section in the layout of the skeleton (#163)', () => {
  // oposs/thinfloe#12 (v4.3.0): the rolled section lost the blank line after
  // "## 4.3.0 - ..." and after each "### ...", while the skeleton above it and
  // the sections below it had them.
  const written = [
    '## [Unreleased]',
    '',
    '### New',
    '',
    '- a new thing',
    '',
    '### Changed',
    '',
    '### Fixed',
    '',
    '- a fixed thing',
    '- another fix',
    '',
    '## 1.2.3 - 2026-08-01',
    '',
    '### New',
    '',
    '- an older thing',
    '',
  ].join('\n');
  const out = changes.roll(written, '1.3.0', '2026-08-17');
  assert.equal(out, [
    '## [Unreleased]',
    '',
    '### New',
    '',
    '### Changed',
    '',
    '### Fixed',
    '',
    '## 1.3.0 - 2026-08-17',
    '',
    '### New',
    '',
    '- a new thing',
    '',
    '### Fixed',
    '',
    '- a fixed thing',
    '- another fix',
    '',
    '## 1.2.3 - 2026-08-01',
    '',
    '### New',
    '',
    '- an older thing',
    '',
  ].join('\n'));
});

test('rolling twice is possible: the result is still parseable', () => {
  const once = changes.roll(FILLED, '1.3.0', '2026-08-17');
  assert.throws(() => changes.roll(once, '1.4.0', '2026-08-18'), /nothing to release/);
});

test('latestRelease returns the topmost version', () => {
  assert.deepEqual(changes.latestRelease(FILLED), { version: '1.2.3', date: '2026-08-01' });
});

test('latestRelease is null before the first release', () => {
  assert.equal(changes.latestRelease(EMPTY), null);
});

test('notesFor returns only that version', () => {
  const notes = changes.notesFor(FILLED, '1.2.3');
  assert.match(notes, /an older thing/);
  assert.doesNotMatch(notes, /an even older thing/);
  assert.doesNotMatch(notes, /## 1\.2\.2/);
});

test('notesFor fails loudly for a version that is not there', () => {
  assert.throws(() => changes.notesFor(FILLED, '9.9.9'), /no section for 9\.9\.9/);
});

const BARE = '# Changelog\n\n## Unreleased\n\n- an entry\n';
const ADDS_NOTHING = /adds nothing under '## \[Unreleased\]'/;

test('gateVerdict', async (t) => {
  const cases = [
    ['both sides equal', EMPTY, EMPTY, false, ADDS_NOTHING],
    ['head adds an entry', EMPTY, FILLED, true, /was updated/],
    ['base has the bare heading, head is converted', BARE, FILLED, true, /was updated/],
    ['base has the bare heading, head is empty', BARE, EMPTY, false, ADDS_NOTHING],
    ['base file is missing, head has an entry', null, FILLED, true, /was updated/],
    ['base file is missing, head is empty', null, EMPTY, false, ADDS_NOTHING],
    ['head has the bare heading', EMPTY, BARE, false, /no '## \[Unreleased\]' heading/],
    ['head file is missing', EMPTY, null, false, /no '## \[Unreleased\]' heading/],
  ];
  for (const [name, base, head, ok, message] of cases) {
    await t.test(name, () => {
      const verdict = changes.gateVerdict(base, head);
      assert.equal(verdict.ok, ok);
      assert.match(verdict.message, message);
    });
  }
});

const FRAG_HEAD = [
  '# Changelog',
  '',
  'Changelog fragments: `CHANGES.d`',
  '',
].join('\n');
const FRAG_REST = ['## 1.2.3 - 2026-08-01', '', '### New', '', '- older', ''].join('\n');
const FRAG_FILE = FRAG_HEAD + FRAG_REST;

test('roll in fragment mode inserts the section after the header and keeps it byte for byte', () => {
  const list = [
    { section: 'fixed', name: '20261126-1200-abcd-b.md', text: '- fixed it\n' },
    { section: 'new', name: '20261126-1200-abcd-a.md', text: '- added it\n' },
  ];
  const out = changes.roll(FRAG_FILE, '1.3.0', '2026-11-26', list);
  assert.equal(out, FRAG_HEAD
    + '## 1.3.0 - 2026-11-26\n\n### New\n\n- added it\n\n### Fixed\n\n- fixed it\n\n'
    + FRAG_REST);
});

test('roll in fragment mode throws "no changelog fragments in CHANGES.d - nothing to release" for an empty list', () => {
  assert.throws(
    () => changes.roll(FRAG_FILE, '1.3.0', '2026-11-26', []),
    /no changelog fragments in CHANGES\.d - nothing to release/,
  );
});

test('roll refuses a file with both the note and [Unreleased]', () => {
  assert.throws(
    () => changes.roll(FRAG_HEAD + EMPTY, '1.3.0', '2026-11-26', []),
    /the switch to fragments is not finished/,
  );
});

test('roll in classic mode ignores the fragments argument', () => {
  const list = [{ section: 'new', name: '20261126-1200-abcd-a.md', text: '- ignored\n' }];
  assert.equal(
    changes.roll(FILLED, '1.3.0', '2026-08-17', list),
    changes.roll(FILLED, '1.3.0', '2026-08-17'),
  );
});
