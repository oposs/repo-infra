## Install

**Homebrew** (macOS and Linux) — this repository is its own tap:

```sh
brew tap oetiker/mdmost https://github.com/oetiker/mdmost
brew trust --formula oetiker/mdmost/mdmost
brew install mdmost
```

Homebrew 6.0 stopped loading formulae from third-party taps until they are trusted, so
the middle line is required. It trusts this one formula rather than the whole tap.
`brew install oetiker/mdmost/mdmost` does the same thing in one step, because a
fully-qualified name trusts the formula it names. On Homebrew 5 and older there is no
`brew trust` command and no trust to grant: skip that line.

On **macOS**, `brew install` may stop with *Your Command Line Tools are too outdated*.
The formula ships prebuilt binaries and compiles nothing, but Homebrew calls any install
without a matching bottle a source build, and a source build insists on working developer
tools. Releases ship bottles for current macOS, so this only comes up on a Mac older than
those bottles. The commands Homebrew prints are the fix:

```sh
sudo rm -rf /Library/Developer/CommandLineTools
sudo xcode-select --install
```

**Debian, Ubuntu** — download `mdmost_<version>_amd64.deb` (or `_arm64.deb`) from the
[releases page](https://github.com/oetiker/mdmost/releases):

```sh
sudo dpkg -i mdmost_*_amd64.deb
man mdmost
```

**Fedora, RHEL, openSUSE** — download the matching `.rpm`:

```sh
sudo rpm -i mdmost-*.x86_64.rpm
```

There is no apt or yum repository, so `apt upgrade` will not find new versions: come
back to the releases page for those.

**Any Linux** — the tarballs are static musl builds and need nothing installed. The
archive carries the man page beside the binary, so install both:

```sh
tar xzf mdmost-*-x86_64-unknown-linux-musl.tar.gz
sudo install -Dm755 mdmost/mdmost       /usr/local/bin/mdmost
sudo install -Dm644 mdmost/man/mdmost.1 /usr/local/share/man/man1/mdmost.1
```

**Rust** — `cargo install mdmost`, or `cargo build --release` from a checkout. Neither
route installs a man page: `cargo install` does not handle man pages at all, and the page
is generated rather than shipped. Run `make man` in a checkout to build one; it needs
pandoc. Rust 2024 edition, and no system dependencies beyond a terminal that speaks ANSI
truecolour. The build needs no C compiler, which is why the regex engine behind the
highlighter is `fancy-regex` rather than oniguruma.

Two caveats. The **macOS** tarball binaries are neither signed nor notarised, so
Gatekeeper will quarantine them; `brew install` is the path of least resistance. The
**Windows** build compiles and is checked on every push but has never been exercised in
anger: expect the mouse, the clipboard and font detection to be less well behaved there
than on Unix.

