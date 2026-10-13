'use strict';

// #58: GitHub parks the pull_request runs of a pull request that
// GITHUB_TOKEN opened, and the pull request shows "Approve workflows to run"
// while its head commit has a parked run. Nothing needs approving: finish
// wrote the required checks itself. So finish deletes those runs right after
// it opens the pull request. They appear a few seconds later, so this polls
// for a bounded time and deletes whatever shows up. It never throws: the runs
// are clutter, and publish deletes any that remain once the release merges.
// The clock and the API are arguments, so the tests need no network and no
// real time.

const { fetchParkedRuns } = require('./release.js');

async function deleteParkedRuns(github, {
  owner, repo, branch, headSha, sleep, now, timeoutMs, intervalMs, log,
}) {
  const start = now();
  const deleted = [];
  const failed = new Set();
  for (;;) {
    let parked = [];
    try {
      parked = await fetchParkedRuns(github, { owner, repo, branch, headSha });
    } catch (error) {
      log.warning(`Could not list the parked runs of ${branch}: ${error.message}`);
    }
    for (const run of parked) {
      if (deleted.includes(run.id)) continue;
      try {
        await github.rest.actions.deleteWorkflowRun({ owner, repo, run_id: run.id });
        deleted.push(run.id);
        log.notice(`Deleted the parked run ${run.id} of ${branch}.`);
      } catch (error) {
        if (!failed.has(run.id)) {
          log.warning(`Could not delete the parked run ${run.id} of ${branch}: ${error.message}`);
        }
        failed.add(run.id);
      }
    }
    if (now() - start + intervalMs > timeoutMs) break;
    await sleep(intervalMs);
  }
  if (deleted.length === 0 && failed.size === 0) {
    log.warning(`No parked run of ${branch} appeared within ${Math.round(timeoutMs / 1000)} s; `
      + 'if the pull request shows "Approve workflows to run", publish deletes them after the merge.');
  }
  return deleted;
}

module.exports = { deleteParkedRuns };
