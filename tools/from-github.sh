#!/usr/bin/env bash
# Has HOST download FILEs into its folder DIR from the GitHub release that already has them,
# so they aren't sent from here a second time: the uplink here is the slowest part of a
# release, and a server downloads from GitHub in seconds. A FILE's release is the tag "v" and
# the name of FILE's folder, as release.yml names it. The repository is private, so HOST gets
# GitHub's own download link for each file, which works for an hour, and never a token.
# HOST keeps a download only when its SHA-256 is the local file's, and gives it the local
# file's time, so that the caller's rsync skips it. The same rsync sends whatever this script
# couldn't get, as when a file isn't in a release or GitHub is out of reach, so this script
# reports such a file and doesn't fail.
# Usage: tools/from-github.sh HOST DIR FILE...
set -uo pipefail
cd "$(dirname "$0")/.." || exit
host="$1"
dir="$2"
shift 2
# shellcheck disable=SC2029  # the folder is meant to expand here
have="$(ssh "$host" "mkdir -p $dir && ls $dir")" || exit 0
token="${GH_TOKEN:-$(gh auth token)}"

{
    echo "cd $dir || exit"
    cat <<'REMOTE'
fetch() {  # SHA256 TIME NAME LINK
    if curl -fsSL -o "$3.part" "$4" && echo "$1  $3.part" | sha256sum --check --status; then
        touch -d "@$2" "$3.part"
        mv "$3.part" "$3"
        echo "$3: downloaded from the GitHub release"
    else
        rm -f "$3.part"
        echo "$3: no good download from the GitHub release"
    fi
}
REMOTE
    for file in "$@"; do
        name="$(basename "$file")"
        if grep -qxF "$name" <<< "$have"; then
            continue
        fi
        tag="v$(basename "$(dirname "$(realpath "$file")")")"
        asset="$(gh release view "$tag" --json assets --jq ".assets[] | select(.name == \"$name\") | .apiUrl")"
        if [ -z "$asset" ]; then
            echo "$name: not in a GitHub release $tag" >&2
            continue
        fi
        # The asset's address answers with a redirect to the download link.
        link="$(curl -fsS -o /dev/null -w '%{redirect_url}' -H @- -H 'Accept: application/octet-stream' "$asset" \
            <<< "Authorization: Bearer $token")"
        if [ -z "$link" ]; then
            echo "$name: no download link from GitHub" >&2
            continue
        fi
        printf 'fetch %s %s %q %q\n' "$(sha256sum < "$file" | cut -d ' ' -f 1)" "$(stat -c %.9Y "$file")" "$name" "$link"
    done
} | ssh "$host" bash
exit 0
