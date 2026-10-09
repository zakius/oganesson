#!/usr/bin/env python3
"""Moves the vendored Helium and helium-linux files to a new helium-linux ref.

Usage: tools/update_helium.py [--dry-run] LINUX_REF   (for example 0.19.1.2)
       tools/update_helium.py --check               (only the series check, at the pins)

We follow helium-linux: the Helium ref is the commit of its helium-chromium submodule at
LINUX_REF, and the Chromium version is that Helium commit's.

The pins are in upstream.txt. For each file upstream changed between the pin and the new ref:
a file we don't carry is skipped; a file still equal to upstream's old copy takes the new one;
a file we changed (our patch refreshes, utils/ fixes) gets a three-way merge. A file whose merge
conflicts takes upstream's clean changes and keeps our side of each conflict, so no conflict
marker reaches it, and the report shows each
conflicting upstream hunk and, for a patch, the Chromium file the hunk is in.
A new upstream patch needs the maintainer's decision first:
the script lists each one and writes nothing until every one has a line in
docs/helium-patch-decisions.md. Under "Want" or "Want while cheap" it then goes into our
series after its nearest upstream neighbor that we carry; under any other heading it stays out.
So does a patch left out under "Undecided" whose line later moves under a carried heading:
the next run adds it, and running this at the current pin adds it without moving the pins.
--check lists the undecided upstream patches and the carried ones missing from our series.

--dry-run writes nothing in the checkout (the clones in work/upstream are still fetched) and
prints the same report, undecided patches included. Both modes exit 1 when a file needs a hand.

Then follow docs/updating.md: refresh the series against the new Chromium, build and test.
Upstream clones are kept in work/upstream.
"""
import difflib, re, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PINS = ROOT / 'upstream.txt'
DECISIONS = ROOT / 'docs/helium-patch-decisions.md'
CARRIED = ('Want', 'Want while cheap')
DRY = False  # --dry-run: report only, write nothing in the checkout.
# Longer than any line a vendored file starts with, so a conflict marker can't be content.
MARK = 32
# Upstream repo: URL, our folder for its files, and the upstream paths we vendor.
REPOS = {
    'helium': ('https://github.com/imputnet/helium.git', ROOT, (
        'chromium_version.txt', 'deps.ini', 'devutils/', 'domain_regex.list',
        'domain_substitution.list', 'downloads.ini', 'flags.gn', 'i18n/', 'patches/',
        'pruning.list', 'resources/', 'revision.txt', 'shell.nix', 'utils/', 'version.txt')),
    'helium-linux': ('https://github.com/imputnet/helium-linux.git', ROOT / 'linux', (
        'docker/', 'flags.linux.gn', 'package/', 'patches/', 'pubkey.asc', 'revision.txt',
        'scripts/')),
}


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True,
                          text=True).stdout


def clone(name):
    path = ROOT / 'work/upstream' / name
    if not path.exists():
        subprocess.run(['git', 'clone', '--quiet', '--bare', '--filter=blob:none',
                        REPOS[name][0], str(path)], check=True)
    git(path, 'fetch', '--quiet', '--tags', '--force', 'origin', '+refs/heads/*:refs/heads/*')
    return path


def show(repo, ref, path):
    return subprocess.run(['git', '-C', str(repo), 'show', f'{ref}:{path}'], check=True,
                          capture_output=True).stdout


def copy(repo, ref, path, dest):
    """Writes path at ref to dest with upstream's executable bit."""
    if DRY:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(show(repo, ref, path))
    mode = git(repo, 'ls-tree', ref, '--', path).split(' ', 1)[0]
    dest.chmod(0o755 if mode == '100755' else 0o644)


def entries(text):
    return [l.strip() for l in text.splitlines() if l.strip() and not l.startswith('#')]


def decisions():
    """Maps each patch in the decisions doc to whether we carry it."""
    result, carried = {}, False
    for line in DECISIONS.read_text().splitlines():
        if line.startswith('## '):
            carried = line[3:].split(' (')[0] in CARRIED
        elif m := re.match(r'- `([^`]+)`', line):
            result[m[1] + '.patch'] = carried
    return result


def undecided(repo, ref, ours):
    """Upstream series entries at ref that are neither in our series nor decided."""
    decided = decisions()
    return [e for e in entries(show(repo, ref, 'patches/series').decode())
            if e not in entries(ours.read_text()) and e not in decided]


def carried_missing(repo, ref, ours):
    """Upstream series entries at ref decided as carried but missing from our series."""
    decided = decisions()
    return [e for e in entries(show(repo, ref, 'patches/series').decode())
            if decided.get(e) and e not in entries(ours.read_text())]


def update_series(repo, old, new, dest, report):
    ours_path = dest / 'patches/series'
    ours = ours_path.read_text().splitlines()
    old_e, new_e = (entries(show(repo, r, 'patches/series').decode()) for r in (old, new))
    decided = decisions()
    for entry in old_e:
        if entry not in new_e and entry in ours:
            ours.remove(entry)
            report.append(f'removed upstream, out of the series: {entry}')
    # An old entry decided as carried but missing was left out while undecided ("Undecided").
    for i, entry in enumerate(new_e):
        if entry in ours or not decided.get(entry):
            continue
        before = [e for e in new_e[:i] if e in ours]
        at = ours.index(before[-1]) + 1 if before else 0
        ours.insert(at, entry)
        copy(repo, new, f'patches/{entry}', dest / 'patches' / entry)
        report.append(f'{"added after a decision" if entry in old_e else "new upstream patch, added"}'
                      f': {entry}')
    if not DRY:
        ours_path.write_text('\n'.join(ours) + '\n')
    return [e for e in new_e if e not in old_e and e not in ours]


def update_files(repo, old, new, dest, vendored, left_out, report):
    # Mode-only changes are listed too (status M), so a script that becomes
    # executable upstream does here.
    changes = git(repo, 'diff', '--name-status', '--no-renames', old, new).splitlines()
    for status, path in (line.split('\t') for line in changes):
        if not path.startswith(vendored) or path == 'patches/series':
            continue
        if path.startswith('patches/') and path.removeprefix('patches/') in left_out:
            continue
        ours = dest / path
        if status == 'A':
            if not path.startswith('patches/'):
                copy(repo, new, path, ours)
                report.append(f'added: {ours.relative_to(ROOT)}')
            continue
        if not ours.exists():
            continue  # A dropped patch or a file we don't carry.
        base = show(repo, old, path)
        if status == 'D':
            if ours.read_bytes() == base:
                if not DRY:
                    ours.unlink()
            else:
                report.append(f'NEEDS A HAND, removed upstream but changed here: {ours.relative_to(ROOT)}')
            continue
        theirs = show(repo, new, path)
        if ours.read_bytes() == base:
            copy(repo, new, path, ours)
            continue
        before = ours.read_bytes()
        merged, conflicts = merge(before, base, theirs)
        rel = ours.relative_to(ROOT)
        if conflicts:
            if not DRY and merged != before:
                ours.write_bytes(merged)
            report.append(f'NEEDS A HAND, merge conflict, kept our side: {rel}')
            report.append(f'  all of upstream\'s change: git -C {repo.relative_to(ROOT)} diff '
                          f'{old} {new} -- {path}')
            for touches, hunk in conflicts:
                where = f' in {touches}' if touches else ''
                # Upstream only moved hunk headers: the hunk's lines and our edit both stay.
                numbers = all(l[1:].startswith('@@') for l in hunk[1:] if l[:1] in '+-')
                report.append(f'  conflict{where}, upstream changed'
                              f'{" line numbers only" if numbers else ""}:')
                report.extend('    ' + line for line in hunk)
        elif merged != before:
            if not DRY:
                ours.write_bytes(merged)
            report.append(f'merged with our changes: {rel}')


def merge(ours, base, theirs):
    """Three-way merges upstream's base -> theirs change into ours.

    Returns the merged bytes, with our side in each conflict, and, per conflict, the Chromium file it is in (for a patch file: the
    last +++ line before the conflict, else the first one in it; None if there is none) and
    upstream's change there as unified diff lines.
    """
    tmp = ROOT / 'work/tmp'
    tmp.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=tmp) as d:
        files = [Path(d) / name for name in ('ours', 'base', 'theirs')]
        for file, data in zip(files, (ours, base, theirs)):
            file.write_bytes(data)
        merged = subprocess.run(['git', 'merge-file', '-p', '--diff3', f'--marker-size={MARK}',
                                 *map(str, files)], capture_output=True)
    if merged.returncode < 0 or merged.returncode > 127:
        raise RuntimeError(merged.stderr.decode())
    conflicts, touches, part = [], None, None
    for line in merged.stdout.decode(errors='replace').splitlines():
        if line.startswith('<' * MARK):
            part, sides, ours_side = 'ours', {'base': [], 'theirs': []}, touches
        elif part and line.startswith('|' * MARK):
            part = 'base'
        elif part and line.startswith('=' * MARK):
            part = 'theirs'
        elif part and line.startswith('>' * MARK):
            inside = [m[1] for l in sides['base'] + sides['theirs']
                      if (m := re.match(r'\+\+\+ b/(\S+)', l))]
            hunk = list(difflib.unified_diff(sides['base'], sides['theirs'], 'old', 'new',
                                             lineterm=''))[2:]
            conflicts.append((ours_side or (inside[0] if inside else None), hunk))
            part = None
        elif part in ('base', 'theirs'):
            sides[part].append(line)
        elif m := re.match(r'\+\+\+ b/(\S+)', line):
            touches = m[1]
    if conflicts:
        with tempfile.TemporaryDirectory(dir=tmp) as d:
            files = [Path(d) / name for name in ('ours', 'base', 'theirs')]
            for file, data in zip(files, (ours, base, theirs)):
                file.write_bytes(data)
            return subprocess.run(['git', 'merge-file', '-p', '--ours', *map(str, files)],
                                  capture_output=True, check=True).stdout, conflicts
    return merged.stdout, conflicts


def main():
    global DRY
    args = sys.argv[1:]
    DRY = '--dry-run' in args
    args = [a for a in args if a != '--dry-run']
    pins = dict(line.split() for line in entries(PINS.read_text()))
    if args == ['--check']:
        missing = [(n, e) for n in REPOS
                   for e in undecided(clone(n), pins[n], REPOS[n][1] / 'patches/series')]
        for name, entry in missing:
            print(f'{name} {pins[name]}: {entry} is neither in our series nor in {DECISIONS.name}')
        absent = [(n, e) for n in REPOS
                  for e in carried_missing(clone(n), pins[n], REPOS[n][1] / 'patches/series')]
        for name, entry in absent:
            print(f'{name} {pins[name]}: {entry} is decided as carried but missing from our series; '
                  f'tools/update_helium.py {pins["helium-linux"]} adds it')
        sys.exit(1 if missing or absent else 0)
    if len(args) != 1:
        sys.exit(__doc__)
    repos = {name: clone(name) for name in REPOS}
    # "160000 commit SHA\thelium-chromium"
    submodule = git(repos['helium-linux'], 'ls-tree', args[0], 'helium-chromium').split()
    if submodule[:2] != ['160000', 'commit']:
        sys.exit(f'helium-linux {args[0]} has no helium-chromium submodule')
    targets = {'helium': submodule[2], 'helium-linux': args[0]}
    missing = [(n, e) for n in REPOS
               for e in undecided(repos[n], targets[n], REPOS[n][1] / 'patches/series')
               if e not in entries(show(repos[n], pins[n], 'patches/series').decode())]
    if missing:
        for name, entry in missing:
            subject = git(repos[name], 'log', '-1', '--format=%s', targets[name], '--',
                          f'patches/{entry}').strip()
            print(f'needs a decision, new {name} patch: {entry}\n  {subject}\n  read it: git -C '
                  f'work/upstream/{name} show {targets[name]}:patches/{entry}')
        if not DRY:
            sys.exit(f'Ask the maintainer whether to keep each one, record the answers in '
                     f'{DECISIONS.relative_to(ROOT)}, then run this again.')
    report = []
    for name, (_, dest, vendored) in REPOS.items():
        old, new = pins[name], targets[name]
        left_out = update_series(repos[name], old, new, dest, report)
        update_files(repos[name], old, new, dest, vendored, left_out, report)
        report.append(f'{name}: {old} -> {new}')
    if not DRY:
        PINS.write_text(re.sub(r'^(helium(?:-linux)?) .*$',
                               lambda m: f'{m[1]} {targets[m[1]]}', PINS.read_text(), flags=re.M))
    print('\n'.join(report))
    hand = sum(line.startswith('NEEDS A HAND') for line in report)
    if DRY:
        print(f'dry run, nothing written; {hand} files need a hand, '
              f'{len(missing)} new upstream patches need a decision')
    sys.exit(1 if hand or missing else 0)


if __name__ == '__main__':
    main()
