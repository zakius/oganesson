#!/usr/bin/env python3
"""Apply the whole series to a sparse Chromium checkout at the pinned version, zero fuzz: the Linux
build's (oganesson.SERIES), then the Windows build's (oganesson.WINDOWS_SERIES) to a copy.

Only the files the patches touch are checked out. When the prepared tree in work/ already holds
the pinned commit of a checkout, its git objects are borrowed and nothing is downloaded;
otherwise only those files are fetched, which takes minutes.
A failing patch doesn't stop the run: its hunks that fit are applied, so the patches after it see
as much of it as they can, and the end lists each series' failing patches with the hunks patch
reported. --keep DIR keeps the Linux tree in DIR/src and the Windows tree in DIR/src-windows,
which regen.py and regen.py --windows work on.

--chromium-version VERSION checks against another Chromium tag, the next milestone's beta (dubna
docs/nightly.md, "Next milestone"). The upstreams' patches are still the current milestone's, so
they are applied with fuzz 2, and some of them still fail: the report names those apart, and only
our failing patches, at zero fuzz, set the exit status.
Usage: tools/check_patches.py [--chromium URL_OR_LOCAL_CLONE] [--chromium-version VERSION]
                              [--keep DIR]
"""
import argparse, re, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import oganesson  # pylint: disable=wrong-import-position
BASES = oganesson.SERIES


# What clone.py's gclient config pins in place of DEPS (patches/helium-utils.patch): commits DEPS
# names that the mirror lacks.
MIRROR_PINS = {
    'third_party/search_engines_data/resources': 'effde84e73491653b245b68ac65835ad2fc4e1de',
}


def git(*args):
    subprocess.run(['git', *args], check=True)


def series(base):
    # helium-windows' without what windows/container-build.sh leaves out.
    drops = (oganesson.drops(oganesson.WINDOWS_DROPS)
             if base == oganesson.HELIUM_WINDOWS / 'patches' else set())
    return [l.strip() for l in (base / 'series').read_text().splitlines()
            if l.strip() and not l.startswith('#') and l.strip() not in drops]


def touched(text):
    return re.findall(r'^--- a/(\S+)', text, re.M)


def local_commit(repo, ref):
    """ref's commit in the local checkout repo, if it has it."""
    r = subprocess.run(['git', '-C', str(repo), 'rev-parse', '-q', '--verify', f'{ref}^{{commit}}'],
                       capture_output=True, text=True)
    return r.stdout.strip() if (repo / '.git').exists() and r.returncode == 0 else None


def tag_commit(url, tag):
    """The commit of url's tag, which a checkout gclient synced has without the tag, or None
    when the remote doesn't answer: the files are then fetched."""
    try:
        r = subprocess.run(['git', 'ls-remote', url, f'refs/tags/{tag}', f'refs/tags/{tag}^{{}}'],
                           capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return None
    # An annotated tag's commit is on its peeled ^{} line, the last one.
    lines = r.stdout.split()
    return lines[-2] if r.returncode == 0 and lines else None


def sparse_clone(url, ref, dest, files, local=None):
    shutil.rmtree(dest, ignore_errors=True)  # a kept tree from an earlier run has an origin and patched files
    git('init', '--quiet', str(dest))
    subprocess.run(['git', '-C', str(dest), 'sparse-checkout', 'set', '--no-cone', '--stdin'],
                   input='\n'.join(files) + '\n', text=True, check=True)
    commit = local and local_commit(local, ref)
    # A dependency's ref is already a commit; Chromium's is its version tag.
    if local and not commit and not re.fullmatch(r'[0-9a-f]{40}', ref):
        tagged = tag_commit(url, ref)
        commit = tagged and local_commit(local, tagged)
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


UPSTREAM = (oganesson.TREE / 'patches', oganesson.HELIUM_LINUX / 'patches',
            oganesson.HELIUM_WINDOWS / 'patches')


def apply_series(src, fuzz=0, bases=BASES, upstream_fuzz=None):
    """Applies the series in order as utils/patches.py does, without stopping at a failure.
    upstream_fuzz, when given, is the fuzz for the upstreams' patches (UPSTREAM) instead.

    Returns (patch, patch's output) for each patch that doesn't apply.
    """
    failed = []
    for base in bases:
        base_fuzz = fuzz if upstream_fuzz is None or base not in UPSTREAM else upstream_fuzz
        for entry in series(base):
            path = base / entry
            cmd = ['patch', '-p1', '--ignore-whitespace', '--forward', f'--fuzz={base_fuzz}',
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


def report(failed, bases=BASES):
    total = sum(len(series(b)) for b in bases)
    print(f'{total - len(failed)} of {total} patches apply with zero fuzz; {len(failed)} fail')
    for path, output in failed:
        print(f'FAILED {path.relative_to(ROOT)}')
        print(*('  ' + line for line in output.splitlines()), sep='\n')


def failed_files(output):
    """The files in which patch's output reports a failed hunk, or which it can't find (it then
    quotes the section's '--- a/' line after a '|')."""
    files, current = set(), None
    for line in output.splitlines():
        missing = re.match(r'\|--- a/(\S+)', line)
        if line.startswith('checking file '):
            current = line.removeprefix('checking file ')
        elif re.match(r'Hunk #\d+ FAILED', line) and current:
            files.add(current)
        elif missing:
            files.add(missing.group(1))
    return files


def report_next(failed, bases):
    """report() for a check against the next milestone: our failing patches in full, each with
    the files of its failed hunks in which an upstream patch failed too (how the upstream rebases
    that patch decides those hunks' context), and the upstreams' failing patches by name."""
    def upstream(path):
        return any(base in path.parents for base in UPSTREAM)
    ours = [(path, output) for path, output in failed if not upstream(path)]
    theirs = [path for path, _ in failed if upstream(path)]
    upstream_files = {f for path, output in failed if upstream(path)
                      for f in failed_files(output)}
    total = sum(len(series(b)) for b in bases if b not in UPSTREAM)
    print(f'{total - len(ours)} of {total} of our patches apply with zero fuzz; {len(ours)} fail; '
          f'{len(theirs)} upstream patches fail')
    for path, output in ours:
        print(f'FAILED {path.relative_to(ROOT)}')
        shared = sorted(failed_files(output) & upstream_files)
        if shared:
            print(f'  an upstream patch failed in these files too: {", ".join(shared)}')
        print(*('  ' + line for line in output.splitlines()), sep='\n')
    for path in theirs:
        print(f'UPSTREAM {path}')
    return ours


def drops_still_used():
    """Files a dropped Helium or helium-windows patch creates that a patch its build carries still
    names (a build file listing it, an include): the build would fail on them. A file whose
    name many folders have (BUILD.gn) is looked for by its folder."""
    problems = []
    for drops, patches, bases in ((oganesson.DROPS, oganesson.HELIUM / 'patches', BASES),
                                  (oganesson.WINDOWS_DROPS, oganesson.HELIUM_WINDOWS / 'patches',
                                   oganesson.WINDOWS_SERIES)):
        added = '\n'.join(l for b in bases for e in series(b)
                          for l in (b / e).read_text(errors='replace').splitlines()
                          if l.startswith('+'))
        for drop in sorted(oganesson.drops(drops)):
            for f in re.findall(r'(?m)^--- /dev/null\n\+\+\+ b/(\S+)',
                                (patches / drop).read_text(errors='replace')):
                name = Path(f).name
                if name in ('BUILD.gn', 'README.chromium', 'OWNERS', 'DIR_METADATA'):
                    name = str(Path(f).parent)
                if name in added:
                    problems.append(f'{drops.relative_to(ROOT)}: {drop} creates {f}, which a '
                                    'carried patch uses')
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--chromium', help='Chromium source to check against (default: the prepared '
                    "tree if it's at the pinned version, else googlesource)")
    ap.add_argument('--chromium-version', help="Chromium tag to check against instead of Helium's "
                    "pinned one: the next milestone's beta")
    ap.add_argument('--keep', help='unpack into this directory instead of a temp one')
    args = ap.parse_args()
    tree_dir = oganesson.helium_tree()
    version = (args.chromium_version
               or (tree_dir / 'chromium_version.txt').read_text().strip())
    paths = sorted({p for b in {*BASES, *oganesson.WINDOWS_SERIES} for e in series(b)
                    for p in touched((b / e).read_text())})
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
            ('v8', 'https://chromium.googlesource.com/v8/v8.git', r"'v8_revision': '([0-9a-f]+)'"),
            ('third_party/skia', 'https://skia.googlesource.com/skia.git',
             r"'skia_revision': '([0-9a-f]+)'"),
            ('third_party/search_engines_data/resources',
             'https://chromium.googlesource.com/external/search_engines_data',
             r"'src/third_party/search_engines_data/resources':.*?'([0-9a-f]{40})'"),
            # The Windows series' only.
            ('third_party/angle', 'https://chromium.googlesource.com/angle/angle.git',
             r"'angle_revision': '([0-9a-f]+)'"),
            ('third_party/dawn', 'https://dawn.googlesource.com/dawn.git',
             r"'dawn_revision': '([0-9a-f]+)'")):
        files = [p.removeprefix(folder + '/') for p in paths if p.startswith(folder + '/')]
        if files:
            ref = MIRROR_PINS.get(folder) or re.search(key, deps, re.S).group(1)
            sparse_clone(url, ref, src / folder, files, tree and tree / folder)
    for action, extra in (('retrieve', []), ('unpack', [str(src)])):
        subprocess.run([str(tree_dir / 'utils/downloads.py'), action, '-i', str(tree_dir / 'deps.ini'),
                        '-c', str(cache), *extra, '--components', 'ublock_origin', 'onboarding'],
                       check=True)
    # Our new files, which the patches then hook in. Preparation copies them over the tree, so a
    # file upstream added at the same path would be replaced without a word.
    ours = oganesson.new_files()
    shadowed = subprocess.run(['git', '-C', str(src), 'ls-tree', '-r', '--name-only', 'HEAD', '--',
                               *ours], capture_output=True, text=True, check=True).stdout.split()
    if shadowed:
        sys.exit('new files that Chromium now has too; rename ours:\n  '
                 + '\n  '.join(ours[name] for name in shadowed))
    oganesson.copy_new_files(src)
    windows = work / 'src-windows'
    shutil.rmtree(windows, ignore_errors=True)
    shutil.copytree(src, windows, symlinks=True)
    # WinSparkle, which helium-windows' updater patches change (windows/container-build.sh).
    for action, extra in (('retrieve', []), ('unpack', [str(windows)])):
        subprocess.run([str(tree_dir / 'utils/downloads.py'), action, '-i',
                        str(oganesson.HELIUM_WINDOWS / 'downloads.ini'), '-c', str(cache), *extra,
                        '--components', 'winsparkle'], check=True)
    failed = []
    for name, tree, bases in (('Linux', src, BASES),
                              ('Windows', windows, oganesson.WINDOWS_SERIES)):
        print(f'{name}: ', end='')
        if args.chromium_version:
            # Fuzz places the upstreams' hunks about where their rebase for the next milestone
            # will, so that ours meet a tree closer to the one they will apply to.
            chain = apply_series(tree, bases=bases, upstream_fuzz=2)
            failed += report_next(chain, bases)
        else:
            chain = apply_series(tree, bases=bases)
            report(chain, bases)
            failed += chain
    for problem in drops_still_used():
        print(f'FAILED {problem}')
        failed = failed or [problem]
    # dubna's update policy: both products build one milestone, except for an
    # exploit in the wild (dubna/README.md).
    milestone = (ROOT / 'dubna/milestone.txt').read_text().strip()
    if not args.chromium_version and version.split('.')[0] != milestone:
        print(f'WARNING: Chromium {version} is not on milestone {milestone} of dubna/milestone.txt; '
              'only an exploit in the wild allows that')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
