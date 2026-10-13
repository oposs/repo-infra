'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { BOT } = require('./release.js');
const { deleteParkedRuns } = require('./unpark.js');

const clock = () => {
  let t = 0;
  return { now: () => t, sleep: async (ms) => { t += ms; } };
};

const parked = (id, sha = 'h') => ({
  id, event: 'pull_request', head_branch: 'release/v1.2.0', head_sha: sha,
  status: 'completed', conclusion: 'action_required',
  head_repository: { full_name: 'o/r' }, actor: { login: BOT },
});

// polls[i] is what the i-th listing answers (an array of runs, or an Error);
// the last entry repeats. failDelete names run ids whose deletion throws.
const api = ({ polls, failDelete = [] }) => {
  const calls = { listed: [], deleted: [] };
  let i = -1;
  let current = [];
  return {
    calls,
    rest: { actions: {
      listWorkflowRunsForRepo: 'list',
      listJobsForWorkflowRun: async () => ({ data: { total_count: 0 } }),
      deleteWorkflowRun: async ({ run_id: id }) => {
        if (failDelete.includes(id)) throw new Error(`HTTP 500 for ${id}`);
        calls.deleted.push(id);
      },
    } },
    // fetchParkedRuns lists twice per poll (action_required, failure).
    paginate: async (route, params) => {
      calls.listed.push(params);
      if (params.status === 'action_required') {
        i += 1;
        current = polls[Math.min(i, polls.length - 1)];
      }
      if (current instanceof Error) throw current;
      return current.filter((x) => x.head_sha === params.head_sha
        && (x.status === params.status || x.conclusion === params.status))
        .filter((x) => !calls.deleted.includes(x.id));
    },
  };
};

const log = () => {
  const lines = { notice: [], warning: [] };
  return { lines, notice: (m) => lines.notice.push(m), warning: (m) => lines.warning.push(m) };
};

const args = (extra) => ({
  owner: 'o', repo: 'r', branch: 'release/v1.2.0', headSha: 'h',
  timeoutMs: 60000, intervalMs: 5000, ...extra,
});

test('deleteParkedRuns deletes the runs as they appear and stops at the timeout', async () => {
  const github = api({ polls: [[], [parked(1)], [parked(1), parked(2)], []] });
  const c = clock();
  const l = log();
  const deleted = await deleteParkedRuns(github, args({ ...c, log: l }));
  assert.deepEqual(deleted, [1, 2]);
  assert.deepEqual(github.calls.deleted, [1, 2]);
  assert.ok(c.now() <= 60000, `waited ${c.now()} ms`);
  assert.ok(c.now() >= 55000, `stopped early at ${c.now()} ms`);
  assert.equal(l.lines.warning.length, 0);
  assert.equal(l.lines.notice.length, 2);
});

test('deleteParkedRuns asks for the release branch head only', async () => {
  const github = api({ polls: [[parked(1, 'other'), parked(2)]] });
  const deleted = await deleteParkedRuns(github, args({ ...clock(), log: log() }));
  assert.deepEqual(deleted, [2]);
  assert.ok(github.calls.listed.every((p) => p.head_sha === 'h' && p.branch === 'release/v1.2.0'));
});

test('deleteParkedRuns warns and returns when no run appears', async () => {
  const github = api({ polls: [[]] });
  const l = log();
  assert.deepEqual(await deleteParkedRuns(github, args({ ...clock(), log: l })), []);
  assert.equal(l.lines.warning.length, 1);
  assert.match(l.lines.warning[0], /No parked run of release\/v1\.2\.0 appeared within 60 s/);
});

test('deleteParkedRuns survives failed listings and still deletes what appears later', async () => {
  const github = api({ polls: [new Error('HTTP 502'), new Error('HTTP 503'), [parked(1)], []] });
  const l = log();
  assert.deepEqual(await deleteParkedRuns(github, args({ ...clock(), log: l })), [1]);
  assert.equal(l.lines.warning.filter((m) => /HTTP 50[23]/.test(m)).length, 2);
});

test('deleteParkedRuns warns about a failed deletion, keeps the others and never throws', async () => {
  const github = api({ polls: [[parked(1), parked(2)]], failDelete: [1] });
  const l = log();
  const deleted = await deleteParkedRuns(github, args({ ...clock(), log: l }));
  assert.deepEqual(deleted, [2]);
  assert.ok(l.lines.warning.some((m) => /Could not delete the parked run 1 .*HTTP 500 for 1/.test(m)));
  // One warning per run, not one per poll.
  assert.equal(l.lines.warning.filter((m) => /run 1 /.test(m)).length, 1);
});
