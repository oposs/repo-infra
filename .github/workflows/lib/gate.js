'use strict';

// D33: Create release PR dispatches the release gate (gate-mtuspy.yml) on the
// release branch and waits for it. The dispatch API returns the run id when
// asked for run details (since February 2026); without it there is no run to
// wait for, which fails the gate. Everything external is an argument, so the
// tests need no network and no real time.

const RUN_ID_FIELD = 'workflow_run_id';
const MAX_FAILED_POLLS = 3;

async function dispatch(github, { owner, repo, workflow, ref }) {
  const { data } = await github.request(
    'POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches',
    { owner, repo, workflow_id: workflow, ref, return_run_details: true },
  );
  const id = data && data[RUN_ID_FIELD];
  if (!id) {
    throw new Error(`${workflow} was dispatched on ${ref}, but GitHub returned no run id `
      + `(${RUN_ID_FIELD}); there is no run to wait for.`);
  }
  return id;
}

async function waitForRun(github, {
  owner, repo, runId, sleep, now, timeoutMs, intervalMs,
}) {
  const start = now();
  let failed = 0;
  let url = '';
  for (;;) {
    let run = null;
    try {
      ({ data: run } = await github.rest.actions.getWorkflowRun({ owner, repo, run_id: runId }));
      failed = 0;
    } catch (error) {
      // A transient API failure (a 5xx) must not throw away a two-hour wait.
      failed += 1;
      if (failed > MAX_FAILED_POLLS) {
        throw new Error(`run ${runId} could not be read ${failed} times in a row: ${error.message}`);
      }
    }
    if (run) {
      if (run.status === 'completed') return { conclusion: run.conclusion, html_url: run.html_url };
      url = run.html_url;
    }
    if (now() - start + intervalMs > timeoutMs) {
      throw new Error(`run ${runId} did not finish within ${Math.round(timeoutMs / 1000)} s: ${url}`);
    }
    await sleep(intervalMs);
  }
}

async function runGate(github, {
  owner, repo, workflow, ref, sleep, now, timeoutMs, intervalMs,
}) {
  try {
    const runId = await dispatch(github, { owner, repo, workflow, ref });
    const run = await waitForRun(github, {
      owner, repo, runId, sleep, now, timeoutMs, intervalMs,
    });
    return { ok: run.conclusion === 'success',
      message: `${workflow} on ${ref}: ${run.conclusion}, ${run.html_url}` };
  } catch (error) {
    return { ok: false, message: error.message };
  }
}

module.exports = { RUN_ID_FIELD, dispatch, waitForRun, runGate };
