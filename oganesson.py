#!/usr/bin/env python3
"""Builds oganesson: Helium's tree with the patch series in patches/, linux/
patches and late/, and our new files in dubna/src/ (shared with tennessine) and
src/.

build:    prepares the Chromium tree in work/ (once per patch set) and builds it
          in helium-linux's builder container.
snapshot: makes work/ a btrfs snapshot of the shared base tree, so a first
          build reuses its sources and build cache.
run:      starts the dev build with a profile in work/profile.
test:     runs the end-to-end tests in tools/e2e against the dev build.
stamp:    marks work/ as prepared for the current patches, after the same edit
          was made in the tree by hand, so build doesn't reset it. Refuses
          when a patch or new file changed since the last stamp isn't in
          the tree, or a removed one still is.
shell:    opens a shell in the builder container.
check-patches: applies the Linux and the Windows series to a sparse checkout,
               zero fuzz, and lists every patch that fails in each.
"""
import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = ROOT / 'work'
# helium-linux's layout, which the shared base tree and its build cache use.
SRC = WORK / 'helium-linux/build/src'
# Helium's tree as the build reads it (helium_tree()): the helium submodule with
# our fixes to its utils/, our branding over its resources/, and its series
# without the patches in DROPS.
HELIUM = ROOT / 'helium'
HELIUM_LINUX = ROOT / 'linux/helium-linux'
HELIUM_WINDOWS = ROOT / 'windows/helium-windows'
TREE = WORK / 'helium-tree'
DROPS = ROOT / 'patches/helium-drops.txt'
WINDOWS_DROPS = ROOT / 'windows/helium-windows-drops.txt'
UTILS_PATCH = ROOT / 'patches/helium-utils.patch'
# Applied in this order: Helium's, helium-linux's, ours (with dubna's), and the
# late ones: late/ for every platform, then linux/late, which renames what
# helium-linux's patches set.
SERIES = (TREE / 'patches', HELIUM_LINUX / 'patches', ROOT / 'patches', ROOT / 'late',
          ROOT / 'linux/late')
# The Windows build's (windows/container-build.sh): helium-windows' patches,
# without WINDOWS_DROPS, for helium-linux's, and windows/late for linux/late.
WINDOWS_SERIES = (TREE / 'patches', HELIUM_WINDOWS / 'patches', ROOT / 'patches', ROOT / 'late',
                  ROOT / 'windows/late')
# Our new files, copied over the tree before the patches: dubna's, which
# tennessine shares, then ours.
SOURCES = ('dubna/src', 'src')
# What preparation reads besides the series and SOURCES: Helium's assembled tree
# (the Chromium pin, whose change also refetches the sources, see
# linux/container-build.sh; version files, lists, translations, resources and the
# scripts that apply them), helium-linux's, our translations and our scripts.
PREP_INPUTS = ('work/helium-tree', 'linux/helium-linux', 'l10n', 'dubna/l10n',
               'tools/branding.py', 'tools/grit_fixups.py', 'dubna/tools/translate.py',
               'linux/container-build.sh', 'tools/prepare.sh')
# The Windows tree's inputs besides those: helium-windows and its build script.
WINDOWS_INPUTS = ('windows/helium-windows', 'windows/container-build.sh',
                  'windows/helium-windows-drops.txt', 'windows/late')
# Caches, tests, resources/generated (which preparation itself writes), git
# metadata and helium-linux's own copy of Helium, which TREE stands in for.
PREP_SKIP = {'__pycache__', 'tests', 'generated', '.git', 'helium-chromium'}
IMAGE = 'oganesson-builder'
WINDOWS_IMAGE = 'oganesson-windows-builder'
MOUNT = '/oganesson'


def fail(message):
    sys.exit(f'oganesson: {message}')


def drops(path):
    """The patches a drops file names: the first field of each line."""
    return {line.split('\t')[0] for line in path.read_text().splitlines()
            if line.strip() and not line.startswith('#')}


def helium_tree():
    """Assembles TREE from the helium submodule's checkout, once per change of
    its inputs: the submodule's commit, UTILS_PATCH, DROPS and our resources/."""
    digest = hashlib.sha256(subprocess.run(['git', '-C', str(HELIUM), 'rev-parse', 'HEAD'],
                                           capture_output=True, check=True).stdout)
    for path in [UTILS_PATCH, DROPS, *sorted((ROOT / 'resources').rglob('*'))]:
        if path.is_file():
            digest.update(str(path.relative_to(ROOT)).encode() + path.read_bytes())
    stamp = TREE / '.oganesson-tree'
    if stamp.is_file() and stamp.read_text() == digest.hexdigest():
        return TREE
    shutil.rmtree(TREE, ignore_errors=True)
    TREE.mkdir(parents=True)
    archive = subprocess.run(['git', '-C', str(HELIUM), 'archive', 'HEAD'], capture_output=True,
                             check=True).stdout
    subprocess.run(['tar', '-x', '-C', str(TREE)], input=archive, check=True)
    subprocess.run(['patch', '-p1', '-s', '--fuzz=0', '--no-backup-if-mismatch', '-d', str(TREE),
                    '-i', str(UTILS_PATCH)], check=True)
    shutil.copytree(ROOT / 'resources', TREE / 'resources', dirs_exist_ok=True)
    dropped = drops(DROPS)
    series = (TREE / 'patches/series').read_text().splitlines()
    missing = dropped - {line.strip() for line in series}
    if missing:
        fail('patches/helium-drops.txt names patches Helium\'s series no longer has:\n  '
             + '\n  '.join(sorted(missing)))
    (TREE / 'patches/series').write_text(
        ''.join(line + '\n' for line in series if line.strip() not in dropped))
    stamp.write_text(digest.hexdigest())
    return TREE


def new_files():
    """{path in the tree: path from ROOT} of every file in SOURCES."""
    found = {}
    for top in SOURCES:
        for path in sorted((ROOT / top).rglob('*')):
            relative = path.relative_to(ROOT)
            if path.is_file() and not PREP_SKIP & set(relative.parts):
                name = str(path.relative_to(ROOT / top))
                if name in found:
                    fail(f'{found[name]} and {relative} are the same tree file')
                found[name] = str(relative)
    return found


def copy_new_files(tree):
    for name, path in new_files().items():
        (Path(tree) / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, Path(tree) / name)


def series_entries(text):
    return [line.strip() for line in text.splitlines()
            if line.strip() and not line.startswith('#')]


def series_patches():
    """Every series patch, in the order preparation applies them."""
    helium_tree()
    return [patches / line for patches in SERIES
            for line in series_entries((patches / 'series').read_text())]


def sections(text):
    """(preamble, [(file, section_text)]); a section starts at a '--- ' line
    followed by a '+++ ' line, and a deletion's file is its '--- ' name."""
    lines = text.splitlines(keepends=True)
    starts = [i for i in range(len(lines) - 1)
              if lines[i].startswith('--- ') and lines[i + 1].startswith('+++ ')]
    pre = ''.join(lines[:starts[0]]) if starts else text
    secs = []
    for j, i in enumerate(starts):
        end = starts[j + 1] if j + 1 < len(starts) else len(lines)
        header = lines[i + 1] if not lines[i + 1].startswith('+++ /dev/null') else lines[i]
        name = header[4:].split('\t')[0].strip()
        name = name.split('/', 1)[1] if '/' in name else name
        secs.append((name, ''.join(lines[i:end])))
    return pre, secs


def patch_hash(extra=()):
    """Hashes every input of the prepared tree: each series and its patches,
    our new files, PREP_INPUTS and `extra` (WINDOWS_INPUTS for that tree)."""
    helium_tree()
    digest = hashlib.sha256()
    for patches in SERIES:
        series = (patches / 'series').read_text()
        digest.update(series.encode())
        for line in series_entries(series):
            digest.update((patches / line).read_bytes())
    paths = []
    for top in (*SOURCES, *PREP_INPUTS, *extra):
        top = ROOT / top
        paths += [top] if top.is_file() else top.rglob('*')
    for path in sorted(paths):
        relative = path.relative_to(ROOT)
        if path.is_file() and not PREP_SKIP & set(relative.parts):
            digest.update(str(relative).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def input_hashes():
    """Each series patch's and new file's hash, by path: what stamp compares
    with the last stamp's to find the changes it checks in the tree."""
    paths = series_patches() + [ROOT / p for p in new_files().values()]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def tree_name(path):
    """The tree path of a new file's path from ROOT, or None for a patch."""
    for top in SOURCES:
        if path.startswith(top + '/'):
            return path[len(top) + 1:]
    return None


def failed_hunks(path, section):
    """The numbers of the section's hunks that path doesn't hold: those that
    don't reverse-apply, dry run and zero fuzz."""
    result = subprocess.run(['patch', '-f', '-R', '--dry-run', '--fuzz=0', str(path)],
                            input=section, capture_output=True, text=True, check=False)
    failed = {int(n) for n in re.findall(r'^Hunk #(\d+) FAILED', result.stdout, re.M)}
    if result.returncode and not failed:  # an error before any hunk
        failed = set(range(1, section.count('\n@@ ') + 1))
    return failed


def applied(path, secs, directory, reverse=False):
    """A copy of path in directory with secs applied in order, or with
    reverse, reversed last first; None when one doesn't apply."""
    copy = Path(directory) / path.name
    shutil.copyfile(path, copy)
    for section in reversed(secs) if reverse else secs:
        if subprocess.run(['patch', '-f', '-s', '--fuzz=0', '--no-backup-if-mismatch', '-r', '-',
                           *(['-R'] if reverse else []), str(copy)], input=section,
                          capture_output=True, text=True, check=False).returncode:
            return None
    return copy


def old_text(path, digest):
    """path's text with that hash, from disk or from one of the last commits
    that changed or removed it; None when neither has it."""
    file = ROOT / path
    blobs = [file.read_bytes()] if file.is_file() else []
    revs = subprocess.run(['git', '-C', str(ROOT), 'log', '-n', '10', '--format=%H', '--', path],
                          capture_output=True, text=True, check=False).stdout.split()
    for rev in (r for rev in revs for r in (rev, f'{rev}^')):
        blobs.append(subprocess.run(['git', '-C', str(ROOT), 'show', f'{rev}:{path}'],
                                    capture_output=True, check=False).stdout)
    return next((b.decode(errors='replace') for b in blobs
                 if hashlib.sha256(b).hexdigest() == digest), None)


def tree_lacks(previous, current):
    """Checks the tree against what changed in the inputs since the last stamp.
    Each series patch and new file whose hash differs must be in the tree: a
    patch's hunks with the later series patches' sections of the same file
    reversed, a new file with the series patches that edit it applied. A hunk
    of the old version of a changed or dropped patch that no patch still has,
    and a removed new file, must be gone from it. Returns (missing,
    unverifiable): unverifiable is what can't be checked, such as hunks where
    the later patches don't reverse, or in branding and translations (.grd,
    .grdp, .xtb)."""
    sys.path.insert(0, str(helium_tree() / 'utils'))
    from domain_substitution import DomainRegexList  # pylint: disable=import-outside-toplevel
    pairs = DomainRegexList(TREE / 'domain_regex.list').regex_pairs
    domsub = set((TREE / 'domain_substitution.list').read_text().split())

    def substitute(name, text, whole=False):
        """Helium's domain substitution, which preparation runs after the
        patches, on a file or (keeping each line's first character) a diff."""
        if name not in domsub:
            return text
        if whole:
            for pair in pairs:
                text = pair.pattern.sub(pair.replacement, text)
            return text
        lines = text.splitlines(keepends=True)
        for pair in pairs:
            lines = [line[:1] + pair.pattern.sub(pair.replacement, line[1:]) for line in lines]
        return ''.join(lines)

    patches = series_patches()
    texts = [p.read_text() for p in patches]
    parsed = [sections(text)[1] for text in texts]
    missing, unverifiable = [], []
    for path, digest in sorted(current.items()):
        if previous.get(path) == digest:
            continue
        if tree_name(path):
            name = tree_name(path)
            tree = SRC / name
            edits = [s for secs in parsed for n, s in secs if n == name]
            with tempfile.TemporaryDirectory() as directory:
                expected = applied(ROOT / path, edits, directory)
                expected = expected and substitute(name, expected.read_text(errors='replace'), True)
            if expected is None:
                unverifiable.append(f'{path}: the series patches that edit it don\'t apply to '
                                    'it; check the tree holds its change')
            elif not tree.is_file() or tree.read_text(errors='replace') != expected:
                missing.append(f'{path}: differs from the tree copy'
                               + (' with the series patches that edit it' if edits else ''))
            continue
        index = patches.index(ROOT / path)
        lacking, hunks = [], 0
        for name, section in parsed[index]:
            tree = SRC / name
            if '\n+++ /dev/null' in section:
                if tree.exists():
                    missing.append(f'{path}: {name} still exists')
                continue
            if not tree.is_file():
                missing.append(f'{path}: {name} is not in the tree')
                continue
            later = [substitute(name, s) for secs in parsed[index + 1:] for n, s in secs if n == name]
            with tempfile.TemporaryDirectory() as directory:
                held = applied(tree, later, directory, reverse=True) if later else tree
                failed = failed_hunks(held or tree, substitute(name, section))
            if name.endswith(('.grd', '.grdp', '.xtb')):
                why = 'branding and translations rewrite it'
            elif held is None:
                why = 'a later patch\'s change there doesn\'t reverse'
            else:
                hunks += section.count('\n@@ ')
                lacking += [f'{path}: {name} hunk {hunk}' for hunk in sorted(failed)]
                continue
            unverifiable += [f'{path}: {name} hunk {hunk} ({why}); check the tree holds it'
                             for hunk in sorted(failed)]
        if hunks and len(lacking) == hunks:
            missing.append(f'{path}: none of its hunks are in the tree')
        else:
            missing += lacking
    for path, digest in sorted(previous.items()):
        if path in current and current[path] == digest:
            continue
        if tree_name(path):
            tree = SRC / tree_name(path)
            if tree.is_file() and hashlib.sha256(tree.read_bytes()).hexdigest() == digest:
                missing.append(f'{path}: removed, but the tree still has it')
            continue
        old = old_text(path, digest)
        if old is None:
            if path not in current:
                unverifiable.append(f'{path}: dropped from the series, and no copy of it is left; '
                                    'check the tree doesn\'t keep its change')
            continue
        for name, section in sections(old)[1]:
            tree = SRC / name
            if ('\n+++ /dev/null' in section or not tree.is_file()
                    or name.endswith(('.grd', '.grdp', '.xtb'))):
                continue
            failed = failed_hunks(tree, substitute(name, section))
            for hunk, body in enumerate(section.split('\n@@ ')[1:], 1):
                body = body.split('\n', 1)[1]
                if hunk not in failed and not any(body in text for text in texts):
                    missing.append(f'{path}: {name} hunk {hunk} of the previous version, which '
                                   'no patch has now, is still in the tree')
    return missing, unverifiable


def write_stamp(force=False, amended=None):
    """Stamps the tree as prepared for the current inputs, after checking it
    against what changed since the last stamp (see tree_lacks). amended, a
    patch tools/amend.py just rebuilt from the tree, counts as unchanged."""
    stamp_file, record_file = SRC / '.oganesson-prepared', SRC / '.oganesson-inputs'
    current = input_hashes()
    record = json.loads(record_file.read_text()) if record_file.is_file() else {}
    stamped = stamp_file.read_text().split()[1:2] if stamp_file.is_file() else []
    # A failed build's preparation removes the stamp and, with git clean, the
    # record, and leaves the tree half patched.
    if not force and not stamped and (SRC / '.downloaded.stamp').is_file():
        fail('the tree was fetched but has no stamp, so a failed build may have left it half '
             'prepared; run ./oganesson.py build, or, if it holds the current patches, '
             'stamp with --force.')
    if not force and (not record or [record['tree']] != stamped):
        print('oganesson: no record of the last stamp\'s inputs; stamping without a check',
              file=sys.stderr)
    elif not force:
        if amended:
            record['files'][amended] = current[amended]
        missing, unverifiable = tree_lacks(record['files'], current)
        for where in unverifiable:
            print(f'oganesson: can\'t check {where}', file=sys.stderr)
        if missing:
            fail('the tree doesn\'t match these changes since the last stamp:\n  '
                 + '\n  '.join(missing) + '\nApply them to the tree, or, if it holds them in '
                 'another form, stamp with --force.')
    record_inputs(patch_hash(), current)


def record_inputs(tree_hash, files):
    """Writes the stamp and, next to it, the per-file hashes it was made for."""
    (SRC / '.oganesson-inputs').write_text(json.dumps({'tree': tree_hash, 'files': files}) + '\n')
    (SRC / '.oganesson-prepared').write_text(f'tree {tree_hash}\n')


def docker_run(command, env=(), nice=0, cpu_shares=None, image=IMAGE, options=()):
    tty = ['-t'] if sys.stdin.isatty() else []
    # --init: a stop signal the docker CLI forwards ends the build (bash as
    # PID 1 would ignore it, and the container would outlive the checkout lock).
    cmd = ['docker', 'run', '--rm', '--init', '-i', *tty, '-u', f'{os.getuid()}:{os.getgid()}',
           '-v', f'{ROOT}:{MOUNT}', '-w', MOUNT, *options]
    if cpu_shares:
        cmd += ['--cpu-shares', str(cpu_shares)]
    for key, value in env:
        cmd += ['-e', f'{key}={value}']
    if nice:
        # Lower CPU and disk priority for everything the build starts.
        command = ['nice', '-n', str(nice), 'ionice', '-c', '2', '-n', '7', *command]
    # The docker CLI inherits the checkout lock: killing only this process
    # leaves the lock held for as long as the build goes on.
    return subprocess.run(cmd + [image, *command], check=False, pass_fds=held_lock()).returncode


def build_image():
    uid_args = []
    if os.getuid() != 0:
        uid_args = ['--build-arg', f'UID={os.getuid()}', '--build-arg', f'GID={os.getgid()}']
    subprocess.run(['docker', 'build', '-t', IMAGE, *uid_args, '-f',
                    str(HELIUM_LINUX / 'docker/build.Dockerfile'), str(HELIUM_LINUX / 'docker')],
                   check=True)


# Builds started on a weekday from 2:00 to 15:00, while the machine is in
# use, default to these limits; others get every CPU at normal priority.
QUIET_JOBS, QUIET_NICE = 24, 19


def quiet_hours(now):
    return now.weekday() < 5 and 2 <= now.hour < 15


def build(args):
    lock = hold_checkout('build')  # noqa: F841 (held until exit)
    if args.jobs is None and args.nice is None and quiet_hours(datetime.now()):
        args.jobs, args.nice = QUIET_JOBS, QUIET_NICE
        print(f'oganesson: weekday daytime build: -j {QUIET_JOBS}, nice {QUIET_NICE}', file=sys.stderr)
    build_image()
    if args.windows:
        subprocess.run(['docker', 'build', '-t', WINDOWS_IMAGE, '-f', str(ROOT / 'windows/Dockerfile'),
                        str(ROOT / 'windows')], check=True)
        sys.exit(build_windows(args))
    tree_hash, files = patch_hash(), input_hashes()
    env = [('OGANESSON_PATCH_HASH', tree_hash)]
    if args.jobs:
        env.append(('OGANESSON_JOBS', str(args.jobs)))
    mode = 'release' if args.release else 'dev'
    # With --nice, the container also gets a low CPU weight, so it yields to
    # other containers too.
    code = docker_run(['bash', f'{MOUNT}/linux/container-build.sh', mode], env,
                      nice=args.nice, cpu_shares=256 if args.nice else None)
    # A tree prepared for these inputs gets their record, for the next stamp.
    stamp_file = SRC / '.oganesson-prepared'
    if stamp_file.is_file() and stamp_file.read_text() == f'tree {tree_hash}\n':
        record_inputs(tree_hash, files)
    if code == 0:
        out = SRC / 'out' / ('Release' if args.release else 'Default')
        print(f'Built {out}/oganesson')
    sys.exit(code)


def build_windows(args):
    """The Windows release build and its packages, cross-compiled
    (windows/container-build.sh). FUSE for the case-insensitive toolchain mount
    Chromium makes."""
    env = [('OGANESSON_PATCH_HASH', patch_hash(WINDOWS_INPUTS)),
           ('OGANESSON_COMMIT_TIME', subprocess.run(
               ['git', '-C', str(ROOT), 'log', '-1', '--format=%cd',
                '--date=format-local:%Y%m%d%H%M%S'], env=dict(os.environ, TZ='UTC0'),
               capture_output=True, text=True, check=True).stdout.strip())]
    if args.jobs:
        env.append(('OGANESSON_JOBS', str(args.jobs)))
    code = docker_run(['bash', f'{MOUNT}/windows/container-build.sh'], env, nice=args.nice,
                      cpu_shares=256 if args.nice else None, image=WINDOWS_IMAGE,
                      options=['--device', '/dev/fuse', '--cap-add', 'SYS_ADMIN',
                               '--security-opt', 'apparmor=unconfined'])
    if code == 0:
        print(f'Built {WORK}/helium-windows/build/src/out/Release/chrome.exe; packages in '
              f'{WORK}/dl/windows')
    return code


def snapshot(args):
    base = args.base.expanduser()
    if not base.is_dir():
        fail(f'no base tree at {base}')
    if WORK.exists():
        fail('work/ already exists; remove it to snapshot the base tree')
    subprocess.run(['btrfs', 'subvolume', 'snapshot', str(base), str(WORK)], check=True)
    print(f'work/ is a snapshot of {base}; the next build resets it to this series')


def run(args):
    binary = SRC / 'out/Default/oganesson'
    if not binary.exists():
        fail('nothing built yet; run ./oganesson.py build')
    os.execv(str(binary), [str(binary), f'--user-data-dir={WORK / "profile"}', *args.extra])


def e2e_tests():
    """Maps each suite to its test names, in the order unittest runs them."""
    return {path.stem.removeprefix('test_'):
            sorted(re.findall(r'^    def test_(\w+)', path.read_text(), re.M))
            for path in sorted((ROOT / 'tools/e2e').glob('test_*.py'))}


def test(args):
    tests = e2e_tests()
    if args.list:
        print('\n'.join(f'{suite}.{name}' for suite, names in tests.items() for name in names))
        return
    modules, patterns = [], []
    for selection in args.suites:
        suite, _, name = selection.partition('.')
        if suite not in tests:
            fail(f'no suite {suite!r}; suites: {", ".join(tests)}')
        if name and name not in tests[suite]:
            fail(f'no test {name!r} in {suite}; tests: {", ".join(tests[suite])}')
        modules.append(f'test_{suite}')
        # Numbered tests are steps of one session, so the earlier steps run too.
        steps = [t for t in tests[suite] if t[0].isdigit() and t < name] if name[:1].isdigit() else []
        patterns += [f'-ktest_{suite}.*.test_{t}' for t in [*steps, name or '*']]
    missing = [tool for tool in ('Xvfb', 'xdotool', 'xwd') if not shutil.which(tool)]
    if missing:
        fail(f'the end-to-end tests need {", ".join(missing)}')
    binary = (args.binary or SRC / 'out' / ('Release' if args.release else 'Default') / 'oganesson').resolve()
    # The harness skips, rather than fails, without a browser.
    if not binary.is_file():
        fail(f'no browser binary at {binary}; run ./oganesson.py build')
    lock = hold_checkout('test')  # noqa: F841 (held until exit)
    env = dict(os.environ, OGANESSON_BINARY=str(binary))
    # Test profiles, kept when a test fails, go under work/ on the home disk:
    # /tmp is a tmpfs with a per-user quota.
    (WORK / 'tmp').mkdir(parents=True, exist_ok=True)
    env['TMPDIR'] = str(WORK / 'tmp')
    if args.keep:
        env['OGANESSON_E2E_KEEP'] = '1'
    # unittest takes `discover` only as its first argument.
    args_ = [*dict.fromkeys(modules), *patterns]
    args_ = ['-v', *args_] if args_ else ['discover', '-v', '-p', 'test_*.py']
    sys.exit(subprocess.run([sys.executable, '-m', 'unittest', *args_], cwd=ROOT / 'tools/e2e',
                            env=env, check=False, pass_fds=held_lock()).returncode)


def stamp(args):
    if not SRC.is_dir():
        fail(f'no tree at {SRC}; run ./oganesson.py snapshot or build')
    lock = hold_checkout('stamp')  # noqa: F841 (held until exit)
    write_stamp(args.force)


def shell(_):
    build_image()
    sys.exit(docker_run(['bash']))


def check_patches(args):
    sys.exit(subprocess.run([sys.executable, str(ROOT / 'tools/check_patches.py'), *args.extra],
                            check=False).returncode)


_LOCK = None


def held_lock():
    """The checkout lock's fd for pass_fds, so children hold it too."""
    return (_LOCK.fileno(),) if _LOCK else ()


def hold_checkout(command):
    """Waits for, then holds until exit, this checkout's lock: one build,
    test run or stamp at a time per work/ tree, so concurrent agents queue
    here instead of polling logs or processes. Callers take it after their
    own checks, so a command that fails them never waits. Without work/
    there is nothing to share yet, and work/ stays absent for `snapshot`."""
    if not WORK.is_dir():
        return None
    lock = open(WORK / '.checkout.lock', 'a+')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.seek(0)
        print(f'oganesson: waiting for {lock.read().strip() or "another command"} '
              'to finish in this checkout', file=sys.stderr, flush=True)
        fcntl.flock(lock, fcntl.LOCK_EX)
    lock.truncate(0)
    lock.write(f'pid {os.getpid()}: oganesson.py {" ".join(sys.argv[1:]) or command}\n')
    lock.flush()
    global _LOCK
    _LOCK = lock
    return lock  # held until the process exits


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    build_parser = commands.add_parser('build', help='prepare the tree and build it in a container')
    build_parser.add_argument('--release', action='store_true',
                              help='official build for x86-64-v2 instead of a component build (much slower)')
    build_parser.add_argument('--windows', action='store_true',
                              help='the Windows x64 release build, cross-compiled (see windows/)')
    build_parser.add_argument('-j', '--jobs', type=int,
                              help='parallel compile jobs (weekdays 2:00-15:00 default: 24, with --nice 19)')
    build_parser.add_argument('--nice', type=int, metavar='N',
                              help='run at nice level N with idle-ish disk priority, so the '
                                   'machine stays responsive (e.g. 10)')
    build_parser.set_defaults(handler=build)
    snapshot_parser = commands.add_parser(
        'snapshot', help='make work/ a btrfs snapshot of the shared base tree')
    snapshot_parser.add_argument('--base', type=Path,
                                 default=Path(os.environ.get('OGANESSON_BASE', '~/dev/oganesson-base')),
                                 help='base tree subvolume (default: $OGANESSON_BASE or '
                                      '~/dev/oganesson-base)')
    snapshot_parser.set_defaults(handler=snapshot)
    run_parser = commands.add_parser('run', help='start the built browser')
    run_parser.add_argument('extra', nargs=argparse.REMAINDER, help='extra browser flags')
    run_parser.set_defaults(handler=run)
    test_parser = commands.add_parser('test', help='run the end-to-end tests against the build')
    test_parser.add_argument('suites', nargs='*',
                             help='suites or suite.test to run, e.g. toolbar gestures.internal_page '
                                  '(default: all)')
    test_parser.add_argument('--list', action='store_true', help='list the suite.test names')
    test_target = test_parser.add_mutually_exclusive_group()
    test_target.add_argument('--binary', type=Path, help='browser to test (default: the dev build)')
    test_target.add_argument('--release', action='store_true', help='test the release build, out/Release')
    test_parser.add_argument('--keep', action='store_true',
                             help="keep every run's profile and log, not only failed ones")
    test_parser.set_defaults(handler=test)
    stamp_parser = commands.add_parser(
        'stamp', help='mark the tree as prepared for the current patches, after making the same '
                      'edit in it by hand; refuses when a patch or new file changed since the '
                      'last stamp is not in the tree, or a removed one still is')
    stamp_parser.add_argument('--force', action='store_true',
                              help='stamp without checking the tree, e.g. when it holds the '
                                   'change in another form')
    stamp_parser.set_defaults(handler=stamp)
    commands.add_parser('shell', help='shell in the builder container').set_defaults(handler=shell)
    check_parser = commands.add_parser('check-patches',
                                       help='apply the whole series to a sparse checkout, zero fuzz')
    check_parser.add_argument('extra', nargs=argparse.REMAINDER,
                              help='options for tools/check_patches.py')
    check_parser.set_defaults(handler=check_patches)
    argv = sys.argv[1:]
    if argv[:1] in (['run'], ['check-patches']):
        # Everything after these goes to the browser or tools/check_patches.py
        # as is: argparse rejects a leading option before REMAINDER takes it.
        args = parser.parse_args(argv[:1])
        args.extra = argv[1:]
    else:
        args = parser.parse_args(argv)
    args.handler(args)


if __name__ == '__main__':
    main()
