'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const commit = require('./commit.js');

function fakeGithub() {
  const seen = { blobs: [], trees: [], commits: [], refs: [] };
  return {
    seen,
    rest: {
      git: {
        getCommit: async ({ commit_sha: sha }) => ({
          data: { sha, tree: { sha: `tree-of-${sha}` } },
        }),
        createBlob: async (params) => {
          seen.blobs.push(params);
          return { data: { sha: `blob-${seen.blobs.length}` } };
        },
        createTree: async (params) => {
          seen.trees.push(params);
          return { data: { sha: 'new-tree' } };
        },
        createCommit: async (params) => {
          seen.commits.push(params);
          return { data: { sha: 'new-commit' } };
        },
        createRef: async (params) => {
          seen.refs.push(params);
          return { data: { ref: params.ref } };
        },
        getTree: async ({ tree_sha: sha }) => {
          seen.treeReads = (seen.treeReads || 0) + 1;
          return { data: { sha, tree: TREES[sha] || [], truncated: false } };
        },
      },
    },
  };
}

/// The base commit's trees, one level per entry as the API returns them
/// without `recursive`: a release commit touches a few files, so walking their
/// directories is cheaper than the whole recursive tree, and never truncated.
const TREES = {
  'tree-of-base-sha': [
    { path: 'CHANGES.md', mode: '100644', type: 'blob', sha: 'b1' },
    { path: 'agents', mode: '040000', type: 'tree', sha: 'agents-tree' },
    { path: 'link', mode: '120000', type: 'blob', sha: 'b2' },
  ],
  'agents-tree': [
    { path: 'plugin', mode: '100755', type: 'blob', sha: 'b3' },
    { path: 'module.py', mode: '100644', type: 'blob', sha: 'b4' },
  ],
};

/// The API's answer when the branch is still there: a closed-but-undeleted
/// release PR, or a run that committed and then failed before opening one.
function refExistsError() {
  const e = new Error('Reference already exists');
  e.status = 422;
  return e;
}

function githubWithExistingRef() {
  const github = fakeGithub();
  github.rest.git.createRef = async (params) => {
    github.seen.refs.push(params);
    throw refExistsError();
  };
  github.seen.updates = [];
  github.rest.git.updateRef = async (params) => {
    github.seen.updates.push(params);
    return { data: { ref: params.ref } };
  };
  return github;
}

const ARGS = {
  owner: 'oposs',
  repo: 'repo-infra',
  branch: 'release/v1.2.3',
  baseSha: 'base-sha',
  message: 'Release v1.2.3',
  files: [
    { path: 'CHANGES.md', content: '# Changelog\n' },
    { path: '.claude-plugin/plugin.json', content: '{}\n' },
  ],
};

test('creates one blob per file, utf-8 encoded', async () => {
  const github = fakeGithub();
  await commit.commitFiles(github, ARGS);
  assert.equal(github.seen.blobs.length, 2);
  assert.equal(github.seen.blobs[0].content, '# Changelog\n');
  assert.equal(github.seen.blobs[0].encoding, 'utf-8');
});

test('the tree is based on the base commit tree, not the commit sha', async () => {
  // createTree's base_tree wants a tree SHA. Passing a commit SHA is the
  // mistake that silently produces a tree with no history behind it.
  const github = fakeGithub();
  await commit.commitFiles(github, ARGS);
  assert.equal(github.seen.trees[0].base_tree, 'tree-of-base-sha');
});

test('every entry is a blob, a plain file unless it was executable', async () => {
  const github = fakeGithub();
  await commit.commitFiles(github, ARGS);
  for (const entry of github.seen.trees[0].tree) {
    assert.equal(entry.mode, '100644');
    assert.equal(entry.type, 'blob');
  }
  assert.deepEqual(
    github.seen.trees[0].tree.map((e) => e.path),
    ['CHANGES.md', '.claude-plugin/plugin.json'],
  );
});

test('the commit has the base as its only parent', async () => {
  const github = fakeGithub();
  await commit.commitFiles(github, ARGS);
  assert.deepEqual(github.seen.commits[0].parents, ['base-sha']);
  assert.equal(github.seen.commits[0].tree, 'new-tree');
  assert.equal(github.seen.commits[0].message, 'Release v1.2.3');
});

test('the branch ref is created and the commit sha returned', async () => {
  const github = fakeGithub();
  const sha = await commit.commitFiles(github, ARGS);
  assert.equal(github.seen.refs[0].ref, 'refs/heads/release/v1.2.3');
  assert.equal(github.seen.refs[0].sha, 'new-commit');
  assert.equal(sha, 'new-commit');
});

test('an empty file list is refused', async () => {
  const github = fakeGithub();
  await assert.rejects(
    () => commit.commitFiles(github, { ...ARGS, files: [] }),
    /nothing to commit/,
  );
});

test('a branch left over from an earlier run is moved, not fatal', async () => {
  // Re-running the release workflow used to die here with an opaque 422.
  // The operator's only way out was deleting the branch by hand.
  const github = githubWithExistingRef();
  const sha = await commit.commitFiles(github, ARGS);
  assert.equal(sha, 'new-commit');
  assert.equal(github.seen.updates.length, 1);
  assert.equal(github.seen.updates[0].ref, 'heads/release/v1.2.3');
  assert.equal(github.seen.updates[0].sha, 'new-commit');
  assert.equal(github.seen.updates[0].force, true);
});

test('an error that is not "ref exists" still fails the run', async () => {
  const github = fakeGithub();
  github.rest.git.createRef = async () => {
    const e = new Error('Bad credentials');
    e.status = 401;
    throw e;
  };
  await assert.rejects(() => commit.commitFiles(github, ARGS), /Bad credentials/);
});

test('an executable file stays executable', async () => {
  // A Checkmk agent plugin is a version file. Written as 100644, the release
  // shipped an agent plugin the agent no longer ran.
  const github = fakeGithub();
  await commit.commitFiles(github, {
    ...ARGS,
    files: [
      { path: 'agents/plugin', content: '#!/bin/sh\n' },
      { path: 'agents/module.py', content: 'x = 1\n' },
      { path: 'CHANGES.md', content: '# Changelog\n' },
    ],
  });
  assert.deepEqual(
    github.seen.trees[0].tree.map((e) => [e.path, e.mode]),
    [['agents/plugin', '100755'], ['agents/module.py', '100644'], ['CHANGES.md', '100644']],
  );
});

test('a new file, or one under a new directory, is a plain file', async () => {
  const github = fakeGithub();
  await commit.commitFiles(github, {
    ...ARGS,
    files: [
      { path: 'agents/new', content: 'a\n' },
      { path: 'missing/dir/file', content: 'b\n' },
    ],
  });
  for (const entry of github.seen.trees[0].tree) assert.equal(entry.mode, '100644');
});

test('a symlink is replaced by a plain file, not written as a link', async () => {
  // Content written under mode 120000 would become the link target.
  const github = fakeGithub();
  await commit.commitFiles(github, { ...ARGS, files: [{ path: 'link', content: 'v\n' }] });
  assert.equal(github.seen.trees[0].tree[0].mode, '100644');
});

test('each directory of the base tree is read once', async () => {
  const github = fakeGithub();
  await commit.commitFiles(github, {
    ...ARGS,
    files: [
      { path: 'agents/plugin', content: 'a\n' },
      { path: 'agents/module.py', content: 'b\n' },
      { path: 'CHANGES.md', content: 'c\n' },
    ],
  });
  assert.equal(github.seen.treeReads, 2);
});
