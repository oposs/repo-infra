'use strict';

// Changelog fragments (D40): the pure rules. A repository opts in with a note in
// the header of CHANGES.md; pull requests then add files under the directory the
// note names instead of editing CHANGES.md, so two pull requests never conflict
// on the same lines.

const { posix } = require('node:path');

const SECTIONS = [['new', '### New'], ['changed', '### Changed'], ['fixed', '### Fixed']];
const NOTE_RE = /^Changelog fragments: `([^`]+?)\/?`/;
// Shared with changes.js: one definition of what a release heading is.
const RELEASE_RE = /^## (\d+\.\d+\.\d+) - (\d{4}-\d{2}-\d{2})\s*$/;
const NAME_RE = /^[0-9]{8}-[0-9]{4}-[0-9a-f]{4}-[a-z0-9]+(-[a-z0-9]+)*\.md$/;

// The header is the part above the first '## ' line; a note below it belongs
// to a release entry and must not switch the mode.
function headerEnd(lines) {
  const i = lines.findIndex((l) => l.startsWith('## '));
  return i === -1 ? lines.length : i;
}

// dir is the normalised directory: './CHANGES.d/' and 'CHANGES.d//' read as
// 'CHANGES.d', as GitHub names the files. Without that, './CHANGES.d' matched no
// path, so classifyPath saw every fragment as outside it.
function refusedDir(raw, dir) {
  if (raw.startsWith('/')) return 'is absolute';
  if (raw.split('/').includes('..')) return "contains '..'";
  if (dir === '.') return 'is the repository root';
  if (dir === '.github' || dir.startsWith('.github/')) return "is or lies under '.github'";
  if (dir === 'CHANGES.md') return "is 'CHANGES.md'";
  return null;
}

function noteDir(text) {
  const lines = text.split(/\r?\n/);
  for (const line of lines.slice(0, headerEnd(lines))) {
    const m = NOTE_RE.exec(line);
    if (!m) continue;
    const dir = posix.normalize(m[1]).replace(/\/$/, '');
    const reason = refusedDir(m[1], dir);
    if (reason) {
      // Marked so a caller can tell a refused note from a fault of its own.
      throw Object.assign(new Error(`Changelog fragments directory '${m[1]}' ${reason}`),
        { refusedNote: true });
    }
    return dir;
  }
  return null;
}

// The files under the section directories of dir, found with lstat semantics:
// a symbolic link or any other non-regular entry is refused, because a link to
// a file would roll text from outside the section and a link to a directory
// crashed the roll with EISDIR. fs and root are arguments so a test needs no
// workspace of its own beyond a scratch directory.
function listFragmentFiles(fs, root, dir) {
  const files = [];
  const refused = [];
  const walk = (rel) => {
    for (const e of fs.readdirSync(posix.join(root, rel), { withFileTypes: true })) {
      const p = `${rel}/${e.name}`;
      if (e.isSymbolicLink()) refused.push(`${p}: is a symbolic link`);
      else if (e.isDirectory()) walk(p);
      else if (e.isFile()) files.push(p);
      else refused.push(`${p}: is not a regular file`);
    }
  };
  for (const [section] of SECTIONS) {
    const rel = `${dir}/${section}`;
    let stat;
    try {
      stat = fs.lstatSync(posix.join(root, rel));
    } catch (error) {
      if (error.code === 'ENOENT') continue;
      throw error;
    }
    if (stat.isSymbolicLink()) refused.push(`${rel}: is a symbolic link`);
    else if (stat.isDirectory()) {
      const before = files.length;
      walk(rel);
      // Sorted within a section; the sections keep the order of SECTIONS.
      files.push(...files.splice(before).sort());
    }
    else refused.push(`${rel}: is not a directory`);
  }
  return { files, refused: refused.sort() };
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
      // A bare '- ' renders as an empty bullet in the release notes.
      if (line.slice(2).trim() === '') return { problem: `an entry without text: '${line}'` };
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

// What a caller that needs both the problem and the entries uses, so the text
// is read once.
const parseFragment = (text) => {
  const { problem = null, entries: list = [] } = parse(text);
  return { problem, entries: list };
};

function entries(text) {
  return parse(text).entries || [];
}

// The released section in the layout #163 introduced: a blank line after the
// heading and after each subsection.
function renderSection(version, date, fragments) {
  // A fragment in a section the loop below does not visit would be dropped
  // from the release without a word.
  for (const f of fragments) {
    if (!SECTIONS.some(([s]) => s === f.section)) {
      throw new Error(`${f.section}/${f.name}: '${f.section}' is not one of new, changed, fixed`);
    }
  }
  const lines = [`## ${version} - ${date}`, ''];
  for (const [section, heading] of SECTIONS) {
    const mine = fragments
      .filter((f) => f.section === section)
      .sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    const all = [];
    for (const f of mine) {
      const parsed = parseFragment(f.text);
      if (parsed.problem) throw new Error(`${section}/${f.name}: ${parsed.problem}`);
      all.push(...parsed.entries);
    }
    if (all.length === 0) continue;
    lines.push(heading, '', ...all.flatMap((e) => e.split('\n')), '');
  }
  return lines;
}

// The entries of a CHANGES.md block: its top-level list items. The gate counts
// them to see that a removed block came back as fragments; a count needs no
// text match and still catches a forgotten restore.
function countEntries(lines) {
  return lines.filter((l) => l.startsWith('- ')).length;
}

// Entry count per '## ' heading of the lines below the header. A released
// section that gained an entry at head is one whose entry will never reach a
// release: git merges a line added under [Unreleased] into the section above it
// without a conflict once main has rolled.
function sectionCounts(rest) {
  const counts = new Map();
  let heading = null;
  for (const l of rest) {
    if (l.startsWith('## ')) {
      heading = l;
      counts.set(heading, counts.get(heading) ?? 0);
    } else if (heading !== null && l.startsWith('- ')) counts.set(heading, counts.get(heading) + 1);
  }
  return counts;
}

function grownSections(baseRest, headRest) {
  const before = sectionCounts(baseRest);
  return [...sectionCounts(headRest)].filter(([h, n]) => n > (before.get(h) ?? 0)).map(([h]) => h);
}

const sameLines = (a, b) => a.length === b.length && a.every((l, i) => l === b[i]);

// What CHANGES.md may do in a fragment-mode pull request: its header and its
// '## ' headings stay, released text may be fixed. switching is set (with the
// entry count of the old [Unreleased] block, which baseText no longer holds)
// when the merge base had no note.
function changesMdProblems(baseText, headText, untaggedTop, switching, dir) {
  const base = (baseText ?? '').split(/\r?\n/);
  const head = (headText ?? '').split(/\r?\n/);
  const baseRest = base.slice(headerEnd(base));
  const headRest = head.slice(headerEnd(head));
  const out = { problems: [], required: 0, removed: null, releasedChanged: false };
  if (switching) {
    out.required = switching.entries;
    if (!sameLines(baseRest, headRest)) {
      out.problems.push('This pull request switches CHANGES.md to fragments and also changes its '
        + 'released sections. Leave the released sections as they are, and fix them in a pull '
        + 'request of its own.');
    }
    return out;
  }
  if (!sameLines(base.slice(0, headerEnd(base)), head.slice(0, headerEnd(head)))) {
    out.problems.push("This pull request changes the header of CHANGES.md (the part above the first '## ' "
      + 'line). With changelog fragments, pull requests leave the header as it is.');
  }
  const baseHeadings = baseRest.filter((l) => l.startsWith('## '));
  const headHeadings = headRest.filter((l) => l.startsWith('## '));
  // Text of released entries may be fixed or removed; a new entry may not be
  // added, since it would be left out of the next release.
  const growth = () => grownSections(baseRest, headRest).map((h) => `This pull request adds an entry to the released section '${h}' `
    + `of CHANGES.md, where the next release would leave it out. Move the entry into a file under ${dir}/new/, `
    + `${dir}/changed/ or ${dir}/fixed/.`);
  if (sameLines(baseHeadings, headHeadings)) {
    out.problems.push(...growth());
    out.releasedChanged = !sameLines(baseRest, headRest);
    return out;
  }
  // The abandon route: the release pull request rolled a section whose release
  // never got its tag, and this pull request takes it back out.
  if (baseHeadings.length > 0 && sameLines(baseHeadings.slice(1), headHeadings)) {
    const top = baseHeadings[0];
    // The workflow derives untaggedTop from the first '## X.Y.Z - date' line, so
    // a top heading of any other shape is no release and has no tag to check.
    const release = RELEASE_RE.exec(top);
    const version = release ? release[1] : null;
    if (!release) {
      out.problems.push(`This pull request removes '${top}' from CHANGES.md, which is not a release section. `
        + 'Only the section of a release that has no tag may be removed.');
      return out;
    }
    if (version !== untaggedTop) {
      out.problems.push(`This pull request removes '${top}' from CHANGES.md, but v${version} is tagged. `
        + 'Only the section of a release that has no tag may be removed.');
      return out;
    }
    const start = baseRest.indexOf(top);
    const end = baseRest.findIndex((l, i) => i > start && l.startsWith('## '));
    out.required = countEntries(baseRest.slice(start + 1, end === -1 ? baseRest.length : end));
    out.removed = top;
    out.problems.push(...growth());
    return out;
  }
  const added = headHeadings.filter((l) => !baseHeadings.includes(l));
  const gone = baseHeadings.filter((l) => !headHeadings.includes(l));
  const named = [...added.map((l) => `adds '${l}'`), ...gone.map((l) => `removes '${l}'`)];
  out.problems.push(`This pull request changes the '## ' headings of CHANGES.md (${named.join(', ') || 'reorders them'}). `
    + 'With changelog fragments, only the release pull request adds a section.');
  return out;
}

// The gate in fragment mode (D40). files are pulls.listFiles entries,
// fragmentTexts the head text of each fragment the pull request touches. Every
// way a fragment can leave the tree fails here, so no entry is lost before the
// release pull request rolls it.
function fragmentVerdict({ dir, baseText, headText, files, fragmentTexts, untaggedTop, switching = null }) {
  const md = changesMdProblems(baseText, headText, untaggedTop, switching, dir);
  const problems = [...md.problems];
  const lost = (path) => problems.push(`This pull request removes ${path}, which another pull request added. `
    + 'Restore it; the release pull request collects and deletes fragments.');
  let touched = 0;
  let addedEntries = 0;
  for (const f of files) {
    const now = classifyPath(dir, f.filename);
    if (f.status === 'removed') {
      if (now.kind === 'fragment') lost(f.filename);
      continue;
    }
    const before = f.previous_filename ? classifyPath(dir, f.previous_filename) : { kind: 'outside' };
    if (now.kind === 'refused') {
      problems.push(`${f.filename}: ${now.reason}`);
      continue;
    }
    if (now.kind !== 'fragment') {
      if (before.kind === 'fragment') lost(f.previous_filename);
      continue;
    }
    const text = fragmentTexts[f.filename];
    if (typeof text !== 'string') {
      problems.push(`${f.filename}: its text at the head of the pull request could not be read`);
      continue;
    }
    const parsed = parseFragment(text);
    if (parsed.problem) {
      problems.push(`${f.filename}: ${parsed.problem}`);
      continue;
    }
    touched += 1;
    // A rename inside the section directories moves entries that are already
    // counted; only a new file brings entries back.
    const brings = f.status === 'added' || f.status === 'copied'
      || (f.status === 'renamed' && before.kind !== 'fragment');
    if (brings) addedEntries += parsed.entries.length;
  }
  if (addedEntries < md.required) {
    const what = md.removed ? `'${md.removed}'` : "'## [Unreleased]' at the merge base";
    problems.push(`${what} held ${md.required} ${md.required === 1 ? 'entry' : 'entries'}, but this pull request restores ${addedEntries} `
      + `in fragments under ${dir}/. Add the missing entries as fragments.`);
  }
  if (problems.length > 0) return { ok: false, message: problems.join('\n') };
  if (touched === 0 && !md.releasedChanged && !md.removed && !switching) {
    return {
      ok: false,
      message: `This pull request adds no changelog fragment. Add one under \`${dir}/<section>/\`, `
        + "or label the pull request 'no-changelog'.",
    };
  }
  if (switching) return { ok: true, message: `CHANGES.md switches to fragments in ${dir}/.` };
  if (md.removed) return { ok: true, message: `${md.removed} is removed and its entries are back in fragments.` };
  if (touched === 0) return { ok: true, message: 'CHANGES.md: only released sections changed.' };
  const one = touched === 1;
  return {
    ok: true,
    message: `${touched} changelog ${one ? 'fragment' : 'fragments'} under ${dir}/ ${one ? 'follows' : 'follow'} the rules.`,
  };
}

module.exports = {
  SECTIONS, RELEASE_RE, noteDir, classifyPath, listFragmentFiles, fragmentProblem, entries, renderSection, headerEnd,
  countEntries, fragmentVerdict,
};
