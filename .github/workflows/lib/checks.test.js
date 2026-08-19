'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const checks = require('./checks.js');

const PARAMS = { owner: 'oposs', repo: 'repo-infra', ref: 'abc123' };

// A fake Octokit whose paginate returns successive fixtures, one per call.
function fakeGithub(pages) {
  let call = 0;
  return {
    rest: { checks: { listForRef: 'listForRef' } },
    paginate: async () => {
      const page = pages[Math.min(call, pages.length - 1)];
      call += 1;
      return page;
    },
    calls: () => call,
  };
}

const ok = (name) => ({ name, status: 'completed', conclusion: 'success' });
const bad = (name) => ({ name, status: 'completed', conclusion: 'failure' });
const running = (name) => ({ name, status: 'in_progress', conclusion: null });
const skipped = (name) => ({ name, status: 'completed', conclusion: 'skipped' });

test('all checks green is ok', async () => {
  const state = await checks.checkState(fakeGithub([[ok('CI'), ok('Changelog')]]), PARAMS);
  assert.equal(state.ok, true);
  assert.equal(state.total, 2);
});

test('a failure is not ok and is named', async () => {
  const state = await checks.checkState(fakeGithub([[ok('CI'), bad('Changelog')]]), PARAMS);
  assert.equal(state.ok, false);
  assert.deepEqual(state.failed.map((c) => c.name), ['Changelog']);
});

test('a running check is not ok and is named', async () => {
  const state = await checks.checkState(fakeGithub([[ok('CI'), running('Slow')]]), PARAMS);
  assert.equal(state.ok, false);
  assert.deepEqual(state.pending.map((c) => c.name), ['Slow']);
});

test('a skipped check does not count as a failure', async () => {
  const state = await checks.checkState(fakeGithub([[ok('CI'), skipped('Optional')]]), PARAMS);
  assert.equal(state.ok, true);
});

test('no checks at all is not ok', async () => {
  // The dangerous case: releasing a commit nothing ever tested.
  const state = await checks.checkState(fakeGithub([[]]), PARAMS);
  assert.equal(state.ok, false);
  assert.equal(state.total, 0);
});

test('waitForChecks returns as soon as something fails', async () => {
  const github = fakeGithub([[bad('CI')]]);
  const state = await checks.waitForChecks(github, PARAMS, {
    sleep: async () => { throw new Error('should not have slept'); },
  });
  assert.equal(state.ok, false);
  assert.equal(github.calls(), 1);
});

test('waitForChecks polls until pending clears', async () => {
  const github = fakeGithub([
    [running('CI')],
    [running('CI')],
    [ok('CI')],
  ]);
  let slept = 0;
  const state = await checks.waitForChecks(github, PARAMS, {
    sleep: async () => { slept += 1; },
  });
  assert.equal(state.ok, true);
  assert.equal(slept, 2);
});

test('waitForChecks gives up after the timeout', async () => {
  const github = fakeGithub([[running('CI')]]);
  let clock = 0;
  const state = await checks.waitForChecks(github, PARAMS, {
    intervalMs: 1000,
    timeoutMs: 3000,
    now: () => clock,
    sleep: async (ms) => { clock += ms; },
  });
  assert.equal(state.timedOut, true);
  assert.equal(state.ok, false);
});
