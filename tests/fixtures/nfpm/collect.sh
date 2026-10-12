#!/bin/sh
# collect.sh <directory> <out>: facts.sh for every package under <directory>,
# one folder per kind and architecture (deb-amd64, rpm-x86_64, ...).
set -eu
here=$(dirname "$0")
find "$1" -name '*.deb' -o -name '*.rpm' | sort | while read -r package; do
  name=$(basename "$package")
  case $name in
  *.deb) key=deb-${name##*_}; key=${key%.deb} ;;
  *.rpm) key=${name%.rpm}; key=rpm-${key##*.} ;;
  esac
  sh "$here/facts.sh" "$package" "$2/$key"
done
