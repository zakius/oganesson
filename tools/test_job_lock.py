#!/usr/bin/env python3
"""Checks job_lock.py's acquire, release and takeover rules. Run: python3 tools/test_job_lock.py"""
import tempfile
from pathlib import Path
from job_lock import acquire, release, status

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / '.job.lock'
    assert status(path, now=0)[0]
    assert acquire(path, 'run-a', hours=1, now=0) == (True, 'acquired')
    ok, message = acquire(path, 'run-b', now=3599)
    assert not ok and message.startswith('held by run-a'), message
    assert acquire(path, 'run-a', hours=1, now=3000) == (True, 'renewed')
    assert not acquire(path, 'run-b', now=3600)[0], 'a renewed lock runs from its new start'
    assert not status(path, now=3600)[0]
    assert not release(path, 'run-b')[0]
    ok, message = acquire(path, 'run-b', hours=2, now=6600)
    assert ok and message.startswith('took over a stuck lock: run-a'), message
    assert not release(path, 'run-a')[0]
    assert release(path, 'run-b') == (True, 'released')
    assert status(path, now=0) == (True, 'free')
    path.write_text('garbage')
    ok, message = acquire(path, 'run-c', now=0)
    assert ok and message.startswith('took over a stuck lock: an unreadable'), message
print('ok')
