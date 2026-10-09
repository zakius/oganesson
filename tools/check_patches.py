#!/usr/bin/env python3
"""Apply the whole series to a sparse Chromium checkout at the pinned version, zero fuzz.

Only the files the patches touch are checked out. When the prepared tree in work/ already holds
the pinned commit of a checkout, its git objects are borrowed and nothing is downloaded;
otherwise only those files are fetched, which takes minutes.
A failing patch doesn't stop the run: its hunks that fit are applied, so the patches after it see
as much of it as they can, and the end lists every failing patch with the hunks patch reported.
Usage: tools/check_patches.py [--chromium URL_OR_LOCAL_CLONE] [--keep DIR]
"""
import argparse, re, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASES = (ROOT / 'patches', ROOT / 'linux/patches', ROOT / 'late')


def git(*args):
    subprocess.run(['git', *args], check=True)


def series(base):
    return [l.strip() for l in (base / 'series').read_text().splitlines()
            if l.strip() and not l.startswith('#')]


def touched(text):
    return re.findall(r'^--- a/(\S+)', text, re.M)


def local_commit(repo, ref):
    """ref's commit in the local checkout repo, if it has it."""
    r = subprocess.run(['git', '-C', str(repo), 'rev-parse', '-q', '--verify', f'{ref}^{{commit}}'],
                       capture_output=True, text=True)
    return r.stdout.strip() if (repo / '.git').exists() and r.returncode == 0 else None


def sparse_clone(url, ref, dest, files, local=None):
    git('init', '--quiet', str(dest))
    subprocess.run(['git', '-C', str(dest), 'sparse-checkout', 'set', '--no-cone', '--stdin'],
                   input='\n'.join(files) + '\n', text=True, check=True)
    commit = local and local_commit(local, ref)
    if commit:
        # Borrow the local checkout's objects. Marked shallow, like a fetched checkout, so
        # history stops at this commit (series_report.py resets to the root commit).
        objects = subprocess.run(['git', '-C', str(local), 'rev-parse', '--path-format=absolute',
                                  '--git-common-dir'], capture_output=True, text=True,
                                 check=True).stdout.strip() + '/objects'
        (dest / '.git/objects/info/alternates').write_text(objects + '\n')
        (dest / '.git/shallow').write_text(commit + '\n')
        git('-C', str(dest), 'checkout', '--quiet', commit)
        return
    origin = Path(url)
    git('-C', str(dest), 'remote', 'add', 'origin', str(origin.resolve()) if origin.is_dir() else url)
    git('-C', str(dest), 'fetch', '--quiet', '--depth=1', '--filter=blob:none', 'origin', ref)
    git('-C', str(dest), 'checkout', '--quiet', 'FETCH_HEAD')


def apply_series(src, fuzz=0):
    """Applies the series in order as utils/patches.py does, without stopping at a failure.

    Returns (patch, patch's output) for each patch that doesn't apply.
    """
    failed = []
    for base in BASES:
        for entry in series(base):
            path = base / entry
            cmd = ['patch', '-p1', '--ignore-whitespace', '--forward', f'--fuzz={fuzz}',
                   '--no-backup-if-mismatch', '-i', str(path), '-d', str(src)]
            check = subprocess.run(cmd + ['--dry-run'], capture_output=True, text=True)
            if check.returncode == 0:
                subprocess.run(cmd + ['--silent'], check=True)
                continue
            failed.append((path, check.stdout + check.stderr))
            # 1: some hunks failed. 2 (a malformed patch, a missing file) applies nothing.
            if check.returncode == 1:
                subprocess.run(cmd + ['--reject-file=-'], capture_output=True)
    return failed


def report(failed):
    total = sum(len(series(b)) for b in BASES)
    print(f'{total - len(failed)} of {total} patches apply with zero fuzz; {len(failed)} fail')
    for path, output in failed:
        print(f'FAILED {path.relative_to(ROOT)}')
        print(*('  ' + line for line in output.splitlines()), sep='\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--chromium', help='Chromium source to check against (default: the prepared '
                    "tree if it's at the pinned version, else googlesource)")
    ap.add_argument('--keep', help='unpack into this directory instead of a temp one')
    args = ap.parse_args()
    version = (ROOT / 'chromium_version.txt').read_text().strip()
    paths = sorted({p for b in BASES for e in series(b) for p in touched((b / e).read_text())})
    tmp = tempfile.TemporaryDirectory()
    work = Path(args.keep or tmp.name)
    src, cache = work / 'src', work / 'cache'
    cache.mkdir(parents=True, exist_ok=True)
    # The prepared tree's objects are borrowed only when no source is given.
    tree = None if args.chromium else ROOT / 'work/helium-linux/build/src'
    chromium = args.chromium or 'https://chromium.googlesource.com/chromium/src.git'
    sparse_clone(chromium, version, src, ['DEPS', *paths], tree)
    deps = (src / 'DEPS').read_text()
    for folder, url, key in (
            ('third_party/boringssl/src', 'https://boringssl.googlesource.com/boringssl',
             r"'boringssl_revision': '([0-9a-f]+)'"),
            ('third_party/devtools-frontend/src',
             'https://chromium.googlesource.com/devtools/devtools-frontend',
             r"'devtools_frontend_revision': '([0-9a-f]+)'"),
            ('third_party/skia', 'https://skia.googlesource.com/skia.git',
             r"'skia_revision': '([0-9a-f]+)'"),
            ('third_party/search_engines_data/resources',
             'https://chromium.googlesource.com/external/search_engines_data',
             r"'src/third_party/search_engines_data/resources':.*?'([0-9a-f]{40})'")):
        files = [p.removeprefix(folder + '/') for p in paths if p.startswith(folder + '/')]
        if files:
            sparse_clone(url, re.search(key, deps, re.S).group(1), src / folder, files,
                         tree and tree / folder)
    for action, extra in (('retrieve', []), ('unpack', [str(src)])):
        subprocess.run([str(ROOT / 'utils/downloads.py'), action, '-i', str(ROOT / 'deps.ini'),
                        '-c', str(cache), *extra, '--components', 'ublock_origin', 'onboarding'],
                       check=True)
    # Our new files, which the patches then hook in.
    shutil.copytree(ROOT / 'src', src, dirs_exist_ok=True)
    failed = apply_series(src)
    report(failed)
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
