#!/usr/bin/env python3
"""Moves the helium, linux/helium-linux and windows/helium-windows submodules to a release.

Usage: tools/update_helium.py [--dry-run] LINUX_TAG   (for example 0.19.2.1)

We follow helium-linux: its helium-chromium submodule names the Helium commit a
release builds on, so helium/ moves there and linux/helium-linux to LINUX_TAG.
helium-windows tags its releases with the same version on the same Helium
commit, usually a few hours later; windows/helium-windows moves to that tag, and
stays when it doesn't exist yet or builds on another Helium commit.
The report lists the patches Helium's and helium-windows' series gain, which
oganesson carries unless they go into patches/helium-drops.txt or
windows/helium-windows-drops.txt, and the ones they lose, and fails when a drop
names a patch the new series no longer has. --dry-run only reports.

On a new Chromium milestone it also pins the milestone's PGO profiles in
pgo-profiles.txt (docs/updating.md, "PGO profiles").

Then follow docs/updating.md: ./oganesson.py check-patches, tools/regen.py for
our patches that fail, build and test. Exits 1 when a drop or helium-windows
needs a hand.
"""
import base64, subprocess, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import oganesson  # pylint: disable=wrong-import-position


def git(repo, *args, check=True):
    return subprocess.run(['git', '-C', str(repo), *args], check=check, capture_output=True,
                          text=True).stdout


def series(repo, ref):
    return [line.strip() for line in git(repo, 'show', f'{ref}:patches/series')
            .splitlines() if line.strip() and not line.startswith('#')]


def changes(name, repo, ref, drops_file):
    """Reports how repo's series changes at ref; the drops it no longer has."""
    old, new = series(repo, 'HEAD'), series(repo, ref)
    added = [p for p in new if p not in old]
    print(f'{len(added)} new {name} patches, carried unless dropped:')
    print(''.join(f'  {p}\n' for p in added), end='')
    print(f'{len(set(old) - set(new))} removed:')
    print(''.join(f'  {p}\n' for p in old if p not in new), end='')
    stale = sorted(oganesson.drops(drops_file) - set(new))
    for drop in stale:
        print(f'{drops_file.relative_to(ROOT)} names {drop}, which the new series no longer has')
    return stale


PGO_PINS = ROOT / 'pgo-profiles.txt'
PGO_NAME = 'https://chromium.googlesource.com/chromium/src/+/refs/tags/{}/chrome/build/{}.pgo.txt'


def pin_pgo_profiles(version):
    """Pins Chromium `version`'s own profiles where the pin is another
    milestone's. A profile's name has the milestone's branch number after the
    target (chrome-linux-8103-...), as the version has it third (157.0.8103.78)."""
    branch = version.split('.')[2]
    lines = []
    for line in PGO_PINS.read_text().splitlines():
        if line and not line.startswith('#'):
            target, pinned = line.split()
            if pinned.split('-')[2] != branch:
                with urllib.request.urlopen(PGO_NAME.format(version, target) + '?format=TEXT') as r:
                    pinned = base64.b64decode(r.read()).decode().strip()
                print(f'{PGO_PINS.name}: {target} {pinned}')
                line = f'{target} {pinned}'
        lines.append(line)
    PGO_PINS.write_text('\n'.join(lines) + '\n')


def main():
    args = sys.argv[1:]
    dry = '--dry-run' in args
    args = [a for a in args if a != '--dry-run']
    if len(args) != 1:
        sys.exit(__doc__)
    tag = args[0]
    git(oganesson.HELIUM_LINUX, 'fetch', '-q', '--tags', 'origin')
    git(oganesson.HELIUM_WINDOWS, 'fetch', '-q', '--tags', 'origin')
    target = git(oganesson.HELIUM_LINUX, 'rev-parse', f'{tag}:helium-chromium').strip()
    windows = git(oganesson.HELIUM_WINDOWS, 'rev-parse', '-q', '--verify', f'{tag}:helium-chromium',
                  check=False).strip() == target
    git(oganesson.HELIUM, 'fetch', '-q', 'origin', target)
    print(f'helium {git(oganesson.HELIUM, "rev-parse", "--short", "HEAD").strip()} -> '
          f'{target[:9]}, helium-linux -> {tag}, helium-windows -> '
          + (tag if windows else f'stays: it has no {tag} on Helium {target[:9]}'))
    stale = changes('Helium', oganesson.HELIUM, target, oganesson.DROPS)
    if windows:
        stale += changes('helium-windows', oganesson.HELIUM_WINDOWS, tag, oganesson.WINDOWS_DROPS)
    if not dry:
        git(oganesson.HELIUM, 'checkout', '-q', target)
        git(oganesson.HELIUM_LINUX, 'checkout', '-q', tag)
        if windows:
            git(oganesson.HELIUM_WINDOWS, 'checkout', '-q', tag)
        pin_pgo_profiles((oganesson.HELIUM / 'chromium_version.txt').read_text().strip())
        print('moved the submodules; commit them with the patch fixes')
    return 1 if stale or not windows else 0


if __name__ == '__main__':
    sys.exit(main())
