#!/usr/bin/env bash
# Runs on the repository server for linux/publish-repo.sh, in DIR (default
# ~/pkgrepo): stages the repository of the packages in src/<version>/ in next/,
# with unsigned metadata, made in the packager images.
set -euo pipefail
cd "${1:-$HOME/pkgrepo}"
for format in deb rpm; do
    docker build -q -t "oganesson-$format-packager" -f "tools/$format.Dockerfile" tools > /dev/null
done
packager() {  # <docker run args>...
    docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/next:/repo" "$@"
}

rm -rf next
mkdir -p next/deb next/rpm
cp tools/oganesson.asc tools/oganesson.repo next/
# Every build's packages have the same file names, so the copies get the
# version folder's name.
for dir in src/*/; do
    version="$(basename "$dir")"
    ln "$dir"*.deb "next/deb/oganesson_${version}_amd64.deb"
    ln "$dir"*.rpm "next/rpm/oganesson-$version.x86_64.rpm"
done
packager -w /repo/deb oganesson-deb-packager sh -c '
    apt-ftparchive packages . > Packages && gzip -9k Packages &&
    apt-ftparchive -o APT::FTPArchive::Release::Origin=oganesson \
        -o APT::FTPArchive::Release::Label=oganesson release . > Release'
packager oganesson-rpm-packager createrepo_c --quiet /repo/rpm
