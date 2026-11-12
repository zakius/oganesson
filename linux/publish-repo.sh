#!/usr/bin/env bash
# Publishes DL's version folders (linux/pack.sh keeps the newest 3) as a signed
# apt repository (deb/, flat) and dnf repository (rpm/) at https://REPO_DOMAIN.
# Each folder's .deb and .rpm go to REPO_TARGET (HOST:DIR), where rsync sends
# only the new ones; linux/package/repo-build.sh makes the metadata there, and
# it comes back here to be signed. DIR/www is served by
# linux/package/repo-compose.yaml. Machines set up with docs/packages.md update
# from it with their normal system updates.
# REPO_DOMAIN and REPO_TARGET come from the environment or from
# ~/.local/share/oganesson-repo/repo.env. The signing key lives only in
# GNUPGHOME (default ~/.local/share/oganesson-repo/gnupg).
# Usage: linux/publish-repo.sh [DL]   (default: work/dl)
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
dl="$(realpath "${1:-$root/work/dl}")"
config="$HOME/.local/share/oganesson-repo"
if [ -f "$config/repo.env" ]; then
    # shellcheck source=/dev/null
    . "$config/repo.env"
fi
: "${REPO_DOMAIN:?set it in $config/repo.env, e.g. packages.example.org}"
target="${REPO_TARGET:?set it in $config/repo.env, e.g. myserver:pkgrepo}"
host="${target%%:*}"
dir="${target#*:}"
export GNUPGHOME="${GNUPGHOME:-$config/gnupg}"
key="$(gpg --list-secret-keys --with-colons 'oganesson packages' | awk -F: '/^fpr/ { print $10; exit }')"
[ -n "$key" ] || { echo "publish-repo.sh: no signing key in $GNUPGHOME" >&2; exit 1; }

# repo-build.sh can run for minutes without output, as when it builds the
# packager images; without keepalives the cloud network drops the idle
# connection and ssh waits on it forever.
keepalive=(-o ServerAliveInterval=15 -o ServerAliveCountMax=8)

upload="$root/work/repo-upload"
rm -rf "$upload"
mkdir -p "$upload/src" "$upload/tools"
for version in "$dl"/[0-9]*-1.[0-9]*/; do
    case "$version" in *.part/) continue ;; esac
    mkdir "$upload/src/$(basename "$version")"
    ln "$version"oganesson_*.deb "$version"oganesson-*.rpm "$upload/src/$(basename "$version")/"
done
cp -a "$root/linux/package/." "$upload/tools/"
gpg --armor --export "$key" > "$upload/tools/oganesson.asc"
cat > "$upload/tools/oganesson.repo" <<REPO
[oganesson]
name=oganesson
baseurl=https://$REPO_DOMAIN/rpm
enabled=1
# The packages aren't signed; the signed repodata carries their checksums.
gpgcheck=0
repo_gpgcheck=1
gpgkey=https://$REPO_DOMAIN/oganesson.asc
# dnf keeps metadata for 48 hours by default; builds come out several times a day.
metadata_expire=1h
REPO
ssh "${keepalive[@]}" "$host" mkdir -p "$dir"
rsync -a --delete -e "ssh ${keepalive[*]}" "$upload/src" "$upload/tools" "$target/"
ssh "${keepalive[@]}" "$host" "cd $dir && cp tools/repo-compose.yaml compose.yaml &&
    echo REPO_DOMAIN=$REPO_DOMAIN > .env && docker compose up -d --quiet-pull"
ssh "${keepalive[@]}" "$host" bash "$dir/tools/repo-build.sh" "$dir"

sign="$root/work/repo-sign"
rm -rf "$sign"
mkdir -p "$sign"
scp -q "${keepalive[@]}" "$target/next/deb/Release" "$target/next/rpm/repodata/repomd.xml" "$sign/"
gpg --batch --yes -u "$key" --clearsign -o "$sign/InRelease" "$sign/Release"
gpg --batch --yes -u "$key" -abs -o "$sign/Release.gpg" "$sign/Release"
gpg --batch --yes -u "$key" --detach-sign --armor -o "$sign/repomd.xml.asc" "$sign/repomd.xml"
scp -q "${keepalive[@]}" "$sign/InRelease" "$sign/Release.gpg" "$target/next/deb/"
scp -q "${keepalive[@]}" "$sign/repomd.xml.asc" "$target/next/rpm/repodata/"
ssh "${keepalive[@]}" "$host" "cd $dir && rsync -a --delete --delay-updates next/ www/ && ls www/deb/*.deb"
