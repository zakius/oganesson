#!/usr/bin/env bash
# Runs a long command in the background, detached from the calling shell and
# agent session, so it survives both. LOG gets its output and, once it ends,
# a last line "EXIT <status>" (or "EXIT stopped"); LOG.pid holds its process
# group id.
#
#   tools/detach.sh LOG -- COMMAND...   start (prints the pid)
#   tools/detach.sh --wait LOG [SECS]   block until it ends (default 4 h) and print
#                                       the EXIT line; exit 1 if it still runs
#   tools/detach.sh --stop LOG          stop it and everything it started
set -euo pipefail

ended() { tail -n 1 "$1" 2>/dev/null | grep -q '^EXIT '; }
# The job's process group still has a member. A stale pid file can't match a
# stranger's group for long: the job's own LOG ends in EXIT once it is gone.
running() { kill -0 -- -"$(cat "$1.pid")" 2>/dev/null; }

case "${1:-}" in
--wait)
    log="$2"
    deadline=$((SECONDS + ${3:-14400}))
    while ! ended "$log" && running "$log" && [ $SECONDS -lt $deadline ]; do
        sleep 5
    done
    if ended "$log"; then
        tail -n 1 "$log"
    else
        echo "detach.sh: $log has no EXIT line yet; still running: $(running "$log" && echo yes || echo no)" >&2
        exit 1
    fi
    ;;
--stop)
    log="$2"
    ended "$log" && { tail -n 1 "$log"; exit 0; }
    pid="$(cat "$log.pid")"
    kill -- -"$pid" 2>/dev/null || true
    for _ in $(seq 60); do running "$log" || break; sleep 1; done
    kill -9 -- -"$pid" 2>/dev/null || true
    while running "$log"; do sleep 1; done
    # Every process of the group is gone: nothing else writes LOG any more.
    echo "EXIT stopped" >> "$log"
    ;;
*)
    log="$1"
    [ "${2:-}" = -- ] || { echo "usage: tools/detach.sh LOG -- COMMAND..." >&2; exit 2; }
    shift 2
    : > "$log"
    # setsid makes the job its own process group, which --stop ends as a whole.
    # Appending (>>) keeps a late writer from overwriting the EXIT line.
    setsid bash -c '"$@" >> "$0" 2>&1; status=$?; echo "EXIT $status" >> "$0"' \
        "$log" "$@" < /dev/null > /dev/null 2>&1 &
    echo $! > "$log.pid"
    cat "$log.pid"
    ;;
esac
