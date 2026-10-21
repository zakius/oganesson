#!/bin/sh
# Holds releases while several tasks are landing on main, so only the last one releases.
#   tools/release-hold.sh add NAME...   NAME is still to land: pushes to main release nothing
#   tools/release-hold.sh done NAME     NAME has landed; if it was the last, start the release
#   tools/release-hold.sh               list what is held for
# The list is the RELEASE_HOLD repository variable, which .github/workflows/release.yml reads.
# ponytail: read-modify-write without a lock; two tasks finishing within seconds could drop a
# name, so check the list afterwards.
set -eu
held="$(gh variable get RELEASE_HOLD 2>/dev/null || true)"
case "${1:-}" in
    add)
        shift
        gh variable set RELEASE_HOLD --body "$(printf '%s\n' $held "$@" | sort -u | tr '\n' ' ' | sed 's/ $//')"
        ;;
    done)
        left="$(printf '%s\n' $held | grep -vxF "$2" | tr '\n' ' ' | sed 's/ $//' || true)"
        if [ -n "$left" ]; then
            gh variable set RELEASE_HOLD --body "$left"
            echo "release still held for: $left"
        else
            gh variable delete RELEASE_HOLD 2>/dev/null || true
            gh workflow run release.yml --ref main
            echo "last task landed; release started"
        fi
        exit 0
        ;;
    '') ;;
    *) echo "usage: $0 [add NAME... | done NAME]" >&2; exit 2 ;;
esac
gh variable get RELEASE_HOLD 2>/dev/null || echo "nothing held"
