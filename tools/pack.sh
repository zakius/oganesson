#!/usr/bin/env bash
# Packs a built output folder's runtime files as a stripped .tar.xz (LZMA2)
# for download: oganesson-<commit>-linux-x64.tar.xz in DEST/<version>, and
# the same build as .deb and .rpm packages and the tarball they are made from
# (oganesson-<version>-x86_64-x86-64-v2_linux.tar.xz, which
# tools/publish-repo.sh uploads), made in the packager image
# (tools/package/Dockerfile, tagged oganesson-packager). <version> is the
# packages' version-release; DEST/latest links to the one just packed.
# Usage: tools/pack.sh [OUT_DIR] [DEST]   (default: the release build, work/dl)
#        tools/pack.sh --prune DEST [KEEP]   (only the pruning below)
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
# The packager image sees the repository at /oganesson, so OUT_DIR must be in it.
case "$out" in "$root"/*) ;; *) echo "pack.sh: $out is outside $root" >&2; exit 1 ;; esac
name="oganesson-$(git -C "$root" rev-parse --short HEAD)-linux-x64"

stage="$(mktemp -d -p "$root/work")"
trap 'rm -rf "$stage"' EXIT
mkdir "$stage/$name"
cd "$out"
# What the browser needs to start (tools/package/package.sh's set): a missing
# one fails before the previous archive goes.
cp -a oganesson oganesson_crashpad_handler chrome_100_percent.pak chrome_200_percent.pak \
    resources.pak icudtl.dat v8_context_snapshot.bin libEGL.so libGLESv2.so \
    libvk_swiftshader.so libvulkan.so.1 vk_swiftshader_icd.json liboganesson_sync.so \
    product_logo_256.png locales "$stage/$name/"
# Whatever else the build made, such as the Qt shims.
for file in chrome-wrapper ./*.so ./*.so.[0-9] ./*.pak ./*.bin resources hyphen-data \
    IwaKeyDistribution; do
    if [ -e "$file" ]; then cp -a "$file" "$stage/$name/"; fi
done
cp "$root/resources/oganesson.desktop" "$stage/$name/"
find "$stage/$name" -maxdepth 1 -type f \( -name oganesson -o -name oganesson_crashpad_handler \
    -o -name '*.so' -o -name '*.so.[0-9]' \) -exec strip --strip-debug {} +

mkdir "$stage/packages"
# Each build's packages count as newer than the last: the commit time goes in
# the release field (1.YYYYMMDDHHMMSS, UTC), which apt, dnf and Discover compare.
release="1.$(TZ=UTC0 git -C "$root" log -1 --format=%cd --date=format-local:%Y%m%d%H%M%S)"
version="$(python3 "$root/utils/helium_version.py" --tree "$root" --platform-tree "$root/linux" \
    --print)-$release"
tar -C "$stage" -cf - "$name" | xz -T0 -9 > "$stage/packages/$name.tar.xz"
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -e PKG_RELEASE="$release" -e PACKAGES="/oganesson/${stage#"$root"/}/packages" -v "$root:/oganesson" oganesson-packager \
    bash /oganesson/tools/package/package.sh "/oganesson/${out#"$root"/}" x86-64-v2 tarball deb rpm

# DEST/<version> appears only once all the files are in it: they are copied
# to <version>.part first, so a full DEST keeps the old folders.
mkdir -p "$dest"
rm -rf "$dest/"[0-9]*-1.[0-9]*.part  # left by runs that failed here
cp -r "$stage/packages" "$dest/$version.part"
rm -rf "${dest:?}/$version"
mv "$dest/$version.part" "$dest/$version"
ln -sfn "$version" "$dest/latest"
# Packages directly in DEST are from pack.sh runs before version folders.
find "$dest" -maxdepth 1 \( -name 'oganesson*.deb' -o -name 'oganesson*.rpm' \
    -o -name 'oganesson-*-linux-x64.tar.xz' -o -name 'oganesson*.part' \) -delete
prune "$dest" "$version"
ls -la "$dest" "$dest/$version"
