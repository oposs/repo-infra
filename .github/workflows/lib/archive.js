'use strict';

// ri-release-rust-binaries and ri-release-go-binaries: the extra_paths input.
// Each path the caller lists is copied into staging/<bin>/ under its own
// relative path, before the build, so the pack steps put it into every
// archive next to the binary. edaptor ships examples/ and mdmost
// integrations/, and their formulas `pkgshare.install` them: a path missing
// from the archive fails `brew install --build-bottle` in ri-release-homebrew.
// The step hands `stageExtraPaths` its environment and nothing else; the
// tests run it on real folders.

const fs = require('fs');
const path = require('path');

// Names a top-level entry of the archive already has, or a folder the piece
// works in. Compared without case: macOS and Windows file systems would fold
// readme.md onto README.md.
function reserved(bin) {
  return [bin, `${bin}.exe`, 'man', 'README.md', 'LICENSE', 'staging', '.repo-infra']
    .map((name) => name.toLowerCase());
}

// The paths of `text`, checked and normalised to the form a/b. Every refusal
// names the path as the caller wrote it.
function parseExtraPaths(text, bin) {
  const taken = reserved(bin);
  const paths = [];
  for (const given of (text || '').split(/\s+/).filter(Boolean)) {
    if (given.includes('\\')) {
      throw new Error(`extra_paths names ${given}; separate folders with /, `
        + 'the same on every target');
    }
    if (path.posix.isAbsolute(given) || /^[A-Za-z]:/.test(given)) {
      throw new Error(`extra_paths names ${given}, an absolute path; `
        + 'name it relative to the repository root');
    }
    const clean = path.posix.normalize(given).replace(/\/+$/, '');
    if (clean === '..' || clean.startsWith('../')) {
      throw new Error(`extra_paths names ${given}, which leaves the repository`);
    }
    if (clean === '.' || clean === '') {
      throw new Error(`extra_paths names ${given}, the repository root itself; `
        + 'name the files or folders to ship');
    }
    const top = clean.split('/')[0];
    if (taken.includes(top.toLowerCase())) {
      throw new Error(`extra_paths names ${given}, but ${top} is part of the archive `
        + 'or a working folder of the piece already');
    }
    if (!paths.includes(clean)) paths.push(clean);
  }
  return paths;
}

// Copies every path of EXTRA_PATHS from `root` into root/staging/<BIN>/ and
// returns one line per path for the log. A path that does not exist, or
// whose real location lies outside `root` through a symlink, fails.
function stageExtraPaths(env, root = process.cwd()) {
  const bin = env.BIN;
  if (!bin) throw new Error('BIN is empty');
  const paths = parseExtraPaths(env.EXTRA_PATHS, bin);
  if (paths.length === 0) return ['extra_paths is empty; the archives hold the binary, '
    + 'the man pages, README.md and LICENSE'];
  const realRoot = fs.realpathSync(root);
  const lines = [];
  for (const rel of paths) {
    const source = path.join(root, rel);
    if (!fs.existsSync(source)) {
      throw new Error(`extra_paths names ${rel}, which does not exist in the repository`);
    }
    const real = fs.realpathSync(source);
    const inside = path.relative(realRoot, real);
    if (inside === '' || inside === '..' || inside.startsWith(`..${path.sep}`)
        || path.isAbsolute(inside)) {
      throw new Error(`extra_paths names ${rel}, which leads outside the repository `
        + 'through a symbolic link');
    }
    const target = path.join(root, 'staging', bin, rel);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    // From the real location: a path that is itself a link inside the
    // repository ships what it points at. Links further down are copied as
    // links.
    fs.cpSync(real, target, { recursive: true });
    const kind = fs.statSync(real).isDirectory() ? 'folder' : 'file';
    lines.push(`${rel}: ${kind} copied to ${bin}/${rel}`);
  }
  return lines;
}

module.exports = { parseExtraPaths, stageExtraPaths };
