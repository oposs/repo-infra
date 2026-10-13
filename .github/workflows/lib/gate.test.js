'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { dispatch, waitForRun, runGate } = require('./gate.js');

const clock = () => {
  let t = 0;
  return { now: () => t, sleep: async (ms) => { t += ms; } };
};

const api = ({ dispatched = { workflow_run_id: 42 }, runs = [] } = {}) => {
  const calls = [];
  let i = 0;
  return {
    calls,
    request: async (route, args) => { calls.push([route, args]); return { data: dispatched }; },
    rest: { actions: { getWorkflowRun: async (args) => {
      calls.push(['getWorkflowRun', args]);
      const run = runs[Math.min(i, runs.length - 1)];
      i += 1;
      if (run.error) throw new Error(run.error);
      return { data: run };
    } } },
  };
};

test('dispatch asks for the run details and returns the run id', async () => {
  const github = api();
  assert.equal(await dispatch(github, { owner: 'o', repo: 'r', workflow: 'gate-mtuspy.yml', ref: 'release/v2.0.0' }), 42);
  assert.deepEqual(github.calls[0], ['POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches',
    { owner: 'o', repo: 'r', workflow_id: 'gate-mtuspy.yml', ref: 'release/v2.0.0', return_run_details: true }]);
});

test('dispatch without a run id in the answer fails naming the workflow', async () => {
  const github = api({ dispatched: {} });
  await assert.rejects(dispatch(github, { owner: 'o', repo: 'r', workflow: 'gate-mtuspy.yml', ref: 'x' }),
    /gate-mtuspy\.yml was dispatched on x, but GitHub returned no run id/);
});

test('waitForRun polls until the run completes', async () => {
  const github = api({ runs: [{ status: 'queued' }, { status: 'in_progress' },
    { status: 'completed', conclusion: 'success', html_url: 'u' }] });
  const c = clock();
  const run = await waitForRun(github, { owner: 'o', repo: 'r', runId: 42, ...c, timeoutMs: 10000, intervalMs: 1000 });
  assert.deepEqual(run, { conclusion: 'success', html_url: 'u' });
  assert.equal(c.now(), 2000);
});

test('waitForRun gives up at the timeout', async () => {
  const github = api({ runs: [{ status: 'in_progress', html_url: 'u' }] });
  const c = clock();
  await assert.rejects(waitForRun(github, { owner: 'o', repo: 'r', runId: 42, ...c, timeoutMs: 5000, intervalMs: 1000 }),
    /run 42 did not finish within 5 s: u/);
});

test('waitForRun survives two failed polls and resolves on the completed run', async () => {
  const github = api({ runs: [{ error: 'HTTP 502' }, { error: 'HTTP 503' },
    { status: 'completed', conclusion: 'success', html_url: 'u' }] });
  const run = await waitForRun(github, { owner: 'o', repo: 'r', runId: 42, ...clock(), timeoutMs: 10000, intervalMs: 1000 });
  assert.deepEqual(run, { conclusion: 'success', html_url: 'u' });
});

test('a successful poll resets the count of failed polls', async () => {
  const github = api({ runs: [{ error: 'e' }, { error: 'e' }, { error: 'e' }, { status: 'queued' },
    { error: 'e' }, { error: 'e' }, { error: 'e' }, { status: 'completed', conclusion: 'success', html_url: 'u' }] });
  const run = await waitForRun(github, { owner: 'o', repo: 'r', runId: 42, ...clock(), timeoutMs: 100000, intervalMs: 1000 });
  assert.equal(run.conclusion, 'success');
});

test('waitForRun rejects on the fourth consecutive failed poll with the last message', async () => {
  const github = api({ runs: [{ error: 'HTTP 500' }, { error: 'HTTP 501' }, { error: 'HTTP 502' }, { error: 'HTTP 503' }] });
  await assert.rejects(waitForRun(github, { owner: 'o', repo: 'r', runId: 42, ...clock(), timeoutMs: 100000, intervalMs: 1000 }),
    /HTTP 503/);
  assert.equal(github.calls.length, 4);
});

test('runGate passes only on success', async () => {
  for (const [conclusion, ok] of [['success', true], ['failure', false], ['cancelled', false], ['timed_out', false]]) {
    const github = api({ runs: [{ status: 'completed', conclusion, html_url: 'u' }] });
    const out = await runGate(github, { owner: 'o', repo: 'r', workflow: 'gate-mtuspy.yml', ref: 'release/v2.0.0', ...clock(), timeoutMs: 1000, intervalMs: 10 });
    assert.equal(out.ok, ok, conclusion);
    assert.match(out.message, new RegExp(`gate-mtuspy\\.yml on release/v2\\.0\\.0: ${conclusion}, u`));
  }
});

test('runGate turns a timeout into a failed verdict, not a hang', async () => {
  const github = api({ runs: [{ status: 'queued', html_url: 'u' }] });
  const out = await runGate(github, { owner: 'o', repo: 'r', workflow: 'gate-mtuspy.yml', ref: 'r1', ...clock(), timeoutMs: 100, intervalMs: 10 });
  assert.equal(out.ok, false);
  assert.match(out.message, /did not finish within/);
});
