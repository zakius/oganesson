#!/usr/bin/env python3
"""Moves the helium and linux/helium-linux submodules to a helium-linux release.

Usage: tools/update_helium.py [--dry-run] LINUX_TAG   (for example 0.19.2.1)

We follow helium-linux: its helium-chromium submodule names the Helium commit a
release builds on, so helium/ moves there and linux/helium-linux to LINUX_TAG.
The report lists the patches Helium's series gains, which oganesson carries
unless they go into patches/helium-drops.txt, and the ones it loses, and fails
when a drop names a patch the new series no longer has. --dry-run only reports.

Then follow docs/updating.md: ./oganesson.py check-patches, tools/regen.py for
our patches that fail, build and test. Exits 1 when a drop needs a hand.
"""
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import oganesson  # pylint: disable=wrong-import-position


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True,
                          text=True).stdout


def series(ref):
    return [line.strip() for line in git(oganesson.HELIUM, 'show', f'{ref}:patches/series')
            .splitlines() if line.strip() and not line.startswith('#')]


def main():
    args = sys.argv[1:]
    dry = '--dry-run' in args
    args = [a for a in args if a != '--dry-run']
    if len(args) != 1:
        sys.exit(__doc__)
    tag = args[0]
    git(oganesson.HELIUM_LINUX, 'fetch', '-q', '--tags', 'origin')
    target = git(oganesson.HELIUM_LINUX, 'rev-parse', f'{tag}:helium-chromium').strip()
    git(oganesson.HELIUM, 'fetch', '-q', 'origin', target)
    old, new = series('HEAD'), series(target)
    added = [p for p in new if p not in old]
    print(f'helium {git(oganesson.HELIUM, "rev-parse", "--short", "HEAD").strip()} -> '
          f'{target[:9]}, helium-linux -> {tag}')
    print(f'{len(added)} new Helium patches, carried unless dropped:')
    print(''.join(f'  {p}\n' for p in added), end='')
    print(f'{len(set(old) - set(new))} removed:')
    print(''.join(f'  {p}\n' for p in old if p not in new), end='')
    drops = {line.split('\t')[0] for line in oganesson.DROPS.read_text().splitlines()
             if line.strip() and not line.startswith('#')}
    stale = sorted(drops - set(new))
    for drop in stale:
        print(f'patches/helium-drops.txt names {drop}, which the new series no longer has')
    if not dry:
        git(oganesson.HELIUM, 'checkout', '-q', target)
        git(oganesson.HELIUM_LINUX, 'checkout', '-q', tag)
        print('moved both submodules; commit them with the patch fixes')
    return 1 if stale else 0


if __name__ == '__main__':
    sys.exit(main())
