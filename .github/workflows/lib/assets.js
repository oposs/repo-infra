'use strict';

// What `finalize` checks before it flips a release from draft to public.
//
// Until this existed, the only thing between that flip and a release with no
// artifacts on it was finalize's own `needs:` list. A `needs:` list is a
// single line in release-publish.yml, and losing it does not fail: finalize
// simply stops waiting and publishes a release whose .deb was never uploaded.
// Nothing goes red, because nothing went wrong -- it just did not wait.
//
// Ordering cannot report its own absence. An assertion can, and it cannot pass
// while being wrong: either the asset is on the release or it is not.

// A pattern is an asset name in which `*` stands for any run of characters --
// `*.deb`, `smtp-proxy-*-x86_64-unknown-linux-musl`. Deliberately not a full
// glob: the only thing that varies between releases is the version, and `*` is
// enough for it. A literal name would be the second place the version is
// written down, and it would go red on every release that did not update it.
function patternToRegExp(pattern) {
  const body = pattern
    .split('*')
    .map((part) => part.replace(/[.+?^${}()|[\]\\]/g, '\\$&'))
    .join('.*');
  return new RegExp(`^${body}$`);
}

// GitHub renames a release asset on upload: `~` becomes `.`, and then every
// run of dots becomes one dot, dots that were there before included. Tried
// on 2026-11-07 with a draft release of this repository:
//   a+b~c.txt -> a+b.c.txt   p~~q.txt -> p.q.txt   d..e.txt -> d.e.txt
//   f~.g.txt  -> f.g.txt     j~-k.txt -> j.-k.txt
// `+`, `-` and `_` stay. A pattern is compared in that same published form,
// and so is the name, so the check before the merge (the built files) and
// the one after the tag (the release's assets) give the same answer (#137).
function publishedName(name) {
  return name.replace(/~/g, '.').replace(/\.{2,}/g, '.');
}

function matches(name, pattern) {
  return patternToRegExp(publishedName(pattern)).test(publishedName(name));
}

// Built files that GitHub would publish under one name, as lists of the
// built names. The second upload of such a name fails half way through the
// release, so the build is refused before the release exists.
function collidingAssets(names) {
  const by = new Map();
  for (const name of names || []) {
    const key = publishedName(name);
    by.set(key, [...(by.get(key) || []), name]);
  }
  return [...by.values()].filter((group) => group.length > 1);
}

// The expected patterns that nothing on the release satisfies, in the order
// they were declared. Empty means the release carries everything it should.
//
// Note what this does NOT do: it never complains about an asset it did not
// expect. A repository that attaches something extra by hand is not broken,
// and a guard that failed on it would train people to route around finalize.
function missingAssets(names, patterns) {
  const present = names || [];
  return (patterns || []).filter(
    (pattern) => !present.some((name) => matches(name, pattern)),
  );
}

// Names of attached assets whose upload did not finish. GitHub keeps an asset
// in state `starter` or `open` when the upload broke half way, and it still
// lists by name, so a name check alone lets a broken file go public.
function unfinishedAssets(attached) {
  return (attached || []).filter((a) => a.state !== 'uploaded').map((a) => a.name);
}

module.exports = { publishedName, matches, missingAssets, collidingAssets, unfinishedAssets };
