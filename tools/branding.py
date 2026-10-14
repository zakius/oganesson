#!/usr/bin/env python3
"""Renames the product in UI strings from Helium to oganesson.

Runs after Helium's name_substitution.py (Chrome -> Helium) and i18n_apply.py,
over the same .grd/.grdp/.xtb files. Only the whole word "Helium" in <message>
text changes. Phrases that name the upstream project or its hosted services
(KEEP) stay. Flag names and descriptions, helium:// URLs, helium.* prefs and
code identifiers are not in these files, or are lowercase, so they stay too.

A changed message gets a new grit fingerprint, so its .xtb translations are
re-keyed to keep applying. Their text is renamed too, except where the English
message also had a KEEP phrase: word order differs between languages, so the
two uses of "Helium" can't be told apart there, and the translation keeps
"Helium" throughout.

Usage: branding.py SRC_TREE [--dry-run]
"""

import argparse
import multiprocessing
import re
import sys
import xml.etree.ElementTree as xml
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

# Helium's utils, with oganesson's fixes (oganesson.py's helium_tree()).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'work/helium-tree/utils'))
# pylint: disable=wrong-import-position
import name_substitution_utils as util
from name_substitution import get_substitutable_files

NAME = 'oganesson'
KEEP = re.compile(r'Helium (?:services|servers|Partner|open source project)'
                  r'|The Helium Authors|development of Helium|verified by Helium')
PATTERN = re.compile(rf'({KEEP.pattern})|\bHelium\b')
# name_substitution.py protects &#36; the same way: ElementTree would decode
# it into a bare $, which grit reads as a placeholder.
DOLLAR = '!!dollar-sign-literal!!'

# Old fingerprint -> new, and the old fingerprints of messages that also had
# a KEEP phrase. Set before the xtb pool forks.
FP_MAP = {}
MIXED = set()


def rename(elem):
    """Renames the product in elem's text and its children's; True if changed."""
    changed = False
    for node in elem.iter():
        for attr in ('text', 'tail'):
            old = getattr(node, attr)
            if not old or (node is elem and attr == 'tail'):
                continue
            new = PATTERN.sub(lambda m: m.group(1) or NAME, old)
            if new != old:
                setattr(node, attr, new)
                changed = True
    return changed


def load(path):
    """The parsed file, and whether it starts with an XML declaration."""
    text = path.read_text(encoding='utf-8').replace('&#36;', DOLLAR)
    return xml.fromstring(text, util.get_parser()), text.startswith('<?xml')


def save(path, root, declaration):
    # Keep a file without a declaration without one: Helium's onboarding
    # generate-i18n.mts reads the first XML node as <grit-part>.
    text = xml.tostring(root, encoding='unicode', xml_declaration=declaration)
    path.write_text(text.replace(DOLLAR, '&#36;'), encoding='utf-8')


def do_grd(args):
    path, dry_run = args
    if 'Helium' not in path.read_text(encoding='utf-8'):
        return {}, set(), [], []
    root, declaration = load(path)
    fp_map, mixed, changes, kept = {}, set(), [], []
    for msg in root.iter('message'):
        before = ' '.join(''.join(msg.itertext()).split())
        old_fp = util.compute_fp(msg)
        if KEEP.search(before):
            kept.append((msg.get('name'), before))
        if rename(msg):
            fp_map[old_fp] = util.compute_fp(msg)
            if KEEP.search(before):
                mixed.add(old_fp)
            changes.append((msg.get('name'), before, ' '.join(''.join(msg.itertext()).split())))
    if changes and not dry_run:
        save(path, root, declaration)
    return fp_map, mixed, changes, kept


def do_xtb(args):
    path, dry_run = args
    root, declaration = load(path)
    count = 0
    for translation in root.iter('translation'):
        old_fp = translation.get('id')
        if old_fp in FP_MAP:
            translation.set('id', FP_MAP[old_fp])
            if old_fp not in MIXED:
                rename(translation)
            count += 1
    if count and not dry_run:
        save(path, root, declaration)
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n', 1)[0])
    parser.add_argument('tree', type=Path)
    parser.add_argument('--dry-run', action='store_true', help='print every change, write nothing')
    args = parser.parse_args()
    util.add_grit_to_path(args.tree)
    # fork: the workers inherit grit's sys.path entry and FP_MAP.
    pool = lambda: ProcessPoolExecutor(mp_context=multiprocessing.get_context('fork'))

    with pool() as executor:
        grds = list(get_substitutable_files(args.tree, ['grd', 'grdp']))
        results = list(executor.map(do_grd, [(p, args.dry_run) for p in grds]))
    changes, kept = [], {}
    for fp_map, mixed, file_changes, file_kept in results:
        FP_MAP.update(fp_map)
        MIXED.update(mixed)
        changes += file_changes
        kept.update(file_kept)

    with pool() as executor:
        xtbs = list(get_substitutable_files(args.tree, ['xtb']))
        translations = sum(executor.map(do_xtb, [(p, args.dry_run) for p in xtbs]))

    if args.dry_run:
        for name, before, after in changes:
            print(f'{name}\n  - {before}\n  + {after}')
    print(f'Kept {len(kept)} messages with upstream Helium phrases (whole message where it has no'
          f' other use of the name):')
    for name, text in sorted(kept.items()):
        print(f'  {name}: {text}')
    files = sum(1 for r in results if r[2])
    print(f'Renamed Helium to {NAME} in {len(changes)} messages ({len(FP_MAP)} distinct) in'
          f' {files} files, and re-keyed {translations} translations'
          f' ({len(MIXED)} of those messages keep "Helium" in translations)')


if __name__ == '__main__':
    main()
