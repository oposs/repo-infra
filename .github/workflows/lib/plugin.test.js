'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { pluginProblems, githubRepo } = require('./plugin.js');

const GOOD = JSON.stringify({ name: 'demo', description: 'A demo', version: '1.2.3' });
const SELF = 'Oetiker/shadcn-egui';

// A repository as git ls-files and the file contents would show it.
function check(tree, repository = SELF) {
  return pluginProblems({
    files: Object.keys(tree),
    read: (path) => tree[path],
    repository,
  });
}

function marketplace(...plugins) {
  return JSON.stringify({ name: 'm', owner: { name: 'o' }, plugins });
}

test('a root plugin is checked as before', () => {
  assert.deepEqual(check({ '.claude-plugin/plugin.json': GOOD, 'README.md': '' }),
    { checked: ['.claude-plugin/plugin.json'], problems: [] });
});

test('a plugin only in a subdirectory is found and checked', () => {
  assert.deepEqual(check({ 'plugin/.claude-plugin/plugin.json': GOOD, 'Cargo.toml': '' }),
    { checked: ['plugin/.claude-plugin/plugin.json'], problems: [] });
});

test('a repository without a plugin fails with one message', () => {
  const { problems } = check({ 'README.md': '' });
  assert.equal(problems.length, 1);
  assert.match(problems[0], /no tracked \.claude-plugin\/plugin\.json/);
});

test('a bad version in a nested plugin names that file', () => {
  const bad = JSON.stringify({ name: 'demo', description: 'A demo', version: '1.2' });
  const { problems } = check({
    '.claude-plugin/plugin.json': GOOD,
    'plugin/.claude-plugin/plugin.json': bad,
  });
  assert.deepEqual(problems, ['plugin/.claude-plugin/plugin.json: version "1.2" is not X.Y.Z']);
});

test('missing fields and broken JSON name their file', () => {
  const { problems } = check({
    'a/.claude-plugin/plugin.json': JSON.stringify({ name: 'a', version: '1.0.0' }),
    'b/.claude-plugin/plugin.json': '{',
  });
  assert.equal(problems.length, 2);
  assert.equal(problems[0], 'a/.claude-plugin/plugin.json: description is missing or empty');
  assert.match(problems[1], /^b\/\.claude-plugin\/plugin\.json: not valid JSON/);
});

test('a file merely named plugin.json elsewhere is not a manifest', () => {
  const { problems } = check({ 'docs/plugin.json': '{', 'x.claude-plugin/plugin.json': '{' });
  assert.match(problems[0], /no tracked/);
});

test('a git-subdir entry for this repository with a plugin passes', () => {
  const tree = {
    '.claude-plugin/marketplace.json': marketplace({
      name: 'shadcn-egui',
      source: {
        source: 'git-subdir', url: 'https://github.com/oetiker/shadcn-egui.git',
        path: 'plugin', ref: 'v1.0.0', sha: 'a'.repeat(40),
      },
    }),
    'plugin/.claude-plugin/plugin.json': GOOD,
  };
  assert.deepEqual(check(tree).problems, []);
});

test('a git-subdir entry whose path holds no plugin.json fails', () => {
  const tree = {
    '.claude-plugin/marketplace.json': marketplace({
      name: 'shadcn-egui',
      source: { source: 'git-subdir', url: 'oetiker/shadcn-egui', path: './plugins/egui/' },
    }),
    'plugin/.claude-plugin/plugin.json': GOOD,
  };
  assert.deepEqual(check(tree).problems, [
    '.claude-plugin/marketplace.json: plugin "shadcn-egui" points at plugins/egui, '
      + 'which has no tracked plugins/egui/.claude-plugin/plugin.json',
  ]);
});

test('an entry for another repository is skipped', () => {
  const tree = {
    '.claude-plugin/marketplace.json': marketplace(
      { name: 'other', source: { source: 'git-subdir', url: 'oposs/repo-infra', path: 'nowhere' } },
      { name: 'gh', source: { source: 'github', repo: 'oposs/mdmost' } },
      { name: 'lab', source: { source: 'url', url: 'https://gitlab.example.com/oetiker/shadcn-egui.git' } },
      { name: 'pkg', source: { source: 'npm', package: '@o/pkg' } },
    ),
    'plugin/.claude-plugin/plugin.json': GOOD,
  };
  assert.deepEqual(check(tree).problems, []);
});

test('a relative entry must point at a plugin', () => {
  const tree = {
    '.claude-plugin/marketplace.json': marketplace(
      { name: 'good', source: './plugin' },
      { name: 'bad', source: './skills' },
    ),
    'plugin/.claude-plugin/plugin.json': GOOD,
  };
  assert.deepEqual(check(tree).problems, [
    '.claude-plugin/marketplace.json: plugin "bad" points at skills, '
      + 'which has no tracked skills/.claude-plugin/plugin.json',
  ]);
});

test('a bare name resolves under metadata.pluginRoot', () => {
  const tree = {
    '.claude-plugin/marketplace.json': JSON.stringify({
      name: 'm', owner: { name: 'o' }, metadata: { pluginRoot: './plugins' },
      plugins: [{ name: 'fmt', source: 'fmt' }],
    }),
    'plugins/fmt/.claude-plugin/plugin.json': GOOD,
  };
  assert.deepEqual(check(tree).problems, []);
});

test('a source without ./ and without pluginRoot fails as Claude Code refuses it', () => {
  const tree = {
    '.claude-plugin/marketplace.json': marketplace(
      { name: 'demo', source: 'plugin' },
      { name: 'nested', source: 'plugins/demo' },
    ),
    'plugin/.claude-plugin/plugin.json': GOOD,
    'plugins/demo/.claude-plugin/plugin.json': GOOD,
  };
  assert.deepEqual(check(tree).problems, [
    '.claude-plugin/marketplace.json: plugin "demo" has source "plugin", which must start with "./"',
    '.claude-plugin/marketplace.json: plugin "nested" has source "plugins/demo", '
      + 'which must start with "./"',
  ]);
});

test('a bare name with pluginRoot passes, a path with a slash still needs ./', () => {
  const tree = {
    '.claude-plugin/marketplace.json': JSON.stringify({
      name: 'm', owner: { name: 'o' }, metadata: { pluginRoot: '.' },
      plugins: [{ name: 'demo', source: 'plugin' }, { name: 'n', source: 'plugins/demo' }],
    }),
    'plugin/.claude-plugin/plugin.json': GOOD,
    'plugins/demo/.claude-plugin/plugin.json': GOOD,
  };
  assert.deepEqual(check(tree).problems, [
    '.claude-plugin/marketplace.json: plugin "n" has source "plugins/demo", which must start with "./"',
  ]);
});

test('a github entry for this repository needs the root plugin', () => {
  // shadcn-egui today: moving the plugin to plugin/ without changing this
  // entry would leave the marketplace pointing at nothing.
  const tree = {
    '.claude-plugin/marketplace.json': marketplace(
      { name: 'shadcn-egui', source: { source: 'github', repo: 'oetiker/shadcn-egui' } },
    ),
    'plugin/.claude-plugin/plugin.json': GOOD,
  };
  assert.deepEqual(check(tree).problems, [
    '.claude-plugin/marketplace.json: plugin "shadcn-egui" points at the repository root, '
      + 'which has no tracked .claude-plugin/plugin.json',
  ]);
  tree['.claude-plugin/plugin.json'] = GOOD;
  assert.deepEqual(check(tree).problems, []);
});

test('a git-subdir entry without a path, or leaving the repository, fails', () => {
  const tree = {
    '.claude-plugin/marketplace.json': marketplace(
      { name: 'a', source: { source: 'git-subdir', url: 'oetiker/shadcn-egui' } },
      { name: 'b', source: './../elsewhere' },
    ),
    '.claude-plugin/plugin.json': GOOD,
  };
  assert.deepEqual(check(tree).problems, [
    '.claude-plugin/marketplace.json: plugin "a" has a git-subdir source without a path',
    '.claude-plugin/marketplace.json: plugin "b" points at ../elsewhere, outside the repository',
  ]);
});

test('github URLs compare by owner/repo, ignoring case and .git', () => {
  for (const url of ['oetiker/shadcn-egui', 'https://github.com/Oetiker/shadcn-egui.git',
    'https://github.com/oetiker/shadcn-egui/', 'git@github.com:oetiker/SHADCN-egui.git',
    'ssh://git@github.com/oetiker/shadcn-egui']) {
    assert.equal(githubRepo(url), 'oetiker/shadcn-egui', url);
  }
  assert.equal(githubRepo('https://gitlab.example.com/oetiker/shadcn-egui'), null);
  assert.equal(githubRepo(undefined), null);
});
