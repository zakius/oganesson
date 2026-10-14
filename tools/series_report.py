#!/usr/bin/env python3
"""Apply every patch to an already prepared tree (see check_patches.py --keep), skipping failures.

Lists every failing patch, as check_patches.py does, on a tree regen.py may have left patched.
Usage: [FUZZ=N] tools/series_report.py WORKDIR   (WORKDIR holds src/ and cache/)
"""
import os, subprocess, sys
from pathlib import Path

from check_patches import apply_series, oganesson, report

ROOT = Path(__file__).resolve().parent.parent
work = Path(sys.argv[1])
src = work / 'src'
for repo in [src, *src.glob('third_party/*/src'), src / 'third_party/skia',
             src / 'third_party/search_engines_data/resources']:
    if (repo / '.git').exists():
        # regen.py leaves a commit per patch on top of the checkout; go back to the checkout.
        root = subprocess.run(['git', '-C', str(repo), 'rev-list', '--max-parents=0', 'HEAD'],
                              capture_output=True, text=True, check=True).stdout.split()[0]
        subprocess.run(['git', '-C', str(repo), 'reset', '-q', '--hard', root], check=True)
        subprocess.run(['git', '-C', str(repo), 'clean', '-fdxq'], check=True)
for action, extra in (('unpack', [str(src)]),):
    subprocess.run([str(ROOT / 'utils/downloads.py'), action, '-i', str(ROOT / 'deps.ini'),
                    '-c', str(work / 'cache'), *extra, '--components', 'ublock_origin', 'onboarding'],
                   check=True, capture_output=True)
oganesson.copy_new_files(src)
report(apply_series(src, int(os.environ.get('FUZZ', '0'))))
