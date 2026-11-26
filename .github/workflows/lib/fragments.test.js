'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fragments = require('./fragments.js');
const cases = require('../../../tests/fixtures/changelog-fragments/cases.json');

const of = (kind) => cases.filter((c) => c.kind === kind);

test('noteDir reads the directory of the note or refuses it', () => {
  for (const c of of('note')) {
    if (!c.ok) {
      assert.throws(() => fragments.noteDir(c.input), /Changelog fragments directory/, c.input);
    } else {
      assert.equal(fragments.noteDir(c.input), c.value, c.input);
    }
  }
});

test('fragment names follow the pattern', () => {
  for (const c of of('name')) {
    const r = fragments.classifyPath('CHANGES.d', `CHANGES.d/fixed/${c.input}`);
    assert.equal(r.kind === 'fragment', c.ok, c.input);
  }
});

test('fragment bodies follow the entry rules', () => {
  for (const c of of('body')) {
    assert.equal(fragments.fragmentProblem(c.input) === null, c.ok, JSON.stringify(c.input));
    if (c.ok) {
      assert.equal(fragments.entries(c.input).join('|'), c.value, JSON.stringify(c.input));
    }
  }
});

test('classifyPath tells fragments from the rest', () => {
  const f = '20261126-0921-a3f9-time-band.md';
  const k = (p) => fragments.classifyPath('CHANGES.d', p);
  assert.deepEqual(k(`CHANGES.d/new/${f}`), { kind: 'fragment', section: 'new' });
  assert.equal(k('src/main.rs').kind, 'outside');
  assert.equal(k('CHANGES.dx/new/a.md').kind, 'outside');
  assert.equal(k('CHANGES.d/README.md').kind, 'root');
  assert.equal(k(`CHANGES.d/other/${f}`).kind, 'refused');
  assert.equal(k(`CHANGES.d/new/sub/${f}`).kind, 'refused');
  assert.match(k('CHANGES.d/new/bad.md').reason, /does not match/);
});

test('headerEnd stops at the first section heading', () => {
  assert.equal(fragments.headerEnd(['# C', '', '## 1.0.0 - 2026-01-01', 'x']), 2);
  assert.equal(fragments.headerEnd(['# C', 'x']), 2);
});

test('renderSection orders by file name across fragments', () => {
  const out = fragments.renderSection('1.3.0', '2026-08-17', [
    { section: 'fixed', name: '20261126-0921-a3f9-b.md', text: '- second\n' },
    { section: 'fixed', name: '20261125-0800-0000-a.md', text: '- first\n- first b\n' },
  ]);
  assert.deepEqual(out.slice(2), ['### Fixed', '', '- first', '- first b', '- second', '']);
});

test('renderSection leaves out empty sections and emits New, Changed, Fixed in order', () => {
  const out = fragments.renderSection('1.3.0', '2026-08-17', [
    { section: 'fixed', name: '20261126-0921-a3f9-x.md', text: '- a fix\n  more\n' },
    { section: 'new', name: '20261126-0921-a3f9-y.md', text: '- a thing\n' },
  ]);
  assert.deepEqual(out, [
    '## 1.3.0 - 2026-08-17', '',
    '### New', '', '- a thing', '',
    '### Fixed', '', '- a fix', '  more', '',
  ]);
});

test('renderSection ignores trailing newlines and CRLF of a fragment', () => {
  const render = (text) => fragments.renderSection('1.3.0', '2026-08-17', [
    { section: 'new', name: '20261126-0921-a3f9-x.md', text },
  ]);
  const plain = render('- a\n  b\n- c\n');
  assert.deepEqual(render('- a\n  b\n- c'), plain);
  assert.deepEqual(render('- a\n  b\n- c\n\n\n'), plain);
  assert.deepEqual(render('- a\r\n  b\r\n- c\r\n'), plain);
});

test('renderSection throws naming the path of an invalid fragment', () => {
  assert.throws(
    () => fragments.renderSection('1.3.0', '2026-08-17', [
      { section: 'new', name: '20261126-0921-a3f9-x.md', text: 'prose\n' },
    ]),
    /new\/20261126-0921-a3f9-x\.md/,
  );
});
