'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { createGateBranch, dispatch, waitForRun, runGate } = require('./gate.js');

const clock = () => {
  let t = 0;
  return { now: () => t, sleep: async (ms) => { t += ms; } };
};

const failure = (message, status) => Object.assign(new Error(message), { status });

const api = ({
  dispatched = { workflow_run_id: 42 }, runs = [], refExists = false, deleteError = null,
} = {}) => {
  const calls = [];
  let i = 0;
  const record = (name, result) => async (args) => { calls.push([name, args]); return result(args); };
  return {
    calls,
    request: async (route, args) => { calls.push([route, args]); return { data: dispatched }; },
    rest: {
      actions: { getWorkflowRun: async (args) => {
        calls.push(['getWorkflowRun', args]);
        const run = runs[Math.min(i, runs.length - 1)];
        i += 1;
        if (run.error) throw new Error(run.error);
        return { data: run };
      } },
      git: {
        getCommit: record('getCommit', () => ({ data: { sha: 'head', tree: { sha: 'tree' } } })),
        createCommit: record('createCommit', () => ({ data: { sha: 'gate' } })),
        createRef: record('createRef', () => {
          if (refExists) throw failure('Reference already exists', 422);
          return { data: {} };
        }),
        updateRef: record('updateRef', () => ({ data: {} })),
        deleteRef: record('deleteRef', () => {
          if (deleteError) throw failure(deleteError, 500);
          return { data: {} };
        }),
      },
    },
  };
};

const named = (github, name) => github.calls.filter(([n]) => n === name).map(([, args]) => args);

const gateArgs = (extra = {}) => ({
  owner: 'o', repo: 'r', workflow: 'gate-mtuspy.yml', head: 'head', version: '2.0.1',
  ...clock(), timeoutMs: 1000, intervalMs: 10, warn: () => {}, ...extra,
});

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

test('the gate commit has the release head as parent and its tree', async () => {
  const github = api();
  assert.equal(await createGateBranch(github, { owner: 'o', repo: 'r', head: 'head', version: '2.0.1' }),
    'gate/v2.0.1');
  assert.deepEqual(named(github, 'getCommit'), [{ owner: 'o', repo: 'r', commit_sha: 'head' }]);
  assert.deepEqual(named(github, 'createCommit'),
    [{ owner: 'o', repo: 'r', message: 'Gate for v2.0.1', tree: 'tree', parents: ['head'] }]);
  assert.deepEqual(named(github, 'createRef'),
    [{ owner: 'o', repo: 'r', ref: 'refs/heads/gate/v2.0.1', sha: 'gate' }]);
  assert.deepEqual(named(github, 'updateRef'), []);
});

test('a gate branch left from an earlier attempt is moved with force', async () => {
  const github = api({ refExists: true });
  await createGateBranch(github, { owner: 'o', repo: 'r', head: 'head', version: '2.0.1' });
  assert.deepEqual(named(github, 'updateRef'),
    [{ owner: 'o', repo: 'r', ref: 'heads/gate/v2.0.1', sha: 'gate', force: true }]);
});

test('createGateBranch passes on any other failure to create the ref', async () => {
  const github = api();
  github.rest.git.createRef = async () => { throw failure('Forbidden', 403); };
  await assert.rejects(createGateBranch(github, { owner: 'o', repo: 'r', head: 'head', version: '2.0.1' }),
    /Forbidden/);
});

test('runGate dispatches on the gate branch, not on the release branch', async () => {
  const github = api({ runs: [{ status: 'completed', conclusion: 'success', html_url: 'u' }] });
  await runGate(github, gateArgs());
  const [, args] = github.calls.find(([route]) => route.includes('/dispatches'));
  assert.equal(args.ref, 'gate/v2.0.1');
  const order = github.calls.map(([name]) => name);
  assert.ok(order.indexOf('createRef') < order.findIndex((n) => n.includes('/dispatches')));
});

test('runGate passes only on success', async () => {
  for (const [conclusion, ok] of [['success', true], ['failure', false], ['cancelled', false], ['timed_out', false]]) {
    const github = api({ runs: [{ status: 'completed', conclusion, html_url: 'u' }] });
    const out = await runGate(github, gateArgs());
    assert.equal(out.ok, ok, conclusion);
    assert.match(out.message, new RegExp(`gate-mtuspy\\.yml on gate/v2\\.0\\.1: ${conclusion}, u`));
  }
});

test('runGate turns a timeout into a failed verdict, not a hang', async () => {
  const github = api({ runs: [{ status: 'queued', html_url: 'u' }] });
  const out = await runGate(github, gateArgs({ timeoutMs: 100 }));
  assert.equal(out.ok, false);
  assert.match(out.message, /did not finish within/);
});

test('runGate deletes the gate branch after success, failure and timeout', async () => {
  for (const [runs, ok] of [
    [[{ status: 'completed', conclusion: 'success', html_url: 'u' }], true],
    [[{ status: 'completed', conclusion: 'failure', html_url: 'u' }], false],
    [[{ status: 'queued', html_url: 'u' }], false],
  ]) {
    const github = api({ runs });
    const out = await runGate(github, gateArgs());
    assert.equal(out.ok, ok);
    assert.deepEqual(named(github, 'deleteRef'), [{ owner: 'o', repo: 'r', ref: 'heads/gate/v2.0.1' }]);
  }
});

test('runGate deletes the gate branch when the dispatch fails', async () => {
  const github = api({ dispatched: {} });
  const out = await runGate(github, gateArgs());
  assert.equal(out.ok, false);
  assert.equal(named(github, 'deleteRef').length, 1);
});

test('a failed deletion of the gate branch only warns', async () => {
  const warnings = [];
  const github = api({ runs: [{ status: 'completed', conclusion: 'success', html_url: 'u' }],
    deleteError: 'HTTP 500' });
  const out = await runGate(github, gateArgs({ warn: (m) => warnings.push(m) }));
  assert.equal(out.ok, true);
  assert.deepEqual(warnings, ['gate/v2.0.1 could not be deleted: HTTP 500']);
});

test('runGate fails without a dispatch when the gate commit cannot be made', async () => {
  const github = api();
  github.rest.git.createCommit = async () => { throw failure('Forbidden', 403); };
  const out = await runGate(github, gateArgs());
  assert.deepEqual(out, { ok: false, message: 'Forbidden' });
  assert.ok(!github.calls.some(([route]) => route.includes('/dispatches')));
  assert.deepEqual(named(github, 'deleteRef'), []);
});
