'use strict';

// ri-release-homebrew (D32): the three formula steps around the bottle
// build. The formula follows the template in references/project-shape.md: a
// url line directly above each of the four sha256 lines marked # mac-arm,
// # mac-x86, # linux-x86 and # linux-arm, and the bottle block between
// # BOTTLE-START and # BOTTLE-END. The steps in ri-release-homebrew.yml hand
// these functions their environment and nothing else. The file system goes
// through `io`, which the tests replace.

const MARKERS = {
  'mac-arm': 'aarch64-apple-darwin',
  'mac-x86': 'x86_64-apple-darwin',
  'linux-x86': 'x86_64-unknown-linux-musl',
  'linux-arm': 'aarch64-unknown-linux-musl',
};
const VERSION_LINE = /^ {2}version ".*"$/m;
const SHA = /sha256 "[0-9a-f]*"/;

function shaLines(lines, marker) {
  const pattern = new RegExp(`${SHA.source} # ${marker}\\s*$`);
  return lines.flatMap((line, i) => (pattern.test(line) ? [i] : []));
}

function setVersion(text, version) {
  return text.replace(VERSION_LINE, `  version "${version}"`);
}

// The lines between the two BOTTLE markers are replaced in place, so a
// second run writes the same file.
function withBlock(text, inner, formula) {
  const lines = text.split('\n');
  const start = lines.findIndex((line) => line.includes('# BOTTLE-START'));
  const end = lines.findIndex((line) => line.includes('# BOTTLE-END'));
  for (const [marker, at] of [['BOTTLE-START', start], ['BOTTLE-END', end]]) {
    if (at < 0) throw new Error(`the marker # ${marker} is gone from ${formula}`);
  }
  if (end < start) throw new Error(`# BOTTLE-END stands above # BOTTLE-START in ${formula}`);
  return [...lines.slice(0, start + 1), ...inner, ...lines.slice(end)].join('\n');
}

// The release does not exist yet, so the local tap points each mac url line
// at the archive this run built. A url line anywhere but directly above its
// sha256 line would be left alone, and brew would fetch a GitHub url that
// answers 404.
function localFormula(text, { formula, version, archives }) {
  const lines = text.split('\n');
  const problems = [];
  for (const marker of ['mac-arm', 'mac-x86']) {
    const found = shaLines(lines, marker);
    if (found.length !== 1) {
      problems.push(`${formula} needs one # ${marker} sha256 line, not ${found.length}`);
      continue;
    }
    const i = found[0];
    if (i === 0 || !/^\s*url "/.test(lines[i - 1])) {
      problems.push(`no url line directly above the # ${marker} sha256 line`);
      continue;
    }
    const indent = lines[i - 1].match(/^\s*/)[0];
    lines[i - 1] = `${indent}url "${archives[marker].url}"`;
    lines[i] = lines[i].replace(SHA, `sha256 "${archives[marker].sha}"`);
  }
  if (problems.length > 0) throw new Error(problems.join('; '));
  return withBlock(setVersion(lines.join('\n'), version), [], formula);
}

// `brew bottle` writes name--version.tag.bottle.tar.gz, with two dashes, the
// name GitHub Packages wants. A plain root_url is fetched with one dash. The
// json records both names.
function bottleFiles(json) {
  return Object.values(json).flatMap((entry) => Object.values(entry.bottle.tags)
    .map((tag) => ({ from: tag.local_filename, to: tag.filename })));
}

// `cellar` sits on the bottle and `brew bottle` copies it onto each tag; the
// tag's own value wins. A relocatable bottle names a symbol such as
// any_skip_relocation, a fixed one the Cellar path, which Ruby needs quoted.
function cellar(value) {
  return value.startsWith('/') ? `"${value}"` : `:${value}`;
}

// Generated, not patched: which architectures produced a bottle is known
// only now, and a sha256 line for a bottle that was never built sends
// Homebrew after a file that does not exist.
function bottleBlock(jsons, { repository, version }) {
  const lines = ['  bottle do',
    `    root_url "https://github.com/${repository}/releases/download/v${version}"`];
  for (const json of jsons) {
    for (const { bottle } of Object.values(json)) {
      for (const [tag, entry] of Object.entries(bottle.tags)) {
        const value = entry.cellar || bottle.cellar;
        if (!value) throw new Error(`the bottle json of ${tag} names no cellar`);
        lines.push(`    sha256 cellar: ${cellar(value)}, `
          + `${tag}: "${entry.sha256}"`);
      }
    }
  }
  lines.push('  end');
  return lines;
}

// The formula arrives carrying the previous release's bottle block. Left
// alone, it would publish a root_url pointing at the previous tag under
// this version: mdmost v0.3.2 did, and every brew install met a 404. Zero
// bottles fails for the same reason.
function releaseFormula(text, { formula, version, shas, jsons, built, repository }) {
  if (!VERSION_LINE.test(text)) throw new Error(`${formula} has no version line`);
  const lines = text.split('\n');
  for (const marker of Object.keys(MARKERS)) {
    const found = shaLines(lines, marker);
    if (found.length === 0) throw new Error(`the marker # ${marker} is gone from ${formula}`);
    if (found.length > 1) {
      throw new Error(`the marker # ${marker} stands on ${found.length} lines of ${formula}`);
    }
    lines[found[0]] = lines[found[0]].replace(SHA, `sha256 "${shas[marker]}"`);
  }
  const rewritten = withBlock(setVersion(lines.join('\n'), version), [], formula);
  if (jsons.length === 0) throw new Error('no bottles were built');
  for (const { to } of jsons.flatMap(bottleFiles)) {
    if (!built.includes(to)) throw new Error(`bottle ${to} was not built under that name`);
  }
  return withBlock(rewritten, bottleBlock(jsons, { repository, version }), formula);
}

function nodeIo() {
  const fs = require('fs');
  const crypto = require('crypto');
  return {
    cwd: () => process.cwd(),
    isFile: (path) => fs.existsSync(path) && fs.statSync(path).isFile(),
    read: (path) => fs.readFileSync(path, 'utf8'),
    write: (path, text) => fs.writeFileSync(path, text),
    mkdir: (path) => fs.mkdirSync(path, { recursive: true }),
    list: (path) => (fs.existsSync(path) ? fs.readdirSync(path).sort() : []),
    rename: (from, to) => fs.renameSync(from, to),
    sha256: (path) => crypto.createHash('sha256').update(fs.readFileSync(path)).digest('hex'),
  };
}

function formulaOf(env, io) {
  const formula = `Formula/${env.BIN}.rb`;
  if (!io.isFile(formula)) throw new Error(`${formula} does not exist`);
  return formula;
}

// Bottle leg, before `brew install --build-bottle`: the formula of the local
// tap, written to $RUNNER_TEMP/local-formula.rb. dist/ holds the two mac
// archives.
function pointAtArchives(env, io = nodeIo()) {
  const formula = formulaOf(env, io);
  const archives = {};
  for (const marker of ['mac-arm', 'mac-x86']) {
    const path = `${io.cwd()}/dist/${env.BIN}-${env.VERSION}-${MARKERS[marker]}.tar.gz`;
    if (!io.isFile(path)) throw new Error(`${path} was not built`);
    archives[marker] = { url: `file://${path}`, sha: io.sha256(path) };
  }
  const out = `${env.RUNNER_TEMP}/local-formula.rb`;
  io.write(out, localFormula(io.read(formula), { formula, version: env.VERSION, archives }));
  return out;
}

function compareVersions(a, b) {
  const x = String(a).split('.').map(Number);
  const y = String(b).split('.').map(Number);
  for (let i = 0; i < Math.max(x.length, y.length); i += 1) {
    const d = (x[i] || 0) - (y[i] || 0);
    if (d !== 0) return d;
  }
  return 0;
}

// Homebrew pours a bottle on the macOS its tag names and on every newer one,
// and checks nothing else about where it was built (find_older_compatible_tag
// and pour_bottle? in Homebrew/brew). `brew bottle` tags with the runner's
// macOS, but the binaries in the bottle were built elsewhere and run from
// their minos on. The bottle claims the oldest macOS brew knows that is not
// older than the newest minos of its files. `symbols` is brew's
// MacOSVersion::SYMBOLS: a name dropped there stops matching any Mac without
// an error, so the choice is read from brew at every release.
function claimedTag(builtTag, symbols, minos) {
  const system = Object.keys(symbols)
    .filter((name) => builtTag === name || builtTag.endsWith(`_${name}`))
    .sort((a, b) => b.length - a.length)[0];
  if (!system) throw new Error(`brew bottle wrote the tag ${builtTag}, which names no macOS brew knows`);
  if (minos.length === 0) throw new Error('no Mach-O file in the bottle names a minimum macOS');
  const floor = minos.reduce((a, b) => (compareVersions(a, b) >= 0 ? a : b));
  const oldest = Object.entries(symbols)
    .filter(([, version]) => compareVersions(version, floor) >= 0)
    .sort(([, a], [, b]) => compareVersions(a, b))[0];
  if (!oldest) throw new Error(`no macOS brew knows is as new as ${floor}, the minos of the bottle`);
  return `${builtTag.slice(0, builtTag.length - system.length)}${oldest[0]}`;
}

// The json with each tag replaced by its claim, and the file names with it.
function retagJson(json, claim) {
  const out = JSON.parse(JSON.stringify(json));
  for (const { bottle } of Object.values(out)) {
    const tags = {};
    for (const [tag, entry] of Object.entries(bottle.tags)) {
      const to = claim(tag);
      for (const key of ['filename', 'local_filename']) {
        entry[key] = entry[key].replace(`.${tag}.bottle.`, `.${to}.bottle.`);
      }
      tags[to] = entry;
    }
    bottle.tags = tags;
  }
  return out;
}

// The minos of every Mach-O load command in `otool -l` output:
// LC_BUILD_VERSION names it minos, the older LC_VERSION_MIN_MACOSX version.
// Text otool prints for a file that is no object file holds neither.
function minosOf(text) {
  const found = [];
  let cmd = '';
  for (const line of text.split('\n')) {
    const [key, value] = line.trim().split(/\s+/);
    if (key === 'cmd') cmd = value;
    else if ((cmd === 'LC_BUILD_VERSION' && key === 'minos')
      || (cmd === 'LC_VERSION_MIN_MACOSX' && key === 'version')) found.push(value);
  }
  return found;
}

// Bottle leg, after `brew bottle --json`: bottle/ receives each bottle under
// the name its json records, retagged to the oldest macOS it runs on, and
// the json. $RUNNER_TEMP holds macos-symbols.json, brew's macOS names, and
// otool.txt, `otool -l` of every file in the keg.
function renameBottles(env, io = nodeIo()) {
  const jsons = io.list('.').filter((name) => name.endsWith('.bottle.json'));
  if (jsons.length === 0) throw new Error('brew bottle wrote no json');
  const symbols = JSON.parse(io.read(`${env.RUNNER_TEMP}/macos-symbols.json`));
  const minos = minosOf(io.read(`${env.RUNNER_TEMP}/otool.txt`));
  io.mkdir('bottle');
  const moved = [];
  for (const name of jsons) {
    const built = JSON.parse(io.read(name));
    const claims = {};
    const json = retagJson(built, (tag) => {
      claims[tag] = claimedTag(tag, symbols, minos);
      return claims[tag];
    });
    const from = bottleFiles(built);
    bottleFiles(json).forEach(({ to }, i) => {
      io.rename(from[i].from, `bottle/${to}`);
      moved.push(to);
    });
    let out = name;
    for (const [tag, to] of Object.entries(claims)) out = out.replace(`.${tag}.bottle.`, `.${to}.bottle.`);
    io.write(`bottle/${out}`, `${JSON.stringify(json, null, 2)}\n`);
  }
  return moved;
}

// Formula job: artifacts/ holds every release asset, bottles/ the json of
// every bottle leg that finished. Writes the formula in place and as
// release-files/Formula/<bin>.rb, and returns it for the log.
function rewriteFormula(env, io = nodeIo()) {
  const formula = formulaOf(env, io);
  const shas = {};
  for (const [marker, target] of Object.entries(MARKERS)) {
    const archive = `artifacts/${env.BIN}-${env.VERSION}-${target}.tar.gz`;
    if (!io.isFile(archive)) throw new Error(`${archive} was not built`);
    shas[marker] = io.sha256(archive);
  }
  const jsons = io.list('bottles').filter((name) => name.endsWith('.bottle.json'))
    .map((name) => JSON.parse(io.read(`bottles/${name}`)));
  const text = releaseFormula(io.read(formula), {
    formula, version: env.VERSION, shas, jsons, built: io.list('artifacts'),
    repository: env.REPOSITORY,
  });
  io.write(formula, text);
  io.mkdir('release-files/Formula');
  io.write(`release-files/Formula/${env.BIN}.rb`, text);
  return text;
}

module.exports = {
  MARKERS, localFormula, bottleFiles, bottleBlock, releaseFormula, claimedTag, retagJson, minosOf,
  pointAtArchives, renameBottles, rewriteFormula,
};
