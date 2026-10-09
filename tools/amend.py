#!/usr/bin/env python3
"""Rewrite a patch's sections from files edited in the prepared tree.

Usage: tools/amend.py PATCH FILE...

PATCH is a series entry under patches/ (e.g. oganesson/core/firefox-menus.patch), FILE a path in
the Chromium tree (e.g. chrome/browser/foo.cc). Edit FILE in work/helium-linux/build/src, then run
this: it rebuilds FILE's section of PATCH (adding one if PATCH didn't touch FILE, dropping it if
the edit is undone) and stamps the tree, so `./oganesson.py build` compiles the edit without
preparing the tree again. The stamp checks every other input as `./oganesson.py stamp` does; when
it refuses, PATCH is left as it was.

The tree file holds every patch of the series and Helium's domain substitution. To get PATCH's
part alone, the script applies the series to FILE's original (src/ or the fetched source) up to
PATCH, keeps the tree's changes on top of the substituted result, and reverse-applies the later
patches that touch FILE. New files belong in src/, not in a patch.

It refuses what it can't rebuild: .grd, .grdp and .xtb files (branding and translations rewrite
them after patching), files from deps.ini downloads (no git original), and an edit whose diff
context holds domain-substituted text. Edit those patches by hand and check them with
`./oganesson.py check-patches`.
"""
import subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'work/helium-linux/build/src'
# patch and diff write temporary files; /tmp may be a small tmpfs.
TMP = ROOT / 'work/tmp'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'utils'))
import oganesson  # pylint: disable=wrong-import-position
from domain_substitution import DomainRegexList  # pylint: disable=wrong-import-position

DOMSUB = DomainRegexList(ROOT / 'domain_regex.list')
DOMSUB_FILES = set((ROOT / 'domain_substitution.list').read_text().split())


def apply(content, section, reverse=False, failure='patch failed'):
    with tempfile.TemporaryDirectory(dir=TMP) as d:
        d = Path(d)
        (d / 'f').write_bytes(content)
        (d / 'p').write_text(section)
        r = subprocess.run(['patch', '-s', '--fuzz=0', '--no-backup-if-mismatch', '-o', str(d / 'o')]
                           + (['-R'] if reverse else []) + [str(d / 'f'), str(d / 'p')],
                           capture_output=True, text=True)
        if r.returncode:
            sys.exit(f'{failure}: {r.stdout}{r.stderr}')
        return (d / 'o').read_bytes()


def diff(a, b, name):
    with tempfile.TemporaryDirectory(dir=TMP) as d:
        d = Path(d)
        (d / 'a').write_bytes(a)
        (d / 'b').write_bytes(b)
        return subprocess.run(['diff', '-u', '--label', f'a/{name}', '--label', f'b/{name}',
                               str(d / 'a'), str(d / 'b')], capture_output=True, text=True).stdout


def original(name, ser):
    """FILE before any patch: our src/ copy, the fetched source (from the git repository that
    holds it, such as DevTools' own), or empty for a file a patch of the series creates."""
    if (ROOT / 'src' / name).exists():
        return (ROOT / 'src' / name).read_bytes()
    path = SRC / name
    r = subprocess.run(['git', '-C', str(path.parent), 'show', f'HEAD:./{path.name}'],
                       capture_output=True)
    if r.returncode == 0:
        return r.stdout
    created = f'--- /dev/null\n+++ b/{name}'
    if any(created in p.read_text() for p in ser):
        return b''
    sys.exit(f'{name} has no original in git or src/, and no patch creates it (a deps.ini '
             'download?); edit its patch by hand')


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    TMP.mkdir(parents=True, exist_ok=True)
    target = ROOT / 'patches' / sys.argv[1]
    ser = oganesson.series_patches()
    if target not in ser:
        sys.exit(f'{sys.argv[1]} is not in patches/series')
    idx = ser.index(target)
    pre, secs = oganesson.sections(target.read_text())
    for name in sys.argv[2:]:
        if name.endswith(('.grd', '.grdp', '.xtb')):
            sys.exit(f'{name}: branding and translations rewrite it after patching; '
                     'edit its patch by hand')
        full = original(name, ser)
        before = None
        later = []
        for i, p in enumerate(ser):
            if i == idx:
                before = full
            for section_name, s in oganesson.sections(p.read_text())[1]:
                if section_name == name:
                    full = apply(full, s)
                    if i > idx:
                        later.append(s)
        tree = (SRC / name).read_bytes()
        substituted = full
        if name in DOMSUB_FILES:
            text = full.decode()
            for pair in DOMSUB.regex_pairs:
                text = pair.pattern.sub(pair.replacement, text)
            substituted = text.encode()
        after = full if substituted == tree else apply(
            full, diff(substituted, tree, name),
            failure=f'{name}: the edit is next to domain-substituted text; edit the patch by hand')
        for s in reversed(later):
            after = apply(after, s, reverse=True)
        new = diff(before, after, name)
        for i, (section_name, _) in enumerate(secs):
            if section_name == name:
                if new:
                    secs[i] = (name, new)
                else:
                    del secs[i]
                break
        else:
            if new:
                secs.append((name, new))
    target.write_text(pre + ''.join(s for _, s in secs))
    # The patch was just made from the tree, so only the other inputs are checked. On a
    # refusal the rewritten patch stays: it holds the edit, which a build that prepares
    # the tree again would otherwise erase.
    try:
        oganesson.write_stamp(amended=str(target.relative_to(ROOT)))
    except SystemExit as error:
        sys.exit(f'{error.code}\n{sys.argv[1]} holds the edit; the tree isn\'t stamped, so the next '
                 'build prepares it again with every patch.')


main()
