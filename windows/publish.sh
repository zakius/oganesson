#!/usr/bin/env bash
# Publishes the newest Windows packages (./oganesson.py build --windows puts them
# in work/dl/windows/VERSION/) to WINDOWS_TARGET (HOST:DIR, default
# oracle:dubna/www/windows), where dubna's site lists them at
# https://dubna.zakius.xyz/windows/. The unversioned names the install page links
# to become hard links to the newest version, and SHA256SUMS covers every file
# there, under both names, so `sha256sum -c` works on whichever was downloaded.
# Usage: windows/publish.sh [VERSION_DIR]
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
dir="${1:-$(find "$root/work/dl/windows" -mindepth 1 -maxdepth 1 -type d -name '[0-9]*' | sort -V | tail -1)}"
target="${WINDOWS_TARGET:-oracle:dubna/www/windows}"
host="${target%%:*}"
path="${target#*:}"
zip="$(cd "$dir" && ls oganesson-*-windows-x64.zip)"
name="${zip%.zip}"
[ -f "$dir/$name-installer.exe" ] || { echo "publish.sh: no $name-installer.exe in $dir" >&2; exit 1; }

ssh "$host" mkdir -p "$path"
rsync -a --partial "$dir/$zip" "$dir/$name-installer.exe" "$target/"
# shellcheck disable=SC2029  # the names are meant to expand here
ssh "$host" "cd $path &&
    ln -f $name.zip oganesson-windows-x64.zip &&
    ln -f $name-installer.exe oganesson-windows-x64-installer.exe &&
    sha256sum oganesson-*.exe oganesson-*.zip > SHA256SUMS.new && mv SHA256SUMS.new SHA256SUMS &&
    cat SHA256SUMS"
