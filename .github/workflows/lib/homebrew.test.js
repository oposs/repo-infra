'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('crypto');
const brew = require('./homebrew.js');

// The formula template of references/project-shape.md with its placeholders
// filled in; tests/test_release_homebrew.py holds the two to the same text.
const FORMULA = `# Homebrew formula for tool. This repository is its own tap.
#
# The release build rewrites the version line, the four sha256 lines by their
# marker comments and the bottle block between the BOTTLE markers. Keep the
# markers, and keep each url line directly above its sha256 line.
class Tool < Formula
  desc "A tool"
  homepage "https://github.com/owner/tool"
  version "0.0.0"
  license "MIT"

  # BOTTLE-START
  # BOTTLE-END

  on_macos do
    on_arm do
      url "https://github.com/owner/tool/releases/download/v#{version}/tool-#{version}-aarch64-apple-darwin.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000" # mac-arm
    end
    on_intel do
      url "https://github.com/owner/tool/releases/download/v#{version}/tool-#{version}-x86_64-apple-darwin.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000" # mac-x86
    end
  end

  on_linux do
    on_intel do
      url "https://github.com/owner/tool/releases/download/v#{version}/tool-#{version}-x86_64-unknown-linux-musl.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000" # linux-x86
    end
    on_arm do
      url "https://github.com/owner/tool/releases/download/v#{version}/tool-#{version}-aarch64-unknown-linux-musl.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000" # linux-arm
    end
  end

  def install
    bin.install "tool"
    Dir["man/*.[1-9]"].each { |page| (man/"man#{page[-1]}").install page }
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/tool --version")
  end
end
`;
// The formula with some platforms left out: each marker's url and sha256
// line goes, then every on_* block that is left empty.
function without(text, ...markers) {
  let lines = text.split('\n');
  for (const marker of markers) {
    const i = lines.findIndex((line) => line.endsWith(` # ${marker}`));
    lines.splice(i - 1, 2);
  }
  for (const block of ['on_intel do', 'on_arm do', 'on_macos do', 'on_linux do']) {
    for (let i = lines.length - 2; i >= 0; i -= 1) {
      if (lines[i].trim() === block && lines[i + 1].trim() === 'end') lines.splice(i, 2);
    }
  }
  lines = lines.join('\n').replace(/\n{3,}/g, '\n\n').split('\n');
  return lines.join('\n');
}
const ARM_ONLY = without(FORMULA, 'mac-x86', 'linux-x86', 'linux-arm');
const ENV = { BIN: 'tool', VERSION: '1.2.3', REPOSITORY: 'owner/tool', RUNNER_TEMP: '/t' };

// The shape `brew bottle --json --no-rebuild` writes: one entry per formula,
// the cellar on the bottle, the two file names on each tag.
function bottleJson(tag, sha, cellar) {
  const entry = { filename: `tool-1.2.3.${tag}.bottle.tar.gz`,
    local_filename: `tool--1.2.3.${tag}.bottle.tar.gz`, sha256: sha };
  if (cellar) entry.cellar = cellar;
  return { 'local/tool/tool': { formula: { name: 'tool', pkg_version: '1.2.3' },
    bottle: { cellar: 'any_skip_relocation', rebuild: 0, tags: { [tag]: entry } } } };
}
const ARM = bottleJson('arm64_sonoma', 'a'.repeat(64));
const INTEL = bottleJson('sequoia', 'b'.repeat(64));

function digest(text) {
  return crypto.createHash('sha256').update(text).digest('hex');
}

// A checkout as the bottle and formula jobs see it: `files` maps a path,
// relative to /w, to its text.
function fakeIo(files) {
  const store = new Map(Object.entries(files));
  return {
    store,
    cwd: () => '/w',
    isFile: (path) => store.has(path.replace(/^\/w\//, '')),
    read: (path) => store.get(path.replace(/^\/w\//, '')),
    write: (path, text) => store.set(path.replace(/^\/w\//, ''), text),
    mkdir: () => {},
    list: (dir) => [...store.keys()]
      .filter((p) => (dir === '.' ? !p.includes('/') : p.startsWith(`${dir}/`)))
      .map((p) => (dir === '.' ? p : p.slice(dir.length + 1)))
      .filter((p) => !p.includes('/')).sort(),
    rename: (from, to) => { store.set(to, store.get(from)); store.delete(from); },
    sha256: (path) => digest(store.get(path.replace(/^\/w\//, ''))),
  };
}

function archives(prefix, targets = Object.values(brew.MARKERS)) {
  return Object.fromEntries(targets.map((t) => [`${prefix}/tool-1.2.3-${t}.tar.gz`, `archive ${t}`]));
}

function formulaJob({ formula = FORMULA, jsons = [ARM, INTEL], built = true } = {}) {
  const files = { 'Formula/tool.rb': formula, ...archives('artifacts') };
  jsons.forEach((json, i) => {
    files[`bottles/${i}.bottle.json`] = JSON.stringify(json);
    if (built) for (const { to } of brew.bottleFiles(json)) files[`artifacts/${to}`] = 'bottle';
  });
  return fakeIo(files);
}

function block(text) {
  return text.split('  # BOTTLE-START\n')[1].split('  # BOTTLE-END')[0];
}

function refusal(fn, expected) {
  assert.throws(fn, (error) => {
    assert.match(error.message, expected);
    assert.doesNotMatch(error.message, /\n/);
    return true;
  });
}

test('the local tap points the mac urls at the built archives', () => {
  const io = fakeIo({ 'Formula/tool.rb': FORMULA,
    ...archives('dist', ['aarch64-apple-darwin', 'x86_64-apple-darwin']) });
  assert.equal(brew.pointAtArchives(ENV, io), '/t/local-formula.rb');
  const local = io.store.get('/t/local-formula.rb');
  for (const [marker, target] of [['mac-arm', 'aarch64-apple-darwin'], ['mac-x86', 'x86_64-apple-darwin']]) {
    assert.ok(local.includes(`      url "file:///w/dist/tool-1.2.3-${target}.tar.gz"\n`
      + `      sha256 "${digest(`archive ${target}`)}" # ${marker}\n`), marker);
  }
  assert.equal(local.split('/releases/download/v#{version}/').length - 1, 2, 'the linux urls stay');
  assert.match(local, /^ {2}version "1\.2\.3"$/m);
  assert.ok(local.includes('  # BOTTLE-START\n  # BOTTLE-END\n'));
});

for (const damage of ['deleted', 'blank line', 'comment']) {
  test(`a mac sha256 line without its url line directly above fails (${damage})`, () => {
    const lines = FORMULA.split('\n');
    const i = lines.findIndex((line) => line.endsWith('# mac-x86'));
    if (damage === 'deleted') lines.splice(i - 1, 1);
    else lines.splice(i, 0, damage === 'blank line' ? '' : '      # the Intel archive');
    const io = fakeIo({ 'Formula/tool.rb': lines.join('\n'),
      ...archives('dist', ['aarch64-apple-darwin', 'x86_64-apple-darwin']) });
    refusal(() => brew.pointAtArchives(ENV, io),
      /^no url line directly above the # mac-x86 sha256 line$/);
  });
}

test('a missing mac archive fails the local tap', () => {
  const io = fakeIo({ 'Formula/tool.rb': FORMULA, ...archives('dist', ['aarch64-apple-darwin']) });
  refusal(() => brew.pointAtArchives(ENV, io),
    /^\/w\/dist\/tool-1\.2\.3-x86_64-apple-darwin\.tar\.gz was not built$/);
});

test('a missing formula fails naming it', () => {
  refusal(() => brew.pointAtArchives(ENV, fakeIo({})), /^Formula\/tool\.rb does not exist$/);
});

// MacOSVersion::SYMBOLS of Homebrew/brew 856ce8c (2026-11-02).
const SYMBOLS = { golden_gate: '27', tahoe: '26', sequoia: '15', sonoma: '14',
  ventura: '13', monterey: '12', big_sur: '11' };
const MACOS = { RUNNER_TEMP: '/t' };
// `otool -l` of a Rust binary (cut down), and what it prints for a text file.
const OTOOL = `/w/keg/bin/tool:
Load command 9
      cmd LC_BUILD_VERSION
  cmdsize 32
 platform 1
    minos 11.0
      sdk 15.0
   ntools 1
     tool 3
  version 1100.0
/w/keg/README.md: is not an object file
`;
const MACOS_FILES = { '/t/macos-symbols.json': JSON.stringify(SYMBOLS), '/t/otool.txt': OTOOL };

test('otool output gives the minos of both load command kinds', () => {
  assert.deepEqual(brew.minosOf(OTOOL), ['11.0']);
  const old = 'Load command 8\n      cmd LC_VERSION_MIN_MACOSX\n  cmdsize 16\n  version 10.12\n      sdk 10.13\n';
  assert.deepEqual(brew.minosOf(OTOOL + old), ['11.0', '10.12']);
  assert.deepEqual(brew.minosOf('/w/keg/README.md: is not an object file\n'), []);
});

test('the bottle claims the oldest macOS its binaries run on', () => {
  assert.equal(brew.claimedTag('arm64_tahoe', SYMBOLS, ['11.0']), 'arm64_big_sur');
  assert.equal(brew.claimedTag('arm64_tahoe', SYMBOLS, ['10.12']), 'arm64_big_sur');
  assert.equal(brew.claimedTag('tahoe', SYMBOLS, ['10.12']), 'big_sur');
});

test('a minos inside a major version claims the next one', () => {
  assert.equal(brew.claimedTag('arm64_tahoe', SYMBOLS, ['11.3']), 'arm64_monterey');
});

test('the newest minos of the bottle decides', () => {
  assert.equal(brew.claimedTag('arm64_tahoe', SYMBOLS, ['11.0', '12.0', '10.12']), 'arm64_monterey');
});

test('a macOS brew dropped is never claimed', () => {
  const { big_sur: _, ...later } = SYMBOLS;
  assert.equal(brew.claimedTag('arm64_tahoe', later, ['11.0']), 'arm64_monterey');
});

test('a tag brew does not know fails', () => {
  refusal(() => brew.claimedTag('arm64_future', SYMBOLS, ['11.0']),
    /^brew bottle wrote the tag arm64_future, which names no macOS brew knows$/);
});

test('a bottle without a Mach-O minos fails', () => {
  refusal(() => brew.claimedTag('arm64_tahoe', SYMBOLS, []),
    /^no Mach-O file in the bottle names a minimum macOS$/);
});

test('a minos newer than every macOS brew knows fails', () => {
  refusal(() => brew.claimedTag('arm64_tahoe', SYMBOLS, ['28.0']),
    /^no macOS brew knows is as new as 28\.0, the minos of the bottle$/);
});

test('the bottles get their recorded names under the claimed tag', () => {
  const io = fakeIo({ ...MACOS_FILES, 'tool--1.2.3.arm64_tahoe.bottle.json': JSON.stringify(bottleJson('arm64_tahoe', 'a'.repeat(64))),
    'tool--1.2.3.arm64_tahoe.bottle.tar.gz': 'a' });
  assert.deepEqual(brew.renameBottles(MACOS, io), ['tool-1.2.3.arm64_big_sur.bottle.tar.gz']);
  assert.deepEqual(io.list('bottle'), ['tool--1.2.3.arm64_big_sur.bottle.json',
    'tool-1.2.3.arm64_big_sur.bottle.tar.gz']);
  assert.equal(io.store.get('bottle/tool-1.2.3.arm64_big_sur.bottle.tar.gz'), 'a');
  const json = JSON.parse(io.store.get('bottle/tool--1.2.3.arm64_big_sur.bottle.json'));
  assert.deepEqual(json, bottleJson('arm64_big_sur', 'a'.repeat(64)));
});

test('the retagged json gives the formula the claimed tag', () => {
  const json = brew.retagJson(bottleJson('arm64_tahoe', 'a'.repeat(64)), () => 'arm64_big_sur');
  const lines = brew.bottleBlock([json], { repository: 'owner/tool', version: '1.2.3' });
  assert.equal(lines[2], `    sha256 cellar: :any_skip_relocation, arm64_big_sur: "${'a'.repeat(64)}"`);
});

test('no bottle json fails the rename', () => {
  refusal(() => brew.renameBottles(MACOS, fakeIo(MACOS_FILES)), /^brew bottle wrote no json$/);
});

test('two bottles give the version, the four checksums and both bottles', () => {
  const io = formulaJob();
  const text = brew.rewriteFormula(ENV, io);
  assert.match(text, /^ {2}version "1\.2\.3"$/m);
  for (const [marker, target] of Object.entries(brew.MARKERS)) {
    assert.ok(text.includes(`sha256 "${digest(`archive ${target}`)}" # ${marker}\n`), marker);
  }
  assert.equal(block(text), [
    '  bottle do',
    '    root_url "https://github.com/owner/tool/releases/download/v1.2.3"',
    `    sha256 cellar: :any_skip_relocation, arm64_sonoma: "${'a'.repeat(64)}"`,
    `    sha256 cellar: :any_skip_relocation, sequoia: "${'b'.repeat(64)}"`,
    '  end', ''].join('\n'));
  assert.equal(io.store.get('Formula/tool.rb'), text);
  assert.equal(io.store.get('release-files/Formula/tool.rb'), text);
});

test('the cellar of a tag wins, and a Cellar path is quoted', () => {
  const lines = brew.bottleBlock([bottleJson('sonoma', 'c'.repeat(64), '/opt/homebrew/Cellar')],
    { repository: 'owner/tool', version: '1.2.3' });
  assert.equal(lines[2], `    sha256 cellar: "/opt/homebrew/Cellar", sonoma: "${'c'.repeat(64)}"`);
});

test('a bottle json without a cellar fails naming the tag', () => {
  const json = bottleJson('sonoma', 'c'.repeat(64));
  delete json['local/tool/tool'].bottle.cellar;
  refusal(() => brew.bottleBlock([json], { repository: 'owner/tool', version: '1.2.3' }),
    /^the bottle json of sonoma names no cellar$/);
});

test('the optional bottle missing still publishes the other', () => {
  const text = brew.rewriteFormula(ENV, formulaJob({ jsons: [ARM] }));
  assert.equal(block(text).split('sha256 cellar:').length - 1, 1);
});

test('zero bottles fail', () => {
  refusal(() => brew.rewriteFormula(ENV, formulaJob({ jsons: [] })), /^no bottles were built$/);
});

test('a bottle missing under its recorded name fails', () => {
  refusal(() => brew.rewriteFormula(ENV, formulaJob({ built: false })),
    /^bottle tool-1\.2\.3\.arm64_sonoma\.bottle\.tar\.gz was not built under that name$/);
});

test('a missing archive fails the formula job', () => {
  const io = formulaJob();
  io.store.delete('artifacts/tool-1.2.3-aarch64-unknown-linux-musl.tar.gz');
  refusal(() => brew.rewriteFormula(ENV, io),
    /^artifacts\/tool-1\.2\.3-aarch64-unknown-linux-musl\.tar\.gz was not built$/);
});

const BUILT_ANYWAY = {
  'mac-x86': 'x86_64-apple-darwin',
  'linux-x86': 'x86_64-unknown-linux-musl',
  'linux-arm': 'aarch64-unknown-linux-musl',
};
for (const marker of ['mac-arm', 'mac-x86', 'linux-x86', 'linux-arm', 'BOTTLE-START', 'BOTTLE-END']) {
  test(`a missing marker # ${marker} fails`, () => {
    const io = formulaJob({ formula: FORMULA.replace(` # ${marker}`, '') });
    const target = BUILT_ANYWAY[marker];
    const expected = target
      ? `^the marker # ${marker} is gone from Formula/tool\\.rb, but `
        + `artifacts/tool-1\\.2\\.3-${target}\\.tar\\.gz was built$`
      : `^the marker # ${marker} is gone from Formula/tool\\.rb$`;
    refusal(() => brew.rewriteFormula(ENV, io), new RegExp(expected));
  });
}

test('a formula without a version line fails', () => {
  const io = formulaJob({ formula: FORMULA.replace('  version "0.0.0"\n', '') });
  refusal(() => brew.rewriteFormula(ENV, io), /^Formula\/tool\.rb has no version line$/);
});

test('a second run changes nothing', () => {
  const io = formulaJob();
  const first = brew.rewriteFormula(ENV, io);
  assert.equal(brew.rewriteFormula(ENV, io), first);
});

test('the previous release block is replaced whole', () => {
  const old = '  # BOTTLE-START\n  bottle do\n'
    + '    root_url "https://github.com/owner/tool/releases/download/v9.9.9"\n'
    + `    sha256 cellar: :any_skip_relocation, old_tag: "${'1'.repeat(64)}"\n`
    + '  end\n  # BOTTLE-END';
  const formula = FORMULA.replace('  # BOTTLE-START\n  # BOTTLE-END', old);
  const inside = block(brew.rewriteFormula(ENV, formulaJob({ formula })));
  assert.doesNotMatch(inside, /v9\.9\.9|old_tag/);
  assert.match(inside, /root_url "https:\/\/github\.com\/owner\/tool\/releases\/download\/v1\.2\.3"/);
});

test('the arm-only formula keeps the mac-arm block alone', () => {
  assert.ok(ARM_ONLY.includes('on_macos do') && ARM_ONLY.includes('# mac-arm'));
  for (const gone of ['on_linux', 'on_intel', '# mac-x86', '# linux-']) {
    assert.ok(!ARM_ONLY.includes(gone), gone);
  }
});

test('an arm-only formula bottles from the arm archive alone', () => {
  const io = fakeIo({ 'Formula/tool.rb': ARM_ONLY, ...archives('dist', ['aarch64-apple-darwin']) });
  assert.equal(brew.pointAtArchives(ENV, io), '/t/local-formula.rb');
  const local = io.store.get('/t/local-formula.rb');
  assert.ok(local.includes('url "file:///w/dist/tool-1.2.3-aarch64-apple-darwin.tar.gz"'));
  assert.ok(local.includes(digest('archive aarch64-apple-darwin')));
  assert.ok(!local.includes('# mac-x86'));
});

test('an arm-only formula is rewritten from the arm archive alone', () => {
  const io = fakeIo({ 'Formula/tool.rb': ARM_ONLY, ...archives('artifacts', ['aarch64-apple-darwin']),
    'bottles/0.bottle.json': JSON.stringify(ARM),
    'artifacts/tool-1.2.3.arm64_sonoma.bottle.tar.gz': 'bottle' });
  const text = brew.rewriteFormula(ENV, io);
  assert.match(text, /^ {2}version "1\.2\.3"$/m);
  assert.ok(text.includes(`sha256 "${digest('archive aarch64-apple-darwin')}" # mac-arm\n`));
  assert.equal(block(text).split('sha256 cellar:').length - 1, 1);
  assert.ok(block(text).includes('arm64_sonoma'));
  assert.ok(!text.includes('# linux-'));
});

test('other archives beside an arm-only formula are ignored', () => {
  const io = fakeIo({ 'Formula/tool.rb': ARM_ONLY, ...archives('artifacts', ['aarch64-apple-darwin']),
    'artifacts/tool-1.2.3-x86_64-unknown-linux-gnu.tar.gz': 'glibc',
    'artifacts/tool_1.2.3~trixie-1_amd64.deb': 'deb',
    'bottles/0.bottle.json': JSON.stringify(ARM),
    'artifacts/tool-1.2.3.arm64_sonoma.bottle.tar.gz': 'bottle' });
  assert.match(brew.rewriteFormula(ENV, io), /^ {2}version "1\.2\.3"$/m);
});

test('a built archive whose marker is gone fails', () => {
  const bottle = fakeIo({ 'Formula/tool.rb': without(FORMULA, 'mac-x86'),
    ...archives('dist', ['aarch64-apple-darwin', 'x86_64-apple-darwin']) });
  refusal(() => brew.pointAtArchives(ENV, bottle),
    /^the marker # mac-x86 is gone from Formula\/tool\.rb, but \/w\/dist\/tool-1\.2\.3-x86_64-apple-darwin\.tar\.gz was built$/);
  refusal(() => brew.rewriteFormula(ENV, formulaJob({ formula: without(FORMULA, 'linux-arm') })),
    /^the marker # linux-arm is gone from Formula\/tool\.rb, but artifacts\/tool-1\.2\.3-aarch64-unknown-linux-musl\.tar\.gz was built$/);
});

test('a formula without # mac-arm fails', () => {
  const bottle = fakeIo({ 'Formula/tool.rb': without(FORMULA, 'mac-arm'),
    ...archives('dist', ['x86_64-apple-darwin']) });
  refusal(() => brew.pointAtArchives(ENV, bottle),
    /^the marker # mac-arm is gone from Formula\/tool\.rb$/);
  const io = fakeIo({ 'Formula/tool.rb': without(FORMULA, 'mac-arm'),
    ...archives('artifacts', ['x86_64-apple-darwin', 'x86_64-unknown-linux-musl', 'aarch64-unknown-linux-musl']) });
  refusal(() => brew.rewriteFormula(ENV, io), /^the marker # mac-arm is gone from Formula\/tool\.rb$/);
});
