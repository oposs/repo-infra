'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  publishDecision, recordHeadWarning, validateBuildRecord, majorTag, moveMajorTag,
} = require('./publish.js');

const TAG = 'v1.2.0';
const HEAD = 'a'.repeat(40);
let nextId = 1;
const rel = (draft, record) => ({
  id: nextId++, tag_name: TAG, draft,
  assets: record ? [{ id: 900, name: 'release-build.json' }, { id: 901, name: 'x.deb' }]
    : [{ id: 901, name: 'x.deb' }],
});
const decide = (tagCommit, releases) => publishDecision({ tag: TAG, tagCommit, releases });

// The whole state table of spec D26 "Publishing": tag present/absent x
// published/draft/none/several x build record present/absent.

test('case 1: tag, one published release, no record: done', () => {
  assert.deepEqual(decide(HEAD, [rel(false, false)]), { action: 'done' });
});

test('case 2: tag and one draft: resume at the tag commit (record or not)', () => {
  for (const record of [true, false]) {
    const d = rel(true, record);
    const want = { action: 'resume', releaseId: d.id, head: HEAD };
    if (record) want.recordAssetId = 900;
    assert.deepEqual(decide(HEAD, [d]), want);
  }
});

test('case 3: no tag and one draft with a record: create', () => {
  const d = rel(true, true);
  assert.deepEqual(decide(null, [d]), { action: 'create', releaseId: d.id, recordAssetId: 900 });
});

test('case 3 refused: no tag and one draft without a record', () => {
  const out = decide(null, [rel(true, false)]);
  assert.equal(out.action, 'fail');
  assert.match(out.message, /release-build\.json/);
});

test('case 3 refused: no tag and no draft names the count', () => {
  const out = decide(null, []);
  assert.equal(out.action, 'fail');
  assert.match(out.message, /found 0/);
});

test('case 3 refused: no tag and two drafts names the count', () => {
  const out = decide(null, [rel(true, true), rel(true, true)]);
  assert.equal(out.action, 'fail');
  assert.match(out.message, /found 2/);
});

test('case 4: tag but no release at all', () => {
  const out = decide(HEAD, []);
  assert.equal(out.action, 'fail');
  assert.match(out.message, /no release/);
});

test('case 4: a published release that still carries the record was published by hand', () => {
  for (const tagCommit of [HEAD, null]) {
    const out = decide(tagCommit, [rel(false, true)]);
    assert.equal(out.action, 'fail');
    assert.match(out.message, /by hand/);
  }
});

test('case 4: tag and several matching releases', () => {
  const out = decide(HEAD, [rel(true, false), rel(true, true)]);
  assert.equal(out.action, 'fail');
  assert.match(out.message, /2 drafts/);
});

test('case 4: tag, a published release and a draft', () => {
  assert.equal(decide(HEAD, [rel(false, false), rel(true, true)]).action, 'fail');
});

test('case 4: no tag but a published release', () => {
  assert.equal(decide(null, [rel(false, false)]).action, 'fail');
});

test('a valid record passes', () => {
  assert.equal(validateBuildRecord({ head: HEAD }, '1.2.0', { version: '1.2.0' }), null);
});

test('a record without a commit sha is refused', () => {
  assert.match(validateBuildRecord({}, '1.2.0', { version: '1.2.0' }), /head/);
  assert.match(validateBuildRecord({ head: 'main' }, '1.2.0', { version: '1.2.0' }), /head/);
});

test('a head whose CHANGES.md is at another version is refused', () => {
  assert.match(validateBuildRecord({ head: HEAD }, '1.2.0', { version: '1.1.0' }), /1\.1\.0/);
  assert.match(validateBuildRecord({ head: HEAD }, '1.2.0', null), /no released version/);
});

test('recovery hints name ways out that prepare does not refuse', () => {
  const noRelease = decide(HEAD, []).message;
  assert.match(noRelease, /carries every release_assets file/);
  const noRecord = decide(null, [rel(true, false)]).message;
  assert.match(noRecord, /Push v1\.2\.0 at the built commit/);
  assert.match(noRecord, /back under \[Unreleased\]/);
  assert.doesNotMatch(noRecord, /Dispatch/);
});

test('recordHeadWarning: silent when the tag is at the built commit, else names both', () => {
  assert.equal(recordHeadWarning(TAG, HEAD, HEAD), null);
  const other = 'b'.repeat(40);
  const w = recordHeadWarning(TAG, HEAD, other);
  assert.ok(w.includes(HEAD) && w.includes(other));
});

test('majorTag: the major of a version', () => {
  assert.equal(majorTag('2.0.1'), 'v2');
  assert.equal(majorTag('10.3.0'), 'v10');
});

test('moveMajorTag updates the major tag to a new annotated tag', async () => {
  const calls = [];
  const github = { rest: { git: {
    createTag: async (a) => { calls.push(['createTag', a]); return { data: { sha: 't1' } }; },
    updateRef: async (a) => { calls.push(['updateRef', a]); return { data: {} }; },
    createRef: async () => { throw new Error('not expected'); },
  } } };
  const notice = await moveMajorTag(github, { owner: 'o', repo: 'r', version: '2.0.1', tag: 'v2.0.1', sha: 'c1' });
  assert.equal(notice, 'Moved v2 to v2.0.1.');
  assert.deepEqual(calls[0], ['createTag', { owner: 'o', repo: 'r', tag: 'v2',
    message: 'Update v2 to v2.0.1', object: 'c1', type: 'commit' }]);
  assert.deepEqual(calls[1], ['updateRef', { owner: 'o', repo: 'r', ref: 'tags/v2', sha: 't1', force: true }]);
});

test('moveMajorTag creates the major tag the first time', async () => {
  const calls = [];
  const github = { rest: { git: {
    createTag: async () => ({ data: { sha: 't1' } }),
    updateRef: async () => { const e = new Error('Reference does not exist'); e.status = 422; throw e; },
    createRef: async (a) => { calls.push(a); return { data: {} }; },
  } } };
  await moveMajorTag(github, { owner: 'o', repo: 'r', version: '2.0.0', tag: 'v2.0.0', sha: 'c1' });
  assert.deepEqual(calls, [{ owner: 'o', repo: 'r', ref: 'refs/tags/v2', sha: 't1' }]);
});

test('moveMajorTag names the ruleset when the move is refused', async () => {
  const github = { rest: { git: {
    createTag: async () => ({ data: { sha: 't1' } }),
    updateRef: async () => { const e = new Error('Repository rule violations found'); e.status = 422; throw e; },
    createRef: async () => { const e = new Error('Reference already exists'); e.status = 422; throw e; },
  } } };
  await assert.rejects(
    moveMajorTag(github, { owner: 'o', repo: 'r', version: '2.0.1', tag: 'v2.0.1', sha: 'c1' }),
    /v2 could not be moved to v2\.0\.1: Repository rule violations found\. A tag ruleset on v\* lets only its bypass list move it; pass app-client-id and app-private-key/);
});

test('moveMajorTag names the secrets when the ruleset answers 403', async () => {
  const refuse = async () => { const e = new Error('Forbidden by rule'); e.status = 403; throw e; };
  const github = { rest: { git: {
    createTag: async () => ({ data: { sha: 't1' } }), updateRef: refuse, createRef: refuse,
  } } };
  await assert.rejects(
    moveMajorTag(github, { owner: 'o', repo: 'r', version: '2.0.1', tag: 'v2.0.1', sha: 'c1' }),
    /v2 could not be moved to v2\.0\.1: Forbidden by rule\..*pass app-client-id and app-private-key/);
});
