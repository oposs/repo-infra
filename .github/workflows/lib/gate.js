'use strict';

// D33: Create release PR dispatches the release gate (gate-mtuspy.yml) and
// waits for it. The dispatch API returns the run id when asked for run details
// (since February 2026); without it there is no run to wait for, which fails
// the gate. Everything external is an argument, so the tests need no network
// and no real time.
//
// The gate never runs on the release head. In release 2.0.0 (PR #70) it did,
// and finish then wrote ci-passed and changelog-updated with GITHUB_TOKEN on
// that head: GitHub filed both check runs into the gate run's check suite,
// which the pull request does not list, and the ruleset kept reporting "2 of 2
// required status checks are expected". So the gate gets a commit of its own,
// with the release head's tree and the head as parent, on branch
// gate/v<version>, and the branch is deleted afterwards. Refs written with
// GITHUB_TOKEN start no workflows, so the branch triggers nothing by itself.

const RUN_ID_FIELD = 'workflow_run_id';
const MAX_FAILED_POLLS = 3;

const gateBranch = (version) => `gate/v${version}`;

async function createGateBranch(github, { owner, repo, head, version }) {
  const branch = gateBranch(version);
  const { data: commit } = await github.rest.git.getCommit({ owner, repo, commit_sha: head });
  const { data: gate } = await github.rest.git.createCommit({
    owner, repo, message: `Gate for v${version}`, tree: commit.tree.sha, parents: [head],
  });
  try {
    await github.rest.git.createRef({ owner, repo, ref: `refs/heads/${branch}`, sha: gate.sha });
  } catch (error) {
    // 422: the branch is left over from an earlier attempt.
    if (error.status !== 422) throw error;
    await github.rest.git.updateRef({ owner, repo, ref: `heads/${branch}`, sha: gate.sha, force: true });
  }
  return branch;
}

async function deleteGateBranch(github, { owner, repo, branch, warn }) {
  try {
    await github.rest.git.deleteRef({ owner, repo, ref: `heads/${branch}` });
  } catch (error) {
    warn(`${branch} could not be deleted: ${error.message}`);
  }
}

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
  owner, repo, workflow, head, version, sleep, now, timeoutMs, intervalMs, warn,
}) {
  let branch = null;
  try {
    branch = await createGateBranch(github, { owner, repo, head, version });
    const runId = await dispatch(github, { owner, repo, workflow, ref: branch });
    const run = await waitForRun(github, {
      owner, repo, runId, sleep, now, timeoutMs, intervalMs,
    });
    return { ok: run.conclusion === 'success',
      message: `${workflow} on ${branch}: ${run.conclusion}, ${run.html_url}` };
  } catch (error) {
    return { ok: false, message: error.message };
  } finally {
    if (branch) await deleteGateBranch(github, { owner, repo, branch, warn });
  }
}

module.exports = {
  RUN_ID_FIELD, gateBranch, createGateBranch, deleteGateBranch, dispatch, waitForRun, runGate,
};
