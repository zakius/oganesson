#!/usr/bin/env bash
# Runs on the repository server for linux/publish-repo.sh, in DIR (default
# ~/pkgrepo): makes the .deb and .rpm of each src/<version>/*.tar.xz that has
# none in pool/ yet, and stages the repository in next/ with unsigned
# metadata. The packager images are the host's own architecture: the .deb's
# dependencies come from src/<version>/depends, found where the build was made.
set -euo pipefail
cd "${1:-$HOME/pkgrepo}"
for format in deb rpm; do
    docker build -q -t "oganesson-$format-packager" -f "tools/$format.Dockerfile" tools > /dev/null
done
packager() {  # <docker run args>...
    docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
        -v "$PWD/tools:/oganesson/linux/package:ro" "$@"
}

mkdir -p pool
for dir in pool/*/; do  # versions no longer uploaded
    [ -d "src/$(basename "$dir")" ] || rm -rf "$dir"
done
for dir in src/*/; do
    version="$(basename "$dir")"
    [ -e "pool/$version/done" ] && continue
    rm -rf "pool/$version"
    mkdir -p "pool/$version"
    tarball="$(cd "$dir" && ls -- *.tar.xz)"
    # <version> is the packages' version-release, as in linux/pack.sh.
    for format in deb rpm; do
        packager -e TARBALL="/src/$tarball" -e VERSION="${version%%-*}" \
            -e DEPENDS="$(cat "$dir/depends")" \
            -e PKG_RELEASE="${version#*-}" -e PACKAGES=/out \
            -v "$PWD/$dir:/src:ro" -v "$PWD/pool/$version:/out" "oganesson-$format-packager" \
            bash /oganesson/linux/package/package.sh / x86-64-v2 "$format"
    done
    touch "pool/$version/done"
done

rm -rf next
mkdir -p next/deb next/rpm
cp tools/oganesson.asc tools/oganesson.repo next/
# Every build's packages have the same file names, so the copies get the
# version folder's name.
for dir in pool/*/; do
    version="$(basename "$dir")"
    ln "$dir"*.deb "next/deb/oganesson_${version}_amd64.deb"
    ln "$dir"*.rpm "next/rpm/oganesson-$version.x86_64.rpm"
done
packager -v "$PWD/next:/repo" -w /repo/deb oganesson-deb-packager sh -c '
    apt-ftparchive packages . > Packages && gzip -9k Packages &&
    apt-ftparchive -o APT::FTPArchive::Release::Origin=oganesson \
        -o APT::FTPArchive::Release::Label=oganesson release . > Release'
packager -v "$PWD/next:/repo" oganesson-rpm-packager createrepo_c --quiet /repo/rpm
