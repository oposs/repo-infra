'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const archive = require('./archive.js');

// A checkout on disk, shaped like edaptor's: examples/ with a nested file,
// a single file in docs/, and the files every archive carries anyway.
function checkout(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'archive-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const write = (rel, text) => {
    fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), text);
  };
  write('examples/config.toml', 'a = 1\n');
  write('examples/deep/hook.sh', '#!/bin/sh\n');
  fs.chmodSync(path.join(root, 'examples/deep/hook.sh'), 0o755);
  write('docs/guide.md', 'guide\n');
  write('docs/other.md', 'other\n');
  write('README.md', 'readme\n');
  return root;
}

function files(dir) {
  return fs.readdirSync(dir, { recursive: true })
    .filter((rel) => fs.statSync(path.join(dir, rel)).isFile())
    .map((rel) => rel.split(path.sep).join('/'))
    .sort();
}

test('an empty or blank extra_paths names no path', () => {
  for (const text of [undefined, '', '  \n ']) {
    assert.deepEqual(archive.parseExtraPaths(text, 'tool'), []);
  }
});

test('paths split on blanks and newlines and come back normalised, once each', () => {
  assert.deepEqual(
    archive.parseExtraPaths(' examples/\n./docs/guide.md  examples docs//x/../y ', 'tool'),
    ['examples', 'docs/guide.md', 'docs/y'],
  );
});

test('an absolute path is refused and named', () => {
  for (const given of ['/etc/passwd', 'C:/Windows', 'c:x']) {
    assert.throws(() => archive.parseExtraPaths(`examples ${given}`, 'tool'),
      { message: `extra_paths names ${given}, an absolute path; `
        + 'name it relative to the repository root' });
  }
});

test('a path that leaves the repository is refused and named', () => {
  for (const given of ['..', '../other', 'examples/../../x', 'a/b/../../..']) {
    assert.throws(() => archive.parseExtraPaths(given, 'tool'),
      { message: `extra_paths names ${given}, which leaves the repository` });
  }
});

test('a backslash is refused, so every target reads the path alike', () => {
  assert.throws(() => archive.parseExtraPaths('examples\\config.toml', 'tool'),
    { message: 'extra_paths names examples\\config.toml; separate folders with /, '
      + 'the same on every target' });
});

test('the repository root itself is refused', () => {
  for (const given of ['.', './', 'examples/..']) {
    assert.throws(() => archive.parseExtraPaths(given, 'tool'),
      { message: `extra_paths names ${given}, the repository root itself; `
        + 'name the files or folders to ship' });
  }
});

test('a path onto what the archive holds already, or a working folder, is refused', () => {
  for (const [given, top] of [['tool', 'tool'], ['tool.exe', 'tool.exe'], ['man/extra.1', 'man'],
    ['README.md', 'README.md'], ['readme.md', 'readme.md'], ['LICENSE', 'LICENSE'],
    ['staging', 'staging'], ['.repo-infra/x', '.repo-infra']]) {
    assert.throws(() => archive.parseExtraPaths(given, 'tool'),
      { message: `extra_paths names ${given}, but ${top} is part of the archive `
        + 'or a working folder of the piece already' });
  }
  // A name that only starts like a reserved one passes.
  assert.deepEqual(archive.parseExtraPaths('tools manual LICENSES', 'tool'),
    ['tools', 'manual', 'LICENSES']);
});

test('without extra_paths nothing is staged', (t) => {
  const root = checkout(t);
  assert.deepEqual(archive.stageExtraPaths({ BIN: 'tool', EXTRA_PATHS: '' }, root),
    ['extra_paths is empty; the archives hold the binary, the man pages, README.md and LICENSE']);
  assert.equal(fs.existsSync(path.join(root, 'staging')), false);
});

test('folders and files land under staging/<bin>/ at their own relative path', (t) => {
  const root = checkout(t);
  const lines = archive.stageExtraPaths(
    { BIN: 'tool', EXTRA_PATHS: 'examples docs/guide.md' }, root);
  assert.deepEqual(lines, [
    'examples: folder copied to tool/examples',
    'docs/guide.md: file copied to tool/docs/guide.md',
  ]);
  assert.deepEqual(files(path.join(root, 'staging/tool')),
    ['docs/guide.md', 'examples/config.toml', 'examples/deep/hook.sh']);
  assert.equal(fs.readFileSync(path.join(root, 'staging/tool/examples/config.toml'), 'utf8'),
    'a = 1\n');
  if (process.platform !== 'win32') {
    assert.ok(fs.statSync(path.join(root, 'staging/tool/examples/deep/hook.sh')).mode & 0o111);
  }
});

test('staging into a staging/<bin>/ the pack step has begun keeps what is there', (t) => {
  const root = checkout(t);
  fs.mkdirSync(path.join(root, 'staging/tool'), { recursive: true });
  fs.writeFileSync(path.join(root, 'staging/tool/tool'), 'binary');
  archive.stageExtraPaths({ BIN: 'tool', EXTRA_PATHS: 'examples' }, root);
  assert.deepEqual(files(path.join(root, 'staging/tool')),
    ['examples/config.toml', 'examples/deep/hook.sh', 'tool']);
});

test('a path that does not exist fails and names the path', (t) => {
  const root = checkout(t);
  assert.throws(
    () => archive.stageExtraPaths({ BIN: 'tool', EXTRA_PATHS: 'examples integrations' }, root),
    { message: 'extra_paths names integrations, which does not exist in the repository' });
});

test('a symbolic link that leads outside the repository fails', (t) => {
  const root = checkout(t);
  const outside = fs.mkdtempSync(path.join(os.tmpdir(), 'outside-'));
  t.after(() => fs.rmSync(outside, { recursive: true, force: true }));
  fs.symlinkSync(outside, path.join(root, 'secrets'));
  assert.throws(() => archive.stageExtraPaths({ BIN: 'tool', EXTRA_PATHS: 'secrets' }, root),
    { message: 'extra_paths names secrets, which leads outside the repository '
      + 'through a symbolic link' });
});

test('a symbolic link inside the repository is followed', (t) => {
  const root = checkout(t);
  fs.symlinkSync('examples', path.join(root, 'samples'));
  archive.stageExtraPaths({ BIN: 'tool', EXTRA_PATHS: 'samples' }, root);
  assert.ok(fs.existsSync(path.join(root, 'staging/tool/samples/config.toml')));
});

test('an empty BIN fails', () => {
  assert.throws(() => archive.stageExtraPaths({ BIN: '', EXTRA_PATHS: 'examples' }, '.'),
    { message: 'BIN is empty' });
});
