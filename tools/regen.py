#!/usr/bin/env python3
"""Regenerate patches so the whole series applies with zero fuzz.

Walks the whole series in order on a prepared tree (check_patches.py --keep). A patch that applies
with zero fuzz is committed as is. One that applies once anchored on one side of its context (see
anchored_apply) is applied and rewritten from the resulting diff. One that needs a real edit is
applied as far as possible (fuzz 3), its rejects are recorded and the walk goes on, so one run
reaches every patch. The end lists the patches that need a real edit, in series order, each with
patch's output and its rejected hunks, and puts the tree back to just before the first of them with
that patch applied as far as possible. Fix its rejects in the tree by hand, delete the .rej files,
then run `regen.py WORKDIR --resume`: it rewrites that patch from the edit and walks on from there.

--dry-run walks and reports the same way but rewrites no patch and moves nothing to src/; only the
tree in WORKDIR changes.

After editing the series (say, adding a dependency before the stopping patch), reset the tree to
its last commit and run `regen.py WORKDIR --retry` to try again from the stopping patch.

To rework one patch, `regen.py WORKDIR --edit PATCH` (after a full run) puts the tree back to
just before PATCH and applies it. Edit the tree, then `--resume`. For our patches
(patches/oganesson), files the edit adds go to src/, not into the patch.

--windows works the same way on the Windows series (oganesson.WINDOWS_SERIES) and its tree,
WORKDIR/src-windows, with a state of its own. Our patches it rewrites are the Linux build's too:
check both series again afterwards.

Exits 1 when a patch needs a real edit.
Usage: tools/regen.py WORKDIR [--windows] [--dry-run | --resume | --retry | --edit PATCH]
"""
import os, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import oganesson  # pylint: disable=wrong-import-position
from check_patches import series  # pylint: disable=wrong-import-position
if len(sys.argv) < 2 or sys.argv[1].startswith('-'):
    sys.exit(__doc__)
work = Path(sys.argv[1])
windows = '--windows' in sys.argv
src = work / ('src-windows' if windows else 'src')
state = work / ('.regen-index-windows' if windows else '.regen-index')
# patch and git write temporary files; /tmp may be a small tmpfs.
(work / 'tmp').mkdir(exist_ok=True)
os.environ['TMPDIR'] = str(work / 'tmp')


def run(*cmd, check=True, **kw):
    return subprocess.run(cmd, check=check, capture_output=True, text=True, **kw)


def git(*args, check=True, repo=None):
    return run('git', '-C', str(repo or src), *args, check=check)


def repos():
    """The Chromium checkout and the nested dependency checkouts inside it."""
    return [r for r in [src, *src.glob('third_party/*/src'), src / 'third_party/skia',
                        src / 'third_party/search_engines_data/resources',
                        src / 'third_party/angle', src / 'third_party/dawn', src / 'v8']
            if (r / '.git').exists()]


oganesson.helium_tree()
entries = [base / line for base in (oganesson.WINDOWS_SERIES if windows else oganesson.SERIES)
           for line in series(base)]



def diff_of_last(path):
    """The staged diff of every repo, under the patch's original description."""
    out = ''
    for repo in repos():
        prefix = '' if repo == src else f'{repo.relative_to(src)}/'
        git('add', '-A', '--sparse', repo=repo)
        out += git('diff', '--cached', '--no-color', f'--src-prefix=a/{prefix}',
                   f'--dst-prefix=b/{prefix}', repo=repo).stdout
    body = re.split(r'^diff --git .*\n', out, flags=re.M)[1:]
    files = []
    for chunk in body:
        m = re.search(r'^(--- .*\n\+\+\+ .*\n(?:.*\n)*)', chunk, re.M)
        # Skip the gitlink lines the nested checkouts show up as in the outer repo.
        if m and '+Subproject commit ' not in m.group(1):
            files.append(m.group(1))
    prologue = re.split(r'^--- ', path.read_text(), maxsplit=1, flags=re.M)[0]
    if (ROOT / 'patches/oganesson') in path.parents:
        kept = []
        for section in files:
            new = re.match(r'--- /dev/null\n\+\+\+ b/(\S+)', section)
            if new:
                dest = ROOT / 'src' / new[1]
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src / new[1], dest)
                print(f'moved {new[1]} to src/')
            else:
                # An edit that only brings a src/ file to its src/ version isn't
                # the patch's: src/ goes in before any patch.
                name = re.match(r'--- a/(\S+)', section)[1]
                ours = oganesson.new_files().get(name)
                if ours and (ROOT / ours).read_bytes() == (src / name).read_bytes():
                    print(f'dropped {name}: same as src/')
                else:
                    kept.append(section)
        files = kept
    # A file can drop out legitimately (gone upstream, moved to src/), or because its checkout
    # isn't in repos(): check each one.
    lost = (set(re.findall(r'^\+\+\+ b/(\S+)', path.read_text(), re.M))
            - set(re.findall(r'^\+\+\+ b/(\S+)', ''.join(files), re.M)))
    for name in sorted(lost):
        print(f'WARNING: {label(path)} no longer edits {name}')
    return prologue + ''.join(files)


def commit(name):
    for repo in repos():
        git('add', '-A', '--sparse', repo=repo)
        git('-c', 'user.name=x', '-c', 'user.email=x@x', 'commit', '-q', '--allow-empty', '-m',
            name, repo=repo)


def anchored_apply(path):
    """Apply a patch that fails with zero fuzz, hunk by hunk, by exact text match.

    A hunk whose full context no longer matches is retried with only its trailing context, then
    with only its leading context: typically a neighbor we don't carry sits on the other side.
    The context kept, and any removed lines, must still match exactly and at exactly one place.
    Unlike patch's fuzz, this never drops context from both sides, so an insertion can't drift
    past what it was written against. Returns False, changing nothing, when a hunk can't be placed.
    """
    sections = re.split(r'^(?=--- )', path.read_text(), flags=re.M)[1:]
    results = {}
    for section in sections:
        lines = section.splitlines(keepends=True)
        old, new = lines[0][4:].split('\t')[0].strip(), lines[1][4:].split('\t')[0].strip()
        target = src / new.removeprefix('b/')
        if old == '/dev/null':
            if target.exists():
                return False
            results[target] = ''.join(l[1:] for l in lines[3:] if l[0] == '+')
            continue
        if target not in results and not target.exists():
            return False
        text = results.get(target, target.read_text() if target.exists() else '')
        for hunk in re.split(r'^(?=@@ )', ''.join(lines[2:]), flags=re.M)[1:]:
            body = [l for l in hunk.splitlines(keepends=True)[1:] if l[:1] in (' ', '-', '+')]
            changed = [i for i, l in enumerate(body) if l[0] != ' ']
            if not changed:
                continue
            first, last = changed[0], changed[-1] + 1
            for lo, hi in ((0, len(body)), (first, len(body)), (0, last)):
                part = body[lo:hi]
                before = ''.join(l[1:] for l in part if l[0] != '+')
                after = ''.join(l[1:] for l in part if l[0] != '-')
                # Leading newlines keep the match on line boundaries.
                if before and ('\n' + text).count('\n' + before) == 1:
                    text = ('\n' + text).replace('\n' + before, '\n' + after)[1:]
                    break
            else:
                return False
        results[target] = text
    for target, text in results.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    return True


def fetch_files(path):
    """Adds the files `path` edits to the sparse checkout, if they aren't in it yet."""
    for name in re.findall(r'^--- a/(\S+)', path.read_text(), re.M):
        if (src / name).exists():
            continue
        # The file may be in one of the nested checkouts.
        repo = next((r for r in repos()[1:] if (src / name).is_relative_to(r)), src)
        git('sparse-checkout', 'add', '/' + str((src / name).relative_to(repo)), check=False,
            repo=repo)


def patch_cmd(path, fuzz, *extra):
    return ['patch', '-p1', f'--fuzz={fuzz}', '--no-backup-if-mismatch', '-i', str(path), '-d',
            str(src), *extra]


def label(path):
    return str(path.relative_to(ROOT))


def edit(start):
    """Puts the tree back to just before entries[start] and applies it as far as it goes."""
    before = label(entries[start - 1]) if start else 'base'
    for repo in repos():
        log = git('log', '--all', '--format=%H %s', repo=repo).stdout.splitlines()
        commit_id = next(line.split()[0] for line in log if line.split(' ', 1)[1] == before)
        git('reset', '-q', '--hard', commit_id, repo=repo)
        git('clean', '-fdq', repo=repo)
    # Commits from before a file moved to src/ lack it. Only missing files: a
    # patch before this point may have edited the others.
    for name, file in oganesson.new_files().items():
        if not (src / name).exists():
            (src / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / file, src / name)
    fetch_files(entries[start])
    run(*patch_cmd(entries[start], 3), check=False)
    state.write_text(str(start))
    rejects = run('find', str(src), '-name', '*.rej', check=False).stdout.split()
    print(f'{label(entries[start])} is applied on its predecessors', *rejects, sep='\n')
    sys.exit('edit the tree, delete the .rej files, then --resume')


def take_rejects():
    """The .rej files' text, removed from the tree so the walk can go on."""
    text = ''
    for rej in sorted(src.rglob('*.rej')):
        text += f'{rej.relative_to(src)}:\n{rej.read_text(errors="replace")}'
        rej.unlink()
    return text


dry = '--dry-run' in sys.argv
start = 0
if '--edit' in sys.argv:
    wanted = sys.argv[sys.argv.index('--edit') + 1]
    match = next((n for n, e in enumerate(entries) if label(e).endswith(wanted)), None)
    if match is None:
        sys.exit(f'no patch named {wanted}')
    edit(match)
elif '--resume' in sys.argv or '--retry' in sys.argv:
    start = int(state.read_text())
    if list(src.rglob('*.rej')):
        sys.exit('rejects are still in the tree')
else:
    # Earlier runs leave commits on top of the Chromium checkout; go back to it.
    root = git('rev-list', '--max-parents=0', 'HEAD').stdout.split()[0]
    git('reset', '-q', '--hard', root)
    git('clean', '-fdxq')
    for repo in repos()[1:]:
        root = git('rev-list', '--max-parents=0', 'HEAD', repo=repo).stdout.split()[0]
        git('reset', '-q', '--hard', root, repo=repo)
        git('clean', '-fdxq', repo=repo)
    subprocess.run([str(oganesson.helium_tree() / 'utils/downloads.py'), 'unpack', '-i',
                    str(oganesson.TREE / 'deps.ini'),
                    '-c', str(work / 'cache'), str(src), '--components', 'ublock_origin',
                    'onboarding'], check=True, capture_output=True)
    if windows:
        # WinSparkle, which helium-windows' updater patches change, as check_patches.py unpacks it.
        subprocess.run([str(oganesson.helium_tree() / 'utils/downloads.py'), 'unpack', '-i',
                        str(oganesson.HELIUM_WINDOWS / 'downloads.ini'), '-c', str(work / 'cache'),
                        str(src), '--components', 'winsparkle'], check=True, capture_output=True)
    oganesson.copy_new_files(src)
    commit('base')


i = start
if '--resume' in sys.argv:
    path = entries[i]
    path.write_text(diff_of_last(path))
    commit(label(path))
    print(f'rewrote {path.relative_to(ROOT)} from the manual edit')
    i += 1
changed, manual = [], []
for i in range(i, len(entries)):
    path = entries[i]
    fetch_files(path)
    # 1: hunks don't fit. 2: trouble, such as a malformed patch, which anchoring can't read either.
    check = run(*patch_cmd(path, 0, '--dry-run', '--silent'), check=False).returncode
    if check == 0:
        run(*patch_cmd(path, 0, '--silent'))
    elif check == 1 and anchored_apply(path):
        if not dry:
            path.write_text(diff_of_last(path))
        changed.append(path.name)
    else:
        # Apply what fits, so the patches after this one see as much of it as they can.
        out = run(*patch_cmd(path, 3), check=False)
        manual.append((i, out.stdout + out.stderr, take_rejects()))
    commit(label(path))
print(f'refreshed by anchoring{" (dry run, not written)" if dry else ""}: {len(changed)}')
print(*changed, sep='\n')
if not manual:
    if not dry:
        state.write_text(str(len(entries)))
    sys.exit()
print(f'\nneed a real edit, in series order: {len(manual)}')
for n, output, rejects in manual:
    print(f'MANUAL {n}: {label(entries[n])}')
    print(*('  ' + line for line in (output + rejects).splitlines()), sep='\n')
if dry:
    sys.exit(1)
print()
edit(manual[0][0])
