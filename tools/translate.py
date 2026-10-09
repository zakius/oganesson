#!/usr/bin/env python3
"""Puts our translations (l10n/<lang>.json) into a prepared tree's .xtb files.

Our strings are the messages of src/chrome/app/oganesson_*.grdp and the ones
our patches (patches/oganesson) add to Chromium's .grd/.grdp files. English is
their source text; l10n/<lang>.json has, per message, its name, the English
text it translates ("source") and the translation ("message"), the format of
Helium's i18n/translations. grit matches a translation to its message by the
English text, so a changed English text needs a new translation.

All our messages go into chrome/app/generated_resources.grd's .xtb files.

Usage: translate.py SRC_TREE    apply, after Helium's i18n_apply.py
       translate.py --check     each of our messages has a current
                                translation in every l10n/<lang>.json
"""
import json, re, sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'utils'))
L10N = ROOT / 'l10n'
MESSAGE = re.compile(r'<message name="(\w+)"[^>]*>\s*(.*?)\s*</message>', re.S)


def our_messages():
    """(name, English text) of every message we add, once each."""
    found = {}
    for grdp in sorted((ROOT / 'src').rglob('oganesson_*.grdp')):
        for name, message in MESSAGE.findall(grdp.read_text()):
            found[(name, re.sub(r'\s+', ' ', message))] = None
    for patch in sorted((ROOT / 'patches/oganesson').rglob('*.patch')):
        for section in re.split(r'(?m)^(?=--- a/)', patch.read_text()):
            if not re.match(r'--- a/\S+\.grdp?\n', section):
                continue
            # The patched file's side of each hunk; a message counts as ours
            # when a line of it is added.
            for hunk in re.split(r'(?m)^@@.*\n', section)[1:]:
                lines = [l for l in hunk.splitlines() if l[:1] in ' +']
                text = '\n'.join(l[1:] for l in lines)
                added = [l[0] == '+' for l in lines]
                for m in MESSAGE.finditer(text):
                    first, last = text.count('\n', 0, m.start()), text.count('\n', 0, m.end())
                    if any(added[first:last + 1]):
                        found[(m[1], re.sub(r'\s+', ' ', m[2]))] = None
    return list(found)


def placeholders(text):
    return sorted(re.findall(r'<ph name="(\w+)"', text))


def load(lang_file):
    return {(t['name'], t['source']): t['message'] for t in json.loads(lang_file.read_text())}


def check():
    messages = our_messages()
    errors = []
    for lang_file in sorted(L10N.glob('*.json')):
        translations = load(lang_file)
        for name, text in messages:
            message = translations.get((name, text))
            if message is None:
                errors.append(f'{lang_file.name}: no translation of {name}: {text}')
            elif placeholders(message) != placeholders(text):
                errors.append(f'{lang_file.name}: {name} has other placeholders than its English')
        for name, text in translations.keys() - set(messages):
            errors.append(f'{lang_file.name}: {name} translates a text we no longer have: {text}')
    print('\n'.join(errors) or f'translate.py: {len(messages)} messages, all translated')
    return 1 if errors else 0


def apply(tree):
    import i18n_apply, name_substitution_utils
    name_substitution_utils.add_grit_to_path(tree)
    xtbs = i18n_apply.parse_xtb_paths(tree / 'chrome/app/generated_resources.grd')
    for lang_file in sorted(L10N.glob('*.json')):
        entries = [(i18n_apply.get_id(name, '', text, None), i18n_apply.to_xtb_message(message))
                   for (name, text), message in load(lang_file).items()]
        i18n_apply.insert_into_xtb(xtbs[lang_file.stem], entries)
        print(f'translate.py: {lang_file.stem}: {len(entries)} translations')


if __name__ == '__main__':
    if sys.argv[1:] == ['--check']:
        sys.exit(check())
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    apply(Path(sys.argv[1]))
