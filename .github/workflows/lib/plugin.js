'use strict';

// What ri-ci-claude-plugin checks (#82).
//
// A plugin may live in a subdirectory, so that a marketplace entry with a
// git-subdir source installs that directory alone. oetiker/shadcn-egui kept
// its 90 KB plugin at the root, and each install copied the whole 41 MB
// repository. So the check finds every tracked .claude-plugin/plugin.json
// instead of reading the root one, and a marketplace at the root must point
// each entry for this repository at one of them.
//
// The marketplace fields follow the Claude Code marketplace reference:
// a relative path string ("./dir", "." or a bare name under
// metadata.pluginRoot) resolves from the repository root; the object
// sources github (repo), url (url) and git-subdir (url, path) name a
// repository, and only those naming this one are checked.

const MANIFEST = /(^|\/)\.claude-plugin\/plugin\.json$/;
const MARKETPLACE = '.claude-plugin/marketplace.json';

function parse(file, read) {
  let data;
  try {
    data = JSON.parse(read(file));
  } catch (error) {
    return { problem: `${file}: not valid JSON (${error.message})` };
  }
  if (data === null || typeof data !== 'object' || Array.isArray(data)) {
    return { problem: `${file}: not a JSON object` };
  }
  return { data };
}

function manifestProblems(file, read) {
  const { data, problem } = parse(file, read);
  if (problem) return [problem];
  const found = [];
  for (const field of ['name', 'description', 'version']) {
    if (!data[field]) found.push(`${file}: ${field} is missing or empty`);
  }
  if (data.version && !/^\d+\.\d+\.\d+$/.test(String(data.version))) {
    found.push(`${file}: version ${JSON.stringify(data.version)} is not X.Y.Z`);
  }
  return found;
}

// owner/repo in lower case, or null when the url names no GitHub repository.
// Accepts the owner/repo shorthand, https://github.com/owner/repo and
// git@github.com:owner/repo, each with or without .git.
function githubRepo(url) {
  if (typeof url !== 'string') return null;
  const match = url.trim()
    .replace(/\/+$/, '')
    .replace(/\.git$/, '')
    .match(/^(?:(?:https?:\/\/|ssh:\/\/git@)github\.com\/|git@github\.com:)?([\w.-]+\/[\w.-]+)$/i);
  return match ? match[1].toLowerCase() : null;
}

// A repository path without ./ and trailing slashes; '' is the root.
function clean(path) {
  return path.replace(/^(\.\/)+/, '').replace(/\/+$/, '').replace(/^\.$/, '');
}

// A relative source Claude Code refuses with `must start with "./"`: neither
// "." nor "./...", and not a bare name it can resolve under pluginRoot.
const UNPREFIXED = Symbol('unprefixed');

// The directory an entry's plugin lives in, '' for the root, null when the
// entry is fetched from somewhere other than this repository, undefined for
// a git-subdir source without a path, or UNPREFIXED.
function entryDirectory(source, self, pluginRoot) {
  if (typeof source === 'string') {
    if (source === '.' || source.startsWith('./')) return clean(source);
    if (pluginRoot && !source.includes('/')) {
      return [clean(pluginRoot), source].filter(Boolean).join('/');
    }
    return UNPREFIXED;
  }
  if (source === null || typeof source !== 'object' || !self) return null;
  if (source.source === 'github' && githubRepo(source.repo) === self) return '';
  if (source.source === 'url' && githubRepo(source.url) === self) return '';
  if (source.source === 'git-subdir' && githubRepo(source.url) === self) {
    return typeof source.path === 'string' ? clean(source.path) : undefined;
  }
  return null;
}

function marketplaceProblems(tracked, read, self) {
  const { data, problem } = parse(MARKETPLACE, read);
  if (problem) return [problem];
  if (!Array.isArray(data.plugins)) return [`${MARKETPLACE}: plugins is not a list`];
  const pluginRoot = (data.metadata || {}).pluginRoot;
  const found = [];
  data.plugins.forEach((entry, index) => {
    const label = `${MARKETPLACE}: plugin ${JSON.stringify((entry || {}).name || `#${index}`)}`;
    const dir = entryDirectory((entry || {}).source, self, pluginRoot);
    if (dir === null) return;
    if (dir === UNPREFIXED) {
      found.push(`${label} has source ${JSON.stringify(entry.source)}, which must start with "./"`);
      return;
    }
    if (dir === undefined) {
      found.push(`${label} has a git-subdir source without a path`);
      return;
    }
    if (dir.split('/').includes('..')) {
      found.push(`${label} points at ${dir}, outside the repository`);
      return;
    }
    const manifest = dir ? `${dir}/.claude-plugin/plugin.json` : '.claude-plugin/plugin.json';
    if (!tracked.has(manifest)) {
      found.push(`${label} points at ${dir || 'the repository root'}, `
        + `which has no tracked ${manifest}`);
    }
  });
  return found;
}

// files: the repository's tracked paths (git ls-files). read(path) returns a
// tracked file's text. repository: owner/repo of the repository checked.
function pluginProblems({ files, read, repository }) {
  const tracked = new Set(files);
  const checked = files.filter((f) => MANIFEST.test(f)).sort();
  if (checked.length === 0) {
    return {
      checked,
      problems: ['no tracked .claude-plugin/plugin.json in this repository, '
        + 'neither at the root nor in a subdirectory'],
    };
  }
  const problems = checked.flatMap((file) => manifestProblems(file, read));
  if (tracked.has(MARKETPLACE)) {
    problems.push(...marketplaceProblems(tracked, read, githubRepo(repository)));
  }
  return { checked, problems };
}

module.exports = { pluginProblems, githubRepo };
