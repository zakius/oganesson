#!/usr/bin/env python3
"""Checks pack.sh's pruning of work/dl. Run: python3 linux/test_pack.py"""
import subprocess
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as tmp:
    dest = Path(tmp)
    versions = ['0.19.1.2-1.20261001000000', '0.18.3.1-1.20261006000000',
                '0.19.1.2-1.20261005000000', '0.19.2.1-1.20261007000000', '0.18.3.1-1.20260901000000']
    others = ['test-helium-0.19.1.2', '0.19.2.1-1.20261008000000.part', 'notes']
    for name in versions + others:
        (dest / name).mkdir()
    (dest / 'latest').symlink_to(versions[3])
    (dest / 'oganesson.deb').touch()
    subprocess.run(['bash', Path(__file__).parent / 'pack.sh', '--prune', dest], check=True)
    left = sorted(path.name for path in dest.iterdir())
    # The newest by commit time, not by name: 0.18.3.1's build of 6 October stays.
    kept = [versions[1], versions[2], versions[3]]
    assert left == sorted([*kept, *others, 'latest', 'oganesson.deb']), left
with tempfile.TemporaryDirectory() as tmp:
    # A repack of an older commit keeps its own folder, and the newest 2 others.
    dest = Path(tmp)
    names = ['0.19.1.2-1.20261001000000', '0.19.1.2-1.20261005000000',
             '0.19.2.1-1.20261007000000', '0.19.2.1-1.20261008000000']
    for name in names:
        (dest / name).mkdir()
    subprocess.run(['bash', Path(__file__).parent / 'pack.sh', '--prune', dest, names[0]], check=True)
    left = sorted(path.name for path in dest.iterdir())
    assert left == [names[0], names[2], names[3]], left
print('ok')
