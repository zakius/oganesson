#!/usr/bin/env bash
# Publishes the newest Windows packages (./oganesson.py build --windows puts them
# in work/dl/windows/VERSION/) to WINDOWS_TARGET (HOST:DIR, from the environment
# or the repository's .env, which Git ignores), where dubna's site lists them at
# https://dubna.zakius.xyz/windows/. The unversioned names the install page links
# to become hard links to the newest version, and SHA256SUMS covers every file
# there, under both names, so `sha256sum -c` works on whichever was downloaded.
# The updater's feed, appcast.xml, offers the update, with its ed25519 signature
# by WINDOWS_UPDATE_KEY, the private key windows/update-key.pem pairs with.
# SHA256SUMS.sig is that key's signature of SHA256SUMS, for a first download:
#   openssl pkeyutl -verify -pubin -inkey update-key.pem -rawin -in SHA256SUMS -sigfile SHA256SUMS.sig
# The host keeps the newest 3 versions, and work/dl/windows the newest 3 (linux/pack.sh --prune).
# Usage: windows/publish.sh [VERSION_DIR]
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
dir="${1:-$(find "$root/work/dl/windows" -mindepth 1 -maxdepth 1 -type d -name '[0-9]*' | sort -V | tail -1)}"
[ -d "$dir" ] || { echo "publish.sh: no version folder to publish (${dir:-none in work/dl/windows})" >&2; exit 1; }
# shellcheck source=/dev/null
[ -f "$root/.env" ] && . "$root/.env"
target="${WINDOWS_TARGET:?set it in $root/.env, e.g. WINDOWS_TARGET=myserver:dubna/www/windows}"
key="${WINDOWS_UPDATE_KEY:?set it in $root/.env: the private key windows/update-key.pem pairs with}"
host="${target%%:*}"
path="${target#*:}"
zip="$(cd "$dir" && ls oganesson-*-windows-x64.zip)"
name="${zip%.zip}"
version="${name#oganesson-}"
version="${version%-windows-x64}"
update="$name-update.exe"
for file in "$name-installer.exe" "$update"; do
    [ -f "$dir/$file" ] || { echo "publish.sh: no $file in $dir" >&2; exit 1; }
done
# A key the browsers don't have would make them refuse every update.
cmp -s <(openssl pkey -in "$key" -pubout) "$root/windows/update-key.pem" ||
    { echo "publish.sh: $key isn't the private key of windows/update-key.pem" >&2; exit 1; }
sign() { openssl pkeyutl -sign -inkey "$key" -rawin -in "$1"; }

# WinSparkle's appcast, as Helium's: the version is the one the browser reports.
appcast="$(mktemp)"
sums="$(mktemp)"
trap 'rm -f "$appcast" "$sums"' EXIT
cat > "$appcast" <<EOF
<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
  <channel>
    <title>oganesson</title>
    <item>
      <title>$version</title>
      <sparkle:version>$version</sparkle:version>
      <sparkle:minimumSystemVersion>10.0</sparkle:minimumSystemVersion>
      <enclosure
        url="https://dubna.zakius.xyz/windows/$update"
        sparkle:os="windows-x64"
        sparkle:edSignature="$(sign "$dir/$update" | base64 -w0)"
        length="$(stat -c %s "$dir/$update")"
        type="application/octet-stream"/>
    </item>
  </channel>
</rss>
EOF

ssh "$host" mkdir -p "$path"
rsync -a --partial "$dir/$zip" "$dir/$name-installer.exe" "$dir/$update" "$target/"
rsync -a "$root/windows/update-key.pem" "$target/"
# The feed after its update, so it never offers a file the host doesn't have yet.
rsync "$appcast" "$target/appcast.xml"
# shellcheck disable=SC2029  # the names are meant to expand here
ssh "$host" "cd $path && chmod 644 appcast.xml &&
    ln -f $name.zip oganesson-windows-x64.zip &&
    ln -f $name-installer.exe oganesson-windows-x64-installer.exe &&
    ls oganesson-*-windows-x64.zip | grep -v '^oganesson-windows-' | sort -V | head -n -3 |
        while read -r old; do rm -f \"\$old\" \"\${old%.zip}-installer.exe\" \"\${old%.zip}-update.exe\"; done &&
    sha256sum oganesson-*.exe oganesson-*.zip > SHA256SUMS.new && mv SHA256SUMS.new SHA256SUMS &&
    cat SHA256SUMS" | tee "$sums"
sign "$sums" | ssh "$host" "cat > $path/SHA256SUMS.sig.new && mv $path/SHA256SUMS.sig.new $path/SHA256SUMS.sig"
"$root/linux/pack.sh" --prune "$root/work/dl/windows" "$(basename "$dir")"
