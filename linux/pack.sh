#!/usr/bin/env bash
# Packs a built output folder for download into DEST/<version>: the .deb and .rpm packages and
# the tarball (oganesson-<version>-x86_64-x86-64-v2_linux.tar.xz), all three from the same
# stripped files and at the same time, made in the
# packager images (linux/package/deb.Dockerfile and rpm.Dockerfile). linux/publish-repo.sh
# uploads the packages. <version> is the packages' version-release; DEST/latest links to the one
# just packed.
# Usage: linux/pack.sh [OUT_DIR] [DEST]   (default: the release build, work/dl)
#        linux/pack.sh --prune DEST [KEEP]   (only the pruning below)
set -euo pipefail

# Keeps DEST's newest 3 version folders (<version>-1.<commit time>, ordered by
# the commit time), or KEEP and the newest 2 others, and leaves everything else
# in DEST alone.
prune() {
    local keep=3
    [ -n "${2:-}" ] && keep=2
    find "$1" -mindepth 1 -maxdepth 1 -type d -name '[0-9]*-1.[0-9]*' \
        ! -name '*.part' ! -name "${2:-.}" -printf '%f\n' \
        | sort -t- -k2 | head -n "-$keep" | while read -r old; do rm -rf "${1:?}/$old"; done
}
if [ "${1:-}" = --prune ]; then prune "$2" "${3:-}"; exit; fi
root="$(cd "$(dirname "$0")/.." && pwd -P)"
out="$(realpath "${1:-$root/work/helium-linux/build/src/out/Release}")"
dest="$(realpath -m "${2:-$root/work/dl}")"
# The packager images see the repository at /oganesson, so OUT_DIR must be in it.
case "$out" in "$root"/*) ;; *) echo "pack.sh: $out is outside $root" >&2; exit 1 ;; esac
stage="$(mktemp -d -p "$root/work")"
trap 'rm -rf "$stage"' EXIT
mkdir "$stage/packages"
# Each build's packages count as newer than the last: the commit time goes in
# the release field (1.YYYYMMDDHHMMSS, UTC), which apt, dnf and Discover compare.
release="1.$(TZ=UTC0 git -C "$root" log -1 --format=%cd --date=format-local:%Y%m%d%H%M%S)"
# The version is Chromium's own, as patches/helium-utils.patch makes the build's.
chromium="$(cat "$root/helium/chromium_version.txt")"
version="$chromium-$release"
packages="/oganesson/${stage#"$root"/}/packages"
for format in deb rpm; do
    docker build -q -t "oganesson-$format-packager" -f "$root/linux/package/$format.Dockerfile" \
        "$root/linux/package" > /dev/null
done
run=(docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e PKG_RELEASE="$release"
     -e PACKAGES="$packages" -v "$root:/oganesson")
tar="oganesson-$chromium-x86_64-x86-64-v2_linux.tar"
"${run[@]}" oganesson-rpm-packager bash /oganesson/linux/package/package.sh \
    "/oganesson/${out#"$root"/}" x86-64-v2 tar
# The tarball, the .rpm and the .deb at once, from the one tar: each compresses for over a
# minute, and its xz uses only a few threads.
run+=(-e TARBALL="$packages/$tar")
"${run[@]}" oganesson-rpm-packager bash /oganesson/linux/package/package.sh / x86-64-v2 tarball &
tarball=$!
"${run[@]}" oganesson-rpm-packager bash /oganesson/linux/package/package.sh / x86-64-v2 rpm &
rpm=$!
"${run[@]}" oganesson-deb-packager bash /oganesson/linux/package/package.sh / x86-64-v2 deb
wait "$tarball"
wait "$rpm"
rm "$stage/packages/$tar"

# DEST/<version> appears only once all the files are in it: they are copied
# to <version>.part first, so a full DEST keeps the old folders.
mkdir -p "$dest"
rm -rf "$dest/"[0-9]*-1.[0-9]*.part  # left by runs that failed here
cp -r "$stage/packages" "$dest/$version.part"
rm -rf "${dest:?}/$version"
mv "$dest/$version.part" "$dest/$version"
ln -sfn "$version" "$dest/latest"
prune "$dest" "$version"
ls -la "$dest" "$dest/$version"
