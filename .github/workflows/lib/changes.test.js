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

// Gate inputs in fragment mode (D40). MB is the merge base; a pull request
// adds files under CHANGES.d and leaves CHANGES.md alone.
const NOTE_HEAD = '# Changelog\n\nChangelog fragments: `CHANGES.d/`. Pull requests do not edit this file.\n\n';
const REL_2 = '## 1.3.0 - 2026-09-01\n\n### Fixed\n\n- fix one\n- fix two\n  more of fix two\n\n';
const REL_1 = '## 1.2.3 - 2026-08-01\n\n### New\n\n- older\n';
const MB = NOTE_HEAD + REL_2 + REL_1;
const FRAG = 'CHANGES.d/fixed/20261126-0921-a3f9-time-band.md';
const FRAG_B = 'CHANGES.d/new/20261126-0922-b0b0-other.md';
const CLASSIC_BASE = '# Changelog\n\n## [Unreleased]\n\n### New\n\n- one\n- two\n\n' + REL_2 + REL_1;

function verdict(over) {
  return changes.changelogVerdict({
    baseText: MB,
    mergeBaseText: MB,
    headText: MB,
    files: [],
    fragmentTexts: {},
    untaggedTop: null,
    remainingFragments: 0,
    ...over,
  });
}
const added = (filename) => ({ filename, status: 'added' });

test('changelogVerdict', async (t) => {
  await t.test('a valid added fragment passes', () => {
    const v = verdict({ files: [added(FRAG)], fragmentTexts: { [FRAG]: '- a fix\n' } });
    assert.equal(v.ok, true, v.message);
  });

  await t.test('an invalid fragment fails naming the path and the reason', () => {
    const v = verdict({ files: [added(FRAG)], fragmentTexts: { [FRAG]: '## heading\n- a fix\n' } });
    assert.equal(v.ok, false);
    assert.ok(v.message.includes(FRAG), v.message);
    assert.match(v.message, /a line starts with '#'/);
  });

  await t.test('a refused path under the directory fails', () => {
    const path = 'CHANGES.d/fixed/bad.md';
    const v = verdict({ files: [added(path), added(FRAG)], fragmentTexts: { [path]: '- x\n', [FRAG]: '- x\n' } });
    assert.equal(v.ok, false);
    assert.ok(v.message.includes(path), v.message);
    assert.match(v.message, /does not match/);
  });

  await t.test('a file directly in the directory is allowed but is no fragment', () => {
    const v = verdict({ files: [{ filename: 'CHANGES.d/README.md', status: 'modified' }] });
    assert.equal(v.ok, false);
    assert.match(v.message, /adds no changelog fragment/);
  });

  await t.test('a header edit fails', () => {
    const head = NOTE_HEAD.replace('Pull requests', 'Contributions') + REL_2 + REL_1;
    const v = verdict({ headText: head, files: [added(FRAG)], fragmentTexts: { [FRAG]: '- x\n' } });
    assert.equal(v.ok, false);
    assert.match(v.message, /header/);
  });

  await t.test('an added ## section fails', () => {
    const head = NOTE_HEAD + '## 1.4.0 - 2026-11-26\n\n### New\n\n- sneaked in\n\n' + REL_2 + REL_1;
    const v = verdict({ headText: head, files: [added(FRAG)], fragmentTexts: { [FRAG]: '- x\n' } });
    assert.equal(v.ok, false);
    assert.match(v.message, /## 1\.4\.0 - 2026-11-26/);
  });

  await t.test('an edit inside a released section passes without a fragment', () => {
    const head = MB.replace('- fix one', '- fix one (#12)');
    const v = verdict({ headText: head });
    assert.equal(v.ok, true, v.message);
  });

  await t.test('a deleted fragment fails', () => {
    const v = verdict({
      files: [{ filename: FRAG, status: 'removed' }, added(FRAG_B)],
      fragmentTexts: { [FRAG_B]: '- x\n' },
    });
    assert.equal(v.ok, false);
    assert.ok(v.message.includes(`removes ${FRAG}, which another pull request added`), v.message);
  });

  await t.test('a fragment renamed out of the directory counts as deleted', () => {
    const v = verdict({
      files: [{ filename: 'notes.md', previous_filename: FRAG, status: 'renamed' }, added(FRAG_B)],
      fragmentTexts: { [FRAG_B]: '- x\n' },
    });
    assert.equal(v.ok, false);
    assert.ok(v.message.includes(`removes ${FRAG}, which another pull request added`), v.message);
  });

  await t.test('a rename between section directories passes', () => {
    const to = 'CHANGES.d/changed/20261126-0921-a3f9-time-band.md';
    const v = verdict({
      files: [{ filename: to, previous_filename: FRAG, status: 'renamed' }],
      fragmentTexts: { [to]: '- moved\n' },
    });
    assert.equal(v.ok, true, v.message);
  });

  await t.test('nothing changed fails', () => {
    const v = verdict({ files: [{ filename: 'src/main.rs', status: 'modified' }] });
    assert.equal(v.ok, false);
    assert.ok(v.message.includes(
      "This pull request adds no changelog fragment. Add one under `CHANGES.d/<section>/`, or label the pull request 'no-changelog'",
    ), v.message);
  });

  await t.test('a refused directory at head fails without throwing', () => {
    const v = verdict({ headText: MB.replace('`CHANGES.d/`', '`../x/`') });
    assert.equal(v.ok, false);
    assert.match(v.message, /^CHANGES\.md at head: Changelog fragments directory '\.\.\/x' contains '\.\.'/);
  });

  await t.test('a refused directory at the merge base names the no-changelog repair', () => {
    const broken = MB.replace('`CHANGES.d/`', '`../x/`');
    const v = verdict({ mergeBaseText: broken });
    assert.equal(v.ok, false);
    assert.match(v.message, /^CHANGES\.md at the merge base: Changelog fragments directory '\.\.\/x'/);
    assert.match(v.message, /labelled 'no-changelog' can repair the note/);
  });

  await t.test('modifying an existing fragment passes', () => {
    const v = verdict({ files: [{ filename: FRAG, status: 'modified' }], fragmentTexts: { [FRAG]: '- reworded\n' } });
    assert.equal(v.ok, true, v.message);
    assert.match(v.message, /^1 changelog fragment under CHANGES\.d\//);
  });

  const abandoned = NOTE_HEAD + REL_1;
  const restore = (text) => ({ files: [added(FRAG)], fragmentTexts: { [FRAG]: text } });

  await t.test('abandon: removing the untagged top section passes when its entries come back', () => {
    const v = verdict({ headText: abandoned, untaggedTop: '1.3.0', ...restore('- fix one\n- fix two\n  more\n') });
    assert.equal(v.ok, true, v.message);
  });

  await t.test('abandon: removing a tagged top section fails', () => {
    const v = verdict({ headText: abandoned, untaggedTop: null, ...restore('- fix one\n- fix two\n') });
    assert.equal(v.ok, false);
    assert.match(v.message, /## 1\.3\.0 - 2026-09-01/);
  });

  await t.test('abandon: untaggedTop naming another version fails as tagged', () => {
    const v = verdict({ headText: abandoned, untaggedTop: '1.2.3', ...restore('- fix one\n- fix two\n') });
    assert.equal(v.ok, false);
    assert.match(v.message, /v1\.3\.0 is tagged/);
  });

  await t.test('abandon: one entry is counted in the singular', () => {
    const one = NOTE_HEAD + '## 1.3.0 - 2026-09-01\n\n### Fixed\n\n- fix one\n\n' + REL_1;
    const v = verdict({ mergeBaseText: one, headText: abandoned, untaggedTop: '1.3.0' });
    assert.equal(v.ok, false);
    assert.match(v.message, /held 1 entry, but this pull request restores 0/);
  });

  await t.test('abandon: too few restored entries fail', () => {
    const v = verdict({ headText: abandoned, untaggedTop: '1.3.0', ...restore('- fix one and two\n') });
    assert.equal(v.ok, false);
    assert.match(v.message, /2 entries/);
    assert.match(v.message, /restores 1/);
  });

  const switched = (over) => verdict({ baseText: CLASSIC_BASE, mergeBaseText: CLASSIC_BASE, headText: MB, ...over });

  await t.test('switch: the note at head only passes with no [Unreleased] and enough entries', () => {
    const v = switched({ files: [added(FRAG)], fragmentTexts: { [FRAG]: '- one\n- two\n' } });
    assert.equal(v.ok, true, v.message);
  });

  await t.test('switch: [Unreleased] left at head fails', () => {
    const head = NOTE_HEAD + '## [Unreleased]\n\n' + REL_2 + REL_1;
    const v = switched({ headText: head, files: [added(FRAG)], fragmentTexts: { [FRAG]: '- one\n- two\n' } });
    assert.equal(v.ok, false);
    assert.match(v.message, /the switch to fragments is not finished/);
  });

  await t.test('switch: fewer entries than [Unreleased] had fail', () => {
    const v = switched({ files: [added(FRAG)], fragmentTexts: { [FRAG]: '- one\n' } });
    assert.equal(v.ok, false);
    assert.match(v.message, /2 entries/);
  });

  await t.test('switch: an edit to a released section fails', () => {
    const v = switched({
      headText: MB.replace('- older', '- older, reworded'),
      files: [added(FRAG)],
      fragmentTexts: { [FRAG]: '- one\n- two\n' },
    });
    assert.equal(v.ok, false);
    assert.match(v.message, /released sections/);
  });

  await t.test('switch back: fails while fragments remain', () => {
    const v = verdict({ baseText: MB, headText: CLASSIC_BASE, remainingFragments: 2 });
    assert.equal(v.ok, false);
    assert.match(v.message, /2 fragment files remain under CHANGES\.d\//);
    const one = verdict({ baseText: MB, headText: CLASSIC_BASE, remainingFragments: 1 });
    assert.match(one.message, /1 fragment file remains under CHANGES\.d\//);
  });

  await t.test('switch back: classic rules once no fragment remains', () => {
    const v = verdict({ baseText: MB, headText: CLASSIC_BASE, remainingFragments: 0 });
    assert.deepEqual(v, changes.gateVerdict(MB, CLASSIC_BASE));
  });

  await t.test('classic mode returns exactly what gateVerdict returns', () => {
    for (const [base, head] of [[EMPTY, FILLED], [EMPTY, EMPTY], [null, FILLED], [EMPTY, null]]) {
      const v = verdict({ baseText: base, mergeBaseText: base, headText: head });
      assert.deepEqual(v, changes.gateVerdict(base, head));
    }
  });
});

test('roll in fragment mode keeps CRLF on every line', () => {
  const crlf = FRAG_FILE.replace(/\n/g, '\r\n');
  const out = changes.roll(crlf, '1.3.0', '2026-11-26', [
    { section: 'new', name: '20261126-1200-abcd-a.md', text: '- added it\r\n  more\r\n' },
  ]);
  assert.ok(out.endsWith('\r\n'));
  for (const line of out.split('\n').slice(0, -1)) {
    assert.ok(line.endsWith('\r'), JSON.stringify(line));
  }
});

test('roll in fragment mode puts the heading on its own line after a header without a trailing newline', () => {
  const header = '# Changelog\n\nChangelog fragments: `CHANGES.d`';
  const out = changes.roll(header, '1.3.0', '2026-11-26', [
    { section: 'new', name: '20261126-1200-abcd-a.md', text: '- added it\n' },
  ]);
  assert.ok(out.split('\n').includes('## 1.3.0 - 2026-11-26'), out);
  assert.ok(out.startsWith(header + '\n'), out);
});
