'use strict';

const fragments = require('./fragments.js');

// The bracketed form, per Keep a Changelog. mdmost used a bare '## Unreleased';
// supporting both would make this a guessing machine, so the odd one out is
// migrated instead.
const UNRELEASED_HEADING = '## [Unreleased]';
const RELEASE_RE = /^## (\d+\.\d+\.\d+) - (\d{4}-\d{2}-\d{2})\s*$/;

// Where a '## ' block ends: at the next '## ', or at the end of the file.
function blockEnd(lines, start) {
  for (let i = start + 1; i < lines.length; i += 1) {
    if (lines[i].startsWith('## ')) return i;
  }
  return lines.length;
}

function findUnreleased(lines) {
  const start = lines.findIndex((l) => l.trim() === UNRELEASED_HEADING);
  if (start === -1) return null;
  return { start, end: blockEnd(lines, start) };
}

function unreleasedBlock(text) {
  const lines = text.split('\n');
  const range = findUnreleased(lines);
  if (!range) {
    throw new Error(`CHANGES.md has no '${UNRELEASED_HEADING}' heading`);
  }
  return lines.slice(range.start + 1, range.end).join('\n');
}

// The changelog gate's decision. A text is null when the file does not exist
// at that commit. A base without the heading counts as an empty block, because
// the pull request that converts a repository onto the standard is the one
// that introduces '## [Unreleased]'; a head without it cannot be judged.
function gateVerdict(baseText, headText) {
  const missing = `CHANGES.md has no '${UNRELEASED_HEADING}' heading; add it and an entry under it.`;
  const blockOf = (text) => (text === null || !findUnreleased(text.split('\n'))
    ? null
    : unreleasedBlock(text));
  const head = blockOf(headText);
  if (head === null) return { ok: false, message: missing };
  const base = blockOf(baseText);
  const unchanged = base === null ? isEmpty(head) : base === head;
  if (unchanged) {
    return {
      ok: false,
      message: `This pull request adds nothing under '${UNRELEASED_HEADING}' in `
        + 'CHANGES.md. Add an entry describing the change, or label the '
        + "pull request 'no-changelog' if it genuinely needs none.",
    };
  }
  return { ok: true, message: 'CHANGES.md [Unreleased] was updated.' };
}

// The gate's decision for both modes. The mode comes from the merge base and
// the head, not from the tip of the base branch: a pull request opened before
// a switch is judged by the rules it was written against, and after a release
// the tip has a '## ' heading the branch lacks. A text is null when the file
// does not exist at that commit. Never throws: a refused note is a failed
// check with a message, not a crashed job.
function changelogVerdict({
  baseText, mergeBaseText, headText, files = [], fragmentTexts = {}, untaggedTop = null,
  remainingFragments = 0,
}) {
  let baseDir;
  let headDir;
  try {
    baseDir = mergeBaseText == null ? null : fragments.noteDir(mergeBaseText);
    headDir = headText == null ? null : fragments.noteDir(headText);
  } catch (e) {
    return { ok: false, message: `CHANGES.md: ${e.message}.` };
  }
  if (headDir === null) {
    if (baseDir !== null && remainingFragments > 0) {
      return {
        ok: false,
        message: `CHANGES.md no longer has the 'Changelog fragments' note, but ${remainingFragments} `
          + `fragment files remain under ${baseDir}/. Move their entries under '${UNRELEASED_HEADING}' `
          + 'and delete the files in this pull request.',
      };
    }
    return gateVerdict(baseText, headText);
  }
  if (findUnreleased(headText.split('\n'))) return { ok: false, message: NOT_FINISHED };
  let rulesBase = mergeBaseText;
  let switching = null;
  if (baseDir === null) {
    const lines = (mergeBaseText ?? '').split('\n');
    const range = findUnreleased(lines);
    switching = { entries: range ? fragments.countEntries(lines.slice(range.start + 1, range.end)) : 0 };
    if (range) rulesBase = [...lines.slice(0, range.start), ...lines.slice(range.end)].join('\n');
  }
  return fragments.fragmentVerdict({
    dir: headDir, baseText: rulesBase, headText, files, fragmentTexts, untaggedTop, switching,
  });
}

function isEmpty(block) {
  return block
    .split('\n')
    .filter((l) => l.trim() !== '' && !l.trim().startsWith('### '))
    .length === 0;
}

// Split a block into its '### ' subsections, with each body trimmed.
function subsections(block) {
  const out = [];
  let current = null;
  for (const line of block.split('\n')) {
    if (line.trim().startsWith('### ')) {
      current = { heading: line.trim(), body: [] };
      out.push(current);
    } else if (current) {
      current.body.push(line);
    }
  }
  return out.map((s) => ({ heading: s.heading, body: s.body.join('\n').trim() }));
}

// A note in the header switches a repository to fragments (D40). Keeping
// '## [Unreleased]' as well would leave two places for entries, and an entry
// in the wrong one would be dropped from the release.
const NOT_FINISHED = `CHANGES.md has the 'Changelog fragments' note and '${UNRELEASED_HEADING}': `
  + 'the switch to fragments is not finished; remove the heading.';

function mode(text) {
  const dir = fragments.noteDir(text);
  if (dir === null) return { kind: 'classic' };
  if (findUnreleased(text.split('\n'))) throw new Error(NOT_FINISHED);
  return { kind: 'fragments', dir };
}

// The section goes between the header and the newest release; everything else
// stays as it is, because the fragments, not CHANGES.md, carry the new entries.
function rollFragments(text, dir, version, date, list) {
  if (list.length === 0) {
    throw new Error(`no changelog fragments in ${dir} - nothing to release`);
  }
  const lines = text.split('\n');
  const eol = text.includes('\r\n') ? '\r' : '';
  const at = fragments.headerEnd(lines);
  const section = fragments.renderSection(version, date, list).map((l) => l + eol);
  return [...lines.slice(0, at), ...section, ...lines.slice(at)].join('\n');
}

function roll(text, version, date, list = []) {
  const m = mode(text);
  if (m.kind === 'fragments') return rollFragments(text, m.dir, version, date, list);
  const lines = text.split('\n');
  const range = findUnreleased(lines);
  if (!range) {
    throw new Error(`CHANGES.md has no '${UNRELEASED_HEADING}' heading`);
  }

  const block = lines.slice(range.start + 1, range.end).join('\n');
  // A heading that appears twice (two branches each brought a skeleton) is
  // one subsection in the release, its entries in the order they were written.
  const kept = [];
  for (const s of subsections(block).filter((s) => s.body !== '')) {
    const earlier = kept.find((k) => k.heading === s.heading);
    if (earlier) {
      earlier.body += '\n' + s.body;
    } else {
      kept.push({ ...s });
    }
  }
  if (kept.length === 0) {
    throw new Error(`'${UNRELEASED_HEADING}' is empty - nothing to release`);
  }

  const skeleton = [UNRELEASED_HEADING, '', '### New', '', '### Changed', '', '### Fixed', ''];
  // A blank line after each heading, as in the skeleton: subsections() trims
  // each body, and the released section came out without them (#163,
  // oposs/thinfloe#12).
  const released = [`## ${version} - ${date}`, ''];
  for (const s of kept) {
    released.push(s.heading, '', s.body, '');
  }

  return [
    ...lines.slice(0, range.start),
    ...skeleton,
    ...released,
    ...lines.slice(range.end),
  ].join('\n');
}

function latestRelease(text) {
  for (const line of text.split('\n')) {
    const m = RELEASE_RE.exec(line);
    if (m) return { version: m[1], date: m[2] };
  }
  return null;
}

function notesFor(text, version) {
  const lines = text.split('\n');
  const start = lines.findIndex((l) => {
    const m = RELEASE_RE.exec(l);
    return m !== null && m[1] === version;
  });
  if (start === -1) {
    throw new Error(`CHANGES.md has no section for ${version}`);
  }
  return lines.slice(start + 1, blockEnd(lines, start)).join('\n').trim();
}

module.exports = {
  unreleasedBlock, gateVerdict, changelogVerdict, isEmpty, mode, roll, latestRelease, notesFor,
};
