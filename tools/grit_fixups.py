#!/usr/bin/env python3
"""Brings grit's checked-in bookkeeping in line with our resources, after the patches.

.gritdeps files list every file a .grd reads, and the build fails when one is out of date; each is
regenerated rather than patched, so our .grdp files need no hunk there.

resource_ids.spec reserves a number of resource IDs ("META" sizes) for each .grd generated at build
time. A WebUI folder our src/ adds TypeScript files to gets one more ID per file: each compiles to
one bundled .js file.

Usage: tools/grit_fixups.py SRC_DIR
"""
import re, subprocess, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = 'tools/gritsettings/resource_ids.spec'


def bump_sizes(spec, counts):
    """spec with each folder's "includes" size raised by its count of our files."""
    for folder, count in sorted(counts.items()):
        key = re.escape(f'"<(SHARED_INTERMEDIATE_DIR)/chrome/browser/resources/{folder}/resources.grd"')
        spec, found = re.subn('(' + key + r': \{\s*"META": \{"sizes": \{"includes": \[)(\d+)',
                              lambda m: m[1] + str(int(m[2]) + count), spec)
        if not found:
            sys.exit(f'grit_fixups: no generated resources.grd with a size for {folder} in {SPEC}')
    return spec


def our_resource_counts():
    """Our TypeScript files per top folder of chrome/browser/resources."""
    resources = ROOT / 'src/chrome/browser/resources'
    return Counter(p.relative_to(resources).parts[0] for p in resources.rglob('*.ts'))


def main():
    src = Path(sys.argv[1])
    for name in subprocess.run(['git', '-C', str(src), 'ls-files', '*.gritdeps'], check=True,
                               capture_output=True, text=True).stdout.split():
        deps = subprocess.run([sys.executable, 'tools/grit/grit_info.py', '--all-inputs',
                               name.removesuffix('.gritdeps')], cwd=src, check=True,
                              capture_output=True, text=True).stdout
        (src / name).write_text(deps)
    spec = src / SPEC
    spec.write_text(bump_sizes(spec.read_text(), our_resource_counts()))


if __name__ == '__main__':
    if sys.argv[1:] == ['--test']:
        text = ('  "<(SHARED_INTERMEDIATE_DIR)/chrome/browser/resources/app_settings/resources.grd": {\n'
                '    "META": {"sizes": {"includes": [45]}},\n    "includes": [2800],\n  },\n')
        out = bump_sizes(text, {'app_settings': 4})
        assert '[49]' in out and '[2800]' in out
        print('ok')
    else:
        main()
