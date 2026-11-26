'use strict';

// Changelog fragments (D40): the pure rules. A repository opts in with a note in
// the header of CHANGES.md; pull requests then add files under the directory the
// note names instead of editing CHANGES.md, so two pull requests never conflict
// on the same lines.

const SECTIONS = [['new', '### New'], ['changed', '### Changed'], ['fixed', '### Fixed']];
const NOTE_RE = /^Changelog fragments: `([^`]+?)\/?`/;
const NAME_RE = /^[0-9]{8}-[0-9]{4}-[0-9a-f]{4}-[a-z0-9]+(-[a-z0-9]+)*\.md$/;

// The header is the part above the first '## ' line; a note below it belongs
// to a release entry and must not switch the mode.
function headerEnd(lines) {
  const i = lines.findIndex((l) => l.startsWith('## '));
  return i === -1 ? lines.length : i;
}

function refusedDir(dir) {
  if (dir.startsWith('/')) return 'is absolute';
  if (dir.split('/').includes('..')) return "contains '..'";
  if (dir === '.github' || dir.startsWith('.github/')) return "is or lies under '.github'";
  if (dir === 'CHANGES.md') return "is 'CHANGES.md'";
  return null;
}

function noteDir(text) {
  const lines = text.split(/\r?\n/);
  for (const line of lines.slice(0, headerEnd(lines))) {
    const m = NOTE_RE.exec(line);
    if (!m) continue;
    const reason = refusedDir(m[1]);
    if (reason) throw new Error(`Changelog fragments directory '${m[1]}' ${reason}`);
    return m[1];
  }
  return null;
}

function classifyPath(dir, path) {
  if (!path.startsWith(`${dir}/`)) return { kind: 'outside' };
  const parts = path.slice(dir.length + 1).split('/');
  if (parts.length === 1) return { kind: 'root' };
  const refuse = (reason) => ({ kind: 'refused', reason });
  const section = SECTIONS.find(([s]) => s === parts[0]);
  if (!section) return refuse(`'${parts[0]}' is not one of new, changed, fixed`);
  if (parts.length > 2) return refuse(`'${path}' is in a subdirectory of ${dir}/${parts[0]}/`);
  if (!NAME_RE.test(parts[1])) {
    return refuse(`'${parts[1]}' does not match <yyyymmdd>-<hhmm>-<4 hex>-<topic>.md`);
  }
  return { kind: 'fragment', section: section[0] };
}

// Entries: '- ' plus continuation lines indented by two spaces. Blank lines
// between entries are dropped, so the rolled section is laid out by the roller
// and not by whoever wrote the fragment.
function parse(text) {
  const out = [];
  for (const line of text.split(/\r?\n/)) {
    if (line.trim() === '') continue;
    if (line.startsWith('- ')) {
      out.push({ lines: [line] });
    } else if (line.startsWith('  ') && out.length > 0) {
      out[out.length - 1].lines.push(line);
    } else if (line.startsWith('#')) {
      return { problem: `a line starts with '#': ${line}` };
    } else {
      return { problem: `text outside an entry: ${line}` };
    }
  }
  if (out.length === 0) return { problem: 'no entry (a line starting with "- ")' };
  return { entries: out.map((e) => e.lines.join('\n')) };
}

function fragmentProblem(text) {
  return parse(text).problem || null;
}

function entries(text) {
  return parse(text).entries || [];
}

// The released section in the layout #163 introduced: a blank line after the
// heading and after each subsection.
function renderSection(version, date, fragments) {
  const lines = [`## ${version} - ${date}`, ''];
  for (const [section, heading] of SECTIONS) {
    const mine = fragments
      .filter((f) => f.section === section)
      .sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    const all = [];
    for (const f of mine) {
      const problem = fragmentProblem(f.text);
      if (problem) throw new Error(`${section}/${f.name}: ${problem}`);
      all.push(...entries(f.text));
    }
    if (all.length === 0) continue;
    lines.push(heading, '', ...all.flatMap((e) => e.split('\n')), '');
  }
  return lines;
}

module.exports = {
  SECTIONS, noteDir, classifyPath, fragmentProblem, entries, renderSection, headerEnd,
};
