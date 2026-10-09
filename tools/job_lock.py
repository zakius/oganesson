#!/usr/bin/env python3
"""The job lock: one upgrade run at a time, held across separate commands of the run.

The lock file holds the owner, the start time and the timeout, or nothing when the lock is free.
A lock held past its start plus its timeout is stuck, and `acquire` takes it over; it prints whose
lock it took. An owner that acquires its own lock again renews it: the start becomes now. An
unreadable file counts as a stuck lock.
Each command reads and writes the file under a short flock, so two agents never both get the lock.

OWNER must be unique per run (the thread id): the same OWNER is the same holder.

Usage: tools/job_lock.py acquire OWNER [HOURS]   (default 12; exit 1 and print the holder when held)
       tools/job_lock.py release OWNER           (exit 1 when OWNER doesn't hold it)
       tools/job_lock.py status                  (exit 1 when held)
The file is work/.job.lock in this checkout; JOB_LOCK sets another path.
"""
import fcntl, json, os, sys, time
from contextlib import contextmanager
from pathlib import Path

PATH = Path(os.environ.get('JOB_LOCK', Path(__file__).resolve().parent.parent / 'work/.job.lock'))
DEFAULT_HOURS = 12


@contextmanager
def locked(path):
    """The lock's record (None when free) and a function that replaces it, under a flock."""
    with open(path, 'a+') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        text = f.read().strip()

        def write(record):
            f.truncate(0)
            f.write(json.dumps(record) + '\n' if record else '')
            f.flush()
            os.fsync(f.fileno())
        try:
            record = json.loads(text) if text else None
        except ValueError:
            record = {'owner': 'an unreadable lock file', 'start': 0, 'timeout': 0}
        yield record, write


def describe(record):
    start = time.strftime('%Y-%m-%d %H:%M', time.localtime(record['start']))
    return f"{record['owner']} since {start}, timeout {record['timeout'] / 3600:g} h"


def acquire(path, owner, hours=DEFAULT_HOURS, now=None):
    """(True, message) when OWNER holds the lock afterwards, else (False, holder)."""
    now = time.time() if now is None else now
    with locked(path) as (record, write):
        if record and record['owner'] != owner and now < record['start'] + record['timeout']:
            return False, f'held by {describe(record)}'
        write({'owner': owner, 'start': now, 'timeout': hours * 3600})
        if not record:
            return True, 'acquired'
        if record['owner'] == owner:
            return True, 'renewed'
        return True, f'took over a stuck lock: {describe(record)}'


def release(path, owner):
    with locked(path) as (record, write):
        if not record or record['owner'] != owner:
            return False, f'not held by {owner}: ' + (describe(record) if record else 'free')
        write(None)
        return True, 'released'


def status(path, now=None):
    now = time.time() if now is None else now
    with locked(path) as (record, _):
        if not record:
            return True, 'free'
        stuck = ' (stuck: acquire takes it over)' if now >= record['start'] + record['timeout'] else ''
        return False, f'held by {describe(record)}{stuck}'


if __name__ == '__main__':
    args = sys.argv[1:]
    if args[:1] == ['acquire'] and len(args) in (2, 3):
        hours = float(args[2]) if len(args) == 3 else DEFAULT_HOURS
        if not 0 < hours <= 1000:  # Also refuses nan.
            sys.exit(f'HOURS must be above 0 and at most 1000, not {args[2]}')
        ok, message = acquire(PATH, args[1], hours)
    elif args[:1] == ['release'] and len(args) == 2:
        ok, message = release(PATH, args[1])
    elif args == ['status']:
        ok, message = status(PATH)
    else:
        sys.exit(__doc__)
    print(f'job lock: {message}', file=sys.stdout if ok else sys.stderr)
    sys.exit(0 if ok else 1)
