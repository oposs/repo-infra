'use strict';

// The releases ri-release-distro-packages builds for (D38), and the matrix
// that one run fans out over.
//
// Debian, Ubuntu and AlmaLinux entries change only when the owner changes the
// list. Fedora and Alpine numbers are bumped by hand when a release appears or
// ends: they were pinned on 2026-11-12 to Fedora 45 and Alpine 3.23 and 3.24.
// Pinned numbers, never `latest`, so a build does not change under a caller
// when the registry moves the tag. A release that leaves RELEASES moves to
// RETIRED, with its codename or dist tag, and is never deleted.

const hub = 'docker.io/library';

const RELEASES = [
  { distro: 'debian-12', image: `${hub}/debian:12`, family: 'deb', codename: 'bookworm' },
  { distro: 'debian-13', image: `${hub}/debian:13`, family: 'deb', codename: 'trixie' },
  { distro: 'ubuntu-22.04', image: `${hub}/ubuntu:22.04`, family: 'deb', codename: 'jammy' },
  { distro: 'ubuntu-24.04', image: `${hub}/ubuntu:24.04`, family: 'deb', codename: 'noble' },
  { distro: 'ubuntu-26.04', image: `${hub}/ubuntu:26.04`, family: 'deb', codename: 'resolute' },
  { distro: 'almalinux-9', image: `${hub}/almalinux:9`, family: 'rpm', dist: 'el9' },
  { distro: 'almalinux-10', image: `${hub}/almalinux:10`, family: 'rpm', dist: 'el10' },
  { distro: 'fedora', image: `${hub}/fedora:45`, family: 'rpm', dist: 'fc45' },
  { distro: 'alpine-3.23', image: `${hub}/alpine:3.23`, family: 'apk', branch: 'v3.23' },
  { distro: 'alpine-3.24', image: `${hub}/alpine:3.24`, family: 'apk', branch: 'v3.24' },
];

// Releases the piece built once and builds no more. ri-publish-gitea still
// routes their packages by codename or dist tag, so a package of an old
// release that is published again goes to the channel it was built for.
const RETIRED = [];

// Every release a package of this piece may name: the routing table.
const ROUTED = [...RELEASES, ...RETIRED];

// Native builds on both architectures, no cross compile. amd64 first.
const ARCHES = [
  { arch: 'amd64', os: 'ubuntu-24.04' },
  { arch: 'arm64', os: 'ubuntu-24.04-arm' },
];

function byDistro(name) {
  return RELEASES.find((r) => r.distro === name);
}

// '' (the workflow default) builds everything. Text that holds only blanks is
// a caller who meant to name releases and named none, so it fails instead of
// silently building all of them.
function distroPlan(text) {
  let chosen = RELEASES;
  if (text !== '') {
    const names = text.split(/\s+/).filter((n) => n !== '');
    if (names.length === 0) {
      throw new Error('distributions names no release');
    }
    const known = RELEASES.map((r) => r.distro);
    for (const n of names) {
      if (!known.includes(n)) {
        throw new Error(
          `distributions names ${n}, which this piece does not build; it builds ${known.join(' ')}`,
        );
      }
    }
    chosen = RELEASES.filter((r) => names.includes(r.distro));
  }
  const include = [];
  for (const r of chosen) {
    for (const a of ARCHES) {
      include.push({
        distro: r.distro, image: r.image, family: r.family, arch: a.arch, os: a.os,
      });
    }
  }
  return { include };
}

module.exports = { RELEASES, RETIRED, ROUTED, distroPlan, byDistro };
