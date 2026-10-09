#!/usr/bin/env python3
"""Keeps the build incremental across a re-prepared source tree.

A re-prepare (container-build.sh's reset_tree, then the patches) rewrites
every file a patch, substitution or copy touched, mostly with the same
contents, and the new modification times make the build recompile nearly
everything. `save` records the content hash and time of every file the
prepared tree changed; `restore`, after the next prepare, gives each file
whose contents came out the same its old time back, so only files that really
changed rebuild.

Usage: tools/keep_mtimes.py save SRC MANIFEST
       tools/keep_mtimes.py restore SRC MANIFEST
"""
import hashlib, os, subprocess, sys
from pathlib import Path

# Unpacked downloads that reset_tree deletes and unpacks again.
UNPACKED = ('third_party/ublock', 'components/helium_onboarding',
            'third_party/search_engines_data/resources_internal')


def changed_files(src):
    """Files of the prepared tree that differ from the fetched sources."""
    # The checkouts reset_tree resets, found the way it finds them.
    found = subprocess.run(['find', '.', '-path', './out', '-prune', '-o', '-path',
                            './uc_staging', '-prune', '-o', '-name', '.git', '-print'],
                           cwd=src, capture_output=True, text=True, check=True).stdout
    for git_dir in found.split():
        repo = (src / git_dir).parent
        for args in (('diff', '--name-only', '-z', '--diff-filter=M'),
                     ('ls-files', '-z', '--others', '--exclude-standard')):
            out = subprocess.run(['git', '-C', str(repo), *args], capture_output=True,
                                 check=True).stdout
            for name in filter(None, out.decode().split('\0')):
                yield repo / name
    for folder in UNPACKED:
        path = src / folder
        if path.is_dir():
            yield from (p for p in path.rglob('*') if p.is_file())


def digest(path):
    return hashlib.sha1(path.read_bytes()).hexdigest()


def save(src, manifest):
    with open(manifest, 'w') as out:
        for path in changed_files(src):
            if path.is_file() and not path.is_symlink():
                out.write(f'{path.relative_to(src)}\t{path.stat().st_mtime_ns}\t{digest(path)}\n')


def restore(src, manifest):
    kept = 0
    for line in Path(manifest).read_text().splitlines():
        name, mtime, sha = line.split('\t')
        path = src / name
        if path.is_file() and digest(path) == sha:
            os.utime(path, ns=(int(mtime), int(mtime)))
            kept += 1
    print(f'keep_mtimes: {kept} unchanged files keep their times')


if __name__ == '__main__':
    if len(sys.argv) != 4 or sys.argv[1] not in ('save', 'restore'):
        sys.exit(__doc__)
    (save if sys.argv[1] == 'save' else restore)(Path(sys.argv[2]), sys.argv[3])
