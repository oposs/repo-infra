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
      const problem = fragmentProblem(f.text);
      if (problem) throw new Error(`${section}/${f.name}: ${problem}`);
      all.push(...entries(f.text));
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

const sameLines = (a, b) => a.length === b.length && a.every((l, i) => l === b[i]);

// What CHANGES.md may do in a fragment-mode pull request: its header and its
// '## ' headings stay, released text may be fixed. switching is set (with the
// entry count of the old [Unreleased] block, which baseText no longer holds)
// when the merge base had no note.
function changesMdProblems(baseText, headText, untaggedTop, switching) {
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
  if (sameLines(baseHeadings, headHeadings)) {
    out.releasedChanged = !sameLines(baseRest, headRest);
    return out;
  }
  // The abandon route: the release pull request rolled a section whose release
  // never got its tag, and this pull request takes it back out.
  if (baseHeadings.length > 0 && sameLines(baseHeadings.slice(1), headHeadings)) {
    const top = baseHeadings[0];
    const version = top.slice(3).split(' ')[0];
    if (version !== untaggedTop) {
      out.problems.push(`This pull request removes '${top}' from CHANGES.md, but v${version} is tagged. `
        + 'Only the section of a release that has no tag may be removed.');
      return out;
    }
    const start = baseRest.indexOf(top);
    const end = baseRest.findIndex((l, i) => i > start && l.startsWith('## '));
    out.required = countEntries(baseRest.slice(start + 1, end === -1 ? baseRest.length : end));
    out.removed = top;
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
  const md = changesMdProblems(baseText, headText, untaggedTop, switching);
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
    const problem = fragmentProblem(text);
    if (problem) {
      problems.push(`${f.filename}: ${problem}`);
      continue;
    }
    touched += 1;
    // A rename inside the section directories moves entries that are already
    // counted; only a new file brings entries back.
    const brings = f.status === 'added' || f.status === 'copied'
      || (f.status === 'renamed' && before.kind !== 'fragment');
    if (brings) addedEntries += entries(text).length;
  }
  if (addedEntries < md.required) {
    const what = md.removed ? `'${md.removed}'` : "'## [Unreleased]' at the merge base";
    problems.push(`${what} held ${md.required} entries, but this pull request restores ${addedEntries} `
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
  return { ok: true, message: `${touched} changelog fragment(s) under ${dir}/ follow the rules.` };
}

module.exports = {
  SECTIONS, noteDir, classifyPath, fragmentProblem, entries, renderSection, headerEnd,
  countEntries, fragmentVerdict,
};
